from datetime import datetime

from pydantic import BaseModel, Field


class GridScoreCreate(BaseModel):
    grid_cell_id: int
    operator_id: str = Field(..., min_length=5, max_length=10)
    time_bucket: datetime
    aggregated_rsrp: float | None = None
    aggregated_rsrq: float | None = None
    aggregated_sinr: float | None = None
    quality_score: float | None = Field(default=None, ge=1.0, le=5.0)
    sample_count: int = Field(default=0, ge=0)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class GridScoreRead(GridScoreCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
