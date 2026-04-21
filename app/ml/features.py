"""
Spatial Feature Engineering for AI Coverage Prediction
-------------------------------------------------------
Computes neighbor-based (spatial lag) features using H3 grid_ring.

DESIGN DECISION — Why NOT raw lat/lon:
  Raw coordinates let tree-based models memorize exact positions instead of
  learning generalizable signal propagation patterns.  Spatial lag features
  (neighbor averages, coverage ratio, RSRP std) encode the local RF
  environment without geographic specificity, preventing overfitting.
"""

from __future__ import annotations

import math
from typing import Any

import h3
import numpy as np


# Metrics extracted from each neighbor cell
_METRIC_KEYS = (
    "qoe_index",
    "aggregated_rsrp",
    "aggregated_sinr",
    "aggregated_rsrq",
    "quality_score",
    "estimated_mos",
    "confidence_score",
)

# Short aliases used in feature names
_METRIC_ALIASES = {
    "qoe_index": "qoe",
    "aggregated_rsrp": "rsrp",
    "aggregated_sinr": "sinr",
    "aggregated_rsrq": "rsrq",
    "quality_score": "quality",
    "estimated_mos": "mos",
    "confidence_score": "confidence",
}


def _safe_mean(values: list[float]) -> float:
    """Return mean of non-empty list, or NaN."""
    if not values:
        return float("nan")
    return float(np.nanmean(values))


def _safe_std(values: list[float]) -> float:
    """Return population std of non-empty list, or NaN."""
    if len(values) < 2:
        return float("nan")
    return float(np.nanstd(values))


def compute_spatial_features(
    h3_index: str,
    scores_lookup: dict[str, dict[str, Any]],
    *,
    k_rings: tuple[int, ...] = (1, 2),
) -> dict[str, float]:
    """
    Compute spatial lag features for an H3 cell from its ring neighbors.

    For each ring distance k in *k_rings*, this function produces:
      - ring{k}_mean_{metric}  — average of neighbor values
      - ring{k}_std_rsrp       — RSRP variability (signal heterogeneity)
      - ring{k}_count          — number of measured neighbors
      - ring{k}_coverage_ratio — fraction of ring cells with data

    Args:
        h3_index:      Target cell's H3 index.
        scores_lookup: Mapping of h3_index → metric dict.  Each dict should
                       contain keys from _METRIC_KEYS with float|None values.
        k_rings:       Ring distances to compute features for.

    Returns:
        Dict of feature_name → float.  Missing data → ``float('nan')``.
    """
    features: dict[str, float] = {}

    for k in k_rings:
        prefix = f"ring{k}"

        # Get cells at exactly distance k (ring, not disk)
        try:
            ring_cells = h3.grid_ring(h3_index, k)
        except Exception:
            # Invalid H3 index or unsupported operation — fill with NaN
            for alias in _METRIC_ALIASES.values():
                features[f"{prefix}_mean_{alias}"] = float("nan")
            features[f"{prefix}_std_rsrp"] = float("nan")
            features[f"{prefix}_count"] = float("nan")
            features[f"{prefix}_coverage_ratio"] = float("nan")
            continue

        total_ring_size = len(ring_cells)
        if total_ring_size == 0:
            for alias in _METRIC_ALIASES.values():
                features[f"{prefix}_mean_{alias}"] = float("nan")
            features[f"{prefix}_std_rsrp"] = float("nan")
            features[f"{prefix}_count"] = 0.0
            features[f"{prefix}_coverage_ratio"] = 0.0
            continue

        # Collect metric values from neighbors that have data
        metric_values: dict[str, list[float]] = {key: [] for key in _METRIC_KEYS}
        measured_count = 0

        for cell in ring_cells:
            cell_data = scores_lookup.get(cell)
            if cell_data is None:
                continue
            measured_count += 1
            for key in _METRIC_KEYS:
                val = cell_data.get(key)
                if val is not None and not (isinstance(val, float) and math.isnan(val)):
                    metric_values[key].append(float(val))

        # Compute mean for each metric
        for key in _METRIC_KEYS:
            alias = _METRIC_ALIASES[key]
            features[f"{prefix}_mean_{alias}"] = _safe_mean(metric_values[key])

        # RSRP standard deviation — captures signal variability
        features[f"{prefix}_std_rsrp"] = _safe_std(
            metric_values["aggregated_rsrp"]
        )

        # Count and coverage ratio
        features[f"{prefix}_count"] = float(measured_count)
        features[f"{prefix}_coverage_ratio"] = (
            measured_count / total_ring_size if total_ring_size > 0 else 0.0
        )

    return features
