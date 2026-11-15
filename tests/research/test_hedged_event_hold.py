"""
test_hedged_event_hold.py
Offline checks of the hedged event hold on synthetic quotes and a synthetic stock path: the zero-day
case against a hand calculation, the buy-back arm's touch arithmetic, the decomposition identity of
H - B, and the drops that must be counted rather than invented.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "study.py"


@pytest.fixture(scope="module")
def st():
    spec = importlib.util.spec_from_file_location("hedged_event_hold", STUDY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _chain(path: Path, day: str, exp: str, legs: dict[tuple[str, float], tuple[float, float]]):
    sym = [f"XYZ   {pd.Timestamp(exp):%y%m%d}{r}{int(k * 1000):08d}" for (r, k) in legs]
    df = pd.DataFrame(
        {
            "symbol": sym,
            "bid_px_00": [v[0] for v in legs.values()],
            "ask_px_00": [v[1] for v in legs.values()],
        },
        index=pd.DatetimeIndex([pd.Timestamp(f"{day} 19:59", tz="UTC")] * len(sym), name="ts_recv"),
    )
    df.to_parquet(path / f"XYZ_{day}.parquet")


def _crsp(days: list[str], prc: list[float], cf: float = 1.0) -> dict[int, pd.DataFrame]:
    idx = pd.DatetimeIndex(pd.to_datetime(days))
    p = np.array(prc, float)
    ret = np.r_[np.nan, p[1:] / p[:-1] - 1]
    g = pd.DataFrame(
        {"prc": p, "ret": ret, "bid": p - 0.01, "ask": p + 0.01, "cfacpr": cf}, index=idx
    )
    return {1: g}


def _row(exit_day: str, exp: str) -> pd.Series:
    return pd.Series(
        {
            "ticker": "XYZ",
            "entry_date": pd.Timestamp("2018-03-06"),
            "exit_date": pd.Timestamp(exit_day),
            "front_expiry": pd.Timestamp(exp),
            "has_entry_chain": True,
            "front_strike": 100.0,
            "front_bid": 6.0,
            "front_mid": 6.2,
            "front_ask": 6.4,
            "front_fwd": 100.0,
            "s2_iv": 0.30,
            "permno": 1.0,
        }
    )


def test_zero_day_case_matches_hand(st, tmp_path, monkeypatch):
    monkeypatch.setattr(st, "CHAINS", tmp_path)
    legs = {("C", 100.0): (4.0, 4.4), ("P", 100.0): (0.05, 0.15)}
    _chain(tmp_path, "2018-03-09", "2018-03-09", legs)
    crsp = _crsp(["2018-03-09"], [104.0])
    r = st.build_event(_row("2018-03-09", "2018-03-09"), crsp)
    assert r["status"] == "ok" and r["n_hedge"] == 0
    m0 = 0.20 * 100 + 6.0
    fee = 0.0065
    hand_h = (6.0 - 4.0 - 2 * fee - 5e-4 * 104.0) / m0
    hand_b = (6.0 - (4.4 + 0.15) - 4 * fee) / m0
    assert r["H"] == pytest.approx(hand_h)
    assert r["B"] == pytest.approx(hand_b)


def test_decomposition_identity(st, tmp_path, monkeypatch):
    monkeypatch.setattr(st, "CHAINS", tmp_path)
    legs = {
        ("C", 100.0): (5.0, 5.4),
        ("P", 100.0): (1.0, 1.3),
        ("C", 105.0): (2.0, 2.3),
        ("P", 105.0): (3.0, 3.4),
    }
    _chain(tmp_path, "2018-03-07", "2018-03-16", legs)
    days = [
        "2018-03-07",
        "2018-03-08",
        "2018-03-09",
        "2018-03-12",
        "2018-03-13",
        "2018-03-14",
        "2018-03-15",
        "2018-03-16",
    ]
    crsp = _crsp(days, [104.0, 103.0, 105.0, 106.0, 104.5, 103.0, 102.0, 101.5])
    r = st.build_event(_row("2018-03-07", "2018-03-16"), crsp)
    assert r["status"] == "ok" and r["n_hedge"] == 7 and r["sigma_src"] == "exit_chain"
    m0 = r["m0"]
    parts = (
        (r["exit_ask"] - r["exit_mid"])
        + (r["exit_mid"] - r["intrinsic"] + r["hedge_pnl"])
        - (r["equity_cost"] + r["disposal"])
        + 2 * 0.0065
    ) / m0
    assert r["H"] - r["B"] == pytest.approx(parts)
    # a hedged hold must not be worse than naked by more than its equity cost on a mean-reverting
    # path that crosses the strike: here only check both are finite and differ
    assert np.isfinite(r["naked"]) and r["naked"] != r["H"]


def test_split_and_missing_chain_are_counted(st, tmp_path, monkeypatch):
    monkeypatch.setattr(st, "CHAINS", tmp_path)
    assert st.build_event(_row("2018-03-07", "2018-03-09"), {})["status"] == "no_exit_chain"
    legs = {("C", 100.0): (5.0, 5.4), ("P", 100.0): (1.0, 1.3)}
    _chain(tmp_path, "2018-03-07", "2018-03-09", legs)
    crsp = _crsp(["2018-03-07", "2018-03-08", "2018-03-09"], [104.0, 103.0, 105.0])
    crsp[1].loc["2018-03-09", "cfacpr"] = 2.0
    assert st.build_event(_row("2018-03-07", "2018-03-09"), crsp)["status"] == "split_in_hold"


def test_zero_ask_leaves_b_undefined_but_h_scored(st, tmp_path, monkeypatch):
    monkeypatch.setattr(st, "CHAINS", tmp_path)
    legs = {("C", 100.0): (8.0, 8.5), ("P", 100.0): (0.0, 0.0)}
    _chain(tmp_path, "2018-03-09", "2018-03-09", legs)
    r = st.build_event(_row("2018-03-09", "2018-03-09"), _crsp(["2018-03-09"], [108.0]))
    assert r["status"] == "ok" and not r["b_defined"]
    assert np.isnan(r["B"]) and np.isfinite(r["H"])
