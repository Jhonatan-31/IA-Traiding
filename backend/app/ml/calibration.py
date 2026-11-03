"""Probability calibration — fit on train/val only; score on held-out test."""
from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss


def expected_calibration_error(
    y_true: np.ndarray, proba: np.ndarray, n_bins: int = 10
) -> float | None:
    y_true = np.asarray(y_true, dtype=float)
    proba = np.asarray(proba, dtype=float)
    if len(y_true) < n_bins or len(np.unique(y_true)) < 2:
        return None
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    total = len(y_true)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (proba >= lo) & (proba < hi if i < n_bins - 1 else proba <= hi)
        if not np.any(mask):
            continue
        conf = float(proba[mask].mean())
        acc = float(y_true[mask].mean())
        ece += (mask.sum() / total) * abs(acc - conf)
    return float(ece)


def reliability_diagram(
    y_true: np.ndarray, proba: np.ndarray, n_bins: int = 8
) -> dict[str, Any] | None:
    if len(y_true) < 20 or len(np.unique(y_true)) < 2:
        return None
    frac_pos, mean_pred = calibration_curve(
        y_true, proba, n_bins=n_bins, strategy="quantile"
    )
    return {
        "fraction_positives": [float(x) for x in frac_pos],
        "mean_predicted": [float(x) for x in mean_pred],
    }


def score_calibration(y_true: np.ndarray, proba: np.ndarray) -> dict[str, Any]:
    out: dict[str, Any] = {
        "n": int(len(y_true)),
        "brier": None,
        "log_loss": None,
        "ece": expected_calibration_error(y_true, proba),
        "reliability": reliability_diagram(y_true, proba),
    }
    try:
        out["brier"] = float(brier_score_loss(y_true, proba))
    except ValueError:
        pass
    try:
        out["log_loss"] = float(log_loss(y_true, proba, labels=[0, 1]))
    except ValueError:
        pass
    return out


class _ProbaCalibrator(BaseEstimator, ClassifierMixin):
    """Wraps a fitted base model + a 1D calibrator on positive-class probability."""

    def __init__(self, base=None, calibrator=None, method: str = "isotonic"):
        self.base = base
        self.calibrator = calibrator
        self.method = method

    def fit(self, X, y):
        return self

    def predict_proba(self, X):
        raw = self.base.predict_proba(X)[:, 1]
        if self.method == "isotonic":
            cal = np.clip(self.calibrator.predict(raw), 1e-6, 1 - 1e-6)
        else:
            # sigmoid via logistic on raw prob reshaped
            cal = self.calibrator.predict_proba(raw.reshape(-1, 1))[:, 1]
        out = np.column_stack([1 - cal, cal])
        return out

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def _fit_manual_calibrator(base, X_val, y_val, method: str):
    raw = base.predict_proba(X_val)[:, 1]
    if method == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(raw, y_val)
        return _ProbaCalibrator(base=base, calibrator=iso, method="isotonic")
    # sigmoid / Platt on validation scores
    lr = LogisticRegression(max_iter=500)
    lr.fit(raw.reshape(-1, 1), y_val)
    return _ProbaCalibrator(base=base, calibrator=lr, method="sigmoid")


def fit_calibrators_on_val(
    base_estimator,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> dict[str, Any]:
    """
    Fit isotonic and sigmoid calibrators using ONLY train+val.
    Method selection uses val Brier — never the final test fold.
    Compatible with sklearn versions that removed cv='prefit'.
    """
    results: dict[str, Any] = {"methods": {}}
    raw = clone(base_estimator)
    raw.fit(X_train, y_train)
    raw_proba = raw.predict_proba(X_val)[:, 1]
    results["methods"]["uncalibrated"] = score_calibration(y_val, raw_proba)

    chosen = "uncalibrated"
    best_brier = results["methods"]["uncalibrated"].get("brier")
    calibrators: dict[str, Any] = {"uncalibrated": raw}

    for method in ("isotonic", "sigmoid"):
        try:
            # Prefer FrozenEstimator path when available
            try:
                from sklearn.frozen import FrozenEstimator

                base = clone(base_estimator)
                base.fit(X_train, y_train)
                cal = CalibratedClassifierCV(FrozenEstimator(base), method=method)
                cal.fit(X_val, y_val)
            except Exception:
                base = clone(base_estimator)
                base.fit(X_train, y_train)
                cal = _fit_manual_calibrator(base, X_val, y_val, method)

            proba = cal.predict_proba(X_val)[:, 1]
            sc = score_calibration(y_val, proba)
            results["methods"][method] = sc
            calibrators[method] = cal
            b = sc.get("brier")
            if b is not None and (best_brier is None or b < best_brier):
                best_brier = b
                chosen = method
        except Exception as exc:
            results["methods"][method] = {"error": f"{type(exc).__name__}: {exc}"}

    results["selected_on_validation"] = chosen
    results["selected_estimator"] = calibrators[chosen]
    results["note"] = (
        "Method chosen by lowest Brier on validation only; evaluate on held-out test separately."
    )
    return results


def bootstrap_ci(
    values: list[float], *, n_boot: int = 500, alpha: float = 0.05, seed: int = 7
) -> dict[str, float | None]:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return {
            "mean": float(arr.mean()) if len(arr) else None,
            "low": None,
            "high": None,
            "n": len(arr),
        }
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        means.append(float(sample.mean()))
    low = float(np.quantile(means, alpha / 2))
    high = float(np.quantile(means, 1 - alpha / 2))
    return {"mean": float(arr.mean()), "low": low, "high": high, "n": int(len(arr))}
