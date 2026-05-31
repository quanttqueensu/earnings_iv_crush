"""Tests for engine.structured_ledger and strategy.run_strategy_structured."""
from __future__ import annotations

from src.baseline.agent0 import run_agent0
from src.engine.backtester import backtest, compare
from src.engine.costs import CostModel
from src.engine.simulate import simulate_events
from src.engine.structured_ledger import STRUCTURED_COLUMNS, build_structured_ledger
from src.strategy.fair_move_model import FairMoveModel
from src.strategy.regime import CALENDAR, IRON_FLY, STRADDLE
from src.strategy.strategy import run_strategy_structured


def test_books_all_three_structures():
    ev = simulate_events(n=3, seed=0)
    led = build_structured_ledger(ev, [STRADDLE, IRON_FLY, CALENDAR])
    assert list(led.columns) == STRUCTURED_COLUMNS
    assert list(led["structure"]) == [STRADDLE, IRON_FLY, CALENDAR]
    assert (led["contracts"] > 0).all()
    assert led["pnl"].notna().all()


def test_iron_fly_capital_at_risk_is_defined_and_bounds_loss():
    ev = simulate_events(n=40, seed=1)
    led = build_structured_ledger(ev, [IRON_FLY] * len(ev), costs=CostModel())
    fly = led[led["structure"] == IRON_FLY]
    assert (fly["capital_at_risk"] > 0).all()
    # Realised loss cannot exceed the defined wing loss plus the charged cost.
    assert (fly["pnl"] >= -(fly["capital_at_risk"] + fly["cost"]) - 1e-6).all()


def test_costs_reduce_total_pnl():
    ev = simulate_events(n=60, seed=2)
    labels = [STRADDLE] * len(ev)
    gross = build_structured_ledger(ev, labels)
    net = build_structured_ledger(ev, labels, costs=CostModel())
    assert net["pnl"].sum() < gross["pnl"].sum()


def test_backtester_scores_structured_ledger():
    ev = simulate_events(n=120, seed=3)
    labels = [IRON_FLY if i % 3 == 0 else STRADDLE for i in range(len(ev))]
    led = build_structured_ledger(ev, labels, costs=CostModel())
    stats = backtest(led)
    assert stats["n_trades"] == len(led)
    assert "sharpe" in stats and "max_drawdown" in stats


def test_run_strategy_structured_forces_iron_fly_in_high_vix():
    # No vix column -> the scalar vix_level drives the regime; 30 > 25 -> iron fly.
    ev = simulate_events(n=300, seed=4)
    model = FairMoveModel().fit(ev, ev["realised_move"])
    led = run_strategy_structured(ev, model, vix_level=30.0, costs=CostModel())
    assert len(led) > 0
    assert set(led["structure"]) == {IRON_FLY}
    assert list(led.columns) == STRUCTURED_COLUMNS


def test_structured_strategy_is_comparable_to_agent0():
    ev = simulate_events(n=300, seed=5, with_vix=True)
    model = FairMoveModel().fit(ev, ev["realised_move"])
    strat = run_strategy_structured(ev, model, costs=CostModel())
    agent0 = run_agent0(ev, seed=5, costs=CostModel())
    c = compare(strat, agent0, n_boot=200, seed=1)
    assert "sharpe_delta" in c
    assert c["sharpe_delta_ci_low"] <= c["sharpe_delta"] <= c["sharpe_delta_ci_high"]
