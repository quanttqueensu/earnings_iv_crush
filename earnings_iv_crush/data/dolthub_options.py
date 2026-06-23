"""
dolthub_options.py
Historical option chains via the free DoltHub ``dolthub/options`` database.

This serves dated chains carrying **real** bid/ask quotes, implied vol and greeks
(the publisher computes them), so unlike the Alpaca adapter it needs no local
Black-Scholes inversion and the spread is genuine rather than the close stamped
on both sides. Coverage runs from roughly 2019 through late 2024, which makes it
the pre-2024 historical sample the Alpaca free tier (~Feb 2024 onward) cannot
reach - the longer span the skew/term work needs to stop being one regime.

Queried through DoltHub's public SQL-over-HTTP API (no key, public database), so
there is no multi-gigabyte clone: each call pulls a single ticker-date snapshot.
The ``option_chain`` primary key is date-led, so every query pins an exact
``date`` - an unbounded ``WHERE act_symbol = ...`` scan times out server-side by
design, and the adapter never issues one.

Schema mapping (``option_chain`` -> ``options.CHAIN_COLUMNS``)::

    expiration -> expiry      strike  -> strike      call_put -> right ('C'|'P')
    bid        -> bid         ask     -> ask         vol      -> iv

There is no open-interest column in this dataset, so ``open_interest`` is NaN.
Any feature that needs OI (e.g. the wing open-interest ratio) must take it from
another source when this provider backs the chain; everything that reads IV,
greeks or the spread works unchanged.

The result matches ``options.CHAIN_COLUMNS`` exactly, so it is a drop-in for
``options.fetch_option_chain`` / ``alpaca_options.fetch_option_chain`` and can be
injected as the ``fetch_chain`` argument of ``data_pipeline.build_event_dataset``
or ``historical_surfaces.build_surface_panel`` with no other change.
"""

from __future__ import annotations

import re
import time

import numpy as np
import pandas as pd
import requests

from .options import CHAIN_COLUMNS

# Public SQL-over-HTTP endpoint for the dolthub/options database (master branch).
_API = "https://www.dolthub.com/api/v1alpha1/dolthub/options/master"
_TIMEOUT = 30
_MAX_RETRIES = 5
_RETRY_BACKOFF = 2.0  # seconds, multiplied by the attempt number

# act_symbol is a plain exchange symbol (letters, digits, dot or hyphen class
# shares). Anything else is rejected before it reaches the SQL string, so the
# inlined literal cannot carry an injection.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")


# ── HTTP transport ───────────────────────────────────────────────────────────


