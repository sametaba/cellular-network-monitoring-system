"""
Data Cleaning Service  (WP2)
----------------------------
Applies the 3GPP-consistent range validation and deduplication rules
described in the project methodology.

All thresholds are module-level constants so they can be changed or
loaded from config without modifying business logic.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.schemas.raw_measurement import RawMeasurementCreate

# ── 3GPP TS 36.214 physical-layer measurement ranges ──────────────────────────
RSRP_MIN, RSRP_MAX = -140.0, -44.0   # dBm
RSRQ_MIN, RSRQ_MAX = -20.0, -3.0    # dB
SINR_MIN, SINR_MAX = -23.0, 40.0    # dB

# GPS horizontal accuracy — readings beyond this are too imprecise to trust.
PRECISION_MAX_M = 500.0

# Deduplication thresholds:
#   Two samples are considered duplicates if they share nearly identical
#   location, technology, and signal values within a short time window.
DEDUP_DISTANCE_M = 5.0      # metres — max spatial separation for duplicates
DEDUP_TIME_S = 3.0          # seconds — max temporal separation for duplicates


# ── Helpers ───────────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return approximate great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _to_utc(dt: datetime) -> datetime:
    """Convert any timezone-aware or naive datetime to UTC-aware datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── Public API ─────────────────────────────────────────────────────────────────

def validate_ranges(row: RawMeasurementCreate) -> tuple[bool, str]:
    """
    Check that all signal metrics fall within physically meaningful ranges.

    Returns (True, "") if the row passes, or (False, reason) if it fails.
    Only fields that are present (not None) are checked — a missing RSRQ
    is acceptable; a RSRQ of -1 dB is not.
    """
    if row.precision is not None and row.precision > PRECISION_MAX_M:
        return False, f"precision {row.precision}m exceeds {PRECISION_MAX_M}m limit"

    if row.rsrp is not None and not (RSRP_MIN <= row.rsrp <= RSRP_MAX):
        return False, f"rsrp {row.rsrp} outside [{RSRP_MIN}, {RSRP_MAX}]"

    if row.rsrq is not None and not (RSRQ_MIN <= row.rsrq <= RSRQ_MAX):
        return False, f"rsrq {row.rsrq} outside [{RSRQ_MIN}, {RSRQ_MAX}]"

    if row.sinr is not None and not (SINR_MIN <= row.sinr <= SINR_MAX):
        return False, f"sinr {row.sinr} outside [{SINR_MIN}, {SINR_MAX}]"

    return True, ""


def normalize_timestamps(rows: list[RawMeasurementCreate]) -> list[RawMeasurementCreate]:
    """
    Ensure all device_timestamps are timezone-aware UTC.

    Naive timestamps are assumed to be UTC (common when Android logs
    System.currentTimeMillis() without explicit TZ info).
    Returns a new list; input is not mutated.
    """
    result = []
    for row in rows:
        utc_ts = _to_utc(row.device_timestamp)
        result.append(row.model_copy(update={"device_timestamp": utc_ts}))
    return result


def _avg_optional(values: list) -> float | None:
    """Return the mean of non-None values, or None if all are None."""
    non_null = [v for v in values if v is not None]
    return sum(non_null) / len(non_null) if non_null else None


def _average_cluster(cluster: list[RawMeasurementCreate]) -> RawMeasurementCreate:
    """
    Collapse a burst cluster into a single representative measurement.

    Numeric signal metrics (rsrp, rsrq, sinr) and location fields
    (lat, lon, precision, speed) are averaged over the cluster members.
    The representative timestamp is the earliest in the cluster.
    Categorical fields (operator_id, technology, cell_id, bearing) are
    taken from the anchor (cluster[0]) — they are identical within a
    valid cluster.
    """
    if len(cluster) == 1:
        return cluster[0]

    anchor = cluster[0]
    earliest_ts = min(_to_utc(r.device_timestamp) for r in cluster)

    return anchor.model_copy(update={
        "device_timestamp": earliest_ts,
        "lat":       sum(r.lat for r in cluster) / len(cluster),
        "lon":       sum(r.lon for r in cluster) / len(cluster),
        "precision": _avg_optional([r.precision for r in cluster]),
        "speed":     _avg_optional([r.speed for r in cluster]),
        "rsrp":      _avg_optional([r.rsrp for r in cluster]),
        "rsrq":      _avg_optional([r.rsrq for r in cluster]),
        "sinr":      _avg_optional([r.sinr for r in cluster]),
    })


def deduplicate(rows: list[RawMeasurementCreate]) -> list[RawMeasurementCreate]:
    """
    Cluster near-duplicate burst measurements and collapse each cluster
    into a single averaged record.

    Two rows belong to the same cluster when they share:
      - operator_id and technology (same network context)
      - spatial separation  ≤ DEDUP_DISTANCE_M metres (5 m)
      - temporal separation ≤ DEDUP_TIME_S seconds   (3 s)

    For each cluster the representative row is produced by _average_cluster():
      - Signal metrics (rsrp, rsrq, sinr) → arithmetic mean of non-None values
      - Location (lat, lon, precision, speed) → centroid / mean
      - Timestamp → earliest device_timestamp in the cluster

    Algorithm:
      Rows are sorted by device_timestamp so that the inner scan can apply
      an early-exit the moment the time gap exceeds DEDUP_TIME_S — this
      keeps practical complexity close to O(n × k) where k is cluster size.

    Time complexity: O(n²) worst case (one giant cluster), O(n) best case.
    Acceptable for typical batch sizes (< 10 000 rows per upload).
    """
    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda r: _to_utc(r.device_timestamp))
    n = len(sorted_rows)
    processed = [False] * n
    result: list[RawMeasurementCreate] = []

    for i, anchor in enumerate(sorted_rows):
        if processed[i]:
            continue

        cluster = [anchor]
        processed[i] = True
        anchor_utc = _to_utc(anchor.device_timestamp)

        for j in range(i + 1, n):
            if processed[j]:
                continue

            candidate = sorted_rows[j]
            cand_utc = _to_utc(candidate.device_timestamp)

            # Early exit: list is sorted, so no later row can match the anchor's window.
            if (cand_utc - anchor_utc).total_seconds() > DEDUP_TIME_S:
                break

            if (
                candidate.operator_id != anchor.operator_id
                or candidate.technology != anchor.technology
            ):
                continue

            dist = _haversine_m(candidate.lat, candidate.lon, anchor.lat, anchor.lon)
            if dist <= DEDUP_DISTANCE_M:
                cluster.append(candidate)
                processed[j] = True

        result.append(_average_cluster(cluster))

    return result


def clean_batch(
    rows: list[RawMeasurementCreate],
) -> tuple[list[RawMeasurementCreate], list[str]]:
    """
    Run the full cleaning pipeline on a list of measurements.

    Pipeline:
      1. Range validation  → rejects physically impossible values
      2. Timestamp normalisation → ensures UTC-aware datetimes
      3. Deduplication → removes near-identical consecutive samples

    Returns:
      cleaned : rows that passed all checks (ready for DB insert)
      errors  : human-readable rejection reasons
    """
    valid: list[RawMeasurementCreate] = []
    errors: list[str] = []

    for i, row in enumerate(rows):
        ok, reason = validate_ranges(row)
        if not ok:
            errors.append(f"row {i}: {reason}")
        else:
            valid.append(row)

    normalized = normalize_timestamps(valid)
    deduped = deduplicate(normalized)

    removed_by_dedup = len(normalized) - len(deduped)
    if removed_by_dedup:
        errors.append(f"{removed_by_dedup} duplicate(s) removed")

    return deduped, errors
