"""
XGBoost Coverage Predictor
----------------------------
Trains per-metric XGBoost regressors on measured H3 cells and predicts
QoE / MOS / quality_score / RSRP / SINR for unmeasured cells using
spatial lag features (neighbor averages).

Overfitting Protection
~~~~~~~~~~~~~~~~~~~~~~
- **No raw lat/lon features** — only spatial-lag features from neighbors.
- **Shallow trees**: max_depth=4 limits model complexity.
- **Low learning rate**: 0.05 with 100 estimators (conservative).
- **L1 + L2 regularization**: reg_alpha=1.0, reg_lambda=5.0.
- **Row / column subsampling**: 80 % each per tree.
- **min_child_weight=5**: prevents splits on tiny leaf groups.

XGBoost handles NaN natively in both training and inference, so
missing neighbor data flows through without explicit imputation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import xgboost as xgb

from app.ml.features import compute_spatial_features

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "coverage_predictor.joblib"

# ── Feature column order (must match training and inference) ─────────────────
FEATURE_COLUMNS: list[str] = [
    # Ring 1
    "ring1_mean_qoe",
    "ring1_mean_rsrp",
    "ring1_mean_sinr",
    "ring1_mean_rsrq",
    "ring1_mean_quality",
    "ring1_mean_mos",
    "ring1_mean_confidence",
    "ring1_std_rsrp",
    "ring1_count",
    "ring1_coverage_ratio",
    # Ring 2
    "ring2_mean_qoe",
    "ring2_mean_rsrp",
    "ring2_mean_sinr",
    "ring2_mean_rsrq",
    "ring2_mean_quality",
    "ring2_mean_mos",
    "ring2_mean_confidence",
    "ring2_std_rsrp",
    "ring2_count",
    "ring2_coverage_ratio",
]

# ── Prediction targets ──────────────────────────────────────────────────────
TARGET_COLUMNS: list[str] = [
    "qoe_index",
    "estimated_mos",
    "quality_score",
    "aggregated_rsrp",
    "aggregated_sinr",
]

# Physical bounds for clamping predictions
_CLAMP_RANGES: dict[str, tuple[float, float]] = {
    "qoe_index": (1.0, 100.0),
    "estimated_mos": (1.0, 5.0),
    "quality_score": (1.0, 5.0),
    "aggregated_rsrp": (-140.0, -44.0),
    "aggregated_sinr": (-23.0, 40.0),
}

# Minimum measured cells required to train a meaningful model
MIN_TRAINING_SAMPLES = 20

# Maximum fraction of NaN features allowed per sample
MAX_NAN_RATIO = 0.5


class CoveragePredictor:
    """
    Spatial interpolation model using one XGBoost regressor per target metric.

    Training uses measured H3 cells: for each cell, spatial lag features are
    computed from its neighbors and its own metrics serve as the target.

    Inference uses unmeasured cells: spatial lag features from measured
    neighbors are fed to the trained models to predict the target metrics.
    """

    def __init__(self) -> None:
        self.models: dict[str, xgb.XGBRegressor] = {}
        self.is_fitted: bool = False

    @staticmethod
    def _create_model() -> xgb.XGBRegressor:
        """Create an XGBoost regressor with strict overfitting protection."""
        return xgb.XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            reg_alpha=1.0,       # L1 regularization
            reg_lambda=5.0,      # L2 regularization (stronger)
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
        )

    @staticmethod
    def _build_feature_row(feat_dict: dict[str, float]) -> list[float]:
        """Extract ordered feature values from a feature dict."""
        return [feat_dict.get(col, float("nan")) for col in FEATURE_COLUMNS]

    @staticmethod
    def _nan_ratio(row: list[float]) -> float:
        """Fraction of NaN values in a feature row."""
        if not row:
            return 1.0
        nan_count = sum(1 for v in row if v != v)  # NaN != NaN
        return nan_count / len(row)

    # ── Training ─────────────────────────────────────────────────────────────

    def train(
        self,
        scores_lookup: dict[str, dict[str, Any]],
    ) -> dict[str, float]:
        """
        Train one XGBoost model per target metric.

        For each measured cell, compute spatial lag features from its neighbors
        and use the cell's own metric as the training target.

        Args:
            scores_lookup: All measured cells ``{h3_index: {metric: value}}``.

        Returns:
            Dict of ``{target_name: train_rmse}``.
        """
        h3_indices = list(scores_lookup.keys())
        if len(h3_indices) < MIN_TRAINING_SAMPLES:
            logger.warning(
                "Not enough training samples (%d < %d). Skipping training.",
                len(h3_indices),
                MIN_TRAINING_SAMPLES,
            )
            return {}

        # Build feature matrix and target vectors
        X_rows: list[list[float]] = []
        targets: dict[str, list[float]] = {t: [] for t in TARGET_COLUMNS}
        valid_mask: list[bool] = []

        for idx in h3_indices:
            feat_dict = compute_spatial_features(idx, scores_lookup)
            row = self._build_feature_row(feat_dict)

            # Skip cells with too many missing features
            if self._nan_ratio(row) > MAX_NAN_RATIO:
                continue

            X_rows.append(row)
            cell = scores_lookup[idx]
            for t in TARGET_COLUMNS:
                val = cell.get(t)
                targets[t].append(float(val) if val is not None else float("nan"))

        if len(X_rows) < MIN_TRAINING_SAMPLES:
            logger.warning(
                "After NaN filtering, only %d usable rows (< %d). Skipping.",
                len(X_rows),
                MIN_TRAINING_SAMPLES,
            )
            return {}

        X = np.array(X_rows, dtype=np.float32)
        metrics: dict[str, float] = {}

        for target_name in TARGET_COLUMNS:
            y = np.array(targets[target_name], dtype=np.float32)

            # Drop rows where target itself is NaN
            valid = ~np.isnan(y)
            if valid.sum() < MIN_TRAINING_SAMPLES:
                logger.warning(
                    "Target '%s' has only %d valid values. Skipping.",
                    target_name,
                    int(valid.sum()),
                )
                continue

            X_valid = X[valid]
            y_valid = y[valid]

            model = self._create_model()
            model.fit(X_valid, y_valid)
            self.models[target_name] = model

            # Training RMSE for logging
            preds = model.predict(X_valid)
            rmse = float(np.sqrt(np.mean((preds - y_valid) ** 2)))
            metrics[target_name] = round(rmse, 4)
            logger.info("Trained '%s': RMSE=%.4f (n=%d)", target_name, rmse, len(y_valid))

        self.is_fitted = len(self.models) > 0
        return metrics

    # ── Prediction ───────────────────────────────────────────────────────────

    def predict(
        self,
        empty_h3_indices: list[str],
        scores_lookup: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any] | None]:
        """
        Predict metrics for unmeasured cells.

        Args:
            empty_h3_indices: H3 indices of cells without measurements.
            scores_lookup:    Measured cells for feature computation.

        Returns:
            List parallel to *empty_h3_indices*.  Each entry is a dict of
            predicted metrics (clamped to valid ranges) plus metadata, or
            ``None`` when prediction is not possible (insufficient neighbor data).
        """
        if not self.is_fitted:
            logger.warning("Predictor not fitted. Returning empty predictions.")
            return [None] * len(empty_h3_indices)

        results: list[dict[str, Any] | None] = []

        for idx in empty_h3_indices:
            feat_dict = compute_spatial_features(idx, scores_lookup)
            row = self._build_feature_row(feat_dict)

            # Skip cells with insufficient spatial context
            if self._nan_ratio(row) > MAX_NAN_RATIO:
                results.append(None)
                continue

            X = np.array([row], dtype=np.float32)
            pred: dict[str, Any] = {"h3_index": idx}

            for target_name, model in self.models.items():
                try:
                    raw_val = float(model.predict(X)[0])
                    lo, hi = _CLAMP_RANGES[target_name]
                    pred[target_name] = round(max(lo, min(hi, raw_val)), 2)
                except Exception:
                    pred[target_name] = None

            # Prediction confidence based on neighbor coverage
            r1_cov = feat_dict.get("ring1_coverage_ratio", 0.0)
            r2_cov = feat_dict.get("ring2_coverage_ratio", 0.0)
            # Weight ring-1 more (closer neighbors are more informative)
            if not (r1_cov != r1_cov):  # NaN check
                confidence = 0.7 * r1_cov + 0.3 * r2_cov
            else:
                confidence = 0.0
            pred["prediction_confidence"] = round(min(1.0, confidence), 2)

            results.append(pred)

        return results

    # ── Persistence ──────────────────────────────────────────────────────────

    def save(self, path: Path = MODEL_PATH) -> None:
        """Save all sub-models + metadata as a single .joblib file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "models": self.models,
            "feature_columns": FEATURE_COLUMNS,
            "target_columns": TARGET_COLUMNS,
        }
        joblib.dump(payload, path)
        logger.info("Model saved to %s", path)

    def load(self, path: Path = MODEL_PATH) -> bool:
        """
        Load model from disk.

        Returns:
            True if loaded successfully, False if file does not exist.
        """
        if not path.exists():
            logger.info("No saved model found at %s", path)
            return False

        try:
            payload = joblib.load(path)
            self.models = payload["models"]
            self.is_fitted = len(self.models) > 0
            logger.info(
                "Loaded model with %d targets from %s",
                len(self.models),
                path,
            )
            return True
        except Exception as exc:
            logger.error("Failed to load model from %s: %s", path, exc)
            return False
