"""
test_smile_strike.py
Offline checks of the hedged strangle engine: with equal strikes and equal volatilities it must
reproduce ``hedged_short_straddle`` exactly, and wing selection must take the nearest quoted
strikes outside one implied move.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.research.hedged_hold import hedged_short_straddle

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research" / "execution" / "2026-11-02-smile-strike-hedged-hold" / "study.py"


@pytest.fixture(scope="module")
def sm():
    spec = importlib.util.spec_from_file_location("smile_strike", STUDY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("k", [95.0, 100.0, 104.0])
def test_equal_strikes_reproduce_straddle(sm, seed, k):
    rng = np.random.default_rng(seed)
    n = 6
    rets = rng.normal(0, 0.02, n)
    closes = 100 * np.cumprod(np.r_[1.0, 1 + rets[:-1]])
    settle = float(closes[-1] * (1 + rets[-1]))
    taus = np.linspace(8, 3, n) / 365
    hs = np.full(n, 3e-4)
    ref = hedged_short_straddle(
        sale_price=6.0,
        sale_mid=6.2,
        strike=k,
        fwd=100.0,
        closes=closes,
        rets=rets,
        taus=taus,
        sigmas=np.full(n, 0.4),
        half_spreads=hs,
        settle_close=settle,
    )
    got = sm.hedged_short_strangle(
        sale=6.0,
        kc=k,
        kp=k,
        closes=closes,
        rets=rets,
        taus=taus,
        sig_c=0.4,
        sig_p=0.4,
        half_spreads=hs,
        settle=settle,
    )
    assert got["net"] == pytest.approx(ref.net_pnl, abs=1e-10)
    assert got["hedge_pnl"] == pytest.approx(ref.hedge_pnl, abs=1e-10)


def test_pick_wings_nearest_outside_one_move(sm):
    c = pd.DataFrame(
        {
            "strike": [85, 90, 95, 100, 105, 110, 115] * 2,
            "right": ["C"] * 7 + ["P"] * 7,
            "bid": [0.0] * 5 + [0.5, 0.2] + [0.1, 0.0, 0.6, 2.0, 0.0, 0.0, 0.0],
            "ask": [1.0] * 14,
        }
    )
    w = sm.pick_wings(c, fwd=100.0, im=0.08)
    assert w is not None
    call, put = w
    assert call["strike"] == 110 and put["strike"] == 85  # 90 put has no bid
