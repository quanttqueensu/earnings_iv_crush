"""
research_ml_nested.py
Nested walk-forward: the model choice itself is made out of sample, so the final result carries no
selection by the researcher.

For each test year Y, the candidate configurations (the zoo grid, optionally thinned) are scored by
an inner walk-forward over the years before Y: each candidate is refit on years < Y' and evaluated
on year Y' for every inner year Y' in the last ``INNER_YEARS`` years before Y. The candidate with the
best mean inner selected-minus-rejected gap (net RoM per trade, at its own threshold) is then refit
on all years < Y and applied to year Y. Year Y's outcomes are never seen by the choice.

The pooled out-of-sample result is a single strategy, so it is read without deflation for the grid.

Usage:
    python research/selection/research_ml_nested.py --events outputs/research/ml_zoo/events_full.parquet
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OUT = Path("outputs/research/ml_zoo")
INNER_YEARS = 3
FIRST_TEST_YEAR = 2016
N_BOOT = 5000
SEED = 0


def _gap(rom: np.ndarray, sel: np.ndarray) -> float:
    if sel.sum() == 0 or (~sel).sum() == 0:
        return float("nan")
    return float(rom[sel].mean() - rom[~sel].mean())


def _fit_select(c: dict[str, Any], tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    import research.selection.research_ml_zoo as zoo

    model = zoo.make_model(c)
    model.fit(tr[zoo.FEATURES], zoo._target(tr, c["target"]))
    s_tr = zoo._score(model, c, tr[zoo.FEATURES])
    s_te = zoo._score(model, c, te[zoo.FEATURES])
    return s_te >= float(np.quantile(s_tr, 1 - c["q"]))


def _inner(args: tuple[int, dict[str, Any], int]) -> tuple[int, int, float]:
    """Mean inner gap of candidate ``cid`` for outer test year ``y``."""
    warnings.filterwarnings("ignore")
    cid, c, y = args
    d = pd.read_parquet(os.environ["ZOO_EVENTS"]).dropna(subset=["y", "rom"])
    yr = d["entry_date"].dt.year
    gaps = []
    for yi in range(y - INNER_YEARS, y):
        tr, te = d[yr < yi], d[yr == yi]
        if len(tr) < 200 or te.empty:
            continue
        sel = _fit_select(c, tr, te)
        gaps.append(_gap(te["rom"].to_numpy(), sel))
    return cid, y, float(np.nanmean(gaps)) if gaps else float("nan")


def candidates() -> list[dict[str, Any]]:
    import research.selection.research_ml_zoo as zoo

    out = []
    for c in zoo.configs():
        for q in (0.3, 0.5, 0.7):
            out.append({**c, "q": q})
    return out


def run(events: Path, workers: int) -> None:
    from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci

    os.environ["ZOO_EVENTS"] = str(events)
    d = pd.read_parquet(events).dropna(subset=["y", "rom"])
    yr = d["entry_date"].dt.year
    years = [y for y in range(FIRST_TEST_YEAR, int(yr.max()) + 1) if (yr == y).any()]
    cands = candidates()
    print(
        f"  {len(cands)} candidates, {len(years)} outer years, {INNER_YEARS} inner years",
        flush=True,
    )
    jobs = [(i, c, y) for y in years for i, c in enumerate(cands)]
    inner: dict[tuple[int, int], float] = {}
    with ProcessPoolExecutor(workers) as ex:
        for k, (cid, y, g) in enumerate(ex.map(_inner, jobs, chunksize=8), start=1):
            inner[(cid, y)] = g
            if k % 500 == 0:
                print(f"    inner {k}/{len(jobs)}", flush=True)
    rows, picks = [], {}
    for y in years:
        scores = {cid: inner[(cid, y)] for cid in range(len(cands))}
        best = max((c for c in scores if scores[c] == scores[c]), key=lambda c: scores[c])
        c = cands[best]
        picks[y] = {"cid": best, "inner_gap": scores[best], **{k: str(v) for k, v in c.items()}}
        tr, te = d[yr < y], d[yr == y].copy()
        te["sel"] = _fit_select(c, tr, te)
        te["pick"] = best
        rows.append(te)
        print(
            f"  {y}: picked {c['model']} {c['target']} q={c['q']} (inner gap {scores[best]:+.4f}); "
            f"out-of-sample gap {_gap(te['rom'].to_numpy(), te['sel'].to_numpy()):+.4f}",
            flush=True,
        )
    o = pd.concat(rows, ignore_index=True)
    rom, sel = o["rom"].to_numpy(), o["sel"].to_numpy()
    keys = pd.to_datetime(o["announce_date"]).dt.strftime("%Y-%m-%d").to_numpy()
    lo, hi = cluster_bootstrap_ci(
        np.arange(len(o), dtype=float),
        keys,
        lambda ix: _gap(rom[ix.astype(int)], sel[ix.astype(int)]),
        n_boot=N_BOOT,
        seed=SEED,
    )
    x = pd.Series(rom[sel])
    res = {
        "n": len(o),
        "n_selected": int(sel.sum()),
        "gap": _gap(rom, sel),
        "gap_ci": [float(lo), float(hi)],
        "selected_mean_rom": float(x.mean()),
        "selected_sharpe_per_trade": float(x.mean() / x.std(ddof=1)),
        "all_mean_rom": float(rom.mean()),
        "by_year_gap": o.groupby(o["entry_date"].dt.year)
        .apply(lambda g: _gap(g["rom"].to_numpy(), g["sel"].to_numpy()))
        .round(4)
        .to_dict(),
        "picks": picks,
    }
    print(json.dumps(res, indent=1, default=str))
    tag = events.stem
    json.dump(res, open(OUT / f"nested_{tag}.json", "w"), indent=1, default=str)
    o.to_parquet(OUT / f"nested_{tag}_oos.parquet", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    run(a.events, a.workers)


if __name__ == "__main__":
    main()
