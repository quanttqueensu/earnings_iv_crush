"""
chain_surface.py
The 15:59 option surface of one earnings event as a fixed tensor: implied-vol smile, relative
spreads and quoted sizes for the front expiry and the next listed expiry, on a grid of
standardised moneyness.

Snapshot. A cached backfill chain (``data/cache/backfill_chains/{ticker}_{entry}.parquet``) holds
the one-minute consolidated BBO stamped 15:59:00 ET (``research/chains.py``). The snapshot keeps
rows stamped at or before 15:59 ET on the entry date and the last row per contract by
``ts_recv``. OCC symbols parse as ``research/chains.py::_parse_chain`` does (root, ``yymmdd``,
right, strike in thousandths); that module loads credentials at import and is never imported
here. A one-sided quote (a bid or ask that is not positive) never becomes a mid: it keeps its
bid or ask IV but gives no mid IV, no relative spread and does not enter the grid.

Forward and time. The front forward is passed in (the base panel's 15:59 parity forward). The
next expiry's forward is the median parity forward ``K + (C - P) / D`` over the strikes nearest
the front forward with both legs two-sided, discounted at FRED DFF, ``D = exp(-r tau)``. Time
to expiry is ACT/365 from 15:59 ET on the entry date to 16:00 ET on the expiry date.

Grid. ``x = ln(K / F) / (sigma_atm sqrt(tau))`` with ``sigma_atm`` the Black-76 IV of the
straddle mid at the two-sided strike nearest the forward. Each channel is interpolated linearly
in ``x`` between quoted strikes of its side, never extrapolated, and never across a bracket
wider than ``ChainSurfaceConfig.max_gap_x``. Channels, in order, are listed in ``CHANNELS``;
the last is the validity mask (1 where every other channel is defined at that point).

Usage
-----
    from earnings_iv_crush.research.chain_surface import event_surface
    s = event_surface(raw, entry_date, front_expiry, front_fwd, dff_pct, m0)

References
----------
Black, F. (1976). The pricing of commodity contracts. Journal of Financial Economics 3(1-2),
167-179.
Hull, J. C. (2018). Options, Futures, and Other Derivatives, 10th edition. Pearson. Chapter 11
(put-call parity) and chapter 18 (Black's model).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from ..config import CHAIN_SURFACE, ChainSurfaceConfig

#: Channels of the surface tensor, in storage order. ``*_iv_rel`` is mid IV over sigma_atm;
#: ``*_rel_spread`` is (ask - bid) / mid; sizes are log1p of contracts at the touch.
CHANNELS: tuple[str, ...] = (
    "call_iv_rel",
    "put_iv_rel",
    "call_rel_spread",
    "put_rel_spread",
    "call_log1p_bid_size",
    "call_log1p_ask_size",
    "put_log1p_bid_size",
    "put_log1p_ask_size",
    "mask",
)
#: Expiry axis of the tensor.
EXPIRIES: tuple[str, ...] = ("front", "next")
#: Raw columns a chain file must carry.
RAW_COLUMNS: tuple[str, ...] = (
    "symbol",
    "bid_px_00",
    "ask_px_00",
    "bid_sz_00",
    "ask_sz_00",
)

_ERFC = np.frompyfunc(math.erfc, 1, 1)
_SQRT2 = math.sqrt(2.0)


# ── Black-76 ─────────────────────────────────────────────────────────────────


def norm_cdf(x: npt.ArrayLike) -> np.ndarray:
    """Standard normal CDF, exact to double precision (``math.erfc`` elementwise)."""
    x = np.asarray(x, float)
    return np.asarray(0.5 * _ERFC(-x / _SQRT2), dtype=float)


def black76(
    fwd: npt.ArrayLike,
    strike: npt.ArrayLike,
    tau: npt.ArrayLike,
    sigma: npt.ArrayLike,
    discount: npt.ArrayLike,
    is_call: npt.ArrayLike,
) -> np.ndarray:
    """Black-76 price of a European call or put on the forward.

    Parameters
    ----------
    fwd, strike, tau, sigma, discount : array_like
        Forward, strike, time in years, decimal vol and discount factor ``exp(-r tau)``.
    is_call : array_like of bool
        True for a call, False for a put.

    Returns
    -------
    ndarray
        ``D (F N(d1) - K N(d2))`` for calls, ``D (K N(-d2) - F N(-d1))`` for puts.
    """
    f, k, t, s, d = (np.asarray(a, float) for a in (fwd, strike, tau, sigma, discount))
    c = np.asarray(is_call, bool)
    sd = s * np.sqrt(t)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(f / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    call = f * norm_cdf(d1) - k * norm_cdf(d2)
    put = k * norm_cdf(-d2) - f * norm_cdf(-d1)
    return np.asarray(d * np.where(c, call, put), dtype=float)


def _bisect(
    value: Callable[[np.ndarray], np.ndarray], price: np.ndarray, cfg: ChainSurfaceConfig
) -> np.ndarray:
    """Vol solving ``value(vol) = price`` by bisection on the bracket; NaN when not bracketed."""
    p = np.asarray(price, float)
    lo = np.full(p.shape, cfg.iv_lo)
    hi = np.full(p.shape, cfg.iv_hi)
    ok = np.isfinite(p) & (p > 0)
    with np.errstate(invalid="ignore"):
        ok &= (value(lo) - p <= 0) & (value(hi) - p >= 0)
    for _ in range(cfg.iv_iterations):
        mid = 0.5 * (lo + hi)
        above = value(mid) > p
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    return np.where(ok, 0.5 * (lo + hi), np.nan)


def implied_vol(
    price: npt.ArrayLike,
    fwd: npt.ArrayLike,
    strike: npt.ArrayLike,
    tau: npt.ArrayLike,
    discount: npt.ArrayLike,
    is_call: npt.ArrayLike,
    cfg: ChainSurfaceConfig = CHAIN_SURFACE,
) -> np.ndarray:
    """Vectorised Black-76 implied vol, NaN outside ``[cfg.iv_lo, cfg.iv_hi]`` or for bad inputs.

    Agrees with ``hedged_hold.option_iv`` (zero rate, ``discount = 1``) to the bisection's
    precision; the test suite checks it on a grid.
    """
    shape = np.broadcast(price, fwd, strike, tau, discount, is_call).shape
    p, f, k, t, d = (
        np.broadcast_to(np.asarray(a, float), shape) for a in (price, fwd, strike, tau, discount)
    )
    c = np.broadcast_to(np.asarray(is_call, bool), shape)
    good = (f > 0) & (k > 0) & (t > 0) & (d > 0)
    out = _bisect(lambda s: black76(f, k, t, s, d, c), np.where(good, p, np.nan), cfg)
    return np.where(good, out, np.nan)


def straddle_implied_vol(
    price: npt.ArrayLike,
    fwd: npt.ArrayLike,
    strike: npt.ArrayLike,
    tau: npt.ArrayLike,
    discount: npt.ArrayLike,
    cfg: ChainSurfaceConfig = CHAIN_SURFACE,
) -> np.ndarray:
    """Black-76 IV of a call-plus-put price at one strike, NaN when not bracketed."""
    shape = np.broadcast(price, fwd, strike, tau, discount).shape
    p, f, k, t, d = (
        np.broadcast_to(np.asarray(a, float), shape) for a in (price, fwd, strike, tau, discount)
    )
    good = (f > 0) & (k > 0) & (t > 0) & (d > 0)

    def value(s: np.ndarray) -> np.ndarray:
        return black76(f, k, t, s, d, True) + black76(f, k, t, s, d, False)

    return np.where(good, _bisect(value, np.where(good, p, np.nan), cfg), np.nan)


# ── snapshot and clocks ──────────────────────────────────────────────────────


def snapshot_cutoff(entry_date: Any, cfg: ChainSurfaceConfig = CHAIN_SURFACE) -> pd.Timestamp:
    """15:59 ET on the entry date as a UTC instant (localised, never string-concatenated)."""
    day = pd.Timestamp(entry_date).date()
    return pd.Timestamp(f"{day} {cfg.snapshot_time}").tz_localize(cfg.exchange_tz).tz_convert("UTC")


def year_fraction(entry_date: Any, expiry: Any, cfg: ChainSurfaceConfig = CHAIN_SURFACE) -> float:
    """ACT/365 years from the 15:59 ET snapshot to 16:00 ET on the expiry date."""
    start = snapshot_cutoff(entry_date, cfg)
    end = (
        pd.Timestamp(f"{pd.Timestamp(expiry).date()} {cfg.expiry_time}")
        .tz_localize(cfg.exchange_tz)
        .tz_convert("UTC")
    )
    return float((end - start).total_seconds()) / 86400.0 / cfg.days_per_year


def rate_from_dff(dff_pct: float) -> float:
    """Continuously compounded rate from FRED DFF in percent, ``ln(1 + DFF / 100)``."""
    return float(np.log1p(dff_pct / 100.0))


def parse_symbols(symbol: pd.Series) -> pd.DataFrame:
    """OCC symbol to ``right``, ``strike`` and ``expiry`` as ``chains._parse_chain`` reads it."""
    body = symbol.astype(str).str.replace(" ", "", regex=False).str[-15:]
    return pd.DataFrame(
        {
            "right": body.str[6],
            "strike": pd.to_numeric(body.str[7:], errors="coerce") / 1000.0,
            "expiry": pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce"),
        },
        index=symbol.index,
    )


@dataclass
class Snapshot:
    """The 15:59 chain: one row per contract, and what the cut removed.

    Attributes
    ----------
    chain : DataFrame
        Columns ``strike``, ``expiry``, ``right``, ``bid``, ``ask``, ``bid_sz``, ``ask_sz``,
        ``ts_recv``; bids and asks as quoted (a non-positive or missing value is kept).
    n_rows, n_after_cutoff, n_unparsed, n_superseded : int
        Raw rows, rows stamped after 15:59 ET (dropped), rows whose symbol does not parse
        (dropped) and earlier rows of a contract replaced by its last row.
    """

    chain: pd.DataFrame
    n_rows: int
    n_after_cutoff: int
    n_unparsed: int
    n_superseded: int


def snapshot(
    raw: pd.DataFrame, entry_date: Any, cfg: ChainSurfaceConfig = CHAIN_SURFACE
) -> Snapshot:
    """The last quote per contract at or before 15:59 ET on ``entry_date``.

    Parameters
    ----------
    raw : DataFrame
        A cached chain file, with ``ts_recv`` as its index or a column, and ``RAW_COLUMNS``.
    entry_date : date-like

    Raises
    ------
    ValueError
        If a required column is missing.
    """
    d = raw.reset_index() if "ts_recv" not in raw.columns else raw.copy()
    missing = [c for c in ("ts_recv", *RAW_COLUMNS) if c not in d.columns]
    if missing:
        raise ValueError(f"chain lacks columns {missing}")
    ts = pd.to_datetime(d["ts_recv"], utc=True)
    n_rows = len(d)
    keep = ts <= snapshot_cutoff(entry_date, cfg)
    d, ts = d.loc[keep], ts[keep]
    sym = parse_symbols(d["symbol"])
    parsed = sym["strike"].notna() & sym["expiry"].notna() & sym["right"].isin(["C", "P"])
    out = pd.DataFrame(
        {
            "strike": sym["strike"],
            "expiry": sym["expiry"],
            "right": sym["right"],
            "bid": pd.to_numeric(d["bid_px_00"], errors="coerce").astype(float),
            "ask": pd.to_numeric(d["ask_px_00"], errors="coerce").astype(float),
            "bid_sz": pd.to_numeric(d["bid_sz_00"], errors="coerce").astype(float),
            "ask_sz": pd.to_numeric(d["ask_sz_00"], errors="coerce").astype(float),
            "ts_recv": ts,
        }
    ).loc[parsed]
    n_parsed = len(out)
    out = (
        out.sort_values("ts_recv", kind="stable")
        .groupby(["expiry", "strike", "right"], as_index=False)
        .last()
        .sort_values(["expiry", "strike", "right"], kind="stable")
        .reset_index(drop=True)
    )
    return Snapshot(
        chain=out,
        n_rows=n_rows,
        n_after_cutoff=int((~keep).sum()),
        n_unparsed=int((~parsed).sum()),
        n_superseded=n_parsed - len(out),
    )


# ── one expiry ───────────────────────────────────────────────────────────────


def _sides(chain: pd.DataFrame, expiry: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Calls and puts of one expiry, indexed by strike, with a two-sided flag and the mid."""
    d = chain[chain["expiry"] == expiry]
    out: dict[str, pd.DataFrame] = {}
    for r in ("C", "P"):
        s = d[d["right"] == r].set_index("strike").sort_index()
        two = (s["bid"] > 0) & (s["ask"] > 0)
        s = s.assign(two_sided=two, mid=np.where(two, (s["bid"] + s["ask"]) / 2.0, np.nan))
        out[r] = s
    return out


