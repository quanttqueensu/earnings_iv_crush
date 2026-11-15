"""
screen.py
Descriptive within-cell screen of every pre-entry feature on the discovery block: quintile
spread of P&L per premium, of the realised-to-implied ratio and of the tail rate, by sub-period.
Not a trial: it is the multiplicity the report discloses (one row per feature screened).

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt/lane2-forensics/screen.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from forensics import OUTCOME_COLS
from lib import load

HERE = Path(__file__).resolve().parent


def main() -> None:
    d = load("discovery")
    d = d[d["im_bin"] >= 0].copy()
    d["tail"] = (d["ratio"] > 2).astype(float)
    d["loser"] = (d["pnl_prem"] <= d["pnl_prem"].quantile(0.05)).astype(float)
    skip = OUTCOME_COLS | {"permno", "year", "cell", "im_bin", "strike", "m0", "s0", "mid0", "F0",
                           "tail", "loser", "fye_known", "e_def", "jsplit_valid"}  # fmt: skip
    feats = [c for c in d.columns if c not in skip and pd.api.types.is_numeric_dtype(d[c])]
    rows = []
    for c in feats:
        s = d[d[c].notna()]
        if len(s) < 800 or s[c].nunique() < 2:
            continue
        r = s.groupby("cell")[c].rank(pct=True)
        binary = s[c].nunique() == 2
        hi = (s[c] == s[c].max()) if binary else (r >= 0.8)
        lo = (s[c] == s[c].min()) if binary else (r <= 0.2)
        row = {"feature": c, "n": len(s), "n_hi": int(hi.sum()), "binary": binary}
        for nm, m in (("all", np.ones(len(s), bool)), ("p1", (s["year"] <= 2017).to_numpy()),
                      ("p2", (s["year"] >= 2018).to_numpy())):  # fmt: skip
            # cell-demeaned outcomes so the tenor and size mix of the two ends does not drive it
            for o in ("pnl_prem", "ratio", "tail", "loser"):
                dm = s[o] - s.groupby("cell")[o].transform("mean")
                row[f"{o}_{nm}"] = dm[hi & m].mean() - dm[lo & m].mean()
        rows.append(row)
    t = pd.DataFrame(rows)
    t["consistent"] = np.sign(t["pnl_prem_p1"]) == np.sign(t["pnl_prem_p2"])
    t = t.sort_values("pnl_prem_all", key=np.abs, ascending=False)
    t.to_csv(HERE / "feature_screen.csv", index=False, float_format="%.5g")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    cols = ["feature", "n", "n_hi", "pnl_prem_all", "pnl_prem_p1", "pnl_prem_p2", "ratio_all",
            "tail_all", "tail_p1", "tail_p2", "loser_all", "consistent"]  # fmt: skip
    print(f"features screened: {len(t)}")
    print(t[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
