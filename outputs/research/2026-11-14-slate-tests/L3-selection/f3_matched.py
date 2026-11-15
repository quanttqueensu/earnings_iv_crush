"""f3_matched.py: F3 risk figures against exposure-matched baselines, and the component split.

The capped book trades fewer events, so its raw session sd and worst session are not comparable
with the uncapped book's. Two baselines at the capped book's trade count, by block and cap:

- scaled: every uncapped event held at weight n_cap / n_uncap (session P&L scales linearly);
- thinned: events kept uniformly at random across the whole block with probability
  n_cap / n_uncap, ignoring sessions (200 seeded draws, medians).

The cap lowers risk through its allocation only if it beats both. Also writes the expected
capped-minus-uncapped shift of each P&L component at each cap (the f3_weighted.py weights),
exploratory. Reads base_corrected H_corr and its components; reads f3_risk.json for the capped
medians.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/f3_matched.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

CAPS = (10, 5, 3)
N_DRAWS = 200  # as f3_risk.py
SEED = 0
COMPONENTS = ("c_premium", "c_settlement", "c_hedge", "c_equity_cost", "c_fees", "c_financing")


def _session(h: np.ndarray, sess: np.ndarray) -> pd.Series:
    return pd.Series(h).groupby(sess).sum()


def main() -> None:
    risk = json.loads((HERE / "f3_risk.json").read_text(encoding="utf-8"))
    b = lib.load_base()
    b["block"] = lib.block_of(b["year"])
    b = b[b["H_corr"].notna()].sort_values("entry_date").reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    out: dict = {}
    for name, _, _ in lib.CFG.blocks:
        g = b[b["block"] == name].reset_index(drop=True)
        sess = g["entry_date"].dt.normalize().to_numpy()
        h = 100 * g["H_corr"].to_numpy(float)
        s_un = _session(h, sess)
        n = g.groupby("entry_date")["ticker"].transform("size").to_numpy(float)
        res: dict = {}
        for cap in CAPS:
            rc = risk[name][f"cap{cap}"]
            n_cap = rc["trades"]["median"]
            p = n_cap / len(g)
            thin_sd, thin_worst = [], []
            for _ in range(N_DRAWS):
                keep = rng.random(len(g)) < p
                s = _session(h[keep], sess[keep])
                thin_sd.append(float(s.std(ddof=1)))
                thin_worst.append(float(s.min()))
            w = np.minimum(1.0, cap / n)
            comp = {
                c: float(
                    100 * ((w * g[c].to_numpy(float)).sum() / w.sum() - g[c].to_numpy(float).mean())
                )
                for c in COMPONENTS
            }
            res[f"cap{cap}"] = {
                "trades_capped": n_cap,
                "exposure_ratio": p,
                "session_sd": {
                    "capped": rc["session_sd"]["median"],
                    "scaled_uncapped": float(p * s_un.std(ddof=1)),
                    "thinned_uncapped": float(np.median(thin_sd)),
                },
                "worst_session": {
                    "capped": rc["worst_session"]["median"],
                    "scaled_uncapped": float(p * s_un.min()),
                    "thinned_uncapped": float(np.median(thin_worst)),
                },
                "component_shift_pct_m0_exploratory": comp,
            }
            r = res[f"cap{cap}"]
            print(
                f"{name} cap{cap}: trades {n_cap:.0f} (ratio {p:.3f}); session sd capped "
                f"{r['session_sd']['capped']:.1f} scaled {r['session_sd']['scaled_uncapped']:.1f} "
                f"thinned {r['session_sd']['thinned_uncapped']:.1f}; worst capped "
                f"{r['worst_session']['capped']:+.1f} scaled "
                f"{r['worst_session']['scaled_uncapped']:+.1f} thinned "
                f"{r['worst_session']['thinned_uncapped']:+.1f}"
            )
            print("   component shift (exploratory):", {k: round(v, 3) for k, v in comp.items()})
        out[name] = res
    (HERE / "f3_matched.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for name, _, _ in lib.CFG.blocks:
        lib.log_view(
            name, "hedged_hold", "session_concentration_cap", "L3 f3_matched.py", "descriptive"
        )


if __name__ == "__main__":
    main()
