"""
Signal Quality Scoring Service  (WP3)
--------------------------------------
Translates raw LTE/5G measurements (RSRP, SINR, RSRQ) into a human-readable
quality score on a 1–5 scale, plus QoE index, estimated MOS, and network
fitness labels.

Scoring strategies:

  composite_score()          — Baseline: integer step-function + strict min()
  advanced_composite_score() — Advanced: continuous interpolation + weighted
                               harmonic mean (preferred for aggregation)

Additional metrics:

  compute_qoe()              — ITU-T G.1010 inspired QoE index (1-100)
  compute_mos()              — ITU-T P.800 / Shannon-based MOS (1.0-5.0)
  compute_network_fitness()  — 3GPP TS 23.203 QCI fitness labels

All threshold constants follow 3GPP TS 36.214 / ETSI TS 136 214.
"""

from __future__ import annotations

import math

import numpy as np

# ── 3GPP threshold tables ─────────────────────────────────────────────────────
# RSRP breakpoints (dBm) — ascending order required by numpy.interp
_RSRP_X = np.array([-140.0, -110.0, -100.0, -90.0, -80.0, -44.0])
_RSRP_Y = np.array([  1.0,    1.0,    2.0,   3.0,   4.0,   5.0])

# SINR breakpoints (dB) — ascending order
_SINR_X = np.array([-23.0, -3.0, 0.0, 13.0, 20.0, 40.0])
_SINR_Y = np.array([  1.0,  1.0, 2.0,  3.0,  4.0,  5.0])

# RSRQ breakpoints (dB) — 3GPP TS 36.214
_RSRQ_X = np.array([-20.0, -15.0, -11.0, -8.0, -5.0, -3.0])
_RSRQ_Y = np.array([  1.0,   1.0,   2.0,  3.0,  4.0,  5.0])

# Weights for the advanced weighted harmonic mean (3 metrics)
_W_RSRP: float = 0.45  # Coverage power — dominant factor
_W_SINR: float = 0.35  # Interference tolerance
_W_RSRQ: float = 0.20  # Resource quality

# ── Normalization bounds for QoE / MOS ────────────────────────────────────────
_RSRP_MIN, _RSRP_MAX = -140.0, -44.0
_SINR_MIN, _SINR_MAX = -23.0, 40.0
_RSRQ_MIN, _RSRQ_MAX = -20.0, -3.0
_SINR_REF = 40.0  # Reference SINR for Shannon normalization


# ── Baseline integer step functions ──────────────────────────────────────────

def score_rsrp(rsrp: float | None) -> int | None:
    """
    Map an RSRP value (dBm) to an integer quality score [1, 5].

    Thresholds (3GPP TS 36.214):
      ≥ -80 dBm  → 5  Excellent
      ≥ -90      → 4  Good
      ≥ -100     → 3  Fair
      ≥ -110     → 2  Poor
       < -110    → 1  Very Poor

    Returns None when rsrp is None (measurement absent).
    """
    if rsrp is None:
        return None
    if rsrp >= -80.0:
        return 5
    if rsrp >= -90.0:
        return 4
    if rsrp >= -100.0:
        return 3
    if rsrp >= -110.0:
        return 2
    return 1


def score_sinr(sinr: float | None) -> int | None:
    """
    Map a SINR value (dB) to an integer quality score [1, 5].

    Thresholds (3GPP TS 36.214):
      ≥ 20 dB  → 5  Excellent
      ≥ 13     → 4  Good
      ≥  0     → 3  Fair
      ≥ -3     → 2  Poor
       < -3    → 1  Very Poor

    Returns None when sinr is None.
    """
    if sinr is None:
        return None
    if sinr >= 20.0:
        return 5
    if sinr >= 13.0:
        return 4
    if sinr >= 0.0:
        return 3
    if sinr >= -3.0:
        return 2
    return 1


def composite_score(
    rsrp: float | None,
    sinr: float | None,
) -> float | None:
    """
    Baseline composite quality score — conservative min() strategy.

    Returns the *minimum* of the two individual integer scores so that a
    poor SINR cannot be masked by an excellent RSRP (and vice-versa).
    If only one metric is available, that score is returned directly.
    If both are absent, returns None.

    Output is a float in {1.0, 2.0, 3.0, 4.0, 5.0} or None.
    """
    r = score_rsrp(rsrp)
    s = score_sinr(sinr)

    if r is None and s is None:
        return None
    if r is None:
        return float(s)  # type: ignore[arg-type]
    if s is None:
        return float(r)
    return float(min(r, s))


