"""
round2.py
Lane I (entry day), round 2: fixes for the round-1 diagnosis, on the k7-10 bin (broad coverage).

T2027  source-neutral modelled fill: the DoltHub half-spread scaled by the median ratio of
       Databento 15:59 to DoltHub end-of-day half-spread on the same contract the same day, from
       strictly earlier events (causal). Early minus S0, paired.
T2028  selector: event variance already priced at D-k (implied event move from the DoltHub
       two-expiry split, over the RMS of the name's strictly earlier announcement moves). Top
       causal tercile sells early; others at S0. Mechanism: little run-up left to pay for.
T2029  selector: trailing 20-session realised vol at D-k below the diffusive implied vol of the
       split (bottom causal tercile of the ratio) sells early. Mechanism: the hedged run-up
       earns implied-minus-realised diffusive premium on the way in.
T2030  early sale left unhedged until the D0 close (then hedged as usual), minus S0. Mechanism:
       the run-up hedge lost about 1% of m0 in round 1 while the mid fell by as much.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/round2.py --set discovery
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from analyse import pick_bin  # noqa: E402
from build import FEATURES, hold, simulate  # noqa: E402
from pull import cached, shift  # noqa: E402
from score import ci, log_trial, signflip_pct  # noqa: E402

from earnings_iv_crush.research.hedged_hold import (  # noqa: E402
    causal_bins,
    split_jump_variance,
    straddle_iv,
    year_frac,
)
from earnings_iv_crush.research.protocol import matched_random_null  # noqa: E402

MIN_SPLIT_GAP = 7  # days between F and the second expiry; HEDGED.jump_split_min_gap_days
MIN_PRIOR_MOVES = 2  # prior announcements before the own-history RMS is defined
RV_WINDOW = 20  # sessions of trailing realised vol at D-k
TERCILE_PRIOR = 100  # strictly earlier events before a causal tercile is assigned (N ~ 800)
MIN_CAL_PAIRS = 20  # same-day calibration pairs before the modelled fill is defined


def second_expiry_iv(ticker: str, day: pd.Timestamp, f: pd.Timestamp) -> tuple[float, float]:
    """ATM straddle IV and year fraction of the first DoltHub expiry at least a week after F."""
    p = cached(ticker, day)
    ch = pd.read_parquet(p)
    exps = sorted(e for e in ch["expiry"].unique() if (pd.Timestamp(e) - f).days >= MIN_SPLIT_GAP)
    if not exps:
        return float("nan"), float("nan")
    e2 = pd.Timestamp(exps[0])
    c = ch[(ch["expiry"] == e2) & (ch["bid"] > 0) & (ch["ask"] >= ch["bid"])].copy()
    c["mid"] = (c["bid"] + c["ask"]) / 2
    piv = c.pivot_table(index="strike", columns="right", values="mid", aggfunc="first").dropna()
    if piv.empty or not {"C", "P"} <= set(piv.columns):
        return float("nan"), float("nan")
    k0 = float((piv["C"] - piv["P"]).abs().idxmin())
    fwd = float(k0 + piv.loc[k0, "C"] - piv.loc[k0, "P"])
    k = float(piv.index[np.argmin(np.abs(piv.index.to_numpy(float) - fwd))])
    t2 = year_frac(day, e2)
    return straddle_iv(float(piv.loc[k, "C"] + piv.loc[k, "P"]), fwd, k, t2), t2


def features(e: pd.DataFrame, crsp: dict, permno: pd.Series) -> pd.DataFrame:
    h = pd.read_parquet(hold.OUT / "events.parquet")
    h = h[h["status"] == "ok"][["ticker", "exit_date", "abs_move"]]
    h["exit_date"] = pd.to_datetime(h["exit_date"])
    out = []
    for _, r in e.iterrows():
        day, f = pd.Timestamp(r["entry"]), pd.Timestamp(r["expiry"])
        iv2, t2 = second_expiry_iv(r["ticker"], day, f)
        t1 = year_frac(day, f)
        jv, dv = float("nan"), float("nan")
        if np.isfinite(iv2) and t2 > t1:
            s = split_jump_variance(r["iv_entry"], t1, iv2, t2)
            if s.valid:
                jv, dv = s.jump_var, s.diffusive_vol
        prior = h[(h["ticker"] == r["ticker"]) & (h["exit_date"] < day)]["abs_move"]
        rms = float(np.sqrt(np.mean(prior**2))) if len(prior) >= MIN_PRIOR_MOVES else np.nan
        g = crsp.get(int(permno[(r["ticker"], r["entry_date"])]))
        rv = np.nan
        if g is not None:
            w = g.loc[:day].tail(RV_WINDOW + 1)
            lr = np.log(w["prc"].abs()).diff().dropna()
            if len(lr) == RV_WINDOW and w["cfacpr"].nunique() == 1:
                rv = float(lr.std(ddof=1) * np.sqrt(252))
        out.append(
            {
                "jump_move": np.sqrt(jv) if np.isfinite(jv) else np.nan,
                "own_rms": rms,
                "diff_vol": dv,
                "rv20": rv,
            }
        )
    f = pd.DataFrame(out, index=e.index)
    f["rich"] = f["jump_move"] / f["own_rms"]
    f["rv_ratio"] = f["rv20"] / f["diff_vol"]
    return f


def unhedged_runup(e: pd.DataFrame, crsp: dict, permno: pd.Series) -> pd.Series:
    """Re-simulate each early arm with no hedge before the D0 close."""
    vals = []
    for _, r in e.iterrows():
        d0, exp = pd.Timestamp(r["entry_date"]), pd.Timestamp(r["expiry"])
        st, g = hold.stock_path(crsp, permno[(r["ticker"], r["entry_date"])], r["entry"], exp)
        if st != "ok" or g is None:
            vals.append(np.nan)
            continue
        res = simulate(
            g=g,
            entry=r["entry"],
            hedge_from=d0,
            d0=d0,
            t1=pd.Timestamp(r["exit_date"]),
            expiry_last=g.index[-1],
            expiry=exp,
            k=r["strike"],
            fwd=r["fwd"],
            bid=r["bid"],
            mid=r["mid"],
            sig_pre=r["iv_entry"],
            sig_post=r["sig_post"],
        )
        vals.append(res["net"] / r["m0"])
    return pd.Series(vals, index=e.index)


def calibration(ok: pd.DataFrame, pool: pd.DataFrame | None) -> pd.DataFrame:
    """Same-day, same-strike pairs: Databento over DoltHub half-spread, with the pair's date."""
    src = ok if pool is None else pd.concat([pool, ok])
    d0 = src[src["arm"] == "D0"]
    s0 = src[src["arm"] == "S0"]
    m = d0.merge(s0, on=["ticker", "entry_date"], suffixes=("", "_s"))
    m = m[np.isclose(m["strike"], m["strike_s"]) & (m["half_spread_prem"] > 0)]
    m["ratio"] = m["half_spread_prem_s"] / m["half_spread_prem"]
    return m[["exit_date", "ratio"]].sort_values("exit_date")


