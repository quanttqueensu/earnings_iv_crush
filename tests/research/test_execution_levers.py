"""
test_execution_levers.py
Offline checks of the execution-lever inputs added for the 2026-11-14 slate-tests lane L2: the
new config leaves every existing default alone, and the cost identities the levers rely on hold
on synthetic hedged paths.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from earnings_iv_crush.config import (
    EXECUTION_LEVERS,
    HEDGED,
    HEDGED_NET,
    ExecutionLeversConfig,
    HedgedHoldConfig,
)
from earnings_iv_crush.research import hedged_hold as hh

# ── config ───────────────────────────────────────────────────────────────────


def test_existing_hedged_defaults_unchanged() -> None:
    assert HEDGED == HedgedHoldConfig()
    assert HEDGED.fee_per_contract_leg == 0.65
    assert HEDGED.equity_cost_floor_bps == 1.0
    assert HEDGED.disposal_bps == 5.0
    assert HEDGED_NET == HedgedHoldConfig(net_assignment=True)


def test_execution_levers_frozen_and_ordered() -> None:
    assert EXECUTION_LEVERS == ExecutionLeversConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        EXECUTION_LEVERS.moc_cutoff_minutes = 5.0  # type: ignore[misc]
    grid = EXECUTION_LEVERS.auction_cost_grid_bps
    assert list(grid) == sorted(grid) and grid[0] == 0.0
    assert list(EXECUTION_LEVERS.depth_sizes) == sorted(EXECUTION_LEVERS.depth_sizes)
    assert EXECUTION_LEVERS.stock_tiered_per_share < EXECUTION_LEVERS.stock_fixed_per_share
    assert EXECUTION_LEVERS.expiry_min_gap_days < EXECUTION_LEVERS.expiry_max_gap_days


# ── cost identities on synthetic paths ───────────────────────────────────────


def _path(seed: int, n: int) -> dict:
    rng = np.random.default_rng(seed)
    s0, sig = 100.0, 0.4
    r = rng.normal(0.0, sig / np.sqrt(252), n)
    closes = s0 * np.exp(np.cumsum(np.r_[rng.normal(0, 0.05), r[:-1]]))
    settle = float(closes[-1] * np.exp(r[-1]))
    return {
        "sale_price": 6.0,
        "sale_mid": 6.2,
        "strike": 100.0,
        "fwd": 100.0,
        "closes": closes,
        "rets": np.exp(r) - 1.0,
        "taus": np.linspace(n, 1, n) / 365.0,
        "sigmas": np.full(n, sig),
        "half_spreads": rng.uniform(0.5e-4, 5e-4, n),
        "settle_close": settle,
    }


def _shares(kw: dict) -> np.ndarray:
    h = np.array(
        [
            hh.straddle_delta(s, kw["strike"], t, v)
            for s, t, v in zip(kw["closes"], kw["taus"], kw["sigmas"], strict=True)
        ]
    )
    return h


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
@pytest.mark.parametrize("n", [1, 3, 12])
@pytest.mark.parametrize("a_bps", [0.0, 0.5, 1.0])
def test_constant_auction_cost_is_traded_notional_times_cost(
    seed: int, n: int, a_bps: float
) -> None:
    """With the floor off and a constant half-spread a, equity cost = a x notional traded."""
    kw = _path(seed, n)
    cfg = dataclasses.replace(HEDGED_NET, equity_cost_floor_bps=0.0)
    kw_a = {**kw, "half_spreads": np.full(n, a_bps / 1e4)}
    res = hh.hedged_short_straddle(**kw_a, cfg=cfg)
    h = _shares(kw)
    traded = np.abs(np.diff(np.r_[0.0, h])) * kw["closes"]
    settle = kw["settle_close"]
    sgn = float(np.sign(settle - kw["strike"]))
    notional = traded.sum() + abs(h[-1] - sgn) * settle
    assert res.equity_cost == pytest.approx(a_bps / 1e4 * notional, rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("seed", [0, 5, 9])
def test_first_close_override_moves_only_hedge_and_cost(seed: int) -> None:
    """Shifting the reaction-close hedge changes hedge P&L by the shift times that close's P&L."""
    kw = _path(seed, 6)
    h = _shares(kw)
    base = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, hedge_ratios=h)
    ref = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET)
    assert base.net_pnl == ref.net_pnl
    bump = h.copy()
    bump[0] -= 0.07
    alt = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, hedge_ratios=bump)
    expect = -0.07 * kw["closes"][0] * kw["rets"][0]
    assert alt.hedge_pnl - base.hedge_pnl == pytest.approx(expect, rel=1e-12)
    assert alt.settlement == base.settlement


def test_fee_bound_fields_are_small_and_positive() -> None:
    """The commission cap and the bounded sale fees exist and are fractions, not basis points."""
    xl = EXECUTION_LEVERS
    assert 0.0 < xl.stock_max_commission_frac <= 0.01
    assert 0.0 < xl.sec_fee_rate_bound < 1e-4
    assert 0.0 < xl.finra_taf_per_share < xl.stock_tiered_per_share
    grid = xl.delta_band_grid
    assert list(grid) == sorted(grid) and grid[0] == 0.0


@pytest.mark.parametrize("seed", [0, 4, 7])
@pytest.mark.parametrize("n", [2, 5, 12])
def test_frozen_hedge_after_first_close_charges_two_orders(seed: int, n: int) -> None:
    """A band wider than any drift holds the first-close hedge: cost is first order plus residual."""
    kw = _path(seed, n)
    cfg = dataclasses.replace(HEDGED_NET, equity_cost_floor_bps=0.0)
    h = np.full(n, _shares(kw)[0])
    res = hh.hedged_short_straddle(**kw, cfg=cfg, hedge_ratios=h)
    settle = kw["settle_close"]
    sgn = float(np.sign(settle - kw["strike"]))
    expect = abs(h[0]) * kw["closes"][0] * kw["half_spreads"][0] + abs(h[-1] - sgn) * settle * (
        kw["half_spreads"][-1]
    )
    assert res.equity_cost == pytest.approx(expect, rel=1e-12, abs=1e-15)
    held = h[0] * float(np.sum(kw["closes"] * kw["rets"]))
    assert res.hedge_pnl == pytest.approx(held, rel=1e-10, abs=1e-12)
