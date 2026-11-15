"""
build_surfaces.py
D0 step 5: build the 15:59 surface tensor for every base event with
``earnings_iv_crush.research.chain_surface``, in parallel over chain files, writing parts
incrementally and the final arrays to ``data/cache/dl/surfaces_2026-11-15.npz``.

Everything derived from Databento rows stays under ``data/cache/dl/`` (gitignored). This script
prints only counts and aggregates.

Output arrays (one row per event, in ``targets.parquet`` order):

- ``grid``: float32, shape (events, 9 channels, 2 expiries, 9 points), NaN where undefined;
- ``ticker``, ``entry_date`` (ISO strings): keys;
- ``scalars``: float64, shape (events, len(SCALARS)), names in ``scalar_names``;
- ``channels``, ``expiries``, ``grid_x``: axis labels.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D0-surface/build_surfaces.py [--workers 12]
    python outputs/research/2026-11-15-deep-learning/D0-surface/build_surfaces.py --limit 200
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.config import CHAIN_SURFACE  # noqa: E402
from earnings_iv_crush.research import chain_surface as cs  # noqa: E402
from earnings_iv_crush.research.hedged_hold import year_frac  # noqa: E402

BASE = ROOT / "outputs/research/2026-11-14-slate-tests/L1-corrections/base_corrected.parquet"
TARGETS = HERE / "targets.parquet"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
DFF = ROOT / "outputs/research/2026-11-13-alpha-hunt/lane1-macro/dl/fred_DFF.csv"
OUT_DIR = ROOT / "data" / "cache" / "dl"
PARTS = OUT_DIR / "surfaces_parts_2026-11-15"
OUT = OUT_DIR / "surfaces_2026-11-15.npz"
CHUNK = 250  # events per part file, so an interrupted build resumes from the last part
SCALARS = (
    "sigma_atm_front",
    "sigma_atm_next",
    "tau_front",
    "tau_next",
    "front_fwd",
    "m0",
    "next_fwd",
    "rate",
    "dff_pct",
    "atm_strike_front",
    "atm_half_spread_front",
    "atm_iv_front_panel_convention",
    "n_parity_next",
    "fill",
    "fill_front",
    "fill_next",
    "fill_no_gap_rule",
    "file_present",
    "front_found",
    "next_found",
    "next_expiry_days",
    "n_rows",
    "n_after_cutoff",
    "n_superseded",
    "n_unparsed",
)


def _dff_table() -> pd.Series:
    s = pd.read_csv(DFF, parse_dates=["observation_date"]).set_index("observation_date")["DFF"]
    s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
    if s.empty:
        raise ValueError("DFF series is empty")
    return s


def _one(job: tuple[str, str, str, float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    ticker, entry, expiry, fwd, m0, dff = job
    sc = dict.fromkeys(SCALARS, np.nan)
    grid = np.full((len(cs.CHANNELS), 2, CHAIN_SURFACE.grid_points), np.nan)
    grid[-1] = 0.0
    sc.update(dff_pct=dff, front_fwd=fwd, m0=m0, file_present=0.0, front_found=0.0, next_found=0.0)
    sc["fill"] = sc["fill_front"] = sc["fill_next"] = sc["fill_no_gap_rule"] = 0.0
    path = CHAINS / f"{ticker}_{entry}.parquet"
    if not path.exists():
        return grid, np.array([sc[k] for k in SCALARS])
    raw = pd.read_parquet(path, columns=list(cs.RAW_COLUMNS))
    s = cs.event_surface(raw, entry, expiry, fwd, dff, m0, CHAIN_SURFACE)
    nogap = cs.event_surface(
        raw, entry, expiry, fwd, dff, m0, replace(CHAIN_SURFACE, max_gap_x=np.inf)
    )
    sc.update({k: v for k, v in s.scalars.items() if k in sc})
    sc.update(
        file_present=1.0,
        front_found=float(s.status["front_found"]),
        next_found=float(s.status["next_found"]),
        fill_front=float(s.grid[-1, 0].mean()),
        fill_next=float(s.grid[-1, 1].mean()),
        fill_no_gap_rule=float(nogap.grid[-1].mean()),
        n_rows=float(s.status["n_rows"]),
        n_after_cutoff=float(s.status["n_after_cutoff"]),
        n_superseded=float(s.status["n_superseded"]),
        n_unparsed=float(s.status["n_unparsed"]),
    )
    ne = s.status["next_expiry"]
    if ne is not None:
        sc["next_expiry_days"] = float((pd.Timestamp(ne) - pd.Timestamp(entry)).days)
    st = s.expiries["front"].strikes
    k = s.scalars["atm_strike_front"]
    if not st.empty and np.isfinite(k):
        # The panel's convention (zero rate, whole calendar days), for an exact reconciliation.
        at = st[np.isclose(st["strike"], k)]
        mid = float(((at["bid"] + at["ask"]) / 2).sum()) if len(at) == 2 else np.nan
        sc["atm_iv_front_panel_convention"] = float(
            cs.straddle_implied_vol(mid, fwd, k, year_frac(entry, expiry), 1.0, CHAIN_SURFACE)
        )
    return s.grid, np.array([sc[k2] for k2 in SCALARS])


def _chunk(jobs: list[Any]) -> tuple[np.ndarray, np.ndarray]:
    out = [_one(j) for j in jobs]
    return np.stack([g for g, _ in out]).astype(np.float32), np.stack([v for _, v in out])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    t0 = time.time()
    t = pd.read_parquet(TARGETS, columns=["ticker", "entry_date", "expiry", "m0"])
    b = pd.read_parquet(BASE, columns=["ticker", "entry_date", "front_fwd", "m0"])
    for f in (t, b):
        f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    d = t.merge(
        b, on=["ticker", "entry_date"], how="left", validate="one_to_one", suffixes=("", "_b")
    )
    if d["front_fwd"].isna().any() or not np.allclose(d["m0"], d["m0_b"]):
        raise ValueError("base join lost front_fwd or m0 disagrees")
    dff = _dff_table()
    pos = dff.index.searchsorted(d["entry_date"], side="right") - 1
    if (pos < 0).any():
        raise ValueError("an entry date precedes the DFF series")
    d["dff_pct"] = dff.to_numpy()[pos]
    lag = (d["entry_date"] - dff.index[pos]).dt.days
    print(f"[dff] last observation on or before entry: lag days max {int(lag.max())}")
    if args.limit:
        d = d.iloc[: args.limit]
    jobs = [
        (r.ticker, str(r.entry_date.date()), str(pd.Timestamp(r.expiry).date()), float(r.front_fwd),
         float(r.m0), float(r.dff_pct))
        for r in d.itertuples()
    ]  # fmt: skip
    PARTS.mkdir(parents=True, exist_ok=True)
    tag = f"n{len(jobs)}"
    chunks = [jobs[i : i + CHUNK] for i in range(0, len(jobs), CHUNK)]
    todo = [i for i in range(len(chunks)) if not (PARTS / f"{tag}_part{i:03d}.npz").exists()]
    print(f"[build] {len(jobs)} events in {len(chunks)} parts; {len(todo)} to build; "
          f"{args.workers} workers", flush=True)  # fmt: skip
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {i: pool.submit(_chunk, chunks[i]) for i in todo}
        for n, (i, fu) in enumerate(futs.items(), 1):
            g, v = fu.result()
            tmp = PARTS / f"{tag}_part{i:03d}.tmp.npz"
            np.savez(tmp, grid=g, scalars=v)
            tmp.replace(PARTS / f"{tag}_part{i:03d}.npz")
            print(f"  part {i:03d} done ({n}/{len(todo)}), {time.time() - t0:.0f}s", flush=True)
    gs, vs = [], []
    for i in range(len(chunks)):
        z = np.load(PARTS / f"{tag}_part{i:03d}.npz")
        gs.append(z["grid"])
        vs.append(z["scalars"])
    grid, scal = np.concatenate(gs), np.concatenate(vs)
    if grid.shape[0] != len(jobs):
        raise AssertionError("assembled rows differ from the event count")
    out = OUT if not args.limit else OUT_DIR / f"surfaces_2026-11-15_limit{args.limit}.npz"
    tmp = out.with_suffix(".tmp.npz")
    np.savez_compressed(
        tmp,
        grid=grid,
        scalars=scal,
        scalar_names=np.array(SCALARS),
        channels=np.array(cs.CHANNELS),
        expiries=np.array(cs.EXPIRIES),
        grid_x=cs.grid_points(CHAIN_SURFACE),
        ticker=d["ticker"].to_numpy(str),
        entry_date=d["entry_date"].dt.strftime("%Y-%m-%d").to_numpy(str),
    )
    tmp.replace(out)
    print(f"[build] wrote {out.relative_to(ROOT)} {grid.shape} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