def parity_forward(
    sides: dict[str, pd.DataFrame],
    anchor: float,
    discount: float,
    cfg: ChainSurfaceConfig = CHAIN_SURFACE,
) -> tuple[float, int]:
    """Median ``K + (C - P) / D`` over the ``cfg.parity_strikes`` two-sided pairs nearest ``anchor``.

    Returns the forward (NaN when fewer than ``cfg.parity_min_strikes`` pairs exist) and the
    number of pairs used.
    """
    c, p = sides["C"], sides["P"]
    both = c.index[c["two_sided"]].intersection(p.index[p["two_sided"]])
    if not len(both) or not np.isfinite(anchor) or discount <= 0:
        return float("nan"), 0
    k = np.asarray(both, float)
    near = k[np.argsort(np.abs(k - anchor), kind="stable")[: cfg.parity_strikes]]
    fw = near + (c.loc[near, "mid"].to_numpy(float) - p.loc[near, "mid"].to_numpy(float)) / discount
    if near.size < cfg.parity_min_strikes:
        return float("nan"), int(near.size)
    return float(np.median(fw)), int(near.size)


def interp_masked(
    x_quoted: np.ndarray, values: np.ndarray, grid: np.ndarray, max_gap: float
) -> np.ndarray:
    """Linear interpolation on ``grid`` with no extrapolation and no bridging of wide holes.

    ``x_quoted`` must be strictly increasing. A grid point outside ``[x_quoted[0],
    x_quoted[-1]]``, or inside a bracket wider than ``max_gap``, is NaN; a point on a quoted
    ``x`` takes its value exactly.
    """
    xq, v, g = (np.asarray(a, float) for a in (x_quoted, values, grid))
    ok = np.isfinite(xq) & np.isfinite(v)
    xq, v = xq[ok], v[ok]
    out = np.full(g.shape, np.nan)
    if xq.size == 0:
        return out
    if xq.size > 1 and not (np.diff(xq) > 0).all():
        raise ValueError("quoted x must be strictly increasing")
    inside = (g >= xq[0]) & (g <= xq[-1])
    out[inside] = np.interp(g[inside], xq, v)
    j = np.clip(np.searchsorted(xq, g, side="left"), 1, max(xq.size - 1, 1))
    exact = np.isin(g, xq)
    if xq.size > 1:
        wide = (xq[j] - xq[j - 1]) > max_gap
        out[inside & wide & ~exact] = np.nan
    return out


