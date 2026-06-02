"""
alpaca_options.py
Historical and current option chains via Alpaca's free options data.

Alpaca's free "indicative" tier serves option *prices* (daily bars, trades) and
the full contract universe back to roughly February 2024, but **not** implied
vol or greeks - those need a signed OPRA agreement. So this adapter pulls the
contract list plus daily close prices and derives implied vol locally by
Black-Scholes inversion (``engine.greeks.implied_vol``), which is exactly the
"derive IV locally" plan recorded in ``notes/data_sourcing.md``.

The result matches the canonical chain schema (``options.CHAIN_COLUMNS``):
``expiry, strike, right, bid, ask, iv, open_interest``. Close prices populate
both ``bid`` and ``ask`` (so ``features._with_mid`` reads the close as the mid),
and ``iv`` is the BS-inverted vol. That means the frame drops straight into
``data_pipeline.build_event_dataset`` and ``historical_surfaces.build_surface_panel``
through their injected ``fetch_chain`` argument with no other change.

Requires ``ALPACA_KEY`` / ``ALPACA_SECRET`` in ``.env``. Two hosts are used:
    paper-api.alpaca.markets  - contract listing (trading API)
    data.alpaca.markets       - option bars + stock bars (market-data API)

Caveats of the free tier, by design:
* No historical NBBO quotes (only bars/trades), so bid/ask carry the close, not a
  true spread; spread cost lives in ``engine.costs`` instead.
* ``open_interest`` is the latest snapshot from the contract record, not the OI
  as of the historical date (historical OI is not on the free tier).
"""
from __future__ import annotations

import time

import pandas as pd
import requests

from ..engine.greeks import implied_vol
from .config import require
from .options import CHAIN_COLUMNS

_TRADING_HOST = "https://paper-api.alpaca.markets"
_DATA_HOST = "https://data.alpaca.markets"
_BAR_CHUNK = 100          # option symbols per bars request
_TIMEOUT = 30
_MAX_RETRIES = 4          # transient network/5xx retries before giving up
_RETRY_BACKOFF = 2.0      # seconds, multiplied by the attempt number


def _headers() -> dict[str, str]:
    """Auth headers, raising a clear error if the keys are not set."""
    return {
        "APCA-API-KEY-ID": require("ALPACA_KEY"),
        "APCA-API-SECRET-KEY": require("ALPACA_SECRET"),
    }


