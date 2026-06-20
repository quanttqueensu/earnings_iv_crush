"""Tests for the Phase-2 volatility features (VRP, Goyal-Saretto, BKM moments)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.data import features
from earnings_iv_crush.engine.greeks import bs_price
from earnings_iv_crush.strategy.fair_move_model import FairMoveModel

# --- volatility premium / VRP ------------------------------------------------


def test_volatility_premium_is_iv_minus_rv():
    assert features.volatility_premium(0.50, 0.30) == pytest.approx(0.20)
    assert np.isnan(features.volatility_premium(float("nan"), 0.30))


def test_variance_risk_premium_is_iv2_minus_rv2():
    assert features.variance_risk_premium(0.50, 0.30) == pytest.approx(0.25 - 0.09)
    assert np.isnan(features.variance_risk_premium(0.5, float("nan")))


# --- BKM model-free moments --------------------------------------------------


def _bs_smile_chain(expiry, spot, t, slope):
    """Chain priced from a smile IV(K) = 0.40 + slope*(K-spot)/spot."""
    rows = []
    for k in range(70, 131, 5):
        iv = 0.40 + slope * (k - spot) / spot
        for right in ("C", "P"):
            px = bs_price(spot, k, t, 0.0, iv, right)
            rows.append(
                {
                    "expiry": pd.Timestamp(expiry),
                    "strike": float(k),
                    "right": right,
                    "bid": px,
                    "ask": px,
                    "iv": iv,
                    "open_interest": 100,
                }
            )
    return pd.DataFrame(rows)


def test_bkm_left_skew_is_negative():
    # IV falls as strike rises (puts richer) -> left-skewed risk-neutral law.
    chain = _bs_smile_chain("2026-06-05", spot=100.0, t=0.1, slope=-0.30)
    m = features.bkm_moments(chain, pd.Timestamp("2026-06-05"), 100.0, 0.1)
    assert m["bkm_var"] > 0
    assert m["bkm_skew"] < 0
    assert np.isfinite(m["bkm_kurt"])


def test_bkm_thin_chain_is_nan():
    # Only one strike each side of spot -> insufficient for the integration.
    rows = []
    for k in (95, 105):
        right = "P" if k < 100 else "C"
        rows.append(
            {
                "expiry": pd.Timestamp("2026-06-05"),
                "strike": float(k),
                "right": right,
                "bid": 1.0,
                "ask": 1.0,
                "iv": 0.4,
                "open_interest": 1,
            }
        )
    m = features.bkm_moments(pd.DataFrame(rows), pd.Timestamp("2026-06-05"), 100.0, 0.1)
    assert np.isnan(m["bkm_skew"])


# --- model picks up the new features -----------------------------------------


def test_fair_move_model_uses_new_features_when_present():
    rng = np.random.default_rng(0)
    n = 150
    ev = pd.DataFrame(
        {
            "trailing_rv": rng.uniform(0.2, 0.8, n),
            "skew_25d": rng.uniform(-0.1, 0.1, n),
            "vol_premium": rng.uniform(-0.1, 0.3, n),
            "variance_risk_premium": rng.uniform(-0.05, 0.2, n),
        }
    )
    y = 0.02 + 0.1 * ev["trailing_rv"] + 0.3 * ev["variance_risk_premium"]
    model = FairMoveModel().fit(ev, y)
    assert "variance_risk_premium" in model.used_features
    assert "vol_premium" in model.used_features


def test_fair_move_model_graceful_without_new_features():
    # Frames lacking the new columns must behave exactly as before.
    rng = np.random.default_rng(1)
    ev = pd.DataFrame(
        {"trailing_rv": rng.uniform(0.2, 0.8, 80), "skew_25d": rng.uniform(-0.1, 0.1, 80)}
    )
    model = FairMoveModel().fit(ev, 0.02 + 0.1 * ev["trailing_rv"])
    assert model.used_features == ["trailing_rv", "skew_25d"]
