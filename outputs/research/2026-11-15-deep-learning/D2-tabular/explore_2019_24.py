"""
explore_2019_24.py
Lane D2, EXPLORATORY and descriptive, chosen after the frozen 2019-24 read: what carries the
held-out log-score gain and the selected book. Reads the per-event output written once by
score_heldout.py (heldout_2019-24_events.parquet) and the corrected panel; fits nothing.

1. The gain over the L4 champion by within-block tercile of tenor, half-spread and implied move.
2. L4's heteroscedasticity on 2019-24: RMS of the outcome's standardised z residual against L4's
   predictive (m_pred_loc, m_pred_scale), by tenor tercile.
3. The selected book against the unselected events and the tight-spread screen, by L1 P&L
   component (% of m0 per trade), so the mechanism is named.

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/explore_2019_24.py
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

COMPONENTS = ["c_premium", "c_settlement", "c_hedge", "c_equity_cost", "c_fees", "c_disposal",
              "c_financing"]  # fmt: skip


def _ci(v: np.ndarray, k: np.ndarray) -> list[float]:
    c = d2lib.date_clustered_ci(v, k, np.mean)
    return [round(c.point, 4), round(c.low, 4), round(c.high, 4), c.n]


def main() -> None:
    d2lib.log_view("2019-24", "explore_2019_24 (exploratory, after the frozen read)", "descriptive")
    cards = pd.read_parquet(HERE / "heldout_2019-24_events.parquet")
    cards["entry_date"] = pd.to_datetime(cards["entry_date"]).dt.normalize()
    import l4lib

    d = l4lib.load()
    X, _, _ = l4lib.design(d, d2lib.C.ONLINE_BAYES_L4_MODEL)
    feats = pd.DataFrame(X[:, 1:], columns=list(d2lib.ob.FEATURES))
    base = pd.concat([d[["ticker", "entry_date", *COMPONENTS]], feats], axis=1)
    li = pd.read_parquet(d2lib.L4_INPUTS, columns=["ticker", "entry_date", "m_pred_loc",
                                                    "m_pred_scale"])  # fmt: skip
    li["entry_date"] = pd.to_datetime(li["entry_date"]).dt.normalize()
    e = cards[cards["scored"]].merge(base, on=["ticker", "entry_date"], how="left",
                                     validate="1:1").merge(li, on=["ticker", "entry_date"],
                                                           how="left", validate="1:1")  # fmt: skip
    if e[COMPONENTS + ["m_pred_loc"]].isna().any().any():
        raise ValueError("a join left NaN components or L4 predictive")
    k = e["announce_date"].to_numpy()
    gain = (e["d2_log_score"] - e["l4_model_log_score"]).to_numpy()
    out: dict[str, Any] = {"label": "EXPLORATORY, descriptive, chosen after the 2019-24 read",
                           "N": len(e)}  # fmt: skip
    for c in ("log1p_dte", "log_half_spread", "log_implied_move"):
        t = pd.qcut(e[c], 3, labels=False).to_numpy()
        out[f"gain_by_{c}_tercile"] = {str(i): _ci(gain[t == i], k[t == i]) for i in range(3)}
    z = d2lib.to_z(e["h"].to_numpy(), e["U"].to_numpy())
    r = (z - e["m_pred_loc"].to_numpy()) / e["m_pred_scale"].to_numpy()
    t = pd.qcut(e["log1p_dte"], 3, labels=False).to_numpy()
    out["l4_rms_std_resid_by_tenor_tercile"] = [
        round(float(np.sqrt(np.mean(r[t == i] ** 2))), 3) for i in range(3)
    ]
    out["l4_scale_sd_over_mean"] = round(float(e["m_pred_scale"].std() / e["m_pred_scale"].mean()),
                                         4)  # fmt: skip
    sel = e["decide"].to_numpy(bool)
    tight = d2lib.tight_per_date(sel, e["half_spread"].to_numpy(float),
                                 e["entry_date"].to_numpy(), e["ticker"].to_numpy())  # fmt: skip
    comp: dict[str, Any] = {}
    for c in COMPONENTS:
        v = e[c].to_numpy(float) * d2lib.PCT
        comp[c] = {
            "sel_minus_unsel": round(float(v[sel].mean() - v[~sel].mean()), 3),
            "sel_minus_tight": round(float(v[sel].mean() - v[tight].mean()), 3),
        }
    out["book_gap_by_component_pct_m0"] = comp
    out["selected_only_vs_tight_only"] = {
        "n_sel_not_tight": int((sel & ~tight).sum()),
        "H_net_sel_not_tight": _ci(e["h"].to_numpy()[sel & ~tight], k[sel & ~tight]),
        "H_net_tight_not_sel": _ci(e["h"].to_numpy()[tight & ~sel], k[tight & ~sel]),
    }
    out["selected_tenor_vs_pool_log1p_dte_z"] = [
        round(float(e.loc[sel, "log1p_dte"].mean()), 3),
        round(float(e["log1p_dte"].mean()), 3),
    ]
    (HERE / "explore_2019_24.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
