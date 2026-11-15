"""
run.py
Lane F scorer: resting-bid buy-back rules against the 15:59:00 taker buy-back, by round.

Usage:
    python outputs/research/2026-11-13-alpha-hunt-2/laneF-resting-exit/run.py --coverage
    python outputs/research/2026-11-13-alpha-hunt-2/laneF-resting-exit/run.py --round 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import (  # noqa: E402
    HERE, ROOT, Rule, clustered_t, fmt, gap_features, load, log_trial, mean_ci, null_pct,
    score_rule,
)

HH = ROOT / "outputs/research/2026-11-02-hedged-event-hold"
BASIS = "per trade, m0 units, paired vs 15:59:00 ask buy-back, option prices only"
GAP_BINS = [0, 0.5, 1.0, 2.0, np.inf]
GAP_LABELS = ["<0.5x", "0.5-1x", "1-2x", ">2x"]


# ── blocks ───────────────────────────────────────────────────────────────────


def block_mask(ev: pd.DataFrame, name: str) -> np.ndarray:
    y = pd.to_datetime(ev["entry_date"]).dt.year
    if name == "disc_broad_2025":
        return ((ev["block"] == "broad_2025_2026") & (y == 2025)).to_numpy()
    if name == "hold_broad_2026":
        return ((ev["block"] == "broad_2025_2026") & (y == 2026)).to_numpy()
    if name == "hold_megacap_2023_24":
        return (ev["block"] == "megacap_2023_2024").to_numpy()
    raise ValueError(name)


def hold_table() -> pd.DataFrame:
    a = pd.read_parquet(HH / "events_confirm_2025_26.parquet")
    b = pd.read_parquet(HH / "events_megacap.parquet")
    h = pd.concat([a, b], ignore_index=True)
    h["entry_date"] = pd.to_datetime(h["entry_date"])
    h = h.drop_duplicates(["ticker", "entry_date"])
    return h[["ticker", "entry_date", "status", "strike", "m0", "B", "H", "abs_move"]].rename(
        columns={"strike": "strike_h", "m0": "m0_h", "B": "B_h", "abs_move": "abs_move_h"}
    )


# ── coverage ─────────────────────────────────────────────────────────────────


def coverage() -> None:
    ev = pd.read_parquet(HERE / "events.parquet")
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    h = hold_table()
    out = {}
    for name, lo, hi, src in (
        ("2025-26 universe (hedged-hold confirm table)", "2025-01-01", "2026-12-31", "confirm"),
        ("megacap 2023-24 (hedged-hold megacap table)", "2023-03-28", "2024-12-31", "megacap"),
    ):
        tab = pd.read_parquet(HH / ("events_confirm_2025_26.parquet" if src == "confirm"
                                    else "events_megacap.parquet"))
        tab["entry_date"] = pd.to_datetime(tab["entry_date"])
        tab = tab[(tab["entry_date"] >= lo) & (tab["entry_date"] <= hi)]
        j = tab.merge(ev[["ticker", "entry_date"]].assign(cov=True), how="left",
                      on=["ticker", "entry_date"])
        j["cov"] = j["cov"].fillna(False).astype(bool)
        res = {"universe": len(j), "covered": int(j["cov"].sum()),
               "status_counts_uncovered": j.loc[~j["cov"], "status"].value_counts().to_dict()}
        for col in ("B", "H", "abs_move"):
            for flag, lab in ((True, "cov"), (False, "uncov")):
                g = j[(j["cov"] == flag) & j[col].notna()]
                if len(g) > 5:
                    ci = mean_ci(g[col], g["exit_date"])
                    res[f"{col}_{lab}"] = f"{ci.point:+.4f} [{ci.low:+.4f}, {ci.high:+.4f}] N={ci.n}"
                else:
                    res[f"{col}_{lab}"] = f"N={len(g)}"
        res["no_exit_leg_share_cov"] = float((j.loc[j["cov"], "status"] == "no_exit_leg").mean())
        res["no_exit_leg_share_uncov"] = float((j.loc[~j["cov"], "status"] == "no_exit_leg").mean())
        out[name] = res
        print(name, json.dumps(res, indent=1, default=str))
    (HERE / "coverage.json").write_text(json.dumps(out, indent=1, default=str))


# ── one trial ────────────────────────────────────────────────────────────────


_CACHE: dict = {}


def scored(ev, legs, rule: Rule) -> pd.DataFrame:
    if rule not in _CACHE:
        d = score_rule(ev, legs, rule)
        d = d.merge(_CACHE["gaps"], on="eid", how="left")
        _CACHE[rule] = d
    return _CACHE[rule]


def describe(d: pd.DataFrame, label: str) -> dict:
    m = d[d["measured"] == True]  # noqa: E712
    dates = m["exit_date"].to_numpy()
    ci = mean_ci(m["imp"], dates)
    lvl_t = mean_ci(m["b_taker"], dates)
    lvl_r = mean_ci(m["b_rule"], dates)
    fills = pd.concat([m[["fill_c", "rested_c"]].set_axis(["f", "r"], axis=1),
                       m[["fill_p", "rested_p"]].set_axis(["f", "r"], axis=1)])
    rested = fills["r"].fillna(False).astype(bool)
    res = {
        "label": label, "n": len(m), "unmeasured": int((d["measured"] != True).sum()),  # noqa: E712
        "imp": ci.point, "lo": ci.low, "hi": ci.high, "t": clustered_t(m["imp"], dates),
        "clusters": ci.clusters,
        "leg_fill_rate_of_rested": float(fills.loc[rested, "f"].astype(bool).mean()),
        "leg_rested_share": float(rested.mean()),
        "both_filled": float((m["n_fill"] == 2).mean()), "any_filled": float((m["n_fill"] >= 1).mean()),
        "level_taker": lvl_t.point, "level_taker_ci": (lvl_t.low, lvl_t.high),
        "level_rule": lvl_r.point, "level_rule_ci": (lvl_r.low, lvl_r.high),
    }
    # markouts and decomposition on filled legs, m0 units (positive = good for the buyer)
    parts = []
    for nm in ("c", "p"):
        f = m[m[f"fill_{nm}"] == True]  # noqa: E712
        if f.empty or f.get(f"half_{nm}") is None:
            continue
        lim = f[f"price_{nm}"]
        parts.append(pd.DataFrame({
            "mk1": (f[f"mid_1_{nm}"] - lim) / f["m0"], "mk5": (f[f"mid_5_{nm}"] - lim) / f["m0"],
            "mk15": (f[f"mid_15_{nm}"] - lim) / f["m0"],
            "mk_end": (f[f"mid_end_{nm}"] - lim) / f["m0"],
            "half_end": (f[f"ask_end_{nm}"] - f[f"mid_end_{nm}"]) / f["m0"],
            "mk5_half": (f[f"mid_5_{nm}"] - lim) / f[f"half_{nm}"],
            "saving": (f[f"ask_end_{nm}"] - lim) / f["m0"],
        }))
    if parts:
        p = pd.concat(parts)
        for c in p.columns:
            res[f"fill_{c}"] = float(p[c].mean())
        res["n_leg_fills"] = len(p)
    # by realised gap (descriptive) and by the 15:00 gap known at the decision
    for col in ("gap_close_ratio", "gap15_ratio"):
        b = pd.cut(m[col], GAP_BINS, labels=GAP_LABELS)
        res[f"by_{col}"] = {
            str(k): {"n": int(len(g)), "imp": round(float(g["imp"].mean()), 5),
                     "any_fill": round(float((g["n_fill"] >= 1).mean()), 3),
                     "level_rule": round(float(g["b_rule"].mean()), 5)}
            for k, g in m.groupby(b, observed=True)
        }
    return res


def print_res(r: dict) -> None:
    print(f"\n[{r['label']}] N={r['n']} (unmeasured {r['unmeasured']}), clusters {r['clusters']}")
    print(f"  improvement {fmt(r['imp'])} [{fmt(r['lo'])}, {fmt(r['hi'])}] t={r['t']:.2f}")
    print(f"  fills: leg fill|rested {r['leg_fill_rate_of_rested']:.3f}, rested share "
          f"{r['leg_rested_share']:.3f}, any {r['any_filled']:.3f}, both {r['both_filled']:.3f}")
    print(f"  level taker {fmt(r['level_taker'])} {tuple(round(v, 4) for v in r['level_taker_ci'])}"
          f"  level rule {fmt(r['level_rule'])} {tuple(round(v, 4) for v in r['level_rule_ci'])}")
    if "fill_saving" in r:
        print(f"  filled legs (N={r['n_leg_fills']}): saving {fmt(r['fill_saving'])} = half-spread@15:59 "
              f"{fmt(r['fill_half_end'])} + markout to 15:59 {fmt(r['fill_mk_end'])}; markout 1/5/15m "
              f"{fmt(r['fill_mk1'])}/{fmt(r['fill_mk5'])}/{fmt(r['fill_mk15'])}; 5m in half-spreads "
              f"{r['fill_mk5_half']:+.3f}")
    for col in ("gap_close_ratio", "gap15_ratio"):
        print(f"  by {col}: {r[f'by_{col}']}")


def trial(tid, hyp, mech, rule, ev, legs, block, verdict_fn=None, mask_fn=None, extra="",
          base_rule=None):
    d = scored(ev, legs, rule)
    sel = d[block_mask(d, block)].copy()
    if base_rule is not None:  # paired against another rule instead of the 15:59:00 taker
        b = scored(ev, legs, base_rule).set_index("eid")
        sel["imp"] = sel["imp"] - sel["eid"].map(b["imp"])
        sel["measured"] = sel["measured"] & sel["eid"].map(b["measured"]).fillna(False)
    npct = ""
    if mask_fn is not None:  # a conditional rule: rest only on selected events, cross the rest
        msk = mask_fn(sel).to_numpy() & (sel["measured"] == True).to_numpy()  # noqa: E712
        meas = (sel["measured"] == True).to_numpy()  # noqa: E712
        pop = sel.loc[meas, "imp"].to_numpy()
        npct = round(null_pct(pop, msk[meas]), 1)
        sel.loc[~msk, "imp"] = 0.0
        sel["b_rule"] = sel["b_taker"] + sel["imp"]
        sel.loc[~msk, ["fill_c", "fill_p"]] = False
        sel["n_fill"] = sel[["fill_c", "fill_p"]].fillna(False).astype(int).sum(axis=1)
    r = describe(sel, f"{tid} {block}")
    print_res(r)
    if npct != "":
        print(f"  matched random null percentile of the rested subset's mean improvement: {npct}")
    verdict = verdict_fn(r) if verdict_fn else (
        "gain>0, CI excludes 0" if r["lo"] > 0 else ("gain<0, CI excludes 0" if r["hi"] < 0
                                                     else "no difference"))
    lvl = f"; book level {fmt(r['level_rule'])} [{fmt(r['level_rule_ci'][0])}, " \
          f"{fmt(r['level_rule_ci'][1])}] vs taker {fmt(r['level_taker'])}"
    log_trial({
        "trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": block, "n": r["n"],
        "effect": round(r["imp"], 6), "ci_low": round(r["lo"], 6), "ci_high": round(r["hi"], 6),
        "t": round(r["t"], 2), "null_percentile": npct if npct != "" else "n/a (paired rule)",
        "basis": BASIS + extra,
        "verdict": f"exploratory: {verdict}; any-leg fill {r['any_filled']:.2f}{lvl}",
    })
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{tid}_{block}.json").write_text(json.dumps(r, indent=1, default=str))
    keep = [c for c in sel.columns if not c.startswith(("mid_", "half_"))]
    sel[keep].to_parquet(HERE / "results" / f"{tid}_{block}.parquet")
    return r, sel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--round", type=int)
    a = ap.parse_args()
    if a.coverage:
        coverage()
    if a.round:
        ev, legs = load()
        ev["entry_date"] = pd.to_datetime(ev["entry_date"])
        _CACHE["gaps"] = gap_features(ev, legs)
        sys.modules.setdefault("run", sys.modules[__name__])  # rounds shares this cache
        import rounds
        getattr(rounds, f"round{a.round}")(ev, legs, trial)


if __name__ == "__main__":
    main()
