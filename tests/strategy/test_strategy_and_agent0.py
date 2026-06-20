"""Tests for run_strategy and run_agent0, plus the end-to-end planted-edge check.

The strategy must select a subset of events and, on the simulated planted edge,
beat the unfiltered Agent 0 control on Sharpe.
"""

from __future__ import annotations

from earnings_iv_crush.baseline.agent0 import run_agent0
from earnings_iv_crush.engine.backtester import backtest
from earnings_iv_crush.engine.pnl import LEDGER_COLUMNS
from earnings_iv_crush.engine.simulate import simulate_events
from earnings_iv_crush.strategy.fair_move_model import FairMoveModel
from earnings_iv_crush.strategy.strategy import run_strategy


def _events():
    return simulate_events(n=300, seed=3, edge_frac=0.35)


def test_agent0_books_every_event_by_default():
    ev = _events()
    ledger = run_agent0(ev, seed=3)
    assert list(ledger.columns) == LEDGER_COLUMNS
    assert len(ledger) == len(ev)  # unfiltered, sample_frac=1.0


def test_agent0_subsamples_with_sample_frac():
    ev = _events()
    ledger = run_agent0(ev, seed=3, sample_frac=0.5)
    assert len(ledger) == 150


def test_strategy_selects_a_strict_subset():
    ev = _events()
    model = FairMoveModel().fit(ev, ev["realised_move"])
    ledger = run_strategy(ev, model)
    assert list(ledger.columns) == LEDGER_COLUMNS
    assert 0 < len(ledger) < len(ev)  # the filter actually bites
    assert set(ledger["ticker"]).issubset(set(ev["ticker"]))


def test_strategy_concentrates_on_rich_events():
    ev = _events()
    model = FairMoveModel().fit(ev, ev["realised_move"])
    ledger = run_strategy(ev, model)
    rich_tickers = set(ev.loc[ev["is_rich"], "ticker"])
    hit_rich = sum(t in rich_tickers for t in ledger["ticker"]) / len(ledger)
    assert hit_rich > 0.7  # mostly the planted rich events


def test_strategy_beats_agent0_on_planted_edge():
    ev = _events()
    model = FairMoveModel().fit(ev, ev["realised_move"])
    strat = backtest(run_strategy(ev, model))
    agent0 = backtest(run_agent0(ev, seed=3))
    # The filter wins on per-trade quality, not absolute P&L (it trades fewer
    # names, so Agent 0's gross P&L is naturally larger).
    assert strat["sharpe"] - agent0["sharpe"] >= 0.5
    assert strat["avg_return_on_margin"] > agent0["avg_return_on_margin"]
    assert strat["hit_rate"] > agent0["hit_rate"]


def test_empty_events_yield_empty_ledgers():
    empty = simulate_events(n=0)
    model_events = simulate_events(n=60, seed=1)
    model = FairMoveModel().fit(model_events, model_events["realised_move"])
    assert run_strategy(empty, model).empty
    assert run_agent0(empty).empty
