"""c1_describe.py: logged feature diagnostics for C1 and the payer confound in trial 2,952.

Feature side (no outcome): implied borrow of dividend payers under projected and realised
dividends, the names at the top of the borrow distribution, and the tail counts on dividend-free
events. Then the composition of trial 2,952's selected set on 2013-18 (payers and burn-in events
carry no bin but sit in the selected set under amendment A1), and, labelled exploratory, the
excluded decile's component contrast against the binned dividend-free events only, which removes
the payer against non-payer mix from the comparison. Discovery block only; no new trial.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c1_describe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import c1_score  # noqa: E402
import lib  # noqa: E402

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.research.protocol import N_BOOT, SEED  # noqa: E402

TOP_Q = 0.99  # names populating the top 1% of the all-event borrow distribution
COMPONENTS = ("c_premium", "c_settlement", "c_hedge", "c_equity_cost", "c_fees", "c_financing")


def _diff(m: np.ndarray) -> float:
    v, s = m[:, 0], m[:, 1] == 1.0
    return float(v[s].mean() - v[~s].mean())


def main() -> None:
    f = pd.read_parquet(HERE / "c1_borrow.parquet")
    ok = f[f["b_status"] == "ok"]
    out: dict = {
        "payer_median_borrow_projected": float(ok.loc[ok["div_free"] == 0, "borrow"].median()),
        "payer_median_borrow_realised": float(
            ok.loc[ok["div_free_realised_diag"] == 0, "borrow_realised_diag"].median()
        ),
        "n_payers_projected": int((ok["div_free"] == 0).sum()),
        "n_payers_realised": int((ok["div_free_realised_diag"] == 0).sum()),
    }
    thr = ok["borrow"].quantile(TOP_Q)
    top = ok[ok["borrow"] >= thr]
    out["top1pct_threshold"] = float(thr)
    out["top1pct_n"] = int(len(top))
    out["top1pct_payer_share"] = float((top["div_free"] == 0).mean())
    out["top1pct_names"] = {k: int(v) for k, v in top["ticker"].value_counts().head(8).items()}
    df = ok[ok["div_free"] == 1]
    out["div_free_n"] = int(len(df))
    out["div_free_over_10pct"] = int((df["borrow"] > 0.10).sum())
    out["div_free_share_over_5pct"] = float((df["borrow"] > 0.05).mean())

    d = c1_score.build()
    pop = d[(d["block"] == "2013-18") & (d["b_status"] == "ok") & d["residual_value"].notna()]
    pop = pop.reset_index(drop=True)
    sel = pop["bin"] != 9
    out["sel_n"] = int(sel.sum())
    out["sel_with_bin"] = int((sel & (pop["bin"] >= 0)).sum())
    out["sel_payers"] = int((sel & (pop["div_free"] == 0)).sum())
    out["sel_div_free_burn_in"] = int((sel & (pop["div_free"] == 1) & (pop["bin"] < 0)).sum())
    # exploratory: excluded decile against binned dividend-free events only
    bf = pop[pop["bin"] >= 0].reset_index(drop=True)
    s = (bf["bin"] != 9).to_numpy(float)
    keys = pd.to_datetime(bf["exit_date"]).dt.normalize().to_numpy()
    ex: dict = {"N": int(len(bf)), "n_sel": int(s.sum())}
    for c in ("residual_value", "H_corr", *COMPONENTS):
        m = np.column_stack([bf[c].to_numpy(float), s])
        lo, hi = cluster_bootstrap_ci(m, keys, _diff, n_boot=N_BOOT, seed=SEED)
        ex[c] = {"diff": 100 * _diff(m), "lo": 100 * lo, "hi": 100 * hi}
    out["exploratory_div_free_only_sel_minus_excl_pct_m0"] = ex
    print(json.dumps(out, indent=2))
    (HERE / "c1_describe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for fam in ("residual_value", "hedged_hold"):
        lib.log_view(
            "2013-18",
            fam,
            c1_score.FEATURE_FAMILY,
            "L3 c1_describe.py (exploratory)",
            "descriptive",
        )


if __name__ == "__main__":
    main()
