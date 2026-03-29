"""
Unit tests for app/services/weights.py

Covers:
  - _accuracy_factor  — GPS precision → weight mapping
  - _recency_factor   — exponential decay with known half-life
  - _motion_factor    — speed category boundaries
  - calculate_weight  — composed product, edge combinations
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.services.weights import (
    MOTION_DRIVING,
    MOTION_STATIONARY,
    MOTION_WALKING,
    RECENCY_HALF_LIFE_HOURS,
    _accuracy_factor,
    _motion_factor,
    _recency_factor,
    calculate_weight,
)

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ── _accuracy_factor ──────────────────────────────────────────────────────────

class TestAccuracyFactor:
    def test_none_returns_half(self):
        assert _accuracy_factor(None) == 0.5

    def test_perfect_precision_gives_one(self):
        # 5 m ≤ 20 m reference → capped at 1.0
        assert _accuracy_factor(5.0) == 1.0

    def test_at_reference_gives_one(self):
        assert _accuracy_factor(20.0) == 1.0

    def test_degrades_above_reference(self):
        # precision=40m → 20/40 = 0.5
        assert abs(_accuracy_factor(40.0) - 0.5) < 1e-9

    def test_large_precision_is_small(self):
        # precision=500m → 20/500 = 0.04
        assert abs(_accuracy_factor(500.0) - 0.04) < 1e-9

    def test_zero_precision_uses_max(self):
        # precision=0 → max(0,1)=1 → 20/1=20 → capped at 1.0
        assert _accuracy_factor(0.0) == 1.0


# ── _recency_factor ───────────────────────────────────────────────────────────

class TestRecencyFactor:
    def test_fresh_measurement_gives_one(self):
        result = _recency_factor(_NOW, now=_NOW)
        assert abs(result - 1.0) < 1e-9

    def test_half_life_gives_half(self):
        old = _NOW - timedelta(hours=RECENCY_HALF_LIFE_HOURS)
        result = _recency_factor(old, now=_NOW)
        assert abs(result - 0.5) < 1e-6

    def test_two_half_lives_gives_quarter(self):
        old = _NOW - timedelta(hours=2 * RECENCY_HALF_LIFE_HOURS)
        result = _recency_factor(old, now=_NOW)
        assert abs(result - 0.25) < 1e-6

    def test_future_timestamp_clamped_to_one(self):
        future = _NOW + timedelta(hours=5)
        result = _recency_factor(future, now=_NOW)
        assert abs(result - 1.0) < 1e-9

    def test_naive_timestamp_treated_as_utc(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)  # no tzinfo
        result = _recency_factor(naive, now=_NOW)
        assert abs(result - 1.0) < 1e-9

    def test_decay_is_monotone(self):
        ages_h = [0, 5, 10, 24, 48]
        scores = [_recency_factor(_NOW - timedelta(hours=h), now=_NOW) for h in ages_h]
        assert scores == sorted(scores, reverse=True), "older → lower weight"


# ── _motion_factor ────────────────────────────────────────────────────────────

class TestMotionFactor:
    def test_none_returns_walking(self):
        assert _motion_factor(None) == MOTION_WALKING

    def test_stationary_below_low(self):
        assert _motion_factor(0.0) == MOTION_STATIONARY
        assert _motion_factor(0.99) == MOTION_STATIONARY

    def test_walking_at_low_boundary(self):
        assert _motion_factor(1.0) == MOTION_WALKING
        assert _motion_factor(3.0) == MOTION_WALKING

    def test_driving_above_high(self):
        assert _motion_factor(3.01) == MOTION_DRIVING
        assert _motion_factor(30.0) == MOTION_DRIVING

    def test_ordering(self):
        assert MOTION_STATIONARY > MOTION_WALKING > MOTION_DRIVING


# ── calculate_weight ──────────────────────────────────────────────────────────

class TestCalculateWeight:
    def test_ideal_conditions_gives_one(self):
        # precision=5m (≤20 ref), fresh, stationary
        w = calculate_weight(5.0, _NOW, 0.0, now=_NOW)
        assert abs(w - 1.0) < 1e-9

    def test_poor_gps_reduces_weight(self):
        w_good = calculate_weight(5.0, _NOW, 0.0, now=_NOW)
        w_bad  = calculate_weight(200.0, _NOW, 0.0, now=_NOW)
        assert w_bad < w_good

    def test_old_measurement_reduces_weight(self):
        w_fresh = calculate_weight(5.0, _NOW, 0.0, now=_NOW)
        w_old   = calculate_weight(5.0, _NOW - timedelta(hours=24), 0.0, now=_NOW)
        assert w_old < w_fresh

    def test_driving_reduces_weight(self):
        w_stationary = calculate_weight(5.0, _NOW, 0.0, now=_NOW)
        w_driving    = calculate_weight(5.0, _NOW, 10.0, now=_NOW)
        assert w_driving < w_stationary

    def test_weight_always_positive(self):
        # Worst plausible inputs (but within valid ranges)
        w = calculate_weight(499.0, _NOW - timedelta(hours=48), 30.0, now=_NOW)
        assert w > 0.0

    def test_weight_at_most_one(self):
        w = calculate_weight(1.0, _NOW, 0.0, now=_NOW)
        assert w <= 1.0 + 1e-9

    def test_coarse_driving_old_is_small(self):
        # precision=200m, 24h old, driving
        w = calculate_weight(200.0, _NOW - timedelta(hours=24), 10.0, now=_NOW)
        # 20/200 * exp(-ln2/10*24) * 0.5 ≈ 0.1 * 0.189 * 0.5 ≈ 0.0094
        assert w < 0.02
