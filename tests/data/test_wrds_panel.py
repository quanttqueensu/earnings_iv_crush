"""Offline tests for wrds_panel: point-in-time selection, guards, and the full
orchestrator wired to synthetic in-memory fixtures (no network)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.data import wrds_panel
from earnings_iv_crush.engine import event_study

# ── session classification ────────────────────────────────────────────────────


def test_session_from_time_boundaries():
    assert wrds_panel.session_from_time(dt.time(16, 30)) == ("amc", "ibes_time")
    assert wrds_panel.session_from_time(dt.time(16, 0)) == ("amc", "ibes_time")  # at the close
    assert wrds_panel.session_from_time(dt.time(7, 0)) == ("bmo", "ibes_time")
    assert wrds_panel.session_from_time(dt.time(9, 30)) == ("bmo", "ibes_time")  # at the open
    assert wrds_panel.session_from_time(dt.time(12, 30)) == ("dmh", "ibes_time")


def test_session_from_time_unknown_defaults_amc():
    assert wrds_panel.session_from_time(dt.time(0, 0)) == ("amc", "default_unknown")
    assert wrds_panel.session_from_time(None) == ("amc", "default_unknown")


# ── vectorised day0 agrees with the scalar event_study reference ─────────────


def test_day0_vectorized_matches_scalar_event_day0():
    ff = pd.DataFrame({"date": pd.bdate_range("2020-01-01", "2020-03-31")})
    cal, cal_index = event_study.make_trading_calendar(ff)

    cases = [
        (dt.date(2020, 2, 10), "bmo"),  # a Monday trading day, bmo -> itself
        (dt.date(2020, 2, 10), "amc"),  # amc -> next trading day
        (dt.date(2020, 2, 8), "bmo"),  # a Saturday, bmo -> next Monday
        (dt.date(2020, 2, 8), "amc"),  # a Saturday, amc -> same next Monday
        (dt.date(2020, 2, 12), "dmh"),
    ]
    anndats = pd.Series([d for d, _ in cases])
    sessions = pd.Series([s for _, s in cases])
    vec = wrds_panel._day0_vectorized(anndats, sessions, cal)

    for i, (d, s) in enumerate(cases):
        assert vec[i] == event_study.event_day0(d, s, cal_index)


# ── point-in-time consensus selection: the denormalised-actual trap ──────────


def test_pit_select_consensus_takes_freshest_pre_announcement_row():
    # AAPL-style trap: statsum carries `actual`/`anndats_act` on every row for
    # the fiscal period, including a snapshot a year before the announcement.
    # The PIT rule must select the row with the max statpers strictly before
    # anndats_act, and take every field (including actual) from that one row.
    raw = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "AAA"],
            "statpers": pd.to_datetime(["2019-11-01", "2020-01-15", "2020-02-12"]),
            "fpedats": pd.to_datetime(["2019-12-31"] * 3),
            "numest": [5, 6, 7],
            "numup": [1, 2, 0],
            "numdown": [0, 1, 0],
            "medest": [1.00, 1.05, 1.10],
            "meanest": [1.00, 1.05, 1.10],
            "stdev": [0.05, 0.04, 0.03],
            "actual": [1.10, 1.10, 1.10],  # denormalised: known on every row
            "anndats_act": pd.to_datetime(["2020-02-10"] * 3),
        }
    )
    out = wrds_panel._pit_select_consensus(raw)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["statpers"] == pd.Timestamp("2020-01-15")  # max statpers < anndats_act
    assert row["meanest"] == pytest.approx(1.05)
    assert row["numest"] == 6
    assert row["numup"] == 2
    assert row["numdown"] == 1
    assert (out["statpers"] < out["anndats_act"]).all()


def test_pit_select_consensus_drops_thin_or_zero_dispersion_coverage():
    raw = pd.DataFrame(
        {
            "ticker": ["BBB", "CCC"],
            "statpers": pd.to_datetime(["2020-01-01", "2020-01-01"]),
            "fpedats": pd.to_datetime(["2019-12-31", "2019-12-31"]),
            "numest": [2, 5],  # BBB fails numest >= 3
            "numup": [0, 1],
            "numdown": [0, 0],
            "medest": [1.0, 1.0],
            "meanest": [1.0, 1.0],
            "stdev": [0.05, 0.0],  # CCC fails stdev > 0
            "actual": [1.1, 1.1],
            "anndats_act": pd.to_datetime(["2020-02-10", "2020-02-10"]),
        }
    )
    out = wrds_panel._pit_select_consensus(raw)
    assert out.empty


def test_pit_select_consensus_excludes_post_announcement_rows():
    # If every row's statpers is at or after anndats_act, nothing is PIT.
    raw = pd.DataFrame(
        {
            "ticker": ["DDD"],
            "statpers": pd.to_datetime(["2020-02-10"]),
            "fpedats": pd.to_datetime(["2019-12-31"]),
            "numest": [5],
            "numup": [1],
            "numdown": [0],
            "medest": [1.0],
            "meanest": [1.0],
            "stdev": [0.05],
            "actual": [1.1],
            "anndats_act": pd.to_datetime(["2020-02-10"]),  # equal, not strictly before
        }
    )
    assert wrds_panel._pit_select_consensus(raw).empty


# ── link / universe joins ─────────────────────────────────────────────────────


def test_link_to_permno_respects_validity_window():
    events = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "fpedats": pd.to_datetime(["2019-12-31", "2019-12-31"]),
            "statpers": pd.to_datetime(["2020-01-15", "2020-01-15"]),
            "anndats_act": pd.to_datetime(["2020-02-10", "2020-02-10"]),
        }
    ).drop_duplicates()
    link = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "permno": [111, 999],
            "sdate": pd.to_datetime(["2015-01-01", "2021-01-01"]),
            "edate": pd.to_datetime(["2020-12-31", "2025-12-31"]),
            "score": [1, 1],
        }
    )
    out = wrds_panel._link_to_permno(events, link)
    assert len(out) == 1
    assert out.iloc[0]["permno"] == 111  # the window covering anndats_act, not the later one


def test_attach_universe_uses_asof_record_not_latest():
    events = pd.DataFrame({"permno": [111], "anndats_act": pd.to_datetime(["2018-06-01"])})
    universe = pd.DataFrame(
        {
            "permno": [111, 111],
            "namedt": pd.to_datetime(["2010-01-01", "2019-01-01"]),
            "nameendt": pd.to_datetime(["2018-12-31", "2030-12-31"]),
            "shrcd": [11, 11],
            "exchcd": [1, 1],
            "siccd": [3674, 3674],
            "ticker": ["AAA", "AAA"],
        }
    )
    out = wrds_panel._attach_universe(events, universe)
    assert len(out) == 1
    # 2018-06-01 falls in the *first* name record's window, not the most recent one.
    assert out.iloc[0]["namedt"] == pd.Timestamp("2010-01-01")


def test_attach_universe_drops_event_outside_any_name_window():
    events = pd.DataFrame({"permno": [111], "anndats_act": pd.to_datetime(["2005-01-01"])})
    universe = pd.DataFrame(
        {
            "permno": [111],
            "namedt": pd.to_datetime(["2010-01-01"]),
            "nameendt": pd.to_datetime(["2020-12-31"]),
            "shrcd": [11],
            "exchcd": [1],
            "siccd": [3674],
            "ticker": ["AAA"],
        }
    )
    assert wrds_panel._attach_universe(events, universe).empty


# ── winsorization ──────────────────────────────────────────────────────────────


def test_winsorize_by_quarter_clips_within_group_only():
    # A large enough Q1 sample that the 1%/99% clip actually bites on its
    # single outlier, and a Q2 sample far from Q1's scale so cross-group
    # contamination would be obvious if the grouping were broken.
    q1_body = list(np.linspace(1.0, 3.0, 19))
    q1 = q1_body + [100.0]  # 20 points, one extreme outlier
    q2 = [-5.0, -4.5, -4.0, -3.5, 6.0]
    values = pd.Series(q1 + q2)
    quarter = pd.Series(["Q1"] * len(q1) + ["Q2"] * len(q2))

    out = wrds_panel._winsorize_by_quarter(values, quarter, lower=0.01, upper=0.99)

    q1_lo, q1_hi = pd.Series(q1).quantile(0.01), pd.Series(q1).quantile(0.99)
    q2_lo, q2_hi = pd.Series(q2).quantile(0.01), pd.Series(q2).quantile(0.99)
    expected = pd.Series(q1).clip(q1_lo, q1_hi).tolist() + pd.Series(q2).clip(q2_lo, q2_hi).tolist()
    assert out.tolist() == pytest.approx(expected)

    # The Q1 outlier is pulled below its raw 100.0 (but not all the way down
    # to the body's ~3.0, since n=20 makes the 99th percentile still fairly
    # extreme); Q2's own range (computed from Q2 alone) is untouched by Q1's
    # outlier.
    assert 3.0 < out.iloc[19] < 100.0
    assert q2_lo == pytest.approx(min(q2), abs=0.5)
    assert q2_hi == pytest.approx(max(q2), abs=0.5)


# ── delisting-aware daily augmentation ────────────────────────────────────────


def test_augment_daily_applies_shumway_fill_on_missing_dlret():
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    daily = pd.DataFrame(
        {
            "permno": [111, 111, 111],
            "date": dates,
            "prc": [50.0, 48.0, 40.0],
            "bidlo": [49.0, 47.0, 39.0],
            "askhi": [51.0, 49.0, 41.0],
            "vol": [100_000, 100_000, 100_000],
            "ret": [np.nan, -0.04, np.nan],  # delisted on the third day, no CRSP ret
            "bid": [49.9, 47.9, 39.9],
            "ask": [50.1, 48.1, 40.1],
            "shrout": [10_000.0, 10_000.0, 10_000.0],
            "cfacpr": [1.0, 1.0, 1.0],
            "openprc": [50.0, 48.0, 40.0],
            "retx": [np.nan, -0.04, np.nan],
        }
    )
    delist = pd.DataFrame(
        {
            "permno": [111],
            "dlstdt": pd.to_datetime(["2020-01-06"]),
            "dlstcd": [574],  # bankruptcy, performance-related 500s code
            "dlret": [np.nan],  # missing -> Shumway (1997) -30% fill
        }
    )
    ff = pd.DataFrame(
        {
            "date": dates,
            "mktrf": [0.001, 0.002, -0.001],
            "smb": [0.0, 0.0, 0.0],
            "hml": [0.0, 0.0, 0.0],
            "rf": [0.00005, 0.00005, 0.00005],
            "umd": [0.0, 0.0, 0.0],
        }
    )
    cal_index = {d.date(): i for i, d in enumerate(dates)}
    out = wrds_panel._augment_daily(daily, ff, delist, cal_index)

    last = out[out["date"] == pd.Timestamp("2020-01-06")].iloc[0]
    # ret is NaN on the delisting day, so ret_adj should reduce to the Shumway fill itself.
    assert last["ret_adj"] == pytest.approx(-0.30)
    others = out[out["date"] != pd.Timestamp("2020-01-06")]
    assert others["ret_adj"].tolist() == pytest.approx(others["ret"].tolist(), nan_ok=True)


# ── full orchestrator on synthetic fixtures ───────────────────────────────────


def _bdays(start, end):
    return pd.bdate_range(start, end)


def _make_ff(dates):
    n = len(dates)
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "date": dates,
            "mktrf": rng.normal(0.0003, 0.01, n),
            "smb": rng.normal(0.0, 0.005, n),
            "hml": rng.normal(0.0, 0.005, n),
            "rf": np.full(n, 0.00005),
            "umd": rng.normal(0.0, 0.005, n),
        }
    )


def _make_crsp(permno, dates, price=80.0, vol=200_000, split_date=None, split_factor=2.0):
    n = len(dates)
    rng = np.random.default_rng(permno)
    prc = price + np.cumsum(rng.normal(0, 0.3, n))
    prc = np.clip(prc, 5.0, None)
    cfacpr = np.ones(n)
    if split_date is not None:
        cfacpr[dates >= pd.Timestamp(split_date)] = split_factor
    ret = np.r_[np.nan, np.diff(prc) / prc[:-1]]
    return pd.DataFrame(
        {
            "permno": permno,
            "date": dates,
            "bidlo": prc - 0.5,
            "askhi": prc + 0.5,
            "prc": prc,
            "vol": np.full(n, vol, dtype=float),
            "ret": ret,
            "bid": prc - 0.02,
            "ask": prc + 0.02,
            "shrout": np.full(n, 50_000.0),  # thousands of shares
            "cfacpr": cfacpr,
            "openprc": prc,
            "retx": ret,
        }
    )


@pytest.fixture
def synthetic_mirror(monkeypatch):
    """Monkeypatch every wrds_panel loader with small in-memory fixtures.

    Scenario: AAA and DDD are clean surviving events; BBB fails the numest
    guard (never reaches PIT-selection); CCC clears PIT-selection and the
    CRSP/universe joins but is dropped by the no-split guard (cfacpr changes
    between its statpers and its day0).
    """
    dates = _bdays("2019-06-03", "2020-04-30")
    ff = _make_ff(dates)

    crsp = pd.concat(
        [
            _make_crsp(111, dates),  # AAA
            _make_crsp(222, dates),  # BBB (dropped before reaching CRSP anyway)
            _make_crsp(333, dates, split_date="2020-02-01", split_factor=2.0),  # CCC
            _make_crsp(444, dates),  # DDD
        ],
        ignore_index=True,
    )

    consensus = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "AAA", "BBB", "CCC", "DDD"],
            "statpers": pd.to_datetime(
                ["2019-11-01", "2020-01-15", "2020-02-12", "2020-01-01", "2020-01-10", "2020-02-20"]
            ),
            "fpedats": pd.to_datetime(
                ["2019-12-31", "2019-12-31", "2019-12-31", "2019-12-31", "2019-12-31", "2019-12-31"]
            ),
            "numest": [5, 6, 7, 2, 4, 4],
            "numup": [1, 2, 0, 0, 1, 0],
            "numdown": [0, 1, 0, 0, 0, 1],
            "medest": [1.00, 1.05, 1.10, 1.0, 2.00, 0.50],
            "meanest": [1.00, 1.05, 1.10, 1.0, 2.00, 0.50],
            "stdev": [0.05, 0.04, 0.03, 0.05, 0.10, 0.02],
            "actual": [1.10, 1.10, 1.10, 1.1, 2.20, 0.55],
            "anndats_act": pd.to_datetime(
                ["2020-02-10", "2020-02-10", "2020-02-10", "2020-02-10", "2020-03-05", "2020-03-10"]
            ),
        }
    )

    link = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "permno": [111, 222, 333, 444],
            "sdate": pd.to_datetime(["2015-01-01"] * 4),
            "edate": pd.to_datetime(["2025-12-31"] * 4),
            "score": [1, 1, 1, 1],
        }
    )

    universe = pd.DataFrame(
        {
            "permno": [111, 222, 333, 444],
            "namedt": pd.to_datetime(["2015-01-01"] * 4),
            "nameendt": pd.to_datetime(["2030-12-31"] * 4),
            "shrcd": [11, 11, 11, 11],
            "exchcd": [1, 1, 1, 1],
            "siccd": [3674, 3674, 3674, 3674],
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
        }
    )

    ann_times = pd.DataFrame(
        {
            "ticker": ["AAA", "CCC", "DDD"],
            "anndats": pd.to_datetime(["2020-02-10", "2020-03-05", "2020-03-10"]),
            "anntims": [dt.time(7, 0), dt.time(8, 0), dt.time(16, 30)],
        }
    )

    delist = pd.DataFrame(columns=["permno", "dlstdt", "dlstcd", "dlret"])

    monkeypatch.setattr(wrds_panel, "load_ff_daily", lambda start, end: ff)
    monkeypatch.setattr(wrds_panel, "load_ibes_consensus", lambda start, end: consensus)
    monkeypatch.setattr(wrds_panel, "load_ibes_link", lambda: link)
    monkeypatch.setattr(wrds_panel, "load_universe", lambda start, end: universe)
    monkeypatch.setattr(wrds_panel, "load_ann_times", lambda start, end: ann_times)
    monkeypatch.setattr(
        wrds_panel,
        "load_crsp_daily",
        lambda permnos, start, end, progress=True: crsp[crsp["permno"].isin(permnos)],
    )
    monkeypatch.setattr(wrds_panel, "load_delistings", lambda: delist)
    monkeypatch.setattr(wrds_panel, "MIN_FINAL_EVENTS", 1)
    return None


def test_build_event_panel_end_to_end(synthetic_mirror, capsys):
    events, daily = wrds_panel.build_event_panel("2020-01-01", "2020-04-01", progress=False)

    # BBB never clears the numest guard; CCC clears every gate except the
    # no-split guard (its cfacpr changes between statpers and day0).
    assert set(events["ibes_ticker"]) == {"AAA", "DDD"}
    assert len(events) == 2

    # Look-ahead invariant: statpers strictly precedes anndats for every event.
    assert (events["statpers"] < events["anndats"]).all()

    aaa = events[events["ibes_ticker"] == "AAA"].iloc[0]
    assert aaa["meanest"] == pytest.approx(
        1.05
    )  # the PIT-selected row, not the stale or leaked one
    assert aaa["actual"] == pytest.approx(1.10)
    expected_sue = (1.10 - 1.05) / aaa["prc_prev"]
    assert aaa["sue"] == pytest.approx(expected_sue, rel=0.05)  # winsorised, small sample tolerance
    assert aaa["rev"] == pytest.approx((2 - 1) / 6)

    assert aaa["session"] == "bmo"
    assert aaa["day0"] == pd.Timestamp("2020-02-10")

    ddd = events[events["ibes_ticker"] == "DDD"].iloc[0]
    assert ddd["session"] == "amc"
    assert ddd["day0"] == pd.Timestamp("2020-03-11")  # first trading day after 2020-03-10

    required_cols = {
        "permno",
        "ibes_ticker",
        "anndats",
        "anntims",
        "session",
        "session_source",
        "day0",
        "day0_ordinal",
        "fpedats",
        "statpers",
        "actual",
        "meanest",
        "medest",
        "stdev",
        "numest",
        "numup",
        "numdown",
        "prc_prev",
        "shrout",
        "siccd",
        "exchcd",
        "mktcap",
        "adv60",
        "sue",
        "disp",
        "rev",
        "spread_bps_entry",
    }
    assert required_cols.issubset(events.columns)
    assert not daily.empty
    assert {"permno", "date", "ordinal", "ret_adj", "spread_bps", "mktrf", "rf"}.issubset(
        daily.columns
    )

    out = capsys.readouterr().out
    assert "FINAL EVENTS" in out
    assert "PIT-selected" in out
