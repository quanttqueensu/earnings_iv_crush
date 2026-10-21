"""
hedged_hold.py
Delta-hedged short straddles held to expiry, the HAR-RV forecast and the two-expiry jump split.

Shared machinery for the 2026-10-20 studies (``research/timing/2026-10-20-hedged-hold/`` and its
siblings under ``research/selection/``). Everything here is a pure function of arrays already
loaded by the caller, so it is tested offline on synthetic paths and chains.

The valuation convention matches ``engine/pnl.py``: Black-Scholes with the project's zero rate,
times in years on ACT/365, prices per share. The chain is priced off the parity forward rather
than spot, which absorbs dividends and borrow without modelling them.

The jump split follows the calendar-cost study (``research/execution/research_calendar_cost.py``):
with total implied variance ``V_x = sigma_x^2 T_x`` on two expiries that both hold the event and a
flat diffusive variance between them, the diffusive rate is ``(V2 - V1) / (T2 - T1)`` and the
announcement jump variance is what remains of ``V1``.

References
----------
Corsi, F. (2009). A Simple Approximate Long-Memory Model of Realized Volatility. *Journal of
Financial Econometrics* 7(2), 174-196.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option Pricing of Earnings
Announcement Risks. *Review of Financial Studies* 32(2), 646-687.
Bakshi, G. and Kapadia, N. (2003). Delta-Hedged Gains and the Negative Market Volatility Risk
Premium. *Review of Financial Studies* 16(2), 527-566.
Cao, J. and Han, B. (2013). Cross Section of Option Returns and Idiosyncratic Stock Volatility.
*Journal of Financial Economics* 108(1), 231-249.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from earnings_iv_crush.config import HEDGED, HedgedHoldConfig

# ── chain helpers ────────────────────────────────────────────────────────────

_IV_BRACKET = (1e-4, 5.0)  # decimal vol; above 500% the quote is not an option price


def straddle_value(fwd: float, strike: float, t: float, sigma: float) -> float:
    """Black-Scholes straddle per share on the forward, zero rate."""
    if t <= 0 or sigma <= 0:
        return abs(fwd - strike)
    sd = sigma * np.sqrt(t)
    d1 = (np.log(fwd / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    call = fwd * norm.cdf(d1) - strike * norm.cdf(d2)
    put = strike * norm.cdf(-d2) - fwd * norm.cdf(-d1)
    return float(call + put)


def straddle_delta(spot: float, strike: float, t: float, sigma: float) -> float:
    """Delta of a long straddle, ``2 N(d1) - 1``; at expiry the sign of the moneyness."""
    if t <= 0 or sigma <= 0:
        return float(np.sign(spot - strike))
    sd = sigma * np.sqrt(t)
    d1 = (np.log(spot / strike) + 0.5 * sd * sd) / sd
    return float(2.0 * norm.cdf(d1) - 1.0)


def straddle_vega(spot: float, strike: float, t: float, sigma: float) -> float:
    """Vega of a long straddle per share, for one volatility point (0.01)."""
    if t <= 0 or sigma <= 0:
        return 0.0
    sd = sigma * np.sqrt(t)
    d1 = (np.log(spot / strike) + 0.5 * sd * sd) / sd
    return float(2.0 * spot * norm.pdf(d1) * np.sqrt(t) * 0.01)


def option_iv(price: float, fwd: float, strike: float, t: float, right: str) -> float:
    """Implied vol of one option on the forward, or NaN outside the no-arbitrage range."""
    if not (price > 0 and fwd > 0 and strike > 0 and t > 0):
        return float("nan")

    def value(s: float) -> float:
        sd = s * np.sqrt(t)
        d1 = (np.log(fwd / strike) + 0.5 * sd * sd) / sd
        d2 = d1 - sd
        if right == "C":
            return float(fwd * norm.cdf(d1) - strike * norm.cdf(d2))
        return float(strike * norm.cdf(-d2) - fwd * norm.cdf(-d1))

    lo, hi = _IV_BRACKET
    f_lo, f_hi = value(lo) - price, value(hi) - price
    if f_lo * f_hi > 0:
        return float("nan")
    return float(brentq(lambda s: value(s) - price, lo, hi, xtol=1e-8, maxiter=200))


def straddle_iv(price: float, fwd: float, strike: float, t: float) -> float:
    """Implied vol of a straddle mid on the forward, or NaN when the price is not bracketed."""
    if not (price > 0 and fwd > 0 and strike > 0 and t > 0):
        return float("nan")
    lo, hi = _IV_BRACKET
    f_lo = straddle_value(fwd, strike, t, lo) - price
    f_hi = straddle_value(fwd, strike, t, hi) - price
    if f_lo * f_hi > 0:
        return float("nan")
    return float(
        brentq(lambda s: straddle_value(fwd, strike, t, s) - price, lo, hi, xtol=1e-8, maxiter=200)
    )


@dataclass(frozen=True)
class AtmQuote:
    """The at-the-money straddle on one expiry, as the strategy would trade it."""

    expiry: pd.Timestamp
    t: float
    fwd: float
    strike: float
    bid: float
    mid: float
    ask: float
    iv: float


def year_frac(start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Calendar days over 365 (ACT/365)."""
    return float((pd.Timestamp(end).normalize() - pd.Timestamp(start).normalize()).days) / 365.0


