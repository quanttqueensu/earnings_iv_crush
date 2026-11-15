"""
describe_sparse.py
D0 descriptive: what distinguishes sparse surfaces (grid fill below 0.5) at 15:59, on quantities
known at entry only (no outcome). Medians over all 9,350 events; writes describe_sparse.log.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D0-surface/describe_sparse.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NPZ = ROOT / "data" / "cache" / "dl" / "surfaces_2026-11-15.npz"
SPARSE = 0.5  # ChainSurfaceConfig.sparse_fill


def main() -> None:
    z = np.load(NPZ)
    s = pd.DataFrame(z["scalars"], columns=[str(c) for c in z["scalar_names"]])
    t = pd.read_parquet(HERE / "targets.parquet", columns=["block", "U_pct"])
    sp = (s["fill"] < SPARSE).to_numpy()
    rows = {
        "ATM straddle half-spread (fraction of mid)": s["atm_half_spread_front"],
        "front days to expiry (ACT/365 x 365)": s["tau_front"] * 365,
        "front ATM sd, sigma_atm sqrt(tau)": s["sigma_atm_front"] * np.sqrt(s["tau_front"]),
        "premium unit U (% of m0)": t["U_pct"],
    }
    lines = [f"sparse N={int(sp.sum())}, rest N={int((~sp).sum())}; medians sparse vs rest"]
    for k, v in rows.items():
        v = v.to_numpy(float)
        lines.append(f"  {k}: {np.nanmedian(v[sp]):.4f} vs {np.nanmedian(v[~sp]):.4f}")
    rho = s["fill"].corr(s["atm_half_spread_front"], method="spearman")
    lines.append(f"  Spearman(fill, ATM half-spread) {rho:+.3f}, N={len(s)}")
    for b in ("2013-18", "2019-24", "2025-26"):
        m = (t["block"] == b).to_numpy()
        lines.append(f"  sparse share {b}: {sp[m].mean():.3f} of {int(m.sum())}")
    text = "\n".join(lines)
    print(text)
    (HERE / "describe_sparse.log").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
