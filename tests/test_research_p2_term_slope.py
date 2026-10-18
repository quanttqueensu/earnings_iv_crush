"""
test_research_p2_term_slope.py
The P2 scorer on synthetic months: legs, arms, sort, null, and the straddle picked.

Offline. Each statistic is checked against a direct computation written out in the test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.off_earnings import research_p2_term_slope as p2


def _book(n_months: int = 6, names: int = 20, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_months):
        f = pd.Timestamp("2022-01-31") + pd.offsets.MonthEnd(m)
        for i in range(names):
            mid = rng.uniform(4, 8)
            half = rng.uniform(0.05, 0.3)
            rows.append(
                {
                    "ticker": f"N{i}",
                    "formation": f,
                    "month": f,
                    "slope": rng.normal(0, 0.05),
                    "mid": mid,
                    "bid": mid - half,
                    "ask": mid + half,
                    "payoff": max(rng.normal(mid, 3), 0.0),
                }
            )
    df = pd.DataFrame(rows)
    df["q"] = p2.assign_quintiles(df)
    return df


def test_quintiles_split_each_month_evenly() -> None:
    df = _book(names=20)
    counts = df.groupby(["formation", "q"]).size()
    assert (counts == 4).all()


def test_thin_month_is_skipped_not_sorted() -> None:
    df = _book(names=p2.MIN_NAMES - 1)
    assert df["q"].isna().all()


@pytest.mark.parametrize("arm", ["mid", "touch"])
def test_long_short_matches_direct_computation(arm: str) -> None:
    df = _book()
    buy = df["mid"] if arm == "mid" else df["ask"]
    sell = df["mid"] if arm == "mid" else df["bid"]
    top, bot = df["q"] == 4, df["q"] == 0
    expected = ((df["payoff"] - buy) / buy)[top].mean() + ((sell - df["payoff"]) / sell)[bot].mean()
    rl, rs = p2.leg_returns(df, arm)
    assert p2.long_short(df["q"].to_numpy(), rl, rs) == pytest.approx(expected)


def test_touch_arm_is_never_better_than_mid() -> None:
    df = _book()
    ml, ms = p2.leg_returns(df, "mid")
    tl, ts = p2.leg_returns(df, "touch")
    assert (tl <= ml + 1e-12).all() and (ts <= ms + 1e-12).all()


def test_clustered_interval_brackets_the_estimate() -> None:
    df = _book(n_months=12)
    est, lo, hi = p2.ls_ci(df, "touch")
    assert lo <= est <= hi


def test_matched_null_keeps_leg_sizes_and_is_reproducible() -> None:
    df = _book()
    a, b = p2.matched_null(df), p2.matched_null(df)
    assert np.array_equal(a, b)
    assert len(a) == p2.N_NULL and np.isfinite(a).all()


def test_straddle_quote_takes_the_nearest_fully_quoted_strike() -> None:
    exp = pd.Timestamp("2022-03-18")
    chain = pd.DataFrame(
        [
            # strike 100 is nearest spot but its put has no bid, so 102.5 is chosen
            {"expiry": exp, "strike": 100.0, "right": "C", "bid": 3.0, "ask": 3.2},
            {"expiry": exp, "strike": 100.0, "right": "P", "bid": 0.0, "ask": 3.1},
            {"expiry": exp, "strike": 102.5, "right": "C", "bid": 1.9, "ask": 2.1},
            {"expiry": exp, "strike": 102.5, "right": "P", "bid": 4.0, "ask": 4.4},
            {"expiry": exp, "strike": 95.0, "right": "C", "bid": 6.0, "ask": 6.4},
            {"expiry": exp, "strike": 95.0, "right": "P", "bid": 1.0, "ask": 1.2},
        ]
    )
    q = p2.straddle_quote(chain, exp, 100.4)
    assert q is not None
    assert q["strike"] == 102.5
    assert (q["bid"], q["ask"]) == pytest.approx((5.9, 6.5))


def test_candidates_are_nyse_sessions_latest_first() -> None:
    cands = p2.month_candidates()
    assert len(cands) == 68
    may = cands[pd.Timestamp("2021-05-28")]  # 2021-05-31 was Memorial Day
    assert pd.Timestamp("2021-05-31") not in may
    assert may == sorted(may, reverse=True)
    assert all(d >= pd.Timestamp("2021-05-26") for d in may)


def test_resolve_steps_back_to_the_latest_non_empty_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(p2, "CACHE", tmp_path)
    (tmp_path / "chains").mkdir()
    days = [pd.Timestamp("2021-05-28"), pd.Timestamp("2021-05-27"), pd.Timestamp("2021-05-26")]
    empty = pd.DataFrame(columns=["expiry", "strike", "right", "bid", "ask", "iv"])
    full = pd.DataFrame(
        [{"expiry": "2021-06-18", "strike": 100.0, "right": "C", "bid": 1.0, "ask": 1.1, "iv": 0.2}]
    )
    assert p2._resolve("AAPL", days) == ("unpulled", None)
    empty.to_parquet(p2._chain_path("AAPL", days[0]))
    full.to_parquet(p2._chain_path("AAPL", days[1]))
    assert p2._resolve("AAPL", days) == ("ok", days[1])
    empty.to_parquet(p2._chain_path("MSFT", days[0]))
    empty.to_parquet(p2._chain_path("MSFT", days[1]))
    empty.to_parquet(p2._chain_path("MSFT", days[2]))
    assert p2._resolve("MSFT", days) == ("none", None)


@pytest.mark.parametrize(
    "ticker, day, expected",
    [("META", "2021-06-30", "FB"), ("META", "2022-06-30", "META"), ("AAPL", "2021-06-30", "AAPL")],
)
def test_meta_is_queried_under_its_former_symbol(ticker: str, day: str, expected: str) -> None:
    assert p2.dolt_symbol(ticker, pd.Timestamp(day)) == expected
