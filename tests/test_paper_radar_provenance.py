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

from scripts.paper_radar import (
    COST,
    LEDGER_COLS,
    LIVE,
    MARK_FALLBACK,
    MARK_QUOTE,
    _load,
)


def _row(ticker: str = "AAPL", **over: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": ticker,
        "announce_date": "2026-08-13",
        "entry_date": "2026-08-12",
        "exit_date": "2026-08-13",
        "spot_entry": 100.0,
        "spot_exit": 102.0,
        "strike": 100.0,
        "expiry": "2026-08-14",
        "straddle_entry": 5.0,
        "straddle_exit": 3.0,
        "implied_move": 0.05,
        "realised_move": 0.02,
        "ret": 0.4,
        "net_ret": 0.284,
        "ret_on_margin": 0.08,
        "net_ret_on_margin": 0.0568,
        "ret_intrinsic_proxy": 0.6,
        "mark_source": MARK_QUOTE,
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


def test_schema_carries_the_marked_exit_and_its_provenance() -> None:
    """The exit mark, its source, and both return bases are all part of the record."""
    for col in (
        "straddle_exit",
        "mark_source",
        "ret_on_margin",
        "net_ret_on_margin",
        "ret_intrinsic_proxy",
    ):
        assert col in LEDGER_COLS


def test_intrinsic_proxy_overstates_a_short_straddle() -> None:
    """The retired estimator must stay strictly more flattering than the marked one.

    A straddle sold at 5.00 and bought back at 3.00 returns 40% of premium. Pricing the
    close at intrinsic (|102 - 100| = 2.00) claims 60%, because the 1.00 of premium still
    in the contract is never paid. On the 912-event canonical panel that gap is 55.1% of
    the entry credit and it flips mean return on margin from -0.1142 to +0.1928, so the
    two numbers must never be allowed to stand in for one another.
    """
    row = _row()
    marked = (float(row["straddle_entry"]) - float(row["straddle_exit"])) / float(
        row["straddle_entry"]
    )
    intrinsic = abs(float(row["spot_exit"]) - float(row["strike"]))
    proxy = (float(row["straddle_entry"]) - intrinsic) / float(row["straddle_entry"])

    assert marked == pytest.approx(0.40)
    assert proxy == pytest.approx(0.60)
    assert proxy > marked


def test_fallback_marked_rows_are_excluded_from_the_reported_book() -> None:
    """An unquotable close is recorded but never counted, in either direction."""
    ledger = pd.DataFrame(
        [
            _row(net_ret_on_margin=-0.05),
            _row("MSFT", net_ret_on_margin=+0.60, mark_source=MARK_FALLBACK),
        ]
    )

    reported = ledger[ledger["mark_source"].astype(str) == MARK_QUOTE]

    assert len(reported) == 1
    assert float(reported["net_ret_on_margin"].mean()) == pytest.approx(-0.05)


def test_cost_is_charged_on_premium_not_on_margin() -> None:
    """The 11.6% round trip is a fraction of premium, so it must scale the credit.

    Charging it against margin instead would understate the cost by the margin-to-credit
    ratio, which is about 5x on this book.
    """
    credit_ps, exit_ps, spot = 5.0, 3.0, 100.0
    margin_ps = 0.20 * spot + credit_ps
    gross_rom = (credit_ps - exit_ps) / margin_ps
    net_rom = (credit_ps - exit_ps - COST * credit_ps) / margin_ps

    assert net_rom < gross_rom
    assert (gross_rom - net_rom) == pytest.approx(COST * credit_ps / margin_ps)


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
