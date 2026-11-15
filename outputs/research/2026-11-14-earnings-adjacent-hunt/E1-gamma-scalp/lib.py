"""
lib.py
Lane E1: a long, intraday delta-hedged straddle inside one 15:00-16:00 session, valued at the
touch from the cached quote grids written by ``extract.py``.

The underlying is the put-call-parity forward of the one cached strike, F = K + C_mid - P_mid
(zero rate, as in ``earnings_iv_crush.research.hedged_hold``). Hedge ratios are taken from F and
the straddle-mid implied vol observed ``lag`` seconds before each rebalance and executed at F at
the rebalance time, which removes the spurious gain a noisy proxy creates when the same noisy
print sets both the ratio and the trade price. Option legs pay the quoted touch plus the
commission in ``HEDGED_NET``; stock legs pay an assumed half-spread plus 1 bp on traded notional.

References
----------
Muravyev, D. and Ni, X. (2020). Why do option returns change sign from day to night? *Journal of
Financial Economics* 136(1), 219-238.
Bakshi, G. and Kapadia, N. (2003). Delta-Hedged Gains and the Negative Market Volatility Risk
Premium. *Review of Financial Studies* 16(2), 527-566.
Zhang, L., Mykland, P. A. and Ait-Sahalia, Y. (2005). A Tale of Two Time Scales. *Journal of the
American Statistical Association* 100(472), 1394-1411.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from earnings_iv_crush.config import HEDGED_NET

HERE = Path(__file__).resolve().parent
TRIALS = HERE / "trials.csv"
STEP = 5  # seconds per grid point (extract.GRID_STEP)
N_GRID = 720
SESS = {"Dm2": 0, "Dm1": 1, "D0": 2, "D1": 3}
FEE = HEDGED_NET.fee_per_contract_leg / 100.0  # per share per leg per side
STOCK_HALF_BPS = 3.0  # SHADOW.equity_half_spread_bps: 90th pct CRSP closing half-spread, 2024
STOCK_EXTRA_BPS = 1.0  # the brief's +1 bp on every stock leg
YEAR_SEC = 365.0 * 86400.0  # ACT/365 calendar seconds


def k_of(hhmmss: str) -> int:
    """Grid index of a 15:mm:ss clock time."""
    h, m, s = map(int, hhmmss.split(":"))
    if h != 15:
        raise ValueError("grid covers 15:00:00-15:59:55 only")
    return (m * 60 + s) // STEP


# ── vectorised Black on the forward ─────────────────────────────────────────


def straddle_px(f: np.ndarray, k: np.ndarray, t: np.ndarray, sig: np.ndarray) -> np.ndarray:
    sd = sig * np.sqrt(t)
    d1 = (np.log(f / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    call = f * ndtr(d1) - k * ndtr(d2)
    return 2.0 * call - (f - k)  # put by parity at zero rate


def straddle_iv(px: np.ndarray, f: np.ndarray, k: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Bisection IV of a straddle mid; NaN where the price is outside the no-arbitrage range."""
    lo = np.full_like(px, 1e-4)
    hi = np.full_like(px, 5.0)
    ok = (px > np.abs(f - k)) & (px < straddle_px(f, k, t, hi)) & (t > 0) & (f > 0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        above = straddle_px(f, k, t, mid) > px
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    out = 0.5 * (lo + hi)
    out[~ok] = np.nan
    return out


def straddle_delta(f: np.ndarray, k: np.ndarray, t: np.ndarray, sig: np.ndarray) -> np.ndarray:
    sd = sig * np.sqrt(t)
    d1 = (np.log(f / k) + 0.5 * sd * sd) / sd
    return 2.0 * ndtr(d1) - 1.0


# ── inputs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Session:
    """Per-event quote arrays of one session, shape (n_events, 720)."""

    cb: np.ndarray
    ca: np.ndarray
    pb: np.ndarray
    pa: np.ndarray
    strike: np.ndarray
    t_sec: np.ndarray  # calendar seconds from 15:00:00 of the session to expiry 16:00

    @property
    def fwd(self) -> np.ndarray:
        return self.strike[:, None] + 0.5 * (self.cb + self.ca) - 0.5 * (self.pb + self.pa)

    @property
    def mid(self) -> np.ndarray:
        return 0.5 * (self.cb + self.ca + self.pb + self.pa)

    def tau(self, k: int) -> np.ndarray:
        return (self.t_sec - k * STEP) / YEAR_SEC


def load(cache: Path = HERE / "cache") -> tuple[pd.DataFrame, np.ndarray]:
    ev = pd.read_parquet(cache / "events.parquet")
    for c in ("entry_date", "exit_date", "expiry", "dm1_date", "dm2_date"):
        ev[c] = pd.to_datetime(ev[c])
    grid = np.load(cache / "grid.npz")["grid"].astype(float)
    if len(ev) != grid.shape[0]:
        raise ValueError("events and grid differ in length")
    return ev, grid


def session(ev: pd.DataFrame, grid: np.ndarray, name: str) -> Session:
    day = {"D1": ev["exit_date"], "D0": ev["entry_date"], "Dm1": ev["dm1_date"],
           "Dm2": ev["dm2_date"]}[name]
    start = day.dt.normalize() + pd.Timedelta(hours=15)
    end = ev["expiry"].dt.normalize() + pd.Timedelta(hours=16)
    g = grid[:, SESS[name]]
    return Session(cb=g[:, 0], ca=g[:, 1], pb=g[:, 2], pa=g[:, 3],
                   strike=ev["strike"].to_numpy(float),
                   t_sec=(end - start).dt.total_seconds().to_numpy(float))


# ── the trade ───────────────────────────────────────────────────────────────


def scalp(
    s: Session,
    *,
    entry: str = "15:01:00",
    exit_: str = "15:59:00",
    clock_sec: int | None = 300,
    band: float | None = None,
    lag_sec: int = 30,
    stock_bps: float = STOCK_HALF_BPS + STOCK_EXTRA_BPS,
    settle: bool = False,
    side: int = 1,
) -> pd.DataFrame:
    """Long (side=+1) or short (side=-1) straddle from ``entry`` to ``exit_``, hedged in F.

    ``clock_sec`` rebalances on a fixed clock from the entry; ``band`` instead checks every
    minute and rebalances when the target hedge differs from the held one by more than ``band``;
    ``clock_sec=None`` and ``band=None`` is the static hedge (one hedge at entry). ``settle``
    replaces the exit sale with expiry at intrinsic against F at 15:59:55 (only valid when the
    contract expires that session). Every P&L is per share of one straddle.
    """
    k0, k1, lag = k_of(entry), k_of(exit_), lag_sec // STEP
    f, mid = s.fwd, s.mid
    n = f.shape[0]
    idx = np.arange(n)
    ask0 = s.ca[:, k0] + s.pa[:, k0]
    bid0 = s.cb[:, k0] + s.pb[:, k0]
    mid0 = 0.5 * (ask0 + bid0)
    if settle:
        f_end = f[:, N_GRID - 1]
        exit_val = np.abs(f_end - s.strike)
        exit_mid = exit_val
        n_exit_legs = 0
        no_bid = np.zeros(n, dtype=bool)
    else:
        cb1, pb1 = s.cb[:, k1], s.pb[:, k1]
        no_bid = ~np.isfinite(cb1) | ~np.isfinite(pb1)
        exit_val = np.nan_to_num(cb1, nan=0.0) + np.nan_to_num(pb1, nan=0.0)
        exit_mid = 0.5 * (s.cb[:, k1] + s.ca[:, k1] + s.pb[:, k1] + s.pa[:, k1])
        n_exit_legs = 2
    # rebalance schedule
    if band is not None:
        sched = list(range(k0, k1, 60 // STEP))
    elif clock_sec is not None:
        sched = list(range(k0, k1, clock_sec // STEP))
    else:
        sched = [k0]
    h = np.zeros(n)  # shares held per straddle
    last_f = np.full(n, np.nan)  # price at which the hedge was last marked
    hedge_pnl = np.zeros(n)
    cost = np.zeros(n)
    n_trade = np.zeros(n)
    n_skip = np.zeros(n)
    for k in sched:
        kl = max(k - lag, 0)
        fl, ml = f[:, kl], mid[:, kl]
        sig = straddle_iv(ml, fl, s.strike, s.tau(kl))
        target = -side * straddle_delta(fl, s.strike, s.tau(kl), sig)
        fk = f[:, k]
        can = np.isfinite(target) & np.isfinite(fk)
        if band is not None:
            can &= np.abs(target - h) > band
        # mark the existing hedge to fk where it is observed
        mark = np.isfinite(fk) & np.isfinite(last_f)
        hedge_pnl[mark] += h[mark] * (fk[mark] - last_f[mark])
        last_f[np.isfinite(fk)] = fk[np.isfinite(fk)]
        dh = np.where(can, target - h, 0.0)
        cost += np.abs(dh) * np.nan_to_num(fk) * stock_bps / 1e4
        n_trade += can & (np.abs(dh) > 0)
        n_skip += ~(np.isfinite(target) & np.isfinite(fk)) & (band is None)
        h = np.where(can, target, h)
    # unwind at the exit (or settlement) price; fall back to the last observed F, counted
    k_end = N_GRID - 1 if settle else k1
    fe = f[:, k_end]
    stale_end = ~np.isfinite(fe)
    fe = np.where(stale_end, last_f, fe)
    mark = np.isfinite(fe) & np.isfinite(last_f)
    hedge_pnl[mark] += h[mark] * (fe[mark] - last_f[mark])
    if settle:
        # physical assignment nets the hedge: only h - sign trades (HEDGED_NET convention)
        resid = h + side * np.sign(fe - s.strike)
        cost += np.abs(resid) * np.nan_to_num(fe) * stock_bps / 1e4
    else:
        cost += np.abs(h) * np.nan_to_num(fe) * stock_bps / 1e4
    fees = FEE * 2 * (1 + (1 if n_exit_legs else 0))
    if side == 1:
        debit = ask0 + 2 * FEE
        net = exit_val - ask0 + hedge_pnl - cost - fees
    else:
        debit = bid0  # credit received; basis for the short is the credit
        exit_cost = (
            np.abs(f[:, N_GRID - 1] - s.strike)
            if settle
            else s.ca[:, k1] + s.pa[:, k1]
        )
        net = bid0 - exit_cost + hedge_pnl - cost - fees
    gross_mid = side * (exit_mid - mid0) + hedge_pnl
    return pd.DataFrame(
        {
            "ask0": ask0, "bid0": bid0, "mid0": mid0, "exit_val": exit_val, "exit_mid": exit_mid,
            "no_exit_bid": no_bid, "hedge_pnl": hedge_pnl, "stock_cost": cost, "fees": fees,
            "debit": debit, "net": net, "gross_mid": gross_mid, "n_trade": n_trade,
            "n_skip": n_skip, "stale_end": stale_end, "h_end": h,
            "touch_rt": (ask0 - mid0) + (exit_mid - np.where(no_bid, 0.0, exit_val)),
        },
        index=idx,
    )


# ── statistics and logging ──────────────────────────────────────────────────


def entry_ok(s: Session, entry: str = "15:01:00") -> np.ndarray:
    """Two-sided quotes on both legs and an invertible straddle IV at the entry and its lag."""
    k0 = k_of(entry)
    ok = np.ones(s.cb.shape[0], dtype=bool)
    for k in (k0, max(k0 - 6, 0)):
        q = np.isfinite(s.cb[:, k] + s.ca[:, k] + s.pb[:, k] + s.pa[:, k])
        ok &= q
    sig = straddle_iv(s.mid[:, k0], s.fwd[:, k0], s.strike, s.tau(k0))
    return ok & np.isfinite(sig)


TRIAL_COLS = ["trial", "utc", "block", "rule", "statistic", "basis", "n", "clusters", "point",
              "low", "high", "per_trade_sharpe", "label", "note"]


def log_trial(row: dict) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRIAL_COLS)
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in TRIAL_COLS})


def rv_signature(s: Session, k0: int, k1: int, steps: tuple[int, ...]) -> pd.DataFrame:
    """Realised variance of log F over [k0, k1] at several sampling steps (grid units),
    averaged over every offset (subsampling), per event."""
    lf = np.log(s.fwd)
    out = {}
    for st in steps:
        acc = np.zeros(lf.shape[0])
        cnt = np.zeros(lf.shape[0])
        for off in range(st):
            ks = np.arange(k0 + off, k1 + 1, st)
            if len(ks) < 2:
                continue
            r = np.diff(lf[:, ks], axis=1)
            good = np.isfinite(r).all(axis=1)
            acc[good] += (r[good] ** 2).sum(axis=1) * (k1 - k0) / (st * (len(ks) - 1))
            cnt[good] += 1
        out[f"rv_{st * STEP}s"] = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    return pd.DataFrame(out)