def atm_quote(chain: pd.DataFrame, expiry: pd.Timestamp, asof: pd.Timestamp) -> AtmQuote | None:
    """Parity forward, strike nearest it with both legs quoted, and the straddle's touch.

    ``chain`` is the output of ``chains._parse_chain`` (columns ``strike``, ``expiry``,
    ``right``, ``bid_px_00``, ``ask_px_00``, ``mid``; every row two-sided). Returns None when
    the expiry has no strike with both legs.
    """
    d = chain[chain["expiry"] == expiry]
    cols = ["strike", "bid_px_00", "ask_px_00", "mid"]
    calls = d[d["right"] == "C"][cols].to_numpy(float)
    puts = d[d["right"] == "P"][cols].to_numpy(float)
    strikes, ci, pi = np.intersect1d(calls[:, 0], puts[:, 0], return_indices=True)
    if not strikes.size:
        return None
    c, p = calls[ci], puts[pi]
    i0 = int(np.argmin(np.abs(c[:, 3] - p[:, 3])))
    fwd = float(strikes[i0] + c[i0, 3] - p[i0, 3])
    if fwd <= 0:
        return None
    i = int(np.argmin(np.abs(strikes - fwd)))
    k = float(strikes[i])
    t = year_frac(asof, expiry)
    if t <= 0:
        return None
    bid = float(c[i, 1] + p[i, 1])
    ask = float(c[i, 2] + p[i, 2])
    mid = float(c[i, 3] + p[i, 3])
    return AtmQuote(
        expiry=pd.Timestamp(expiry),
        t=t,
        fwd=fwd,
        strike=k,
        bid=bid,
        mid=mid,
        ask=ask,
        iv=straddle_iv(mid, fwd, k, t),
    )


def pick_expiry(
    expiries: Sequence[pd.Timestamp],
    asof: pd.Timestamp,
    dte: tuple[int, int],
    not_before: pd.Timestamp | None = None,
) -> pd.Timestamp | None:
    """Shortest expiry with ``dte[0] <= days <= dte[1]``, expiring on or after ``not_before``."""
    lo, hi = dte
    best = None
    for e in sorted(pd.Timestamp(x) for x in expiries):
        days = (e.normalize() - pd.Timestamp(asof).normalize()).days
        if not_before is not None and e.normalize() < pd.Timestamp(not_before).normalize():
            continue
        if lo <= days <= hi:
            best = e
            break
    return best


def put_skew(
    chain: pd.DataFrame, quote: AtmQuote, target_delta: float = HEDGED.put_delta_target
) -> float:
    """Implied vol of the put nearest ``target_delta`` minus the straddle's ATM vol."""
    d = chain[(chain["expiry"] == quote.expiry) & (chain["right"] == "P")]
    best, best_gap = float("nan"), np.inf
    for k, mid in zip(d["strike"].to_numpy(float), d["mid"].to_numpy(float), strict=True):
        iv = option_iv(mid, quote.fwd, k, quote.t, "P")
        if not np.isfinite(iv):
            continue
        sd = iv * np.sqrt(quote.t)
        delta = float(norm.cdf((np.log(quote.fwd / k) + 0.5 * sd * sd) / sd) - 1.0)
        gap = abs(delta - target_delta)
        if gap < best_gap:
            best, best_gap = iv, gap
    return float(best - quote.iv) if np.isfinite(best) else float("nan")


