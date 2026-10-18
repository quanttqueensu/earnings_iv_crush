"""
test_flow_liquidity_fill_rules.py
Pin the resting-order fill rules of research_flow_liquidity (addendum 01) on synthetic ticks.

The maker backtest is only as honest as its fill rule, so each rule is tested against a tape
whose correct answer is known by construction: strict versus optimistic trade prints, fills
from the quote alone, the window boundaries, and P&L-unfavourable tick rounding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.execution.research_flow_liquidity import TZ, _first_fill, _round_limit

DAY = pd.Timestamp("2025-04-24")
T0 = (DAY + pd.Timedelta(hours=15)).tz_localize(TZ)
T1 = (DAY + pd.Timedelta(hours=15, minutes=59, seconds=59)).tz_localize(TZ)


def _tape(rows: list[tuple[int, str, float, float, float]]) -> pd.DataFrame:
    """Rows of (seconds after 15:00, action, price, bid, ask)."""
    return pd.DataFrame(
        {
            "t": [T0 + pd.Timedelta(seconds=s) for s, *_ in rows],
            "action": [a for _, a, *_ in rows],
            "price": [p for *_, p, _, _ in rows],
            "bid_px_00": [b for *_, b, _ in rows],
            "ask_px_00": [a for *_, a in rows],
        }
    )


@pytest.mark.parametrize(
    "mid, side, schedule, expected",
    [
        (1.235, "sell", "penny", 1.23),
        (1.235, "buy", "penny", 1.24),
        (3.12, "sell", "penny", 3.10),
        (3.12, "buy", "penny", 3.15),
        (1.235, "sell", "nonpenny", 1.20),
        (3.12, "buy", "nonpenny", 3.20),
        (2.00, "sell", "penny", 2.00),
    ],
)
def test_round_limit_is_unfavourable(mid: float, side: str, schedule: str, expected: float) -> None:
    assert _round_limit(mid, side, schedule) == pytest.approx(expected)


def test_strict_needs_a_print_through_the_limit() -> None:
    tape = _tape([(10, "T", 2.00, 1.90, 2.10), (20, "T", 2.01, 1.90, 2.10)])
    assert _first_fill(tape, T0, T1, 2.00, "sell", "strict") == tape["t"].iloc[1]
    assert _first_fill(tape, T0, T1, 2.00, "sell", "optimistic") == tape["t"].iloc[0]


def test_quote_reaching_the_limit_fills_without_a_trade() -> None:
    tape = _tape([(5, "A", np.nan, 1.95, 2.10), (30, "A", np.nan, 2.00, 2.10)])
    assert _first_fill(tape, T0, T1, 2.00, "sell", "strict") == tape["t"].iloc[1]
    buy = _tape([(5, "A", np.nan, 1.90, 2.05), (30, "A", np.nan, 1.90, 2.00)])
    assert _first_fill(buy, T0, T1, 2.00, "buy", "strict") == buy["t"].iloc[1]


def test_no_fill_when_tape_stays_away() -> None:
    tape = _tape([(10, "T", 1.95, 1.90, 2.10), (20, "A", np.nan, 1.92, 2.08)])
    assert _first_fill(tape, T0, T1, 2.00, "sell", "strict") is None
    assert _first_fill(tape, T0, T1, 2.00, "sell", "optimistic") is None


def test_events_outside_the_window_are_ignored() -> None:
    late = pd.DataFrame(
        {
            "t": [T1 + pd.Timedelta(seconds=5)],
            "action": ["T"],
            "price": [2.50],
            "bid_px_00": [2.40],
            "ask_px_00": [2.60],
        }
    )
    assert _first_fill(late, T0, T1, 2.00, "sell", "strict") is None


def test_buy_side_mirrors_sell_side() -> None:
    tape = _tape([(10, "T", 2.00, 1.90, 2.10), (20, "T", 1.99, 1.90, 2.10)])
    assert _first_fill(tape, T0, T1, 2.00, "buy", "strict") == tape["t"].iloc[1]
    assert _first_fill(tape, T0, T1, 2.00, "buy", "optimistic") == tape["t"].iloc[0]


def test_limit_reference_falls_back_to_first_quote_after_window_start() -> None:
    from research.execution.research_flow_liquidity import _quote_after, _quote_at

    tape = _tape([(1, "A", np.nan, 1.90, 2.10), (90, "A", np.nan, 1.80, 2.00)])
    assert _quote_at(tape, T0) is None
    assert _quote_after(tape, T0, T0 + pd.Timedelta(minutes=1)) == (1.90, 2.10)
