"""
Measurements API  (WP5)
-----------------------
Endpoints:
  POST /measurements/upload    — CSV file upload from Android app
  POST /measurements/batch     — JSON array of measurements
  GET  /measurements           — list raw measurements (paginated + filtered)
  POST /measurements/simulate  — generate synthetic data (dev only)
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.raw_measurement import RawMeasurement, Technology
from app.schemas.raw_measurement import (
    RawMeasurementCreate,
    RawMeasurementRead,
    UploadResult,
)
from app.services.cleaning import clean_batch
from app.services.ingestion import (
    bulk_insert,
    generate_simulation_data,
    parse_csv,
)

router = APIRouter(prefix="/measurements", tags=["measurements"])


# ── POST /measurements/upload ─────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=UploadResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a CSV file of measurements from the Android app",
)
async def upload_csv(
    file: Annotated[UploadFile, File(description="CSV file exported by the mobile app")],
    session: AsyncSession = Depends(get_db),
) -> UploadResult:
    """
    Parse a CSV file, run the cleaning pipeline, and bulk-insert valid rows.

    The response body reports how many rows were accepted and rejected, along
    with a list of human-readable rejection reasons for debugging.

    Expected CSV columns (order-independent, case-insensitive):
      timestamp, lat, lon, accuracy, speed, bearing, mcc, mnc, technology,
      cell_id, rsrp, rsrq, sinr
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .csv files are accepted",
        )

    parsed, parse_errors = await parse_csv(file)
    cleaned, clean_errors = clean_batch(parsed)

    inserted = await bulk_insert(session, cleaned)

    total_received = len(parsed) + len(parse_errors)
    rejected = total_received - inserted

    return UploadResult(
        accepted=inserted,
        rejected=rejected,
        errors=parse_errors + clean_errors,
    )


# ── POST /measurements/batch ──────────────────────────────────────────────────

@router.post(
    "/batch",
    response_model=UploadResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a JSON array of measurements",
)
async def batch_ingest(
    rows: list[RawMeasurementCreate],
    session: AsyncSession = Depends(get_db),
) -> UploadResult:
    """
    Ingest a JSON array of measurements through the cleaning pipeline and
    insert the valid ones into the database.

    This endpoint is useful for:
      • Testing without a real CSV file
      • Future SDK clients that prefer JSON
    """
    if not rows:
        return UploadResult(accepted=0, rejected=0, errors=["Empty payload"])

    cleaned, errors = clean_batch(rows)
    inserted = await bulk_insert(session, cleaned)
    rejected = len(rows) - inserted

    return UploadResult(accepted=inserted, rejected=rejected, errors=errors)


# ── GET /measurements ─────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[RawMeasurementRead],
    summary="List raw measurements with optional filters",
)
async def list_measurements(
    operator_id: str | None = Query(default=None, description="MCC+MNC string, e.g. 28601"),
    technology: Technology | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, description="ISO-8601 UTC start time"),
    to_ts: datetime | None = Query(default=None, description="ISO-8601 UTC end time"),
    is_cleaned: bool | None = Query(default=None, description="Filter by cleaning status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[RawMeasurement]:
    """
    Return a paginated list of raw measurements.

    All filter parameters are optional and combinable.  The default page size
    is 100 rows (max 1 000) to prevent accidentally fetching the full table.
    """
    stmt = select(RawMeasurement).order_by(RawMeasurement.server_timestamp.desc())

    if operator_id:
        stmt = stmt.where(RawMeasurement.operator_id == operator_id)
    if technology:
        stmt = stmt.where(RawMeasurement.technology == technology)
    if from_ts:
        stmt = stmt.where(RawMeasurement.server_timestamp >= from_ts)
    if to_ts:
        stmt = stmt.where(RawMeasurement.server_timestamp <= to_ts)
    if is_cleaned is not None:
        stmt = stmt.where(RawMeasurement.is_cleaned == is_cleaned)

    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── POST /measurements/simulate ───────────────────────────────────────────────

@router.post(
    "/simulate",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="[DEV ONLY] Generate and insert synthetic measurements",
)
async def simulate_measurements(
    count: int = Query(default=500, ge=1, le=10_000, description="Number of rows to generate"),
    min_lat: float = Query(default=41.0, description="Bounding box minimum latitude"),
    min_lon: float = Query(default=28.9, description="Bounding box minimum longitude"),
    max_lat: float = Query(default=41.1, description="Bounding box maximum latitude"),
    max_lon: float = Query(default=29.1, description="Bounding box maximum longitude"),
    operator_id: str = Query(default="28601", description="MCC+MNC string"),
    technology: Technology = Query(default=Technology.LTE),
    hours_back: int = Query(default=24, ge=1, le=720),
    session: AsyncSession = Depends(get_db),
) -> UploadResult:
    """
    Generate synthetic measurements and insert them directly into the database.

    **Only available in development mode** (`APP_ENV=development`).

    Signal values follow realistic 3GPP distributions so the aggregation
    pipeline can be tested end-to-end without a real Android device.

    Default bounding box covers central Istanbul.
    """
    if settings.APP_ENV != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Simulation endpoint is only available in development mode",
        )

    rows = generate_simulation_data(
        count=count,
        bbox=[min_lat, min_lon, max_lat, max_lon],
        operator_id=operator_id,
        technology=technology,
        hours_back=hours_back,
    )

    # Simulation data skips cleaning — it is already within valid ranges.
    # Mark rows as cleaned=True so they are immediately available to the
    # aggregation engine.
    inserted = await bulk_insert(session, rows)

    # Mark all inserted rows as cleaned (bulk UPDATE)
    from sqlalchemy import update
    await session.execute(
        update(RawMeasurement)
        .where(RawMeasurement.is_cleaned == False)  # noqa: E712
        .values(is_cleaned=True)
    )

    return UploadResult(accepted=inserted, rejected=0, errors=[])
