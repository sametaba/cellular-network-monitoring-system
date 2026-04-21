"""
AI Coverage Prediction Service
-------------------------------
Orchestrates the ML prediction pipeline:
  1. Load measured cells from grid_scores (latest time_bucket)
  2. Find unmeasured H3 neighbor cells via grid_disk
  3. Run XGBoost predictor
  4. Return GeoJSON features with ``is_ai_predicted: True``

All database access follows the existing async SQLAlchemy patterns
established in ``aggregation.py`` and ``heatmap.py``.
"""

from __future__ import annotations

import logging
from typing import Any

import h3
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.predictor import CoveragePredictor
from app.models.grid_cell import GridCell
from app.models.grid_score import GridScore
from app.services.grid import h3_to_geojson_polygon

logger = logging.getLogger(__name__)

# ── Module-level singleton ──────────────────────────────────────────────────
_predictor: CoveragePredictor | None = None


def get_predictor() -> CoveragePredictor:
    """Lazy-initialise and cache the predictor singleton."""
    global _predictor
    if _predictor is None:
        _predictor = CoveragePredictor()
        _predictor.load()  # attempt to load from disk
    return _predictor


# ── Database helpers ────────────────────────────────────────────────────────

async def build_scores_lookup(
    session: AsyncSession,
    operator_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Build ``{h3_index: {metric: value}}`` lookup from latest grid_scores.

    Uses the same "latest time_bucket per (cell, operator)" logic as the
    heatmap endpoint to ensure consistency.
    """
    # Subquery: latest time_bucket per (grid_cell_id, operator_id)
    latest_sq = (
        select(
            GridScore.grid_cell_id,
            GridScore.operator_id,
            func.max(GridScore.time_bucket).label("max_bucket"),
        )
        .group_by(GridScore.grid_cell_id, GridScore.operator_id)
    )
    if operator_id:
        latest_sq = latest_sq.where(GridScore.operator_id == operator_id)
    latest_sq = latest_sq.subquery()

    query = (
        select(GridScore, GridCell.grid_index)
        .join(GridCell, GridScore.grid_cell_id == GridCell.id)
        .join(
            latest_sq,
            and_(
                GridScore.grid_cell_id == latest_sq.c.grid_cell_id,
                GridScore.operator_id == latest_sq.c.operator_id,
                GridScore.time_bucket == latest_sq.c.max_bucket,
            ),
        )
    )
    if operator_id:
        query = query.where(GridScore.operator_id == operator_id)

    result = await session.execute(query)
    rows = result.all()

    lookup: dict[str, dict[str, Any]] = {}
    for score, grid_index in rows:
        # If multiple operators, keep the one with higher quality_score
        existing = lookup.get(grid_index)
        if existing is not None:
            if (score.quality_score or 0) <= (existing.get("quality_score") or 0):
                continue

        lookup[grid_index] = {
            "qoe_index": score.qoe_index,
            "aggregated_rsrp": score.aggregated_rsrp,
            "aggregated_sinr": score.aggregated_sinr,
            "aggregated_rsrq": score.aggregated_rsrq,
            "quality_score": score.quality_score,
            "estimated_mos": score.estimated_mos,
            "sample_count": score.sample_count,
            "confidence_score": score.confidence_score,
            "operator_id": score.operator_id,
        }

    return lookup


def find_empty_neighbors(measured_indices: set[str], k: int = 2) -> set[str]:
    """
    Find H3 cells within *k*-ring distance of measured cells that have
    no measurements.

    Uses ``h3.grid_disk`` (includes all cells up to distance k) for each
    measured cell, then subtracts the measured set.
    """
    all_neighbors: set[str] = set()
    for idx in measured_indices:
        try:
            disk = h3.grid_disk(idx, k)
            all_neighbors.update(disk)
        except Exception:
            continue  # skip invalid H3 indices
    return all_neighbors - measured_indices


def _parse_bbox_tuple(bbox: str) -> tuple[float, float, float, float]:
    """Parse ``'minLon,minLat,maxLon,maxLat'`` into a 4-tuple."""
    parts = [float(v.strip()) for v in bbox.split(",")]
    return parts[0], parts[1], parts[2], parts[3]


# ── Public API ──────────────────────────────────────────────────────────────

async def predict_coverage(
    session: AsyncSession,
    bbox: str | None = None,
    operator_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Full prediction pipeline.

    1. Build scores_lookup from DB.
    2. Train model if not fitted (or load from disk).
    3. Find empty neighbor cells (within 2-ring of measured).
    4. Optionally filter to bbox.
    5. Predict and return GeoJSON features with ``is_ai_predicted=True``.
    """
    scores_lookup = await build_scores_lookup(session, operator_id)
    if not scores_lookup:
        logger.info("No measured cells found. Cannot predict.")
        return []

    # Ensure model is trained
    predictor = get_predictor()
    if not predictor.is_fitted:
        logger.info("Training predictor on %d measured cells...", len(scores_lookup))
        predictor.train(scores_lookup)
        if predictor.is_fitted:
            predictor.save()
        else:
            logger.warning("Training failed. Returning empty predictions.")
            return []

    # Find unmeasured cells around measured ones
    measured_indices = set(scores_lookup.keys())
    empty_indices = find_empty_neighbors(measured_indices, k=2)

    if not empty_indices:
        return []

    # Optional bbox filter
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = _parse_bbox_tuple(bbox)
            filtered: set[str] = set()
            for idx in empty_indices:
                try:
                    lat, lng = h3.cell_to_latlng(idx)
                    if min_lat <= lat <= max_lat and min_lon <= lng <= max_lon:
                        filtered.add(idx)
                except Exception:
                    continue
            empty_indices = filtered
        except (ValueError, IndexError):
            pass  # ignore malformed bbox, predict all

    if not empty_indices:
        return []

    # Run predictions
    predictions = predictor.predict(list(empty_indices), scores_lookup)

    # Determine the dominant operator_id to label predictions
    op_id = operator_id or _dominant_operator(scores_lookup)

    # Build GeoJSON features
    features: list[dict[str, Any]] = []
    for pred in predictions:
        if pred is None:
            continue
        h3_idx = pred["h3_index"]
        geometry = h3_to_geojson_polygon(h3_idx)

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "grid_index": h3_idx,
                "operator_id": op_id,
                "quality_score": pred.get("quality_score"),
                "aggregated_rsrp": pred.get("aggregated_rsrp"),
                "aggregated_rsrq": None,
                "aggregated_sinr": pred.get("aggregated_sinr"),
                "sample_count": None,
                "confidence_score": pred.get("prediction_confidence"),
                "time_bucket": None,
                "qoe_index": pred.get("qoe_index"),
                "estimated_mos": pred.get("estimated_mos"),
                "fit_streaming": None,
                "fit_volte": None,
                "is_ai_predicted": True,
            },
        })

    logger.info(
        "Predicted %d cells (from %d empty candidates).",
        len(features),
        len(empty_indices),
    )
    return features


async def train_model(
    session: AsyncSession,
    operator_id: str | None = None,
) -> dict[str, Any]:
    """
    Train / retrain the prediction model from current data.

    Returns training metrics (RMSE per target).
    """
    scores_lookup = await build_scores_lookup(session, operator_id)
    if not scores_lookup:
        return {"error": "No measured cells found", "metrics": {}}

    predictor = get_predictor()
    metrics = predictor.train(scores_lookup)
    if predictor.is_fitted:
        predictor.save()

    return {
        "trained_on": len(scores_lookup),
        "targets": len(predictor.models),
        "metrics": metrics,
    }


def _dominant_operator(scores_lookup: dict[str, dict[str, Any]]) -> str:
    """Return the operator_id that appears most frequently."""
    counts: dict[str, int] = {}
    for data in scores_lookup.values():
        op = data.get("operator_id", "unknown")
        counts[op] = counts.get(op, 0) + 1
    if not counts:
        return "unknown"
    return max(counts, key=lambda k: counts[k])
