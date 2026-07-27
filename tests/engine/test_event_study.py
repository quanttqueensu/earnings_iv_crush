"""Offline tests for engine.event_study: calendar, CAR, calendar-time
portfolio, factor alpha, cost model, and cluster-robust significance
(synthetic fixtures, no network)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine import event_study, stats

# ── trading calendar ───────────────────────────────────────────────────────────


def test_make_trading_calendar_sorted_unique():
    ff = pd.DataFrame({"date": pd.to_datetime(["2020-01-03", "2020-01-02", "2020-01-02"])})
    cal, cal_index = event_study.make_trading_calendar(ff)
    assert list(cal) == sorted(cal)
    assert len(cal) == 2
    assert cal_index[dt.date(2020, 1, 2)] == 0
    assert cal_index[dt.date(2020, 1, 3)] == 1


def test_event_day0_bmo_vs_amc_and_weekend_roll():
    ff = pd.DataFrame({"date": pd.bdate_range("2020-02-01", "2020-02-29")})
    _, cal_index = event_study.make_trading_calendar(ff)
    # Monday 2020-02-10: bmo trades same day, amc/dmh trade the next day.
    assert (
        event_study.event_day0(dt.date(2020, 2, 10), "bmo", cal_index)
        == cal_index[dt.date(2020, 2, 10)]
    )
    assert (
        event_study.event_day0(dt.date(2020, 2, 10), "amc", cal_index)
        == cal_index[dt.date(2020, 2, 11)]
    )
    assert (
        event_study.event_day0(dt.date(2020, 2, 10), "dmh", cal_index)
        == cal_index[dt.date(2020, 2, 11)]
    )
    # Saturday 2020-02-08: both roll forward to Monday 2020-02-10.
    assert (
        event_study.event_day0(dt.date(2020, 2, 8), "bmo", cal_index)
        == cal_index[dt.date(2020, 2, 10)]
    )
    assert (
        event_study.event_day0(dt.date(2020, 2, 8), "amc", cal_index)
        == cal_index[dt.date(2020, 2, 10)]
    )


def test_event_day0_raises_beyond_calendar_coverage():
    ff = pd.DataFrame({"date": pd.bdate_range("2020-02-01", "2020-02-10")})
    _, cal_index = event_study.make_trading_calendar(ff)
    with pytest.raises(ValueError):
        event_study.event_day0(dt.date(2020, 3, 1), "amc", cal_index)


# ── CAR ─────────────────────────────────────────────────────────────────────


def _daily_fixture():
    dates = pd.bdate_range("2020-01-01", "2020-01-20")
    ff = pd.DataFrame({"date": dates})
    cal, cal_index = event_study.make_trading_calendar(ff)
    ordinals = np.arange(len(dates))
    rng = np.random.default_rng(0)
    daily = pd.DataFrame(
        {
            "permno": [111] * len(dates) + [222] * len(dates),
            "ordinal": np.r_[ordinals, ordinals],
            "ret_adj": np.r_[rng.normal(0, 0.01, len(dates)), rng.normal(0, 0.01, len(dates))],
            "mktrf": np.r_[np.full(len(dates), 0.001), np.full(len(dates), 0.001)],
            "rf": np.r_[np.full(len(dates), 0.0001), np.full(len(dates), 0.0001)],
        }
    )
    return daily, cal, cal_index


def test_car_raw_matches_manual_sum():
    daily, cal, cal_index = _daily_fixture()
    events = pd.DataFrame({"permno": [111], "day0": [10]})
    got = event_study.car(daily, events, a=-1, b=1, adjust="raw")
    sub = daily[(daily["permno"] == 111) & daily["ordinal"].between(9, 11)]
    assert got.iloc[0] == pytest.approx(sub["ret_adj"].sum())


def test_car_mkt_adjust_subtracts_market():
    daily, cal, cal_index = _daily_fixture()
    events = pd.DataFrame({"permno": [111], "day0": [10]})
    raw = event_study.car(daily, events, a=0, b=0, adjust="raw")
    mkt = event_study.car(daily, events, a=0, b=0, adjust="mkt")
    row = daily[(daily["permno"] == 111) & (daily["ordinal"] == 10)].iloc[0]
    assert mkt.iloc[0] == pytest.approx(raw.iloc[0] - (row["mktrf"] + row["rf"]))


def test_car_delisting_aware_missing_days_return_nan():
    daily, cal, cal_index = _daily_fixture()
    # permno 222 has no rows past ordinal 5 (simulating an early delisting).
    truncated = daily[~((daily["permno"] == 222) & (daily["ordinal"] > 5))]
    events = pd.DataFrame({"permno": [111, 222], "day0": [10, 10]})
    got = event_study.car(truncated, events, a=-1, b=1, adjust="raw")
    assert np.isfinite(got.iloc[0])
    assert np.isnan(got.iloc[1])  # window [9,11] has no surviving data for 222


def test_car_unknown_adjust_raises():
    daily, cal, cal_index = _daily_fixture()
    events = pd.DataFrame({"permno": [111], "day0": [10]})
    with pytest.raises(ValueError):
        event_study.car(daily, events, 0, 0, adjust="bogus")


# ── calendar-time portfolio ────────────────────────────────────────────────────


def test_calendar_time_portfolio_ew_long_only():
    dates = pd.bdate_range("2020-01-01", "2020-01-10")
    daily = pd.DataFrame(
        {
            "permno": [111] * len(dates) + [222] * len(dates),
            "ordinal": list(range(len(dates))) * 2,
            "date": list(dates) * 2,
            "ret_adj": [0.01] * len(dates) + [0.03] * len(dates),
        }
    )
    positions = pd.DataFrame(
        {
            "permno": [111, 222],
            "entry_ordinal": [2, 4],
            "exit_ordinal": [6, 6],
            "side": [1, 1],
        }
    )
    ret = event_study.calendar_time_portfolio(positions, daily, weight="ew")
    # On day ordinal 3 only 111 is active -> return 0.01.
    assert ret.loc[dates[3]] == pytest.approx(0.01)
    # On day ordinal 5 both are active -> equal-weight average.
    assert ret.loc[dates[5]] == pytest.approx((0.01 + 0.03) / 2)


def test_calendar_time_portfolio_short_leg_flips_sign():
    dates = pd.bdate_range("2020-01-01", "2020-01-05")
    daily = pd.DataFrame(
        {
            "permno": [111] * len(dates),
            "ordinal": list(range(len(dates))),
            "date": list(dates),
            "ret_adj": [0.02] * len(dates),
        }
    )
    positions = pd.DataFrame(
        {"permno": [111], "entry_ordinal": [0], "exit_ordinal": [4], "side": [-1]}
    )
    ret = event_study.calendar_time_portfolio(positions, daily, weight="ew")
    assert np.allclose(ret.to_numpy(), -0.02)


def test_calendar_time_portfolio_long_short_combined():
    dates = pd.bdate_range("2020-01-01", "2020-01-05")
    daily = pd.DataFrame(
        {
            "permno": [111] * len(dates) + [222] * len(dates),
            "ordinal": list(range(len(dates))) * 2,
            "date": list(dates) * 2,
            "ret_adj": [0.02] * len(dates) + [0.05] * len(dates),
        }
    )
    positions = pd.DataFrame(
        {
            "permno": [111, 222],
            "entry_ordinal": [0, 0],
            "exit_ordinal": [4, 4],
            "side": [1, -1],
        }
    )
    ret = event_study.calendar_time_portfolio(positions, daily, weight="ew")
    assert np.allclose(ret.to_numpy(), (0.02 - 0.05) / 2)


def test_calendar_time_portfolio_vw_weights_by_entry_mktcap():
    dates = pd.bdate_range("2020-01-01", "2020-01-05")
    daily = pd.DataFrame(
        {
            "permno": [111] * len(dates) + [222] * len(dates),
            "ordinal": list(range(len(dates))) * 2,
            "date": list(dates) * 2,
            "ret_adj": [0.10] * len(dates) + [0.00] * len(dates),
        }
    )
    positions = pd.DataFrame(
        {
            "permno": [111, 222],
            "entry_ordinal": [0, 0],
            "exit_ordinal": [4, 4],
            "side": [1, 1],
            "entry_mktcap": [9.0, 1.0],  # 111 dominates a value-weighted average
        }
    )
    ret = event_study.calendar_time_portfolio(positions, daily, weight="vw")
    assert np.allclose(ret.to_numpy(), 0.09)  # 0.9*0.10 + 0.1*0.00


def test_calendar_time_portfolio_empty_positions():
    daily = pd.DataFrame(columns=["permno", "ordinal", "date", "ret_adj"])
    positions = pd.DataFrame(columns=["permno", "entry_ordinal", "exit_ordinal", "side"])
    ret = event_study.calendar_time_portfolio(positions, daily)
    assert ret.empty


def test_calendar_time_portfolio_bad_weight_raises():
    with pytest.raises(ValueError):
        event_study.calendar_time_portfolio(pd.DataFrame(), pd.DataFrame(), weight="bogus")


# ── FF4 alpha ──────────────────────────────────────────────────────────────────


def test_ff4_alpha_recovers_known_alpha():
    rng = np.random.default_rng(1)
    n = 500
    dates = pd.bdate_range("2018-01-01", periods=n)
    mktrf = rng.normal(0.0004, 0.01, n)
    smb = rng.normal(0.0, 0.005, n)
    hml = rng.normal(0.0, 0.005, n)
    umd = rng.normal(0.0, 0.005, n)
    rf = np.full(n, 0.00003)
    true_alpha = 0.0005
    beta = 1.2
    noise = rng.normal(0, 0.002, n)
    ret = true_alpha + rf + beta * mktrf + 0.3 * smb - 0.2 * hml + 0.1 * umd + noise
    daily_ret = pd.Series(ret, index=dates)
    ff = pd.DataFrame({"date": dates, "mktrf": mktrf, "smb": smb, "hml": hml, "rf": rf, "umd": umd})

    out = event_study.ff4_alpha(daily_ret, ff, nw_lags=5)
    assert out["alpha_daily"] == pytest.approx(true_alpha, abs=0.0006)
    assert out["alpha_ann"] == pytest.approx(out["alpha_daily"] * 252)
    assert out["betas"]["mktrf"] == pytest.approx(beta, abs=0.2)
    assert out["n_days"] == n
    assert 0.0 <= out["r2"] <= 1.0


def test_ff4_alpha_zero_investment_book_must_not_subtract_rf():
    """A long-short book's return is already an excess return; subtracting rf biases alpha by -mean(rf).

    Regression test for a shipped defect: `ff4_alpha` unconditionally subtracted rf, which on
    the PEAD decile long-short deducted the risk-free rate from a portfolio that never tied up
    capital. It suppressed the holdout alpha by exactly mean(rf) and flipped the fit-period
    alpha's sign.
    """
    rng = np.random.default_rng(7)
    n = 800
    dates = pd.bdate_range("2015-01-01", periods=n)
    mktrf = rng.normal(0.0004, 0.01, n)
    smb = rng.normal(0.0, 0.005, n)
    hml = rng.normal(0.0, 0.005, n)
    umd = rng.normal(0.0, 0.005, n)
    rf = np.full(n, 0.00008)  # ~2%/yr, the scale that mattered in the real sample
    true_alpha = 0.00012
    # Zero-investment spread: NO rf term. The long leg's rf is funded by the short leg's proceeds.
    ls_ret = true_alpha + 0.05 * mktrf + 0.1 * umd + rng.normal(0, 0.002, n)
    ff = pd.DataFrame({"date": dates, "mktrf": mktrf, "smb": smb, "hml": hml, "rf": rf, "umd": umd})
    series = pd.Series(ls_ret, index=dates)

    correct = event_study.ff4_alpha(series, ff, subtract_rf=False)
    buggy = event_study.ff4_alpha(series, ff, subtract_rf=True)

    assert correct["alpha_daily"] == pytest.approx(true_alpha, abs=0.00008)
    assert correct["subtract_rf"] is False
    # The buggy basis is the correct one shifted down by exactly the mean risk-free rate.
    assert buggy["alpha_daily"] == pytest.approx(correct["alpha_daily"] - rf.mean(), abs=1e-9)
    assert buggy["t_alpha"] < correct["t_alpha"]


def test_calendar_time_portfolio_cost_must_be_signed_before_aggregation():
    """`calendar_time_portfolio` applies `side`, so a cost written into `ret_adj` must be pre-signed.

    Regression test for a shipped defect: the PEAD net book subtracted a bare `cost_frac` from
    each leg's underlying return, and the downstream `side` multiply turned it into a REBATE on
    every short leg (`-1 * (ret - cost) = -ret + cost`). Costs then cancelled across a balanced
    long-short and the "net" series was silently a gross one. The correct charge is
    `side * cost_frac` against the underlying return, giving `side * ret - cost` on both legs.
    """
    cost = 0.002
    daily = pd.DataFrame(
        {
            "permno": [1, 1, 2, 2],
            "ordinal": [10, 11, 10, 11],
            "date": pd.to_datetime(["2020-01-02", "2020-01-03"] * 2),
            "ret_adj": [0.01, 0.005, 0.01, 0.005],
        }
    )
    positions = pd.DataFrame(
        {"permno": [1, 2], "entry_ordinal": [10, 10], "exit_ordinal": [11, 11], "side": [1, -1]}
    )
    gross = event_study.calendar_time_portfolio(positions, daily, weight="ew")
    # A balanced long/short on the same return series is flat gross.
    assert gross.to_numpy() == pytest.approx([0.0, 0.0])

    signed = daily.copy()
    sides = {1: 1.0, 2: -1.0}
    entry = signed["ordinal"] == 10
    signed.loc[entry, "ret_adj"] -= signed.loc[entry, "permno"].map(sides) * cost
    net = event_study.calendar_time_portfolio(positions, signed, weight="ew")
    # Both legs pay: the book is down the full cost on the entry day, flat thereafter.
    assert net.to_numpy() == pytest.approx([-cost, 0.0])
    assert net.mean() < gross.mean()

    unsigned = daily.copy()
    unsigned.loc[entry, "ret_adj"] -= cost  # the defect
    wrong = event_study.calendar_time_portfolio(positions, unsigned, weight="ew")
    # The short leg is paid the cost, it cancels the long leg's, and the book trades for free.
    assert wrong.to_numpy() == pytest.approx([0.0, 0.0])


def test_ff4_alpha_too_few_days_raises():
    dates = pd.bdate_range("2020-01-01", periods=5)
    daily_ret = pd.Series(0.01, index=dates)
    ff = pd.DataFrame(
        {
            "date": dates,
            "mktrf": 0.001,
            "smb": 0.0,
            "hml": 0.0,
            "rf": 0.0,
            "umd": 0.0,
        }
    )
    with pytest.raises(ValueError):
        event_study.ff4_alpha(daily_ret, ff)


# ── cost model ─────────────────────────────────────────────────────────────────


def test_equity_roundtrip_cost_bps_raw_quote():
    daily = pd.DataFrame(
        {
            "permno": [111],
            "date": pd.to_datetime(["2020-01-02"]),
            "bid": [99.9],
            "ask": [100.1],
        }
    )
    out = event_study.equity_roundtrip_cost_bps(daily)
    expected = 1e4 * (100.1 - 99.9) / 100.0
    assert out.iloc[0] == pytest.approx(expected)


def test_equity_roundtrip_cost_bps_falls_back_to_trailing_median():
    dates = pd.bdate_range("2020-01-01", periods=5)
    # Four clean days at a spread of ~20bps, then a fifth day with a crossed
    # (invalid) quote that must fall back to the trailing median of the prior days.
    daily = pd.DataFrame(
        {
            "permno": [111] * 5,
            "date": dates,
            "bid": [99.9, 99.9, 99.9, 99.9, 100.5],
            "ask": [100.1, 100.1, 100.1, 100.1, 100.0],  # ask <= bid on the last day
        }
    )
    out = event_study.equity_roundtrip_cost_bps(daily)
    assert np.isfinite(out.iloc[4])
    assert out.iloc[4] == pytest.approx(out.iloc[:4].mean(), rel=1e-6)


def test_equity_roundtrip_cost_bps_winsorised_and_nan_without_fallback():
    daily = pd.DataFrame(
        {
            "permno": [111, 222],
            "date": pd.to_datetime(["2020-01-02", "2020-01-02"]),
            "bid": [1.0, np.nan],
            "ask": [1000.0, np.nan],  # absurd spread -> winsorised at the cap
        }
    )
    out = event_study.equity_roundtrip_cost_bps(daily)
    assert out.iloc[0] == pytest.approx(event_study.SPREAD_WINSOR_BPS)
    assert np.isnan(out.iloc[1])  # no data and no fallback history -> NaN


# ── cluster bootstrap ──────────────────────────────────────────────────────────


def test_cluster_bootstrap_ci_resamples_clusters_not_rows():
    # 10 rows of +1 in cluster "A", 1 row of -1 in cluster "B". A naive i.i.d.
    # row bootstrap of these 11 rows would concentrate tightly near
    # (10 - 1) / 11 ~ 0.818 and never touch -1. A cluster bootstrap must be
    # able to draw {B, B} and land on exactly -1.
    values = np.array([1.0] * 10 + [-1.0])
    clusters = np.array(["A"] * 10 + ["B"])
    lo, hi = event_study.cluster_bootstrap_ci(
        values, clusters, stat_fn=lambda x: float(x.mean()), n_boot=2000, seed=0
    )
    assert lo <= -0.9
    assert hi >= 0.9


def test_cluster_bootstrap_ci_empty_returns_nan():
    lo, hi = event_study.cluster_bootstrap_ci(np.array([]), np.array([]), lambda x: 0.0)
    assert np.isnan(lo) and np.isnan(hi)


# ── book scorecard ──────────────────────────────────────────────────────────────


def test_summarise_book_reuses_engine_stats_and_reports_both_sharpe_bases():
    rng = np.random.default_rng(2)
    n = 60
    returns = pd.Series(rng.normal(0.01, 0.05, n))
    # Roughly one trade every ~2 weeks over ~2.3 years -> sparse event cadence.
    dates = pd.date_range("2020-01-01", periods=n, freq="14D")

    out = event_study.summarise_book(returns, dates, label="test-book")

    assert out["label"] == "test-book"
    assert out["n"] == n
    assert out["hit_rate"] == pytest.approx((returns > 0).mean())
    assert out["sharpe_per_trade"] == pytest.approx(stats.sharpe(returns, periods_per_year=1.0))

    ppy = stats.infer_periods_per_year(pd.DatetimeIndex(dates))
    assert out["periods_per_year"] == pytest.approx(ppy)
    assert out["sharpe_annualised"] == pytest.approx(stats.sharpe(returns, periods_per_year=ppy))
    # A sparse ~26/yr event cadence must not be inflated to a daily sqrt(252) basis.
    assert out["periods_per_year"] < 100

    assert out["dsr"] <= out["psr"] + 1e-9
    assert out["sharpe_ci_low"] <= out["sharpe_annualised"] <= out["sharpe_ci_high"]


def test_summarise_book_empty_returns_zero_n():
    out = event_study.summarise_book(
        pd.Series([], dtype=float), pd.Series([], dtype="datetime64[ns]"), "empty"
    )
    assert out == {"label": "empty", "n": 0}
