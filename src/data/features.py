"""Per-event feature maths for the strategy dataset.

Pure functions only: each takes already-fetched market data (an option chain,
the underlying price history) and returns numbers. No network access lives
here, so the maths is unit-tested against synthetic chains and then wired to a
live provider in `data_pipeline`.

Option-chain schema (one name, one as-of date):
    expiry (datetime64), strike (float), right ('C'|'P'),
    bid, ask, iv, open_interest

These functions cover everything computable from a chain plus price history.
The remaining fair-move features (eps_dispersion, prior_surprise, oi_growth)
need analyst / historical-snapshot sources that are not wired yet, so the
pipeline fills them as NaN for now.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..engine.greeks import bs_delta

TRADING_DAYS = 252
BACK_MONTH_MIN_GAP_DAYS = 21   # back expiry sits at least ~1 month past front
NAN = float("nan")

# Feature keys this module produces, in dataset order.
FEATURE_KEYS = [
    "implied_move",
    "front_atm_iv",
    "back_atm_iv",
    "iv_term_spread",
    "trailing_rv",
    "skew_25d",
]


def _with_mid(chain: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the chain with a `mid` column from bid/ask.

    Falls back to whichever side is present when one is missing.
    """
    out = chain.copy()
    bid = pd.to_numeric(out["bid"], errors="coerce")
    ask = pd.to_numeric(out["ask"], errors="coerce")
    mid = (bid + ask) / 2
    out["mid"] = mid.where(mid.notna(), ask.fillna(bid))
    return out


def atm_strike(chain: pd.DataFrame, spot: float) -> float:
    """The listed strike closest to spot."""
    strikes = np.sort(pd.to_numeric(chain["strike"], errors="coerce").dropna().unique())
    if strikes.size == 0:
        return NAN
    return float(strikes[np.argmin(np.abs(strikes - spot))])


def nearest_strike(chain: pd.DataFrame, expiry, spot: float) -> float:
    """The strike closest to spot among the rows of one expiry.

    Strike grids differ across expiries (weeklies are sparser), so the ATM
    strike must be chosen per expiry rather than globally - otherwise an exact
    lookup can miss a strike that only some other expiry lists.
    """
    strikes = pd.to_numeric(
        chain.loc[chain["expiry"] == expiry, "strike"], errors="coerce"
    ).dropna().unique()
    if strikes.size == 0:
        return NAN
    strikes = np.sort(strikes)
    return float(strikes[np.argmin(np.abs(strikes - spot))])


def nearest_expiries(chain: pd.DataFrame, announce_date,
                     back_gap_days: int = BACK_MONTH_MIN_GAP_DAYS):
    """(front, back) expiries straddling the announcement.

    Front is the first expiry strictly after the announcement (the front-week
    that prices the event). Back is the first expiry at least `back_gap_days`
    beyond the front, falling back to the latest available expiry. Either may
    be None when the chain does not reach far enough.
    """
    announce = pd.Timestamp(pd.to_datetime(announce_date))
    exps = np.sort(pd.to_datetime(chain["expiry"].unique()))
    after = exps[exps > announce]
    if after.size == 0:
        return None, None
    front = pd.Timestamp(after[0])
    later = exps[exps >= front + pd.Timedelta(days=back_gap_days)]
    if later.size:
        back = pd.Timestamp(later[0])
    else:
        last = pd.Timestamp(exps[-1])
        back = last if last > front else None
    return front, back


def atm_iv(chain: pd.DataFrame, expiry, strike: float) -> float:
    """Mean ATM implied vol (call and put) for one expiry/strike."""
    rows = chain[(chain["expiry"] == expiry) & np.isclose(chain["strike"], strike)]
    iv = pd.to_numeric(rows["iv"], errors="coerce")
    return float(iv.mean()) if iv.notna().any() else NAN


