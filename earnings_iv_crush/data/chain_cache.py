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
# The geometry each variant name had when its cache entries were first written.
# If VARIANTS is ever changed, chain_key appends the new geometry to the key so
# stale snapshots fetched under the old geometry are never silently served.
_CANONICAL_GEOMETRY: dict[str, tuple[float, int]] = {
    "entry": (0.20, 90),
    "panel": (0.06, 70),
}


def chain_key(ticker: str, asof: str, variant: str, source: str = "alpaca") -> str:
    """Cache key for one chain snapshot.

    ``source`` tags the provider so snapshots from different chain sources (e.g.
    Alpaca vs the NSE bhavcopy) never collide. Defaults to ``"alpaca"`` so keys
    written before the source tag existed still resolve. If the variant's
    geometry has drifted from the canonical values its existing cache was
    built under, the key carries the live geometry so old snapshots miss.
    """
    geometry = VARIANTS.get(variant)
    tag = ""
    if geometry is not None and geometry != _CANONICAL_GEOMETRY.get(variant):
        tag = f"_w{geometry[0]}_h{geometry[1]}"
    return f"{source}_chain_{variant}{tag}_{ticker}_{asof}"


def cached_chain_fetcher(
    variant: str = "entry",
    cache_dir=None,
    fetch=None,
    source: str = "alpaca",
    refresh_empty: bool = False,
):
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
        signature; injectable for testing. Defaults to Alpaca.
    source : str, optional
        Provider tag for the cache key (e.g. ``"dolthub"``, ``"nse"``), so
        snapshots from different sources are cached separately. Defaults to
        ``"alpaca"``.
    refresh_empty : bool, optional
        Treat cached EMPTY snapshots as misses and refetch them. An empty
        sentinel written during a transient provider outage is otherwise
        permanent silent data loss; run one pass with this on to heal the
        cache. Defaults to ``False`` (rate-limit friendly).

    Returns
    -------
    callable
        ``fetch_chain(ticker, asof) -> chain`` with the canonical schema. The
        returned callable exposes ``empty_served`` — how many cached empty
        sentinels it handed out — so callers can surface the potential loss.
    """
    strike_window, horizon_days = VARIANTS[variant]
    fetch = fetch or alpaca_options.fetch_option_chain
    kwargs = {} if cache_dir is None else {"cache_dir": cache_dir}

    def fetch_chain(ticker: str, asof: str) -> pd.DataFrame:
        key = chain_key(ticker, asof, variant, source)
        if cache.has_frame(key, **kwargs):
            df = cache.read_frame(key, **kwargs)
            if not df.empty:
                df["expiry"] = pd.to_datetime(df["expiry"])  # CSV fallback safety
                return df
            if not refresh_empty:
                fetch_chain.empty_served += 1  # type: ignore[attr-defined]
                return df
        df = fetch(ticker, asof, strike_window=strike_window, horizon_days=horizon_days)
        if df is None:
            df = pd.DataFrame(columns=CHAIN_COLUMNS)
        cache.write_frame(df, key, **kwargs)  # empty frames cached as sentinels
        return df

    fetch_chain.empty_served = 0  # type: ignore[attr-defined]
    return fetch_chain
