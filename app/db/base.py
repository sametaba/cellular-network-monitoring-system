# This module is imported by alembic/env.py to ensure every ORM model is
# registered on Base.metadata before autogenerate runs.
# Add new model imports here as the project grows.

from app.models.base import Base  # noqa: F401
from app.models.grid_cell import GridCell  # noqa: F401
from app.models.grid_score import GridScore  # noqa: F401
from app.models.raw_measurement import RawMeasurement  # noqa: F401
