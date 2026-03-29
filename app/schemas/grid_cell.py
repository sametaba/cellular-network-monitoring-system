from pydantic import BaseModel, Field


class GridCellCreate(BaseModel):
    grid_index: str = Field(..., min_length=1, max_length=64)
    geometry_center_lat: float = Field(..., ge=-90.0, le=90.0)
    geometry_center_lon: float = Field(..., ge=-180.0, le=180.0)


class GridCellRead(GridCellCreate):
    id: int

    model_config = {"from_attributes": True}
