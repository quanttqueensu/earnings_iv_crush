"""
chain_cache.py
Disk-cached wrapper around the Alpaca historical chain fetcher.

The real backtest needs tens of thousands of (ticker, date) chain snapshots
and Alpaca's free tier is rate-limited, so every snapshot is cached to the
git-ignored ``data/processed`` tree on first fetch — including empty results,
which are written as sentinel frames so a name with no chain that day is not
re-fetched on every run.

Two variants exist because the entry/exit snapshots need the full ATM
neighbourhood (strike window 0.20, 90-day horizon) while the term-panel
trailing days only need the front/back ATM IVs (window 0.06, 70-day horizon,
matching ``term_panel``'s defaults). The variant is part of the cache key.
"""

from __future__ import annotations

import pandas as pd

from . import alpaca_options, cache
from .options import CHAIN_COLUMNS

# Per-variant fetch parameters: (strike_window, horizon_days).
VARIANTS: dict[str, tuple[float, int]] = {
    "entry": (0.20, 90),
    "panel": (0.06, 70),
}


def chain_key(ticker: str, asof: str, variant: str) -> str:
    """Cache key for one chain snapshot."""
    return f"alpaca_chain_{variant}_{ticker}_{asof}"


def cached_chain_fetcher(variant: str = "entry", cache_dir=None, fetch=None):
    """Return a ``fetch_chain(ticker, asof)`` that caches every snapshot.

    Parameters
    ----------
    variant : str
        ``"entry"`` (full ATM neighbourhood) or ``"panel"`` (tight window for
        the term spread). Part of the cache key.
    cache_dir : str or Path, optional
        Cache root; defaults to ``cache.DEFAULT_CACHE_DIR``.
    fetch : callable, optional
        Underlying fetcher with the ``alpaca_options.fetch_option_chain``
        signature; injectable for testing.

    Returns
    -------
    callable
        ``fetch_chain(ticker, asof) -> chain`` with the canonical schema.
    """
    strike_window, horizon_days = VARIANTS[variant]
    fetch = fetch or alpaca_options.fetch_option_chain
    kwargs = {} if cache_dir is None else {"cache_dir": cache_dir}

    def fetch_chain(ticker: str, asof: str) -> pd.DataFrame:
        key = chain_key(ticker, asof, variant)
        if cache.has_frame(key, **kwargs):
            df = cache.read_frame(key, **kwargs)
            if not df.empty:
                df["expiry"] = pd.to_datetime(df["expiry"])  # CSV fallback safety
            return df
        df = fetch(ticker, asof, strike_window=strike_window, horizon_days=horizon_days)
        if df is None:
            df = pd.DataFrame(columns=CHAIN_COLUMNS)
        cache.write_frame(df, key, **kwargs)  # empty frames cached as sentinels
        return df

    return fetch_chain
