"""
test_hedged_hold_corrections.py
The opt-in valuation corrections to ``hedged_short_straddle``: the defaults reproduce the frozen
function bit for bit, and the hedge-ratio override, early assignment and financing match hand
calculations on synthetic paths.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from scipy.stats import norm

from earnings_iv_crush.config import HEDGED, HEDGED_NET, HOLD_CORRECTIONS, HedgedHoldConfig
from earnings_iv_crush.engine.pnl import build_trade
from earnings_iv_crush.research import hedged_hold as hh

# ── the frozen function, restated as the independent reference ───────────────


def _frozen(
    *,
    sale_price: float,
    sale_mid: float,
    strike: float,
    fwd: float,
    closes: np.ndarray,
    rets: np.ndarray,
    taus: np.ndarray,
    sigmas: np.ndarray,
    half_spreads: np.ndarray,
    settle_close: float,
    hedge: bool = True,
    cfg: HedgedHoldConfig = HEDGED,
) -> tuple[float, float, float, float, float, float, float]:
    """The body of ``hedged_short_straddle`` before the corrections existed, line for line."""
    n = len(closes)
    floor = cfg.equity_cost_floor_bps / 1e4
    hs = np.maximum(np.asarray(half_spreads, dtype=float), floor)
    h_prev, hedge_pnl, cost, max_notional = 0.0, 0.0, 0.0, 0.0
    for i in range(n):
        h = hh.straddle_delta(closes[i], strike, taus[i], sigmas[i]) if hedge else 0.0
        cost += abs(h - h_prev) * closes[i] * hs[i]
        hedge_pnl += h * closes[i] * rets[i]
        max_notional = max(max_notional, abs(h) * closes[i])
        h_prev = h
    settlement = abs(settle_close - strike)
    if hedge and cfg.net_assignment:
        residual = h_prev - float(np.sign(settle_close - strike))
        cost += abs(residual) * settle_close * hs[-1]
        disposal = 0.0
    else:
        cost += abs(h_prev) * settle_close * hs[-1]
        disposal = cfg.disposal_bps / 1e4 * settle_close if settlement > 0 else 0.0
    fees = 2.0 * cfg.fee_per_contract_leg / 100.0
    net = sale_price - settlement + hedge_pnl - cost - fees - disposal
    gross_mid = sale_mid - settlement + hedge_pnl
    margin = 0.20 * fwd + sale_price + cfg.hedge_margin_frac * max_notional
    return net, gross_mid, margin, hedge_pnl, cost, settlement, max_notional


def _path(days: int, sigma: float, seed: int, settle_shift: float = 0.0) -> dict:
    rng = np.random.default_rng(seed)
    dt = 1 / 365
    steps = np.exp(-0.5 * sigma**2 * dt + sigma * np.sqrt(dt) * rng.standard_normal(days))
    p = 100.0 * np.concatenate([[1.0], np.cumprod(steps)])
    p[-1] += settle_shift
    return {
        "sale_price": 4.2,
        "sale_mid": 4.4,
        "strike": 100.0,
        "fwd": 100.0,
        "closes": p[:-1],
        "rets": p[1:] / p[:-1] - 1.0,
        "taus": (days - np.arange(days)) / 365,
        "sigmas": np.full(days, sigma),
        "half_spreads": rng.uniform(0.0, 0.002, days),
        "settle_close": float(p[-1]),
    }


# ── defaults are unchanged ───────────────────────────────────────────────────


@pytest.mark.parametrize("cfg", [HEDGED, HEDGED_NET])
@pytest.mark.parametrize("hedge", [True, False])
@pytest.mark.parametrize("days", [1, 3, 12, 30])
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_defaults_reproduce_the_frozen_function_exactly(
    cfg: HedgedHoldConfig, hedge: bool, days: int, seed: int
) -> None:
    kw = _path(days, 0.45, seed)
    new = hh.hedged_short_straddle(**kw, hedge=hedge, cfg=cfg)
    old = _frozen(**kw, hedge=hedge, cfg=cfg)
    got = (
        new.net_pnl,
        new.gross_pnl_mid,
        new.margin,
        new.hedge_pnl,
        new.equity_cost,
        new.settlement,
        new.max_hedge_notional,
    )
    assert got == old  # bit for bit, not approximately
    assert new.financing == 0.0 and new.early_settlement == 0.0
    assert new.call_assigned_at == -1 and new.put_assigned_at == -1


@pytest.mark.parametrize("settle", [100.0])
def test_defaults_at_the_strike_exactly(settle: float) -> None:
    kw = _path(3, 0.3, 5)
    kw["settle_close"] = settle
    for cfg in (HEDGED, HEDGED_NET):
        assert hh.hedged_short_straddle(**kw, cfg=cfg).net_pnl == _frozen(**kw, cfg=cfg)[0]


def test_naked_hold_still_reconciles_to_build_trade() -> None:
    kw = _path(30, 0.3, 3)
    kw.update(sale_price=hh.straddle_value(100.0, 100.0, 30 / 365, 0.3))
    kw.update(sale_mid=kw["sale_price"], half_spreads=np.zeros(30))
    cost_free = replace(HEDGED, disposal_bps=0.0, equity_cost_floor_bps=0.0)
    res = hh.hedged_short_straddle(
        **kw,
        hedge=False,
        cfg=replace(cost_free, fee_per_contract_leg=1.30),
        hedge_ratios=None,
        call_assigned_at=None,
        put_assigned_at=None,
        financing=None,
    )
    row = build_trade(
        "X",
        "2020-01-02",
        "2020-02-01",
        100.0,
        100.0,
        30 / 365,
        0.0,
        0.3,
        0.3,
        kw["settle_close"],
        1,
    )
    assert res.net_pnl * 100 == pytest.approx(row["pnl"], rel=1e-9)
    assert res.margin * 100 == pytest.approx(row["margin"], rel=1e-9)


# ── hedge-ratio override ─────────────────────────────────────────────────────


@pytest.mark.parametrize("cfg", [HEDGED, HEDGED_NET])
@pytest.mark.parametrize("seed", [0, 4])
def test_override_with_the_internal_delta_is_identical(cfg: HedgedHoldConfig, seed: int) -> None:
    kw = _path(10, 0.4, seed)
    deltas = np.array(
        [
            hh.straddle_delta(s, 100.0, t, v)
            for s, t, v in zip(kw["closes"], kw["taus"], kw["sigmas"], strict=True)
        ]
    )
    a = hh.hedged_short_straddle(**kw, cfg=cfg)
    b = hh.hedged_short_straddle(**kw, cfg=cfg, hedge_ratios=deltas)
    assert a == b


def test_override_is_used_as_given() -> None:
    kw = _path(4, 0.4, 9)
    ratios = np.array([0.3, -0.2, 0.1, 0.0])
    r = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, hedge_ratios=ratios)
    assert r.hedge_pnl == pytest.approx(float(np.sum(ratios * kw["closes"] * kw["rets"])))
    with pytest.raises(ValueError):
        hh.hedged_short_straddle(**kw, hedge_ratios=ratios[:3])


# ── early assignment ─────────────────────────────────────────────────────────

_K, _HS = 100.0, 0.001


def _two_closes(s0: float, s1: float, settle: float, div: float = 0.0) -> dict:
    return {
        "sale_price": 5.0,
        "sale_mid": 5.2,
        "strike": _K,
        "fwd": s0,
        "closes": np.array([s0, s1]),
        "rets": np.array([(s1 + 0.0) / s0 - 1.0, (settle + div) / s1 - 1.0]),
        "taus": np.array([2 / 365, 1 / 365]),
        "sigmas": np.array([0.4, 0.4]),
        "half_spreads": np.array([_HS, _HS]),
        "settle_close": settle,
    }


def _nd1(s: float, t: float, v: float) -> float:
    sd = v * np.sqrt(t)
    return float(norm.cdf((np.log(s / _K) + 0.5 * sd * sd) / sd))


@pytest.mark.parametrize("settle", [95.0, 101.0, 106.0])
def test_call_assignment_matches_hand_calculation(settle: float) -> None:
    """Call exercised at close 1 (the cum-dividend close): pay intrinsic, hedge the put alone."""
    kw = _two_closes(103.0, 108.0, settle, div=1.5)
    r = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, call_assigned_at=1)
    h0 = 2 * _nd1(103.0, 2 / 365, 0.4) - 1
    h1 = _nd1(108.0, 1 / 365, 0.4) - 1  # put alone
    hedge_pnl = h0 * 103.0 * kw["rets"][0] + h1 * 108.0 * kw["rets"][1]
    # delivered share nets against the hedge before the rebalance at close 1
    cost = abs(h0) * 103.0 * _HS + abs(h1 - (h0 - 1.0)) * 108.0 * _HS
    p_itm = 1.0 if settle < _K else 0.0
    cost += abs(h1 + p_itm) * settle * _HS
    settlement = (108.0 - _K) + max(_K - settle, 0.0)
    fees = 2 * HEDGED_NET.fee_per_contract_leg / 100
    hand = 5.0 - settlement + hedge_pnl - cost - fees
    assert r.net_pnl == pytest.approx(hand, abs=1e-12)
    assert r.early_settlement == pytest.approx(8.0)
    assert r.call_assigned_at == 1 and r.disposal == 0.0


def test_unnetted_assignment_pays_disposal_on_the_delivered_share() -> None:
    kw = _two_closes(103.0, 108.0, 104.0)
    r = hh.hedged_short_straddle(**kw, cfg=HEDGED, call_assigned_at=1)
    assert r.disposal == pytest.approx(HEDGED.disposal_bps / 1e4 * 108.0)


def test_assignment_out_of_the_money_raises() -> None:
    kw = _two_closes(103.0, 97.0, 99.0)
    with pytest.raises(ValueError):
        hh.hedged_short_straddle(**kw, call_assigned_at=1)
    with pytest.raises(ValueError):
        hh.hedged_short_straddle(**kw, put_assigned_at=0)


@pytest.mark.parametrize(
    ("div", "spot", "expected"),
    [(3.0, 110.0, 0), (0.02, 110.0, 0), (0.02, 102.0, -1), (3.0, 95.0, -1), (0.0, 110.0, -1)],
)
def test_call_exercise_rule(div: float, spot: float, expected: int) -> None:
    """Exercise when the dividend beats the put's value on the ex-dividend open, in the money."""
    got = hh.optimal_call_exercise(
        closes=np.array([spot]),
        strike=100.0,
        dividends=np.array([div]),
        taus_ex=np.array([5 / 365]),
        sigmas=np.array([0.3]),
    )
    assert got == expected


