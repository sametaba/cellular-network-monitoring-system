"""
Heatmap Endpoint  —  GET /api/v1/heatmap
------------------------------------------
Returns a GeoJSON FeatureCollection where each Feature is one H3 hexagonal
grid cell with aggregated signal quality data as properties.

This is the primary endpoint consumed by the MapLibre GL JS frontend.

Query parameters
----------------
bbox        Required  "minLon,minLat,maxLon,maxLat" — spatial filter
operator_id Optional  MCC+MNC string (e.g. "28601")
time_from   Optional  ISO-8601 datetime — start of time range
time_to     Optional  ISO-8601 datetime — end of time range
            If neither time_from nor time_to is given, only the most recent
            time_bucket per (cell, operator) pair is returned.
resolution  Optional  H3 resolution 7|8|9 (default 9).
            Values < 9 re-group res-9 cells into coarser parent cells at
            query time — no DB schema change required.

Response
--------
GeoJSON FeatureCollection — geometry is the H3 hex polygon (Polygon type),
properties include quality_score, aggregated_rsrp/rsrq/sinr, sample_count,
confidence_score, and time_bucket.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import h3 as h3lib
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.grid_cell import GridCell
from app.models.grid_score import GridScore
from app.services.grid import h3_to_geojson_polygon

router = APIRouter(tags=["heatmap"])


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """
    Parse a bbox query string into (min_lon, min_lat, max_lon, max_lat).

    Raises:
        HTTPException 422 if the string is malformed or coordinates are invalid.
    """
    try:
        parts = [float(v.strip()) for v in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("expected 4 values")
        min_lon, min_lat, max_lon, max_lat = parts
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid bbox format: {exc}. Expected 'minLon,minLat,maxLon,maxLat'",
        ) from exc

    if not (-180 <= min_lon <= max_lon <= 180):
        raise HTTPException(status_code=422, detail="bbox longitude values out of range")
    if not (-90 <= min_lat <= max_lat <= 90):
        raise HTTPException(status_code=422, detail="bbox latitude values out of range")

    return min_lon, min_lat, max_lon, max_lat


def _regroup_by_resolution(
    rows: list[tuple],  # list of (GridScore, grid_index)
    resolution: int,
) -> list[dict]:
    """
    Re-group res-9 grid_scores into coarser parent cells at the given resolution.

    Each group aggregates:
      - RSRP/RSRQ/SINR: weighted average (weight = sample_count)
      - quality_score: weighted average
      - sample_count: sum
      - confidence_score: maximum within group
      - time_bucket: maximum (most recent)
      - operator_id: taken from group key

    Returns a list of feature property dicts (geometry computed separately).
    """
    groups: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "rsrp_wsum": 0.0, "rsrq_wsum": 0.0, "sinr_wsum": 0.0,
        "score_wsum": 0.0, "qoe_wsum": 0.0, "mos_wsum": 0.0,
        "weight_total": 0.0,
        "sample_count": 0, "confidence_score": 0.0,
        "time_bucket": None, "operator_id": "",
        "rsrp_count": 0, "rsrq_count": 0, "sinr_count": 0,
        "score_count": 0, "qoe_count": 0, "mos_count": 0,
        "fit_streaming": False, "fit_volte": False,
    })

    for score, grid_index in rows:
        try:
            parent = h3lib.cell_to_parent(grid_index, resolution)
        except Exception:
            continue  # skip invalid H3 indices
        key = (parent, score.operator_id)
        g = groups[key]

        w = float(score.sample_count or 1)
        g["operator_id"] = score.operator_id
        g["sample_count"] += score.sample_count or 1
        g["weight_total"] += w

        if score.aggregated_rsrp is not None:
            g["rsrp_wsum"] += score.aggregated_rsrp * w
            g["rsrp_count"] += 1

        if score.aggregated_rsrq is not None:
            g["rsrq_wsum"] += score.aggregated_rsrq * w
            g["rsrq_count"] += 1

        if score.aggregated_sinr is not None:
            g["sinr_wsum"] += score.aggregated_sinr * w
            g["sinr_count"] += 1

        if score.quality_score is not None:
            g["score_wsum"] += score.quality_score * w
            g["score_count"] += 1

        if score.qoe_index is not None:
            g["qoe_wsum"] += score.qoe_index * w
            g["qoe_count"] += 1

        if score.estimated_mos is not None:
            g["mos_wsum"] += score.estimated_mos * w
            g["mos_count"] += 1

        if score.fit_streaming:
            g["fit_streaming"] = True
        if score.fit_volte:
            g["fit_volte"] = True

        if score.confidence_score is not None:
            g["confidence_score"] = max(g["confidence_score"], score.confidence_score)

        if score.time_bucket is not None:
            if g["time_bucket"] is None or score.time_bucket > g["time_bucket"]:
                g["time_bucket"] = score.time_bucket

    features = []
    for (parent_index, _), g in groups.items():
        wt = g["weight_total"] or 1.0
        features.append({
            "grid_index":       parent_index,
            "operator_id":      g["operator_id"],
            "quality_score":    g["score_wsum"] / wt if g["score_count"] else None,
            "aggregated_rsrp":  g["rsrp_wsum"] / wt if g["rsrp_count"] else None,
            "aggregated_rsrq":  g["rsrq_wsum"] / wt if g["rsrq_count"] else None,
            "aggregated_sinr":  g["sinr_wsum"] / wt if g["sinr_count"] else None,
            "sample_count":     g["sample_count"],
            "confidence_score": g["confidence_score"] or None,
            "time_bucket":      g["time_bucket"].isoformat() if g["time_bucket"] else None,
            "qoe_index":        g["qoe_wsum"] / wt if g["qoe_count"] else None,
            "estimated_mos":    g["mos_wsum"] / wt if g["mos_count"] else None,
            "fit_streaming":    g["fit_streaming"],
            "fit_volte":        g["fit_volte"],
        })

    return features


@router.get("")
async def get_heatmap(
    bbox: str = Query(
        ...,
        description="Bounding box: 'minLon,minLat,maxLon,maxLat'",
        examples={"istanbul": {"value": "28.9,41.0,29.1,41.1"}},
    ),
    operator_id: str | None = Query(
        default=None,
        description="Operator MCC+MNC filter (e.g. '28601')",
    ),
    time_from: datetime | None = Query(
        default=None,
        description="Start of time range (ISO-8601 UTC)",
    ),
    time_to: datetime | None = Query(
        default=None,
        description="End of time range (ISO-8601 UTC)",
    ),
    resolution: int = Query(
        default=9,
        ge=7,
        le=9,
        description="H3 resolution (7=~1.2km, 8=~460m, 9=~175m). Values < 9 re-group "
                    "res-9 stored cells into coarser parent cells at query time.",
    ),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return a GeoJSON FeatureCollection of H3 grid cells with aggregated
    signal quality data for the requested bounding box.

    When no time range is provided, the response contains only the latest
    aggregated score per (cell, operator) pair — ideal for live dashboards.

    The `resolution` parameter controls hexagon granularity:
      - resolution=9 (default): stored res-9 cells (~175 m edge)
      - resolution=8: cells re-grouped into ~460 m parent hexagons
      - resolution=7: cells re-grouped into ~1.2 km parent hexagons
    """
    min_lon, min_lat, max_lon, max_lat = _parse_bbox(bbox)

    # ── Build base query: grid_scores JOIN grid_cells within bbox ─────────────
    base_q = (
        select(GridScore, GridCell.grid_index)
        .join(GridCell, GridScore.grid_cell_id == GridCell.id)
        .where(
            and_(
                GridCell.geometry_center_lat >= min_lat,
                GridCell.geometry_center_lat <= max_lat,
                GridCell.geometry_center_lon >= min_lon,
                GridCell.geometry_center_lon <= max_lon,
            )
        )
    )

    if operator_id:
        base_q = base_q.where(GridScore.operator_id == operator_id)

    # ── Time range filter ─────────────────────────────────────────────────────
    if time_from or time_to:
        if time_from:
            base_q = base_q.where(GridScore.time_bucket >= time_from)
        if time_to:
            base_q = base_q.where(GridScore.time_bucket <= time_to)
    else:
        # No time range specified → return only the most recent bucket per
        # (grid_cell_id, operator_id) pair via a correlated subquery.
        latest_subq = (
            select(
                GridScore.grid_cell_id,
                GridScore.operator_id,
                func.max(GridScore.time_bucket).label("max_bucket"),
            )
            .group_by(GridScore.grid_cell_id, GridScore.operator_id)
            .subquery()
        )
        base_q = base_q.join(
            latest_subq,
            and_(
                GridScore.grid_cell_id == latest_subq.c.grid_cell_id,
                GridScore.operator_id == latest_subq.c.operator_id,
                GridScore.time_bucket == latest_subq.c.max_bucket,
            ),
        )

    result = await session.execute(base_q)
    rows = result.all()

    # ── Resolution re-grouping or direct mapping ──────────────────────────────
    if resolution < 9:
        props_list = _regroup_by_resolution(rows, resolution)
        features = [
            {
                "type": "Feature",
                "geometry": h3_to_geojson_polygon(p["grid_index"]),
                "properties": p,
            }
            for p in props_list
        ]
    else:
        features = []
        for score, grid_index in rows:
            geometry = h3_to_geojson_polygon(grid_index)
            features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "grid_index":       grid_index,
                    "operator_id":      score.operator_id,
                    "quality_score":    score.quality_score,
                    "aggregated_rsrp":  score.aggregated_rsrp,
                    "aggregated_rsrq":  score.aggregated_rsrq,
                    "aggregated_sinr":  score.aggregated_sinr,
                    "sample_count":     score.sample_count,
                    "confidence_score": score.confidence_score,
                    "time_bucket":      score.time_bucket.isoformat() if score.time_bucket else None,
                    "qoe_index":        score.qoe_index,
                    "estimated_mos":    score.estimated_mos,
                    "fit_streaming":    score.fit_streaming,
                    "fit_volte":        score.fit_volte,
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
    }
