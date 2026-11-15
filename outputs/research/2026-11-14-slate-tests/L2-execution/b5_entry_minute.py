"""
b5_entry_minute.py
L2 idea B5: sell the straddle at the first minute in 15:00 to 15:58 whose relative spread is below
the name's causal median (from strictly earlier events), else at 15:59:00. Declared in
diagnosis.log entry [14].

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b5_entry_minute.py --build
    python outputs/research/2026-11-14-slate-tests/L2-execution/b5_entry_minute.py --block 2023

``--build`` reads the 1,779 study's broad 2023-24 entry tick files (its loader imported) and writes
per-event minute grids to ``_cache/b5_minutes.parquet``; ``--block`` scores one entry year.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import l2lib as L  # noqa: E402
from earnings_iv_crush.research.protocol import log_block_view  # noqa: E402

MAKER = L.ROOT / "research" / "execution" / "2026-11-13-maker-entry-confirmation" / "study.py"
GRID = L.HERE / "_cache" / "b5_minutes.parquet"
FIRST_MIN, LAST_MIN, CLOSE_MIN = 15 * 60, 15 * 60 + 58, 15 * 60 + 59
MIN_PRIOR_EVENTS = 2  # declared: the benchmark needs two earlier events of the name
N_NULL, SEED = 2000, 0

_W: dict[str, Any] = {}


def _init() -> None:
    spec = importlib.util.spec_from_file_location("maker_confirmation_study", MAKER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["maker_confirmation_study"] = mod
    spec.loader.exec_module(mod)
    _W["st"] = mod


def _grid(e: dict) -> list[dict] | None:
    """Bid and ask sums of the straddle at each minute boundary 15:00 to 15:59."""
    st = _W["st"]
    path = st._path(pd.Series(e))
    if not path.exists():
        return None
    pre = st.f1._frame(path)
    if pre is None:
        return None
    day = pd.Timestamp(e["entry_date"]).normalize()
    if st.f1.is_early_close(day):
        return None
    rows = []
    legs = {r: pre[pre["right"] == r] for r in "CP"}
    for m in range(FIRST_MIN, CLOSE_MIN + 1):
        q = [st.f1._quote_at(legs[r], st._at(day, m)) for r in "CP"]
        if any(x is None for x in q):
            continue
        rows.append(
            {
                "ticker": e["ticker"],
                "entry_date": day,
                "m0": float(e["m0"]),
                "minute": m,
                "bid": q[0][0] + q[1][0],
                "ask": q[0][1] + q[1][1],
            }
        )
    return rows


def build(workers: int) -> None:
    _init()
    ev = _W["st"].load_events()
    jobs = [dict(r) for _, r in ev.iterrows()]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        res = list(ex.map(_grid, jobs, chunksize=10))
    n_none = sum(r is None for r in res)
    rows = [x for r in res if r for x in r]
    d = pd.DataFrame(rows)
    print(f"events {len(jobs)}; no tick file or early close {n_none}; grid rows {len(d)}")
    tmp = GRID.with_suffix(".tmp.parquet")
    d.to_parquet(tmp)
    tmp.replace(GRID)
    print(f"wrote {GRID}")


def choose(g: pd.DataFrame) -> pd.DataFrame:
    """One row per event: the rule's minute and its outcome, causal benchmarks per name."""
    g = g.copy()
    g["mid"] = (g["bid"] + g["ask"]) / 2
    g["s"] = (g["ask"] - g["bid"]) / g["mid"]
    out = []
    hist: dict[str, list[np.ndarray]] = {}
    for (day, tk), e in g.sort_values(["entry_date", "ticker"]).groupby(
        ["entry_date", "ticker"], sort=True
    ):
        close = e[e["minute"] == CLOSE_MIN]
        win = e[(e["minute"] >= FIRST_MIN) & (e["minute"] <= LAST_MIN)]
        prior = [x for x in hist.get(tk, []) if x.size]
        rec = {"ticker": tk, "entry_date": day, "m0": float(e["m0"].iloc[0])}
        if close.empty:
            rec["status"] = "no_1559_quote"
        elif len(prior) < MIN_PRIOR_EVENTS:
            rec["status"] = "burn_in"
        else:
            bench = float(np.median(np.concatenate(prior)))
            hit = win[win["s"] < bench]
            rec["status"] = "ok"
            rec["bench"] = bench
            c = close.iloc[0]
            if hit.empty:
                rec.update(minute=CLOSE_MIN, gain=0.0, drift=0.0, half=0.0)
            else:
                h = hit.iloc[0]
                rec.update(
                    minute=int(h["minute"]),
                    gain=(h["bid"] - c["bid"]) / rec["m0"],
                    drift=(h["mid"] - c["mid"]) / rec["m0"],
                    half=((c["mid"] - c["bid"]) - (h["mid"] - h["bid"])) / rec["m0"],
                )
            # timing null: the same event at every window minute, for random draws
            rec["alt_gains"] = ((win["bid"] - c["bid"]) / rec["m0"]).to_numpy()
        out.append(rec)
        # the benchmark is updated only after the event's own decision
        if not win.empty:
            hist.setdefault(tk, []).append(win["s"].to_numpy())
    return pd.DataFrame(out)


def score(year: int) -> None:
    g = pd.read_parquet(GRID)
    g["entry_date"] = pd.to_datetime(g["entry_date"])
    c = choose(g)
    print("funnel (all years):", c["status"].value_counts().to_dict())
    c = c[(c["entry_date"].dt.year == year)]
    ok = c[c["status"] == "ok"].reset_index(drop=True)
    early = ok["minute"] < CLOSE_MIN
    dates = ok["entry_date"]
    prim = L.mean_ci(ok["gain"], dates)
    rng = np.random.default_rng(SEED)
    alts = ok.loc[early, "alt_gains"].tolist()
    null = np.empty(N_NULL)
    for i in range(N_NULL):
        s = sum(float(a[rng.integers(0, a.size)]) for a in alts if a.size)
        null[i] = s / len(ok)
    res = {
        "year": year,
        "funnel_year": c["status"].value_counts().to_dict(),
        "n": len(ok),
        "share_early": float(early.mean()),
        "median_minute_early": float(ok.loc[early, "minute"].median()) if early.any() else None,
        "primary_paired_mean": L.iv_dict(prim),
        "drift_on_early": float(ok.loc[early, "drift"].mean() * 100) if early.any() else None,
        "half_spread_saved_on_early": float(ok.loc[early, "half"].mean() * 100)
        if early.any()
        else None,
        "gain_on_early": float(ok.loc[early, "gain"].mean() * 100) if early.any() else None,
        "null_median": float(np.median(null) * 100),
        "null_p95": float(np.percentile(null, 95) * 100),
        "null_percentile": float(100 * (null < prim.point).mean()),
        "always_1500": L.iv_dict(
            L.mean_ci(ok["alt_gains"].map(lambda a: float(a[0]) if a.size else np.nan), dates)
        ),
    }
    for k, v in res.items():
        print(k, v)
    L.write_json(L.HERE / f"b5_{year}.json", res)
    log_block_view(
        L.BLOCKS_VIEWED,
        panel="broad_entry_ticks",
        period=str(year),
        outcome_family="entry_execution",
        feature_family="entry_minute_spread_state",
        viewed_by="L2-execution b5_entry_minute.py",
        kind="trial",
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--block", type=int, choices=(2023, 2024))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    a = ap.parse_args(argv)
    if a.build:
        build(a.workers)
    if a.block:
        score(a.block)


if __name__ == "__main__":
    main()
