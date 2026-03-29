"""
Unit tests for app/services/scoring.py

Covers:
  - score_rsrp / score_sinr — 3GPP boundary conditions
  - composite_score — None fallback behaviour
  - advanced_composite_score — WHM edge cases and monotonicity
"""

import pytest

from app.services.scoring import (
    advanced_composite_score,
    composite_score,
    compute_mos,
    compute_network_fitness,
    compute_qoe,
    score_rsrp,
    score_sinr,
)


# ── score_rsrp ────────────────────────────────────────────────────────────────

class TestScoreRsrp:
    def test_none_returns_none(self):
        assert score_rsrp(None) is None

    def test_excellent_boundary(self):
        assert score_rsrp(-80.0) == 5
        assert score_rsrp(-44.0) == 5   # upper extreme

    def test_good_boundary(self):
        assert score_rsrp(-80.1) == 4
        assert score_rsrp(-90.0) == 4

    def test_fair_boundary(self):
        assert score_rsrp(-90.1) == 3
        assert score_rsrp(-100.0) == 3

    def test_poor_boundary(self):
        assert score_rsrp(-100.1) == 2
        assert score_rsrp(-110.0) == 2

    def test_very_poor(self):
        assert score_rsrp(-110.1) == 1
        assert score_rsrp(-140.0) == 1  # lower extreme


# ── score_sinr ────────────────────────────────────────────────────────────────

class TestScoreSinr:
    def test_none_returns_none(self):
        assert score_sinr(None) is None

    def test_excellent_boundary(self):
        assert score_sinr(20.0) == 5
        assert score_sinr(40.0) == 5   # upper extreme

    def test_good_boundary(self):
        assert score_sinr(19.9) == 4
        assert score_sinr(13.0) == 4

    def test_fair_boundary(self):
        assert score_sinr(12.9) == 3
        assert score_sinr(0.0) == 3

    def test_poor_boundary(self):
        assert score_sinr(-0.1) == 2
        assert score_sinr(-3.0) == 2

    def test_very_poor(self):
        assert score_sinr(-3.1) == 1
        assert score_sinr(-23.0) == 1  # lower extreme


# ── composite_score ───────────────────────────────────────────────────────────

class TestCompositeScore:
    def test_both_none_returns_none(self):
        assert composite_score(None, None) is None

    def test_rsrp_only(self):
        # RSRP=-80 → 5, no SINR → returns 5.0
        assert composite_score(-80.0, None) == 5.0

    def test_sinr_only(self):
        # SINR=20 → 5, no RSRP → returns 5.0
        assert composite_score(None, 20.0) == 5.0

    def test_min_strategy_rsrp_limits(self):
        # RSRP=-100 → 3, SINR=20 → 5, min=3
        assert composite_score(-100.0, 20.0) == 3.0

    def test_min_strategy_sinr_limits(self):
        # RSRP=-80 → 5, SINR=0 → 3, min=3
        assert composite_score(-80.0, 0.0) == 3.0

    def test_both_excellent(self):
        assert composite_score(-80.0, 20.0) == 5.0

    def test_returns_float(self):
        result = composite_score(-90.0, 13.0)
        assert isinstance(result, float)


# ── advanced_composite_score ──────────────────────────────────────────────────

class TestAdvancedCompositeScore:
    def test_both_none_returns_none(self):
        assert advanced_composite_score(None, None) is None

    def test_rsrp_only(self):
        # Only RSRP → continuous score returned directly
        result = advanced_composite_score(-90.0, None)
        assert result is not None
        assert 1.0 <= result <= 5.0

    def test_sinr_only(self):
        result = advanced_composite_score(None, 13.0)
        assert result is not None
        assert 1.0 <= result <= 5.0

    def test_both_excellent_gives_five(self):
        # RSRP=-44 → 5.0, SINR=40 → 5.0, WHM(5,5)=5.0
        result = advanced_composite_score(-44.0, 40.0)
        assert result is not None
        assert abs(result - 5.0) < 0.01

    def test_both_very_poor_gives_one(self):
        # RSRP=-140 → 1.0, SINR=-23 → 1.0, WHM(1,1)=1.0
        result = advanced_composite_score(-140.0, -23.0)
        assert result is not None
        assert abs(result - 1.0) < 0.01

    def test_asymmetric_penalty_between_min_and_mean(self):
        # RSRP=-44 → 5.0, SINR=-3 → 1.0
        # With 2 metrics, weights normalize: w_rsrp=0.45/0.80=0.5625, w_sinr=0.35/0.80=0.4375
        # WHM = 0.80 / (0.45/5 + 0.35/1) = 0.80 / (0.09 + 0.35) = 0.80/0.44 ≈ 1.818
        result = advanced_composite_score(-44.0, -3.0)
        assert result is not None
        assert 1.0 < result < 3.4
        assert abs(result - 1.818) < 0.05

    def test_output_clamped_to_range(self):
        # Any input should give output in [1, 5]
        for rsrp, sinr in [(-140, -23), (-44, 40), (-100, 0), (-80, 13)]:
            r = advanced_composite_score(float(rsrp), float(sinr))
            assert r is not None
            assert 1.0 <= r <= 5.0

    def test_monotone_in_rsrp(self):
        # Better RSRP → higher score (SINR fixed)
        sinr = 5.0
        scores = [advanced_composite_score(float(rsrp), sinr) for rsrp in [-130, -100, -80, -60, -44]]
        assert scores == sorted(scores), "score should increase with better RSRP"

    def test_monotone_in_sinr(self):
        # Better SINR → higher score (RSRP fixed)
        rsrp = -90.0
        scores = [advanced_composite_score(rsrp, float(sinr)) for sinr in [-20, -3, 0, 10, 20, 35]]
        assert scores == sorted(scores), "score should increase with better SINR"


