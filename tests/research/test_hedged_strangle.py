"""
test_hedged_strangle.py
Offline checks of ``hedged_hold.hedged_short_strangle``: a hand-calculated hold in each
settlement region under both settlement conventions, equal strikes reproducing
``hedged_short_straddle``, the naked case reconciling to ``engine.pnl.build_trade``, and the
unnetted convention reproducing the closed smile-strike study's strangle.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.stats import norm

from earnings_iv_crush.config import HEDGED, HEDGED_NET, HedgedHoldConfig
from earnings_iv_crush.engine.pnl import build_trade
from earnings_iv_crush.research import hedged_hold as hh

ROOT = Path(__file__).resolve().parents[2]
SMILE = ROOT / "research" / "execution" / "2026-11-02-smile-strike-hedged-hold" / "study.py"


def _path(days: int, sigma: float, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    dt = 1 / 365
    steps = np.exp(-0.5 * sigma**2 * dt + sigma * np.sqrt(dt) * rng.standard_normal(days))
    p = 100.0 * np.concatenate([[1.0], np.cumprod(steps)])
    return {
        "fwd": 100.0,
        "closes": p[:-1],
        "rets": p[1:] / p[:-1] - 1.0,
        "taus": (days - np.arange(days)) / 365,
        "half_spreads": rng.uniform(0.0, 0.002, days),
        "settle_close": float(p[-1]),
    }


def _strangle(kw: dict[str, Any], kc: float, kp: float, sc: float, sp: float, **extra: Any):
    n = len(kw["closes"])
    return hh.hedged_short_strangle(
        sale_price=3.1,
        sale_mid=3.3,
        call_strike=kc,
        put_strike=kp,
        call_sigmas=np.full(n, sc),
        put_sigmas=np.full(n, sp),
        **kw,
        **extra,
    )


# ── hand calculation ─────────────────────────────────────────────────────────

_KC, _KP, _S0, _TAU, _SC, _SP, _HS = 104.0, 96.0, 100.0, 3 / 365, 0.50, 0.60, 0.002


def _d1(k: float, sig: float) -> float:
    sd = sig * np.sqrt(_TAU)
    return (np.log(_S0 / k) + 0.5 * sd * sd) / sd


@pytest.mark.parametrize("cfg", [HEDGED, HEDGED_NET])
@pytest.mark.parametrize("settle", [90.0, 96.0, 100.0, 104.0, 110.0])
def test_one_close_matches_hand_calculation(cfg: HedgedHoldConfig, settle: float) -> None:
    h = float(norm.cdf(_d1(_KC, _SC)) + norm.cdf(_d1(_KP, _SP)) - 1.0)
    call_itm, put_itm = float(settle > _KC), float(settle < _KP)
    settlement = max(settle - _KC, 0.0) + max(_KP - settle, 0.0)
    if cfg.net_assignment:
        close_leg, disposal = abs(h - call_itm + put_itm) * settle * _HS, 0.0
    else:
        close_leg = abs(h) * settle * _HS
        disposal = cfg.disposal_bps / 1e4 * settle if settlement > 0 else 0.0
    cost = abs(h) * _S0 * _HS + close_leg
    fees = 2 * cfg.fee_per_contract_leg / 100
    hedge_pnl = h * (settle - _S0)
    want = 3.1 - settlement + hedge_pnl - cost - fees - disposal
    got = hh.hedged_short_strangle(
        sale_price=3.1,
        sale_mid=3.3,
        call_strike=_KC,
        put_strike=_KP,
        fwd=_S0,
        closes=np.array([_S0]),
        rets=np.array([settle / _S0 - 1.0]),
        taus=np.array([_TAU]),
        call_sigmas=np.array([_SC]),
        put_sigmas=np.array([_SP]),
        half_spreads=np.array([_HS]),
        settle_close=settle,
        cfg=cfg,
    )
    assert got.net_pnl == pytest.approx(want, abs=1e-12)
    assert got.settlement == pytest.approx(settlement, abs=1e-12)
    assert got.equity_cost == pytest.approx(cost, abs=1e-12)
    assert got.disposal == pytest.approx(disposal, abs=1e-15)
    assert got.gross_pnl_mid == pytest.approx(3.3 - settlement + hedge_pnl, abs=1e-12)
    assert got.margin == pytest.approx(0.2 * _S0 + 3.1 + 0.5 * abs(h) * _S0, abs=1e-12)


@pytest.mark.parametrize("days", [1, 4, 15])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_netting_changes_only_the_settlement_close(days: int, seed: int) -> None:
    kw = _path(days, 0.5, seed)
    old = _strangle(kw, 103.0, 97.0, 0.5, 0.55, cfg=HEDGED)
    new = _strangle(kw, 103.0, 97.0, 0.5, 0.55, cfg=HEDGED_NET)
    s, hs = kw["settle_close"], max(kw["half_spreads"][-1], 1e-4)
    # the hedge held into the settlement close, restated by hand
    taus, closes = kw["taus"], kw["closes"]
    sd_c, sd_p = 0.5 * np.sqrt(taus[-1]), 0.55 * np.sqrt(taus[-1])
    hl = float(
        norm.cdf((np.log(closes[-1] / 103.0) + 0.5 * sd_c**2) / sd_c)
        + norm.cdf((np.log(closes[-1] / 97.0) + 0.5 * sd_p**2) / sd_p)
        - 1.0
    )
    resid = hl - float(s > 103.0) + float(s < 97.0)
    disposal = HEDGED.disposal_bps / 1e4 * s if old.settlement > 0 else 0.0
    want = hs * s * (abs(hl) - abs(resid)) + disposal
    assert new.net_pnl - old.net_pnl == pytest.approx(want, abs=1e-12)
    assert new.hedge_pnl == old.hedge_pnl and new.settlement == old.settlement


# ── reductions to the straddle and to build_trade ────────────────────────────


@pytest.mark.parametrize("cfg", [HEDGED, HEDGED_NET])
@pytest.mark.parametrize("hedge", [True, False])
@pytest.mark.parametrize("days", [1, 3, 12, 30])
@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("k", [95.0, 100.0, 104.0])
def test_equal_strikes_reproduce_the_straddle(
    cfg: HedgedHoldConfig, hedge: bool, days: int, seed: int, k: float
) -> None:
    kw = _path(days, 0.45, seed)
    n = len(kw["closes"])
    ref = hh.hedged_short_straddle(
        sale_price=3.1,
        sale_mid=3.3,
        strike=k,
        sigmas=np.full(n, 0.45),
        hedge=hedge,
        cfg=cfg,
        **kw,
    )
    got = _strangle(kw, k, k, 0.45, 0.45, hedge=hedge, cfg=cfg)
    for f in ("net_pnl", "gross_pnl_mid", "margin", "hedge_pnl", "equity_cost", "settlement"):
        assert getattr(got, f) == pytest.approx(getattr(ref, f), abs=1e-12), f
    assert got.disposal == ref.disposal and got.fees == ref.fees


def test_naked_equal_strikes_reconcile_to_build_trade() -> None:
    kw = _path(30, 0.3, 3)
    kw["half_spreads"] = np.zeros(30)
    sale = hh.straddle_value(100.0, 100.0, 30 / 365, 0.3)
    cost_free = replace(HEDGED, disposal_bps=0.0, equity_cost_floor_bps=0.0)
    n = len(kw["closes"])
    res = hh.hedged_short_strangle(
        sale_price=sale,
        sale_mid=sale,
        call_strike=100.0,
        put_strike=100.0,
        call_sigmas=np.full(n, 0.3),
        put_sigmas=np.full(n, 0.3),
        hedge=False,
        cfg=replace(cost_free, fee_per_contract_leg=1.30),
        **kw,
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


@pytest.mark.parametrize("cfg", [HEDGED, HEDGED_NET])
@pytest.mark.parametrize("settle", [80.0, 100.0, 120.0])
def test_naked_distinct_strikes_settle_at_intrinsic(cfg: HedgedHoldConfig, settle: float) -> None:
    kw = _path(5, 0.4, 7)
    kw["settle_close"] = settle
    res = _strangle(kw, 105.0, 95.0, 0.4, 0.4, hedge=False, cfg=cfg)
    intrinsic = max(settle - 105.0, 0.0) + max(95.0 - settle, 0.0)
    disposal = cfg.disposal_bps / 1e4 * settle if intrinsic > 0 else 0.0
    want = 3.1 - intrinsic - 2 * cfg.fee_per_contract_leg / 100 - disposal
    assert res.net_pnl == pytest.approx(want, abs=1e-12)
    assert res.hedge_pnl == 0.0 and res.equity_cost == 0.0


# ── the closed smile-strike study ────────────────────────────────────────────


@pytest.fixture(scope="module")
def sm() -> Any:
    spec = importlib.util.spec_from_file_location("smile_strike_for_strangle", SMILE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("days", [1, 3, 12])
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
@pytest.mark.parametrize("strikes", [(103.0, 97.0), (110.0, 92.0), (100.0, 100.0)])
def test_unnetted_reproduces_the_closed_study(
    sm: Any, days: int, seed: int, strikes: tuple[float, float]
) -> None:
    kw = _path(days, 0.5, seed)
    kc, kp = strikes
    ref = sm.hedged_short_strangle(
        sale=3.1,
        kc=kc,
        kp=kp,
        closes=kw["closes"],
        rets=kw["rets"],
        taus=kw["taus"],
        sig_c=0.5,
        sig_p=0.6,
        half_spreads=kw["half_spreads"],
        settle=kw["settle_close"],
    )
    got = _strangle(kw, kc, kp, 0.5, 0.6, cfg=HEDGED)
    assert got.net_pnl == pytest.approx(ref["net"], abs=1e-13)
    assert got.settlement == ref["settlement"]
    assert got.hedge_pnl == ref["hedge_pnl"]
    assert got.equity_cost == ref["eq_cost"]
    assert got.disposal == ref["disposal"]
    assert got.max_hedge_notional == ref["peak"]


# ── override and validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("cfg", [HEDGED, HEDGED_NET])
def test_override_with_the_internal_delta_is_identical(cfg: HedgedHoldConfig) -> None:
    kw = _path(8, 0.5, 4)
    n = len(kw["closes"])
    ratios = np.array(
        [
            hh._leg_delta(kw["closes"][i], 103.0, kw["taus"][i], 0.5, True, False)
            + hh._leg_delta(kw["closes"][i], 97.0, kw["taus"][i], 0.55, False, True)
            for i in range(n)
        ]
    )
    a = _strangle(kw, 103.0, 97.0, 0.5, 0.55, cfg=cfg)
    b = _strangle(kw, 103.0, 97.0, 0.5, 0.55, cfg=cfg, hedge_ratios=ratios)
    assert a == b


def test_override_is_used_as_given() -> None:
    kw = _path(4, 0.5, 6)
    r = _strangle(kw, 103.0, 97.0, 0.5, 0.55, hedge_ratios=np.zeros(4), cfg=HEDGED_NET)
    assert r.hedge_pnl == 0.0
    s = kw["settle_close"]
    resid = abs(-float(s > 103.0) + float(s < 97.0))
    assert r.equity_cost == pytest.approx(resid * s * max(kw["half_spreads"][-1], 1e-4))


def test_rejects_ragged_paths_and_inverted_strikes() -> None:
    kw = _path(4, 0.5, 6)
    with pytest.raises(ValueError, match="same length"):
        hh.hedged_short_strangle(
            sale_price=3.1,
            sale_mid=3.3,
            call_strike=103.0,
            put_strike=97.0,
            call_sigmas=np.full(3, 0.5),
            put_sigmas=np.full(4, 0.5),
            **kw,
        )
    with pytest.raises(ValueError, match="hedge_ratios"):
        _strangle(kw, 103.0, 97.0, 0.5, 0.5, hedge_ratios=np.zeros(3))
    with pytest.raises(ValueError, match="above call strike"):
        _strangle(kw, 97.0, 103.0, 0.5, 0.5)
