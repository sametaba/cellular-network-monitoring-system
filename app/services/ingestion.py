"""
Ingestion Service  (WP5 — data intake layer)
--------------------------------------------
Handles:
  • CSV file parsing (mobile app uploads)
  • JSON batch validation
  • Bulk database inserts
  • Synthetic data generation for development/testing
"""

from __future__ import annotations

import io
import random
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import UploadFile
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_measurement import RawMeasurement, Technology
from app.schemas.raw_measurement import RawMeasurementCreate

# ── CSV column mapping ────────────────────────────────────────────────────────
# Maps expected CSV header names (from the Android app) to the internal
# schema field names.  The app currently writes these column names; if the
# format ever changes, update only this dict.
_CSV_COLUMN_MAP: dict[str, str] = {
    # timestamp variants
    "timestamp": "device_timestamp",
    "device_timestamp": "device_timestamp",
    "time": "device_timestamp",
    # location
    "lat": "lat",
    "latitude": "lat",
    "lon": "lon",
    "lng": "lon",
    "longitude": "lon",
    "accuracy": "precision",
    "precision": "precision",
    "speed": "speed",
    "bearing": "bearing",
    # operator / cell
    "mcc": "_mcc",   # intermediate — combined with mnc below
    "mnc": "_mnc",
    "operator_id": "operator_id",
    "technology": "technology",
    "tech": "technology",
    "cell_id": "cell_id",
    "cellid": "cell_id",
    # signal metrics
    "rsrp": "rsrp",
    "rsrq": "rsrq",
    "sinr": "sinr",
}

# RSRP value guard: some Android APIs return 0 or positive values when the
# reading is unavailable.  These sentinels are treated as null.
_RSRP_INVALID_SENTINELS = {0, 1, 99, 2147483647}

# ── CSV parsing ───────────────────────────────────────────────────────────────

async def parse_csv(file: UploadFile) -> tuple[list[RawMeasurementCreate], list[str]]:
    """
    Parse a CSV UploadFile into a list of RawMeasurementCreate objects.

    The file is read entirely into memory (acceptable for typical batch sizes
    < 50 MB).  Rows that fail Pydantic validation are skipped and their
    errors are collected.

    Returns:
        (valid_rows, parse_errors)
    """
    raw_bytes = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:
        return [], [f"CSV parse error: {exc}"]

    # Normalise column names: lowercase + strip whitespace
    df.columns = [c.strip().lower() for c in df.columns]

    # Rename columns according to the mapping
    rename_map = {col: mapped for col, mapped in _CSV_COLUMN_MAP.items() if col in df.columns}
    df = df.rename(columns=rename_map)

    # Combine MCC + MNC into operator_id when they arrive as separate columns
    if "_mcc" in df.columns and "_mnc" in df.columns and "operator_id" not in df.columns:
        df["operator_id"] = (
            df["_mcc"].astype(str).str.zfill(3)
            + df["_mnc"].astype(str).str.zfill(2)
        )
        df = df.drop(columns=["_mcc", "_mnc"])

    # operator_id must always be a string.  Pandas reads plain numeric CSV
    # values as int64 (e.g. 28601 → 28601), which fails Pydantic str validation.
    if "operator_id" in df.columns:
        df["operator_id"] = df["operator_id"].astype(str)

    # Replace sentinel RSRP values with NaN → will become None in Pydantic
    if "rsrp" in df.columns:
        df["rsrp"] = df["rsrp"].apply(
            lambda v: None if v in _RSRP_INVALID_SENTINELS else v
        )

    valid_rows: list[RawMeasurementCreate] = []
    errors: list[str] = []

    for idx, row in df.iterrows():
        row_dict = row.where(pd.notna(row), other=None).to_dict()
        try:
            measurement = RawMeasurementCreate(**row_dict)
            valid_rows.append(measurement)
        except Exception as exc:
            errors.append(f"row {idx}: {exc}")

    return valid_rows, errors


# ── Bulk insert ───────────────────────────────────────────────────────────────

