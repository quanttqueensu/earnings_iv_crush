"""Tests for the pre-registered trial ledger.

The ledger exists so a Deflated Sharpe Ratio charges for the search that was
actually made. Every test here is about making the count hard to understate.
"""

from __future__ import annotations

import json

import pytest

from earnings_iv_crush.engine.alpha_adjudication import TrialLedger, TrialLedgerError


def test_declared_specifications_are_counted(tmp_path):
    ledger = TrialLedger(tmp_path / "trials.json")
    ledger.declare("vasquez::q=0.80", {"pctl": 0.80})
    ledger.declare("vasquez::q=0.85", {"pctl": 0.85})
    assert ledger.n_trials == 2


def test_abandoned_branches_still_cost_deflation(tmp_path):
    """Declaring then not running must not reduce the trial count."""
    ledger = TrialLedger(tmp_path / "trials.json")
    labels = ledger.declare_grid("slope", {"pctl": [0.7, 0.8, 0.9], "horizon": [1, 3]})
    assert len(labels) == 6
    ledger.record(labels[0], {"sharpe": 0.11})
    assert ledger.n_trials == 6  # not 1
    assert len(ledger.results) == 1


def test_grid_declares_the_full_cartesian_product(tmp_path):
    ledger = TrialLedger(tmp_path / "trials.json")
    labels = ledger.declare_grid("g", {"a": [1, 2], "b": ["x", "y", "z"]})
    assert len(labels) == 6
    assert len(set(labels)) == 6
    assert ledger.n_trials == 6


def test_recording_an_undeclared_label_raises(tmp_path):
    ledger = TrialLedger(tmp_path / "trials.json")
    with pytest.raises(TrialLedgerError, match="never declared"):
        ledger.record("sneaky", {"sharpe": 2.0})


def test_redeclaring_with_a_different_spec_raises(tmp_path):
    ledger = TrialLedger(tmp_path / "trials.json")
    ledger.declare("a", {"pctl": 0.80})
    ledger.declare("a", {"pctl": 0.80})  # idempotent
    with pytest.raises(TrialLedgerError, match="different specification"):
        ledger.declare("a", {"pctl": 0.85})


def test_ledger_persists_across_sessions(tmp_path):
    path = tmp_path / "trials.json"
    first = TrialLedger(path)
    first.declare_grid("g", {"a": [1, 2, 3]})
    first.record("g::a=1", {"sharpe": 0.2})

    reopened = TrialLedger(path)
    assert reopened.n_trials == 3
    assert reopened.results["g::a=1"]["sharpe"] == 0.2


def test_ledger_file_is_readable_json(tmp_path):
    path = tmp_path / "trials.json"
    ledger = TrialLedger(path)
    ledger.declare("a", {"pctl": 0.8})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["declared"]["a"] == {"pctl": 0.8}


def test_sr_trials_std_needs_two_finite_results(tmp_path):
    ledger = TrialLedger(tmp_path / "trials.json")
    ledger.declare_grid("g", {"a": [1, 2, 3]})
    assert ledger.sr_trials_std() == 0.0
    ledger.record("g::a=1", {"sharpe": 0.10})
    assert ledger.sr_trials_std() == 0.0
    ledger.record("g::a=2", {"sharpe": 0.30})
    assert ledger.sr_trials_std() > 0.0
