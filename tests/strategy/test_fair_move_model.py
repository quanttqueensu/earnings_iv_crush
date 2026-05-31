"""Tests for the fair-move regression: coefficient recovery, NaN handling,
walk-forward look-ahead safety."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategy.fair_move_model import FairMoveModel


def _events(n=200, seed=0):
    rng = np.random.default_rng(seed)
    rv = rng.uniform(0.2, 0.8, n)
    skew = rng.uniform(-0.1, 0.1, n)
    return pd.DataFrame({"trailing_rv": rv, "skew_25d": skew})


def test_recovers_known_coefficients():
    ev = _events()
    # realised_move = 0.02 + 0.10*rv + 0.50*skew, no noise -> OLS recovers exactly.
    y = 0.02 + 0.10 * ev["trailing_rv"] + 0.50 * ev["skew_25d"]
    model = FairMoveModel().fit(ev, y)

    assert model.used_features == ["trailing_rv", "skew_25d"]
    params = model.result.params
    assert params["const"] == pytest.approx(0.02, abs=1e-6)
    assert params["trailing_rv"] == pytest.approx(0.10, abs=1e-6)
    assert params["skew_25d"] == pytest.approx(0.50, abs=1e-6)


def test_predict_is_nonnegative_and_aligned():
    ev = _events(50)
    y = 0.02 + 0.10 * ev["trailing_rv"] + 0.50 * ev["skew_25d"]
    model = FairMoveModel().fit(ev, y)
    pred = model.predict(ev)
    assert len(pred) == len(ev)
    assert (pred >= 0).all()
    assert pred.index.equals(ev.index)


def test_ignores_entirely_missing_features():
    ev = _events(60)
    ev["eps_dispersion"] = np.nan      # pending source -> all NaN
    ev["oi_growth"] = np.nan
    y = 0.02 + 0.10 * ev["trailing_rv"]
    model = FairMoveModel().fit(ev, y)
    # The all-NaN columns are dropped, the populated ones kept.
    assert "eps_dispersion" not in model.used_features
    assert "trailing_rv" in model.used_features


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        FairMoveModel().predict(_events(5))


def test_walk_forward_no_lookahead():
    ev = _events(60)
    y = 0.02 + 0.10 * ev["trailing_rv"] + 0.50 * ev["skew_25d"]
    preds = FairMoveModel().fit_predict_walk_forward(ev, y, min_train=20)

    # First min_train rows have no out-of-sample prediction.
    assert preds.iloc[:20].isna().all()
    assert preds.iloc[20:].notna().all()

    # Row i must equal a model fit only on rows [0, i) -> proves no look-ahead.
    i = 40
    ref = FairMoveModel().fit(ev.iloc[:i], y.iloc[:i]).predict(ev.iloc[[i]]).iloc[0]
    assert preds.iloc[i] == pytest.approx(ref)
