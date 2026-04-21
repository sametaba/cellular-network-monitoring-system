import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Technology(str, enum.Enum):
    """Radio access technology reported by the device."""
    LTE     = "LTE"      # 4G Long Term Evolution
    NR      = "NR"       # 5G New Radio (3GPP standard identifier)
    FIVEG   = "5G"       # 5G (legacy mobile-app string — some devices send "5G")
    WCDMA   = "WCDMA"    # 3G Wideband CDMA
    GSM     = "GSM"      # 2G Global System for Mobile
    UNKNOWN = "Unknown"  # Technology not reported / unrecognised


class RawMeasurement(Base):
    """
    Stores every individual signal measurement uploaded by a mobile device.

    This is the highest-volume table in the system; rows are append-only and
    never updated.  Writes come from the ingestion endpoint; reads are mostly
    done by the aggregation job that populates grid_scores.

    Columns
    -------
    device_timestamp  : UTC time the device recorded the sample.
    server_timestamp  : UTC time the server received it (set by the DB).
    lat / lon         : WGS-84 coordinates (plain Float; PostGIS geometry is
                        on grid_cells for boundary polygons).
    precision         : GPS horizontal accuracy in metres (lower = better).
    speed             : Device speed in m/s, nullable.
    bearing           : Compass heading in degrees [0–360), nullable.
    operator_id       : MCC+MNC concatenated, e.g. "28601" (Turkcell TR).
    technology        : Radio access type: LTE or NR (5G).
    cell_id           : E-UTRAN / NR cell identifier, nullable.
    rsrp              : Reference Signal Received Power, dBm  (–140 … –44).
    rsrq              : Reference Signal Received Quality, dB  (–20 … –3).
    sinr              : Signal-to-Interference-plus-Noise Ratio, dB.
    quality_score     : Composite 1–5 score derived from RSRP + SINR.
                        Set by the scoring service after ingestion.
    sample_weight     : Per-sample weight used during grid aggregation.
                        Derived from GPS accuracy, recency, and speed.
    is_cleaned        : True once the cleaning pipeline has validated and
                        de-duplicated this row.  Only cleaned rows are fed
                        into the aggregation engine.
    """

    __tablename__ = "raw_measurements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Timestamps
    device_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    server_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Location
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)  # accuracy m
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)      # m/s
    bearing: Mapped[float | None] = mapped_column(Float, nullable=True)    # degrees

    # Cell identity
    operator_id: Mapped[str] = mapped_column(String(10), nullable=False)   # MCC+MNC
    technology: Mapped[Technology] = mapped_column(SAEnum(Technology), nullable=False)
    cell_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Signal metrics
    rsrp: Mapped[float | None] = mapped_column(Float, nullable=True)  # dBm
    rsrq: Mapped[float | None] = mapped_column(Float, nullable=True)  # dB
    sinr: Mapped[float | None] = mapped_column(Float, nullable=True)  # dB

    # Derived / pipeline columns — populated by the processing services
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_cleaned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Indexes: time-based queries are the most common access pattern.
    # A composite index on (operator_id, server_timestamp) supports
    # per-operator aggregation windows efficiently.
    __table_args__ = (
        Index("ix_raw_server_ts", "server_timestamp"),
        Index("ix_raw_operator_ts", "operator_id", "server_timestamp"),
        Index("ix_raw_lat_lon", "lat", "lon"),
        Index("ix_raw_is_cleaned", "is_cleaned"),
    )

    def __repr__(self) -> str:
        return (
            f"<RawMeasurement id={self.id} op={self.operator_id} "
            f"tech={self.technology} rsrp={self.rsrp} score={self.quality_score}>"
        )
