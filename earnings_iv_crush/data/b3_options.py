"""
b3_options.py
Historical Brazilian single-name option chains via the free B3 COTAHIST file.

B3 (Brasil, Bolsa, Balcao) publishes COTAHIST, the end-of-day historical
quotations file, free and without a key: one fixed-width, latin-1 text record per
instrument per session, covering shares, ETFs and their options since 1986. This
adapter reads the stock-option records (market type ``070`` call, ``080`` put) for
one underlying and serves them through the canonical chain interface, so the same
backtest engine runs on Brazilian names.

Unlike a settlement-only feed, COTAHIST carries the session's best bid and ask
(``PREOFC``/``PREOFV``) per contract, so the spread is genuine rather than a mark
stamped on both sides - useful for the slippage layer later. Spot is resolved
self-consistently from the same file's *vista* (cash-equity, market type ``010``)
record for the underlying, so it matches the raw option strikes; there is no
yfinance split-adjustment mismatch (the failure mode that corrupted the NSE ATM
strike before spot was sourced in-file).

Schema mapping (COTAHIST option rows -> ``options.CHAIN_COLUMNS``)::

    DATVEN -> expiry    PREEXE -> strike    TPMERC (070|080) -> right (C|P)
    PREOFC -> bid       PREOFV -> ask       (open_interest is NaN; COTAHIST has none)

``iv`` is inverted locally from the bid/ask mid via ``engine.greeks.implied_vol``.

Caveats, by design:
* Brazilian single-name options are American-style; a European Black-Scholes
  inversion slightly understates IV (the early-exercise premium), most for ITM
  puts. ATM near-dated legs - what the term gate reads - are least affected.
* No open interest in COTAHIST, so ``open_interest`` is NaN; a name/strike that
  did not trade has a zero or stale bid/ask and is dropped by the mid check.
* This reads the daily ``COTAHIST_D`` files (recent sessions). Deep multi-year
  history lives in the annual ``COTAHIST_A<year>`` files; wiring those (download
  once, slice by date) is a documented follow-on, not included here.
* Option liquidity is concentrated in a handful of names (PETR, VALE, ITUB,
  BBAS, BBDC); the tradeable cross-section is thin, so the effective event count
  is small - read a Brazil result as a weak, correlated out-of-sample check.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..engine.greeks import implied_vol
from .options import CHAIN_COLUMNS

# Public daily COTAHIST file: one zipped fixed-width text file per session.
_COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{ddmmyyyy}.ZIP"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
_TIMEOUT = 40
_MAX_RETRIES = 5
_RETRY_BACKOFF = 2.0  # seconds, multiplied by the attempt number

# B3 tickers are 4 alpha chars plus a class digit (PETR4), sometimes a unit
# suffix (SANB11); options key on the 4-char root.
_TICKER_RE = re.compile(r"^[A-Za-z0-9]{4,8}$")

# Market-type codes in COTAHIST: cash equity, and the two option books.
_MKT_VISTA = "010"
_MKT_CALL = "070"
_MKT_PUT = "080"

# In-process cache of parsed per-session frames, keyed by the YYYYMMDD string.
_DAILY_CACHE: dict[str, tuple[pd.DataFrame, dict[str, float]]] = {}

# Normalised per-session option columns produced by ``_parse``.
_OPT_COLUMNS = ["root", "expiry", "strike", "right", "bid", "ask"]


# ── HTTP transport ───────────────────────────────────────────────────────────


def _download_cotahist(yyyymmdd: str) -> bytes | None:
    """Raw daily COTAHIST zip bytes for one session, or ``None`` on a 404.

    ``None`` means no session file (holiday/weekend/not-yet-published), so the
    caller steps back. Transient failures retry with a linear backoff. Isolated
    so tests monkeypatch it without the network.
    """
    dd, mm, yyyy = yyyymmdd[6:8], yyyymmdd[4:6], yyyymmdd[0:4]
    url = _COTAHIST_URL.format(ddmmyyyy=f"{dd}{mm}{yyyy}")
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        else:
            if r.status_code == 404:
                return None
            if r.status_code < 500:
                r.raise_for_status()
                return r.content
            last_error = requests.HTTPError(f"{r.status_code} server error: {url}")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    assert last_error is not None
    raise last_error


# ── Parsing ──────────────────────────────────────────────────────────────────


def _f(field: str) -> float:
    """Parse a COTAHIST price field (implied two decimals) to a float."""
    field = field.strip()
    return float(field) / 100.0 if field else 0.0


def _parse(zip_bytes: bytes) -> tuple[pd.DataFrame, dict[str, float]]:
    """Parse a COTAHIST zip into (option rows, vista-price-by-ticker).

    Reads the fixed-width type-01 quote records: option rows (market type 070/080)
    into ``_OPT_COLUMNS`` with their best bid/ask, and cash-equity rows (010) into
    a ``{ticker: last_price}`` map keyed on the most liquid class per root (the one
    with the largest traded quantity), so an option root resolves to the right
    underlying price. ``latin-1`` is COTAHIST's encoding.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        lines = z.read(z.namelist()[0]).decode("latin-1").splitlines()

    opt_rows = []
    # root -> (best traded quantity seen, last price) so the liquid class wins.
    vista: dict[str, tuple[float, float]] = {}
    for ln in lines:
        if len(ln) < 210 or ln[0:2] != "01":
            continue
        tpmerc = ln[24:27]
        codneg = ln[12:24].strip()
        if tpmerc == _MKT_VISTA:
            quatot = float(ln[152:170].strip() or 0)
            price = _f(ln[108:121])  # PREULT (last)
            root = codneg[:4]
            if price > 0 and (root not in vista or quatot > vista[root][0]):
                vista[root] = (quatot, price)
            continue
        if tpmerc not in (_MKT_CALL, _MKT_PUT):
            continue
        bid = _f(ln[121:134])  # PREOFC
        ask = _f(ln[134:147])  # PREOFV
        last = _f(ln[108:121])  # PREULT, fallback mark
        if bid <= 0 and ask <= 0 and last <= 0:
            continue
        opt_rows.append(
            {
                "root": codneg[:4],
                "expiry": ln[202:210].strip(),  # DATVEN, YYYYMMDD
                "strike": _f(ln[188:201]),  # PREEXE
                "right": "C" if tpmerc == _MKT_CALL else "P",
                "bid": bid if bid > 0 else last,
                "ask": ask if ask > 0 else last,
            }
        )

    prices = {root: price for root, (_, price) in vista.items()}
    if not opt_rows:
        return pd.DataFrame(columns=_OPT_COLUMNS), prices
    df = pd.DataFrame(opt_rows, columns=_OPT_COLUMNS)
    df["expiry"] = pd.to_datetime(df["expiry"], format="%Y%m%d", errors="coerce")
    return df[df["expiry"].notna()].reset_index(drop=True), prices


