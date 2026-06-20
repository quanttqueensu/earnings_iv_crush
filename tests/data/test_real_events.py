"""Tests for earnings_iv_crush.data.real_events: execution-event assembly from injected data.

Both providers are injected with synthetic builders, so no network is touched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from earnings_iv_crush.data import real_events as re
from earnings_iv_crush.engine.greeks import bs_price


def _chain(asof, spot, sigma=0.4, front_extra_iv=0.0, expiries=("2024-06-14", "2024-07-12")):
    """Fixed-date expiries x strikes around spot, IV-consistent prices.

    Real option expiries are fixed calendar dates, so the same expiries must
    appear in both the entry-day and exit-day chains; the fixture pins them
    rather than offsetting from ``asof`` so the exit IV re-read resolves. The
    first expiry carries the elevated (pre-event) IV.
    """
    asof_ts = pd.Timestamp(asof)
    exps = [pd.Timestamp(e) for e in expiries]
    rows = []
    for i, exp in enumerate(exps):
        extra = front_extra_iv if i == 0 else 0.0
        t = max((exp - asof_ts).days, 1) / 365.0
        for k in np.arange(round(spot) - 10, round(spot) + 11, 5.0):
            for right in ("C", "P"):
                s = sigma + extra
                rows.append(
                    {
                        "expiry": exp,
                        "strike": float(k),
                        "right": right,
                        "bid": bs_price(spot, k, t, 0.0, s, right),
                        "ask": bs_price(spot, k, t, 0.0, s, right),
                        "iv": s,
                        "open_interest": 100,
                    }
                )
    return pd.DataFrame(rows)


def _prices(ticker, start, end, level=100.0):
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({"date": dates, "close": [level] * len(dates)})


def test_assembles_execution_columns_offline():
    # AMC (default): enter at the announce-date close, exit the next close.
    cal = pd.DataFrame({"ticker": ["AAA"], "announce_date": ["2024-06-10"]})

    def fetch_chain(t, d):
        # Front IV elevated up to and including the (AMC) entry day, normal after.
        pre = pd.Timestamp(d) <= pd.Timestamp("2024-06-10")
        return _chain(d, 100.0, sigma=0.4, front_extra_iv=0.5 if pre else 0.0)

    df = re.build_execution_events(
        cal, fetch_chain=fetch_chain, fetch_prices=lambda t, s, e: _prices(t, s, e, 100.0)
    )

    assert list(df.columns) == re.EVENT_COLUMNS
    assert len(df) == 1
    row = df.iloc[0]
    # Entry front IV (0.9) richer than exit IV (0.4) -> the crush is captured.
    assert row["iv_entry"] > row["iv_exit"]
    assert row["strike"] == 100.0
    assert row["t_entry"] > row["t_exit"]  # less time left at exit
    assert row["t_exit"] > 0  # the executed expiry outlives the exit (crush marks)
    assert row["realised_move"] == 0.0  # flat synthetic prices
    assert row["iv_term_spread"] > 0  # front richer than back


def test_amc_and_bmo_set_entry_and_exit_dates():
    # AMC reports after the announce-date close: entry = D, exit = D+1.
    entry, exit_ = re.entry_exit_dates("2024-06-10", "amc")
    assert entry == pd.Timestamp("2024-06-10")
    assert exit_ == pd.Timestamp("2024-06-11")
    # BMO reports before the announce-date open: entry = D-1, exit = D.
    entry, exit_ = re.entry_exit_dates("2024-06-10", "bmo")
    assert entry == pd.Timestamp("2024-06-07")  # prior business day (Fri)
    assert exit_ == pd.Timestamp("2024-06-10")


def test_bmo_session_flag_shifts_window():
    cal = pd.DataFrame({"ticker": ["AAA"], "announce_date": ["2024-06-10"], "session": ["bmo"]})

    def fetch_chain(t, d):
        pre = pd.Timestamp(d) < pd.Timestamp("2024-06-10")  # crush at the 06-10 open
        return _chain(d, 100.0, sigma=0.4, front_extra_iv=0.5 if pre else 0.0)

    df = re.build_execution_events(
        cal, fetch_chain=fetch_chain, fetch_prices=lambda t, s, e: _prices(t, s, e, 100.0)
    )
    row = df.iloc[0]
    assert row["entry_date"] == "2024-06-07"
    assert row["exit_date"] == "2024-06-10"
    assert row["iv_entry"] > row["iv_exit"]
    assert row["t_exit"] > 0


def test_same_session_weekly_rolls_to_next_expiry():
    # An expiry that lapses the day after entry cannot leave >= min_dte days at
    # exit, so the assembler must roll to the next surviving expiry.
    cal = pd.DataFrame({"ticker": ["AAA"], "announce_date": ["2024-06-10"]})  # AMC -> exit 06-11
    expiries = ("2024-06-11", "2024-06-21")  # 06-11 expires AT exit; 06-21 survives

    def fetch_chain(t, d):
        return _chain(d, 100.0, sigma=0.4, front_extra_iv=0.3, expiries=expiries)

    df = re.build_execution_events(
        cal,
        fetch_chain=fetch_chain,
        fetch_prices=lambda t, s, e: _prices(t, s, e, 100.0),
        min_exit_dte_days=2,
    )
    row = df.iloc[0]
    # Executed expiry rolled to 06-21, so >= 2 trading days remain at the 06-11 exit.
    assert row["t_exit"] > 0
    # t_exit corresponds to 06-21 minus 06-11, not the lapsed 06-11 weekly.
    assert row["t_exit"] == (pd.Timestamp("2024-06-21") - pd.Timestamp("2024-06-11")).days / 365.0


def test_thin_or_missing_chain_is_skipped():
    cal = pd.DataFrame({"ticker": ["AAA", "BBB"], "announce_date": ["2024-06-10", "2024-06-11"]})

    def fetch_chain(t, d):
        return _chain(d, 100.0) if t == "AAA" else pd.DataFrame()

    df = re.build_execution_events(
        cal, fetch_chain=fetch_chain, fetch_prices=lambda t, s, e: _prices(t, s, e)
    )
    assert set(df["ticker"]) == {"AAA"}


def test_empty_calendar_returns_typed_frame():
    df = re.build_execution_events(
        pd.DataFrame(columns=["ticker", "announce_date"]),
        fetch_chain=lambda *a: pd.DataFrame(),
        fetch_prices=lambda *a: pd.DataFrame(),
    )
    assert list(df.columns) == re.EVENT_COLUMNS
    assert df.empty
