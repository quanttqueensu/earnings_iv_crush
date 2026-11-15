"""posthoc_nan_check.py: why the frozen held-out read returned NaN intervals for g (exploratory).

Re-runs the frozen pairing on held-out and counts bootstrap resamples whose mean Tuesday
consumed variance is not positive (sqrt undefined). Diagnostic only; no statistic here is a
held-out result.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N04-crude-eia-opec/posthoc_nan_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eia_event_variance as m  # noqa: E402

for series in ("c1", "spot"):
    df = m.load_daily(series)
    lo, hi = m.BLOCKS["heldout"]
    df = df[(df.index >= lo) & (df.index <= hi)]
    pairs = m.build_pairs(df, "tue", "wed")
    vc = pairs["dV_c"].to_numpy()
    ve = pairs["dV_e"].to_numpy()
    rng = np.random.default_rng(20261113)
    n = len(vc)
    means = np.array([vc[rng.integers(0, n, n)].mean() for _ in range(10_000)])
    print(
        f"{series}: N={n}, mean dV_Tue {vc.mean():.2e}, mean dV_Wed {ve.mean():.2e}, "
        f"share of resamples with mean dV_Tue <= 0: {np.mean(means <= 0):.4f}, "
        f"sd of dV per day {vc.std():.2e} vs mean OVX-implied day {(df['ovx']**2).mean()/1e4/365:.2e}"
    )

# Exploratory: the frozen intervals with the undefined resamples dropped (nanquantile).
for series in ("c1", "spot"):
    df = m.load_daily(series)
    lo, hi = m.BLOCKS["heldout"]
    df = df[(df.index >= lo) & (df.index <= hi)]
    p = m.build_pairs(df, "tue", "wed")
    ae, ac = np.sqrt(p["r2_e"].to_numpy()), np.sqrt(p["r2_c"].to_numpy())
    ve, vc = p["dV_e"].to_numpy(), p["dV_c"].to_numpy()
    rng = np.random.default_rng(20261113)
    n = len(p)
    gs, rcs, dfs = [], [], []
    for _ in range(10_000):
        i = rng.integers(0, n, n)
        mv, mc = ve[i].mean(), vc[i].mean()
        b = ae[i].mean() / ac[i].mean()
        ii = np.sqrt(max(mv, 0.0) / mc) if mc > 0 else np.nan
        gs.append(ii - b)
        rb = ae[i].mean() / (np.sqrt(2 / np.pi) * np.sqrt(max(mv, 1e-12))) - 1
        rc = ac[i].mean() / (np.sqrt(2 / np.pi) * np.sqrt(mc)) - 1 if mc > 0 else np.nan
        rcs.append(rc)
        dfs.append(rb - rc)
    q = lambda x: [
        round(float(v), 4) for v in np.nanquantile(np.array(x), [0.025, 0.975])
    ]  # noqa: E731
    print(f"{series} exploratory nan-dropped 95%: g {q(gs)}, R_ctl {q(rcs)}, R_buy-R_ctl {q(dfs)}")
