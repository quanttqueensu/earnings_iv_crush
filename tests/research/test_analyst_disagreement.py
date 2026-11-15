"""
test_analyst_disagreement.py
Within-cell Delta and the cell-matched null on synthetic data.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = (
    Path(__file__).resolve().parents[2]
    / "research/selection/2026-11-07-analyst-disagreement-hedged-hold/study.py"
)
_spec = importlib.util.spec_from_file_location("analyst_disagreement", _PATH)
assert _spec is not None and _spec.loader is not None
study = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = study
_spec.loader.exec_module(study)


def test_delta_is_treated_weighted_within_cell_difference():
    y = np.array([1.0, 1.0, 0.0, 0.0, 5.0, 5.0, 5.0, 4.0, 4.0])
    f = np.array([1, 1, 0, 0, 1, 1, 1, 0, 0], dtype=float)
    c = np.array([0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=float)
    # cell 0: diff 1 with 2 treated; cell 1: diff 1 with 3 treated -> weighted mean 1
    assert study._delta(np.column_stack([y, f, c])) == pytest.approx(1.0)


def test_cell_composition_alone_does_not_beat_the_cell_matched_null():
    rng = np.random.default_rng(0)
    n = 3000
    cells = rng.integers(0, 2, n).astype(float)
    h = np.where(cells == 0, 0.05, -0.05) + rng.normal(0, 0.05, n)
    treated = (cells == 0) & (rng.random(n) < 0.3)
    assert study.cell_matched_null(h, treated, cells) < 95
