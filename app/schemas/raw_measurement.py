from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.raw_measurement import Technology


class RawMeasurementCreate(BaseModel):
    """Payload expected from the mobile client on ingestion."""

    device_timestamp: datetime
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    precision: float | None = Field(default=None, ge=0)
    speed: float | None = Field(default=None, ge=0)
    bearing: float | None = Field(default=None, ge=0, le=360)
    operator_id: str = Field(..., min_length=5, max_length=10)
    technology: Technology
    cell_id: int | None = None
    rsrp: float | None = Field(default=None, ge=-140, le=-44)
    rsrq: float | None = Field(default=None, ge=-20, le=-3)
    sinr: float | None = None

    @field_validator("operator_id")
    @classmethod
    def operator_id_must_be_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("operator_id must be numeric MCC+MNC string, e.g. '28601'")
        return v


class RawMeasurementRead(RawMeasurementCreate):
    """Full row returned by read endpoints — includes server-side fields."""

    id: int
    server_timestamp: datetime
    quality_score: float | None = None
    sample_weight: float | None = None
    is_cleaned: bool = False

    model_config = {"from_attributes": True}


class UploadResult(BaseModel):
    """Response body for CSV / batch upload endpoints."""

    accepted: int
    rejected: int
    errors: list[str] = []
