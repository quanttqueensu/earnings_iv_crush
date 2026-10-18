"""
research_date_shift.py
Pre-registered test: do earnings-date delays predict a worse short earnings straddle?

``research/selection/preregs/date_shift_prereg.md``. The shift is this quarter's reporting lag minus the same quarter's
lag a year earlier (Compustat ``rdq`` minus ``datadate``), public at entry because report dates are
scheduled in advance (Johnson and So, JFQA 2018). Two blocks never used for this signal: the
2013-2024 megacap panel and the attrition-corrected 2025-2026 broad block.

Usage:
    python research/selection/research_date_shift.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402

PREREG = Path("research/selection/preregs/date_shift_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_date_shift.json")
FUNDQ = [
    Path("data/processed/wrds/raw/comp_na_daily_all.fundq.a7e4dcbbed3b.parquet"),
    Path("data/processed/wrds/raw/comp_na_daily_all.fundq.a2b512f91484.parquet"),
]
PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
BROAD = Path("outputs/research/oos_2026_attrition_audit/events.csv")
BROAD_EVENTS = Path("outputs/research/events_broad_oos_2025.parquet")
OUT = Path("outputs/research/date_shift")
DELAY, ONTIME, ADVANCE = 5, 2, -5
MATCH_DAYS = 3
N_BOOT = 5000
N_NULL = 1000
SEED = 0
N_TRIALS = 1510


def _check_prereg() -> None:
    want = json.loads(PREREG_JSON.read_text())["prereg_sha256"]
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != want:
        raise SystemExit("pre-registration hash mismatch")


def shifts() -> pd.DataFrame:
    q = pd.concat([pd.read_parquet(p) for p in FUNDQ]).dropna(subset=["rdq"])
    q = q.drop_duplicates(["gvkey", "datadate"])
    q["rdq"] = pd.to_datetime(q["rdq"])
    q["datadate"] = pd.to_datetime(q["datadate"])
    q["lag"] = (q["rdq"] - q["datadate"]).dt.days
    q = q.sort_values(["gvkey", "datadate"])
    q["shift"] = q["lag"] - q.groupby(["gvkey", "fqtr"])["lag"].shift(1)
    q["tic"] = q["tic"].astype(str).str.replace(".", "-", regex=False)
    return q[["tic", "rdq", "shift"]].dropna()


def attach(ev: pd.DataFrame, q: pd.DataFrame, block: str) -> pd.DataFrame:
    ev = ev.copy()
    ev["announce_date"] = pd.to_datetime(ev["announce_date"])
    m = ev.merge(q, left_on="ticker", right_on="tic", how="left")
    m = m[(m["rdq"] - m["announce_date"]).dt.days.abs() <= MATCH_DAYS]
    m = m.sort_values("shift").drop_duplicates(["ticker", "announce_date"])
    print(f"  {block}: events {len(ev)}, matched {len(m)}", flush=True)
    if m.empty:
        raise SystemExit(f"no events matched in {block}")
    m["group"] = np.select(
        [m["shift"] >= DELAY, m["shift"].abs() <= ONTIME, m["shift"] <= ADVANCE],
        ["delayed", "on_time", "advanced"],
        default="other",
    )
    m["block"] = block
    return m.drop(columns=["tic", "rdq"])


def load() -> pd.DataFrame:
    q = shifts()
    p = pd.read_parquet(PANEL)
    pm = p[["ticker", "announce_date", "return_on_margin", "realised_move", "implied_move"]].rename(
        columns={"return_on_margin": "rom"}
    )
    pm["ratio"] = pm["realised_move"] / pm["implied_move"]
    b = pd.read_csv(BROAD, parse_dates=["entry_date"])
    ev = pd.read_parquet(BROAD_EVENTS, columns=["ticker", "announce_date", "entry_date"])
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    ev = ev.drop_duplicates(["ticker", "entry_date"])  # two exact duplicate calendar rows
    b = b.drop_duplicates(["ticker", "entry_date"])
    b = b.merge(ev, on=["ticker", "entry_date"], how="left", validate="many_to_one")
    bm = b.rename(columns={"net_rom": "rom", "realised_over_implied": "ratio"})[
        ["ticker", "announce_date", "rom", "ratio"]
    ]
    d = pd.concat([attach(pm, q, "megacap_2013_2024"), attach(bm, q, "broad_2025_2026")])
    return d.dropna(subset=["rom", "ratio"]).reset_index(drop=True)


def _diff_ci(d: pd.DataFrame, col: str, a: str, b: str) -> tuple[float, list[float]]:
    sub = d[d["group"].isin([a, b])].reset_index(drop=True)
    x = sub[col].to_numpy(dtype=float)
    ga = (sub["group"] == a).to_numpy()
    keys = sub["announce_date"].astype(str).to_numpy()

    def stat(ix: np.ndarray) -> float:
        j = ix.astype(int)
        xa, xb = x[j][ga[j]], x[j][~ga[j]]
        return float(xa.mean() - xb.mean()) if len(xa) and len(xb) else float("nan")

    point = float(x[ga].mean() - x[~ga].mean())
    lo, hi = cluster_bootstrap_ci(
        np.arange(len(x), dtype=float), keys, stat, n_boot=N_BOOT, seed=SEED
    )
    return point, [float(lo), float(hi)]


def score() -> None:
    _check_prereg()
    OUT.mkdir(parents=True, exist_ok=True)
    d = load()
    d.to_csv(OUT / "events.csv", index=False)
    counts = d.groupby(["block", "group"]).size().unstack(fill_value=0)
    print(counts.to_string())
    res: dict[str, Any] = {"counts": counts.to_dict()}
    res["D_pooled"], res["D_pooled_ci"] = _diff_ci(d, "rom", "on_time", "delayed")
    res["D_by_block"] = {}
    for blk, g in d.groupby("block"):
        pt, ci = _diff_ci(g.reset_index(drop=True), "rom", "on_time", "delayed")
        res["D_by_block"][blk] = {"D": pt, "ci": ci}
    res["ratio_delayed_minus_ontime"], res["ratio_ci"] = _diff_ci(d, "ratio", "delayed", "on_time")
    # trading rule: drop delayed events from the unconditional book, against random drops
    rng = np.random.default_rng(SEED)
    base = d["rom"].mean()
    kept = d[d["group"] != "delayed"]["rom"].mean()
    lift = float(kept - base)
    null = np.empty(N_NULL)
    nd = d.groupby("block")["group"].apply(lambda s: int((s == "delayed").sum()))
    for k in range(N_NULL):
        drop = np.zeros(len(d), dtype=bool)
        for blk, n in nd.items():
            ix = np.flatnonzero((d["block"] == blk).to_numpy())
            drop[rng.choice(ix, n, replace=False)] = True
        null[k] = d.loc[~drop, "rom"].mean() - base
    res["exclusion_lift"] = lift
    res["exclusion_null_p95"] = float(np.quantile(null, 0.95))
    res["exclusion_null_pct"] = float((null < lift).mean())
    book = d[d["group"] != "delayed"]["rom"].reset_index(drop=True)
    res["book_sharpe"] = float(book.mean() / book.std(ddof=1))
    res["book_dsr"] = float(deflated_sharpe_ratio(book, n_trials=N_TRIALS))
    res["pass"] = bool(
        res["D_pooled_ci"][0] > 0
        and all(v["D"] > 0 for v in res["D_by_block"].values())
        and res["ratio_ci"][0] > 0
        and lift > res["exclusion_null_p95"]
    )
    res["verdict"] = "PASS" if res["pass"] else "FAIL"
    # secondary
    res["advanced_minus_ontime"], res["advanced_ci"] = _diff_ci(d, "rom", "advanced", "on_time")
    res["spearman_shift_rom"] = float(spearmanr(d["shift"], d["rom"])[0])
    res["spearman_shift_ratio"] = float(spearmanr(d["shift"], d["ratio"])[0])
    res["group_means"] = (
        d.groupby(["block", "group"])[["rom", "ratio"]]
        .mean()
        .round(4)
        .reset_index()
        .to_dict("records")
    )
    print(json.dumps(res, indent=1, default=str))
    json.dump(res, open(OUT / "summary.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    score()