def _session(yyyymmdd: str, cache_dir: str | Path | None):
    """Parsed (options, vista prices) for one session, memoised and disk-cached."""
    if yyyymmdd in _DAILY_CACHE:
        return _DAILY_CACHE[yyyymmdd]

    root = Path(cache_dir) if cache_dir is not None else Path("data/processed")
    zdir = root / "b3_cotahist"
    zpath = zdir / f"COTAHIST_D{yyyymmdd}.ZIP"
    if zpath.exists():
        zip_bytes: bytes | None = zpath.read_bytes()
    else:
        zip_bytes = _download_cotahist(yyyymmdd)
        if zip_bytes is not None:
            zdir.mkdir(parents=True, exist_ok=True)
            zpath.write_bytes(zip_bytes)

    parsed = (
        _parse(zip_bytes) if zip_bytes is not None else (pd.DataFrame(columns=_OPT_COLUMNS), {})
    )
    _DAILY_CACHE[yyyymmdd] = parsed
    return parsed


# ── Public spot series ───────────────────────────────────────────────────────


def fetch_underlying_ohlcv(
    ticker: str,
    start: str,
    end: str,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Daily underlying close series for a B3 name, from COTAHIST's vista record.

    Drop-in for ``equities.fetch_equity_ohlcv`` (same schema) but sourced from the
    same COTAHIST files the chain uses, so spot and strikes are the one raw, un-
    adjusted price. Only ``close`` is meaningful; OHLC repeat it and ``volume`` is
    NaN. ``end`` is inclusive.
    """
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"unsupported B3 ticker: {ticker!r}")
    cols = ["date", "open", "high", "low", "close", "volume"]
    root = ticker[:4]
    dates: list[pd.Timestamp] = []
    closes: list[float] = []
    for day in pd.bdate_range(pd.Timestamp(start), pd.Timestamp(end)):
        _, prices = _session(day.strftime("%Y%m%d"), cache_dir)
        price = prices.get(root)
        if price:
            dates.append(day)
            closes.append(price)
    if not dates:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [float("nan")] * len(dates),
        },
        columns=cols,
    )


# ── Public chain fetcher ─────────────────────────────────────────────────────


def fetch_option_chain(
    ticker: str,
    asof: str,
    horizon_days: int = 90,
    strike_window: float = 0.20,
    r: float = 0.0,
    spot: float | None = None,
    lookback_days: int = 5,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """ATM-centred option chain for ``ticker`` as of ``asof`` (YYYY-MM-DD).

    Drop-in for ``options.fetch_option_chain`` with the same return schema, but
    backed by the free B3 COTAHIST daily file with a locally inverted ``iv``.
    ``ticker`` is the cash-equity symbol (e.g. ``PETR4``); its options are keyed
    on the shared 4-char root. When ``asof`` is not a session the snapshot steps
    back up to ``lookback_days`` days.

    Parameters
    ----------
    ticker : str
        B3 cash-equity ticker (e.g. ``PETR4``, ``VALE3``).
    asof : str
        As-of date (``YYYY-MM-DD``).
    horizon_days : int, optional
        Calendar days past ``asof`` to include expiries. Defaults to ``90``.
    strike_window : float, optional
        Half-width of the strike band as a fraction of spot. Defaults to ``0.20``.
    r : float, optional
        Risk-free rate for the local IV inversion. Defaults to ``0.0``.
    spot : float or None, optional
        Underlying price; taken from the file's vista record when ``None``.
    lookback_days : int, optional
        Calendar days to step back to the latest session. Defaults to ``5``.
    cache_dir : str or Path or None, optional
        Root for the raw-zip disk cache; defaults to ``data/processed``.

    Returns
    -------
    pandas.DataFrame
        Chain with ``CHAIN_COLUMNS`` (``open_interest`` is NaN). Empty (correctly
        typed) when no session resolves or the name has no options that day.
    """
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"unsupported B3 ticker: {ticker!r}")
    asof_ts = pd.Timestamp(asof)
    root = ticker[:4]

    options = pd.DataFrame(columns=_OPT_COLUMNS)
    prices: dict[str, float] = {}
    for back in range(lookback_days + 1):
        day = asof_ts - pd.Timedelta(days=back)
        options, prices = _session(day.strftime("%Y%m%d"), cache_dir)
        if not options.empty:
            break

    chain = options[options["root"] == root]
    if chain.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    row_spot = spot if spot is not None else prices.get(root, float("nan"))
    if not (row_spot and row_spot == row_spot):  # NaN-safe
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    horizon = asof_ts + pd.Timedelta(days=horizon_days)
    lo = row_spot * (1 - strike_window)
    hi = row_spot * (1 + strike_window)
    days = (chain["expiry"] - asof_ts).dt.days
    keep = (days > 0) & (chain["expiry"] <= horizon) & chain["strike"].between(lo, hi)
    chain = chain[keep]
    if chain.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    mid = (chain["bid"] + chain["ask"]) / 2.0
    t_years = (chain["expiry"] - asof_ts).dt.days / 365.0
    ivs = [
        implied_vol(m, row_spot, k, t, r, right)
        for m, k, t, right in zip(mid, chain["strike"], t_years, chain["right"], strict=True)
    ]
    return pd.DataFrame(
        {
            "expiry": chain["expiry"].to_numpy(),
            "strike": chain["strike"].to_numpy(),
            "right": chain["right"].to_numpy(),
            "bid": chain["bid"].to_numpy(),
            "ask": chain["ask"].to_numpy(),
            "iv": ivs,
            "open_interest": np.nan,
        },
        columns=CHAIN_COLUMNS,
    )
