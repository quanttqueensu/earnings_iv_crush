"""
providers.py
Market bundles: the one place that binds a market to its data providers.

The backtest engine is market-agnostic - the term gate, surface maths, cost model
and significance stack all run off the canonical ``options.CHAIN_COLUMNS`` chain
and a ``ticker, announce_date, session`` calendar. A market is therefore just three
fetchers: the option-chain source, the earnings calendar, and the equity spot
series. This module registers those bundles and resolves one by name, so
``run_research`` (and any other entry point) selects a market without scattering
provider ``if`` branches through the run logic.

The universe is US single-name equity options, on the free DoltHub historical chain
(or Alpaca for the 2024+ window) with Yahoo earnings dates and yfinance spot.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from . import dolthub_options, earnings
from .alpaca_options import fetch_option_chain as _alpaca_chain
from .alpaca_options import fetch_underlying_ohlcv as _alpaca_ohlcv

# ── Universes ────────────────────────────────────────────────────────────────

# Liquid US large-caps (the historical DoltHub/Alpaca default).
US_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AMD",
    "NFLX",
    "JPM",
    "BAC",
    "XOM",
    "WMT",
    "DIS",
    "INTC",
    "CRM",
    "QCOM",
    "MU",
]


# ── Market registry ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Market:
    """The provider bundle for one market.

    Attributes
    ----------
    name : str
        Market key (``"us"``).
    chain_source : str
        Chain-provider tag; part of the disk cache key so snapshots from
        different sources never collide.
    fetch_chain : Callable
        ``fetch(ticker, asof, *, strike_window, horizon_days) -> chain`` in the
        canonical schema.
    fetch_earnings : Callable
        ``fetch(tickers, start, end) -> DataFrame[ticker, announce_date, session]``.
    fetch_prices : Callable
        ``fetch(ticker, start, end) -> OHLCV`` for spot.
    default_start : str
        Earliest date the chain source covers (``YYYY-MM-DD``).
    universe : list[str]
        Default ticker set when ``--tickers`` is not given.
    """

    name: str
    chain_source: str
    fetch_chain: Callable[..., pd.DataFrame]
    fetch_earnings: Callable[..., pd.DataFrame]
    fetch_prices: Callable[..., pd.DataFrame]
    default_start: str
    universe: list[str] = field(default_factory=list)


# Chain providers selectable within a market (``--chain-source`` override).
_CHAIN_FETCHERS: dict[str, Callable[..., pd.DataFrame]] = {
    "alpaca": _alpaca_chain,
    "dolthub": dolthub_options.fetch_option_chain,
}

_MARKETS: dict[str, Market] = {
    "us": Market(
        name="us",
        chain_source="dolthub",  # free historical default (2019-2024)
        fetch_chain=dolthub_options.fetch_option_chain,
        fetch_earnings=earnings.fetch_earnings_dates,
        fetch_prices=_alpaca_ohlcv,
        default_start="2019-01-02",
        universe=US_UNIVERSE,
    ),
}


def resolve(market: str, chain_source: str | None = None) -> Market:
    """Resolve a market bundle, optionally overriding its chain provider.

    Parameters
    ----------
    market : str
        Market key (``"us"``).
    chain_source : str or None, optional
        Override the market's default chain provider (``"alpaca"`` or
        ``"dolthub"``). ``None`` keeps the market default.

    Returns
    -------
    Market
        The resolved bundle.
    """
    if market not in _MARKETS:
        raise ValueError(f"unknown market {market!r}; choose from {sorted(_MARKETS)}")
    mkt = _MARKETS[market]
    if chain_source is None or chain_source == mkt.chain_source:
        return mkt
    if chain_source not in _CHAIN_FETCHERS:
        raise ValueError(
            f"unknown chain source {chain_source!r}; choose from {sorted(_CHAIN_FETCHERS)}"
        )
    return Market(
        name=mkt.name,
        chain_source=chain_source,
        fetch_chain=_CHAIN_FETCHERS[chain_source],
        fetch_earnings=mkt.fetch_earnings,
        fetch_prices=mkt.fetch_prices,
        default_start=mkt.default_start,
        universe=mkt.universe,
    )
