"""Tests for src.data.alpaca_options.

The network layer (list_contracts / _daily_close / _underlying_close) is
monkeypatched so the assembly + IV-inversion logic is tested offline, mirroring
the _fetch_raw monkeypatch style in test_options.py. One opt-in `live` test hits
the real Alpaca API and is deselected unless run with `-m live`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import requests

from src.data import alpaca_options as ao
from src.data.options import CHAIN_COLUMNS
from src.engine.greeks import bs_price


def _contracts():
    """Two expiries x {90,100,110} strikes x {C,P}, spot=100."""
    rows = []
    for exp in ("2024-06-21", "2024-07-19"):
        for k in (90.0, 100.0, 110.0):
            for right, typ in (("C", "call"), ("P", "put")):
                rows.append({
                    "symbol": f"X{exp}{right}{int(k)}",
                    "expiry": pd.Timestamp(exp),
                    "strike": k,
                    "right": right,
                    "open_interest": 500,
                })
    return pd.DataFrame(rows, columns=["symbol", "expiry", "strike", "right", "open_interest"])


def _bs_closes(contracts, spot, asof, r=0.0, sigma=0.40):
    """A close for each contract priced at a known sigma, so IV should invert to it."""
    asof_ts = pd.Timestamp(asof)
    out = {}
    for c in contracts.itertuples(index=False):
        t = (c.expiry - asof_ts).days / 365.0
        out[c.symbol] = float(bs_price(spot, c.strike, t, r, sigma, c.right))
    return out


def _patch(monkeypatch, contracts, spot, asof, sigma=0.40):
    monkeypatch.setattr(ao, "_underlying_close", lambda *a, **k: spot)
    monkeypatch.setattr(ao, "list_contracts", lambda *a, **k: contracts)
    monkeypatch.setattr(ao, "_daily_close",
                        lambda *a, **k: _bs_closes(contracts, spot, asof, sigma=sigma))


def test_schema_matches_canonical_chain(monkeypatch):
    asof, spot = "2024-06-03", 100.0
    _patch(monkeypatch, _contracts(), spot, asof)
    df = ao.fetch_option_chain("X", asof)

    assert list(df.columns) == CHAIN_COLUMNS
    assert set(df["right"]) == {"C", "P"}
    assert set(df["expiry"]) == {pd.Timestamp("2024-06-21"), pd.Timestamp("2024-07-19")}
    # bid == ask == close (no historical quote stream on the free tier)
    assert (df["bid"] == df["ask"]).all()
    assert (df["open_interest"] == 500).all()


def test_iv_inverts_back_to_input_sigma(monkeypatch):
    """Prices generated at sigma=0.40 must invert back to ~0.40."""
    asof, spot, sigma = "2024-06-03", 100.0, 0.40
    _patch(monkeypatch, _contracts(), spot, asof, sigma=sigma)
    df = ao.fetch_option_chain("X", asof)

    # ATM strikes invert cleanly; allow a small tolerance for the bracket solver.
    atm = df[np.isclose(df["strike"], 100.0)]
    assert not atm.empty
    assert np.allclose(atm["iv"], sigma, atol=1e-3)


def test_missing_spot_returns_empty_typed_frame(monkeypatch):
    monkeypatch.setattr(ao, "_underlying_close", lambda *a, **k: float("nan"))
    df = ao.fetch_option_chain("X", "2024-06-03")
    assert list(df.columns) == CHAIN_COLUMNS
    assert df.empty


def test_contracts_without_a_close_are_skipped(monkeypatch):
    asof, spot = "2024-06-03", 100.0
    contracts = _contracts()
    _patch(monkeypatch, contracts, spot, asof)
    # Drop closes for one symbol -> that row must not appear.
    closes = _bs_closes(contracts, spot, asof)
    dropped = contracts["symbol"].iloc[0]
    closes.pop(dropped)
    monkeypatch.setattr(ao, "_daily_close", lambda *a, **k: closes)

    df = ao.fetch_option_chain("X", asof)
    assert dropped not in set(c.symbol for c in contracts.itertuples()) or len(df) == len(contracts) - 1


def test_bars_batch_recovers_from_one_bad_symbol(monkeypatch):
    """A single 400-triggering symbol must not sink the whole batch."""
    bad = "1BADSYM240101C00100000"

    def fake_get(host, path, params):
        syms = params["symbols"].split(",")
        if bad in syms:
            raise requests.HTTPError("400")          # batch with the bad symbol fails
        return {"bars": {s: [{"t": "2024-06-03T04:00:00Z", "c": 1.0}] for s in syms}}

    monkeypatch.setattr(ao, "_get", fake_get)
    good = [f"AAA240614C00{i:03d}000" for i in (90, 95, 100, 105)]
    out = ao._daily_close([good[0], good[1], bad, good[2], good[3]], "2024-06-03")
    assert set(out) == set(good)                      # all good symbols recovered
    assert bad not in out                             # bad one dropped


@pytest.mark.live
def test_live_alpaca_chain_has_atm_iv():
    """Real call: a recent expired AAPL chain should yield a finite ATM IV."""
    df = ao.fetch_option_chain("AAPL", "2024-05-06")
    assert list(df.columns) == CHAIN_COLUMNS
    assert not df.empty
    assert df["iv"].notna().any()
