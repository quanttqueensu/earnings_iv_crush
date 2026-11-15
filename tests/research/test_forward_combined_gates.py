"""
test_forward_combined_gates.py
The forward combined-gate scorer on synthetic books: residual value, causality, loud joins.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_PATH = (
    Path(__file__).resolve().parents[2]
    / "research/selection/2026-11-07-forward-combined-gates/study.py"
)
_spec = importlib.util.spec_from_file_location("forward_combined_gates", _PATH)
assert _spec is not None and _spec.loader is not None
study = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = study
_spec.loader.exec_module(study)


def _book(n: int, seed: int = 0, effect: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2026-11-09", periods=n // 3 + 1).repeat(3)[:n]
    d = pd.DataFrame(
        {
            "ticker": [f"T{i}" for i in range(n)],
            "entry_date": dates - pd.offsets.BDay(1),
            "announce_date": dates,
            "exit_date": dates,
            "iv_term_spread_nearest": rng.normal(0.1, 0.05, n),
            "implied_move": rng.uniform(0.02, 0.10, n),
            "entry_rel_spread": rng.uniform(0.02, 0.20, n),
            "residual_value": rng.normal(-0.01, 0.02, n),
            "return_on_margin": rng.normal(0.0, 0.1, n),
            "tenor": rng.choice(["0-1d", "2-4d", "10d+"], n),
        }
    )
    return d


def test_residual_value_matches_hand_calculation():
    d = pd.DataFrame(
        {
            "assumed_mid_mark_ps": [3.0],
            "spot_exit": [105.0],
            "strike": [100.0],
            "contracts": [2],
            "margin": [4000.0],
        }
    )
    # Intrinsic 5.00 exceeds the 3.00 mid by 2.00: an impossible mark, but the sign must
    # still follow the formula, -(mid - intrinsic) x 100 x contracts / margin.
    assert study.residual_value(d).iloc[0] == pytest.approx(-(3.0 - 5.0) * 200 / 4000)


def test_causal_quantile_ignores_same_day_and_needs_history():
    dates = pd.Series(pd.to_datetime(["2026-11-09"] * 30 + ["2026-11-10"] * 2))
    vals = pd.Series(np.r_[np.arange(30.0), 1000.0, -1000.0])
    q = study.causal_quantile(vals, dates, 0.5)
    assert q.iloc[:30].isna().all()  # no strictly earlier trades
    assert q.iloc[30] == q.iloc[31] == pytest.approx(np.median(np.arange(30.0)))


def test_load_events_raises_when_a_trade_has_no_reconciliation(tmp_path):
    base = {"ticker": ["A", "B"], "entry_date": ["2026-11-09", "2026-11-10"]}
    pd.DataFrame(
        {
            **base,
            "exit_date": ["2026-11-10", "2026-11-11"],
            "strike": [100.0, 50.0],
            "contracts": [1, 1],
            "spot_exit": [101.0, 49.0],
            "margin": [2000.0, 1000.0],
            "return_on_margin": [0.01, -0.02],
        }
    ).to_parquet(tmp_path / "forward_ledger_nostop.parquet")
    pd.DataFrame(
        {
            **base,
            "announce_date": ["2026-11-09", "2026-11-10"],
            "transmitted": [True, True],
            "iv_term_spread_nearest": [0.1, 0.2],
            "implied_move": [0.05, 0.06],
            "entry_rel_spread": [0.05, 0.1],
            "front_expiry": ["2026-11-13", "2026-11-13"],
        }
    ).to_parquet(tmp_path / "open_positions.parquet")
    pd.DataFrame(
        {"ticker": ["A"], "entry_date": ["2026-11-09"], "assumed_mid_mark_ps": [2.0]}
    ).to_parquet(tmp_path / "forward_reconciliation.parquet")
    with pytest.raises(ValueError, match="lack a position or reconciliation"):
        study.load_events(tmp_path)


def test_small_book_withholds_verdict_and_reports_every_bin():
    r = study.score_gate(_book(120), study.GATES[1])
    assert r["verdict"].startswith("WITHHELD")
    assert len(r["bins"]) == 4
    assert sum(b["n"] for b in r["bins"]) == r["n_selected"] + r["n_unselected"]


def test_planted_effect_is_found_and_null_book_is_not():
    book = _book(1500, seed=1)
    c = study.cells(book, study.GATES[1])
    planted = book.copy()
    planted.loc[c["selected"], "residual_value"] += 0.03
    planted.loc[c["selected"], "return_on_margin"] += 0.05
    hit = study.score_gate(planted, study.GATES[1])
    assert hit["n_selected"] >= study.MIN_SELECTED_FOR_VERDICT
    assert hit["verdict"] == "PASS"
    miss = study.score_gate(book, study.GATES[1])
    assert miss["verdict"] == "FAIL"


def test_tenor_composition_alone_does_not_pass():
    # Selected trades are all short-dated and short-dated trades carry more residual value,
    # but within each bucket the gate picks at random: the tenor-matched null must not pass.
    rng = np.random.default_rng(3)
    n = 4000
    tenor = np.where(rng.random(n) < 0.5, 0.0, 3.0)
    values = np.where(tenor == 0.0, 0.03, -0.03) + rng.normal(0, 0.01, n)
    selected = (tenor == 0.0) & (rng.random(n) < 0.4)
    assert study.matched_random_null(values, selected, stat=np.mean).percentile > 99
    assert study.tenor_matched_null(values, selected, tenor, n_draws=500) < 95