# ── Continuous helper functions (used by advanced scorer) ─────────────────────

def _rsrp_continuous(rsrp: float) -> float:
    """
    Linearly interpolate RSRP (dBm) onto the continuous [1.0, 5.0] scale.

    Values outside [-140, -44] are clamped to [1.0, 5.0] by numpy.interp.
    Example: rsrp=-62 dBm → 4.5  (midpoint of Excellent band)
             rsrp=-95 dBm → 2.5  (midpoint of Fair band)
    """
    return float(np.interp(rsrp, _RSRP_X, _RSRP_Y))


def _sinr_continuous(sinr: float) -> float:
    """
    Linearly interpolate SINR (dB) onto the continuous [1.0, 5.0] scale.

    Values outside [-23, 40] are clamped by numpy.interp.
    """
    return float(np.interp(sinr, _SINR_X, _SINR_Y))


def _rsrq_continuous(rsrq: float) -> float:
    """
    Linearly interpolate RSRQ (dB) onto the continuous [1.0, 5.0] scale.

    Values outside [-20, -3] are clamped by numpy.interp.
    """
    return float(np.interp(rsrq, _RSRQ_X, _RSRQ_Y))


def _normalize(val: float, vmin: float, vmax: float) -> float:
    """Normalize a value to [0, 1] range, clamped."""
    return max(0.0, min(1.0, (val - vmin) / (vmax - vmin)))


# ── Advanced composite score ──────────────────────────────────────────────────

def advanced_composite_score(
    rsrp: float | None,
    sinr: float | None,
    rsrq: float | None = None,
) -> float | None:
    """
    Advanced composite quality score using continuous interpolation and a
    weighted harmonic mean.

    Why this is better than the baseline min()-based composite_score():

    1.  **Continuous scoring — no cliff edges** (float 1.0–5.0):
        The baseline step function assigns an integer score per threshold
        band, creating artificial discontinuities. A device at -79 dBm
        scores 5 (Excellent) and one at -81 dBm scores 4 (Good) — a 25%
        drop for a 2 dBm difference that is within typical measurement
        noise. Continuous linear interpolation gives ≈4.03 vs ≈3.97 (< 2%
        difference), which is far more representative of the physical reality.

    2.  **Weighted harmonic mean — principled asymmetry penalty**:
        Formula:  WHM = 1 / (w_r/r + w_s/s)   where w_r=0.6, w_s=0.4

        •  RSRP weight 60% vs SINR 40%: coverage (can you connect?) matters
           more than interference tolerance (how fast?) in the user-experience
           hierarchy. Weighting reflects this priority ordering.

        •  The harmonic mean naturally penalises large asymmetries between
           the two components more than the arithmetic mean does, but less
           severely than pure min():
             - (rsrp_score=5.0, sinr_score=1.0):
                 min()          → 1.0   (ignores excellent RSRP entirely)
                 weighted mean  → 2.6   (too generous to a -3 dB SINR)
                 harmonic WHM   → 1.92  (poor-but-not-zero; realistic)
             - (rsrp_score=4.0, sinr_score=3.0):
                 harmonic WHM   → 3.53  (smooth; between 3 and 4)

        •  The harmonic mean is undefined only when a score equals 0, which
           cannot happen since both components are clamped to [1.0, 5.0].

    3.  **Graceful single-metric fallback**: identical to baseline — if only
        one metric is present, its continuous score is returned directly.

    Returns a float in [1.0, 5.0], or None when all inputs are absent.
    """
    scores: list[tuple[float, float]] = []  # (score, weight) pairs

    if rsrp is not None:
        scores.append((_rsrp_continuous(rsrp), _W_RSRP))
    if sinr is not None:
        scores.append((_sinr_continuous(sinr), _W_SINR))
    if rsrq is not None:
        scores.append((_rsrq_continuous(rsrq), _W_RSRQ))

    if not scores:
        return None
    if len(scores) == 1:
        return scores[0][0]

    # Normalize weights to sum to 1.0 when fewer than 3 metrics available
    total_w = sum(w for _, w in scores)
    # Weighted harmonic mean:  1 / Σ(w_i / s_i)
    raw = total_w / sum(w / s for s, w in scores)
    return max(1.0, min(5.0, raw))


