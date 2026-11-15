"""stage_b_options.py: trials 2476-2477, short bank straddles over the stress-test window on DoltHub.

Pre-registered in diagnosis.log entry 1. Per cycle 2020-2026 and per primary bank: entry at the
last DoltHub end-of-day snapshot on or before the results day, exit at the first snapshot on or
after the session following the capital-action night; controls shift both dates by -28 and -35
calendar days. Traded contract: nearest common expiry at least two days after exit that ends
before the name's next earnings date, strike the common strike nearest the entry parity forward
within 3%. Short straddle sold at the entry bid, bought back at the exit ask.

``--fetch`` pulls chains from DoltHub's public API (no key, one request a second). Without it the
script scores from the local chains/ cache only. ``--block discovery`` (default) scores 2020-2022;
``--block heldout`` is reserved for the frozen held-out read and refuses to run unless the freeze
note exists.

Usage
-----
    python stage_b_options.py --fetch
    python stage_b_options.py --block discovery
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, ROOT)
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

import dolt  # noqa: E402

PRIMARY = ["JPM", "BAC", "C", "WFC", "GS", "MS", "USB", "PNC", "COF", "STT"]
SHIFTS = [0, -28, -35]
SEARCH_DAYS = 5
MIN_DTE_AFTER_EXIT = 2
ATM_TOL = 0.03
DISCOVERY_CYCLES = {"2020", "2020b", "2021", "2022"}
FREEZE = os.path.join(HERE, "freeze_stage_b.md")
# round 1 excluded any traded expiry spanning the next earnings date; on DoltHub that removed
# every June cycle (diagnosis.log entry 6), so round 2 applies no earnings rule to either leg
EARNINGS_RULE = os.environ.get("N14_EARNINGS_RULE", "allow")


def mean(x: np.ndarray) -> float:
    return float(np.mean(x))


def earnings_dates() -> dict[str, list[pd.Timestamp]]:
    out: dict[str, list[pd.Timestamp]] = {}
    for f in os.listdir(os.path.join(ROOT, "data/cache/backfill_chains")):
        t, d = f[:-8].rsplit("_", 1)
        out.setdefault(t, []).append(pd.Timestamp(d))
    for f in ["earnings_compustat", "earnings_dolthub"]:
        e = pd.read_parquet(os.path.join(ROOT, f"data/cache/dolthub_p2/{f}.parquet"))
        for t, d in zip(e["ticker"], e["announce_date"]):
            out.setdefault(t, []).append(pd.Timestamp(d))
    e = pd.read_parquet(os.path.join(
        ROOT, "outputs/research/2026-11-13-alpha-hunt-2/laneH-other-scheduled-events/"
        "earnings_dates.parquet"))
    for t, d in zip(e["ticker"], e["edate"]):
        out.setdefault(t, []).append(pd.Timestamp(d))
    return {t: sorted(set(v)) for t, v in out.items()}


def windows() -> pd.DataFrame:
    cal = pd.read_csv(os.path.join(HERE, "stress_calendar.csv"))
    cal["night"] = pd.to_datetime(cal["night"])
    cal = cal[cal["night"] >= "2020-01-01"]
    bd = pd.offsets.BDay()
    rows = []
    for cyc, g in cal.groupby("cycle"):
        d = g["night"].min()
        last = g["night"].max()
        exit_target = last + bd
        for s in SHIFTS:
            sh = pd.Timedelta(days=s)
            rows.append({"cycle": str(cyc), "shift": s, "D": d + sh, "exit_target": exit_target + sh})
    return pd.DataFrame(rows)


def find_snap(t: str, start: pd.Timestamp, backward: bool, fetch: bool) -> pd.Timestamp | None:
    days = [start - pd.Timedelta(days=k) if backward else start + pd.Timedelta(days=k)
            for k in range(SEARCH_DAYS + 1)]
    for d in days:
        if d.weekday() >= 5:
            continue
        key = f"{t}|{d:%Y-%m-%d}"
        if fetch:
            dolt.cover(d, PRIMARY)
        if key not in dolt._snap and not fetch:
            continue
        if dolt.has_snap(t, d):
            return d
    return None


def pair(c: pd.DataFrame, e: pd.Timestamp) -> pd.DataFrame:
    x = c[c["expiry"] == e]
    p = x.pivot_table(index="strike", columns="right", values=["bid", "ask", "iv"], aggfunc="first")
    p.columns = [f"{a}_{b}" for a, b in p.columns]
    need = ["bid_C", "ask_C", "bid_P", "ask_P", "iv_C", "iv_P"]
    if not set(need) <= set(p.columns):
        return pd.DataFrame(columns=need)
    return p[need].dropna(subset=["ask_C", "ask_P"])


def forward(p: pd.DataFrame) -> float:
    two = p[(p["bid_C"] > 0) & (p["bid_P"] > 0)]
    if two.empty:
        return np.nan
    mc, mp = (two["bid_C"] + two["ask_C"]) / 2, (two["bid_P"] + two["ask_P"]) / 2
    k = (mc - mp).abs().idxmin()
    return float(k + mc[k] - mp[k])


def price(t: str, en: pd.Timestamp, ex: pd.Timestamp, next_earn: pd.Timestamp | None) -> dict:
    c0, c1 = dolt.chain(t, en), dolt.chain(t, ex)
    common = sorted(set(c0["expiry"]) & set(c1["expiry"]))
    common = [e for e in common if e >= ex + pd.Timedelta(days=MIN_DTE_AFTER_EXIT)]
    if not common:
        return {"status": "no_common_expiry"}
    if next_earn is not None and EARNINGS_RULE == "exclude":
        common = [e for e in common if e < next_earn]
        if not common:
            return {"status": "all_expiries_span_earnings"}
    for e in common:
        p0, p1 = pair(c0, e), pair(c1, e)
        f0, f1 = forward(p0), forward(p1)
        if not (np.isfinite(f0) and np.isfinite(f1)):
            continue
        ks = sorted(set(p0.index) & set(p1.index))
        if not ks:
            continue
        k = min(ks, key=lambda s: abs(s - f0))
        if abs(k / f0 - 1) > ATM_TOL:
            continue
        a, b = p0.loc[k], p1.loc[k]
        if not (a["bid_C"] > 0 and a["bid_P"] > 0):
            return {"status": "entry_one_sided"}
        bid0, ask0 = a["bid_C"] + a["bid_P"], a["ask_C"] + a["ask_P"]
        ask1 = b["ask_C"] + b["ask_P"]
        two1 = b["bid_C"] > 0 and b["bid_P"] > 0
        mid0 = (bid0 + ask0) / 2
        mid1 = (b["bid_C"] + b["bid_P"] + ask1) / 2 if two1 else np.nan
        m0 = 0.20 * f0 + bid0
        return {"status": "ok", "expiry": e, "strike": k, "f0": f0, "f1": f1,
                "dte_entry": (e - en).days, "bid0": bid0, "ask0": ask0, "mid0": mid0,
                "ask1": ask1, "mid1": mid1, "m0": m0,
                "pnl_touch_m0": (bid0 - ask1) / m0, "pnl_mid_m0": (mid0 - mid1) / m0,
                "pnl_touch_prem": (bid0 - ask1) / mid0,
                "half_spread_prem": (mid0 - bid0) / mid0,
                "iv0": float(np.mean([a["iv_C"], a["iv_P"]])),
                "iv1": float(np.mean([b["iv_C"], b["iv_P"]])),
                "real_abs": abs(np.log(f1 / f0)),
                "spans_earnings": bool(next_earn is not None and e >= next_earn)}
    return {"status": "no_atm_common_contract"}


def build(fetch: bool, cycles: set[str] | None = None) -> pd.DataFrame:
    earn = earnings_dates()
    rows = []
    for _, w in windows().iterrows():
        if cycles is not None and w["cycle"] not in cycles:
            continue
        for t in PRIMARY:
            r = {"ticker": t, **w.to_dict()}
            en = find_snap(t, w["D"], backward=True, fetch=fetch)
            ex = find_snap(t, w["exit_target"], backward=False, fetch=fetch) if en else None
            if en is None or ex is None:
                r["status"] = "no_entry_snapshot" if en is None else "no_exit_snapshot"
                rows.append(r)
                continue
            nxt = [d for d in earn.get(t, []) if d > ex]
            r.update({"entry": en, "exit": ex, "next_earn": nxt[0] if nxt else pd.NaT})
            r.update(price(t, en, ex, nxt[0] if nxt else None))
            rows.append(r)
    d = pd.DataFrame(rows)
    if fetch:
        d.to_csv(os.path.join(HERE, "stage_b_rows.csv"), index=False)
    return d


def score(d: pd.DataFrame, block: str) -> None:
    if block == "heldout" and not os.path.exists(FREEZE):
        raise SystemExit("held-out read refused: freeze_stage_b.md does not exist")
    cyc = DISCOVERY_CYCLES if block == "discovery" else set(d["cycle"]) - DISCOVERY_CYCLES
    d = d[d["cycle"].isin(cyc)].copy()
    print(f"== block {block}: cycles {sorted(cyc)}")
    print("funnel (status by shift):")
    print(d.pivot_table(index="status", columns="shift", values="ticker", aggfunc="count",
                        fill_value=0).to_string())
    ok = d[d["status"] == "ok"].copy()
    ok["d_iv_vp"] = 100 * (ok["iv1"] - ok["iv0"])
    ev = ok[ok["shift"] == 0].set_index(["ticker", "cycle"])
    ct = ok[ok["shift"] != 0].groupby(["ticker", "cycle"])[
        ["pnl_touch_m0", "pnl_mid_m0", "d_iv_vp", "half_spread_prem", "real_abs"]].mean()
    j = ev.join(ct, rsuffix="_ctrl", how="inner").reset_index()
    print(f"event windows priced {len(ev)}, with at least one priced control {len(j)}")
    dropped = d[(d["shift"] == 0) & (d["status"] != "ok")]
    print(f"event windows dropped {len(dropped)}: {dropped['status'].value_counts().to_dict()}")
    if j.empty:
        print("nothing to score")
        return
    key = pd.to_datetime(j["D"])
    out = {}
    for name, v in [
        ("event level, net at touch, share of m0", j["pnl_touch_m0"]),
        ("event level, gross at mid, share of m0", j["pnl_mid_m0"]),
        ("trial 2476: event minus control, net at touch, share of m0",
         j["pnl_touch_m0"] - j["pnl_touch_m0_ctrl"]),
        ("event minus control, gross at mid, share of m0", j["pnl_mid_m0"] - j["pnl_mid_m0_ctrl"]),
        ("trial 2477: IV change event minus control, vol points", j["d_iv_vp"] - j["d_iv_vp_ctrl"]),
        ("IV change event, vol points", j["d_iv_vp"]),
        ("entry half-spread, share of mid premium, event", j["half_spread_prem"]),
        ("entry half-spread, share of mid premium, controls", j["half_spread_prem_ctrl"]),
        ("realised |log move| entry to exit, event", j["real_abs"]),
        ("realised |log move| entry to exit, controls", j["real_abs_ctrl"]),
    ]:
        ci = date_clustered_ci(v, key, stat=mean)
        out[name] = ci
        print(f"{name}: {ci.point:+.4f} [{ci.low:+.4f}, {ci.high:+.4f}] N={ci.n} "
              f"clusters={ci.clusters}")
    print("per cycle (means):")
    j["ev_minus_ctrl"] = j["pnl_touch_m0"] - j["pnl_touch_m0_ctrl"]
    print(j.groupby("cycle")[["pnl_touch_m0", "pnl_touch_m0_ctrl", "ev_minus_ctrl", "d_iv_vp",
                              "d_iv_vp_ctrl", "dte_entry", "half_spread_prem"]]
          .mean().round(4).to_string())
    j.to_csv(os.path.join(HERE, f"stage_b_scored_{block}_{EARNINGS_RULE}.csv"), index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--block", default="discovery", choices=["discovery", "heldout"])
    a = ap.parse_args()
    if a.fetch:
        build(True)
        return
    if a.block == "heldout" and not os.path.exists(FREEZE):
        raise SystemExit("held-out read refused: freeze_stage_b.md does not exist")
    cyc = DISCOVERY_CYCLES if a.block == "discovery" else None
    score(build(False, cyc), a.block)


if __name__ == "__main__":
    main()
