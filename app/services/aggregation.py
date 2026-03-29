"""
Aggregation Service  (WP4)
---------------------------
Two public responsibilities:

  process_raw_batch(session, ids)
      Validates, scores, and weights a list of raw_measurement IDs that have
      not yet been cleaned.  Updates those rows in-place and marks them
      is_cleaned=True.  Called by the pipeline endpoint before aggregation.

  run_aggregation(session, hours_back, operator_id)
      Reads all cleaned measurements in the given time window, groups them
      by (H3 cell @ resolution 9, operator_id, hourly bucket), computes
      weighted-average RSRP/RSRQ/SINR and a confidence score, then
      upserts one row per group into grid_scores.

Design notes:
  • raw_measurements intentionally has no h3_index column so schema is not
    touched; the H3 index is computed on-the-fly from (lat, lon).
  • sample_weight is persisted per measurement (set by process_raw_batch)
    so aggregation can use a simple Σ(w·x)/Σw formula without re-running
    the weight sub-factors.
  • time_bucket granularity: floor to UTC hour.
  • Upsert key: (grid_cell_id, operator_id, time_bucket) —
    constraint name: uq_grid_scores_cell_op_bucket.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from geoalchemy2.shape import from_shape
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.grid_cell import GridCell
from app.models.grid_score import GridScore
from app.models.raw_measurement import RawMeasurement
from app.schemas.raw_measurement import RawMeasurementCreate
from app.services.cleaning import validate_ranges
from app.services.grid import (
    assign_h3_index,
    cell_center,
    h3_to_shapely_polygon,
)
from app.services.scoring import (
    advanced_composite_score,
    compute_mos,
    compute_network_fitness,
    compute_qoe,
)
from app.services.weights import calculate_weight

# Default H3 resolution used for all aggregation runs.
# Adaptive resolution per cell is a Faz 5+ feature.
_DEFAULT_RESOLUTION: int = 9


# ── Time helpers ──────────────────────────────────────────────────────────────

def _floor_to_hour(dt: datetime) -> datetime:
    """Truncate a datetime to the start of its UTC hour."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc)
    return utc.replace(minute=0, second=0, microsecond=0)


# ── GridCell helpers ──────────────────────────────────────────────────────────

async def _get_or_create_grid_cell(
    session: AsyncSession,
    h3_index: str,
    resolution: int = _DEFAULT_RESOLUTION,
) -> int:
    """
    Return the `id` of the GridCell row for the given H3 index.

    If the row does not exist yet it is created (with geometry computed from
    the H3 boundary) and flushed so its auto-generated id becomes available.

    Returns:
        Integer primary key of the grid_cells row.
    """
    result = await session.execute(
        select(GridCell.id).where(GridCell.grid_index == h3_index)
    )
    cell_id: int | None = result.scalar_one_or_none()
    if cell_id is not None:
        return cell_id

    lat, lon = cell_center(h3_index)
    shapely_poly = h3_to_shapely_polygon(h3_index)
    geom = from_shape(shapely_poly, srid=4326)

    cell = GridCell(
        grid_index=h3_index,
        h3_resolution=resolution,
        geometry_center_lat=lat,
        geometry_center_lon=lon,
        geometry=geom,
    )
    session.add(cell)
    await session.flush()   # populate cell.id without committing
    return cell.id          # type: ignore[return-value]


# ── Confidence score ──────────────────────────────────────────────────────────

def compute_confidence(sample_count: int, score_values: list[float]) -> float:
    """
    Estimate how reliable a grid cell's aggregated score is.

    Two factors:

    n_factor (sample adequacy)
        tanh(log10(n+1)) — smoothly saturates toward 1.0 as n grows.
        n=1  → 0.29   (very low confidence — single measurement)
        n=5  → 0.65
        n=10 → 0.77
        n=30 → 0.90
        n=100 → 0.96

    consistency_factor (metric stability)
        1 / (1 + std(quality_scores)) — high standard deviation means
        measurements in the cell are contradictory (e.g. -70 dBm next
        to -130 dBm), which reduces reliability.
        std=0.0 → 1.00   (perfectly consistent)
        std=0.5 → 0.67
        std=1.0 → 0.50
        std=2.0 → 0.33

    Final:  confidence = n_factor × consistency_factor ∈ [0.0, 1.0]
    """
    n_factor = math.tanh(math.log10(sample_count + 1))

    if len(score_values) >= 2:
        std_score = statistics.stdev(score_values)
    else:
        # Single value → no dispersion; apply a moderate penalty for sparse data
        std_score = 0.0

    consistency_factor = 1.0 / (1.0 + std_score)
    return max(0.0, min(1.0, n_factor * consistency_factor))