def _query(sql: str) -> list[dict]:
    """Run ``sql`` against the DoltHub API and return the ``rows`` list.

    Retries transient failures (dropped connections, timeouts, 5xx) and the
    API's own ``context deadline exceeded`` (its query-time budget, hit by any
    scan that is not pinned to a date) with a linear backoff. A successful call
    with no matching rows returns ``[]``; a query the server rejects outright
    raises ``RuntimeError`` with its message.
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.get(_API, params={"q": sql}, timeout=_TIMEOUT)
            r.raise_for_status()
            body = r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last_error = exc
        else:
            status = body.get("query_execution_status")
            if status == "Success":
                return body.get("rows") or []
            message = body.get("query_execution_message", "")
            # The time budget is transient (load-dependent); retry it. Any other
            # rejection (bad SQL, missing table) is permanent, so fail loudly.
            if "deadline exceeded" not in message.lower():
                raise RuntimeError(f"DoltHub query failed: {message}")
            last_error = RuntimeError(f"DoltHub query timed out: {message}")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    assert last_error is not None  # the loop always records a failure before here
    raise last_error


# ── Chain assembly ───────────────────────────────────────────────────────────


def _chain_sql(
    ticker: str,
    snapshot: str,
    asof_ts: pd.Timestamp,
    horizon_days: int,
    spot: float | None,
    strike_window: float,
) -> str:
    """Build the date-pinned chain query for one ticker snapshot.

    Expiries are limited to ``[asof, asof + horizon_days]`` and, when ``spot`` is
    known, strikes to ``+/- strike_window`` of spot, so the payload stays small.
    """
    if not _SYMBOL_RE.match(ticker):
        raise ValueError(f"unsupported ticker symbol: {ticker!r}")
    horizon = (asof_ts + pd.Timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    clauses = [
        f"date = '{snapshot}'",
        f"act_symbol = '{ticker}'",
        f"expiration >= '{asof_ts.strftime('%Y-%m-%d')}'",
        f"expiration <= '{horizon}'",
    ]
    if spot and strike_window:
        clauses.append(f"strike >= {round(spot * (1 - strike_window), 2)}")
        clauses.append(f"strike <= {round(spot * (1 + strike_window), 2)}")
    return (
        "SELECT expiration, strike, call_put, bid, ask, vol "
        "FROM option_chain WHERE " + " AND ".join(clauses)
    )


def _to_chain(rows: list[dict]) -> pd.DataFrame:
    """Map raw ``option_chain`` rows onto the canonical chain schema."""
    df = pd.DataFrame(rows)
    return pd.DataFrame(
        {
            "expiry": pd.to_datetime(df["expiration"]),
            "strike": pd.to_numeric(df["strike"], errors="coerce"),
            # call_put is "Call"/"Put"; the first letter gives the canonical right.
            "right": df["call_put"].str[0].str.upper(),
            "bid": pd.to_numeric(df["bid"], errors="coerce"),
            "ask": pd.to_numeric(df["ask"], errors="coerce"),
            "iv": pd.to_numeric(df["vol"], errors="coerce"),
            "open_interest": np.nan,  # not carried by this dataset
        },
        columns=CHAIN_COLUMNS,
    )


# ── Public chain fetcher ─────────────────────────────────────────────────────


def fetch_option_chain(
    ticker: str,
    asof: str,
    horizon_days: int = 90,
    strike_window: float = 0.20,
    spot: float | None = None,
    lookback_days: int = 5,
) -> pd.DataFrame:
    """ATM-centred option chain for ``ticker`` as of ``asof`` (YYYY-MM-DD).

    Drop-in for ``options.fetch_option_chain`` with the same return schema, but
    backed by the DoltHub historical database. ``iv`` and the bid/ask spread are
    the publisher's own values, not locally inverted. If ``asof`` is not a
    trading day in the dataset (weekend, holiday, or a gap), the snapshot steps
    back up to ``lookback_days`` calendar days to the most recent prior session,
    matching the Alpaca adapter's behaviour.

    Parameters
    ----------
    ticker : str
        Underlying ticker (``act_symbol`` form, e.g. ``AAPL``, ``BRK.B``).
    asof : str
        As-of date (``YYYY-MM-DD``); must fall within dataset coverage
        (~2019 to late 2024).
    horizon_days : int, optional
        Calendar days past ``asof`` to include expiries. Defaults to ``90``.
    strike_window : float, optional
        Half-width of the strike band as a fraction of spot, applied only when
        ``spot`` is given. Defaults to ``0.20``.
    spot : float or None, optional
        Underlying price used to centre the strike band; when ``None`` all
        strikes in the expiry window are returned. Defaults to ``None``.
    lookback_days : int, optional
        Calendar days to step back to find the latest available session on or
        before ``asof``. Defaults to ``5``.

    Returns
    -------
    pandas.DataFrame
        Chain with ``CHAIN_COLUMNS``; ``open_interest`` is NaN. Empty (correctly
        typed) when no session resolves in the lookback window.
    """
    asof_ts = pd.Timestamp(asof)
    for back in range(lookback_days + 1):
        snapshot = (asof_ts - pd.Timedelta(days=back)).strftime("%Y-%m-%d")
        rows = _query(_chain_sql(ticker, snapshot, asof_ts, horizon_days, spot, strike_window))
        if rows:
            return _to_chain(rows)
    return pd.DataFrame(columns=CHAIN_COLUMNS)
