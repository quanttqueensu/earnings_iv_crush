"""Tests for earnings_iv_crush.data.dolthub_options.

The HTTP layer (``_query``) is monkeypatched so the SQL assembly, snapshot
step-back and schema mapping are tested offline, mirroring the transport
monkeypatch style in test_alpaca_options.py. One opt-in `live` test hits the
real DoltHub API and is deselected unless run with `-m live`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.data import dolthub_options as do
from earnings_iv_crush.data.options import CHAIN_COLUMNS


def _rows(snapshot: str = "2024-06-03"):
    """Two expiries x {90,100,110} strikes x {Call,Put}, with IV and a spread."""
    out = []
    for exp in ("2024-06-21", "2024-07-19"):
        for k in (90.0, 100.0, 110.0):
            for cp in ("Call", "Put"):
                out.append(
                    {
                        "date": snapshot,
                        "act_symbol": "AAPL",
                        "expiration": exp,
                        "strike": f"{k:.2f}",
                        "call_put": cp,
                        "bid": "1.20",
                        "ask": "1.40",
                        "vol": "0.4200",
                    }
                )
    return out


def test_schema_matches_canonical_chain(monkeypatch):
    monkeypatch.setattr(do, "_query", lambda sql: _rows())
    df = do.fetch_option_chain("AAPL", "2024-06-03")

    assert list(df.columns) == CHAIN_COLUMNS
    assert set(df["right"]) == {"C", "P"}
    assert set(df["expiry"]) == {pd.Timestamp("2024-06-21"), pd.Timestamp("2024-07-19")}
    # Real two-sided quote (unlike the Alpaca close-on-both-sides adapter).
    assert (df["ask"] > df["bid"]).all()
    assert np.allclose(df["iv"], 0.42)
    # This dataset has no open-interest column.
    assert df["open_interest"].isna().all()


def test_date_is_pinned_and_expiry_window_applied():
    captured = {}

    def fake_query(sql):
        captured["sql"] = sql
        return _rows()

    # Patch the bound function the fetcher calls.
    original = do._query
    do._query = fake_query  # type: ignore[assignment]
    try:
        do.fetch_option_chain("AAPL", "2024-06-03", horizon_days=60)
    finally:
        do._query = original  # type: ignore[assignment]

    sql = captured["sql"]
    assert "date = '2024-06-03'" in sql  # always date-pinned (no full scan)
    assert "act_symbol = 'AAPL'" in sql
    assert "expiration >= '2024-06-03'" in sql
    assert "expiration <= '2024-08-02'" in sql  # asof + 60 days


def test_strike_band_only_when_spot_given(monkeypatch):
    seen = {}
    monkeypatch.setattr(do, "_query", lambda sql: seen.update(last=sql) or _rows())

    do.fetch_option_chain("AAPL", "2024-06-03")
    assert "strike >=" not in seen["last"]

    do.fetch_option_chain("AAPL", "2024-06-03", spot=100.0, strike_window=0.20)
    assert "strike >= 80.0" in seen["last"]
    assert "strike <= 120.0" in seen["last"]


def test_snapshot_steps_back_to_prior_session(monkeypatch):
    # The first two candidate dates (asof, asof-1) return nothing; the third does.
    tried = []

    def fake_query(sql):
        day = sql.split("date = '")[1][:10]
        tried.append(day)
        return _rows(snapshot="2024-05-31") if day == "2024-05-31" else []

    monkeypatch.setattr(do, "_query", fake_query)
    # 2024-06-02 is a Sunday; the dataset's last session is Fri 2024-05-31.
    df = do.fetch_option_chain("AAPL", "2024-06-02")
    assert tried[:3] == ["2024-06-02", "2024-06-01", "2024-05-31"]
    assert not df.empty


def test_no_session_in_window_returns_empty_typed_frame(monkeypatch):
    monkeypatch.setattr(do, "_query", lambda sql: [])
    df = do.fetch_option_chain("AAPL", "2024-06-03")
    assert list(df.columns) == CHAIN_COLUMNS
    assert df.empty


def test_bad_symbol_is_rejected_before_querying(monkeypatch):
    # Should never reach the network for an injection-shaped symbol.
    monkeypatch.setattr(do, "_query", lambda sql: pytest.fail("must not query"))
    with pytest.raises(ValueError):
        do.fetch_option_chain("AAPL'; DROP TABLE option_chain; --", "2024-06-03")


def test_query_raises_on_permanent_error(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "query_execution_status": "Error",
                "query_execution_message": "table not found: option_chain",
                "rows": [],
            }

    monkeypatch.setattr(do.requests, "get", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="table not found"):
        do._query("SELECT 1")


@pytest.mark.live
def test_live_dolthub_chain_has_atm_iv():
    """Real call: a 2024 AAPL chain should yield finite IV and a real spread."""
    df = do.fetch_option_chain("AAPL", "2024-06-28", spot=210.0)
    assert list(df.columns) == CHAIN_COLUMNS
    assert not df.empty
    assert df["iv"].notna().any()
    assert (df["ask"] >= df["bid"]).all()
