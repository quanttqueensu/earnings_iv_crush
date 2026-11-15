"""
legs.py
Lane B, per-leg strike choice: for each event, the four two-strike combinations of the call and
the put on the two strikes that bracket the entry parity forward (K_lo <= fwd < K_hi), each
hedge-held to expiry by the frozen smile-strike builder ``build_g`` (equal strikes give the
straddle). Decision time: the last 15:59 ET record of the entry chain.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneB-contract-choice/legs.py [LIMIT]
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import build as bd  # noqa: E402  (loads the frozen modules and the read cache)

sm, st = bd.sm, bd.st
COMBOS = {"ll": ("lo", "lo"), "hh": ("hi", "hi"), "hl": ("hi", "lo"), "lh": ("lo", "hi")}


def legs_one(e: pd.Series, crsp: dict) -> dict:
    out: dict = {"ticker": e["ticker"], "entry_date": e["entry_date"]}
    exp, t0 = pd.Timestamp(e["expiry"]), pd.Timestamp(e["entry_date"])
    fwd0 = (e["m0"] - e["s0"]) / st.MARGIN_SPOT_FRAC
    c0 = sm.chain(e["ticker"], t0, exp)
    if c0 is None:
        return {**out, "lstatus": "no_entry_chain"}
    two = c0[(c0["bid"] > 0) & (c0["ask"] > 0)]
    calls, puts = two[two["right"] == "C"].set_index("strike"), two[two["right"] == "P"].set_index(
        "strike"
    )
    ks = np.array(sorted(set(calls.index) & set(puts.index)), float)
    lo, hi = ks[ks <= fwd0], ks[ks > fwd0]
    if lo.size == 0 or hi.size == 0:
        return {**out, "lstatus": "no_bracket"}
    kk = {"lo": float(lo.max()), "hi": float(hi.min())}
    out["lstatus"] = "ok"
    out["k_lo"], out["k_hi"], out["fwd"] = kk["lo"], kk["hi"], fwd0
    for side in ("lo", "hi"):
        for r, tab in (("C", calls), ("P", puts)):
            q = tab.loc[kk[side]]
            out[f"{r}{side}_bid"], out[f"{r}{side}_ask"] = float(q["bid"]), float(q["ask"])
    for lab, (cs, ps) in COMBOS.items():
        kc, kp = kk[cs], kk[ps]
        cl = c0[(c0["right"] == "C") & np.isclose(c0["strike"], kc)].iloc[-1]
        pt = c0[(c0["right"] == "P") & np.isclose(c0["strike"], kp)].iloc[-1]
        sm.pick_wings = lambda c, fw, im, _a=cl, _b=pt: (_a, _b)
        g = sm.build_g(e, crsp)
        out[f"{lab}_status"] = g["status"]
        if g["status"] == "ok":
            out[f"{lab}_usd"] = float(g["G"] * g["mg"])
            out[f"{lab}_usd_mid"] = float(g["G_mid"] * g["mg"])
            out[f"{lab}_mg"] = float(g["mg"])
            out[f"{lab}_sale"] = float(g["sale"])
    sm.pick_wings = bd._pick
    return out


def main() -> None:
    ev = pd.read_parquet(bd.H_EVENTS)
    ev = ev[ev["status"] == "ok"].copy()
    for c in ("entry_date", "exit_date", "expiry"):
        ev[c] = pd.to_datetime(ev[c])
    f = pd.read_parquet(st.FEATURES)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    ev = ev.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"])
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if limit:
        ev = ev.sample(limit, random_state=0)
    print(f"events: {len(ev)}", flush=True)
    crsp = st.load_crsp()
    pd.read_parquet = bd._cached_read  # type: ignore[assignment]
    rows, t_start = [], time.time()
    for i, (_, e) in enumerate(ev.iterrows()):
        bd._cache.clear()
        rows.append(legs_one(e, crsp))
        if (i + 1) % 500 == 0:
            el = time.time() - t_start
            print(f"  {i + 1}/{len(ev)}  {el:.0f}s  eta {el / (i + 1) * (len(ev) - i - 1):.0f}s",
                  flush=True)
    pd.read_parquet = bd._real_read  # type: ignore[assignment]
    d = pd.DataFrame(rows)
    print("funnel:", dict(Counter(d["lstatus"])))
    for lab in COMBOS:
        print(f"  {lab}:", dict(Counter(d.get(f"{lab}_status", pd.Series()).fillna("not_built"))))
    out = HERE / ("legs.parquet" if not limit else "legs_smoke.parquet")
    d.to_parquet(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
