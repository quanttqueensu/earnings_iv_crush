"""
test_nse_options.py
Offline tests for the NSE UDiFF F&O bhavcopy chain adapter.

Builds synthetic UDiFF zips with the real column header and monkeypatches the
downloader, so the adapter's parsing, schema, right-mapping, OI passthrough,
strike/horizon windowing and local IV inversion are all exercised with no
network. The inversion is checked against an independently priced mark.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.data import nse_options
from earnings_iv_crush.data.options import CHAIN_COLUMNS
from earnings_iv_crush.engine.greeks import bs_price

# The authoritative UDiFF F&O header (order matters; the adapter reads by name).
_UDIFF_HEADER = [
    "TradDt",
    "BizDt",
    "Sgmt",
    "Src",
    "FinInstrmTp",
    "FinInstrmId",
    "ISIN",
    "TckrSymb",
    "SctySrs",
    "XpryDt",
    "FininstrmActlXpryDt",
    "StrkPric",
    "OptnTp",
    "FinInstrmNm",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "LastPric",
    "PrvsClsgPric",
    "UndrlygPric",
    "SttlmPric",
    "OpnIntrst",
    "ChngInOpnIntrst",
    "TtlTradgVol",
    "TtlTrfVal",
    "TtlNbOfTxsExctd",
    "SsnId",
    "NewBrdLotQty",
    "Rmks",
    "Rsvd1",
    "Rsvd2",
    "Rsvd3",
    "Rsvd4",
]


def _row(fin_tp, ticker, expiry, strike, optn_tp, settle, spot, oi, close=None):
    """One UDiFF CSV row as a dict keyed by the real column names."""
    d = {c: "" for c in _UDIFF_HEADER}
    d.update(
        {
            "TradDt": "2025-01-15",
            "Sgmt": "FO",
            "Src": "NSE",
            "FinInstrmTp": fin_tp,
            "TckrSymb": ticker,
            "XpryDt": expiry,
            "StrkPric": f"{strike:.2f}",
            "OptnTp": optn_tp,
            "ClsPric": f"{(close if close is not None else settle):.2f}",
            "UndrlygPric": f"{spot:.2f}",
            "SttlmPric": f"{settle:.2f}",
            "OpnIntrst": str(oi),
        }
    )
    return d


def _udiff_zip(rows) -> bytes:
    """Pack rows into a UDiFF-style zipped CSV, as the archive server serves it."""
    df = pd.DataFrame(rows, columns=_UDIFF_HEADER)
    csv = df.to_csv(index=False)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("BhavCopy_NSE_FO_0_0_0_20250115_F_0000.csv", csv)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clear_daily_cache():
    """The adapter memoises parsed sessions in-process; reset between tests."""
    nse_options._DAILY_CACHE.clear()
    yield
    nse_options._DAILY_CACHE.clear()


def _install(monkeypatch, zip_bytes):
    """Serve the same synthetic session for any requested date."""
    monkeypatch.setattr(nse_options, "_download_fo_zip", lambda yyyymmdd: zip_bytes)


def test_schema_mapping_and_oi(monkeypatch, tmp_path):
    spot, strike = 2900.0, 2900.0
    t = 30 / 365.0
    sigma = 0.25
    mark_c = bs_price(spot, strike, t, 0.0, sigma, "C")
    mark_p = bs_price(spot, strike, t, 0.0, sigma, "P")
    rows = [
        _row("STO", "RELIANCE", "2025-02-14", strike, "CE", mark_c, spot, 12345),
        _row("STO", "RELIANCE", "2025-02-14", strike, "PE", mark_p, spot, 67890),
    ]
    _install(monkeypatch, _udiff_zip(rows))

    ch = nse_options.fetch_option_chain(
        "RELIANCE", "2025-01-15", horizon_days=90, strike_window=0.20, cache_dir=tmp_path
    )
    assert list(ch.columns) == CHAIN_COLUMNS
    assert set(ch["right"]) == {"C", "P"}
    # Settlement mark carried on both sides (no NBBO in a settlement file).
    assert (ch["bid"] == ch["ask"]).all()
    # Real OI, not a snapshot or NaN.
    oi = dict(zip(ch["right"], ch["open_interest"]))
    assert oi["C"] == 12345 and oi["P"] == 67890


def test_iv_inversion_recovers_sigma(monkeypatch, tmp_path):
    spot, strike = 2900.0, 2900.0
    t = 30 / 365.0
    sigma = 0.32
    mark_c = bs_price(spot, strike, t, 0.0, sigma, "C")
    _install(
        monkeypatch,
        _udiff_zip([_row("STO", "RELIANCE", "2025-02-14", strike, "CE", mark_c, spot, 100)]),
    )

    ch = nse_options.fetch_option_chain("RELIANCE", "2025-01-15", cache_dir=tmp_path)
    assert len(ch) == 1
    assert ch["iv"].iloc[0] == pytest.approx(sigma, abs=1e-3)


def test_non_stock_options_excluded(monkeypatch, tmp_path):
    spot = 2900.0
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, 0.25, "C")
    rows = [
        _row("STO", "RELIANCE", "2025-02-14", spot, "CE", mark, spot, 100),
        _row("IDO", "NIFTY", "2025-02-14", spot, "CE", mark, spot, 100),  # index option
        _row("STF", "RELIANCE", "2025-02-14", 0.0, "", 0.0, spot, 100),  # stock future
    ]
    _install(monkeypatch, _udiff_zip(rows))
    ch = nse_options.fetch_option_chain("RELIANCE", "2025-01-15", cache_dir=tmp_path)
    assert len(ch) == 1  # only the STO stock option survives
    # A different underlying's rows never leak into this ticker's chain.
    assert nse_options.fetch_option_chain("NIFTY", "2025-01-15", cache_dir=tmp_path).empty


def test_strike_and_horizon_windows(monkeypatch, tmp_path):
    spot = 2900.0
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, 0.25, "C")
    rows = [
        _row("STO", "RELIANCE", "2025-02-14", 2900.0, "CE", mark, spot, 100),  # ATM, in window
        _row("STO", "RELIANCE", "2025-02-14", 3600.0, "CE", mark, spot, 100),  # +24%, out of band
        _row("STO", "RELIANCE", "2025-09-14", 2900.0, "CE", mark, spot, 100),  # beyond 90d horizon
    ]
    _install(monkeypatch, _udiff_zip(rows))
    ch = nse_options.fetch_option_chain(
        "RELIANCE", "2025-01-15", horizon_days=90, strike_window=0.20, cache_dir=tmp_path
    )
    assert len(ch) == 1
    assert ch["strike"].iloc[0] == 2900.0
    assert ch["expiry"].iloc[0] == pd.Timestamp("2025-02-14")


def test_missing_session_returns_empty(monkeypatch, tmp_path):
    # Every lookback date 404s -> the downloader returns None throughout.
    monkeypatch.setattr(nse_options, "_download_fo_zip", lambda yyyymmdd: None)
    ch = nse_options.fetch_option_chain("RELIANCE", "2025-01-15", cache_dir=tmp_path)
    assert ch.empty
    assert list(ch.columns) == CHAIN_COLUMNS


def test_pre_udiff_date_raises(tmp_path):
    with pytest.raises(ValueError, match="UDiFF"):
        nse_options.fetch_option_chain("RELIANCE", "2024-01-02", cache_dir=tmp_path)


def test_bad_symbol_raises(tmp_path):
    with pytest.raises(ValueError, match="symbol"):
        nse_options.fetch_option_chain("RELIANCE; DROP TABLE", "2025-01-15", cache_dir=tmp_path)


def test_ampersand_symbol_allowed(monkeypatch, tmp_path):
    spot = 2900.0
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, 0.25, "C")
    _install(
        monkeypatch, _udiff_zip([_row("STO", "M&M", "2025-02-14", spot, "CE", mark, spot, 100)])
    )
    ch = nse_options.fetch_option_chain("M&M", "2025-01-15", cache_dir=tmp_path)
    assert len(ch) == 1
    assert not np.isnan(ch["iv"].iloc[0])


def test_underlying_ohlcv_from_bhavcopy_spot(monkeypatch, tmp_path):
    # The underlying series is the file's own raw UndrlygPric, so it matches the
    # raw strikes (unlike a split-adjusted yfinance series).
    spot = 1643.0
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, 0.25, "C")
    _install(
        monkeypatch,
        _udiff_zip([_row("STO", "HDFCBANK", "2025-02-14", spot, "CE", mark, spot, 100)]),
    )
    px = nse_options.fetch_underlying_ohlcv(
        "HDFCBANK", "2025-01-15", "2025-01-17", cache_dir=tmp_path
    )
    assert list(px.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert (px["close"] == spot).all()  # raw spot, not back-adjusted
    assert len(px) == 3  # Wed/Thu/Fri business days in the window


def test_underlying_ohlcv_absent_ticker_empty(monkeypatch, tmp_path):
    spot = 2900.0
    mark = bs_price(spot, spot, 30 / 365.0, 0.0, 0.25, "C")
    _install(
        monkeypatch,
        _udiff_zip([_row("STO", "RELIANCE", "2025-02-14", spot, "CE", mark, spot, 100)]),
    )
    px = nse_options.fetch_underlying_ohlcv(
        "NOTLISTED", "2025-01-15", "2025-01-17", cache_dir=tmp_path
    )
    assert px.empty
    assert list(px.columns) == ["date", "open", "high", "low", "close", "volume"]
