"""
compare_d1.py
Lane D2, descriptive: D1's frozen primary against D2's frozen primary on identical 2019-24
events, from the two lanes' held-out outputs already on disk (D1 heldout/cards_primary_2019-24
.parquet, D2 heldout_2019-24_events.parquet). Fits nothing; reads no other lane's code. The
comparison was planned in LANES.md ("report both against L4 and against each other"), but its
statistic was not frozen in advance, so it is labelled descriptive.

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/compare_d1.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import d2lib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

D1 = HERE.parent / "D1-surface-net" / "heldout" / "cards_primary_2019-24.parquet"


def _ci(v: np.ndarray, k: np.ndarray) -> list[float]:
    c = d2lib.date_clustered_ci(v, k, np.mean)
    return [round(c.point, 4), round(c.low, 4), round(c.high, 4), c.n]


def main() -> None:
    d2lib.log_view("2019-24", "compare_d1 (descriptive, D1 vs D2 frozen outputs)", "descriptive")
    a = pd.read_parquet(HERE / "heldout_2019-24_events.parquet")
    b = pd.read_parquet(D1)
    for f in (a, b):
        f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    m = a[a["scored"]].merge(
        b[["ticker", "entry_date", "log_score", "decide", "mean", "m_log_score"]].rename(
            columns={"log_score": "d1_log_score", "decide": "d1_decide", "mean": "d1_mean"}
        ),
        on=["ticker", "entry_date"], how="inner", validate="1:1",
    )  # fmt: skip
    ok = np.isfinite(m["d1_log_score"]) & np.isfinite(m["d2_log_score"])
    print(f"[compare] D2 scored {int(a['scored'].sum())}; joined {len(m)}; both finite {ok.sum()}")
    m = m[ok]
    if not np.allclose(m["m_log_score"], m["l4_model_log_score"]):
        raise ValueError("the two lanes' L4 champion scores disagree on identical events")
    k = m["announce_date"].to_numpy()
    out: dict[str, Any] = {"label": "descriptive, 2019-24, real", "N": len(m)}
    out["d1_minus_l4"] = _ci((m["d1_log_score"] - m["l4_model_log_score"]).to_numpy(), k)
    out["d2_minus_l4"] = _ci((m["d2_log_score"] - m["l4_model_log_score"]).to_numpy(), k)
    dd = (m["d1_log_score"] - m["d2_log_score"]).to_numpy()
    out["d1_minus_d2"] = _ci(dd, k)
    yr = m["year"].to_numpy()
    out["d1_minus_d2_by_year"] = {str(y): _ci(dd[yr == y], k[yr == y]) for y in np.unique(yr)}
    s1, s2 = m["d1_decide"].to_numpy(bool), m["decide"].to_numpy(bool)
    out["n_decide_d1_d2_both"] = [int(s1.sum()), int(s2.sum()), int((s1 & s2).sum())]
    out["corr_pred_mean"] = round(float(np.corrcoef(m["d1_mean"], m["pred_mean"])[0, 1]), 4)
    (HERE / "compare_d1.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