def atm_straddle_mid(chain: pd.DataFrame, expiry, strike: float) -> float:
    """Call mid + put mid at the ATM strike for one expiry."""
    rows = _with_mid(chain)
    rows = rows[(rows["expiry"] == expiry) & np.isclose(rows["strike"], strike)]
    call = rows.loc[rows["right"] == "C", "mid"]
    put = rows.loc[rows["right"] == "P", "mid"]
    if call.empty or put.empty or call.isna().all() or put.isna().all():
        return NAN
    return float(call.iloc[0] + put.iloc[0])


def implied_move(chain: pd.DataFrame, spot: float, expiry, strike: float) -> float:
    """Market-implied event move = ATM straddle mid / spot (a fraction)."""
    if not spot or spot != spot:
        return NAN
    straddle = atm_straddle_mid(chain, expiry, strike)
    return straddle / spot if straddle == straddle else NAN


def realised_vol(price_history: pd.DataFrame, window: int = 20,
                 trading_days: int = TRADING_DAYS) -> float:
    """Annualised trailing realised vol from close-to-close log returns."""
    close = pd.to_numeric(price_history["close"], errors="coerce").dropna()
    rets = np.log(close / close.shift(1)).dropna()
    if rets.size >= window:
        rets = rets.iloc[-window:]
    if rets.size < 2:
        return NAN
    return float(rets.std(ddof=1) * np.sqrt(trading_days))


def skew_25d(chain: pd.DataFrame, expiry, spot: float, t_years: float,
             r: float = 0.0, target: float = 0.25) -> float:
    """25-delta IV skew for one expiry: IV(25d put) - IV(25d call).

    Each option's delta is computed from its own quoted IV, then IV is
    interpolated to the +/-0.25 delta points. Positive means puts are bid up
    relative to calls (the usual equity skew).
    """
    rows = chain[chain["expiry"] == expiry].copy()
    rows["iv"] = pd.to_numeric(rows["iv"], errors="coerce")
    rows = rows.dropna(subset=["iv"])
    if t_years is None or t_years <= 0 or rows.empty:
        return NAN
    rows["delta"] = [
        bs_delta(spot, k, t_years, r, iv, right)
        for k, iv, right in zip(rows["strike"], rows["iv"], rows["right"])
    ]
    calls = rows[rows["right"] == "C"].sort_values("delta")
    puts = rows[rows["right"] == "P"].sort_values("delta")
    if len(calls) < 2 or len(puts) < 2:
        return NAN
    iv_call = np.interp(target, calls["delta"], calls["iv"])
    iv_put = np.interp(-target, puts["delta"], puts["iv"])
    return float(iv_put - iv_call)


def event_features(chain: pd.DataFrame, spot: float, announce_date, asof_date,
                   price_history: pd.DataFrame, r: float = 0.0,
                   rv_window: int = 20) -> dict:
    """Compute the chain/price-derived features for one earnings event.

    Returns a dict keyed by FEATURE_KEYS. Missing inputs yield NaN rather than
    raising, so one thin chain never sinks the whole dataset build.
    """
    blank = {k: NAN for k in FEATURE_KEYS}
    if chain is None or chain.empty:
        blank["trailing_rv"] = realised_vol(price_history, rv_window)
        return blank

    front, back = nearest_expiries(chain, announce_date)
    k_front = nearest_strike(chain, front, spot) if front is not None else NAN
    k_back = nearest_strike(chain, back, spot) if back is not None else NAN
    front_iv = atm_iv(chain, front, k_front) if front is not None else NAN
    back_iv = atm_iv(chain, back, k_back) if back is not None else NAN
    asof = pd.Timestamp(pd.to_datetime(asof_date))
    t_front = (front - asof).days / 365.0 if front is not None else NAN

    spread = front_iv - back_iv if (front_iv == front_iv and back_iv == back_iv) else NAN
    return {
        "implied_move": implied_move(chain, spot, front, k_front) if front is not None else NAN,
        "front_atm_iv": front_iv,
        "back_atm_iv": back_iv,
        "iv_term_spread": spread,
        "trailing_rv": realised_vol(price_history, rv_window),
        "skew_25d": skew_25d(chain, front, spot, t_front, r) if front is not None else NAN,
    }
