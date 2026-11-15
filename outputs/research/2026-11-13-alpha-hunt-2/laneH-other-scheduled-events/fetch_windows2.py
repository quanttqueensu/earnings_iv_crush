"""fetch_windows2.py: round-2 window search that survives DoltHub expiry rotation and strike drift.

For each window centred on D: entry candidates are the two latest snapshots in D-8..D-1, exit
candidates the two earliest in D+1..D+7. Pairs are tried in order (latest entry, earliest exit);
the first pair sharing an expiry >= exit + 2 days with a strike within ATM_TOL of the entry parity
forward is kept. Controls (D-28, D-56) are searched for every event whose own window prices.
Symbols outside the DoltHub universe that had no snapshot in round 1 are not re-queried.

Output: windows2.csv, snap_cache.json (date presence), chains/ (shared cache).
"""
from __future__ import annotations

import json
import os

import pandas as pd

from fetch_windows import chain, q
from price_windows import forward, load, pair

ATM_TOL = 0.03
MIN_DTE_AFTER_EXIT = 2
SHIFTS = [0, -28, -56]
CACHE = "snap_cache.json"
snap = json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def has_snap(t: str, d: pd.Timestamp) -> bool:
    key = f"{t}|{d:%Y-%m-%d}"
    if key not in snap:
        rows = q(f"select count(*) n from option_chain where date='{d:%Y-%m-%d}' "
                 f"and act_symbol='{t}'")
        snap[key] = int(rows[0]["n"]) > 0
    return snap[key]


def cands(t: str, days: list[pd.Timestamp], k: int = 2) -> list[pd.Timestamp]:
    out = []
    for d in days:
        if d.weekday() < 5 and has_snap(t, d):
            out.append(d)
            if len(out) == k:
                break
    return out


def pair_ok(t: str, en: pd.Timestamp, ex: pd.Timestamp) -> bool:
    chain(t, en)
    chain(t, ex)
    c0, c1 = load(t, en), load(t, ex)
    for e in sorted(set(c0["expiry"]) & set(c1["expiry"])):
        if e < ex + pd.Timedelta(days=MIN_DTE_AFTER_EXIT):
            continue
        p0, p1 = pair(c0, e), pair(c1, e)
        f0 = forward(p0)
        if not pd.notna(f0):
            continue
        ks = set(p0.index) & set(p1.index)
        if any(abs(k / f0 - 1) <= ATM_TOL for k in ks):
            return True
    return False


def window(t: str, d: pd.Timestamp) -> dict:
    pre = cands(t, [d - pd.Timedelta(days=i) for i in range(1, 9)])
    if not pre:
        return {"entry": pd.NaT, "exit": pd.NaT, "status": "no_entry"}
    post = cands(t, [d + pd.Timedelta(days=i) for i in range(1, 8)])
    if not post:
        return {"entry": pd.NaT, "exit": pd.NaT, "status": "no_exit"}
    for en in pre:
        for ex in post:
            if pair_ok(t, en, ex):
                return {"entry": en, "exit": ex, "status": "ok"}
    return {"entry": pre[0], "exit": post[0], "status": "no_atm_common_contract"}


def main() -> None:
    ev = pd.read_csv("events.csv", parse_dates=["event_date"])
    u = json.load(open("dolt_universe.json"))
    univ = set(u["2020-06-17"]) | set(u["2023-05-10"])
    r1 = pd.read_csv("windows.csv")
    r1_0 = r1[r1["shift"] == 0].set_index("event_id")["status"]
    recs = []
    for i, e in ev.iterrows():
        if not (pd.Timestamp("2019-01-07") <= e["event_date"] <= pd.Timestamp("2024-11-08")):
            continue
        if e["ticker"] not in univ and r1_0.get(e["event_id"]) == "no_entry":
            recs.append({"event_id": e["event_id"], "ticker": e["ticker"], "shift": 0,
                         "event_date": e["event_date"], "entry": pd.NaT, "exit": pd.NaT,
                         "status": "symbol_not_in_dolthub"})
            continue
        st0 = None
        for s in SHIFTS:
            if s and st0 != "ok":
                break
            d = e["event_date"] + pd.Timedelta(days=s)
            try:
                w = window(e["ticker"], d)
            except RuntimeError as exc:
                print("ERROR", e["event_id"], s, exc, flush=True)
                w = {"entry": pd.NaT, "exit": pd.NaT, "status": "error"}
            st0 = w["status"] if s == 0 else st0
            recs.append({"event_id": e["event_id"], "ticker": e["ticker"], "shift": s,
                         "event_date": d, **w})
        pd.DataFrame(recs).to_csv("windows2.csv", index=False)
        json.dump(snap, open(CACHE, "w"))
        print(f"{i+1}/{len(ev)} {e['event_id']} {e['ticker']} {st0}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
