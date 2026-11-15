"""
round2.py
Lane C round 2, discovery block only (entry 2013-2018). Trials 1,847 to 1,850, written after the
round-1 diagnosis and before this script was first run.

1847  mechanism control: does the HAR forecast sort the diffusive part with IV held fixed?
1848  gap rule over every event with days left (one-sided reaction quotes included), top tercile
1849  the same, top decile only (discovery-informed: round 1 showed one-sided events move most)
1850  entry-time selector on the event hold: pre-event diffusive implied vol (two-expiry split)
      minus a HAR forecast at entry; top tercile kept

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/round2.py
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

import build_panel as bp
import lanec_lib as L
from earnings_iv_crush.config import HEDGED
from earnings_iv_crush.research import hedged_hold as hh

BASIS_RULE = "per trade, fraction of m0, net at touch; rule book minus always-hold, paired"
OUT = L.HERE / "entry_panel.parquet"


def entry_panel() -> pd.DataFrame:
    """Every status-ok event (both universes) with a HAR forecast made before the entry date."""
    if OUT.exists():
        return pd.read_parquet(OUT)
    d = bp.load_events()
    d = d[d["status"] == "ok"].copy().reset_index(drop=True)
    d["n_hedge"] = d["n_hedge"].astype(int)
    excl_by = (pd.read_parquet(bp.EVENTS, columns=["ticker", "exit_date"])
               .assign(exit_date=lambda x: pd.to_datetime(x["exit_date"]).dt.normalize())
               .groupby("ticker")["exit_date"].apply(set).to_dict())
    crsp = bp.load_crsp()
    har = []
    for _, r in d.iterrows():
        if not np.isfinite(r["permno"]) or int(r["permno"]) not in crsp:
            har.append(np.nan)
            continue
        g = crsp[int(r["permno"])]
        g = g[g.index < r["entry_date"]]
        x = np.log1p(g["ret"].to_numpy(float))
        excl = {e for e in excl_by.get(r["ticker"], set()) if e < r["entry_date"]}
        x[np.isin(g.index.normalize(), list(excl))] = np.nan
        har.append(hh.har_annual_variance(x, max(int(r["n_hedge"]), 1)))
    d["har_entry"] = har
    fwd0 = (d["m0"] - d["s0"]) / 0.20
    d["implied_move"] = d["mid0"] / fwd0
    d["gap_ratio"] = d["abs_move"] / d["implied_move"]
    d["year"] = d["entry_date"].dt.year
    d.to_parquet(OUT, index=False)
    return d


def log(tid: int, hyp: str, mech: str, eff: dict, null_pct: float, basis: str, verdict: str,
        sec: str) -> None:
    print(f"\n[{tid}] {L.fmt(eff)}  null pct {null_pct:.1f} -> {verdict}\n    {sec}")
    L.log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": "2013-18",
                 "n": eff["n"], "effect": eff["point"], "ci_low": eff["low"],
                 "ci_high": eff["high"], "t": eff["t"], "null_pct": null_pct, "basis": basis,
                 "verdict": verdict + " (exploratory)", "secondary": sec})


def main() -> None:
    # ── 1847 mechanism control on the two-sided panel ──
    p = L.load()
    disc = (p["block"] == "discovery").to_numpy()
    ivb = L.bins(p, p["iv_pts"])
    hb = L.bins(p, -np.sqrt(p["har_ex"]))  # bin 2 = lowest forecast realised vol
    for lab, extra in (("all", np.ones(len(p), bool)), ("h5", (p["n_hedge"] >= 5).to_numpy())):
        m = disc & (ivb >= 0) & (hb >= 0) & extra
        blk = p[m].copy()
        blk["D_res"] = blk["D_mid"] - blk.groupby(ivb[m])["D_mid"].transform("mean")
        pt, lo, hi = L.tmb(blk, "D_res", hb[m])
        nul = L.matched_random_null(blk["D_res"].to_numpy(float), hb[m] == 2, L.mean)
        print(f"1847 [{lab}] D_mid within IV tercile, low-forecast minus high-forecast: "
              f"{100 * pt:+.3f} [{100 * lo:+.3f}, {100 * hi:+.3f}]% m0, N={len(blk)}, "
              f"null pct {nul.percentile:.1f}")
        if lab == "h5":
            se = (hi - lo) / 3.92
            eff = {"point": pt, "low": lo, "high": hi, "n": len(blk), "t": pt / se}
            v = "pass discovery" if lo > 0 and nul.percentile >= 95 else "fail discovery"
            log(1847, "with post-event IV held fixed (causal IV tercile), a lower HAR forecast of "
                      "realised vol over the remaining days means a larger diffusive part D_mid "
                      "(events with 5+ sessions left)",
                "if the forecast carries information on future realised vol, D must rise as the "
                "forecast falls at a given IV; if not, round-1 sorting came from the IV level",
                eff, nul.percentile, "per trade, fraction of m0, gross at the reaction-close mid; "
                "top minus bottom of the IV-demeaned diffusive part", v,
                "the all-events version is printed above")

    # ── 1848-1850 on the full event universe ──
    e = entry_panel().sort_values("exit_date").reset_index(drop=True)
    e["block"] = np.where(e["year"].between(2013, 2018), "discovery",
                          np.where(e["year"].between(2019, 2024), "heldout", "other"))
    print(f"\nentry panel: {len(e)} status-ok events; {dict(Counter(e['block']))}")

    days = e["n_hedge"] >= 1
    gb3 = hh.causal_bins(e["gap_ratio"].where(days).to_numpy(float), e["exit_date"], 3,
                         L.MIN_PRIOR)
    gb10 = hh.causal_bins(e["gap_ratio"].where(days).to_numpy(float), e["exit_date"], 10,
                          L.MIN_PRIOR)
    for tid, b, top, lab in ((1848, gb3, 2, "top tercile"), (1849, gb10, 9, "top decile")):
        m = (e["block"] == "discovery").to_numpy() & days.to_numpy() & (b >= 0)
        blk = e[m]
        res = L.hold_or_close(blk, b[m] == top)
        v = "pass discovery" if res["effect"]["low"] > 0 and res["null_pct"] >= 95 else \
            "fail discovery"
        sec = (f"rule level {L.fmt(res['level_rule'])}%; always-hold {L.fmt(res['level_hold'])}%; "
               f"G closed {100 * res['G_closed']:+.3f}% kept {100 * res['G_kept']:+.3f}%; "
               f"closed {res['n_closed']}")
        log(tid, f"close at the reaction close when the gap over the entry implied move is in the "
                 f"causal {lab}, one-sided reaction quotes included; else hold hedged",
            "after a large surprise realised vol stays high and the in-the-money leg carries the "
            "move, so the remaining diffusive premium is negative enough to beat the exit spread",
            res["effect"], res["null_pct"], BASIS_RULE, v, sec)

    sig = 100 * (np.sqrt(e["jsplit_sd2"].where(e["jsplit_valid"].astype(bool))) -
                 np.sqrt(e["har_entry"]))
    print(f"\n1850 signal finite on {int(np.isfinite(sig).sum())} of {len(e)} "
          f"(jsplit valid {int(e['jsplit_valid'].astype(bool).sum())}, "
          f"HAR finite {int(np.isfinite(e['har_entry']).sum())})")
    b = hh.causal_bins(sig.to_numpy(float), e["entry_date"], 3, L.MIN_PRIOR)
    m = (e["block"] == "discovery").to_numpy() & (b >= 0)
    blk = e[m]
    un = e[(e["block"] == "discovery").to_numpy() & (b < 0)]
    print(f"  assigned {len(blk)}, unassigned {len(un)}; H assigned {100 * blk['H'].mean():+.3f}% "
          f"vs unassigned {100 * un['H'].mean():+.3f}%")
    top = b[m] == 2
    lvl = L.ci(blk.loc[top, "H"], blk.loc[top, "exit_date"])
    nul = L.matched_random_null(blk["H"].to_numpy(float), top, L.mean)
    pt, lo, hi = hh.top_minus_bottom_ci(blk["H"].to_numpy(float), top, b[m] == 0,
                                        blk["exit_date"])
    pdm = p.merge(blk.assign(bin=b[m])[["ticker", "entry_date", "bin"]],
                  on=["ticker", "entry_date"], how="inner")
    dp, dl, dh = hh.top_minus_bottom_ci(pdm["D_mid"].to_numpy(float), pdm["bin"] == 2,
                                        pdm["bin"] == 0, pdm["exit_date"])
    jp, jl, jh = hh.top_minus_bottom_ci(pdm["J"].to_numpy(float), pdm["bin"] == 2,
                                        pdm["bin"] == 0, pdm["exit_date"])
    v = "pass discovery" if lvl["low"] > 0 and nul.percentile >= 95 else "fail discovery"
    sec = (f"top-bottom H {100 * pt:+.3f} [{100 * lo:+.3f}, {100 * hi:+.3f}]%; on the two-sided "
           f"subset (N={len(pdm)}) top-bottom D_mid {100 * dp:+.3f} [{100 * dl:+.3f}, "
           f"{100 * dh:+.3f}]%, J {100 * jp:+.3f} [{100 * jl:+.3f}, {100 * jh:+.3f}]%; all assigned "
           f"H {100 * blk['H'].mean():+.3f}%")
    log(1850, "at entry, keep only events in the causal top tercile of pre-event diffusive "
              "implied vol (two-expiry split) minus a HAR forecast of realised vol over the "
              "post-event days; hedged hold to expiry",
        "the hold's diffusive part earns post-event IV minus realised; pre-event the split's "
        "diffusive vol estimates post-event IV and HAR estimates realised, so their gap forecasts D "
        "without crossing any extra spread (differs from S3a: event front contract held, D target)",
        lvl, nul.percentile, "per trade, fraction of m0, net at touch, top-tercile book level", v,
        sec)


if __name__ == "__main__":
    main()
