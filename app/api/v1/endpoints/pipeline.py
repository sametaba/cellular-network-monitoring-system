"""
Pipeline Endpoint  —  POST /api/v1/pipeline/run
-------------------------------------------------
Manual trigger for the full data-processing pipeline:

  1. Fetch raw_measurement rows that have NOT been cleaned yet (is_cleaned=False)
     in the requested time window.
  2. Validate signal ranges + compute quality_score and sample_weight for each
     valid row (process_raw_batch).
  3. Run aggregation over the newly cleaned data → upsert grid_scores
     (run_aggregation).

Intended for development and testing.  In production the scheduler runs
this automatically every 15 minutes (see app/core/scheduler.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.raw_measurement import RawMeasurement
from app.services.aggregation import process_raw_batch, run_aggregation

router = APIRouter(tags=["pipeline"])


# ── Request / Response schemas ────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    operator_id: str | None = Field(
        default=None,
        description="Limit processing to a single operator (MCC+MNC). "
                    "If omitted, all operators are processed.",
    )
    hours_back: int = Field(
        default=24,
        ge=1,
        le=168,  # max 1 week
        description="How many hours of uncleaned measurements to process.",
    )


class PipelineRunResult(BaseModel):
    cleaned: int = Field(description="Rows validated and marked is_cleaned=True")
    rejected: int = Field(description="Rows that failed signal range validation")
    cells_upserted: int = Field(description="grid_scores rows inserted or updated")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/run", response_model=PipelineRunResult)
async def run_pipeline(
    request: PipelineRunRequest,
    session: AsyncSession = Depends(get_db),
) -> PipelineRunResult:
    """
    Execute the cleaning → scoring → aggregation pipeline and return a
    summary of rows processed.

    Workflow
    --------
    1. **Fetch uncleaned IDs** — SELECT id FROM raw_measurements WHERE
       is_cleaned=False AND server_timestamp >= cutoff [AND operator_id=?]

    2. **process_raw_batch** — For each ID: validate 3GPP signal ranges,
       compute advanced_composite_score (quality_score), calculate_weight
       (sample_weight), bulk-UPDATE the rows that pass.

    3. **run_aggregation** — Group cleaned rows into (H3 cell, operator,
       hourly bucket) tuples, compute weighted averages and confidence,
       upsert into grid_scores.

    4. **Commit** — all changes are committed in one transaction.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=request.hours_back)

    # Step 1 — collect IDs of uncleaned rows in the time window
    id_stmt = select(RawMeasurement.id).where(
        RawMeasurement.is_cleaned == False,       # noqa: E712
        RawMeasurement.server_timestamp >= cutoff,
    )
    if request.operator_id:
        id_stmt = id_stmt.where(RawMeasurement.operator_id == request.operator_id)

    id_result = await session.execute(id_stmt)
    ids: list[int] = list(id_result.scalars())

    # Step 2 — validate, score, weight
    batch_result = await process_raw_batch(session, ids)

    # Step 3 — aggregate into grid_scores
    cells_upserted = await run_aggregation(
        session,
        hours_back=request.hours_back,
        operator_id=request.operator_id,
    )

    # Step 4 — commit everything
    await session.commit()

    return PipelineRunResult(
        cleaned=batch_result["cleaned"],
        rejected=batch_result["rejected"],
        cells_upserted=cells_upserted,
    )