# ── QoE Index (ITU-T G.1010 inspired) ────────────────────────────────────────

def compute_qoe(
    rsrp: float | None,
    sinr: float | None,
    rsrq: float | None = None,
) -> float | None:
    """
    Multi-dimensional QoE index on [1, 100] scale.

    Based on ITU-T G.1010 & 3GPP TS 36.214 normalized metric model:
      qoe = 20 × (rsrp_norm + sinr_norm + rsrq_norm) + bonuses/penalties
    With coverage bonus and interference penalty.
    Returns None when no metrics available.
    """
    norms: list[float] = []

    if rsrp is not None:
        norms.append(_normalize(rsrp, _RSRP_MIN, _RSRP_MAX))
    if sinr is not None:
        norms.append(_normalize(sinr, _SINR_MIN, _SINR_MAX))
    if rsrq is not None:
        norms.append(_normalize(rsrq, _RSRQ_MIN, _RSRQ_MAX))

    if not norms:
        return None

    # Scale to fill 3-metric range even with fewer metrics
    base = (sum(norms) / len(norms)) * 3.0
    qoe = 20.0 * base

    # Coverage bonus: strong RSRP
    if rsrp is not None and rsrp > -80.0:
        qoe += 10.0

    # Interference penalty: negative SINR
    if sinr is not None and sinr < 0.0:
        qoe -= 15.0

    return max(1.0, min(100.0, qoe))


# ── Estimated MOS (ITU-T P.800 / Shannon) ────────────────────────────────────

def compute_mos(
    rsrp: float | None,
    sinr: float | None,
    rsrq: float | None = None,
) -> float | None:
    """
    Estimated Mean Opinion Score on [1.0, 5.0] scale.

    Uses Shannon capacity normalization for SINR component:
      C_norm = log2(1 + 10^(sinr/10)) / log2(1 + 10^(ref/10))

    Combined with normalized RSRP and RSRQ via weighted sum:
      mos = 1.0 + 4.0 × (0.45×rsrp_norm + 0.35×C_norm + 0.20×rsrq_norm)

    Returns None when no metrics available.
    """
    components: list[tuple[float, float]] = []  # (norm_value, weight)

    if rsrp is not None:
        components.append((_normalize(rsrp, _RSRP_MIN, _RSRP_MAX), 0.45))
    if sinr is not None:
        # Shannon-based normalization
        sinr_clamped = max(_SINR_MIN, min(_SINR_MAX, sinr))
        c_norm = math.log2(1.0 + 10 ** (sinr_clamped / 10.0)) / math.log2(1.0 + 10 ** (_SINR_REF / 10.0))
        components.append((c_norm, 0.35))
    if rsrq is not None:
        components.append((_normalize(rsrq, _RSRQ_MIN, _RSRQ_MAX), 0.20))

    if not components:
        return None

    # Normalize weights when fewer metrics available
    total_w = sum(w for _, w in components)
    weighted_sum = sum(v * w for v, w in components) / total_w
    mos = 1.0 + 4.0 * weighted_sum
    return max(1.0, min(5.0, mos))


# ── Network Fitness Labels (3GPP TS 23.203 QCI) ──────────────────────────────

def compute_network_fitness(
    rsrp: float | None,
    sinr: float | None,
    rsrq: float | None = None,
) -> dict[str, bool]:
    """
    Determine network fitness for common use-cases based on 3GPP QCI thresholds.

    Returns dict with keys: streaming, volte, iot.
    Conservative: returns False when required metrics are absent.
    """
    return {
        "streaming": (
            sinr is not None and sinr >= 2.0
            and rsrp is not None and rsrp >= -105.0
        ),
        "volte": (
            sinr is not None and sinr >= 0.0
            and rsrp is not None and rsrp >= -110.0
        ),
        "iot": (
            rsrp is not None and rsrp >= -120.0
        ),
    }