def _get(host: str, path: str, params: dict) -> dict:
    """GET ``host+path`` with auth, returning parsed JSON.

    Retries transient failures (dropped connections, timeouts, 5xx) with a
    linear backoff so one network blip does not abort a long panel build. A 4xx
    raises immediately (``_bars_batch`` relies on that to split a bad batch).
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.get(f"{host}{path}", params=params, headers=_headers(),
                             timeout=_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        else:
            if r.status_code < 500:
                r.raise_for_status()         # 4xx -> immediate (callers may catch)
                return r.json()
            last_error = requests.HTTPError(f"{r.status_code} server error: {path}")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    raise last_error


def list_contracts(underlying: str, asof: str, horizon_days: int = 90,
                   strike_window: float | None = 0.20, spot: float | None = None,
                   max_pages: int = 20) -> pd.DataFrame:
    """Contracts for ``underlying`` expiring within ``horizon_days`` of ``asof``.

    Queries both active and expired (inactive) statuses so a historical ``asof``
    still resolves its universe, de-duplicating by symbol. When ``spot`` is given
    and ``strike_window`` is set, strikes are limited to +/-``strike_window`` of
    spot server-side to keep the payload small.

    Returns a DataFrame with ``symbol, expiry, strike, right, open_interest``.
    """
    asof_ts = pd.Timestamp(asof)
    base = {
        "underlying_symbols": underlying,
        "expiration_date_gte": asof_ts.strftime("%Y-%m-%d"),
        "expiration_date_lte": (asof_ts + pd.Timedelta(days=horizon_days)).strftime("%Y-%m-%d"),
        "limit": 1000,
    }
    if spot and strike_window:
        base["strike_price_gte"] = round(spot * (1 - strike_window), 2)
        base["strike_price_lte"] = round(spot * (1 + strike_window), 2)

    seen: dict[str, dict] = {}
    for status in ("active", "inactive"):
        params = dict(base, status=status)
        token = None
        for _ in range(max_pages):
            if token:
                params["page_token"] = token
            body = _get(_TRADING_HOST, "/v2/options/contracts", params)
            for c in body.get("option_contracts") or []:
                sym = c.get("symbol")
                # Skip malformed/non-standard symbols (a valid OCC symbol starts
                # with the alpha root); Alpaca occasionally lists adjusted symbols
                # the bars endpoint then rejects, which would 400 the whole batch.
                if sym and sym[0].isalpha() and sym not in seen:
                    seen[sym] = {
                        "symbol": sym,
                        "expiry": pd.Timestamp(c["expiration_date"]),
                        "strike": float(c["strike_price"]),
                        "right": "C" if c.get("type") == "call" else "P",
                        "open_interest": pd.to_numeric(c.get("open_interest"),
                                                       errors="coerce"),
                    }
            token = body.get("next_page_token")
            if not token:
                break

    cols = ["symbol", "expiry", "strike", "right", "open_interest"]
    return pd.DataFrame(list(seen.values()), columns=cols)


def _bars_batch(symbols: list[str], start: str, end: str) -> dict:
    """Daily bars for a batch of symbols, tolerant of a bad symbol in the batch.

    A single malformed/unsupported symbol makes Alpaca 400 the whole request, so
    on an HTTP error the batch is split and retried recursively; a lone symbol
    that still fails is dropped. Returns the ``bars`` mapping (symbol -> [bar]).
    """
    if not symbols:
        return {}
    try:
        body = _get(_DATA_HOST, "/v1beta1/options/bars", {
            "symbols": ",".join(symbols), "timeframe": "1Day",
            "start": start, "end": end, "limit": 10000,
        })
        return body.get("bars") or {}
    except requests.HTTPError:
        if len(symbols) == 1:
            return {}                       # drop the offending symbol
        mid = len(symbols) // 2
        left = _bars_batch(symbols[:mid], start, end)
        left.update(_bars_batch(symbols[mid:], start, end))
        return left


def _daily_close(symbols: list[str], asof: str, lookback_days: int = 5) -> dict[str, float]:
    """Most recent daily close on or before ``asof`` for each option symbol.

    Looks back up to ``lookback_days`` so a contract that did not trade exactly on
    ``asof`` still resolves to its latest prior close. Batches the request in
    chunks of ``_BAR_CHUNK`` symbols, each batch fault-tolerant via ``_bars_batch``.
    """
    asof_ts = pd.Timestamp(asof)
    start = (asof_ts - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = (asof_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    out: dict[str, float] = {}
    for i in range(0, len(symbols), _BAR_CHUNK):
        bars_map = _bars_batch(symbols[i:i + _BAR_CHUNK], start, end)
        for sym, bars in bars_map.items():
            usable = [b for b in bars if pd.Timestamp(b["t"]).tz_localize(None) <= asof_ts + pd.Timedelta(days=1)]
            if usable:
                out[sym] = float(usable[-1]["c"])
    return out


def _underlying_close(ticker: str, asof: str, lookback_days: int = 7) -> float:
    """Most recent IEX daily close on or before ``asof`` for the underlying."""
    asof_ts = pd.Timestamp(asof)
    start = (asof_ts - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = (asof_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    body = _get(_DATA_HOST, "/v2/stocks/bars", {
        "symbols": ticker, "timeframe": "1Day",
        "start": start, "end": end, "feed": "iex", "limit": 1000,
    })
    bars = (body.get("bars") or {}).get(ticker) or []
    if not bars:
        return float("nan")
    return float(bars[-1]["c"])


def fetch_option_chain(ticker: str, asof: str, horizon_days: int = 90,
                       strike_window: float = 0.20, r: float = 0.0,
                       spot: float | None = None) -> pd.DataFrame:
    """ATM-centred option chain for ``ticker`` as of ``asof`` (YYYY-MM-DD).

    Drop-in for ``options.fetch_option_chain`` with the same return schema, but
    backed by Alpaca's historical data and a locally inverted ``iv`` column.
    ``asof`` may be any trading day back to ~Feb 2024. Returns an empty,
    correctly-typed frame when the spot or contract universe cannot be resolved.
    """
    if spot is None:
        spot = _underlying_close(ticker, asof)
    if not (spot and spot == spot):                     # NaN-safe
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    contracts = list_contracts(ticker, asof, horizon_days, strike_window, spot)
    if contracts.empty:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    closes = _daily_close(contracts["symbol"].tolist(), asof)
    asof_ts = pd.Timestamp(asof)
    rows = []
    for c in contracts.itertuples(index=False):
        price = closes.get(c.symbol)
        if price is None or price <= 0:
            continue
        t = (c.expiry - asof_ts).days / 365.0
        iv = implied_vol(price, spot, c.strike, t, r, c.right)
        rows.append({
            "expiry": c.expiry,
            "strike": c.strike,
            "right": c.right,
            "bid": price,
            "ask": price,
            "iv": iv,
            "open_interest": c.open_interest,
        })
    return pd.DataFrame(rows, columns=CHAIN_COLUMNS)
