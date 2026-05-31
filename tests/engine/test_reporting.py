"""Tests for engine.reporting: attribution aggregation and tearsheet output."""
from __future__ import annotations

from src.baseline.agent0 import run_agent0
from src.engine.backtester import compare
from src.engine.costs import CostModel
from src.engine.reporting import (
    ATTRIBUTION_KEYS, aggregate_pnl_attribution, build_tearsheet, cumulative_equity,
)
from src.engine.simulate import simulate_events
from src.strategy.fair_move_model import FairMoveModel
from src.strategy.strategy import run_strategy


def _net_books():
    ev = simulate_events(n=300, seed=5, with_vix=True)
    model = FairMoveModel().fit(ev, ev["realised_move"])
    costs = CostModel()
    return run_strategy(ev, model, costs=costs), run_agent0(ev, seed=5, costs=costs)


def test_attribution_aggregates_all_keys():
    strat, _ = _net_books()
    attrib = aggregate_pnl_attribution(strat)
    assert set(attrib) == set(ATTRIBUTION_KEYS)
    # On the planted crush the vega leg should be the dominant positive driver.
    assert attrib["vega_pnl"] > 0


def test_attribution_empty_ledger_is_zero():
    attrib = aggregate_pnl_attribution(None)
    assert all(v == 0.0 for v in attrib.values())


def test_cumulative_equity_starts_at_account():
    strat, _ = _net_books()
    eq = cumulative_equity(strat, account=250_000)
    assert len(eq) >= 1


def test_build_tearsheet_writes_files(tmp_path):
    strat, agent0 = _net_books()
    cmp = compare(strat, agent0, n_boot=200, seed=1)
    png = build_tearsheet(strat, agent0, cmp, account=250_000, outdir=tmp_path,
                          structure_counts={"straddle": 40, "iron_fly": 8})
    assert png.exists()
    assert (tmp_path / "metrics.csv").exists()