# ── Pipeline helper ───────────────────────────────────────────────────────────

async def process_raw_batch(
    session: AsyncSession,
    ids: list[int],
) -> dict[str, int]:
    """
    Validate, score, and weight a batch of raw_measurement rows.

    For each ID in `ids`:
      1. Validate physical signal ranges (3GPP TS 36.214).
      2. Compute quality_score via advanced_composite_score(rsrp, sinr).
      3. Compute sample_weight via calculate_weight(precision, server_ts, speed).
      4. Bulk-UPDATE: set is_cleaned=True, quality_score, sample_weight.
         Invalid rows are left with is_cleaned=False.

    Args:
        session: Open AsyncSession (caller owns commit/rollback).
        ids:     List of raw_measurement primary keys to process.

    Returns:
        {"cleaned": N, "rejected": M}
    """
    if not ids:
        return {"cleaned": 0, "rejected": 0}

    # Fetch all rows in one query
    result = await session.execute(
        select(RawMeasurement).where(RawMeasurement.id.in_(ids))
    )
    rows: list[RawMeasurement] = list(result.scalars())

    valid_updates: list[dict] = []
    rejected = 0

    for row in rows:
        # Re-use cleaning service for range validation
        schema_row = RawMeasurementCreate(
            device_timestamp=row.device_timestamp,
            lat=row.lat,
            lon=row.lon,
            precision=row.precision,
            speed=row.speed,
            bearing=row.bearing,
            operator_id=row.operator_id,
            technology=row.technology,
            cell_id=row.cell_id,
            rsrp=row.rsrp,
            rsrq=row.rsrq,
            sinr=row.sinr,
        )
        ok, _ = validate_ranges(schema_row)
        if not ok:
            rejected += 1
            continue

        q_score = advanced_composite_score(row.rsrp, row.sinr, row.rsrq)
        weight = calculate_weight(row.precision, row.server_timestamp, row.speed)

        valid_updates.append({
            "id": row.id,
            "quality_score": q_score,
            "sample_weight": weight,
        })

    if valid_updates:
        # Individual UPDATE per row; for very large batches a bulk VALUES
        # approach (e.g. psycopg2 execute_values) would be faster, but
        # this keeps the code readable for a graduation-project scale.
        for upd in valid_updates:
            await session.execute(
                update(RawMeasurement)
                .where(RawMeasurement.id == upd["id"])
                .values(
                    is_cleaned=True,
                    quality_score=upd["quality_score"],
                    sample_weight=upd["sample_weight"],
                )
            )

    return {"cleaned": len(valid_updates), "rejected": rejected}


# ── Main aggregation loop ─────────────────────────────────────────────────────

