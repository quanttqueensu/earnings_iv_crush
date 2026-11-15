"""c1_divwindow.py: flag events whose whole parity window (entry, T2] has no projected ex-date.

American calls carry early-exercise value ahead of an ex-date, which lifts the parity forward of
any expiry that spans one and contaminates the implied borrow; only windows with no projected
ex-date give a clean read. Adds ``div_free`` (causal) and ``div_free_realised_diag`` to
``c1_borrow.parquet``. No outcome is read.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c1_divwindow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import c1_borrow_build as cb  # noqa: E402

BUFFER_DAYS = 3  # ex-dates within a few days after T2 still sit inside quote-staleness noise


def main() -> None:
    hist = cb._div_history()
    d = pd.read_parquet(cb.OUT)
    b = pd.read_parquet(cb.BASE, columns=["ticker", "entry_date", "expiry"])
    d = d.merge(b, on=["ticker", "entry_date"], validate="one_to_one")
    free, free_r = [], []
    for t, e, x, f1, dt in zip(
        d["ticker"], d["entry_date"], d["expiry"], d["F1"], d["dt_years"], strict=True
    ):
        if not np.isfinite(f1):
            free.append(np.nan)
            free_r.append(np.nan)
            continue
        t2 = pd.Timestamp(x) + pd.Timedelta(days=round(dt * 365) + BUFFER_DAYS)
        h = hist.get(t, [])
        pj, _ = cb.projected_divs(h, pd.Timestamp(e), pd.Timestamp(e) - pd.Timedelta(days=1), t2)
        free.append(float(pj == 0))
        free_r.append(float(cb.realised_divs(h, pd.Timestamp(e), t2) == 0))
    d["div_free"], d["div_free_realised_diag"] = free, free_r
    ok = d["b_status"] == "ok"
    print(pd.crosstab(d.loc[ok, "div_free"], d.loc[ok, "div_free_realised_diag"]))
    print(
        d.loc[ok]
        .groupby("div_free")["borrow"]
        .describe(percentiles=[0.1, 0.5, 0.9, 0.99])
        .round(4)
        .to_string()
    )
    d = d.drop(columns=["expiry"])
    tmp = cb.OUT.with_suffix(".tmp")
    d.to_parquet(tmp)
    tmp.replace(cb.OUT)


if __name__ == "__main__":
    main()
