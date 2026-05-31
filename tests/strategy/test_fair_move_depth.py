"""Tests for the fair-move model depth: diagnostics, ridge, OOS evaluation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategy.fair_move_model import FairMoveModel


def _events(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "trailing_rv": rng.uniform(0.2, 0.8, n),
        "skew_25d": rng.uniform(-0.1, 0.1, n),
    })


def _clean_target(ev):
    return 0.02 + 0.10 * ev["trailing_rv"] + 0.50 * ev["skew_25d"]


# --- diagnostics -------------------------------------------------------------

def test_ols_diagnostics_report_perfect_fit_without_noise():
    ev = _events()
    model = FairMoveModel().fit(ev, _clean_target(ev))
    d = model.diagnostics()
    assert d["method"] == "ols"
    assert d["r_squared"] == pytest.approx(1.0, abs=1e-9)
    assert set(d["tstats"]) == {"const", "trailing_rv", "skew_25d"}
    assert d["params"]["trailing_rv"] == pytest.approx(0.10, abs=1e-6)


def test_diagnostics_before_fit_raises():
    with pytest.raises(RuntimeError):
        FairMoveModel().diagnostics()


# --- ridge -------------------------------------------------------------------

def test_ridge_fits_predicts_and_reports_params():
    ev = _events(120)
    model = FairMoveModel(method="ridge", alpha=0.5).fit(ev, _clean_target(ev))
    pred = model.predict(ev)
    assert len(pred) == len(ev) and (pred >= 0).all()
    d = model.diagnostics()
    assert d["method"] == "ridge"
    assert set(d["params"]) == {"const", "trailing_rv", "skew_25d"}
    assert d["tstats"] is None


def test_ridge_walk_forward_runs():
    ev = _events(60)
    preds = FairMoveModel(method="ridge").fit_predict_walk_forward(
        ev, _clean_target(ev), min_train=20
    )
    assert preds.iloc[:20].isna().all()
    assert preds.iloc[20:].notna().all()


# --- out-of-sample evaluation ------------------------------------------------

def test_evaluate_walk_forward_recovers_clean_signal():
    ev = _events(120)
    out = FairMoveModel().evaluate_walk_forward(ev, _clean_target(ev), min_train=20)
    assert out["n_oos"] == 100
    assert out["oos_r2"] > 0.99
    assert out["calibration_slope"] == pytest.approx(1.0, abs=0.05)
    assert out["mae"] == pytest.approx(0.0, abs=1e-3)


def test_evaluate_walk_forward_degrades_with_noise():
    ev = _events(150, seed=2)
    rng = np.random.default_rng(9)
    noisy = _clean_target(ev) + rng.normal(0, 0.05, len(ev))
    out = FairMoveModel().evaluate_walk_forward(ev, noisy, min_train=20)
    # Still positively skilled, but no longer a perfect fit.
    assert 0.0 < out["oos_r2"] < 0.99
    assert out["corr"] > 0.0