async def run_aggregation(
    session: AsyncSession,
    hours_back: int = 24,
    operator_id: str | None = None,
) -> int:
    """
    Aggregate cleaned measurements into grid_scores.

    Algorithm
    ---------
    1. Fetch all is_cleaned=True rows in [utcnow - hours_back, utcnow].
    2. Group in Python by (h3_index @ res9, operator_id, floor_to_hour(server_ts)).
    3. For each group compute:
       - Weighted-average RSRP, RSRQ, SINR using stored sample_weight.
       - Final quality_score via advanced_composite_score(w_rsrp, w_sinr).
       - confidence via compute_confidence(n, quality_scores).
    4. get_or_create the GridCell row for this H3 index.
    5. Upsert into grid_scores (ON CONFLICT → UPDATE all metric columns).

    Args:
        session:    Open AsyncSession.  Caller is responsible for commit.
        hours_back: How far back in time to look for cleaned measurements.
        operator_id: Optional filter; if None, all operators are aggregated.

    Returns:
        Number of grid_scores rows upserted.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours_back)

    stmt = select(
        RawMeasurement.id,
        RawMeasurement.lat,
        RawMeasurement.lon,
        RawMeasurement.rsrp,
        RawMeasurement.rsrq,
        RawMeasurement.sinr,
        RawMeasurement.quality_score,
        RawMeasurement.sample_weight,
        RawMeasurement.operator_id,
        RawMeasurement.server_timestamp,
    ).where(
        RawMeasurement.is_cleaned == True,   # noqa: E712
        RawMeasurement.server_timestamp >= cutoff,
    )
    if operator_id:
        stmt = stmt.where(RawMeasurement.operator_id == operator_id)

    result = await session.execute(stmt)
    all_rows = result.all()

    if not all_rows:
        return 0

    # Group rows by (h3_index, operator_id, hourly_bucket)
    groups: dict[tuple, list] = defaultdict(list)
    for row in all_rows:
        h3_idx = assign_h3_index(row.lat, row.lon, _DEFAULT_RESOLUTION)
        bucket = _floor_to_hour(row.server_timestamp)
        groups[(h3_idx, row.operator_id, bucket)].append(row)

    upserted = 0

    for (h3_idx, op_id, bucket), group_rows in groups.items():

        # ── Weighted averages ─────────────────────────────────────────────────
        def _wavg(vals_and_weights: list[tuple]) -> float | None:
            """Weighted average of (value, weight) pairs, ignoring None values."""
            pairs = [(v, w) for v, w in vals_and_weights if v is not None and w]
            if not pairs:
                return None
            total_w = sum(w for _, w in pairs)
            if total_w < 1e-12:  # epsilon guard against zero-division
                return None
            return sum(v * w for v, w in pairs) / total_w

        default_w = 1.0  # fallback if sample_weight not yet computed
        w_rsrp = _wavg([(r.rsrp, r.sample_weight or default_w) for r in group_rows])
        w_rsrq = _wavg([(r.rsrq, r.sample_weight or default_w) for r in group_rows])
        w_sinr = _wavg([(r.sinr, r.sample_weight or default_w) for r in group_rows])

        final_score = advanced_composite_score(w_rsrp, w_sinr, w_rsrq)
        qoe = compute_qoe(w_rsrp, w_sinr, w_rsrq)
        mos = compute_mos(w_rsrp, w_sinr, w_rsrq)
        fitness = compute_network_fitness(w_rsrp, w_sinr, w_rsrq)

        score_vals = [r.quality_score for r in group_rows if r.quality_score is not None]
        confidence = compute_confidence(len(group_rows), score_vals)

        # ── Get or create GridCell ────────────────────────────────────────────
        cell_id = await _get_or_create_grid_cell(session, h3_idx, _DEFAULT_RESOLUTION)

        # ── Upsert grid_scores ────────────────────────────────────────────────
        ins = pg_insert(GridScore).values(
            grid_cell_id=cell_id,
            operator_id=op_id,
            time_bucket=bucket,
            aggregated_rsrp=w_rsrp,
            aggregated_rsrq=w_rsrq,
            aggregated_sinr=w_sinr,
            quality_score=final_score,
            sample_count=len(group_rows),
            confidence_score=confidence,
            qoe_index=qoe,
            estimated_mos=mos,
            fit_streaming=fitness["streaming"],
            fit_volte=fitness["volte"],
        )
        upd_stmt = ins.on_conflict_do_update(
            index_elements=["grid_cell_id", "operator_id", "time_bucket"],
            set_={
                "aggregated_rsrp":   ins.excluded.aggregated_rsrp,
                "aggregated_rsrq":   ins.excluded.aggregated_rsrq,
                "aggregated_sinr":   ins.excluded.aggregated_sinr,
                "quality_score":     ins.excluded.quality_score,
                "sample_count":      ins.excluded.sample_count,
                "confidence_score":  ins.excluded.confidence_score,
                "qoe_index":         ins.excluded.qoe_index,
                "estimated_mos":     ins.excluded.estimated_mos,
                "fit_streaming":     ins.excluded.fit_streaming,
                "fit_volte":         ins.excluded.fit_volte,
                "updated_at":        func.now(),
            },
        )
        await session.execute(upd_stmt)
        upserted += 1

    return upserted