@pytest.mark.parametrize("vol", [0.15, 0.3, 0.6, 0.9])
def test_call_exercise_rule_against_put_value(vol: float) -> None:
    """Exercise exactly when D exceeds the put on the ex-dividend open, computed independently."""
    s, k, t, d = 108.0, 100.0, 10 / 365, 1.0
    sd = vol * np.sqrt(t)
    d1 = (np.log((s - d) / k) + 0.5 * sd * sd) / sd
    put = k * norm.cdf(-(d1 - sd)) - (s - d) * norm.cdf(-d1)
    got = hh.optimal_call_exercise(
        closes=np.array([s]),
        strike=k,
        dividends=np.array([d]),
        taus_ex=np.array([t]),
        sigmas=np.array([vol]),
    )
    assert (got == 0) == (d > put)


def test_rates_make_call_exercise_rarer() -> None:
    args = {
        "closes": np.array([104.0]),
        "strike": 100.0,
        "dividends": np.array([0.5]),
        "taus_ex": np.array([30 / 365]),
        "sigmas": np.array([0.05]),
    }
    assert hh.optimal_call_exercise(**args) == 0
    assert hh.optimal_call_exercise(**args, rates=np.array([0.08])) == -1


def test_put_exercise_rule() -> None:
    args = {
        "closes": np.array([60.0]),
        "strike": 100.0,
        "taus": np.array([20 / 365]),
        "sigmas": np.array([0.3]),
    }
    assert hh.optimal_put_exercise(**args, rates=np.array([0.0])) == -1
    assert hh.optimal_put_exercise(**args, rates=np.array([0.05])) == 0
    near = {**args, "closes": np.array([99.0])}
    assert hh.optimal_put_exercise(**near, rates=np.array([0.05])) == -1


