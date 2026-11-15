"""
diag_r5.py
Descriptive read after the held-out failure of the frozen model (no new configuration, no new
trial): the pooled walk-forward 2016-24 read of 1908 + 1921 (every prediction is out of sample),
the held-out quintile and tenor profile, the events that moved the held-out mean, and the
2025-26 threshold funnel.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/diag_r5.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

O = HERE / "oos"
disc = pd.read_parquet(O / "1908_gbm_mid_noncost_discovery.parquet")
held = pd.read_parquet(O / "1921_gbm_mid_noncost_heldout.parquet")
view = pd.read_parquet(O / "1922_gbm_mid_noncost_viewed.parquet")
pool = pd.concat([disc, held], ignore_index=True)
pool["pr"] = pool.groupby("q")["pred"].rank(pct=True)
d = pool["announce_date"].to_numpy()
pr, ym, yx = (pool[c].to_numpy(float) for c in ("pr", "ym_ex", "y_ex"))


def _ic(idx: np.ndarray, y: np.ndarray) -> float:
    i = idx.astype(int)
    return float(spearmanr(pr[i], y[i]).statistic)


for name, y in (("touch", yx), ("mid", ym)):
    ic = date_clustered_ci(np.arange(len(pool), dtype=float), d, lambda i, y=y: _ic(i, y))
    print(f"pooled 2016-24 OOS rank IC vs excess at {name}: {ic.point:+.4f} "
          f"[{ic.low:+.4f}, {ic.high:+.4f}], N {ic.n}, {ic.clusters} dates")
s = pool["sel"].to_numpy(bool)
for name, y in (("touch", yx), ("mid", ym)):
    e = date_clustered_ci(y[s], d[s], np.mean)
    print(f"pooled 2016-24 top-quintile excess at {name}: {e.point:+.4f} [{e.low:+.4f}, "
          f"{e.high:+.4f}], N {e.n}")
h = date_clustered_ci(pool.loc[s, "H"].to_numpy(float), d[s], np.mean)
print(f"pooled picks level H on m0, net touch: {h.point:+.4f} [{h.low:+.4f}, {h.high:+.4f}]; "
      f"all events {pool['H'].mean():+.4f}")
qic = pool.groupby("q").apply(lambda g: spearmanr(g["pred"], g["ym_ex"]).statistic,
                              include_groups=False)
print(f"quarterly IC at mid: positive in {(qic > 0).sum()} of {len(qic)} quarters; mean "
      f"{qic.mean():+.4f}, sd {qic.std():.4f}, t of the mean {qic.mean() / qic.std() * np.sqrt(len(qic)):+.2f}")
print("IC at mid by year: " + ", ".join(f"{y}:{v:+.3f}" for y, v in
                                         qic.groupby(qic.index.year).mean().items()))

held["tenor"] = held["qcell"].str[-1]
print("\nheld-out picks by tenor code (0: 0-1d ... 3: 10d+), n / excess at mid: " + ", ".join(
    f"{t}:{len(g)}/{g['ym_ex'].mean():+.3f}" for t, g in held[held["sel"]].groupby("tenor")))
hs = held[held["sel"]].sort_values("ym_ex")
print("held-out worst picks: " + "; ".join(
    f"{a} {b.date()} {c:+.2f}" for a, b, c in
    zip(hs["ticker"][:5], hs["entry_date"][:5], hs["ym_ex"][:5], strict=True)))
w = np.clip(hs["ym_ex"], *np.quantile(held["ym_ex"], [0.01, 0.99]))
print(f"held-out excess at mid with the outcome winsorised at 1/99%: {w.mean():+.4f}; "
      f"median pick {hs['ym_ex'].median():+.4f} vs unselected "
      f"{held.loc[~held['sel'], 'ym_ex'].median():+.4f}")

print("\n2025-26 funnel: selected share by quarter (causal threshold from training predictions):")
print(view.groupby("q")["sel"].agg(["size", "mean"]).round(3).T.to_string())
view["pr"] = view.groupby("q")["pred"].rank(pct=True)
top = view["pr"] > 0.8
e = date_clustered_ci(view.loc[top, "ym_ex"].to_numpy(float), view.loc[top, "announce_date"],
                      np.mean)
print(f"2025-26 within-quarter top quintile instead (descriptive): excess at mid {e.point:+.4f} "
      f"[{e.low:+.4f}, {e.high:+.4f}], N {e.n}")
