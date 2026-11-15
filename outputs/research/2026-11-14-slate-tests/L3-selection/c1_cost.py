"""c1_cost.py: descriptive cost read for C1, the hedged hold re-valued at the implied borrow.

Each dividend-free 2013-24 event is passed through L1's ``build_base.build_one`` (imported, never
edited) with ``HoldCorrectionsConfig.borrow_fee_bps`` replaced by max(general collateral, implied
borrow). Events whose implied borrow is at or below general collateral must reproduce the stored
``H_corr`` exactly, which is the reconciliation check. Not a trial: it re-prices a cost.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c1_cost.py
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

from earnings_iv_crush.config import HOLD_CORRECTIONS  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

BB_PATH = HERE.parent / "L1-corrections" / "build_base.py"
_BB: Any = None


def _init() -> None:
    global _BB
    spec = importlib.util.spec_from_file_location("l1_build_base", BB_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["l1_build_base"] = mod
    spec.loader.exec_module(mod)
    mod._init_worker()
    _BB = mod


def one(args: tuple[dict, dict, float]) -> dict:
    frow, brow, bps = args
    _BB.FC = dataclasses.replace(HOLD_CORRECTIONS, borrow_fee_bps=bps)
    r = _BB.build_one((frow, brow))
    return {
        "ticker": brow["ticker"],
        "entry_date": brow["entry_date"],
        "bps": bps,
        "H_corr_borrow": r.get("H_corr", np.nan),
        "h_status_b": r.get("h_status"),
        "c_fin_borrow": r.get("c_financing", np.nan),
    }


def main() -> None:
    _init()
    base = pd.read_parquet(_BB.BASE)
    f = pd.read_parquet(_BB.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    f = f.drop_duplicates(["ticker", "entry_date"])
    m = base.merge(
        f, on=["ticker", "entry_date"], how="left", suffixes=("_b", ""), validate="one_to_one"
    )
    bw = pd.read_parquet(HERE / "c1_borrow.parquet")
    m = m.merge(
        bw[["ticker", "entry_date", "borrow", "div_free"]],
        on=["ticker", "entry_date"],
        how="left",
        validate="one_to_one",
    )
    m = m[(m["src"] == "crsp") & (m["div_free"] == 1) & m["borrow"].notna()]
    gc = HOLD_CORRECTIONS.borrow_fee_bps
    fcols = list(f.columns)
    jobs = [
        (
            {c: r[c] for c in fcols},
            {c: r[c] for c in ("ticker", "entry_date", "src", "H", "settle")},
            float(max(gc, 1e4 * r["borrow"])),
        )
        for _, r in m.iterrows()
    ]
    print(f"jobs {len(jobs)} (CRSP 2013-24, dividend-free window, borrow known)", flush=True)
    with ProcessPoolExecutor(max_workers=6, initializer=_init) as ex:
        res = pd.DataFrame(list(ex.map(one, jobs, chunksize=20)))
    b = lib.load_base()
    d = res.merge(
        b[["ticker", "entry_date", "H_corr", "exit_date", "year"]],
        on=["ticker", "entry_date"],
        validate="one_to_one",
    )
    d = d.merge(bw[["ticker", "entry_date", "borrow"]], on=["ticker", "entry_date"])
    d["dH"] = d["H_corr_borrow"] - d["H_corr"]
    at_gc = d["bps"] <= gc
    gap = float(np.nanmax(np.abs(d.loc[at_gc, "dH"]))) if at_gc.any() else np.nan
    print(f"reconciliation: events at GC {int(at_gc.sum())}, max |dH| {gap:.2e}")
    print(d["h_status_b"].value_counts().to_string())
    d["dec"] = pd.qcut(d["borrow"], 10, labels=False)
    out: dict[str, Any] = {"N": int(len(d)), "recon_max_abs_dH_at_gc": gap}
    ci = date_clustered_ci(d["dH"], d["exit_date"], np.mean)
    out["all"] = {"mean_dH_pct": 100 * ci.point, "lo": 100 * ci.low, "hi": 100 * ci.high, "n": ci.n}
    rows = []
    for k, g in d.groupby("dec"):
        rows.append(
            {
                "decile": int(k),
                "n": len(g),
                "borrow_mean": float(g["borrow"].mean()),
                "dH_mean_pct": float(100 * g["dH"].mean()),
                "dH_min_pct": float(100 * g["dH"].min()),
            }
        )
    out["by_decile"] = rows
    hi = d[d["borrow"] > 0.05]
    if len(hi) > 1:
        c2 = date_clustered_ci(hi["dH"], hi["exit_date"], np.mean)
        out["borrow_above_5pct"] = {
            "n": c2.n,
            "mean_dH_pct": 100 * c2.point,
            "lo": 100 * c2.low,
            "hi": 100 * c2.high,
        }
    print(json.dumps(out, indent=2))
    (HERE / "c1_cost.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    d.to_parquet(HERE / "c1_cost.parquet")
    lib.log_view("2013-24", "hedged_hold", "implied_borrow_cost", "L3 c1_cost.py", "descriptive")


if __name__ == "__main__":
    main()