def test_put_assignment_takes_a_share() -> None:
    kw = _two_closes(97.0, 80.0, 79.0)
    r = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, put_assigned_at=1)
    h0 = 2 * _nd1(97.0, 2 / 365, 0.4) - 1
    h1 = _nd1(80.0, 1 / 365, 0.4)  # call alone
    cost = abs(h0) * 97.0 * _HS + abs(h1 - (h0 + 1.0)) * 80.0 * _HS + abs(h1) * 79.0 * _HS
    hedge_pnl = h0 * 97.0 * kw["rets"][0] + h1 * 80.0 * kw["rets"][1]
    hand = 5.0 - 20.0 + hedge_pnl - cost - 2 * HEDGED_NET.fee_per_contract_leg / 100
    assert r.net_pnl == pytest.approx(hand, abs=1e-12)


# ── financing ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("spot", [110.0, 90.0])
def test_financing_matches_hand_calculation(spot: float) -> None:
    kw = _two_closes(spot, spot, spot)
    fc = HOLD_CORRECTIONS
    fin = hh.HoldFinancing(
        rates=np.array([0.05, 0.05]),
        days=np.array([1.0, 3.0]),
        premium_rate=0.05,
        premium_days=6.0,
        cfg=fc,
    )
    base = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET)
    r = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, financing=fin)
    hand = 0.0
    for i, d in enumerate((1.0, 3.0)):
        v = hh.straddle_delta(spot, _K, kw["taus"][i], 0.4) * spot
        rate = (
            0.05 + fc.long_spread_bps / 1e4
            if v > 0
            else 0.05 - (fc.short_rebate_spread_bps + fc.borrow_fee_bps) / 1e4
        )
        hand += -v * rate * d / fc.day_basis
    hand += 5.0 * (0.05 - fc.cash_credit_spread_bps / 1e4) * 6.0 / fc.day_basis
    assert r.financing == pytest.approx(hand, abs=1e-14)
    assert r.net_pnl - base.net_pnl == pytest.approx(hand, abs=1e-12)


