"""
test_pairwise_tercile_gates.py
Pairwise tercile gates on synthetic events: mark convention, planted pass, null fail.
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
    / "research/selection/2026-11-07-pairwise-tercile-gates/study.py"
)
_spec = importlib.util.spec_from_file_location("pairwise_tercile_gates", _PATH)
assert _spec is not None and _spec.loader is not None
study = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = study
_spec.loader.exec_module(study)


def test_leg_mark_follows_the_one_sided_convention():
    assert study.leg_mark(1.0, 1.2) == pytest.approx(1.1)
    assert study.leg_mark(0.0, 0.4) == pytest.approx(0.2)  # zero bid: half the ask
    assert np.isnan(study.leg_mark(0.5, 0.0))  # no ask: undefined, never a mid


def test_residual_value_is_time_value_left_over_margin():
    # Marks 3.0 + 0.5 against intrinsic |104 - 100| = 4: the seller is 0.5 better off.
    assert study.residual_value(3.0, 0.5, 104.0, 100.0, 25.0) == pytest.approx(0.5 / 25.0)


def _panel(n: int = 4200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    years = rng.integers(2013, 2027, n)
    dates = pd.to_datetime([f"{y}-01-01" for y in years]) + pd.to_timedelta(
        rng.integers(0, 360, n), unit="D"
    )
    d = pd.DataFrame({f: rng.normal(size=n) for f in study.FAVOURABLE})
    d["announce_date"] = dates
    d["year"] = years
    d["residual_value"] = rng.normal(-0.01, 0.02, n)
    d["realised_move"] = rng.normal(0, 0.05, n)
    d["implied_move"] = 0.06
    d["H"] = rng.normal(0.0, 0.1, n)
    return d.sort_values("announce_date").reset_index(drop=True)


def test_planted_pair_passes_in_every_block_and_null_pair_fails(monkeypatch):
    d = _panel()
    a, b = "implied_over_hist", "entry_half_spread"  # favourable: top of a, bottom of b
    planted = (d[a] > np.quantile(d[a], 2 / 3)) & (d[b] < np.quantile(d[b], 1 / 3))
    d.loc[planted, "residual_value"] += 0.03
    d.loc[planted, "H"] += 0.08
    monkeypatch.setattr(study, "PAIRS", [(a, b), ("bkm_kurt", "name_prior_ratio")])
    card, cells = study.score(d)
    v = card.set_index("pair")["verdict"]
    assert v[f"{a} x {b}"] == "TRADABLE"
    assert v["bkm_kurt x name_prior_ratio"] == "FAIL"
    assert len(cells) == 2 * 3 * 9  # every bin of every pair in every block is kept
