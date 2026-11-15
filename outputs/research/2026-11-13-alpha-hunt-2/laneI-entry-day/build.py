"""
build.py
Lane I (entry day): price the earlier-entry hedged hold against the standard entry, per event.

For each hedged-hold event (status ok) the standard arm ``S0`` sells the front ATM straddle at the
15:59 bid on the entry session D0 (Databento, the project's base trade). Each early arm ``D{k}``
sells the same expiry at the DoltHub end-of-day bid k sessions earlier (k = 0..10; ``D0`` is the
same-day DoltHub quote and serves as a same-source control), at the strike nearest the parity
forward on that day. Every arm is then delta-hedged with stock at every close from its entry close
to the session before expiry and settles at intrinsic, with the costs of
``research.hedged_hold.hedged_short_straddle`` (CRSP half-spread per hedge change, floored; option
fee; disposal). Pre-event closes hedge at the arm's own entry straddle IV; from the reaction
session on, at the straddle IV of the arm's strike on the reaction-session 15:59 chain (fallback
``s2_iv``), the rule of the 2026-11-02 study.

P&L is split into the run-up (entry to the D0 15:59 mark), the event (D0 15:59 to the reaction
session 15:59) and the post-event segment (to settlement), marked at Databento mids. All P&L is
per share divided by the standard m0 (0.20 x front forward + 15:59 front bid premium).

Checks: the per-arm loop reconciles to ``hedged_short_straddle`` to 1e-9, and a replica of the
2026-11-02 arm (hedge from the reaction close only) reconciles to that study's ``H`` column.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/build.py --set discovery
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/build.py --set heldout

References
----------
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. (2019) Option pricing of earnings
announcement risks. RFS 32(2).
Gao, C., Xing, Y. and Zhang, X. (2018) Anticipating uncertainty: straddles around earnings
announcements. JFQA 53(6).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402
from earnings_iv_crush.research.hedged_hold import (  # noqa: E402
    hedged_short_straddle,
    straddle_delta,
    straddle_iv,
    year_frac,
)
from pull import K_MAX, cached, shift  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "hold_study", ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "study.py"
)
hold = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hold)

FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
FEE = HEDGED.fee_per_contract_leg / 100.0
FLOOR = HEDGED.equity_cost_floor_bps / 1e4
FWD_TOL = 0.05  # parity forward vs CRSP close on the entry day; beyond 5% the quote is not that day
_FWD: dict[tuple, float] = {}  # reaction-session parity forward, one read per event


# ── chains ──────────────────────────────────────────────────────────────────


def databento_chain(ticker: str, day: pd.Timestamp) -> pd.DataFrame | None:
    """Last 15:59 record per contract (raw, zero bids kept) for one session."""
    p = hold.CHAINS / f"{ticker}_{day.date()}.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["symbol", "bid_px_00", "ask_px_00"]).reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d.sort_values("ts_recv").groupby(["expiry", "strike", "right"], as_index=False).last()
    return d.rename(columns={"bid_px_00": "bid", "ask_px_00": "ask"})[
        ["expiry", "strike", "right", "bid", "ask"]
    ]


def straddle_mid(ch: pd.DataFrame | None, expiry: pd.Timestamp, k: float) -> float:
    """Two-sided straddle mid at one strike, NaN if either leg is one-sided or absent."""
    if ch is None:
        return float("nan")
    s = ch[(ch["expiry"] == expiry) & np.isclose(ch["strike"], k)]
    if set(s["right"]) != {"C", "P"} or len(s) != 2:
        return float("nan")
    if (s["bid"] <= 0).any() or (s["ask"] < s["bid"]).any():
        return float("nan")
    return float((s["bid"] + s["ask"]).sum() / 2)


def dolthub_atm(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> dict | str:
    """ATM straddle on ``expiry`` from the DoltHub snapshot of ``day``, or a funnel reason."""
    p = cached(ticker, day)
    if p is None:
        return "no_snapshot_file"
    ch = pd.read_parquet(p)
    if ch.empty:
        return "empty_snapshot"
    ch = ch[ch["expiry"] == expiry]
    if ch.empty:
        return "expiry_absent"
    two = ch[(ch["bid"] > 0) & (ch["ask"] >= ch["bid"])].copy()
    two["mid"] = (two["bid"] + two["ask"]) / 2
    piv = two.pivot_table(index="strike", columns="right", values="mid", aggfunc="first")
    if not {"C", "P"} <= set(piv.columns) or piv.dropna().empty:
        return "no_two_sided_pair"
    piv = piv.dropna()
    k0 = float((piv["C"] - piv["P"]).abs().idxmin())
    fwd = float(k0 + piv.loc[k0, "C"] - piv.loc[k0, "P"])
    if fwd <= 0:
        return "bad_forward"
    k = float(piv.index[np.argmin(np.abs(piv.index.to_numpy(float) - fwd))])
    legs = two[two["strike"] == k].set_index("right")
    bid = float(legs["bid"].sum())
    ask = float(legs["ask"].sum())
    mid = (bid + ask) / 2
    t = year_frac(day, expiry)
    return {
        "strike": k,
        "fwd": fwd,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "iv": straddle_iv(mid, fwd, k, t),
        "n_expiries_snapshot": int(pd.read_parquet(p)["expiry"].nunique()),
    }


# ── one arm ─────────────────────────────────────────────────────────────────


def simulate(
    *,
    g: pd.DataFrame,
    entry: pd.Timestamp,
    hedge_from: pd.Timestamp,
    d0: pd.Timestamp,
    t1: pd.Timestamp,
    expiry_last: pd.Timestamp,
    expiry: pd.Timestamp,
    k: float,
    fwd: float,
    bid: float,
    mid: float,
    sig_pre: float,
    sig_post: float,
) -> dict:
    """Hedged short straddle with P&L split by segment; reconciled to the library function."""
    sess = g.loc[hedge_from:expiry_last]
    closes = sess["prc"].to_numpy(float)
    rets = np.append(sess["ret"].to_numpy(float)[1:], np.nan)[:-1]
    cl = closes[:-1]
    days = sess.index[:-1]
    settle = float(closes[-1])
    taus = np.array([year_frac(d, expiry) for d in days])
    sig = np.where(days <= d0, sig_pre, sig_post)
    hs = ((sess["ask"] - sess["bid"]) / 2 / sess["prc"]).to_numpy(float)[:-1]
    seg = np.where(days < d0, "runup", np.where(days == d0, "event", "post"))
    out = {"runup_hedge": 0.0, "event_hedge": 0.0, "post_hedge": 0.0}
    cost = {"runup": 0.0, "event": 0.0, "post": 0.0}
    hp, h_prev, tot_cost = 0.0, 0.0, 0.0
    for i in range(len(cl)):
        h = straddle_delta(cl[i], k, taus[i], sig[i])
        c = abs(h - h_prev) * cl[i] * max(hs[i], FLOOR)
        pnl = h * cl[i] * rets[i]
        out[f"{seg[i]}_hedge"] += pnl
        cost[seg[i]] += c
        hp += pnl
        tot_cost += c
        h_prev = h
    unwind = abs(h_prev) * settle * max(hs[-1], FLOOR) if len(cl) else 0.0
    cost["post"] += unwind
    tot_cost += unwind
    intrinsic = abs(settle - k)
    disposal = HEDGED.disposal_bps / 1e4 * settle if intrinsic > 0 else 0.0
    net = bid - intrinsic + hp - tot_cost - 2 * FEE - disposal
    if len(cl):
        ref = hedged_short_straddle(
            sale_price=bid,
            sale_mid=mid,
            strike=k,
            fwd=fwd,
            closes=cl,
            rets=rets,
            taus=taus,
            sigmas=sig,
            half_spreads=hs,
            settle_close=settle,
        )
        if abs(ref.net_pnl - net) > 1e-9:
            raise AssertionError(f"segment loop {net} != library {ref.net_pnl}")
    return {
        "net": net,
        "gross_mid": mid - intrinsic + hp,
        "hedge_pnl": hp,
        "equity_cost": tot_cost,
        "disposal": disposal,
        "intrinsic": intrinsic,
        "settle": settle,
        **out,
        **{f"{s}_cost": v for s, v in cost.items()},
    }


# ── one event ───────────────────────────────────────────────────────────────


def post_sigma(t: str, t1: pd.Timestamp, exp: pd.Timestamp, k: float, s2_iv: float) -> float:
    """Study rule: straddle IV of strike ``k`` on the reaction-session chain, else ``s2_iv``."""
    q = hold.exit_quotes(t, t1, k, exp)
    if q.get("status") == "ok" and min(q["bid_C"], q["bid_P"]) > 0:
        mid = (q["bid_C"] + q["ask_C"] + q["bid_P"] + q["ask_P"]) / 2
        key = (t, t1, exp)
        if key not in _FWD:
            _FWD[key] = hold.exit_fwd(t, t1, exp)
        fx = _FWD[key]
        if np.isfinite(fx):
            s = straddle_iv(mid, fx, k, year_frac(t1, exp))
            if np.isfinite(s):
                return s
    return float(s2_iv) if np.isfinite(s2_iv) else float("nan")


def build_event(r: pd.Series, f: pd.Series, crsp: dict) -> list[dict]:
    t, d0, t1 = r["ticker"], pd.Timestamp(r["entry_date"]), pd.Timestamp(r["exit_date"])
    exp = pd.Timestamp(r["expiry"])
    base = {"ticker": t, "entry_date": d0, "exit_date": t1, "expiry": exp, "m0": r["m0"]}
    start = shift(d0, -K_MAX)
    st, g = hold.stock_path(crsp, f["permno"], start, exp)
    if st != "ok" or g is None:
        return [{**base, "arm": "event", "status": f"path_{st}"}]
    expiry_last = g.index[-1]
    ch0 = databento_chain(t, d0)
    ch1 = databento_chain(t, t1)
    s2 = float(f.get("s2_iv", np.nan))
    rows = []

    # replica of the 2026-11-02 H (hedge from the reaction close only)
    rep_sig = post_sigma(t, t1, exp, float(f["front_strike"]), s2)
    rep = simulate(
        g=g,
        entry=d0,
        hedge_from=t1,
        d0=d0,
        t1=t1,
        expiry_last=expiry_last,
        expiry=exp,
        k=float(f["front_strike"]),
        fwd=float(f["front_fwd"]),
        bid=float(f["front_bid"]),
        mid=float(f["front_mid"]),
        sig_pre=rep_sig,
        sig_post=rep_sig,
    )
    rows.append({**base, "arm": "REP", "status": "ok", "k": 0, "net_m0": rep["net"] / r["m0"]})

    specs: list[tuple[str, int, dict | str]] = []
    specs.append(
        (
            "S0",
            0,
            {
                "strike": float(f["front_strike"]),
                "fwd": float(f["front_fwd"]),
                "bid": float(f["front_bid"]),
                "ask": float(f["front_ask"]),
                "mid": float(f["front_mid"]),
                "iv": straddle_iv(
                    float(f["front_mid"]),
                    float(f["front_fwd"]),
                    float(f["front_strike"]),
                    year_frac(d0, exp),
                ),
                "n_expiries_snapshot": np.nan,
            },
        )
    )
    for k in range(K_MAX + 1):
        day = shift(d0, -k)
        specs.append((f"D{k}", k, dolthub_atm(t, day, exp)))

    for arm, k, q in specs:
        day = shift(d0, -k)
        if isinstance(q, str):
            rows.append({**base, "arm": arm, "k": k, "entry": day, "status": q})
            continue
        if abs(q["fwd"] / float(g.loc[day, "prc"]) - 1.0) > FWD_TOL:
            rows.append({**base, "arm": arm, "k": k, "entry": day, "status": "fwd_mismatch"})
            continue
        if not np.isfinite(q["iv"]):
            rows.append({**base, "arm": arm, "k": k, "entry": day, "status": "no_entry_iv"})
            continue
        sp = post_sigma(t, t1, exp, q["strike"], s2)
        if not np.isfinite(sp):
            rows.append({**base, "arm": arm, "k": k, "entry": day, "status": "no_post_sigma"})
            continue
        res = simulate(
            g=g,
            entry=day,
            hedge_from=day,
            d0=d0,
            t1=t1,
            expiry_last=expiry_last,
            expiry=exp,
            k=q["strike"],
            fwd=q["fwd"],
            bid=q["bid"],
            mid=q["mid"],
            sig_pre=q["iv"],
            sig_post=sp,
        )
        mark0 = straddle_mid(ch0, exp, q["strike"]) if arm != "S0" else q["mid"]
        mark1 = straddle_mid(ch1, exp, q["strike"])
        m0 = r["m0"]
        row = {
            **base,
            "arm": arm,
            "k": k,
            "entry": day,
            "status": "ok",
            "strike": q["strike"],
            "fwd": q["fwd"],
            "bid": q["bid"],
            "ask": q["ask"],
            "mid": q["mid"],
            "iv_entry": q["iv"],
            "sig_post": sp,
            "n_exp_snap": q["n_expiries_snapshot"],
            "half_spread_prem": (q["ask"] - q["bid"]) / 2 / q["mid"],
            "half_spread_m0": (q["ask"] - q["bid"]) / 2 / m0,
            "net_m0": res["net"] / m0,
            "gross_mid_m0": res["gross_mid"] / m0,
            "prem_m0": q["mid"] / m0,
            "mark_d0": mark0,
            "mark_t1": mark1,
            # segment P&L of the short at Databento mid marks, hedge and costs by segment
            "seg_runup_m0": (q["mid"] - mark0 + res["runup_hedge"] - res["runup_cost"]) / m0,
            "seg_event_m0": (mark0 - mark1 + res["event_hedge"] - res["event_cost"]) / m0,
            "seg_post_m0": (
                mark1 - res["intrinsic"] + res["post_hedge"] - res["post_cost"] - res["disposal"]
            )
            / m0,
            "entry_spread_m0": -(q["mid"] - q["bid"]) / m0,
            "fees_m0": -2 * FEE / m0,
            "runup_hedge_m0": res["runup_hedge"] / m0,
            "runup_cost_m0": res["runup_cost"] / m0,
            "abs_runup_move": abs(float(g.loc[d0, "prc"]) / float(g.loc[day, "prc"]) - 1.0),
        }
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build lane I arms")
    ap.add_argument("--set", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    ev = pd.read_csv(HERE / f"events_{a.set}.csv", parse_dates=["entry_date"])
    h = pd.read_parquet(hold.OUT / "events.parquet")
    h["entry_date"] = pd.to_datetime(h["entry_date"])
    h = h[h["status"] == "ok"].merge(ev, on=["ticker", "entry_date"], how="inner")
    feats = pd.read_parquet(FEATURES)
    feats["entry_date"] = pd.to_datetime(feats["entry_date"])
    feats = feats.drop_duplicates(["ticker", "entry_date"]).set_index(["ticker", "entry_date"])
    print(f"  events {len(ev)} -> joined to hold ok {len(h)}")
    crsp = hold.load_crsp()
    rows: list[dict] = []
    for i, (_, r) in enumerate(h.iterrows()):
        rows.extend(build_event(r, feats.loc[(r["ticker"], r["entry_date"])], crsp))
        if (i + 1) % 200 == 0:
            print(f"  built {i + 1}/{len(h)}", flush=True)
    d = pd.DataFrame(rows)
    d = d.merge(
        h[["ticker", "entry_date", "H", "B", "b_defined"]], on=["ticker", "entry_date"], how="left"
    )
    rep = d[d["arm"] == "REP"]
    gap = (rep["net_m0"] - rep["H"]).abs()
    print(f"  replica vs study H: max abs gap {gap.max():.2e} over {len(rep)} events")
    if gap.max() > 1e-6:
        raise AssertionError("replica does not reconcile to the 2026-11-02 H")
    print("  funnel by arm:")
    tab = d.groupby(["arm", "status"]).size().unstack(fill_value=0)
    print(tab.to_string())
    d.to_parquet(HERE / f"arms_{a.set}.parquet")
    print(f"  wrote arms_{a.set}.parquet  {Counter(d['status'])}")


if __name__ == "__main__":
    main()
