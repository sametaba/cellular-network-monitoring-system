"""
AI Insights Endpoints
---------------------
GET  /api/v1/insights/predict-coverage — predicted QoE for unmeasured cells
POST /api/v1/insights/train            — train / retrain the ML model
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.ai_service import predict_coverage, train_model

router = APIRouter(tags=["insights"])


@router.get("/predict-coverage")
async def get_predicted_coverage(
    bbox: str = Query(
        ...,
        description="Bounding box: 'minLon,minLat,maxLon,maxLat'",
        examples=["28.9,41.0,29.1,41.1"],
    ),
    operator_id: str | None = Query(
        default=None,
        description="Operator MCC+MNC filter (e.g. '28601')",
    ),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return predicted coverage for unmeasured H3 cells within the bounding box.

    Each feature in the returned GeoJSON FeatureCollection carries
    ``is_ai_predicted: true`` so the frontend can visually distinguish
    predictions from real measurements.
    """
    features = await predict_coverage(session, bbox=bbox, operator_id=operator_id)
    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.post("/train")
async def train_prediction_model(
    operator_id: str | None = Query(
        default=None,
        description="Train for a specific operator, or all if omitted",
    ),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Train / retrain the coverage prediction model. Returns training metrics."""
    result = await train_model(session, operator_id)
    return {"status": "ok", **result}
