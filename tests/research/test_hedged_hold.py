"""
test_hedged_hold.py
Offline checks of the hedged hold-to-expiry machinery against independent references.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.config import HEDGED
from earnings_iv_crush.engine.pnl import build_trade
from earnings_iv_crush.research import hedged_hold as hh

NO_COST = replace(HEDGED, fee_per_contract_leg=0.0, disposal_bps=0.0, equity_cost_floor_bps=0.0)


# ── HAR ──────────────────────────────────────────────────────────────────────


def _simulate_har(n: int, coef: tuple[float, float, float, float], seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rv = list(np.full(22, 1e-4))
    for _ in range(n):
        a = np.asarray(rv)
        mean = coef[0] + coef[1] * a[-1] + coef[2] * a[-5:].mean() + coef[3] * a[-22:].mean()
        rv.append(max(mean * rng.gamma(4.0, 0.25), 1e-8))
    return np.asarray(rv)


def test_har_fit_matches_normal_equations() -> None:
    rv = _simulate_har(3000, (2e-5, 0.3, 0.3, 0.2), seed=1)
    coef, n = hh.har_fit(rv)
    # the module tolerates one missing day a week and a fifth of a month (excluded event days)
    s = pd.Series(rv)
    weekly = s.rolling(5, min_periods=4).mean()
    monthly = s.rolling(22, min_periods=17).mean()
    x = np.column_stack([np.ones(len(rv)), s, weekly, monthly])[:-1]
    y = rv[1:]
    ok = np.isfinite(x).all(axis=1)
    ref = np.linalg.solve(x[ok].T @ x[ok], x[ok].T @ y[ok])
    assert n == int(ok.sum())
    np.testing.assert_allclose(coef, ref, rtol=1e-6)


def test_har_recovers_planted_coefficients() -> None:
    planted = np.array([2e-5, 0.3, 0.3, 0.2])
    coef, _ = hh.har_fit(_simulate_har(40000, tuple(planted), seed=2))
    np.testing.assert_allclose(coef[1:], planted[1:], atol=0.05)


def test_har_forecast_converges_to_unconditional_mean() -> None:
    coef = np.array([1e-5, 0.3, 0.3, 0.2])
    rv = np.full(30, 1e-4)
    uncond = coef[0] / (1 - coef[1:].sum())
    avg = hh.har_forecast_sum(rv, coef, 5000) / 5000
    assert avg == pytest.approx(uncond, rel=0.02)


def test_har_needs_minimum_history() -> None:
    r = np.random.default_rng(0).normal(0, 0.01, 300)
    assert np.isnan(hh.har_annual_variance(r, 20))


# ── jump split and chain parsing ─────────────────────────────────────────────


@pytest.mark.parametrize("sd", [0.2, 0.45])
@pytest.mark.parametrize("jump", [0.03, 0.08])
def test_split_recovers_planted_jump(sd: float, jump: float) -> None:
    t1, t2 = 7 / 365, 35 / 365
    iv1 = np.sqrt((sd**2 * t1 + jump**2) / t1)
    iv2 = np.sqrt((sd**2 * t2 + jump**2) / t2)
    s = hh.split_jump_variance(iv1, t1, iv2, t2)
    assert s.valid
    assert s.diffusive_vol == pytest.approx(sd, rel=1e-9)
    assert s.jump_vol == pytest.approx(jump, rel=1e-9)


def test_split_rejects_inverted_expiries() -> None:
    with pytest.raises(ValueError):
        hh.split_jump_variance(0.3, 0.1, 0.3, 0.05)


def _bs_chain(fwd: float, sigma: float, expiry: pd.Timestamp, asof: pd.Timestamp) -> pd.DataFrame:
    t = hh.year_frac(asof, expiry)
    rows = []
    for k in np.arange(80.0, 121.0, 2.5):
        straddle = hh.straddle_value(fwd, k, t, sigma)
        sd = sigma * np.sqrt(t)
        d1 = (np.log(fwd / k) + 0.5 * sd * sd) / sd
        from scipy.stats import norm

        call = fwd * norm.cdf(d1) - k * norm.cdf(d1 - sd)
        put = straddle - call
        for right, px in (("C", call), ("P", put)):
            rows.append(
                {
                    "strike": k,
                    "expiry": expiry,
                    "right": right,
                    "bid_px_00": px * 0.98,
                    "ask_px_00": px * 1.02,
                    "mid": px,
                }
            )
    return pd.DataFrame(rows)


def test_atm_quote_recovers_forward_and_vol() -> None:
    asof, exp = pd.Timestamp("2020-01-02"), pd.Timestamp("2020-02-01")
    q = hh.atm_quote(_bs_chain(100.6, 0.32, exp, asof), exp, asof)
    assert q is not None
    assert q.fwd == pytest.approx(100.6, rel=1e-9)
    assert q.strike == 100.0
    assert q.iv == pytest.approx(0.32, rel=1e-6)
    assert q.bid < q.mid < q.ask


def test_put_skew_is_zero_on_a_flat_smile() -> None:
    asof, exp = pd.Timestamp("2020-01-02"), pd.Timestamp("2020-02-01")
    chain = _bs_chain(100.0, 0.30, exp, asof)
    q = hh.atm_quote(chain, exp, asof)
    assert q is not None
    assert hh.put_skew(chain, q) == pytest.approx(0.0, abs=1e-6)


def test_pick_expiry_respects_window_and_event() -> None:
    asof = pd.Timestamp("2020-01-02")
    exps = [pd.Timestamp(x) for x in ("2020-01-03", "2020-01-17", "2020-01-31", "2020-03-20")]
    assert hh.pick_expiry(exps, asof, (20, 45)) == pd.Timestamp("2020-01-31")
    assert hh.pick_expiry(exps, asof, (1, 45), not_before=pd.Timestamp("2020-01-10")) == (
        pd.Timestamp("2020-01-17")
    )
    assert hh.pick_expiry(exps, asof, (100, 200)) is None


# ── hedged P&L ───────────────────────────────────────────────────────────────


def _gbm_paths(n_paths: int, days: int, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    dt = 1 / 365
    z = rng.standard_normal((n_paths, days))
    steps = np.exp(-0.5 * sigma**2 * dt + sigma * np.sqrt(dt) * z)
    return 100.0 * np.column_stack([np.ones(n_paths), np.cumprod(steps, axis=1)])


def _hold(path: np.ndarray, sigma_imp: float, hedge: bool = True) -> hh.HedgedResult:
    days = path.size - 1
    t0 = days / 365
    premium = hh.straddle_value(100.0, 100.0, t0, sigma_imp)
    closes = path[:-1]
    rets = path[1:] / path[:-1] - 1.0
    taus = (days - np.arange(days)) / 365
    return hh.hedged_short_straddle(
        sale_price=premium,
        sale_mid=premium,
        strike=100.0,
        fwd=100.0,
        closes=closes,
        rets=rets,
        taus=taus,
        sigmas=np.full(days, sigma_imp),
        half_spreads=np.zeros(days),
        settle_close=float(path[-1]),
        hedge=hedge,
        cfg=NO_COST,
    )


@pytest.mark.parametrize("sigma", [0.2, 0.4])
@pytest.mark.parametrize("days", [20, 45])
def test_hedged_pnl_is_fair_when_realised_equals_implied(sigma: float, days: int) -> None:
    paths = _gbm_paths(1500, days, sigma, seed=days)
    premium = hh.straddle_value(100.0, 100.0, days / 365, sigma)
    pnl = np.array([_hold(p, sigma).net_pnl for p in paths])
    assert abs(pnl.mean()) < 0.05 * premium
    naked = np.array([_hold(p, sigma, hedge=False).net_pnl for p in paths])
    assert pnl.std() < 0.6 * naked.std()


def test_hedged_pnl_positive_when_implied_exceeds_realised() -> None:
    paths = _gbm_paths(1000, 30, 0.20, seed=7)
    pnl = np.array([_hold(p, 0.30).net_pnl for p in paths])
    assert pnl.mean() > 0


def test_naked_hold_reconciles_to_build_trade() -> None:
    path = _gbm_paths(1, 30, 0.3, seed=3)[0]
    sigma = 0.3
    res = hh.hedged_short_straddle(
        sale_price=hh.straddle_value(100.0, 100.0, 30 / 365, sigma),
        sale_mid=hh.straddle_value(100.0, 100.0, 30 / 365, sigma),
        strike=100.0,
        fwd=100.0,
        closes=path[:-1],
        rets=path[1:] / path[:-1] - 1.0,
        taus=(30 - np.arange(30)) / 365,
        sigmas=np.full(30, sigma),
        half_spreads=np.zeros(30),
        settle_close=float(path[-1]),
        hedge=False,
        cfg=replace(NO_COST, fee_per_contract_leg=1.30),
    )
    row = build_trade(
        "X",
        "2020-01-02",
        "2020-02-01",
        100.0,
        100.0,
        30 / 365,
        0.0,
        sigma,
        sigma,
        float(path[-1]),
        1,
    )
    assert res.net_pnl * 100 == pytest.approx(row["pnl"], rel=1e-9)
    assert res.margin * 100 == pytest.approx(row["margin"], rel=1e-9)


def test_hedged_rejects_ragged_paths() -> None:
    with pytest.raises(ValueError):
        hh.hedged_short_straddle(
            sale_price=1.0,
            sale_mid=1.0,
            strike=100.0,
            fwd=100.0,
            closes=np.ones(3) * 100,
            rets=np.zeros(2),
            taus=np.ones(3),
            sigmas=np.ones(3),
            half_spreads=np.zeros(3),
            settle_close=100.0,
        )


# ── sorts and intervals ──────────────────────────────────────────────────────


def test_causal_bins_use_only_earlier_dates() -> None:
    dates = pd.to_datetime(["2020-01-01"] * 3 + ["2020-01-02"] * 2)
    vals = np.array([1.0, 2.0, 3.0, 100.0, -100.0])
    out = hh.causal_bins(vals, dates, n_bins=3, min_prior=3)
    assert (out[:3] == -1).all()
    assert out[3] == 2 and out[4] == 0


def test_jump_forecast_weights() -> None:
    r = [0.01] * 7 + [0.05]
    expected = np.sqrt((0.05**2 + np.mean(np.square(r[-4:])) + np.mean(np.square(r))) / 3)
    assert hh.jump_forecast(r) == pytest.approx(expected)
    assert np.isnan(hh.jump_forecast([0.02, 0.03]))


def test_top_minus_bottom_point_and_interval() -> None:
    rng = np.random.default_rng(0)
    v = rng.normal(0, 1, 600)
    top = np.zeros(600, bool)
    bot = np.zeros(600, bool)
    top[:200], bot[400:] = True, True
    v[:200] += 1.0
    keys = pd.date_range("2020-01-01", periods=600, freq="D")
    p, lo, hi = hh.top_minus_bottom_ci(v, top, bot, keys, n_boot=500)
    assert p == pytest.approx(v[:200].mean() - v[400:].mean())
    assert lo < p < hi and lo > 0


# ── GARCH ────────────────────────────────────────────────────────────────────


def _simulate_garch(n: int, p: tuple[float, float, float, float], seed: int):
    rng = np.random.default_rng(seed)
    w, a, b, d = p
    dummy = np.zeros(n)
    dummy[::63] = 1.0
    r, s2 = np.zeros(n), np.zeros(n)
    s2_prev, r_prev = w / (1 - a - b), 0.0
    for t in range(n):
        s2[t] = w + a * r_prev**2 + b * s2_prev + d * dummy[t]
        r[t] = np.sqrt(s2[t]) * rng.standard_normal()
        s2_prev, r_prev = s2[t], r[t]
    return r, dummy, s2


def test_garch_filter_matches_loop() -> None:
    r, dummy, _ = _simulate_garch(500, (1e-6, 0.08, 0.9, 4e-4), seed=0)
    p = np.array([1e-6, 0.08, 0.9, 4e-4])
    init = float(np.var(r))
    got = hh.garch_variance_path(r, dummy, p, init)
    ref, prev = [], init
    for t in range(r.size):
        rlag = init if t == 0 else r[t - 1] ** 2
        prev = p[0] + p[1] * rlag + p[2] * prev + p[3] * dummy[t]
        ref.append(prev)
    np.testing.assert_allclose(got, ref, rtol=1e-10)


def test_garch_fit_recovers_parameters() -> None:
    planted = (2e-6, 0.08, 0.88, 6e-4)
    r, dummy, _ = _simulate_garch(12000, planted, seed=4)
    p = hh.garch_fit(r, dummy)
    assert p[1] == pytest.approx(0.08, abs=0.03)
    assert p[2] == pytest.approx(0.88, abs=0.04)
    assert p[3] == pytest.approx(6e-4, rel=0.35)


def test_garch_forecast_long_horizon_is_unconditional() -> None:
    p = np.array([2e-6, 0.08, 0.88, 0.0])
    r = np.full(50, 0.01)
    long = hh.garch_annual_variance(r, np.zeros(50), p, 20000)
    assert long == pytest.approx(p[0] / (1 - 0.96) * 252, rel=0.02)