@dataclass
class ExpirySurface:
    """One expiry's grid and scalars.

    Attributes
    ----------
    grid : ndarray, shape (len(CHANNELS), cfg.grid_points)
    sigma_atm, atm_strike, atm_half_spread : float
        Straddle mid IV, strike and straddle half-spread ``(ask - bid) / 2 / mid`` at the
        two-sided strike nearest the forward (NaN when none).
    strikes : DataFrame
        Per strike and side: bid, ask and mid IV, x, and whether the strike entered the grid.
    """

    grid: np.ndarray
    sigma_atm: float
    atm_strike: float
    atm_half_spread: float
    strikes: pd.DataFrame = field(default_factory=pd.DataFrame)


def grid_points(cfg: ChainSurfaceConfig = CHAIN_SURFACE) -> np.ndarray:
    """The standardised-moneyness grid."""
    return np.linspace(cfg.grid_lo, cfg.grid_hi, cfg.grid_points)


def expiry_surface(
    sides: dict[str, pd.DataFrame],
    fwd: float,
    tau: float,
    discount: float,
    cfg: ChainSurfaceConfig = CHAIN_SURFACE,
) -> ExpirySurface:
    """Channels on the grid for one expiry; an all-NaN grid with mask 0 when it cannot be built."""
    g = grid_points(cfg)
    grid = np.full((len(CHANNELS), g.size), np.nan)
    grid[-1] = 0.0
    nan = float("nan")
    if not (np.isfinite(fwd) and fwd > 0 and np.isfinite(tau) and tau > 0):
        return ExpirySurface(grid, nan, nan, nan)
    c, p = sides["C"], sides["P"]
    both = c.index[c["two_sided"]].intersection(p.index[p["two_sided"]])
    if not len(both):
        return ExpirySurface(grid, nan, nan, nan)
    kb = np.asarray(both, float)
    k_atm = float(kb[np.argmin(np.abs(kb - fwd))])
    q = {
        f"{r}{col}": float(np.asarray(s.loc[[k_atm], col], float)[0])
        for r, s in (("c", c), ("p", p))
        for col in ("bid", "ask", "mid")
    }
    mid = q["cmid"] + q["pmid"]
    half = (q["cask"] + q["pask"] - q["cbid"] - q["pbid"]) / 2.0 / mid
    sig = float(straddle_implied_vol(mid, fwd, k_atm, tau, discount, cfg))
    if not (np.isfinite(sig) and sig > 0):
        return ExpirySurface(grid, sig, k_atm, half)
    rows = []
    for r, s in (("C", c), ("P", p)):
        k = s.index.to_numpy(float)
        is_call = r == "C"
        iv = {
            q: implied_vol(s[q].to_numpy(float), fwd, k, tau, discount, is_call, cfg)
            for q in ("bid", "ask", "mid")
        }
        x = np.log(k / fwd) / (sig * np.sqrt(tau))
        use = s["two_sided"].to_numpy(bool) & np.isfinite(iv["mid"])
        rows.append(
            pd.DataFrame(
                {
                    "right": r,
                    "strike": k,
                    "x": x,
                    "bid": s["bid"].to_numpy(float),
                    "ask": s["ask"].to_numpy(float),
                    "iv_bid": iv["bid"],
                    "iv_ask": iv["ask"],
                    "iv_mid": iv["mid"],
                    "in_grid": use,
                }
            )
        )
        off = 0 if is_call else 1
        xu = x[use]
        mid_r = s["mid"].to_numpy(float)[use]
        vals = {
            "iv_rel": iv["mid"][use] / sig,
            "rel_spread": (s["ask"].to_numpy(float)[use] - s["bid"].to_numpy(float)[use]) / mid_r,
            "log1p_bid_size": np.log1p(s["bid_sz"].to_numpy(float)[use]),
            "log1p_ask_size": np.log1p(s["ask_sz"].to_numpy(float)[use]),
        }
        grid[0 + off] = interp_masked(xu, vals["iv_rel"], g, cfg.max_gap_x)
        grid[2 + off] = interp_masked(xu, vals["rel_spread"], g, cfg.max_gap_x)
        grid[4 + 2 * off] = interp_masked(xu, vals["log1p_bid_size"], g, cfg.max_gap_x)
        grid[5 + 2 * off] = interp_masked(xu, vals["log1p_ask_size"], g, cfg.max_gap_x)
    grid[-1] = np.isfinite(grid[:-1]).all(axis=0).astype(float)
    return ExpirySurface(grid, sig, k_atm, half, pd.concat(rows, ignore_index=True))


