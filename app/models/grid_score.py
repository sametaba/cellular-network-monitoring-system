from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class GridScore(Base):
    """
    Pre-aggregated signal quality scores for a grid cell, keyed by operator
    and time bucket.

    The aggregation job reads from `raw_measurements` (where is_cleaned=True),
    groups by (grid_cell_id, operator_id, time_bucket), and upserts here.
    The dashboard reads from this table for heat-map rendering.

    Columns
    -------
    grid_cell_id        : FK → grid_cells.id.
    operator_id         : MCC+MNC string, same format as raw_measurements.
    time_bucket         : Truncated timestamp representing the window start
                          (e.g. hourly: 2024-01-15 14:00:00+00).
    aggregated_rsrp     : Weighted mean RSRP across samples (dBm).
    aggregated_rsrq     : Weighted mean RSRQ across samples (dB).
    aggregated_sinr     : Weighted mean SINR across samples (dB).
    quality_score       : Composite 1–5 score for the cell; dashboard uses
                          this column for colour-coding the heatmap.
    sample_count        : Number of raw measurements that fed into this row.
    confidence_score    : [0.0 – 1.0] quality of the estimate; derived from
                          sample_count, spatial spread, and metric dispersion.
    created_at          : Row creation time (set by DB).
    updated_at          : Last update time (managed by the aggregation job).
    """

    __tablename__ = "grid_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Foreign key
    grid_cell_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("grid_cells.id", ondelete="CASCADE"), nullable=False
    )

    # Grouping dimensions
    operator_id: Mapped[str] = mapped_column(String(10), nullable=False)
    time_bucket: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Aggregated metrics
    aggregated_rsrp: Mapped[float | None] = mapped_column(Float, nullable=True)
    aggregated_rsrq: Mapped[float | None] = mapped_column(Float, nullable=True)
    aggregated_sinr: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Composite quality score (1–5) — the primary dashboard metric
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Advanced quality metrics (Faz 9)
    qoe_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_mos: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit_streaming: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fit_volte: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship back to GridCell
    grid_cell: Mapped["GridCell"] = relationship(  # noqa: F821
        "GridCell", back_populates="scores"
    )

    # A unique constraint ensures one row per (cell, operator, time window).
    # The aggregation job uses ON CONFLICT DO UPDATE against this.
    __table_args__ = (
        UniqueConstraint(
            "grid_cell_id", "operator_id", "time_bucket",
            name="uq_grid_scores_cell_op_bucket",
        ),
        Index("ix_grid_scores_cell_id", "grid_cell_id"),
        Index("ix_grid_scores_operator_bucket", "operator_id", "time_bucket"),
    )

    def __repr__(self) -> str:
        return (
            f"<GridScore id={self.id} cell={self.grid_cell_id} "
            f"op={self.operator_id} bucket={self.time_bucket} "
            f"score={self.quality_score} n={self.sample_count}>"
        )
