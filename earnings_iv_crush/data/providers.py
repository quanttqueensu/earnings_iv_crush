"""
providers.py
Market bundles: the one place that binds a market to its free data providers.

The backtest engine is market-agnostic - the term gate, surface maths, cost model
and significance stack all run off the canonical ``options.CHAIN_COLUMNS`` chain
and a ``ticker, announce_date, session`` calendar. So adding a market is just
choosing three fetchers: the option-chain source, the earnings calendar, and the
equity spot series. This module registers those bundles and resolves one by name,
so ``run_research`` (and any other entry point) selects a market without scattering
provider ``if`` branches through the run logic.

US runs on the free DoltHub historical chain (or Alpaca for the 2024+ window) with
Yahoo earnings dates and yfinance spot. India runs on the free NSE UDiFF F&O
bhavcopy (``nse_options``) with Yahoo earnings dates and yfinance spot, both keyed
by the ``.NS`` suffix that ``nse_options`` does not use - so the India wrappers add
``.NS`` for the Yahoo/price calls and strip it back to the bare bhavcopy symbol the
chain adapter expects.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from . import b3_options, dolthub_options, earnings, nse_options
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

# Liquid NSE F&O single names (bhavcopy ``TckrSymb`` form). A curated, high-OI
# subset of the F&O list - deep enough for a term-spread signal test without the
# noise of the thin tail. Expand with --tickers for the full F&O universe.
NSE_FO_UNIVERSE = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "AXISBANK",
    "KOTAKBANK",
    "ITC",
    "LT",
    "BHARTIARTL",
    "HINDUNILVR",
    "BAJFINANCE",
    "MARUTI",
    "SUNPHARMA",
    "TATAMOTORS",
    "TATASTEEL",
    "WIPRO",
    "HCLTECH",
    "ONGC",
    "NTPC",
    "POWERGRID",
    "ULTRACEMCO",
    "TITAN",
    "ASIANPAINT",
    "ADANIENT",
    "ADANIPORTS",
    "JSWSTEEL",
    "COALINDIA",
    "GRASIM",
    "HINDALCO",
    "BAJAJFINSV",
    "TECHM",
    "NESTLEIND",
    "DRREDDY",
    "CIPLA",
    "BRITANNIA",
    "EICHERMOT",
    "HEROMOTOCO",
    "BPCL",
    "M&M",
    "BAJAJ-AUTO",
    "SBILIFE",
    "HDFCLIFE",
]

# Liquid B3 single names carrying stock options (cash-equity ticker form). The
# tradeable option cross-section in Brazil is concentrated in the first handful;
# this curated set is the deep end. See b3_options for the concentration caveat.
BRAZIL_UNIVERSE = [
    "PETR4",
    "VALE3",
    "ITUB4",
    "BBAS3",
    "BBDC4",
    "MGLU3",
    "JBSS3",
    "ABEV3",
    "B3SA3",
    "LREN3",
    "CSAN3",
    "WEGE3",
    "SUZB3",
    "PRIO3",
    "RENT3",
    "GGBR4",
    "ELET3",
    "EQTL3",
    "RADL3",
    "HAPV3",
    "CMIG4",
    "USIM5",
    "CSNA3",
    "ITSA4",
    "RAIL3",
    "RDOR3",
    "NTCO3",
]


def india_full_universe(cache_dir: str | None = None) -> list[str]:
    """The full current NSE single-stock-option universe (~180 names).

    Derived from the latest bhavcopy via ``nse_options.fo_underlyings`` so it is
    always current; falls back to the curated ``NSE_FO_UNIVERSE`` if the session
    file cannot be resolved (e.g. offline).
    """
    names = nse_options.fo_underlyings(cache_dir=cache_dir)
    return names or NSE_FO_UNIVERSE


# ── India provider wrappers (.NS suffix reconciliation) ──────────────────────


def _to_ns(ticker: str) -> str:
    """Bare NSE symbol -> Yahoo ``.NS`` symbol (idempotent)."""
    return ticker if ticker.endswith(".NS") else f"{ticker}.NS"


def _from_ns(ticker: str) -> str:
    """Yahoo ``.NS`` symbol -> bare NSE symbol (the bhavcopy ``TckrSymb`` form)."""
    return ticker[:-3] if ticker.endswith(".NS") else ticker


def nse_earnings_dates(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Yahoo earnings dates for NSE names, returned in bare-symbol form.

    Adds ``.NS`` for the Yahoo lookup, then strips it so the ``ticker`` column
    matches the bhavcopy symbol the chain adapter keys on.
    """
    cal = earnings.fetch_earnings_dates([_to_ns(t) for t in tickers], start, end)
    if cal is not None and not cal.empty:
        cal = cal.copy()
        cal["ticker"] = cal["ticker"].map(_from_ns)
    return cal


# ── Brazil provider wrappers (.SA suffix reconciliation) ─────────────────────


def _to_sa(ticker: str) -> str:
    """Bare B3 ticker -> Yahoo ``.SA`` symbol (idempotent)."""
    return ticker if ticker.endswith(".SA") else f"{ticker}.SA"


def _from_sa(ticker: str) -> str:
    """Yahoo ``.SA`` symbol -> bare B3 ticker (the COTAHIST form)."""
    return ticker[:-3] if ticker.endswith(".SA") else ticker


def b3_earnings_dates(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Yahoo earnings dates for B3 names, returned in bare-ticker (COTAHIST) form."""
    cal = earnings.fetch_earnings_dates([_to_sa(t) for t in tickers], start, end)
    if cal is not None and not cal.empty:
        cal = cal.copy()
        cal["ticker"] = cal["ticker"].map(_from_sa)
    return cal


# ── Market registry ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Market:
    """The provider bundle for one market.

    Attributes
    ----------
    name : str
        Market key (``"us"`` or ``"india"``).
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
    "nse": nse_options.fetch_option_chain,
    "b3": b3_options.fetch_option_chain,
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
    "india": Market(
        name="india",
        chain_source="nse",
        fetch_chain=nse_options.fetch_option_chain,
        fetch_earnings=nse_earnings_dates,
        fetch_prices=nse_options.fetch_underlying_ohlcv,
        default_start="2024-07-08",  # first UDiFF session
        universe=NSE_FO_UNIVERSE,
    ),
    "brazil": Market(
        name="brazil",
        chain_source="b3",
        fetch_chain=b3_options.fetch_option_chain,
        fetch_earnings=b3_earnings_dates,
        fetch_prices=b3_options.fetch_underlying_ohlcv,
        default_start="2025-01-02",  # reliable daily COTAHIST coverage window
        universe=BRAZIL_UNIVERSE,
    ),
}


def resolve(market: str, chain_source: str | None = None) -> Market:
    """Resolve a market bundle, optionally overriding its chain provider.

    Parameters
    ----------
    market : str
        Market key (``"us"`` or ``"india"``).
    chain_source : str or None, optional
        Override the market's default chain provider (``"alpaca"``,
        ``"dolthub"`` or ``"nse"``). ``None`` keeps the market default.

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