# ── jump split ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class JumpSplit:
    """Diffusive variance rate and announcement jump variance from two expiries."""

    diffusive_var: float
    jump_var: float

    @property
    def valid(self) -> bool:
        return bool(self.diffusive_var > 0 and self.jump_var >= 0)

    @property
    def diffusive_vol(self) -> float:
        return float(np.sqrt(self.diffusive_var)) if self.diffusive_var > 0 else float("nan")

    @property
    def jump_vol(self) -> float:
        return float(np.sqrt(self.jump_var)) if self.jump_var >= 0 else float("nan")


def split_jump_variance(iv1: float, t1: float, iv2: float, t2: float) -> JumpSplit:
    """Two-expiry split: ``sd2 = (V2 - V1) / (T2 - T1)``, ``J = V1 - sd2 T1``.

    Raises
    ------
    ValueError
        If the second expiry is not later than the first.
    """
    if not t2 > t1:
        raise ValueError(f"second expiry must be later ({t2} <= {t1})")
    v1, v2 = iv1 * iv1 * t1, iv2 * iv2 * t2
    sd2 = (v2 - v1) / (t2 - t1)
    return JumpSplit(diffusive_var=float(sd2), jump_var=float(v1 - sd2 * t1))


# ── HAR-RV ───────────────────────────────────────────────────────────────────


def _har_design(rv: np.ndarray, lags: tuple[int, int, int]) -> np.ndarray:
    """Columns: daily RV, weekly mean, monthly mean, each ending at row t (NaN-aware)."""
    s = pd.Series(rv)
    d_lag, w_lag, m_lag = lags
    daily = s.rolling(d_lag, min_periods=d_lag).mean()
    weekly = s.rolling(w_lag, min_periods=max(1, w_lag - 1)).mean()
    monthly = s.rolling(m_lag, min_periods=max(1, int(0.8 * m_lag))).mean()
    return np.column_stack([daily.to_numpy(), weekly.to_numpy(), monthly.to_numpy()])


def har_fit(rv: np.ndarray, lags: tuple[int, int, int] = HEDGED.har_lags) -> tuple[np.ndarray, int]:
    """OLS of ``RV_{t+1}`` on a constant and the three HAR regressors at ``t``.

    Rows with any missing regressor or target are dropped (excluded announcement days are
    NaN). Returns the coefficients ``(b0, bd, bw, bm)`` and the number of rows used.
    """
    x = _har_design(np.asarray(rv, dtype=float), lags)
    y = np.asarray(rv, dtype=float)[1:]
    x = x[:-1]
    ok = np.isfinite(y) & np.isfinite(x).all(axis=1)
    if ok.sum() < 4:
        return np.full(4, np.nan), int(ok.sum())
    a = np.column_stack([np.ones(ok.sum()), x[ok]])
    coef, *_ = np.linalg.lstsq(a, y[ok], rcond=None)
    return coef, int(ok.sum())


def har_forecast_sum(
    rv: np.ndarray, coef: np.ndarray, h: int, lags: tuple[int, int, int] = HEDGED.har_lags
) -> float:
    """Sum of the iterated one-step HAR forecasts over the next ``h`` days.

    Missing history at the origin (an excluded announcement day) is filled by the mean of the
    finite values in the same window, so the forecast does not inherit the event day.
    """
    hist = [float(v) for v in np.asarray(rv, dtype=float)[-lags[2] :]]
    total = 0.0
    for _ in range(int(h)):
        arr = np.asarray(hist, dtype=float)
        month = np.nanmean(arr[-lags[2] :])
        week = np.nanmean(arr[-lags[1] :])
        day = arr[-1] if np.isfinite(arr[-1]) else week
        f = float(coef[0] + coef[1] * day + coef[2] * week + coef[3] * month)
        f = max(f, 0.0)
        total += f
        hist.append(f)
    return total