async def bulk_insert(
    session: AsyncSession,
    rows: list[RawMeasurementCreate],
) -> int:
    """
    Insert a list of validated measurements into the database in one statement.

    Uses SQLAlchemy Core `insert().values(...)` instead of individual ORM
    flushes to avoid N round-trips.

    Returns the number of rows inserted.
    """
    if not rows:
        return 0

    records = [
        {
            "device_timestamp": r.device_timestamp,
            "lat": r.lat,
            "lon": r.lon,
            "precision": r.precision,
            "speed": r.speed,
            "bearing": r.bearing,
            "operator_id": r.operator_id,
            "technology": r.technology.value,
            "cell_id": r.cell_id,
            "rsrp": r.rsrp,
            "rsrq": r.rsrq,
            "sinr": r.sinr,
            # Pipeline columns start as False/None; scoring service fills them later
            "is_cleaned": False,
            "quality_score": None,
            "sample_weight": None,
        }
        for r in rows
    ]

    stmt = insert(RawMeasurement).values(records)
    await session.execute(stmt)
    return len(records)


# ── Simulation data generator ─────────────────────────────────────────────────

_OPERATORS = {
    "28601": "Turkcell",
    "28602": "Vodafone TR",
    "28603": "Türk Telekom",
}

# Realistic RSRP distribution parameters (μ, σ) per synthetic scenario
_RSRP_SCENARIOS = [
    (-75.0, 8.0),   # good coverage area
    (-95.0, 10.0),  # fair coverage
    (-115.0, 7.0),  # poor / edge of cell
]


def generate_simulation_data(
    count: int,
    bbox: list[float],   # [min_lat, min_lon, max_lat, max_lon]
    operator_id: str,
    technology: Technology = Technology.LTE,
    hours_back: int = 24,
) -> list[RawMeasurementCreate]:
    """
    Generate `count` synthetic measurements within the given bounding box.

    Signal values follow realistic distributions based on 3GPP field experience:
    - RSRP: mix of good/fair/poor coverage zones
    - RSRQ: correlated with RSRP (lower RSRP → lower RSRQ)
    - SINR: semi-independent, slightly correlated with RSRP

    Timestamps are spread uniformly over the last `hours_back` hours.
    """
    if len(bbox) != 4:
        raise ValueError("bbox must be [min_lat, min_lon, max_lat, max_lon]")

    min_lat, min_lon, max_lat, max_lon = bbox
    now = datetime.now(tz=timezone.utc)
    rows: list[RawMeasurementCreate] = []

    for _ in range(count):
        lat = random.uniform(min_lat, max_lat)
        lon = random.uniform(min_lon, max_lon)
        # Pick a random coverage scenario, weighted towards fair coverage
        mu, sigma = random.choices(_RSRP_SCENARIOS, weights=[2, 5, 3])[0]
        rsrp = round(random.gauss(mu, sigma), 1)
        rsrp = max(-140.0, min(-44.0, rsrp))  # clamp to valid range

        # RSRQ loosely correlated with RSRP
        rsrq_base = -3.0 + (rsrp - (-44.0)) / (-140.0 - (-44.0)) * (-17.0)
        rsrq = round(random.gauss(rsrq_base, 2.0), 1)
        rsrq = max(-20.0, min(-3.0, rsrq))

        # SINR: good when RSRP is good, noisy otherwise
        sinr_base = 20.0 + (rsrp - (-44.0)) / (-140.0 - (-44.0)) * (-43.0)
        sinr = round(random.gauss(sinr_base, 4.0), 1)
        sinr = max(-23.0, min(40.0, sinr))

        device_ts = now - timedelta(seconds=random.uniform(0, hours_back * 3600))

        rows.append(
            RawMeasurementCreate(
                device_timestamp=device_ts,
                lat=round(lat, 7),
                lon=round(lon, 7),
                precision=round(random.uniform(3.0, 50.0), 1),
                speed=round(random.uniform(0.0, 30.0), 1),
                bearing=round(random.uniform(0.0, 359.9), 1),
                operator_id=operator_id,
                technology=technology,
                cell_id=random.randint(1, 9999999),
                rsrp=rsrp,
                rsrq=rsrq,
                sinr=sinr,
            )
        )

    return rows
