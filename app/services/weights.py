"""
Sample Weight Calculation Service  (WP3)
-----------------------------------------
Computes a per-measurement aggregation weight w_i ∈ (0, 1] that reflects
how much an individual sample should contribute to the grid-cell aggregate.

Three independent sub-factors are multiplied together:

  w_i = accuracy_factor  ×  recency_factor  ×  motion_factor

Each sub-factor is exposed as a standalone function so it can be tested and
tuned independently.  All thresholds are module-level constants.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# ── Constants — all thresholds are named so they can be adjusted centrally ───

# GPS accuracy: measurements with horizontal error ≤ this threshold receive
# the maximum accuracy weight of 1.0.  Errors above degrade the weight.
GPS_REFERENCE_PRECISION_M: float = 20.0

# Recency: the weight of a measurement halves every RECENCY_HALF_LIFE_HOURS.
# A half-life of 10 h means: age 0 h → 1.0, age 10 h → 0.5, age 24 h → 0.19.
RECENCY_HALF_LIFE_HOURS: float = 10.0

# Motion context thresholds (m/s)
SPEED_WALKING_LOW: float = 1.0   # below this → Stationary
SPEED_WALKING_HIGH: float = 3.0  # below this → Walking; above → Driving

# Motion factor values — stationary is best because the device is fixed
# relative to the cell, walking is moderate, driving causes rapid cell
# changes and Doppler spread that reduce measurement reliability.
MOTION_STATIONARY: float = 1.0
MOTION_WALKING: float = 0.7
MOTION_DRIVING: float = 0.5

# Fallback weight for unknown speed — treated as walking (conservative)
_MOTION_UNKNOWN: float = MOTION_WALKING
# Fallback weight for unknown precision — half the maximum (neutral)
_ACCURACY_UNKNOWN: float = 0.5


# ── Sub-factor functions ──────────────────────────────────────────────────────

def _accuracy_factor(precision_m: float | None) -> float:
    """
    GPS accuracy weight.

    Smaller horizontal error radius → higher weight:
      precision ≤ GPS_REFERENCE_PRECISION_M (20 m) → 1.0  (maximum)
      precision = 50 m  → 0.40
      precision = 100 m → 0.20
      precision = 500 m → 0.04  (approaching the cleaning cutoff)

    Formula: min(1.0, GPS_REFERENCE_PRECISION_M / max(precision_m, 1.0))

    Args:
        precision_m: GPS horizontal accuracy in metres, or None if unknown.

    Returns:
        Float in (0.0, 1.0].
    """
    if precision_m is None:
        return _ACCURACY_UNKNOWN
    return min(1.0, GPS_REFERENCE_PRECISION_M / max(precision_m, 1.0))


def _recency_factor(server_timestamp: datetime, now: datetime | None = None) -> float:
    """
    Recency weight — newer measurements contribute more to aggregates.

    Uses exponential decay:
      factor = exp(-λ × age_hours),  λ = ln(2) / RECENCY_HALF_LIFE_HOURS

    With RECENCY_HALF_LIFE_HOURS = 10:
      age = 0 h  → 1.000
      age = 10 h → 0.500
      age = 24 h → 0.189
      age = 48 h → 0.036

    Args:
        server_timestamp: When the server received the measurement (UTC).
        now:              Reference time; defaults to UTC now if not given.
                          Pass a fixed value in tests for deterministic output.

    Returns:
        Float in (0.0, 1.0].
    """
    now_utc: datetime = now or datetime.now(tz=timezone.utc)

    # Ensure server_timestamp is timezone-aware
    if server_timestamp.tzinfo is None:
        server_timestamp = server_timestamp.replace(tzinfo=timezone.utc)

    age_seconds = (now_utc - server_timestamp).total_seconds()
    age_hours = max(0.0, age_seconds / 3600.0)  # clamp negative (clock skew)

    lam = math.log(2.0) / RECENCY_HALF_LIFE_HOURS
    return math.exp(-lam * age_hours)


def _motion_factor(speed_ms: float | None) -> float:
    """
    Motion context weight.

    A stationary device (e.g. on a windowsill) records stable, repeatable
    signals from the same cell sector.  A moving device introduces multi-path
    variation, Doppler effects, and rapid hand-off events that reduce the
    signal's representativeness for a fixed geographic cell.

      < 1.0 m/s  (Stationary) → 1.0  (full weight)
      1.0–3.0 m/s (Walking)   → 0.7
      > 3.0 m/s  (Driving)    → 0.5  (minimum weight)
      None (unknown)           → 0.7  (conservative fallback)

    Args:
        speed_ms: Device speed in m/s, or None if unavailable.

    Returns:
        Float in {0.5, 0.7, 1.0}.
    """
    if speed_ms is None:
        return _MOTION_UNKNOWN
    if speed_ms < SPEED_WALKING_LOW:
        return MOTION_STATIONARY
    if speed_ms <= SPEED_WALKING_HIGH:
        return MOTION_WALKING
    return MOTION_DRIVING


# ── Public API ────────────────────────────────────────────────────────────────

def calculate_weight(
    precision_m: float | None,
    server_timestamp: datetime,
    speed_ms: float | None,
    now: datetime | None = None,
) -> float:
    """
    Compute the per-sample aggregation weight.

    w_i = accuracy_factor(precision_m)
        × recency_factor(server_timestamp, now)
        × motion_factor(speed_ms)

    Range: (0.0, 1.0] — all three sub-factors are individually bounded in
    (0.0, 1.0], so their product is strictly positive and at most 1.0.

    Args:
        precision_m:       GPS horizontal accuracy radius in metres (or None).
        server_timestamp:  UTC datetime when the server ingested the row.
        speed_ms:          Device speed in m/s at measurement time (or None).
        now:               Override the current time (useful in tests).

    Returns:
        Float weight in (0.0, 1.0].

    Example:
        >>> from datetime import datetime, timezone
        >>> now = datetime.now(tz=timezone.utc)
        >>> calculate_weight(5.0, now, 0.0)   # precise GPS, fresh, stationary
        1.0
        >>> calculate_weight(200.0, now, 10.0) # coarse GPS, fresh, driving
        0.05
    """
    return (
        _accuracy_factor(precision_m)
        * _recency_factor(server_timestamp, now)
        * _motion_factor(speed_ms)
    )
