"""Quote-marked OPRA chains.

The transport is monkeypatched so symbology, session slicing and schema mapping are
tested offline, mirroring the style of ``test_dolthub_options.py``. The properties that
matter here and did not exist on the trade-marked path are that the chain is genuinely
two-sided, and that the 15:59 snapshot is resolved in *exchange* time: a fixed UTC cut
would mark the summer half of the sample an hour early, silently, on every event.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.data import databento_quotes as dq
from earnings_iv_crush.data.options import CHAIN_COLUMNS

EXPIRY = pd.Timestamp("2024-02-02")


def _chain() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "expiry": [EXPIRY] * 4,
            "strike": [180.0, 180.0, 185.0, 185.0],
            "right": ["C", "P", "C", "P"],
            "bid": [1.0] * 4,
            "ask": [1.0] * 4,
        }
    )


def _bars(session: str, tz_offset_hours: int) -> pd.DataFrame:
    """Minute bars for one symbol across 15:40-16:05 exchange time, stamped in UTC."""
    local = pd.date_range(f"{session} 15:40", f"{session} 16:05", freq="1min")
    utc = local + pd.Timedelta(hours=tz_offset_hours)
    n = len(local)
    # Mid walks up by 0.01/min so the snapshot and the window median are distinguishable
    # and their expected values are known exactly.
    bid = np.round(1.00 + 0.01 * np.arange(n), 4)
    return pd.DataFrame(
        {
            "bid_px_00": bid,
            "ask_px_00": np.round(bid + 0.10, 4),
            "symbol": [dq.osi_symbol("AAPL", EXPIRY, "C", 180.0)] * n,
        },
        index=pd.DatetimeIndex(utc, name="ts_recv").tz_localize("UTC"),
    )


# ── symbology ────────────────────────────────────────────────────────────────


def test_osi_symbol_matches_the_occ_format() -> None:
    assert dq.osi_symbol("AAPL", EXPIRY, "C", 180.0) == "AAPL  240202C00180000"
    assert dq.osi_symbol("AAPL", EXPIRY, "P", 182.5) == "AAPL  240202P00182500"


def test_osi_symbol_pads_short_roots_to_six_characters() -> None:
    assert dq.osi_symbol("F", EXPIRY, "C", 12.0).startswith("F     ")
    assert len(dq.osi_symbol("F", EXPIRY, "C", 12.0)) == len("AAPL  240202C00180000")


def test_symbols_for_chain_covers_every_contract_once() -> None:
    syms = dq.symbols_for_chain("AAPL", _chain())
    assert len(syms) == 4
    assert syms == sorted(set(syms))


# ── session slicing ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("session", "offset"),
    [("2024-01-31", 5), ("2024-07-31", 4)],  # EST is UTC-5, EDT is UTC-4
)
def test_snapshot_is_resolved_in_exchange_time_across_dst(session: str, offset: int) -> None:
    """The 15:59 mark must be 15:59 *local* in both winter and summer."""
    marks = dq._session_marks(_bars(session, offset), pd.Timestamp(session))
    assert len(marks) == 1
    # 15:40 is bid 1.00, so 15:59 is the twentieth bar: 1.00 + 0.19.
    assert float(marks["bid"].iloc[0]) == pytest.approx(1.19)


def test_window_median_uses_the_trailing_quarter_hour() -> None:
    marks = dq._session_marks(_bars("2024-01-31", 5), pd.Timestamp("2024-01-31"))
    # 15:45..15:59 inclusive is 15 bars. Bids run 1.05..1.19, so mids run 1.10..1.24 and
    # the median is the eighth, at 15:52: bid 1.12, mid 1.17.
    assert int(marks["n_window_bars"].iloc[0]) == 15
    assert float(marks["mid_window"].iloc[0]) == pytest.approx(1.17)


def test_bars_after_the_cut_are_excluded_from_the_snapshot() -> None:
    """16:00-16:05 exists in the pulled data and must not become the mark."""
    marks = dq._session_marks(_bars("2024-01-31", 5), pd.Timestamp("2024-01-31"))
    assert float(marks["bid"].iloc[0]) < 1.20


def test_other_sessions_are_ignored() -> None:
    bars = _bars("2024-01-31", 5)
    assert dq._session_marks(bars, pd.Timestamp("2024-02-01")).empty


def test_empty_bars_give_empty_marks() -> None:
    assert dq._session_marks(pd.DataFrame(), pd.Timestamp("2024-01-31")).empty


# ── schema mapping ───────────────────────────────────────────────────────────


def _marks_and_meta() -> tuple[pd.DataFrame, pd.DataFrame]:
    marks = dq._session_marks(_bars("2024-01-31", 5), pd.Timestamp("2024-01-31"))
    meta = pd.DataFrame(
        {
            "expiry": [EXPIRY],
            "strike": [180.0],
            "right": ["C"],
            "symbol": [dq.osi_symbol("AAPL", EXPIRY, "C", 180.0)],
        }
    )
    return marks, meta


def test_chain_matches_the_canonical_schema() -> None:
    marks, meta = _marks_and_meta()
    chain = dq._chain_from_marks(marks, meta, pd.Timestamp("2024-01-31"), 180.0, 0.0)
    assert list(chain.columns)[: len(CHAIN_COLUMNS)] == CHAIN_COLUMNS


def test_chain_is_genuinely_two_sided() -> None:
    """The property the trade-marked adapter could never satisfy."""
    marks, meta = _marks_and_meta()
    chain = dq._chain_from_marks(marks, meta, pd.Timestamp("2024-01-31"), 180.0, 0.0)
    assert (chain["ask"] > chain["bid"]).all()


def test_iv_is_inverted_from_the_mid_not_a_single_side() -> None:
    from earnings_iv_crush.engine.greeks import implied_vol

    marks, meta = _marks_and_meta()
    chain = dq._chain_from_marks(marks, meta, pd.Timestamp("2024-01-31"), 180.0, 0.0)
    mid = float((chain["bid"].iloc[0] + chain["ask"].iloc[0]) / 2)
    expected = implied_vol(mid, 180.0, 180.0, 2 / 365.0, 0.0, "C")
    assert float(chain["iv"].iloc[0]) == pytest.approx(expected, abs=1e-9)


def test_open_interest_is_nan_rather_than_fabricated() -> None:
    marks, meta = _marks_and_meta()
    chain = dq._chain_from_marks(marks, meta, pd.Timestamp("2024-01-31"), 180.0, 0.0)
    assert chain["open_interest"].isna().all()


def test_expired_contracts_are_dropped() -> None:
    marks, meta = _marks_and_meta()
    chain = dq._chain_from_marks(marks, meta, pd.Timestamp("2024-02-05"), 180.0, 0.0)
    assert chain.empty


def test_fetch_option_chain_never_pulls_when_uncached(tmp_path, monkeypatch) -> None:
    """Every pull on this path is billed, so a cache miss must return empty, not spend."""
    monkeypatch.setattr(dq, "_CACHE_ROOT", tmp_path)

    def _boom() -> None:
        raise AssertionError("fetch_option_chain must not contact the API")

    monkeypatch.setattr(dq, "_client", _boom)
    out = dq.fetch_option_chain("AAPL", "2024-01-31")
    assert out.empty
    assert list(out.columns) == CHAIN_COLUMNS


# ── definition-sourced instrument sets (the pre-2019 extension path) ──────────


def _defn() -> pd.DataFrame:
    """A minimal OPRA definition frame, in the shape `_select_instruments` returns."""
    return pd.DataFrame(
        {
            "exp": [EXPIRY] * 4,
            "strike_price": [180.0, 180.0, 185.0, 185.0],
            "instrument_class": ["C", "P", "C", "P"],
            "raw_symbol": ["X"] * 4,
        }
    )


def test_definition_chain_keeps_only_calls_and_puts(monkeypatch) -> None:
    """A non-option class must be dropped, never coerced.

    Coercing an unknown class to "C" would build a well-formed OSI symbol for a contract
    that does not exist, and the pull would be billed for it and return nothing.
    """
    defn = _defn()
    defn.loc[0, "instrument_class"] = "F"  # future, not an option
    monkeypatch.setattr(dq, "_chain_from_definitions", dq._chain_from_definitions)
    from earnings_iv_crush.data import databento_options as dbo

    monkeypatch.setattr(dbo, "_get_df", lambda *a, **k: defn)
    monkeypatch.setattr(dbo, "_select_instruments", lambda d, asof, spot: d)
    out = dq._chain_from_definitions("AAPL", pd.Timestamp("2024-01-31"), 180.0)
    assert set(out["right"]) == {"C", "P"}
    assert len(out) == 3


def test_definition_chain_is_empty_on_dry_run(monkeypatch) -> None:
    """Definitions are billed, so a dry run must not call the transport at all."""
    from earnings_iv_crush.data import databento_options as dbo

    def _boom(*a, **k):
        raise AssertionError("dry run must not contact the API")

    monkeypatch.setattr(dbo, "_get_df", _boom)
    out = dq._chain_from_definitions("AAPL", pd.Timestamp("2024-01-31"), 180.0, dry_run=True)
    assert out.empty


def test_missing_spot_does_not_cache_an_empty_chain(tmp_path, monkeypatch) -> None:
    """A missing spot must leave the cache untouched so a rerun retries the event.

    Writing an empty chain here would mark the event permanently satisfied and drop it
    from every later build, turning a recoverable input gap into silent sample loss.
    """
    monkeypatch.setattr(dq, "_CACHE_ROOT", tmp_path)
    billed = dq.prefetch_event(
        "AAPL", "2013-04-23", "2013-04-24", allow_definition=True, spot_entry=None
    )
    assert billed == 0.0
    assert not list(tmp_path.rglob("*.parquet"))
