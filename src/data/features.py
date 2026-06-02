"""
features.py
Per-event feature maths for the strategy dataset.

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

from ..config import GLOBAL
from ..engine.greeks import bs_delta

# Sourced from the central config (see ``src/config.py``).
TRADING_DAYS = GLOBAL.trading_days_per_year
BACK_MONTH_MIN_GAP_DAYS = GLOBAL.back_month_min_gap_days   # back expiry ~1 month past front
NAN = float("nan")

# np.trapz was renamed np.trapezoid in NumPy 2.0; support both.
_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))

# Feature keys this module produces, in dataset order.
FEATURE_KEYS = [
    "implied_move",
    "front_atm_iv",
    "back_atm_iv",
    "iv_term_spread",
    "trailing_rv",
    "skew_25d",
    "vol_premium",            # front ATM IV - trailing RV (Goyal & Saretto 2009)
    "variance_risk_premium",  # front ATM IV^2 - trailing RV^2 (Bollerslev-Tauchen-Zhou 2009)
    "bkm_skew",               # model-free risk-neutral skew (Bakshi-Kapadia-Madan 2003)
    "bkm_kurt",               # model-free risk-neutral kurtosis (BKM 2003)
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


def volatility_premium(front_iv: float, trailing_rv: float) -> float:
    """Goyal & Saretto (2009) volatility deviation: front ATM IV minus trailing RV.

    A large positive value means options are priced above recently realised
    volatility, which tends to mean-revert and is a short-vol signal.
    """
    if front_iv != front_iv or trailing_rv != trailing_rv:
        return NAN
    return float(front_iv - trailing_rv)


def variance_risk_premium(front_iv: float, trailing_rv: float) -> float:
    """Bollerslev-Tauchen-Zhou (2009) variance risk premium: IV^2 minus RV^2.

    The compensation embedded in option prices for bearing variance risk, in
    annualised variance units. Positive for the typical short-vol earnings setup.
    """
    if front_iv != front_iv or trailing_rv != trailing_rv:
        return NAN
    return float(front_iv ** 2 - trailing_rv ** 2)


def bkm_moments(chain: pd.DataFrame, expiry, spot: float, t_years: float,
                r: float = 0.0) -> dict:
    """Model-free risk-neutral variance, skew and kurtosis (Bakshi-Kapadia-Madan 2003).

    Builds the volatility, cubic and quartic "contracts" by integrating
    out-of-the-money option prices (puts below spot, calls at/above spot) against
    the BKM weighting kernels, then forms the risk-neutral moments. Equity
    index/single-name distributions are typically left-skewed, so ``bkm_skew`` is
    usually negative.

    Parameters
    ----------
    chain : pd.DataFrame
        Option chain (needs ``expiry``, ``strike``, ``right``, ``bid``, ``ask``).
    expiry :
        The expiry to evaluate.
    spot : float
        Underlying price (USD).
    t_years : float
        Time to expiry in years.
    r : float
        Risk-free rate (annualised, continuously compounded). Defaults to ``0``.

    Returns
    -------
    dict
        ``bkm_var``, ``bkm_skew`` and ``bkm_kurt``. All ``nan`` when the OTM
        cross-section is too thin (fewer than two strikes on either side) or the
        implied variance is non-positive.
    """
    nan_out = {"bkm_var": NAN, "bkm_skew": NAN, "bkm_kurt": NAN}
    if t_years is None or t_years <= 0 or spot <= 0:
        return nan_out
    rows = _with_mid(chain[chain["expiry"] == expiry])
    if rows.empty:
        return nan_out

    puts = rows[(rows["right"] == "P") & (rows["strike"] < spot)]
    calls = rows[(rows["right"] == "C") & (rows["strike"] >= spot)]
    puts = puts.dropna(subset=["mid"]).sort_values("strike")
    calls = calls.dropna(subset=["mid"]).sort_values("strike")
    if len(puts) < 2 or len(calls) < 2:
        return nan_out

    strikes = np.concatenate([puts["strike"].to_numpy(float),
                              calls["strike"].to_numpy(float)])
    prices = np.concatenate([puts["mid"].to_numpy(float),
                             calls["mid"].to_numpy(float)])
    order = np.argsort(strikes)
    strikes, prices = strikes[order], prices[order]

    u = np.log(strikes / spot)
    g_v = 2.0 * (1.0 - u) / strikes ** 2
    g_w = (6.0 * u - 3.0 * u ** 2) / strikes ** 2
    g_x = (12.0 * u ** 2 - 4.0 * u ** 3) / strikes ** 2

    v = float(_trapz(g_v * prices, strikes))
    w = float(_trapz(g_w * prices, strikes))
    x = float(_trapz(g_x * prices, strikes))

    er = np.exp(r * t_years)
    mu = er - 1.0 - er / 2.0 * v - er / 6.0 * w - er / 24.0 * x
    var = er * v - mu ** 2
    if not np.isfinite(var) or var <= 0:
        return nan_out
    skew = (er * w - 3.0 * mu * er * v + 2.0 * mu ** 3) / var ** 1.5
    kurt = (er * x - 4.0 * mu * er * w + 6.0 * er * mu ** 2 * v - 3.0 * mu ** 4) / var ** 2
    return {"bkm_var": float(var), "bkm_skew": float(skew), "bkm_kurt": float(kurt)}


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
    trailing = realised_vol(price_history, rv_window)
    bkm = bkm_moments(chain, front, spot, t_front, r) if front is not None else \
        {"bkm_skew": NAN, "bkm_kurt": NAN}
    return {
        "implied_move": implied_move(chain, spot, front, k_front) if front is not None else NAN,
        "front_atm_iv": front_iv,
        "back_atm_iv": back_iv,
        "iv_term_spread": spread,
        "trailing_rv": trailing,
        "skew_25d": skew_25d(chain, front, spot, t_front, r) if front is not None else NAN,
        "vol_premium": volatility_premium(front_iv, trailing),
        "variance_risk_premium": variance_risk_premium(front_iv, trailing),
        "bkm_skew": bkm["bkm_skew"],
        "bkm_kurt": bkm["bkm_kurt"],
    }
