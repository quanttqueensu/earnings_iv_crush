"""
heldout.py
The single held-out read frozen in ``freeze_2026-11-13_m4_demeaned_richness.md`` (trials 1,897 to
1,900), plus the M4 calibration on the held-out blocks for context (not a trial; realised moves
only). Refuses to run without the freeze note.

Usage
-----
    python heldout.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib
from fit_calib import clustered, ratio
from selector import score

FREEZE = lib.HERE / "freeze_2026-11-13_m4_demeaned_richness.md"


def main() -> None:
    if not FREEZE.exists():
        raise PermissionError("no freeze note: held-out read refused")
    e = pd.read_parquet(lib.HERE / "rich_m4.parquet")
    lab = "exploratory (frozen, discovery-derived, no clean block)"
    mech = "frozen M4 demeaned richness; see freeze note"
    r = score(e, "R_dm", "yb", "heldout", 1897, label=lab, mech=mech,
              hyp="FROZEN m4 top-tercile demeaned R_ratio -> yb (primary)")
    r2 = score(e, "R_dm", "yb", "heldout2", 1898, label=lab, mech=mech,
               hyp="FROZEN m4 top-tercile demeaned R_ratio -> yb, second held-out")
    r3 = score(e, "R_dm", "y", "heldout", 1899, label=lab, mech=mech,
               hyp="FROZEN m4 top-tercile demeaned R_ratio -> y (secondary)")
    tv = e["jsplit_jump_var"] + e["jsplit_sd2"] * e["front_t"]
    e["jump_share"] = np.where(e["jsplit_valid"].astype(bool), e["jsplit_jump_var"] / tv, np.nan)
    e["js_bin"] = lib.causal_bins(e["jump_share"].to_numpy(float), e["announce_date"], 3)
    e["hs_bin"] = lib.causal_bins(e["half_spread"].to_numpy(float), e["announce_date"], 3)
    e2 = e[(e["js_bin"] >= 0) & (e["hs_bin"] >= 0)].copy()
    e2["cell"] = (e2["cell"] * 10 + e2["js_bin"]) * 10 + e2["hs_bin"]
    score(e2, "R_dm", "yb", "heldout", 1900, label=lab, mech=mech,
          hyp="FROZEN primary inside implied move x tenor x jump share x half-spread cells (driver)")
    for k, v in (("primary 2013-18", r), ("2025-26", r2), ("hedged 2013-18", r3)):
        print(f"{k}: delta {v['delta']:+.4f} [{v['lo']:+.4f}, {v['hi']:+.4f}] t {v['t']:+.2f} null"
              f" {v['null_pct']:.1f}; pass {v['lo'] > 0 and v['null_pct'] >= 95}")

    ev = pd.read_parquet(lib.HERE / "events_model4.parquet")
    for blk in ("heldout", "heldout2"):
        lo, hi = lib.BLOCKS[blk]
        d = ev[ev["year"].between(lo, hi)]
        d = d[np.isfinite(d["r"]) & np.isfinite(d["pred_var4"]) & np.isfinite(d["mkt_var"])]
        keys = d["announce_date"].dt.normalize().to_numpy()
        p, l_, u_, _ = clustered(ratio, keys, (d["r"] ** 2).to_numpy(), d["pred_var4"].to_numpy())
        pm, lm, um, _ = clustered(ratio, keys, (d["r"] ** 2).to_numpy(), d["mkt_var"].to_numpy())
        print(f"M4 calibration {lo}-{hi} (descriptive): realised/model variance {p:.3f}"
              f" [{l_:.3f}, {u_:.3f}], realised/market {pm:.3f} [{lm:.3f}, {um:.3f}], N {len(d)}")


if __name__ == "__main__":
    main()
