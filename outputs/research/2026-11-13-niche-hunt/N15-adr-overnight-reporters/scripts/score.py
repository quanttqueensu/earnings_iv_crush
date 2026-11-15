"""
score.py
Score lane N15 on one block exactly as pre-registered in ``diagnosis.log`` entry [2]: foreign
issuers' net short-straddle event return at the touch against week- and tenor-matched US
reporters, with date-clustered intervals, a matched random null, attrition checks and the
descriptive spread, crush and move ratios.

Usage
-----
    python .../scripts/score.py --year 2025 [--variant primary|fill_missing]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

LANE = Path(__file__).resolve().parents[1]
N_NULL = 2000
SEED = 0
FILL_TICK = 0.05  # one nickel tick added to intrinsic for an unquoted exit leg (variant only)


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _median(a: np.ndarray) -> float:
    return float(np.median(a))


def ci(x: pd.Series, dates: pd.Series, stat=_mean) -> dict:
    x = x.astype(float)
    m = x.notna().to_numpy()
    if m.sum() < 3:
        return {"point": float("nan"), "low": float("nan"), "high": float("nan"), "n": int(m.sum())}
    iv = date_clustered_ci(x[m].to_numpy(), pd.Series(dates)[m].to_numpy(), stat)
    return {
        "point": round(iv.point, 5),
        "low": round(iv.low, 5),
        "high": round(iv.high, 5),
        "n": iv.n,
        "clusters": iv.clusters,
    }


def bucket(days: float) -> str:
    return "0-3" if days <= 3 else "4-10" if days <= 10 else "11+"


def load(year: int, variant: str) -> pd.DataFrame:
    d = pd.read_parquet(LANE / "cache" / f"events_{year}.parquet")
    d["d1"] = pd.to_datetime(d["d1"])
    if variant in ("pending", "pending_fill"):
        # diagnosis.log [4]: keep events whose D1 chain shows a pending announcement
        b = pd.read_parquet(LANE / "cache" / f"bracket_{year}.parquet")
        b["d1"] = pd.to_datetime(b["d1"])
        d = d.merge(b[["ticker", "d1", "jump_var"]], on=["ticker", "d1"], how="left")
        if variant == "pending_fill":
            # diagnosis.log [5]: an unquoted exit leg valued at intrinsic plus one tick
            fill = (d["status"] == "no_exit_leg") & d["B_fill"].notna()
            print(f"fill variant: {int(fill.sum())} no_exit_leg events restored at intrinsic + 0.05")
            d.loc[fill, "status"] = "ok"
            d.loc[fill, "B"] = d.loc[fill, "B_fill"]
        n0 = int((d["status"] == "ok").sum())
        no_term = (d["status"] == "ok") & d["jump_var"].isna()
        flat = (d["status"] == "ok") & (d["jump_var"] <= 0)
        d.loc[no_term, "status"] = "no_next_expiry"
        d.loc[flat, "status"] = "no_pending_event"
        print(f"bracket filter: ok {n0} -> {int((d['status'] == 'ok').sum())} "
              f"(no next expiry {int(no_term.sum())}, no pending event {int(flat.sum())})")
    elif variant != "primary":
        raise SystemExit(f"unknown variant {variant}")
    return d


def matched(d: pd.DataFrame) -> pd.DataFrame:
    ok = d[(d["status"] == "ok") & d["B"].notna()].copy()
    ok["week"] = ok["d1"].dt.isocalendar().week.astype(int) + 100 * ok["d1"].dt.year
    ok["bkt"] = ok["tenor_days"].map(bucket)
    us = ok[ok["grp"] == "US"]
    ctrl = us.groupby(["week", "bkt"]).agg(
        B_ctrl=("B", "mean"),
        n_ctrl=("B", "size"),
        hs_ctrl=("hs_share", "mean"),
        im_ctrl=("im", "mean"),
    )
    f = ok[ok["grp"] != "US"].merge(ctrl, left_on=["week", "bkt"], right_index=True, how="left")
    return ok, us, f


def random_null(f: pd.DataFrame, us: pd.DataFrame) -> dict:
    rng = np.random.default_rng(SEED)
    pools = {k: g["B"].to_numpy(float) for k, g in us.groupby(["week", "bkt"])}
    fm = f[f["B_ctrl"].notna()]
    keys = list(zip(fm["week"], fm["bkt"]))
    draws = np.array(
        [np.mean([pools[k][rng.integers(len(pools[k]))] for k in keys]) for _ in range(N_NULL)]
    )
    obs = float(fm["B"].mean())
    return {
        "observed_mean_B": round(obs, 5),
        "null_mean": round(float(draws.mean()), 5),
        "null_p2.5": round(float(np.quantile(draws, 0.025)), 5),
        "null_p97.5": round(float(np.quantile(draws, 0.975)), 5),
        "percentile": round(float((draws < obs).mean() * 100), 1),
        "n": len(keys),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--variant", default="primary")
    a = ap.parse_args()
    d = load(a.year, a.variant)
    res: dict = {"year": a.year, "variant": a.variant}

    # ── funnel and attrition ────────────────────────────────────────────────
    fun = d.groupby(["grp", "status"]).size().unstack(fill_value=0)
    print("funnel:\n" + fun.to_string())
    res["funnel"] = {g: {k: int(v) for k, v in r.items()} for g, r in fun.iterrows()}
    ok_all = d[d["status"] == "ok"]
    und = ok_all[ok_all["B"].isna()]
    print(f"ok but B undefined (an exit ask of zero): {len(und)}")
    # outcome dependence: dropped no_exit_leg events' implied move against kept ones
    drop = d[d["status"] == "no_exit_leg"]
    for g in ["F", "US"]:
        sel_d = drop[drop["grp"] != "US"] if g == "F" else drop[drop["grp"] == "US"]
        sel_k = ok_all[ok_all["grp"] != "US"] if g == "F" else ok_all[ok_all["grp"] == "US"]
        res[f"attrition_{g}"] = {
            "dropped_no_exit_leg": len(sel_d),
            "kept": len(sel_k),
            "im_dropped_mean": round(float(sel_d["im"].mean()), 4) if len(sel_d) else None,
            "im_kept_mean": round(float(sel_k["im"].mean()), 4),
        }
    print("attrition:", json.dumps({k: v for k, v in res.items() if k.startswith("attr")}))

    ok, us, f = matched(d)
    nf0 = len(f)
    fm = f[f["B_ctrl"].notna()].copy()
    print(f"F events with B: {nf0}; matched to a US week-tenor cell: {len(fm)}")
    res["n_F_with_B"], res["n_F_matched"] = nf0, len(fm)

    # ── primary ─────────────────────────────────────────────────────────────
    fm["diff"] = fm["B"] - fm["B_ctrl"]
    res["primary"] = {
        "diff_B_F_minus_ctrl": ci(fm["diff"], fm["d1"]),
        "mean_B_F": ci(fm["B"], fm["d1"]),
        "mean_B_ctrl_matched": ci(fm["B_ctrl"], fm["d1"]),
        "mean_B_US_all": ci(us["B"], us["d1"]),
        "per_trade_sharpe_F": round(float(fm["B"].mean() / fm["B"].std(ddof=1)), 4),
    }
    res["random_null"] = random_null(f, us)
    p = res["primary"]
    res["pass_a"] = bool(p["diff_B_F_minus_ctrl"]["low"] > 0)
    res["pass_b"] = bool(p["mean_B_F"]["low"] > 0)
    print(json.dumps(res["primary"], indent=1))
    print("null:", res["random_null"])
    print(f"pass (a) {res['pass_a']}  pass (b) {res['pass_b']}")

    # ── descriptive and subgroups (exploratory) ─────────────────────────────
    ok["crush_vp"] = (ok["iv1"] - ok["iv2"]) * 100
    ok["rm_im"] = ok["rm"] / ok["im"]
    desc = {}
    for g, sub in [("F", ok[ok["grp"] != "US"])] + list(ok.groupby("grp")):
        desc[g] = {
            "n": len(sub),
            "names": int(sub["ticker"].nunique()),
            "hs_share_median": ci(sub["hs_share"], sub["d1"], _median),
            "im_mean": round(float(sub["im"].mean()), 4),
            "crush_vp_median": ci(sub["crush_vp"], sub["d1"], _median),
            "rm_over_im_mean": ci(sub["rm_im"], sub["d1"]),
            "B_mean": ci(sub["B"], sub["d1"]),
            "B_mid_mean": ci(sub["B_mid"], sub["d1"]),
            "B_prem_median": ci(sub["B_prem"], sub["d1"], _median),
        }
    fm_g = {}
    for g, sub in fm.groupby("grp"):
        fm_g[g] = {
            "diff": ci(sub["diff"], sub["d1"]),
            "hs_minus_ctrl": ci(sub["hs_share"] - sub["hs_ctrl"], sub["d1"]),
            "im_minus_ctrl": ci(sub["im"] - sub["im_ctrl"], sub["d1"]),
        }
    fm_all = {
        "hs_minus_ctrl": ci(fm["hs_share"] - fm["hs_ctrl"], fm["d1"]),
        "im_minus_ctrl": ci(fm["im"] - fm["im_ctrl"], fm["d1"]),
    }
    res["descriptive"], res["matched_by_group"], res["matched_F"] = desc, fm_g, fm_all
    for g, v in desc.items():
        print(g, json.dumps(v))
    for g, v in fm_g.items():
        print("matched", g, json.dumps(v))
    print("matched F", json.dumps(fm_all))
    out = LANE / f"results_{a.year}_{a.variant}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