def selector_trial(
    tid: int, m: pd.DataFrame, feat: str, top: bool, block: str, hyp: str, mech: str
) -> None:
    bins = causal_bins(m[feat].to_numpy(float), m["entry"], 3, TERCILE_PRIOR)
    a = m[bins >= 0].copy()
    sel = (bins[bins >= 0] == (2 if top else 0))
    c = ci(a.loc[sel, "diff"], a.loc[sel, "exit_date"])
    nul = matched_random_null(a["diff"].to_numpy(float), sel, lambda x: float(np.mean(x)))
    switch = np.where(sel, a["net_m0"], a["net_m0_s"])
    lvl = ci(pd.Series(switch, index=a.index), a["exit_date"])
    print(
        f"T{tid} {feat} {'top' if top else 'bottom'} tercile: N={c['n']} of {len(a)} "
        f"diff {c['point']:+.4f} [{c['low']:+.4f}, {c['high']:+.4f}] t={c['t']:+.2f}; "
        f"null pct {nul.percentile:.1f} (median {np.median(nul.null):+.4f}); switching book "
        f"{lvl['point']:+.4f} [{lvl['low']:+.4f}, {lvl['high']:+.4f}] vs S0 "
        f"{a['net_m0_s'].mean():+.4f}"
    )
    log_trial(
        {
            "trial_id": tid,
            "hypothesis": hyp,
            "mechanism": mech,
            "block": block,
            "n": c["n"],
            "effect": round(c["point"], 5),
            "ci_low": round(c["low"], 5),
            "ci_high": round(c["high"], 5),
            "t": round(c["t"], 2),
            "null_pct": round(nul.percentile, 1),
            "basis": "per trade, standard m0, net at the touch, early (k7-10) minus S0 on the "
            "selected events; null = matched random selection of the same size",
            "verdict": f"exploratory; switching book {lvl['point']:+.4f} "
            f"[{lvl['low']:+.4f}, {lvl['high']:+.4f}] vs S0 {a['net_m0_s'].mean():+.4f} on "
            f"{len(a)} assigned events",
        }
    )


