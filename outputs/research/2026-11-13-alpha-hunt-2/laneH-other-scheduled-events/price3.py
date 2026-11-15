"""price3.py: round-3 windows and pricing with fixed calendar windows and a bounded exit.

Entry: latest DoltHub snapshot in D-5..D-1. Exit: earliest snapshot in D+1..D+7 sharing an expiry
>= exit + 2 days with the entry snapshot (depends on the snapshot calendar only). Strike: the
entry-chain strike nearest the entry parity forward (two-sided at entry). Buy-back: the same
strike's exit quotes when two-sided; otherwise bounded above by intrinsic at the exit forward plus
the exit ATM straddle (ask for touch, mid for mid). Controls at D-28 and D-56.

Output: windows3_priced.parquet.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from fetch_windows import chain
from fetch_windows2 import has_snap, snap
from price_windows import atm_iv, forward, load, pair

MIN_DTE_AFTER_EXIT = 2
SHIFTS = [0, -28, -56]
# "bound": intrinsic + exit ATM straddle (round 3); "smile": Black-76 on the interpolated exit
# smile plus the ATM half-spread (round 4)
EXIT_MODE = "bound"
OUT = "windows3_priced.parquet"
FORCE_MODEL = False  # reconciliation run: model-mark every exit


def bs_vega(f: float, k: float, sig: float, t: float) -> float:
    if not (sig > 0 and t > 0):
        return np.nan
    d1 = (np.log(f / k) + 0.5 * sig**2 * t) / (sig * np.sqrt(t))
    return float(f * np.exp(-0.5 * d1**2) / np.sqrt(2 * np.pi) * np.sqrt(t))


def smile_iv(p: pd.DataFrame, f: float, k: float) -> float:
    """OTM-side IV interpolated linearly in strike, flat beyond the quoted range."""
    iv = np.where(p.index.to_numpy() >= f, p["iv_C"], p["iv_P"]).astype(float)
    ks = p.index.to_numpy(float)
    ok = np.isfinite(iv) & (iv > 0)
    if not ok.any():
        return np.nan
    return float(np.interp(k, ks[ok], iv[ok]))


def black_straddle(f: float, k: float, sig: float, t: float) -> float:
    from scipy.stats import norm
    if not (np.isfinite(sig) and sig > 0 and t > 0):
        return abs(f - k)
    sd = sig * np.sqrt(t)
    d1 = (np.log(f / k) + 0.5 * sd**2) / sd
    d2 = d1 - sd
    c = f * norm.cdf(d1) - k * norm.cdf(d2)
    return float(c + (c - (f - k)))


def find_window(t: str, d: pd.Timestamp) -> dict:
    pre = [x for x in (d - pd.Timedelta(days=i) for i in range(1, 6))
           if x.weekday() < 5 and has_snap(t, x)]
    if not pre:
        return {"status": "no_entry"}
    en = pre[0]
    posts = [x for x in (d + pd.Timedelta(days=i) for i in range(1, 8))
             if x.weekday() < 5 and has_snap(t, x)]
    if not posts:
        return {"status": "no_exit", "entry": en}
    chain(t, en)
    c0 = load(t, en)
    for ex in posts:
        chain(t, ex)
        c1 = load(t, ex)
        common = sorted(e for e in set(c0["expiry"]) & set(c1["expiry"])
                        if e >= ex + pd.Timedelta(days=MIN_DTE_AFTER_EXIT))
        if common:
            return {"status": "ok", "entry": en, "exit": ex, "expiry": common[0]}
    return {"status": "no_common_expiry", "entry": en, "exit": posts[0]}


def price(t: str, en: pd.Timestamp, ex: pd.Timestamp, e: pd.Timestamp, d: pd.Timestamp) -> dict:
    c0, c1 = load(t, en), load(t, ex)
    p0, p1 = pair(c0, e), pair(c1, e)
    f0, f1 = forward(p0), forward(p1)
    if not np.isfinite(f0):
        return {"price_status": "no_entry_forward"}
    if not np.isfinite(f1):
        return {"price_status": "no_exit_forward"}
    two0 = p0[(p0["bid_C"] > 0) & (p0["bid_P"] > 0)]
    if two0.empty:
        return {"price_status": "entry_one_sided"}
    k = min(two0.index, key=lambda s: abs(s - f0))
    a = two0.loc[k]
    bid0, ask0 = a["bid_C"] + a["bid_P"], a["ask_C"] + a["ask_P"]
    mid0 = (bid0 + ask0) / 2
    bounded = True
    if (not FORCE_MODEL) and k in p1.index and p1.loc[k, "bid_C"] > 0 and p1.loc[k, "bid_P"] > 0:
        b = p1.loc[k]
        ask1 = b["ask_C"] + b["ask_P"]
        mid1 = (b["bid_C"] + b["bid_P"] + ask1) / 2
        iv1 = float(np.nanmean([b["iv_C"], b["iv_P"]]))
        bounded = False
    else:
        two1 = p1[(p1["bid_C"] > 0) & (p1["bid_P"] > 0)]
        if two1.empty:
            return {"price_status": "exit_no_two_sided_atm"}
        ka = min(two1.index, key=lambda s: abs(s - f1))
        b = two1.loc[ka]
        if EXIT_MODE == "bound":
            intr = abs(f1 - k)
            ask1 = intr + b["ask_C"] + b["ask_P"]
            mid1 = intr + (b["bid_C"] + b["bid_P"] + b["ask_C"] + b["ask_P"]) / 2
            iv1 = np.nan
        else:
            # reconciliation runs leave the traded strike out of the smile (leave-one-out)
            iv1 = smile_iv(p1.drop(index=k, errors="ignore") if FORCE_MODEL else p1, f1, k)
            mid1 = black_straddle(f1, k, iv1, (e - ex).days / 365)
            ask1 = mid1 + ((b["ask_C"] + b["ask_P"]) - (b["bid_C"] + b["bid_P"])) / 2
    m0 = 0.20 * f0 + bid0
    iv0 = float(np.nanmean([a["iv_C"], a["iv_P"]]))
    tt = (e - en).days / 365
    vega0 = 2 * bs_vega(f0, k, iv0, tt)
    exps = sorted(x for x in c0["expiry"].unique() if x > d)
    jump2 = sd2 = np.nan
    if len(exps) >= 2:
        s1, s2 = atm_iv(pair(c0, exps[0]), f0), atm_iv(pair(c0, exps[1]), f0)
        t1, t2 = (exps[0] - en).days / 365, (exps[1] - en).days / 365
        if np.isfinite(s1) and np.isfinite(s2) and t2 > t1 > 0:
            sd2 = (s2**2 * t2 - s1**2 * t1) / (t2 - t1)
            jump2 = s1**2 * t1 - sd2 * t1
    dt = (ex - en).days / 365
    impl_abs = (np.sqrt(2 / np.pi) * np.sqrt(max(jump2, 0) + max(sd2, 0) * dt)
                if np.isfinite(jump2) else np.nan)
    return {
        "price_status": "ok", "bounded_exit": bounded, "strike": k, "f0": f0, "f1": f1,
        "moneyness": k / f0 - 1, "dte_entry": (e - en).days, "bid0": bid0, "ask0": ask0,
        "mid0": mid0, "ask1": ask1, "mid1": mid1, "m0": m0,
        "pnl_touch_m0": (bid0 - ask1) / m0, "pnl_mid_m0": (mid0 - mid1) / m0,
        "pnl_touch_prem": (bid0 - ask1) / mid0, "pnl_mid_prem": (mid0 - mid1) / mid0,
        "iv0": iv0, "iv1": iv1, "crush_vp": 100 * (iv0 - iv1),
        "vega_pnl_m0": vega0 * (iv0 - iv1) / m0 if np.isfinite(iv1) else np.nan,
        "jump2": jump2,
        "impl_jump_abs": np.sqrt(2 / np.pi) * np.sqrt(max(jump2, 0)) if np.isfinite(jump2)
        else np.nan,
        "impl_abs_window": impl_abs, "real_abs": abs(np.log(f1 / f0)),
        "entry_halfspread_prem": (mid0 - bid0) / mid0,
    }


def main() -> None:
    ev = pd.read_csv("events.csv", parse_dates=["event_date"])
    ed = pd.read_parquet("earnings_dates.parquet")
    u = json.load(open("dolt_universe.json"))
    univ = set(u["2020-06-17"]) | set(u["2023-05-10"])
    w2 = pd.read_csv("windows2.csv")
    gone = set(w2.loc[w2["status"] == "symbol_not_in_dolthub", "event_id"])
    recs = []
    for _, e in ev.iterrows():
        if not (pd.Timestamp("2019-01-07") <= e["event_date"] <= pd.Timestamp("2024-11-08")):
            continue
        base = {"event_id": e["event_id"], "ticker": e["ticker"], "category": e["category"],
                "sub": e["sub"], "material": e["material"], "orig_date": e["event_date"]}
        if e["event_id"] in gone and e["ticker"] not in univ:
            recs.append({**base, "shift": 0, "event_date": e["event_date"],
                         "status": "symbol_not_in_dolthub"})
            continue
        for s in SHIFTS:
            d = e["event_date"] + pd.Timedelta(days=s)
            w = find_window(e["ticker"], d)
            rec = {**base, "shift": s, "event_date": d, **w}
            if w["status"] == "ok":
                rec.update(price(e["ticker"], w["entry"], w["exit"], w["expiry"], d))
                et = ed.loc[ed["ticker"] == e["ticker"], "edate"]
                rec["earn_screened"] = len(et) > 0
                rec["earn_in_window"] = bool(((et >= w["entry"]) & (et <= w["exit"])).any())
                oth = ev.loc[ev["ticker"] == e["ticker"], "event_date"]
                rec["other_event_in_window"] = bool(s != 0 and (
                    (oth >= w["entry"] - pd.Timedelta(days=2))
                    & (oth <= w["exit"] + pd.Timedelta(days=2))).any())
            recs.append(rec)
            if s == 0 and rec.get("price_status") != "ok":
                break
        json.dump(snap, open("snap_cache.json", "w"))
    out = pd.DataFrame(recs)
    out["price_status"] = out["price_status"].fillna(out["status"])
    out["block"] = np.where(out["orig_date"] < "2022-01-01", "disc_2019_21", "held_2022_24")
    out.to_parquet(OUT)
    for cat, g in out.groupby("category"):
        e0 = g[g["shift"] == 0]
        ok = e0[e0["price_status"] == "ok"]
        print(f"\n== {cat}: ticker-events {len(e0)}")
        print(e0["price_status"].value_counts().to_string())
        print("priced", len(ok), "| bounded exit", int(ok["bounded_exit"].sum()),
              "| earnings in window", int(ok["earn_in_window"].sum()))
        print(ok.groupby("block").size().to_string())
        c = g[(g["shift"] != 0)]
        print("controls", len(c), "priced", int((c["price_status"] == "ok").sum()),
              "| earnings", int(c["earn_in_window"].fillna(False).sum()),
              "| other event", int(c["other_event_in_window"].fillna(False).sum()),
              "| bounded", int(c["bounded_exit"].fillna(False).sum()))


if __name__ == "__main__":
    main()
