"""
test_paper_radar_provenance.py
The live paper book must never silently absorb a trade scored after the fact.

The forward recorder and the after-the-fact backfill produce rows with identical
columns and wildly different inferential status: a backfilled entry was chosen knowing
the outcome. Once the two share a file with nothing to tell them apart, any statistic
computed over it is a backtest wearing a paper record's clothes. These tests pin the
three places that separation can fail.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.paper_radar import LEDGER_COLS, LIVE, _load


def _row(ticker: str = "AAPL", **over: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": ticker,
        "announce_date": "2026-08-13",
        "entry_date": "2026-08-12",
        "exit_date": "2026-08-13",
        "spot_entry": 100.0,
        "spot_exit": 102.0,
        "implied_move": 0.05,
        "realised_move": 0.02,
        "ret": 0.6,
        "net_ret": 0.484,
        "in_rich_set": "false",
        "source": LIVE,
    }
    row.update(over)
    return row


def test_ledger_schema_carries_source() -> None:
    """Provenance is part of the schema, not an optional annotation."""
    assert "source" in LEDGER_COLS


def test_load_refuses_a_populated_ledger_with_no_source(tmp_path) -> None:
    """A book whose rows cannot be attributed must stop the run, not be appended to.

    This is the failure that matters: an older unattributed ledger is picked up by a
    later run, live exits are appended, and the merged file is then quoted as forward
    evidence. Raising here is the only point at which the two are still separable.
    """
    legacy = _row()
    del legacy["source"]
    path = tmp_path / "radar_ledger.csv"
    pd.DataFrame([legacy]).to_csv(path, index=False)

    with pytest.raises(SystemExit, match="source"):
        _load(path, LEDGER_COLS)


def test_load_accepts_an_empty_legacy_ledger(tmp_path) -> None:
    """A headers-only file has nothing to misattribute, so it must not block the run."""
    path = tmp_path / "radar_ledger.csv"
    pd.DataFrame(columns=[c for c in LEDGER_COLS if c != "source"]).to_csv(path, index=False)

    assert _load(path, LEDGER_COLS).empty


def test_load_round_trips_a_stamped_ledger(tmp_path) -> None:
    path = tmp_path / "radar_ledger.csv"
    pd.DataFrame([_row(), _row("MSFT", source="backfill")]).to_csv(path, index=False)

    got = _load(path, LEDGER_COLS)
    assert len(got) == 2
    assert set(got["source"]) == {LIVE, "backfill"}


def test_only_live_rows_count_toward_the_forward_book() -> None:
    """The reported book is the live subset, so a backfilled winner cannot flatter it.

    Mirrors the filter in ``main``: a book of one live loser and one backfilled winner
    must read as a losing book of N=1, never as a break-even book of N=2.
    """
    ledger = pd.DataFrame([_row(net_ret=-0.30), _row("MSFT", net_ret=+0.90, source="backfill")])

    live = ledger[ledger["source"].astype(str).str.lower() == LIVE]

    assert len(live) == 1
    assert float(live["net_ret"].mean()) == pytest.approx(-0.30)
    assert float(live["net_ret"].mean()) < float(ledger["net_ret"].mean())