# ── advanced_composite_score with RSRQ ──────────────────────────────────────

class TestAdvancedCompositeWithRsrq:
    def test_three_metrics_excellent(self):
        result = advanced_composite_score(-44.0, 40.0, -3.0)
        assert result is not None
        assert abs(result - 5.0) < 0.01

    def test_three_metrics_poor(self):
        result = advanced_composite_score(-140.0, -23.0, -20.0)
        assert result is not None
        assert abs(result - 1.0) < 0.01

    def test_rsrq_only(self):
        result = advanced_composite_score(None, None, -8.0)
        assert result is not None
        assert 1.0 <= result <= 5.0

    def test_rsrq_none_backward_compat(self):
        # 2-metric call should still work
        r2 = advanced_composite_score(-90.0, 13.0)
        r3 = advanced_composite_score(-90.0, 13.0, None)
        assert r2 == r3

    def test_three_metrics_better_than_two(self):
        # Adding a good RSRQ should not decrease the score when other metrics are good
        r2 = advanced_composite_score(-80.0, 20.0)
        r3 = advanced_composite_score(-80.0, 20.0, -3.0)
        assert r3 is not None and r2 is not None
        # Both excellent, should be close to 5.0
        assert abs(r3 - r2) < 0.5


# ── compute_qoe ─────────────────────────────────────────────────────────────

class TestComputeQoe:
    def test_all_none_returns_none(self):
        assert compute_qoe(None, None, None) is None

    def test_excellent_signals_high_qoe(self):
        result = compute_qoe(-44.0, 40.0, -3.0)
        assert result is not None
        assert result >= 70.0

    def test_poor_signals_low_qoe(self):
        result = compute_qoe(-130.0, -10.0, -18.0)
        assert result is not None
        assert result <= 30.0

    def test_clamped_to_range(self):
        # Very good signals
        result = compute_qoe(-44.0, 40.0, -3.0)
        assert result is not None
        assert 1.0 <= result <= 100.0

        # Very bad signals
        result = compute_qoe(-140.0, -23.0, -20.0)
        assert result is not None
        assert 1.0 <= result <= 100.0

    def test_coverage_bonus(self):
        # RSRP > -80 triggers +10 bonus
        base = compute_qoe(-85.0, 10.0)
        bonus = compute_qoe(-75.0, 10.0)
        assert bonus is not None and base is not None
        assert bonus > base

    def test_interference_penalty(self):
        # SINR < 0 triggers -15 penalty
        good = compute_qoe(-90.0, 5.0)
        bad = compute_qoe(-90.0, -5.0)
        assert good is not None and bad is not None
        assert good > bad

    def test_single_metric(self):
        result = compute_qoe(-90.0, None, None)
        assert result is not None
        assert 1.0 <= result <= 100.0


# ── compute_mos ─────────────────────────────────────────────────────────────

class TestComputeMos:
    def test_all_none_returns_none(self):
        assert compute_mos(None, None, None) is None

    def test_excellent_signals_high_mos(self):
        result = compute_mos(-44.0, 40.0, -3.0)
        assert result is not None
        assert result >= 4.0

    def test_poor_signals_low_mos(self):
        result = compute_mos(-130.0, -10.0, -18.0)
        assert result is not None
        assert result <= 2.5

    def test_clamped_to_range(self):
        for rsrp, sinr, rsrq in [(-44, 40, -3), (-140, -23, -20), (-90, 0, -11)]:
            r = compute_mos(float(rsrp), float(sinr), float(rsrq))
            assert r is not None
            assert 1.0 <= r <= 5.0

    def test_monotone_in_sinr(self):
        mos_values = [compute_mos(-90.0, float(s)) for s in [-20, -3, 0, 13, 20, 35]]
        assert mos_values == sorted(mos_values), "MOS should increase with better SINR"

    def test_single_metric(self):
        result = compute_mos(None, 10.0, None)
        assert result is not None
        assert 1.0 <= result <= 5.0


# ── compute_network_fitness ─────────────────────────────────────────────────

class TestNetworkFitness:
    def test_all_none_all_false(self):
        result = compute_network_fitness(None, None, None)
        assert result == {"streaming": False, "volte": False, "iot": False}

    def test_excellent_all_true(self):
        result = compute_network_fitness(-80.0, 20.0, -5.0)
        assert result["streaming"] is True
        assert result["volte"] is True
        assert result["iot"] is True

    def test_streaming_threshold(self):
        # Streaming needs SINR>=2 and RSRP>=-105
        assert compute_network_fitness(-105.0, 2.0)["streaming"] is True
        assert compute_network_fitness(-105.0, 1.9)["streaming"] is False
        assert compute_network_fitness(-105.1, 2.0)["streaming"] is False

    def test_volte_threshold(self):
        # VoLTE needs SINR>=0 and RSRP>=-110
        assert compute_network_fitness(-110.0, 0.0)["volte"] is True
        assert compute_network_fitness(-110.0, -0.1)["volte"] is False

    def test_iot_threshold(self):
        # IoT needs RSRP>=-120
        assert compute_network_fitness(-120.0, None)["iot"] is True
        assert compute_network_fitness(-120.1, None)["iot"] is False
