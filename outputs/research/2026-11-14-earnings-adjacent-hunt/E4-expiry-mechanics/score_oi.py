"""
score_oi.py
E4 trial 2,773: sell the hedged straddle at whichever of K-1, K0, K+1 carries the largest
open-interest proxy (cumulative Alpaca option volume before the entry date), event-night delta
matched, valued under HEDGED_NET. Scores the declaration in ``diagnosis.log`` entry 2.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/score_oi.py \
        --block discovery [--trial 2773] [--rule maxV]

Per trade, in units of the base trade's m0 (0.20 times forward plus the 15:59 bid), net at the
touch, paired against the ATM hedged hold; date-clustered 95% intervals on the reaction date.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import straddle_delta  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci, log_block_view  # noqa: E402

HERE = Path(__file__).resolve().parent
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
BLOCKS = {"discovery": (2014, 2018), "heldout": (2019, 2024)}
EQ_FLOOR = 1e-4  # HEDGED.equity_cost_floor_bps = 1 bp
N_DRAWS, SEED = 2000, 0
STALE_TOL = 0.02  # |log(F/S)| above which the megacap entry spot is suspect (docs/SYSTEM.md 6.1)
NB = ("km1", "kp1")
VIEWS = HERE / "block_views.csv"


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def ci(x: pd.Series, dates: pd.Series) -> dict:
    iv = date_clustered_ci(x.to_numpy(float), dates, _mean)
    se = (iv.high - iv.low) / 3.92
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n,
            "clusters": iv.clusters, "t": iv.point / se if se > 0 else float("nan")}


def load() -> pd.DataFrame:
    d = pd.read_parquet(HERE / "oi_arms.parquet")
    d = d[d["status"].eq("ok") & d["k0_status"].eq("ok")].copy()
    d["year"] = pd.to_datetime(d["entry_date"]).dt.year
    d["exit_date"] = pd.to_datetime(d["exit_date"])
    d["m0b"] = d["k0_m0"]
    for lab in ("k0", *NB):
        d[f"{lab}_ok"] = d.get(f"{lab}_status", pd.Series(index=d.index)).eq("ok")
        d[f"{lab}_g"] = (d[f"{lab}_usd"] - d["k0_usd"]) / d["m0b"]
        d[f"{lab}_hs_saved"] = (
            (d["k0_mid"] - d["k0_bid"]) - (d[f"{lab}_mid"] - d[f"{lab}_bid"])
        ) / d["m0b"]
    # event-night delta match (trial 1,819 construction)
    c = pd.read_parquet(CRSP, columns=["permno", "date", "prc", "ret", "bid", "ask"])
    c["date"] = pd.to_datetime(c["date"])
    for col in ("prc", "ret", "bid", "ask"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    c["hs"] = ((c["ask"] - c["bid"]) / 2 / c["prc"]).clip(lower=EQ_FLOOR)
    c = c.set_index(["permno", "date"]).sort_index()
    pe = pd.MultiIndex.from_arrays([d["permno"].astype(int), pd.to_datetime(d["entry_date"])])
    px = pd.MultiIndex.from_arrays([d["permno"].astype(int), d["exit_date"]])
    s_e = c["prc"].reindex(pe).to_numpy()
    hs_e = c["hs"].reindex(pe).to_numpy()
    r_x = c["ret"].reindex(px).to_numpy(dtype=float)
    p_x = c["prc"].reindex(px).to_numpy()
    hs_x = c["hs"].reindex(px).to_numpy()
    d["s_entry"] = s_e
    d["stale"] = np.abs(np.log(d["fwd"] / d["s_entry"])) > STALE_TOL
    for lab in ("k0", *NB):
        d[f"{lab}_delta"] = [
            straddle_delta(f, k, t, s) if np.isfinite(k) and np.isfinite(s) else np.nan
            for f, k, t, s in zip(d["fwd"], d[f"{lab}_K"], d["t0"], d[f"{lab}_mid_iv"])
        ]
    for lab in NB:
        x = d[f"{lab}_delta"] - d["k0_delta"]
        pnl = x * s_e * r_x - x.abs() * (s_e * hs_e + p_x * hs_x)
        d[f"{lab}_gdn"] = d[f"{lab}_g"] + pnl / d["m0b"]
        d[f"{lab}_ok"] &= np.isfinite(d[f"{lab}_gdn"])
    d["H_net"] = d["k0_usd"] / d["m0b"]
    return d


def choose(e: pd.DataFrame, rule: str) -> pd.Series:
    """Chosen label per event: K0 unless an available neighbour is strictly better."""
    best = pd.Series("k0", index=e.index)
    if rule == "maxV":
        bestv = e["k0_V"].astype(float).copy()
        for lab in NB:
            v = e[f"{lab}_V"].astype(float)
            m = e[f"{lab}_ok"] & v.notna() & (v > bestv)
            best[m], bestv[m] = lab, v[m]
        return best
    raise ValueError(f"unknown rule {rule}")


def random_null(e: pd.DataFrame, k: int, n: int) -> np.ndarray:
    g = np.column_stack([e[f"{lab}_gdn"].to_numpy(float) for lab in NB])
    ok = np.column_stack([e[f"{lab}_ok"].to_numpy(bool) for lab in NB])
    elig = np.flatnonzero(ok.any(axis=1))
    rng = np.random.default_rng(SEED)
    out = np.empty(N_DRAWS)
    for b in range(N_DRAWS):
        idx = rng.choice(elig, size=k, replace=False)
        tot = 0.0
        for i in idx:
            tot += g[i, rng.choice(np.flatnonzero(ok[i]))]
        out[b] = tot / n
    return out


def score(e: pd.DataFrame, rule: str) -> dict:
    ch = choose(e, rule)
    gain = pd.Series(0.0, index=e.index)
    hs = pd.Series(0.0, index=e.index)
    dist = pd.Series(np.nan, index=e.index)
    for lab in NB:
        m = ch == lab
        gain[m] = e.loc[m, f"{lab}_gdn"]
        hs[m] = e.loc[m, f"{lab}_hs_saved"]
        dist[m] = (
            (e.loc[m, f"{lab}_intrinsic"] - e.loc[m, "k0_intrinsic"]) / e.loc[m, "m0b"]
        )
    sw = ch != "k0"
    k, n = int(sw.sum()), len(e)
    nul = random_null(e, k, n) if k else np.array([np.nan])
    r = ci(gain, e["exit_date"])
    return {
        "rule": rule, "n": n, "switched": k, "share_switched": k / n,
        "primary_gain": r,
        "null_percentile": float(100 * (nul < gain.sum() / n).mean()),
        "null_median": float(np.median(nul)),
        "driver_gain_minus_hs_saved_on_switched": float((gain - hs)[sw].mean()) if k else None,
        "hs_saved_on_switched": float(hs[sw].mean()) if k else None,
        "gain_on_switched": float(gain[sw].mean()) if k else None,
        "settlement_intrinsic_change_on_switched": float(dist[sw].mean()) if k else None,
        "share_chosen_closer_at_expiry": float((dist[sw] < 0).mean()) if k else None,
        "level_H_net": ci(e["H_net"], e["exit_date"]),
        "level_chosen": ci(e["H_net"] + gain, e["exit_date"]),
        "_gain": gain, "_sw": sw,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", choices=list(BLOCKS), required=True)
    ap.add_argument("--trial", type=int, default=2773)
    ap.add_argument("--rule", default="maxV")
    a = ap.parse_args(argv)
    y0, y1 = BLOCKS[a.block]
    d = load()
    d = d[d["year"].between(y0, y1)]
    funnel = {"built_ok": int(len(d))}
    elig = d["km1_ok"] | d["kp1_ok"]
    funnel["no_buildable_neighbour"] = int((~elig).sum())
    funnel["H_net_mean_dropped"] = float(d.loc[~elig, "H_net"].mean()) if (~elig).any() else None
    funnel["H_net_mean_kept"] = float(d.loc[elig, "H_net"].mean())
    e = d[elig].copy()
    res = score(e, a.rule)
    sens = score(e[~e["stale"]].copy(), a.rule)
    out = {k: v for k, v in res.items() if not k.startswith("_")}
    out.update(trial=a.trial, block=a.block, years=[y0, y1], funnel=funnel,
               stale_share=float(e["stale"].mean()),
               excluding_stale={k: v for k, v in sens.items() if not k.startswith("_")})
    p = out["primary_gain"]
    out["verdict"] = (
        "pass" if (p["low"] > 0 and out["null_percentile"] >= 95
                   and (out["driver_gain_minus_hs_saved_on_switched"] or -1) > 0)
        else "fail"
    )
    fn = HERE / f"results_oi_{a.trial}_{a.block}.json"
    fn.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    log_block_view(VIEWS, panel="hedged_event_hold_megacap", period=f"{y0}-{y1 % 100:02d}",
                   outcome_family="hedged_hold", feature_family="open_interest_proxy",
                   viewed_by=f"E4 trial {a.trial:,}")
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