def har_annual_variance(
    log_returns: np.ndarray,
    h: int,
    cfg: HedgedHoldConfig = HEDGED,
) -> float:
    """HAR forecast of annualised variance over the next ``h`` trading days, or NaN.

    ``log_returns`` holds strictly pre-decision daily log returns with excluded days as NaN.
    NaN when fewer than ``cfg.har_min_rows`` complete rows exist or the fit is degenerate.
    """
    if h <= 0:
        return float("nan")
    rv = np.asarray(log_returns, dtype=float) ** 2
    coef, n = har_fit(rv, cfg.har_lags)
    if n < cfg.har_min_rows or not np.isfinite(coef).all():
        return float("nan")
    return har_forecast_sum(rv, coef, h, cfg.har_lags) / h * 252.0


# ── jump forecast ────────────────────────────────────────────────────────────


def jump_forecast(prior_moves: Sequence[float], cfg: HedgedHoldConfig = HEDGED) -> float:
    """HAR-style RMS of prior announcement moves, most recent last; NaN if too few."""
    r = np.asarray(prior_moves, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < cfg.jump_hist_min:
        return float("nan")
    sq = r * r
    parts = [sq[-w:].mean() for w in cfg.jump_hist_windows]
    return float(np.sqrt(np.mean(parts)))


# ── hedged hold to expiry ────────────────────────────────────────────────────


@dataclass(frozen=True)
class HedgedResult:
    """Per-share outcome of one hedged short straddle held to expiry."""

    net_pnl: float
    gross_pnl_mid: float
    margin: float
    hedge_pnl: float
    equity_cost: float
    settlement: float
    max_hedge_notional: float

    @property
    def net_rom(self) -> float:
        return self.net_pnl / self.margin


def hedged_short_straddle(
    *,
    sale_price: float,
    sale_mid: float,
    strike: float,
    fwd: float,
    closes: np.ndarray,
    rets: np.ndarray,
    taus: np.ndarray,
    sigmas: np.ndarray,
    half_spreads: np.ndarray,
    settle_close: float,
    hedge: bool = True,
    cfg: HedgedHoldConfig = HEDGED,
) -> HedgedResult:
    """Short one straddle per share at ``sale_price``, hedge at each close, settle at intrinsic.

    Parameters
    ----------
    closes, taus, sigmas, half_spreads : array, length n
        Close, years to expiry, hedge volatility and per-side equity half-spread (fraction) at
        each hedging close, the first being the entry date's close.
    rets : array, length n
        Total return from close i to the next close; the last element is the return into the
        settlement close.
    settle_close : float
        Unadjusted close on the expiry date (or the last session before it).
    hedge : bool
        False holds the straddle naked, the case that reconciles to ``engine.pnl.build_trade``.

    Notes
    -----
    The hedge holds ``+delta`` shares against the short straddle's ``-delta``. Its P&L uses
    total returns, so dividends paid during the hold accrue to the hedge. Each change in the
    hedge pays the half-spread, floored at ``cfg.equity_cost_floor_bps``; the hedge is
    unwound at the settlement close.
    """
    n = len(closes)
    if not (len(rets) == len(taus) == len(sigmas) == len(half_spreads) == n) or n == 0:
        raise ValueError("path arrays must be non-empty and the same length")
    floor = cfg.equity_cost_floor_bps / 1e4
    hs = np.maximum(np.asarray(half_spreads, dtype=float), floor)
    h_prev, hedge_pnl, cost, max_notional = 0.0, 0.0, 0.0, 0.0
    for i in range(n):
        h = straddle_delta(closes[i], strike, taus[i], sigmas[i]) if hedge else 0.0
        cost += abs(h - h_prev) * closes[i] * hs[i]
        hedge_pnl += h * closes[i] * rets[i]
        max_notional = max(max_notional, abs(h) * closes[i])
        h_prev = h
    cost += abs(h_prev) * settle_close * hs[-1]
    settlement = abs(settle_close - strike)
    disposal = cfg.disposal_bps / 1e4 * settle_close if settlement > 0 else 0.0
    fees = 2.0 * cfg.fee_per_contract_leg / 100.0
    net = sale_price - settlement + hedge_pnl - cost - fees - disposal
    gross_mid = sale_mid - settlement + hedge_pnl
    margin = 0.20 * fwd + sale_price + cfg.hedge_margin_frac * max_notional
    return HedgedResult(
        net_pnl=float(net),
        gross_pnl_mid=float(gross_mid),
        margin=float(margin),
        hedge_pnl=float(hedge_pnl),
        equity_cost=float(cost),
        settlement=float(settlement),
        max_hedge_notional=float(max_notional),
    )


# ── causal sorts and paired intervals ────────────────────────────────────────


def causal_bins(
    values: Sequence[float] | np.ndarray,
    dates: Sequence[object] | np.ndarray | pd.Series,
    n_bins: int,
    min_prior: int,
) -> np.ndarray:
    """Bin index 0..n_bins-1 from breakpoints of strictly earlier events; -1 if unassigned.

    Events on the same date share breakpoints built only from earlier dates, so no event
    contributes to its own cut. Prints how many events were left unassigned.
    """
    v = np.asarray(values, dtype=float)
    d = pd.to_datetime(pd.Series(np.asarray(dates))).dt.normalize().to_numpy()
    out = np.full(v.size, -1, dtype=int)
    order = np.argsort(d, kind="stable")
    qs = np.linspace(0, 1, n_bins + 1)[1:-1]
    seen: list[float] = []
    i = 0
    while i < order.size:
        j = i
        while j < order.size and d[order[j]] == d[order[i]]:
            j += 1
        idx = order[i:j]
        if len(seen) >= min_prior:
            cuts = np.quantile(np.asarray(seen), qs)
            for k in idx:
                if np.isfinite(v[k]):
                    out[k] = int(np.searchsorted(cuts, v[k], side="right"))
        seen.extend(float(x) for x in v[idx] if np.isfinite(x))
        i = j
    n_un = int((out < 0).sum())
    if n_un:
        print(f"  causal_bins: {n_un} of {v.size} events unassigned (burn-in or missing signal)")
    return out


def top_minus_bottom_ci(
    values: Sequence[float] | np.ndarray,
    top: Sequence[bool] | np.ndarray,
    bottom: Sequence[bool] | np.ndarray,
    keys: Sequence[object] | np.ndarray | pd.Series,
    *,
    n_boot: int = 5000,
    seed: int = 0,
    ci: float = 0.95,
) -> tuple[float, float, float]:
    """Mean(top) - mean(bottom) with a percentile interval resampling whole clusters.

    Raises
    ------
    ValueError
        If either group is empty.
    """
    v = np.asarray(values, dtype=float)
    t = np.asarray(top, dtype=bool) & np.isfinite(v)
    b = np.asarray(bottom, dtype=bool) & np.isfinite(v)
    if not t.any() or not b.any():
        raise ValueError("top or bottom group is empty")
    k = pd.to_datetime(pd.Series(np.asarray(keys))).dt.normalize().to_numpy()
    uniq, inv = np.unique(k, return_inverse=True)
    m = uniq.size
    st = np.bincount(inv, weights=np.where(t, v, 0.0), minlength=m)
    nt = np.bincount(inv, weights=t.astype(float), minlength=m)
    sb = np.bincount(inv, weights=np.where(b, v, 0.0), minlength=m)
    nb = np.bincount(inv, weights=b.astype(float), minlength=m)
    point = float(st.sum() / nt.sum() - sb.sum() / nb.sum())
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot)
    for i in range(n_boot):
        c = np.bincount(rng.integers(0, m, m), minlength=m)
        tt, bb = (c * nt).sum(), (c * nb).sum()
        draws[i] = (c * st).sum() / tt - (c * sb).sum() / bb if tt > 0 and bb > 0 else np.nan
    a = (1 - ci) / 2
    return point, float(np.nanquantile(draws, a)), float(np.nanquantile(draws, 1 - a))
