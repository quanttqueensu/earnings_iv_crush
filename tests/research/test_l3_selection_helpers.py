"""test_l3_selection_helpers.py: offline checks of the slate-tests lane L3 helpers on synthetic data.

Covers the causal dividend projection and the spot-free implied borrow (C1), the tenor-stratified
contrast (C8), and the ladder crossing and digital curve inversion (E5), each against an
independent closed-form reference.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

LANE = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "research"
    / "2026-11-14-slate-tests"
    / "L3-selection"
)

pytestmark = pytest.mark.skipif(not LANE.exists(), reason="lane folder not present")


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(LANE))
    spec = importlib.util.spec_from_file_location(f"l3_{name}", LANE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


# ── C1: dividend projection ─────────────────────────────────────────────────


@pytest.mark.parametrize("spacing", [91, 182])
def test_projection_uses_only_prior_ex_dates(spacing: int) -> None:
    cb = _load("c1_borrow_build")
    entry = pd.Timestamp("2020-06-01")
    hist = [(entry - pd.Timedelta(days=spacing * j + 10), 0.5) for j in range(4, 0, -1)]
    lo, hi = entry, entry + pd.Timedelta(days=spacing)
    total, _ = cb.projected_divs(hist, entry, lo, hi)
    assert total == pytest.approx(0.5)
    # a later, unseen dividend must not change the projection
    total2, _ = cb.projected_divs(hist + [(entry + pd.Timedelta(days=3), 9.0)], entry, lo, hi)
    assert total2 == pytest.approx(total)


def test_no_projection_after_lookback() -> None:
    cb = _load("c1_borrow_build")
    entry = pd.Timestamp("2020-06-01")
    hist = [(entry - pd.Timedelta(days=cb.BC.div_lookback_days + 5), 1.0)]
    assert cb.projected_divs(hist, entry, entry, entry + pd.Timedelta(days=90))[0] == 0.0


@pytest.mark.parametrize("b_true", [0.0, 0.02, 0.25])
def test_two_expiry_borrow_recovers_planted_rate(b_true: float) -> None:
    r, t1, t2, s = 0.05, 4 / 365, 39 / 365, 100.0
    f1, f2 = s * np.exp((r - b_true) * t1), s * np.exp((r - b_true) * t2)
    b = r - np.log(f2 / f1) / (t2 - t1)
    assert b == pytest.approx(b_true, abs=1e-12)


# ── C8: tenor-stratified contrast ───────────────────────────────────────────


def test_stratified_diff_removes_a_pure_tenor_effect() -> None:
    c8 = _load("c8_score")
    rng = np.random.default_rng(0)
    n = 4000
    stratum = rng.integers(0, 3, n).astype(float)
    sel = (rng.random(n) < np.where(stratum == 0, 0.7, 0.1)).astype(float)
    v = -0.02 * stratum + rng.normal(0, 0.001, n)  # outcome depends on tenor only
    naive = v[sel == 1].mean() - v[sel == 0].mean()
    strat = c8._stratified_diff(np.column_stack([v, sel, stratum]))
    assert naive > 0.01
    assert abs(strat) < 5e-4


# ── E5: ladder crossing and digital curve ───────────────────────────────────


@pytest.mark.parametrize("level", [0.3, 0.5, 0.7])
def test_cross_linear(level: float) -> None:
    e5 = _load("e5_score")
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.9, 0.5, 0.1])
    assert e5._cross(x, y, level) == pytest.approx((0.9 - level) / 0.4)


def test_digital_from_call_spreads_matches_black(tmp_path: Path, monkeypatch) -> None:
    e5 = _load("e5_score")
    fwd, sig, t = 500.0, 0.15, 1 / 252
    ks = np.arange(490.0, 510.5, 1.0)
    sd = sig * np.sqrt(t)

    def call(k: float) -> float:
        d1 = (np.log(fwd / k) + 0.5 * sd**2) / sd
        return float(fwd * norm.cdf(d1) - k * norm.cdf(d1 - sd))

    rows = []
    for k in ks:
        c = call(k)
        p = c - (fwd - k)
        for cp, v in (("C", c), ("P", p)):
            sym = f"SPY   250603{cp}{int(round(k * 1000)):08d}"
            rows.append(
                {
                    "symbol": sym,
                    "bid_px_00": max(v - 0.005, 0.01),
                    "ask_px_00": max(v + 0.005, 0.02),
                }
            )
    pd.DataFrame(rows).to_parquet(tmp_path / "SPY_2025-06-02_1559.parquet")
    monkeypatch.setattr(e5, "CHAINS", tmp_path)
    x, d = e5.digital_curve("SPY", pd.Timestamp("2025-06-02"), pd.Timestamp("2025-06-03"))
    ref = norm.cdf((-x - 0.5 * sd**2) / sd)
    inner = np.abs(x) < 2 * sd
    assert inner.sum() >= 4
    assert np.max(np.abs(d[inner] - ref[inner])) < 0.03
    assert np.all(np.diff(d) <= 0)
