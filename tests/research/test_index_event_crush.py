"""
test_index_event_crush.py
Offline checks of the index event study's pricing and inference on synthetic quotes: the expiry and
strike rules, the touch arithmetic against an independent hand calculation, the exit-ask drop, and
the circular block bootstrap's coverage of a known mean.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research" / "off_earnings" / "2026-11-01-index-event-crush" / "study.py"


@pytest.fixture(scope="module")
def st():
    spec = importlib.util.spec_from_file_location("index_event_crush", STUDY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _occ(exp: str, cp: str, k: float) -> str:
    return f"SPY   {pd.Timestamp(exp):%y%m%d}{cp}{int(round(k * 1000)):08d}"


def _write(path: Path, rows: list[tuple[str, float, float]]) -> None:
    df = pd.DataFrame(
        {
            "ts_recv": pd.Timestamp("2024-01-01 20:59", tz="UTC"),
            "symbol": [r[0] for r in rows],
            "bid_px_00": [r[1] for r in rows],
            "ask_px_00": [r[2] for r in rows],
            "bid_sz_00": 1,
            "ask_sz_00": 1,
        }
    )
    df.to_parquet(path)


@pytest.fixture()
def chains(tmp_path, st, monkeypatch):
    monkeypatch.setattr(st, "CHAINS", tmp_path)
    t, t1 = pd.Timestamp("2024-03-05"), pd.Timestamp("2024-03-06")
    entry = [
        # an expiry on the exit date itself must be skipped (strictly after t1)
        (_occ("2024-03-06", "C", 500), 1.0, 1.1),
        (_occ("2024-03-06", "P", 500), 1.0, 1.1),
        # the rule picks 2024-03-07; strike 501 has the smallest |C mid - P mid|
        (_occ("2024-03-07", "C", 500), 3.0, 3.1),
        (_occ("2024-03-07", "P", 500), 2.0, 2.1),
        (_occ("2024-03-07", "C", 501), 2.5, 2.6),
        (_occ("2024-03-07", "P", 501), 2.45, 2.55),
        (_occ("2024-03-08", "C", 501), 4.0, 4.2),
        (_occ("2024-03-08", "P", 501), 4.0, 4.2),
    ]
    exit_ = [
        (_occ("2024-03-07", "C", 501), 1.9, 2.0),
        (_occ("2024-03-07", "P", 501), 1.3, 1.4),
    ]
    _write(tmp_path / f"SPY_{t.date()}_1559.parquet", entry)
    _write(tmp_path / f"SPY_{t1.date()}_1559.parquet", exit_)
    return t, t1


def test_expiry_and_strike_rule(st, chains):
    t, t1 = chains
    r = st.build_trade("SPY", t, t1, "1559")
    assert r["status"] == "ok"
    assert r["expiry"] == pd.Timestamp("2024-03-07")
    assert r["strike"] == 501.0
    assert r["dte"] == 2


def test_touch_arithmetic_matches_hand_calculation(st, chains):
    t, t1 = chains
    r = pd.DataFrame([st.build_trade("SPY", t, t1, "1559")])
    d = st._returns(r).iloc[0]
    p0 = (2.5 + 2.6) / 2 + (2.45 + 2.55) / 2
    hand = ((2.5 + 2.45) - (2.0 + 1.4)) / p0
    hand_net = ((2.5 + 2.45) - (2.0 + 1.4) - 4 * 0.0065) / p0
    hand_mid = (p0 - ((1.9 + 2.0) / 2 + (1.3 + 1.4) / 2)) / p0
    assert d["p0"] == pytest.approx(p0)
    assert d["short_touch"] == pytest.approx(hand)
    assert d["short_touch_net"] == pytest.approx(hand_net)
    assert d["short_mid"] == pytest.approx(hand_mid)
    assert d["long_touch"] == pytest.approx(((1.9 + 1.3) - (2.6 + 2.55)) / p0)
    # the touch always costs the short relative to the mid
    assert d["short_touch"] < d["short_mid"]


def test_missing_exit_ask_drops_trade(st, chains, tmp_path):
    t, t1 = chains
    _write(
        tmp_path / f"SPY_{t1.date()}_1559.parquet",
        [(_occ("2024-03-07", "C", 501), 1.9, 2.0), (_occ("2024-03-07", "P", 501), 0.0, 0.0)],
    )
    assert st.build_trade("SPY", t, t1, "1559")["status"] == "no_exit_ask"


def test_one_sided_chain_has_no_pair(st, chains, tmp_path):
    t, t1 = chains
    _write(
        tmp_path / f"SPY_{t.date()}_1559.parquet",
        [(_occ("2024-03-07", "P", 501), 2.45, 2.55), (_occ("2024-03-07", "C", 501), 0.0, 2.6)],
    )
    assert st.build_trade("SPY", t, t1, "1559")["status"] == "no_two_sided_pair"


def test_missing_snapshot_is_reported_not_invented(st, chains):
    t, _ = chains
    r = st.build_trade("SPY", t, pd.Timestamp("2024-03-08"), "1559")
    assert r["status"] == "no_exit_snapshot"


@pytest.mark.parametrize("mu", [0.0, 0.05])
def test_block_ci_covers_known_mean(st, mu):
    rng = np.random.default_rng(1)
    x = mu + rng.standard_normal(2000) * 0.5
    lo, hi = st.block_ci(x)
    assert lo < mu < hi
    assert lo < x.mean() < hi
