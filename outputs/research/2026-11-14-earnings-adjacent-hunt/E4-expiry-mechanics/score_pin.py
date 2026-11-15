"""
score_pin.py
E4 trial 2,772: do CRSP closes pin to listed strikes on the post-earnings expiry session?
Scores the declaration in ``diagnosis.log`` (entry 2) on one block per call.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/score_pin.py \
        --block discovery

Primary: mean over events of pin_E - pin_C, where pin = 1{close within USD 0.125 of a listed
strike of the front expiry} and pin_C averages the control sessions E+1, E+2 and E-1 when E-1 falls
after the reaction session. Date-clustered 95% interval, clusters = expiry session.

References
----------
Ni, S. X., Pearson, N. D. and Poteshman, A. M. (2005) Stock price clustering on option expiration
dates. Journal of Financial Economics 78(1), 49-87.
Zhang, G., Chen, H. and Cai, F. (2015) Weekly options on stock pinning. Journal of Business and
Economic Studies 21(1/2), 62-.
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

from earnings_iv_crush.research.protocol import date_clustered_ci, log_block_view  # noqa: E402

HERE = Path(__file__).resolve().parent
BAND = 0.125  # USD, the NPP (2005) and Zhang et al. (2015) pin band
BLOCKS = {"discovery": (2013, 2018), "heldout": (2019, 2024)}
VIEWS = HERE / "block_views.csv"


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def prepare(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["year"] = pd.to_datetime(d["entry_date"]).dt.year
    for lab in ("E", "Em1", "Ep1", "Ep2"):
        d[f"pin_{lab}"] = (d[f"dist_{lab}"] <= BAND + 1e-9).astype(float)
        d.loc[~d[f"inside_{lab}"].fillna(False).astype(bool), f"pin_{lab}"] = np.nan
    ctrl = d[["pin_Ep1", "pin_Ep2"]].copy()
    ctrl["pin_Em1"] = np.where(d["em1_after_reaction"], d["pin_Em1"], np.nan)
    d["pin_C"] = ctrl.mean(axis=1, skipna=True)
    d["n_ctrl"] = ctrl.notna().sum(axis=1)
    d["diff"] = d["pin_E"] - d["pin_C"]
    # grid at the expiry close, for the by-spacing table
    d["grid"] = d["spacing_E"].round(2)
    return d


def ci(x: pd.Series, dates: pd.Series) -> dict:
    iv = date_clustered_ci(x.to_numpy(float), dates, _mean)
    se = (iv.high - iv.low) / 3.92
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n,
            "clusters": iv.clusters, "t": iv.point / se if se > 0 else float("nan")}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", choices=list(BLOCKS), required=True)
    a = ap.parse_args(argv)
    y0, y1 = BLOCKS[a.block]
    d = prepare(pd.read_parquet(HERE / "pin_inputs.parquet"))
    d = d[(d["year"] >= y0) & (d["year"] <= y1)]
    n0 = len(d)
    funnel = {"events": n0, "split_near": int(d["split_near"].sum())}
    d = d[~d["split_near"]]
    funnel["close_outside_grid_E"] = int(d["pin_E"].isna().sum())
    funnel["no_control"] = int((d["n_ctrl"] == 0).sum())
    ok = d["pin_E"].notna() & (d["n_ctrl"] > 0)
    s = d[ok].copy()
    funnel["scored"] = len(s)
    dates = pd.to_datetime(s["expiry_session"])
    res = {
        "trial": 2772, "block": a.block, "years": [y0, y1], "funnel": funnel,
        "primary_diff": ci(s["diff"], dates),
        "pin_E": float(s["pin_E"].mean()), "pin_C": float(s["pin_C"].mean()),
        "by_panel": {}, "by_grid": {}, "relative_band_0p05": None,
    }
    for p, g in s.groupby("panel"):
        res["by_panel"][p] = {**ci(g["diff"], pd.to_datetime(g["expiry_session"])),
                              "pin_E": float(g["pin_E"].mean()), "pin_C": float(g["pin_C"].mean())}
    for gr, g in s.groupby("grid"):
        if len(g) >= 100:
            res["by_grid"][str(gr)] = {**ci(g["diff"], pd.to_datetime(g["expiry_session"])),
                                       "pin_E": float(g["pin_E"].mean()),
                                       "pin_C": float(g["pin_C"].mean())}
    # band relative to the local strike spacing (secondary, scale-free)
    rel = {}
    for lab in ("E", "Em1", "Ep1", "Ep2"):
        rel[lab] = (s[f"dist_{lab}"] / s[f"spacing_{lab}"] <= 0.05).astype(float)
        rel[lab][s[f"spacing_{lab}"].isna()] = np.nan
    rc = pd.concat([rel["Ep1"], rel["Ep2"],
                    rel["Em1"].where(s["em1_after_reaction"])], axis=1).mean(axis=1)
    rdiff = (rel["E"] - rc).dropna()
    res["relative_band_0p05"] = ci(rdiff, pd.to_datetime(s.loc[rdiff.index, "expiry_session"]))
    out = HERE / f"results_pin_{a.block}.json"
    out.write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    for p in sorted(s["panel"].unique()):
        pname = "hedged_event_hold" if p == "broad" else "hedged_event_hold_megacap"
        log_block_view(VIEWS, panel=pname,period=f"{y0}-{y1 % 100:02d}",
                       outcome_family="expiry_pinning", feature_family="strike_grid",
                       viewed_by="E4 trial 2,772")
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