# ── one event ────────────────────────────────────────────────────────────────


@dataclass
class EventSurface:
    """The event's tensor, scalars and build status.

    Attributes
    ----------
    grid : ndarray, shape (len(CHANNELS), 2, cfg.grid_points)
        Expiry axis ordered as ``EXPIRIES``.
    scalars : dict
        ``sigma_atm_front``, ``sigma_atm_next``, ``tau_front``, ``tau_next``, ``front_fwd``,
        ``m0``, plus ``next_fwd``, ``rate``, ``atm_strike_front``, ``atm_half_spread_front``,
        ``n_parity_next`` and ``fill`` (mean of the mask over both expiries).
    status : dict
        ``front_found``, ``next_found``, ``next_expiry`` and the snapshot's row counts.
    expiries : dict
        The two ``ExpirySurface`` objects (front, next), for spot checks.
    """

    grid: np.ndarray
    scalars: dict[str, float]
    status: dict[str, Any]
    expiries: dict[str, ExpirySurface]


def event_surface(
    raw: pd.DataFrame,
    entry_date: Any,
    front_expiry: Any,
    front_fwd: float,
    dff_pct: float,
    m0: float,
    cfg: ChainSurfaceConfig = CHAIN_SURFACE,
) -> EventSurface:
    """Build one event's surface from its raw 15:59 chain file.

    Parameters
    ----------
    raw : DataFrame
        The cached chain file as read (``ts_recv`` index or column).
    entry_date, front_expiry : date-like
        The event's entry session and the base panel's front expiry.
    front_fwd : float
        The base panel's 15:59 parity forward on the front expiry.
    dff_pct : float
        FRED DFF in percent, the last value on or before the entry date.
    m0 : float
        The event's margin unit, carried as a scalar.
    """
    snap = snapshot(raw, entry_date, cfg)
    ch = snap.chain
    rate = rate_from_dff(dff_pct) if np.isfinite(dff_pct) else float("nan")
    fe = pd.Timestamp(front_expiry).normalize()
    exps = np.sort(ch["expiry"].unique())
    front_found = bool(np.isin(np.datetime64(fe, "ns"), exps.astype("datetime64[ns]")))
    later = [pd.Timestamp(e) for e in exps if pd.Timestamp(e) > fe]
    ne = later[0] if later else None
    tau_f = year_fraction(entry_date, fe, cfg)
    tau_n = year_fraction(entry_date, ne, cfg) if ne is not None else float("nan")
    disc_f = float(np.exp(-rate * tau_f)) if np.isfinite(rate) else float("nan")
    disc_n = float(np.exp(-rate * tau_n)) if np.isfinite(rate) and ne is not None else float("nan")
    g = grid_points(cfg)
    empty = np.full((len(CHANNELS), g.size), np.nan)
    empty[-1] = 0.0
    nan = float("nan")
    if front_found:
        front = expiry_surface(_sides(ch, fe), front_fwd, tau_f, disc_f, cfg)
    else:
        front = ExpirySurface(empty.copy(), nan, nan, nan)
    next_fwd, n_par = float("nan"), 0
    if ne is not None and np.isfinite(disc_n):
        sn = _sides(ch, ne)
        next_fwd, n_par = parity_forward(sn, front_fwd, disc_n, cfg)
        nxt = expiry_surface(sn, next_fwd, tau_n, disc_n, cfg)
    else:
        nxt = ExpirySurface(empty.copy(), nan, nan, nan)
    grid = np.stack([front.grid, nxt.grid], axis=1)
    scalars = {
        "sigma_atm_front": front.sigma_atm,
        "sigma_atm_next": nxt.sigma_atm,
        "tau_front": tau_f,
        "tau_next": tau_n,
        "front_fwd": float(front_fwd),
        "m0": float(m0),
        "next_fwd": next_fwd,
        "rate": rate,
        "atm_strike_front": front.atm_strike,
        "atm_half_spread_front": front.atm_half_spread,
        "n_parity_next": float(n_par),
        "fill": float(grid[-1].mean()),
    }
    status = {
        "front_found": front_found and np.isfinite(front.sigma_atm),
        "next_found": ne is not None and np.isfinite(nxt.sigma_atm),
        "next_expiry": ne,
        "n_rows": snap.n_rows,
        "n_after_cutoff": snap.n_after_cutoff,
        "n_unparsed": snap.n_unparsed,
        "n_superseded": snap.n_superseded,
    }
    return EventSurface(grid, scalars, status, {"front": front, "next": nxt})
