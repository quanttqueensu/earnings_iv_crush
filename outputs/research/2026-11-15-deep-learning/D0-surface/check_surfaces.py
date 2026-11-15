"""
check_surfaces.py
D0 step 5 checks on the built surface tensor: the funnel, fill by block, reconciliation of the
front ATM straddle IV and half-spread against the lane E panel, five hand spot checks against
the raw chain files on an independent code path, and the sparse-surface attrition test
(trial 3,135).

Prints counts, aggregates and the spot checks' derived numbers only (no vendor rows). Writes
``check_surfaces.json`` and appends trial 3,135 to ``trials.csv`` when run on the full file.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D0-surface/check_surfaces.py [--npz PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.config import CHAIN_SURFACE  # noqa: E402
from earnings_iv_crush.research.hedged_hold import option_iv, straddle_iv  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci, log_block_view  # noqa: E402

NPZ = ROOT / "data" / "cache" / "dl" / "surfaces_2026-11-15.npz"
TARGETS = HERE / "targets.parquet"
BASE = ROOT / "outputs/research/2026-11-14-slate-tests/L1-corrections/base_corrected.parquet"
PANEL = ROOT / "outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/panel.parquet"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
BLOCKS_VIEWED = HERE / "blocks_viewed.csv"
TRIALS = HERE / "trials.csv"
BLOCKS = ("2013-18", "2019-24", "2025-26")
N_SPOT = 5
SPOT_SEED = 20261115
OCC = re.compile(r"^(?P<root>.+?)\s*(?P<ymd>\d{6})(?P<right>[CP])(?P<k>\d{8})$")


def _diff_ci(values: np.ndarray, group: np.ndarray, keys: np.ndarray) -> Any:
    v, g = np.asarray(values, float), np.asarray(group, bool)

    def stat(idx: np.ndarray) -> float:
        i = idx.astype(int)
        a, b = v[i][g[i]], v[i][~g[i]]
        return float(a.mean() - b.mean()) if a.size and b.size else float("nan")

    return date_clustered_ci(np.arange(v.size, dtype=float), keys, stat)


def _q(a: np.ndarray) -> dict[str, float]:
    a = a[np.isfinite(a)]
    return {
        "n": int(a.size),
        "median": float(np.median(a)),
        "p99": float(np.quantile(a, 0.99)),
        "max": float(a.max()),
    }


# ── spot check on an independent path ────────────────────────────────────────


def _spot(row: pd.Series, grid: np.ndarray, sc: dict[str, float], x: np.ndarray) -> dict[str, Any]:
    """Re-derive the ATM straddle IV and the call and put IV at x = 0 from the raw file."""
    raw = pd.read_parquet(CHAINS / f"{row['ticker']}_{row['entry_date']}.parquet").reset_index()
    cut = pd.Timestamp(f"{row['entry_date']} 15:59", tz="America/New_York")
    raw = raw[raw["ts_recv"] <= cut]
    parts = raw["symbol"].astype(str).str.extract(OCC)
    raw = raw.assign(
        right=parts["right"],
        strike=parts["k"].astype(float) / 1000.0,
        expiry=pd.to_datetime(parts["ymd"], format="%y%m%d"),
    )
    raw = raw.sort_values("ts_recv").drop_duplicates(["expiry", "strike", "right"], keep="last")
    exp = pd.Timestamp(row["expiry"])
    e = raw[(raw["expiry"] == exp) & (raw["bid_px_00"] > 0) & (raw["ask_px_00"] > 0)]
    e = e.assign(mid=(e["bid_px_00"] + e["ask_px_00"]) / 2)
    w = e.pivot_table(index="strike", columns="right", values="mid").dropna()
    f = float(row["front_fwd"])
    k = float(w.index[np.argmin(np.abs(w.index.to_numpy() - f))])
    end = pd.Timestamp(f"{exp.date()} 16:00", tz="America/New_York")
    tau = (end - cut).total_seconds() / 86400 / 365
    disc = float(np.exp(-sc["rate"] * tau))
    # Black-76 with discount D is D times the zero-rate price on the forward.
    sig = straddle_iv(float(w.loc[k, "C"] + w.loc[k, "P"]) / disc, f, k, tau)
    out: dict[str, Any] = {
        "event": f"{row['ticker']} {row['entry_date']}",
        "atm_strike": [k, sc["atm_strike_front"]],
        "sigma_atm": [sig, sc["sigma_atm_front"]],
        "tau": [tau, sc["tau_front"]],
    }
    for r, ci in (("C", 0), ("P", 1)):
        side = w[r] if r in w else pd.Series(dtype=float)
        ivs = np.array([option_iv(p / disc, f, kk, tau, r) for kk, p in side.items()])
        ok = np.isfinite(ivs)
        # Two-sided strikes of this side alone (the pivot above kept both-legged strikes; the
        # grid uses every two-sided strike of the side).
        s2 = e[e["right"] == r].set_index("strike")["mid"].sort_index()
        ks2 = s2.index.to_numpy(float)
        iv2 = np.array([option_iv(p / disc, f, kk, tau, r) for kk, p in s2.items()])
        x2 = np.log(ks2 / f) / (sig * np.sqrt(tau))
        m2 = np.isfinite(iv2)
        j = np.searchsorted(x2[m2], 0.0)
        hand = float(np.interp(0.0, x2[m2], iv2[m2] / sig)) if 0 < j < m2.sum() else float("nan")
        out[f"{r}_iv_rel_x0"] = [hand, float(grid[ci, 0, int(np.argmin(np.abs(x)))])]
        out[f"{r}_n_strikes"] = int(ok.sum())
    return out


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--npz", type=Path, default=NPZ)
    args = ap.parse_args(argv)
    full = args.npz.resolve() == NPZ.resolve()
    z = np.load(args.npz)
    grid, S = z["grid"], z["scalars"]
    names = [str(s) for s in z["scalar_names"]]
    sc = pd.DataFrame(S, columns=names)
    sc["ticker"], sc["entry_date"] = z["ticker"], z["entry_date"]
    t = pd.read_parquet(TARGETS)
    t["entry_date"] = t["entry_date"].dt.strftime("%Y-%m-%d")
    t = t.iloc[: len(sc)].reset_index(drop=True)
    if (
        not (t["ticker"].to_numpy() == sc["ticker"].to_numpy()).all()
        or not (t["entry_date"].to_numpy() == sc["entry_date"].to_numpy()).all()
    ):
        raise AssertionError("surface keys differ from targets.parquet order")
    res: dict[str, Any] = {
        "npz": str(args.npz.resolve().relative_to(ROOT)),
        "shape": list(grid.shape),
    }

    # Funnel.
    ok_f, ok_n = sc["front_found"] == 1, sc["next_found"] == 1
    allmask = sc["fill"] == 0
    funnel = {
        "events": len(sc),
        "file present": int((sc["file_present"] == 1).sum()),
        "front expiry found (ATM straddle IV defined)": int(ok_f.sum()),
        "next expiry found (parity forward and ATM IV defined)": int(ok_n.sum()),
        "both found": int((ok_f & ok_n).sum()),
        "all-mask events (fill 0)": int(allmask.sum()),
        "sparse (fill < 0.5)": int((sc["fill"] < CHAIN_SURFACE.sparse_fill).sum()),
        "rows stamped after 15:59 ET (dropped)": int(sc["n_after_cutoff"].sum()),
        "rows superseded by a later row of the contract": int(sc["n_superseded"].sum()),
        "unparsed symbols": int(sc["n_unparsed"].sum()),
        "next parity on fewer than 5 pairs": int((ok_n & (sc["n_parity_next"] < 5)).sum()),
    }
    print("[funnel]", json.dumps(funnel, indent=1))
    by_block = {}
    for blk in BLOCKS:
        m = (t["block"] == blk).to_numpy()
        by_block[blk] = {
            "events": int(m.sum()),
            "front_found": int((ok_f & m).sum()),
            "next_found": int((ok_n & m).sum()),
            "fill_mean": float(sc.loc[m, "fill"].mean()),
            "fill_front_mean": float(sc.loc[m, "fill_front"].mean()),
            "fill_next_mean": float(sc.loc[m, "fill_next"].mean()),
            "fill_no_gap_rule_mean": float(sc.loc[m, "fill_no_gap_rule"].mean()),
            "all_mask": int((allmask & m).sum()),
            "sparse": int(((sc["fill"] < CHAIN_SURFACE.sparse_fill) & m).sum()),
        }
    print("[fill by block]", json.dumps(by_block, indent=1))
    pt = grid[:, -1].mean(axis=0)
    res["fill_by_point"] = {"front": pt[0].round(3).tolist(), "next": pt[1].round(3).tolist()}
    print("[fill by grid point]", res["fill_by_point"])
    res["funnel"], res["by_block"] = funnel, by_block

    # Reconciliation against the lane E panel.
    p = pd.read_parquet(PANEL, columns=["ticker", "entry_date", "front_iv", "half_spread"])
    b = pd.read_parquet(BASE, columns=["ticker", "entry_date", "strike"])
    for f in (p, b):
        f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.strftime("%Y-%m-%d")
    r = sc.merge(p, on=["ticker", "entry_date"], how="left", validate="one_to_one").merge(
        b, on=["ticker", "entry_date"], how="left", validate="one_to_one"
    )
    f = r["front_found"] == 1
    strike_match = np.isclose(r.loc[f, "atm_strike_front"], r.loc[f, "strike"])
    d_hs = (r["atm_half_spread_front"] - r["half_spread"]).abs()[f].to_numpy()
    d_ivx = (r["atm_iv_front_panel_convention"] - r["front_iv"]).abs()[f].to_numpy()
    d_iv = (r["sigma_atm_front"] - r["front_iv"]).abs()[f].to_numpy()
    c0 = int(np.argmin(np.abs(z["grid_x"])))
    g0 = 0.5 * (grid[:, 0, 0, c0] + grid[:, 1, 0, c0]) * r["sigma_atm_front"].to_numpy()
    d_g0 = np.abs(g0 - r["front_iv"].to_numpy())[f.to_numpy()]
    rel_iv = d_iv / r.loc[f, "front_iv"].to_numpy()
    recon = {
        "N": int(f.sum()),
        "atm_strike_equals_base_strike": [int(strike_match.sum()), int(f.sum())],
        "half_spread_abs_diff": _q(d_hs),
        "half_spread_within_tol": float(np.mean(d_hs <= CHAIN_SURFACE.recon_spread_tol)),
        "iv_panel_convention_abs_diff": _q(d_ivx),
        "iv_surface_convention_abs_diff": _q(d_iv),
        "iv_surface_convention_rel_diff": _q(rel_iv),
        "iv_within_tol": float(np.mean(d_iv <= CHAIN_SURFACE.recon_iv_tol)),
        "iv_grid_x0_mean_call_put_abs_diff": _q(d_g0),
        "tolerances": {
            "iv": CHAIN_SURFACE.recon_iv_tol,
            "half_spread": CHAIN_SURFACE.recon_spread_tol,
        },
    }
    print("[reconciliation]", json.dumps(recon, indent=1))
    res["reconciliation"] = recon

    # Spot checks.
    rng = np.random.default_rng(SPOT_SEED)
    pool = np.flatnonzero((f & (r["next_found"] == 1)).to_numpy())
    pick = rng.choice(pool, size=min(N_SPOT, pool.size), replace=False)
    bb = pd.read_parquet(BASE, columns=["ticker", "entry_date", "expiry", "front_fwd"])
    bb["entry_date"] = pd.to_datetime(bb["entry_date"]).dt.strftime("%Y-%m-%d")
    bb = bb.set_index(["ticker", "entry_date"])
    spots = []
    for i in pick:
        row = bb.loc[(sc.at[i, "ticker"], sc.at[i, "entry_date"])]
        info = pd.Series(
            {"ticker": sc.at[i, "ticker"], "entry_date": sc.at[i, "entry_date"],
             "expiry": row["expiry"], "front_fwd": row["front_fwd"]}
        )  # fmt: skip
        s = _spot(info, grid[i], sc.iloc[i].to_dict(), z["grid_x"])
        spots.append(s)
        print("[spot]", json.dumps(s, default=float))
    res["spot_checks"] = spots

    # Attrition: do sparse surfaces depend on the outcome?
    if full:
        for blk in ("2013-18", "2019-24"):
            log_block_view(
                BLOCKS_VIEWED,
                panel="base_corrected",
                period=blk,
                outcome_family="hedged_hold_H_net",
                feature_family="chain_surface_fill",
                viewed_by="D0 check_surfaces (sparse-surface attrition, trial 3,135)",
                kind="trial",
            )
    att: dict[str, Any] = {}
    sparse = (sc["fill"] < CHAIN_SURFACE.sparse_fill).to_numpy()
    for label, m in (
        ("2013-24", t["block"].isin(["2013-18", "2019-24"]).to_numpy()),
        ("2013-18", (t["block"] == "2013-18").to_numpy()),
        ("2019-24", (t["block"] == "2019-24").to_numpy()),
    ):
        m = m & t["target_ok"].to_numpy()
        for col in ("H_net", "residual_value"):
            v = t[col].to_numpy(float)[m] * 100
            g = sparse[m]
            if g.sum() < 2 or (~g).sum() < 2:
                att[f"{label} {col}"] = {"n_sparse": int(g.sum()), "note": "too few to test"}
                continue
            w = ttest_ind(v[g], v[~g], equal_var=False)
            ci = _diff_ci(v, g, t["announce_date"].to_numpy()[m])
            att[f"{label} {col}"] = {
                "n_sparse": int(g.sum()),
                "n_rest": int((~g).sum()),
                "mean_sparse": float(v[g].mean()),
                "mean_rest": float(v[~g].mean()),
                "diff": float(ci.point),
                "ci": [float(ci.low), float(ci.high)],
                "clusters": int(ci.clusters),
                "welch_t": float(w.statistic),
                "welch_p": float(w.pvalue),
            }
            a = att[f"{label} {col}"]
            print(
                f"[attrition {label} {col}] sparse {a['n_sparse']} vs {a['n_rest']}: "
                f"{a['mean_sparse']:+.3f} vs {a['mean_rest']:+.3f} % of m0; diff {a['diff']:+.3f} "
                f"[{a['ci'][0]:+.3f}, {a['ci'][1]:+.3f}]; Welch t {a['welch_t']:+.2f}, "
                f"p {a['welch_p']:.3f}"
            )
    res["attrition"] = att
    out = HERE / ("check_surfaces.json" if full else "check_surfaces_subset.json")
    out.write_text(json.dumps(res, indent=1, default=float) + "\n", encoding="utf-8")
    if full and "2013-24 H_net" in att and "diff" in att["2013-24 H_net"]:
        a, rv = att["2013-24 H_net"], att["2013-24 residual_value"]
        with TRIALS.open("a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(
                [3135, "D0 attrition: sparse surfaces (grid fill < 0.5)",
                 "sparse minus rest mean, Welch t and date-clustered 95%", "2013-24",
                 f"{a['n_sparse']} vs {a['n_rest']}",
                 f"H_net {a['diff']:+.3f} % of m0 (Welch p {a['welch_p']:.3f}); residual_value "
                 f"{rv['diff']:+.3f} % of m0 (Welch p {rv['welch_p']:.2g})",
                 f"H_net [{a['ci'][0]:+.3f}, {a['ci'][1]:+.3f}]; residual_value "
                 f"[{rv['ci'][0]:+.3f}, {rv['ci'][1]:+.3f}]",
                 "see check_surfaces.json (exploratory)"]
            )  # fmt: skip
    print(f"written {out.name}")


if __name__ == "__main__":
    main()
