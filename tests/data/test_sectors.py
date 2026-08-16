"""Tests for data.sectors: the frozen GICS map that feeds the concentration cap.

The map is static by design, so the risk here is not a stale label but a broken
contract with its consumer. ``engine.risk.cap_concentration`` groups on a
``sector`` column and silently skips the cap when it is missing, so the labels
have to come back complete, aligned to the tickers asked for, and never NaN.
"""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.data import sectors
from earnings_iv_crush.data.universe import get_universe
from earnings_iv_crush.engine import risk


def test_every_megacap_name_has_a_sector() -> None:
    """An unmapped name resolves to "Unknown", which would escape the cap."""
    unmapped = [t for t in get_universe("megacap") if sectors.sector_of(t) == "Unknown"]
    assert not unmapped, f"megacap names missing from the frozen sector map: {unmapped}"


def test_unknown_ticker_degrades_rather_than_raising() -> None:
    assert sectors.sector_of("NOT_A_TICKER") == "Unknown"


def test_labels_align_to_the_tickers_asked_for() -> None:
    tickers = ["AAPL", "MSFT", "NOT_A_TICKER"]
    labels = sectors.sector_labels(tickers)
    assert list(labels.index) == tickers
    assert labels.name == "sector"
    assert labels.notna().all()


def test_the_map_actually_drives_the_concentration_cap() -> None:
    """The consumer contract, end to end: label a frame, then cap it."""
    tickers = ["AAPL", "MSFT", "NVDA", "JPM"]
    events = pd.DataFrame({"ticker": tickers, "entry_date": ["d"] * 4})
    events["sector"] = events["ticker"].map(sectors.sector_of)

    capped = risk.cap_concentration(events, max_per_sector=1)

    # One position per sector per day, whatever the sectors turn out to be.
    assert capped.groupby(["entry_date", "sector"]).size().max() == 1
