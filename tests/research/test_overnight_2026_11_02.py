"""
test_overnight_2026_11_02.py
Offline checks for the open-hedge and maker-entry scorers: the open-hedge P&L term against a hand
calculation, and the resting-entry fill policy (limit, 15:59:00 cancel, improvement only on filled
legs) on a synthetic tick tape.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.research.hedged_hold import straddle_delta

ROOT = Path(__file__).resolve().parents[2]


def test_open_hedge_term_matches_hand():
    # the frozen formula: d_o (C - O) - 5bp |d_o| O - 3bp |d_o| C, over m0
    o, c, k, tau, sig, m0 = 108.0, 106.0, 100.0, 3 / 365, 0.30, 26.0
    d_o = straddle_delta(o, k, tau, sig)
    add = (d_o * (c - o) - 5e-4 * abs(d_o) * o - 3e-4 * abs(d_o) * c) / m0
    assert d_o > 0.9  # deep in the money after an up gap
    # an intraday reversal after an up gap makes the open hedge lose
    assert add < 0
    assert add == pytest.approx((d_o * -2.0 - d_o * (0.054 + 0.0318)) / m0)


@pytest.fixture(scope="module")
def f1():
    spec = importlib.util.spec_from_file_location(
        "flow", ROOT / "research" / "execution" / "research_flow_liquidity.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # optional deps of the closed study (dotenv, deploy helpers)
        pytest.skip(f"flow module not importable offline: {exc}")
    return mod


def _tape(day: str, rows: list[tuple[str, str, float, float, float]]) -> pd.DataFrame:
    t = pd.to_datetime([f"{day} {r[0]}" for r in rows]).tz_localize("America/New_York")
    return pd.DataFrame(
        {
            "t": t,
            "action": [r[1] for r in rows],
            "price": [r[4] for r in rows],
            "bid_px_00": [r[2] for r in rows],
            "ask_px_00": [r[3] for r in rows],
        }
    )


def test_resting_sell_fills_only_on_print_through(f1):
    leg = _tape(
        "2025-03-05",
        [
            ("14:59:00", "A", 1.90, 2.10, 0.0),  # 15:00 mid 2.00 -> limit 2.00
            ("15:20:00", "T", 1.95, 2.05, 2.00),  # print at the limit: strict rule ignores it
            ("15:40:00", "T", 1.96, 2.06, 2.01),  # print through the limit: fill
            ("15:58:30", "A", 1.80, 2.00, 0.0),
        ],
    )
    t15 = pd.Timestamp("2025-03-05 15:00", tz="America/New_York")
    t1559 = pd.Timestamp("2025-03-05 15:59", tz="America/New_York")
    q15 = f1._quote_at(leg, t15)
    limit = f1._round_limit(sum(q15) / 2, "sell", "penny")
    assert limit == pytest.approx(2.00)
    tf = f1._first_fill(leg, t15, t1559, limit, "sell", "strict")
    assert tf == pd.Timestamp("2025-03-05 15:40", tz="America/New_York")
    # improvement on this leg = limit - the 15:59:00 bid
    assert limit - f1._quote_at(leg, t1559)[0] == pytest.approx(0.20)
    assert np.isfinite(limit)
