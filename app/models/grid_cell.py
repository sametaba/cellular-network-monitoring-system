from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class GridCell(Base):
    """
    Represents a single cell in the spatial grid that covers the map.

    The `grid_index` column holds an H3 hexagonal index string (e.g.
    "891f1d48177ffff"). The `geometry` column stores the hex boundary as a
    PostGIS POLYGON so spatial queries can be run directly in SQL.

    Columns
    -------
    grid_index          : H3 cell index string. Unique per row.
    h3_resolution       : H3 resolution used (7 = ~1.2 km, 8 = ~461 m,
                          9 = ~174 m). Drives adaptive zoom behaviour.
    geometry_center_lat : Latitude of the cell's centroid (WGS-84).
    geometry_center_lon : Longitude of the cell's centroid (WGS-84).
    geometry            : PostGIS POLYGON of the H3 hex boundary (SRID 4326).
                          Populated by the grid service when the cell is
                          created. Null-safe: old rows without PostGIS
                          extension still work via lat/lon fallback.
    """

    __tablename__ = "grid_cells"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    grid_index: Mapped[str] = mapped_column(String(64), nullable=False)
    h3_resolution: Mapped[int] = mapped_column(Integer, nullable=False, default=9)

    geometry_center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    geometry_center_lon: Mapped[float] = mapped_column(Float, nullable=False)

    # PostGIS polygon of the H3 hex boundary.
    # nullable=True so the table works even if PostGIS extension is not yet
    # installed; the grid service fills this on insert.
    geometry: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
        nullable=True,
    )

    # Relationship: one cell → many score snapshots
    scores: Mapped[list["GridScore"]] = relationship(  # noqa: F821
        "GridScore", back_populates="grid_cell", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("grid_index", name="uq_grid_cells_index"),
        Index("ix_grid_center", "geometry_center_lat", "geometry_center_lon"),
        Index("ix_grid_resolution", "h3_resolution"),
    )

    def __repr__(self) -> str:
        return (
            f"<GridCell id={self.id} index={self.grid_index!r} "
            f"res={self.h3_resolution} "
            f"({self.geometry_center_lat}, {self.geometry_center_lon})>"
        )
