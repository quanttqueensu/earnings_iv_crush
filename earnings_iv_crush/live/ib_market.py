"""
ib_market.py
Live underlying price and option-chain snapshot from Interactive Brokers.

The research feature maths (``data.features``) consumes a chain in the canonical
schema ``[expiry, strike, right, bid, ask, iv, open_interest]``. This module
produces exactly that frame from a live IB session, so the same
``event_features`` call computes the gate inputs (``iv_term_spread``,
``skew_25d``, ``implied_move``, ``front_atm_iv``) on live quotes that it computes
on cached history - no second code path for the signal.

Implied vol is taken from IB's own option model (``modelGreeks.impliedVol`` via
``reqTickers``), which is preferable to a local Black-Scholes inversion of a
delayed close. Where the model vol is missing the column is left NaN and the
feature maths degrades to NaN for that contract, exactly as it does on a thin
cached chain.

All IB calls live here and in ``ib_orders``; ``ib_async`` is imported lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..config import LIVE
from ..data.options import CHAIN_COLUMNS

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ib_async import IB, Contract, Option


@dataclass(frozen=True)
class UnderlyingQuote:
    """A qualified underlying and its current price.

    Attributes
    ----------
    contract : ib_async.Contract
        The qualified SMART/USD stock contract (carries the resolved ``conId``).
    spot : float
        Last / close price used to centre the strike band and the ATM strike.
    """

    contract: Contract
    spot: float


def qualify_underlying(ib: IB, ticker: str) -> UnderlyingQuote:
    """Qualify ``ticker`` as a SMART US equity and fetch its current price.

    The price prefers the last trade, then the close, then the midpoint, so it
    resolves whether the market is open (last) or the snapshot is delayed
    (close). Class shares use IB's space form (``BRK B``), matching how IB lists
    them.

    Parameters
    ----------
    ib : ib_async.IB
        A connected client.
    ticker : str
        Underlying symbol (Yahoo-style ``BRK-B`` is translated to ``BRK B``).

    Returns
    -------
    UnderlyingQuote
        The qualified contract and a finite spot.

    Raises
    ------
    ValueError
        If the contract cannot be qualified or no usable price is returned.
    """
    from ib_async import Stock

    symbol = ticker.replace("-", " ")
    qualified = ib.qualifyContracts(Stock(symbol, "SMART", "USD"))
    if not qualified:
        raise ValueError(f"Could not qualify underlying {ticker!r} on IB.")
    contract = qualified[0]

    [tick] = ib.reqTickers(contract)
    spot = _first_finite(tick.last, tick.close, tick.marketPrice())
    if not np.isfinite(spot) or spot <= 0:
        raise ValueError(f"No usable price for {ticker!r} (got {spot!r}).")
    return UnderlyingQuote(contract=contract, spot=float(spot))


def snapshot_chain(
    ib: IB,
    underlying: UnderlyingQuote,
    *,
    horizon_days: int = LIVE.horizon_days,
    strike_window: float = LIVE.strike_window,
) -> pd.DataFrame:
    """Snapshot a strike-windowed option chain into the canonical schema.

    Expiries are limited to within ``horizon_days`` of today and strikes to
    +/-``strike_window`` of spot, to keep the market-data request small (IB caps
    concurrent option lines). The returned frame's ``iv`` is IB's model implied
    vol; ``bid``/``ask`` are the live touches; ``open_interest`` is NaN (IB
    serves it on a separate request not needed for the gates).

    Parameters
    ----------
    ib : ib_async.IB
        A connected client.
    underlying : UnderlyingQuote
        The qualified underlying and spot from :func:`qualify_underlying`.
    horizon_days : int, optional
        Calendar-day expiry horizon. Defaults to ``LiveConfig.horizon_days``.
    strike_window : float, optional
        Strike half-band as a fraction of spot. Defaults to
        ``LiveConfig.strike_window``.

    Returns
    -------
    pd.DataFrame
        Chain with ``CHAIN_COLUMNS``; empty (correctly typed) when no contracts
        resolve.
    """
    from ib_async import Option

    spot = underlying.spot
    params = ib.reqSecDefOptParams(underlying.contract.symbol, "", "STK", underlying.contract.conId)
    smart = [p for p in params if p.exchange == "SMART"] or list(params)
    if not smart:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    today = pd.Timestamp.today().normalize()
    horizon = today + pd.Timedelta(days=horizon_days)
    expiries = sorted(
        {e for p in smart for e in p.expirations if today < pd.Timestamp(e) <= horizon}
    )
    lo, hi = spot * (1 - strike_window), spot * (1 + strike_window)
    strikes = sorted({k for p in smart for k in p.strikes if lo <= k <= hi})
    if not expiries or not strikes:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    contracts = [
        Option(underlying.contract.symbol, expiry, strike, right, "SMART", tradingClass="")
        for expiry in expiries
        for strike in strikes
        for right in ("C", "P")
    ]
    qualified = [c for c in ib.qualifyContracts(*contracts) if getattr(c, "conId", 0)]
    if not qualified:
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    rows = []
    for tick in ib.reqTickers(*qualified):
        con: Option = tick.contract  # type: ignore[assignment]
        iv = tick.modelGreeks.impliedVol if tick.modelGreeks else float("nan")
        rows.append(
            {
                "expiry": pd.Timestamp(con.lastTradeDateOrContractMonth),
                "strike": float(con.strike),
                "right": con.right,
                "bid": _nan_if_missing(tick.bid),
                "ask": _nan_if_missing(tick.ask),
                "iv": float(iv) if iv is not None else float("nan"),
                "open_interest": float("nan"),
            }
        )
    return pd.DataFrame(rows, columns=CHAIN_COLUMNS)


# ── helpers ──────────────────────────────────────────────────────────────────


def _first_finite(*values: float | None) -> float:
    """Return the first finite, present value, else NaN."""
    for v in values:
        if v is not None and np.isfinite(v):
            return float(v)
    return float("nan")


def _nan_if_missing(price: float | None) -> float:
    """IB encodes 'no quote' as -1 or NaN; normalise both to NaN."""
    if price is None or not np.isfinite(price) or price < 0:
        return float("nan")
    return float(price)
