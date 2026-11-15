"""
lib.py
Resting-bid buy-back rules for the short earnings straddle on reaction-session ticks (lane F).

A rule rests a buy limit on one or both legs from a start minute after 15:00 ET and crosses
whatever has not filled at the 15:59:00 ask. The paired statistic per event is

    improvement = sum over legs (ask_15:59:00 - price paid) / m0

so an unfilled leg contributes zero and a filled leg contributes its saving against the taker
buy-back the programme books (15:59:00 is the chain's own sampling instant, where the ticks
reproduce the cached chain exactly; F1 addendum 03). Fill rules:

    brief    a trade printed at or below the limit, or the ask at or below it
    through  a trade strictly below the limit, or the ask at or below it
    clean    a trade at or below the limit and at or above the prevailing NBBO bid (prints below
             the bid are mostly complex-order legs that would not reach a simple resting bid),
             or the ask at or below it

A filled order is paid at its limit even when the ask crossed below it (conservative). Limits
round up to the legal tick (penny schedule: 0.01 below 3.00, 0.05 at or above), the
P&L-unfavourable direction for a buy. A leg with no two-sided quote at the reference instant is
not rested and is crossed. A one-sided quote never becomes a mid.

References
----------
Muravyev, D. (2016). Order Flow and Expected Option Returns. Journal of Finance 71(2), 673-708.
Chan, K., Chung, Y. P. and Johnson, H. (1995). The intraday behavior of bid-ask spreads for
NYSE stocks and CBOE options. Journal of Financial and Quantitative Analysis 30(3), 329-346.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import date_clustered_ci, matched_random_null  # noqa: E402

END = 3540.0  # 15:59:00 in seconds after 15:00
FEES = 4 * 0.0065  # four option commissions per straddle round trip, per share (hedged-hold B)
TRIALS = HERE / "trials.csv"
TRIAL_COLS = [
    "trial_id", "hypothesis", "mechanism", "block", "n", "effect", "ci_low", "ci_high", "t",
    "null_percentile", "basis", "verdict",
]


# ── data ─────────────────────────────────────────────────────────────────────


@dataclass
class Leg:
    qt: np.ndarray  # all record times
    qb: np.ndarray
    qa: np.ndarray
    two: np.ndarray  # two-sided mask
    tt: np.ndarray  # trade times
    tp: np.ndarray
    tb: np.ndarray  # NBBO bid on the trade record
    penny: bool = True  # quotes below 3.00 off the nickel grid, so the class trades in pennies


def load() -> tuple[pd.DataFrame, dict[tuple[int, str], Leg]]:
    ev = pd.read_parquet(HERE / "events.parquet")
    tk = pd.read_parquet(
        HERE / "ticks.parquet",
        columns=["eid", "right", "sec", "action", "price", "bid_px_00", "ask_px_00"],
    )
    tk = tk.sort_values(["eid", "right", "sec"], kind="stable").reset_index(drop=True)
    key = tk["eid"].astype(np.int64).to_numpy() * 2 + (tk["right"].to_numpy() == "P")
    cuts = np.flatnonzero(np.diff(key)) + 1
    starts = np.r_[0, cuts]
    ends = np.r_[cuts, len(tk)]
    sec = tk["sec"].to_numpy()
    bid = tk["bid_px_00"].to_numpy()
    ask = tk["ask_px_00"].to_numpy()
    px = tk["price"].to_numpy()
    is_t = (tk["action"] == "T").to_numpy()
    legs: dict[tuple[int, str], Leg] = {}
    for s, e in zip(starts, ends):
        k = key[s]
        sl = slice(s, e)
        t_mask = is_t[sl]
        b, a = bid[sl], ask[sl]
        lowp = np.r_[b[(b > 0) & (b < 3.0)], a[(a > 0) & (a < 3.0)]]
        hip = np.r_[b[b >= 3.0], a[a >= 3.0]]
        penny = bool(np.any(np.abs(lowp * 20 - np.round(lowp * 20)) > 1e-6)) or bool(
            np.any(np.abs(hip * 10 - np.round(hip * 10)) > 1e-6)
        )
        legs[(int(k // 2), "P" if k % 2 else "C")] = Leg(
            qt=sec[sl], qb=b, qa=a, two=(b > 0) & (a > b),
            tt=sec[sl][t_mask], tp=px[sl][t_mask], tb=b[t_mask], penny=penny,
        )
    # A class has one tick schedule: either leg's evidence of pennies applies to both.
    for (eid, r), lg in legs.items():
        other = legs.get((eid, "P" if r == "C" else "C"))
        if other is not None and other.penny:
            lg.penny = True
    return ev, legs


# ── quote helpers ────────────────────────────────────────────────────────────


def tick_of(p: float, penny: bool = True) -> float:
    if penny:
        return 0.01 if p < 3.0 else 0.05
    return 0.05 if p < 3.0 else 0.10


def round_up(p: float, penny: bool = True) -> float:
    t = tick_of(p, penny)
    return float(round(np.ceil(p / t - 1e-9) * t, 4))


def quote_at(leg: Leg, t: float, fallback: float = 60.0) -> tuple[float, float] | None:
    """Last two-sided quote at or before t; else the first in (t, t + fallback]."""
    r = quote_at_t(leg, t, fallback)
    return None if r is None else (r[0], r[1])


def quote_at_t(leg: Leg, t: float, fallback: float = 60.0) -> tuple[float, float, float] | None:
    """As quote_at, plus the time the quote became known (orders cannot rest before it)."""
    i = np.searchsorted(leg.qt, t, side="right")
    idx = np.flatnonzero(leg.two[:i])
    if idx.size:
        j = idx[-1]
        return float(leg.qb[j]), float(leg.qa[j]), t
    k = np.searchsorted(leg.qt, t + fallback, side="right")
    idx = np.flatnonzero(leg.two[i:k])
    if idx.size:
        j = i + idx[0]
        return float(leg.qb[j]), float(leg.qa[j]), float(leg.qt[j])
    return None


def ask_at(leg: Leg, t: float) -> float | None:
    """Last positive ask at or before t (bid may be zero: the taker buy-back needs only an ask)."""
    i = np.searchsorted(leg.qt, t, side="right")
    idx = np.flatnonzero(leg.qa[:i] > 0)
    return float(leg.qa[idx[-1]]) if idx.size else None


def mid_at(leg: Leg, t: float) -> float | None:
    q = quote_at(leg, t, fallback=0.0)
    return None if q is None else (q[0] + q[1]) / 2


def first_fill(leg: Leg, lim: float, a: float, b: float, rule: str) -> float | None:
    """First time in (a, b] a resting buy at ``lim`` fills under ``rule``."""
    i0, i1 = np.searchsorted(leg.qt, [a, b], side="right")
    qa = leg.qa[i0:i1]
    hq = np.flatnonzero((qa > 0) & (qa <= lim + 1e-9))
    tq = leg.qt[i0 + hq[0]] if hq.size else np.inf
    j0, j1 = np.searchsorted(leg.tt, [a, b], side="right")
    tp, tb = leg.tp[j0:j1], leg.tb[j0:j1]
    if rule == "brief":
        m = tp <= lim + 1e-9
    elif rule == "through":
        m = tp < lim - 1e-9
    elif rule == "clean":
        m = (tp <= lim + 1e-9) & (tb > 0) & (tp >= tb - 1e-9)
    else:
        raise ValueError(rule)
    ht = np.flatnonzero(m)
    tt = leg.tt[j0 + ht[0]] if ht.size else np.inf
    t = min(tq, tt)
    return None if not np.isfinite(t) else float(t)


# ── rules ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    start: int = 0  # minutes after 15:00 when the order goes in
    repeg: bool = False  # re-price to the current mid at the top of every minute
    price: str = "mid"  # mid | bid1 (bid plus one tick) | mid_m1 (mid minus one tick)
    legs: str = "both"  # both | wide (wider dollar spread at the start) | itm | otm
    fill: str = "brief"
    taker_at: int | None = None  # control: lift the ask at this minute instead of resting
    ticks: str = "penny"  # penny schedule for every class, or "auto": inferred from the quotes
    ladder_at: int | None = None  # with repeg: ``price`` before this minute, the mid from it
    cross_at: int = 59  # minute at which unfilled legs lift the ask (59 = 15:59:00, the baseline)


def _limit(q: tuple[float, float], price: str, penny: bool = True) -> float | None:
    b, a = q
    mid = (a + b) / 2
    if price == "mid":
        return round_up(mid, penny)
    if price == "bid1":
        tk = tick_of(b, penny)
        return round(b + tk, 4) if b + tk < a - 1e-9 else round_up(mid, penny)
    if price == "mid_m1":
        lim = round_up(mid, penny) - tick_of(mid, penny)
        return round(lim, 4) if lim > b + 1e-9 else round(b, 4)
    raise ValueError(price)


def leg_outcome(leg: Leg, rule: Rule, rested: bool) -> dict | None:
    ask_end = ask_at(leg, END)
    if ask_end is None:
        return None
    out = {"ask_end": ask_end, "price": ask_end, "filled": False, "rested": False, "tf": np.nan}
    if rule.taker_at is not None:
        q = ask_at(leg, rule.taker_at * 60.0) or (quote_at(leg, rule.taker_at * 60.0) or (0, 0))[1]
        if q:
            out.update(price=float(q), filled=True, tf=rule.taker_at * 60.0)
        return out
    stop = min(rule.cross_at * 60.0, END)
    if stop < END:
        ax = ask_at(leg, stop)
        if ax is None:
            return None
        out["price"] = ax
    if not rested:
        return out
    t0 = rule.start * 60.0
    mins = range(rule.start, rule.cross_at) if rule.repeg else [rule.start]
    for k in mins:
        a = k * 60.0
        b = (k + 1) * 60.0 if rule.repeg else stop
        qq = quote_at_t(leg, a, fallback=60.0 if k == rule.start else 0.0)
        if qq is None:
            continue
        q, a = (qq[0], qq[1]), max(a, qq[2])
        px = rule.price if rule.ladder_at is None or k < rule.ladder_at else "mid"
        lim = _limit(q, px, leg.penny if rule.ticks == "auto" else True)
        if lim is None:
            continue
        out["rested"] = True
        out.setdefault("lim0", lim)
        tf = first_fill(leg, lim, max(a, t0), min(b, stop), rule.fill)
        if tf is not None:
            qf = quote_at(leg, tf, fallback=0.0)
            out.update(price=lim, filled=True, tf=tf, lim=lim,
                       half=(qf[1] - qf[0]) / 2 if qf else np.nan)
            for h, lab in ((60, "1"), (300, "5"), (900, "15")):
                m = mid_at(leg, min(tf + h, END))
                out[f"mid_{lab}"] = m if m is not None else np.nan
            m = mid_at(leg, END)
            out["mid_end"] = m if m is not None else np.nan
            return out
    return out


def score_rule(ev: pd.DataFrame, legs: dict, rule: Rule) -> pd.DataFrame:
    rows = []
    for e in ev.itertuples(index=False):
        lc, lp = legs.get((e.eid, "C")), legs.get((e.eid, "P"))
        if lc is None or lp is None:
            rows.append({"eid": e.eid, "measured": False})
            continue
        rest = {"C": True, "P": True}
        if rule.legs != "both":
            qc, qp = quote_at(lc, rule.start * 60.0), quote_at(lp, rule.start * 60.0)
            if qc is None or qp is None:
                rest = {"C": qc is not None, "P": qp is not None}
            elif rule.legs == "wide":
                wc, wp = qc[1] - qc[0], qp[1] - qp[0]
                rest = {"C": wc >= wp, "P": wp > wc}
            elif rule.legs in ("itm", "otm"):
                mc, mp = sum(qc) / 2, sum(qp) / 2
                itm_c = mc >= mp
                rest = {"C": itm_c == (rule.legs == "itm"), "P": itm_c != (rule.legs == "itm")}
        oc, op = leg_outcome(lc, rule, rest["C"]), leg_outcome(lp, rule, rest["P"])
        if oc is None or op is None:
            rows.append({"eid": e.eid, "measured": False})
            continue
        r = {"eid": e.eid, "measured": True}
        imp = 0.0
        for nm, o in (("c", oc), ("p", op)):
            imp += o["ask_end"] - o["price"]
            r[f"fill_{nm}"] = o["filled"]
            r[f"rested_{nm}"] = o["rested"]
            r[f"tf_{nm}"] = o["tf"]
            r[f"ask_end_{nm}"] = o["ask_end"]
            r[f"price_{nm}"] = o["price"]
            for k in ("half", "mid_1", "mid_5", "mid_15", "mid_end"):
                r[f"{k}_{nm}"] = o.get(k, np.nan)
        r["imp_abs"] = imp
        rows.append(r)
    d = pd.DataFrame(rows)
    d = ev.merge(d, on="eid", how="left")
    d["imp"] = d["imp_abs"] / d["m0"]
    d["b_taker"] = (d["s0_c"] + d["s0_p"] - d["ask_end_c"] - d["ask_end_p"] - FEES) / d["m0"]
    d["b_rule"] = d["b_taker"] + d["imp"]
    d["n_fill"] = d[["fill_c", "fill_p"]].fillna(False).astype(int).sum(axis=1)
    return d


# ── features known at the decision ───────────────────────────────────────────


def gap_features(ev: pd.DataFrame, legs: dict) -> pd.DataFrame:
    """Parity-implied spot at 15:00 on the reaction session (known before the order goes in)
    and the realised close-to-close reaction (descriptive only)."""
    out = []
    for e in ev.itertuples(index=False):
        lc, lp = legs.get((e.eid, "C")), legs.get((e.eid, "P"))
        qc = quote_at(lc, 0.0) if lc is not None else None
        qp = quote_at(lp, 0.0) if lp is not None else None
        s15 = e.strike + (sum(qc) - sum(qp)) / 2 if qc and qp else np.nan
        spr = ((qc[1] - qc[0]) + (qp[1] - qp[0])) if qc and qp else np.nan
        prem = (sum(qc) + sum(qp)) / 2 if qc and qp else np.nan
        out.append({
            "eid": e.eid,
            "gap15": abs(s15 / e.spot_entry - 1) if np.isfinite(s15) else np.nan,
            "spread15_prem": spr / prem if np.isfinite(spr) and prem > 0 else np.nan,
            "gap_close": abs(e.spot_exit / e.spot_entry - 1),
        })
    g = pd.DataFrame(out)
    g = ev[["eid", "implied_move"]].merge(g, on="eid")
    g["gap15_ratio"] = g["gap15"] / g["implied_move"]
    g["gap_close_ratio"] = g["gap_close"] / g["implied_move"]
    return g.drop(columns="implied_move")


# ── statistics and logging ───────────────────────────────────────────────────


def clustered_t(x: np.ndarray, dates: np.ndarray) -> float:
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    x, dates = x[ok], np.asarray(dates)[ok]
    n, mu = len(x), x.mean()
    g = pd.Series(x - mu).groupby(pd.to_datetime(dates)).sum().to_numpy()
    se = np.sqrt((g**2).sum() * (len(g) / max(len(g) - 1, 1))) / n
    return float(mu / se) if se > 0 else float("nan")


def mean_ci(x, dates):
    return date_clustered_ci(np.asarray(x, float), dates, stat=lambda v: float(np.mean(v)))


def null_pct(pop: np.ndarray, mask: np.ndarray) -> float:
    return matched_random_null(pop, mask, stat=lambda v: float(np.mean(v)), n_draws=2000).percentile


def log_trial(row: dict) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRIAL_COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in TRIAL_COLS})


def fmt(x: float) -> str:
    return f"{x:+.5f}" if np.isfinite(x) else "nan"
