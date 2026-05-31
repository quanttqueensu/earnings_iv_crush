"""Option chains via yfinance (no key required) - the development fallback.

This is the keyless development fallback: it returns the
*current* chain only (yfinance has no history) and its IV/greeks are rough, so
it is for development and live current-snapshot work, not the historical
backtest. IBKR / Alpaca / OptionMetrics replace it as those land.

Returns the ATM-centred chain across the nearest expiries, normalised to:
    expiry (datetime64), strike (float), right ('C'|'P'),
    bid, ask, iv, open_interest
"""
from __future__ import annotations

import pandas as pd

CHAIN_COLUMNS = ["expiry", "strike", "right", "bid", "ask", "iv", "open_interest"]


def _fetch_raw(ticker: str, asof: str, max_expiries: int, horizon_days: int):
    """Return (spot, [(expiry, calls_df, puts_df), ...]) from yfinance.

    Pulls expiries on/after `asof` up to `horizon_days` out, capped at
    `max_expiries`. Isolated so tests can monkeypatch it without the network.
    """
    import yfinance as yf  # lazy import, matching equities.py

    tk = yf.Ticker(ticker)
    try:
        spot = float(tk.fast_info["lastPrice"])
    except Exception:
        spot = None

    asof_ts = pd.Timestamp(asof)
    horizon = asof_ts + pd.Timedelta(days=horizon_days)
    out = []
    for exp in tk.options:                       # sorted ascending by yfinance
        exp_ts = pd.Timestamp(exp)
        if exp_ts < asof_ts:
            continue
        if exp_ts > horizon:
            break
        oc = tk.option_chain(exp)
        out.append((exp, oc.calls, oc.puts))
        if len(out) >= max_expiries:
            break
    return spot, out


def _normalize(spot, raw, strike_window: float) -> pd.DataFrame:
    """Flatten raw (calls, puts) frames into the canonical chain schema.

    When spot is known, strikes are limited to +/-`strike_window` of it so the
    result is ATM-centred; otherwise all strikes are kept.
    """
    lo = spot * (1 - strike_window) if spot else None
    hi = spot * (1 + strike_window) if spot else None
    rows = []
    for exp, calls, puts in raw:
        for df, right in ((calls, "C"), (puts, "P")):
            for _, o in df.iterrows():
                strike = float(o["strike"])
                if lo is not None and not (lo <= strike <= hi):
                    continue
                rows.append({
                    "expiry": pd.Timestamp(exp),
                    "strike": strike,
                    "right": right,
                    "bid": o.get("bid"),
                    "ask": o.get("ask"),
                    "iv": o.get("impliedVolatility"),
                    "open_interest": o.get("openInterest"),
                })
    return pd.DataFrame(rows, columns=CHAIN_COLUMNS)


def fetch_option_chain(ticker: str, asof: str, max_expiries: int = 6,
                       horizon_days: int = 90, strike_window: float = 0.20) -> pd.DataFrame:
    """ATM-centred option chain for one name across the nearest expiries.

    `asof` should be ~today: yfinance serves only the live chain, so a far-past
    date yields an empty frame. Columns: expiry, strike, right, bid, ask, iv,
    open_interest.
    """
    spot, raw = _fetch_raw(ticker, asof, max_expiries, horizon_days)
    return _normalize(spot, raw, strike_window)
