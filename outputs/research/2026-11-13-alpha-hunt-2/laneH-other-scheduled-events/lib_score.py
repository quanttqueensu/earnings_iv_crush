"""lib_score.py: shared scoring helpers for lane H (levels, paired event-minus-control, null, trial log)."""
from __future__ import annotations

import csv
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\jodor\Documents\QUANTT_IVCrush_Project")
from earnings_iv_crush.research.protocol import date_clustered_ci, matched_random_null  # noqa: E402

COLS = ["trial_id", "hypothesis", "mechanism", "block", "N", "effect", "ci_low", "ci_high", "t",
        "null_percentile", "basis", "verdict"]


def usable(w: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ok = w[(w["price_status"] == "ok") & (~w["earn_in_window"].fillna(True).astype(bool))]
    ev = ok[ok["shift"] == 0]
    ct = ok[(ok["shift"] != 0) & (~ok["other_event_in_window"].fillna(False).astype(bool))]
    ct = ct[ct["event_id"].isin(ev["event_id"])]
    return ev, ct


def level(ev: pd.DataFrame, col: str) -> dict:
    v = ev[col].astype(float)
    m = v.notna()
    ci = date_clustered_ci(v[m], ev.loc[m, "event_date"], stat=np.mean)
    hw = (ci.high - ci.low) / 2
    return {"N": ci.n, "effect": ci.point, "ci_low": ci.low, "ci_high": ci.high,
            "t": ci.point / (hw / 1.96) if hw > 0 else np.nan, "clusters": ci.clusters}


def paired(ev: pd.DataFrame, ct: pd.DataFrame, col: str) -> tuple[dict, pd.DataFrame]:
    cm = ct.groupby("event_id")[col].mean().rename("ctrl")
    d = ev.set_index("event_id")[[col, "event_date", "ticker"]].join(cm, how="inner").dropna()
    d["diff"] = d[col] - d["ctrl"]
    out = level(d.reset_index().rename(columns={"diff": "_d"}), "_d")
    pool = pd.concat([ev.assign(sel=True), ct.assign(sel=False)])
    pool = pool[pool["event_id"].isin(d.index)].dropna(subset=[col])
    nc = matched_random_null(pool[col].to_numpy(float), pool["sel"].to_numpy(bool), stat=np.mean)
    out["null_percentile"] = nc.percentile
    return out, d


def log_trial(path: str, row: dict) -> None:
    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["trial_id"] != str(row["trial_id"])]
    rows.append({k: (str(row[k]) if k == "trial_id" else f"{row[k]:.5g}" if isinstance(row.get(k), float) else row.get(k, ""))
                 for k in COLS})
    rows.sort(key=lambda r: str(r["trial_id"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
