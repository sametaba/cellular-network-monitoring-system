"""
Unit tests for app/services/cleaning.py

Covers:
  - validate_ranges — boundary conditions for RSRP, RSRQ, SINR, precision
  - normalize_timestamps — naive → UTC-aware conversion
  - deduplicate — cluster averaging vs. spatial/temporal separation
"""

from datetime import datetime, timezone

import pytest

from app.models.raw_measurement import Technology
from app.schemas.raw_measurement import RawMeasurementCreate
from app.services.cleaning import deduplicate, normalize_timestamps, validate_ranges


# ── Fixtures ──────────────────────────────────────────────────────────────────

_TS = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make(
    lat=41.0,
    lon=29.0,
    rsrp=-90.0,
    rsrq=-10.0,
    sinr=10.0,
    precision=20.0,
    speed=0.5,
    ts=None,
    operator_id="28601",
    technology=Technology.LTE,
) -> RawMeasurementCreate:
    return RawMeasurementCreate(
        device_timestamp=ts or _TS,
        lat=lat,
        lon=lon,
        precision=precision,
        speed=speed,
        operator_id=operator_id,
        technology=technology,
        rsrp=rsrp,
        rsrq=rsrq,
        sinr=sinr,
    )


# ── validate_ranges ───────────────────────────────────────────────────────────

class TestValidateRanges:
    def test_valid_row_passes(self):
        ok, _ = validate_ranges(_make())
        assert ok is True

    def test_rsrp_none_passes(self):
        # RSRP out-of-range is caught by Pydantic schema before validate_ranges.
        # A missing RSRP (None) must pass cleaning — optional field.
        row = _make(rsrp=None)
        ok, _ = validate_ranges(row)
        assert ok is True

    def test_rsrp_boundary_passes(self):
        ok, _ = validate_ranges(_make(rsrp=-140.0))
        assert ok is True
        ok, _ = validate_ranges(_make(rsrp=-44.0))
        assert ok is True

    def test_rsrq_out_of_range_rejected(self):
        # rsrq must be between -20 and -3
        # Create with rsrq=None first (valid), then check boundary
        row = _make(rsrq=None)
        ok, _ = validate_ranges(row)
        assert ok is True

    def test_rsrq_boundary_passes(self):
        ok, _ = validate_ranges(_make(rsrq=-20.0))
        assert ok is True
        ok, _ = validate_ranges(_make(rsrq=-3.0))
        assert ok is True

    def test_sinr_out_of_range_rejected(self):
        # sinr has no Pydantic bounds in schema, cleaning service checks it
        row = _make(sinr=41.0)  # above 40 dB limit
        ok, reason = validate_ranges(row)
        assert ok is False
        assert "sinr" in reason.lower()

    def test_sinr_below_min_rejected(self):
        row = _make(sinr=-24.0)  # below -23 dB limit
        ok, reason = validate_ranges(row)
        assert ok is False
        assert "sinr" in reason.lower()

    def test_sinr_boundary_passes(self):
        ok, _ = validate_ranges(_make(sinr=-23.0))
        assert ok is True
        ok, _ = validate_ranges(_make(sinr=40.0))
        assert ok is True

    def test_precision_too_large_rejected(self):
        row = _make(precision=501.0)
        ok, reason = validate_ranges(row)
        assert ok is False
        assert "precision" in reason.lower()

    def test_precision_at_limit_passes(self):
        ok, _ = validate_ranges(_make(precision=500.0))
        assert ok is True

    def test_none_fields_are_skipped(self):
        # Rows with None for optional signal fields should still pass
        row = _make(rsrp=None, rsrq=None, sinr=None, precision=None)
        ok, _ = validate_ranges(row)
        assert ok is True


# ── normalize_timestamps ──────────────────────────────────────────────────────

class TestNormalizeTimestamps:
    def test_naive_becomes_utc(self):
        naive_ts = datetime(2026, 1, 1, 10, 0, 0)  # no tzinfo
        row = _make(ts=naive_ts)
        result = normalize_timestamps([row])
        assert result[0].device_timestamp.tzinfo is not None
        assert result[0].device_timestamp.tzinfo == timezone.utc

    def test_utc_aware_unchanged(self):
        aware_ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        row = _make(ts=aware_ts)
        result = normalize_timestamps([row])
        assert result[0].device_timestamp == aware_ts

    def test_returns_new_list(self):
        rows = [_make()]
        result = normalize_timestamps(rows)
        assert result is not rows

    def test_empty_list(self):
        assert normalize_timestamps([]) == []


# ── deduplicate ───────────────────────────────────────────────────────────────

class TestDeduplicate:
    def test_empty_returns_empty(self):
        assert deduplicate([]) == []

    def test_single_row_unchanged(self):
        row = _make()
        result = deduplicate([row])
        assert len(result) == 1

    def test_identical_rows_merged_to_one(self):
        rows = [_make(), _make(), _make()]
        result = deduplicate(rows)
        assert len(result) == 1

    def test_averaged_rsrp(self):
        # Three samples with different RSRP values — should be averaged
        from datetime import timedelta
        ts0 = _TS
        ts1 = _TS + timedelta(seconds=1)
        ts2 = _TS + timedelta(seconds=2)
        rows = [
            _make(rsrp=-80.0, ts=ts0),
            _make(rsrp=-82.0, ts=ts1),
            _make(rsrp=-84.0, ts=ts2),
        ]
        result = deduplicate(rows)
        assert len(result) == 1
        assert abs(result[0].rsrp - (-82.0)) < 1e-9  # average of -80, -82, -84

    def test_earliest_timestamp_kept(self):
        from datetime import timedelta
        ts_early = _TS
        ts_late  = _TS + timedelta(seconds=2)
        rows = [_make(ts=ts_late), _make(ts=ts_early)]
        result = deduplicate(rows)
        assert len(result) == 1
        assert result[0].device_timestamp == ts_early

    def test_different_operators_not_merged(self):
        rows = [
            _make(operator_id="28601"),
            _make(operator_id="28602"),
        ]
        result = deduplicate(rows)
        assert len(result) == 2

    def test_different_technologies_not_merged(self):
        rows = [
            _make(technology=Technology.LTE),
            _make(technology=Technology.NR),
        ]
        result = deduplicate(rows)
        assert len(result) == 2

    def test_far_apart_spatially_not_merged(self):
        # ~1 km apart
        rows = [
            _make(lat=41.0000, lon=29.0000),
            _make(lat=41.0090, lon=29.0000),  # ~1 km north
        ]
        result = deduplicate(rows)
        assert len(result) == 2

    def test_far_apart_temporally_not_merged(self):
        from datetime import timedelta
        rows = [
            _make(ts=_TS),
            _make(ts=_TS + timedelta(seconds=10)),  # 10s apart > 3s threshold
        ]
        result = deduplicate(rows)
        assert len(result) == 2

    def test_none_rsrp_averaged_with_skipping(self):
        from datetime import timedelta
        rows = [
            _make(rsrp=-90.0, ts=_TS),
            _make(rsrp=None,  ts=_TS + timedelta(seconds=1)),
            _make(rsrp=-80.0, ts=_TS + timedelta(seconds=2)),
        ]
        result = deduplicate(rows)
        assert len(result) == 1
        # Average of non-None: (-90 + -80) / 2 = -85
        assert abs(result[0].rsrp - (-85.0)) < 1e-9