def run(which: str, ids: dict[str, int], pool: pd.DataFrame | None = None) -> pd.DataFrame:
    d = pd.read_parquet(HERE / f"arms_{which}.parquet")
    ok = d[d["status"] == "ok"]
    block = f"{which} (k7-10 bin, 2019-24)"
    s0 = ok[ok["arm"] == "S0"]
    e = pick_bin(ok, 7, 10)
    m = e.merge(
        s0[["ticker", "entry_date", "net_m0", "half_spread_prem"]],
        on=["ticker", "entry_date"],
        suffixes=("", "_s"),
    ).reset_index(drop=True)
    m["diff"] = m["net_m0"] - m["net_m0_s"]
    feats = pd.read_parquet(FEATURES)
    feats["entry_date"] = pd.to_datetime(feats["entry_date"])
    permno = feats.drop_duplicates(["ticker", "entry_date"]).set_index(["ticker", "entry_date"])[
        "permno"
    ]
    crsp = hold.load_crsp()

    if "T2027" in ids:
        cal = calibration(ok, pool)
        ratios = []
        for _, r in m.iterrows():
            prior = cal[cal["exit_date"] < r["entry"]]["ratio"]
            ratios.append(prior.median() if len(prior) >= MIN_CAL_PAIRS else np.nan)
        m["cal_ratio"] = ratios
        hs = (m["ask"] - m["bid"]) / 2 / m["m0"]
        m["net_model"] = m["net_m0"] + (1 - m["cal_ratio"]) * hs
        x = m.dropna(subset=["net_model"])
        dd = x["net_model"] - x["net_m0_s"]
        c = ci(dd, x["exit_date"])
        pct = signflip_pct(dd, x["exit_date"])
        lvl = ci(x["net_model"], x["exit_date"])
        print(
            f"T{ids['T2027']} modelled fill (ratio median {x['cal_ratio'].median():.3f}): "
            f"N={c['n']} diff {c['point']:+.4f} [{c['low']:+.4f}, {c['high']:+.4f}] "
            f"t={c['t']:+.2f} flip {pct:.1f}; early level {lvl['point']:+.4f}"
        )
        log_trial(
            {
                "trial_id": ids["T2027"],
                "hypothesis": "Early sale (k7-10) at a source-neutral modelled fill beats S0",
                "mechanism": "round-1 deficit is the DoltHub quote source, not the entry day",
                "block": block,
                "n": c["n"],
                "effect": round(c["point"], 5),
                "ci_low": round(c["low"], 5),
                "ci_high": round(c["high"], 5),
                "t": round(c["t"], 2),
                "null_pct": round(pct, 1),
                "basis": "per trade, standard m0, net, modelled early fill (DoltHub half-spread x "
                "causal Databento/DoltHub ratio) minus S0 at the 15:59 touch",
                "verdict": f"exploratory, modelled fill; early level {lvl['point']:+.4f} "
                f"[{lvl['low']:+.4f}, {lvl['high']:+.4f}], S0 {x['net_m0_s'].mean():+.4f}",
            }
        )

    f = features(m, crsp, permno)
    m = pd.concat([m, f], axis=1)
    print(
        "  feature coverage: rich",
        int(m["rich"].notna().sum()),
        "rv_ratio",
        int(m["rv_ratio"].notna().sum()),
        "of",
        len(m),
    )
    if "T2028" in ids:
        selector_trial(
            ids["T2028"],
            m,
            "rich",
            True,
            block,
            "Sell early (k7-10) only when the implied event move at D-k is rich against the "
            "name's own prior moves (top causal tercile)",
            "event variance already priced at D-k leaves little run-up for the early seller to "
            "give away",
        )
    if "T2029" in ids:
        selector_trial(
            ids["T2029"],
            m,
            "rv_ratio",
            False,
            block,
            "Sell early (k7-10) only when trailing 20-session realised vol at D-k is low against "
            "the diffusive implied vol (bottom causal tercile)",
            "the hedged run-up earns implied-minus-realised diffusive premium",
        )
    if "T2030" in ids:
        m["net_unh"] = unhedged_runup(m, crsp, permno)
        x = m.dropna(subset=["net_unh"])
        dd = x["net_unh"] - x["net_m0_s"]
        c = ci(dd, x["exit_date"])
        pct = signflip_pct(dd, x["exit_date"])
        lvl = ci(x["net_unh"], x["exit_date"])
        vs = ci(x["net_unh"] - x["net_m0"], x["exit_date"])
        print(
            f"T{ids['T2030']} unhedged run-up: N={c['n']} diff vs S0 {c['point']:+.4f} "
            f"[{c['low']:+.4f}, {c['high']:+.4f}] t={c['t']:+.2f} flip {pct:.1f}; vs hedged "
            f"early {vs['point']:+.4f} [{vs['low']:+.4f}, {vs['high']:+.4f}]; level "
            f"{lvl['point']:+.4f}; sd {x['net_unh'].std():.4f} vs hedged {x['net_m0'].std():.4f}"
        )
        log_trial(
            {
                "trial_id": ids["T2030"],
                "hypothesis": "Early sale (k7-10) left unhedged until the D0 close beats S0",
                "mechanism": "the run-up hedge loses to pre-event mean reversion",
                "block": block,
                "n": c["n"],
                "effect": round(c["point"], 5),
                "ci_low": round(c["low"], 5),
                "ci_high": round(c["high"], 5),
                "t": round(c["t"], 2),
                "null_pct": round(pct, 1),
                "basis": "per trade, standard m0, net at the touch, paired minus S0",
                "verdict": f"exploratory; vs hedged early {vs['point']:+.4f} "
                f"[{vs['low']:+.4f}, {vs['high']:+.4f}]; level {lvl['point']:+.4f}",
            }
        )
    m.to_parquet(HERE / f"round2_{which}.parquet")
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description="Lane I round 2")
    ap.add_argument("--set", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    run(a.set, {"T2027": 2027, "T2028": 2028, "T2029": 2029, "T2030": 2030})


if __name__ == "__main__":
    main()
