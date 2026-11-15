"""
round3.py
Round 3 on the discovery block, M3 richness. (a) Right driver: is the richness effect the
term-structure jump share under another name? Score within implied-move x tenor x jump-share
tercile cells. (b) Level drift: the causal tercile cut lets a model-level lag (2024) push most of
a year into the top bin; score the richness ratio net of its trailing 63-session cross-sectional
median instead.

Usage
-----
    python round3.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib
from selector import score

TRAIL_DAYS = 91  # calendar days of earlier events behind the cross-sectional median (~63 sessions)


def trailing_median(v: pd.Series, dates: pd.Series, days: int = TRAIL_DAYS, min_n: int = 30) -> np.ndarray:
    """Median of v over events dated strictly before each event and within ``days``."""
    d = pd.to_datetime(dates).dt.normalize().to_numpy()
    order = np.argsort(d, kind="stable")
    ds, vs = d[order], v.to_numpy(float)[order]
    out = np.full(len(v), np.nan)
    for i in range(len(ds)):
        lo = np.searchsorted(ds, ds[i] - np.timedelta64(days, "D"), side="left")
        hi = np.searchsorted(ds, ds[i], side="left")
        w = vs[lo:hi]
        w = w[np.isfinite(w)]
        if w.size >= min_n:
            out[order[i]] = np.median(w)
    return out


def main() -> None:
    e = pd.read_parquet(lib.HERE / "rich_m3.parquet")
    tv = e["jsplit_jump_var"] + e["jsplit_sd2"] * e["front_t"]
    e["jump_share"] = np.where(e["jsplit_valid"].astype(bool), e["jsplit_jump_var"] / tv, np.nan)
    e["js_bin"] = lib.causal_bins(e["jump_share"].to_numpy(float), e["announce_date"], 3)
    e3 = e[e["js_bin"] >= 0].copy()
    print(f"jump-share tercile assigned {len(e3)} of {len(e)}")
    e3["cell"] = e3["cell"] * 10 + e3["js_bin"]
    mech = ("richness carries residual value beyond the term-structure jump share: holding the share"
            " fixed, a premium above the model-fair jump still pays")
    for sg, oc, t in [("R_ratio", "yb", 1883), ("R_ratio", "y", 1884)]:
        score(e3, sg, oc, "discovery", t, mech=mech,
              hyp=f"m3 top-tercile {sg} -> {oc}, cells implied move x tenor x jump share")

    e["R_dm"] = e["R_ratio"] - trailing_median(e["R_ratio"], e["announce_date"])
    mech2 = ("richness relative to the trailing cross-section removes the model's slow level error,"
             " so the top tercile is the most over-priced events of their own period"
             " (discovery-derived fix of the 2024 concentration)")
    for oc, t in [("yb", 1885), ("y", 1886)]:
        score(e, "R_dm", oc, "discovery", t, mech=mech2,
              hyp=f"m3 top-tercile R_ratio minus trailing 91-day median -> {oc}")
    e.to_parquet(lib.HERE / "rich_m3_r3.parquet", index=False)


if __name__ == "__main__":
    main()

