"""
test_demo_pipeline.py
The day-one demo has to keep working, because it is the first thing a new member runs
after the suite and a broken one is worse than none.

The substantive assertion is that the synthetic generator stays *fair*: it draws the
realised move at the scale the straddle charges for it, so the gross book must sit near
zero. If someone tunes the generator until the demo shows an edge, the demo stops being
a wiring check and starts being an advertisement, and this fails.
"""

from __future__ import annotations

import numpy as np

from earnings_iv_crush.engine.costs import CostModel
from earnings_iv_crush.engine.pnl import build_ledger
from scripts.demo_pipeline import make_events

REQUIRED = [
    "ticker",
    "announce_date",
    "entry_date",
    "exit_date",
    "spot_entry",
    "spot_exit",
    "strike",
    "t_entry",
    "t_exit",
    "iv_entry",
    "iv_exit",
]


def test_generator_supplies_every_column_build_ledger_needs() -> None:
    ev = make_events(120, seed=0)
    missing = [c for c in REQUIRED if c not in ev.columns]
    assert not missing, f"demo events missing {missing}"
    assert len(ev) == 120
    assert ev["announce_date"].is_monotonic_increasing


def test_generator_is_fair_so_the_gross_book_sits_near_zero() -> None:
    """No gross edge by construction. A demo that shows one has been tuned."""
    ev = make_events(1500, seed=0)
    gross = build_ledger(ev)
    r = gross["return_on_margin"]
    per_trade_sharpe = float(r.mean() / r.std())
    assert abs(per_trade_sharpe) < 0.12, (
        f"gross per-trade Sharpe {per_trade_sharpe:+.4f} is not near zero; the synthetic "
        "generator has stopped pricing the announcement fairly"
    )


def test_costs_move_the_book_the_only_direction_they_can() -> None:
    ev = make_events(400, seed=1)
    gross = build_ledger(ev)["return_on_margin"].mean()
    net = build_ledger(ev, costs=CostModel())["return_on_margin"].mean()
    assert net < gross, "charging the cost stack must reduce the book"


def test_demo_is_deterministic_under_a_seed() -> None:
    a = make_events(80, seed=3)["spot_exit"].to_numpy()
    b = make_events(80, seed=3)["spot_exit"].to_numpy()
    assert np.array_equal(a, b)
    c = make_events(80, seed=4)["spot_exit"].to_numpy()
    assert not np.array_equal(a, c)