def test_early_intrinsic_forgoes_interest_until_settlement() -> None:
    kw = _two_closes(103.0, 108.0, 106.0)
    fc = HOLD_CORRECTIONS
    fin = hh.HoldFinancing(
        rates=np.array([0.04, 0.05]),
        days=np.array([1.0, 3.0]),
        premium_rate=0.04,
        premium_days=5.0,
    )
    with_a = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, financing=fin, call_assigned_at=1)
    no_fin = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, call_assigned_at=1)
    h0 = 2 * _nd1(103.0, 2 / 365, 0.4) - 1
    h1 = _nd1(108.0, 1 / 365, 0.4) - 1
    short_rate = 0.05 - (fc.short_rebate_spread_bps + fc.borrow_fee_bps) / 1e4
    carry = -h0 * 103.0 * (0.04 + fc.long_spread_bps / 1e4) * 1.0 / fc.day_basis
    carry += -h1 * 108.0 * short_rate * 3.0 / fc.day_basis  # put-only hedge is short
    lost = 8.0 * (0.05 - fc.cash_credit_spread_bps / 1e4) * 3.0 / fc.day_basis
    prem = 5.0 * (0.04 - fc.cash_credit_spread_bps / 1e4) * 5.0 / fc.day_basis
    assert with_a.financing == pytest.approx(carry - lost + prem, abs=1e-14)
    assert with_a.net_pnl - no_fin.net_pnl == pytest.approx(with_a.financing, abs=1e-12)


def test_cash_credit_is_floored_at_zero() -> None:
    kw = _two_closes(100.0, 100.0, 100.0)
    fin = hh.HoldFinancing(
        rates=np.zeros(2), days=np.zeros(2), premium_rate=0.001, premium_days=10.0
    )
    assert hh.hedged_short_straddle(**kw, financing=fin).financing == 0.0
