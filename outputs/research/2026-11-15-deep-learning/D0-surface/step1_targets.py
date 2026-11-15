"""
step1_targets.py
D0 step 1: the deep-learning programme's target file. Joins L1's corrected panel to L2's hedge
commission, forms ``H_net = H_corr - comm_1c`` and the premium unit ``U`` exactly as L4 builds
it, prints the funnel and tests whether the events without commission depend on the outcome.

Basis: every outcome column is a fraction of m0 per trade (0.20 times the 15:59 parity forward
plus the 15:59 straddle bid), net at the touch, not annualised, as stored upstream. ``U_pct`` is
the transform unit L4 passes to ``run_online`` (100 s0 / m0, % of m0); ``U`` is the same as a
fraction of m0. Nothing is filled: an event without ``comm_1c`` or ``H_corr`` has NaN ``H_net``.

Name collision. ``base_corrected.parquet`` carries a column ``H_net`` that is L1's netting
correction (``H`` re-settled under ``HEDGED_NET``). It is not this file's ``H_net`` and is not
copied here; this file's ``H_net`` is the brief's declaration.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D0-surface/step1_targets.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
L4 = ROOT / "outputs" / "research" / "2026-11-14-slate-tests" / "L4-bayes"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(L4))

import l4lib  # noqa: E402

from earnings_iv_crush.config import ONLINE_BAYES_L4_MODEL  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci, log_block_view  # noqa: E402

COMM = ROOT / "outputs" / "research" / "2026-11-14-slate-tests" / "L2-execution"
COMM = COMM / "hedge_commission.parquet"
OUT = HERE / "targets.parquet"
RES = HERE / "step1_results.json"
TRIALS = HERE / "trials.csv"
TRIAL_FIELDS = ["trial_id", "idea", "rule", "block", "N", "statistic", "interval", "verdict"]
BLOCKS_VIEWED = HERE / "blocks_viewed.csv"
KEYS = ["ticker", "entry_date"]


def _diff_ci(values: np.ndarray, group: np.ndarray, keys: np.ndarray) -> Any:
    """Group minus rest mean, date-clustered by resampling event indices by announcement date."""
    v, g = np.asarray(values, float), np.asarray(group, bool)

    def stat(idx: np.ndarray) -> float:
        i = idx.astype(int)
        a, b = v[i][g[i]], v[i][~g[i]]
        return float(a.mean() - b.mean()) if a.size and b.size else float("nan")

    return date_clustered_ci(np.arange(v.size, dtype=float), keys, stat)


def main() -> None:
    d = l4lib.load()
    c = pd.read_parquet(COMM, columns=KEYS + ["comm_1c"])
    c["entry_date"] = pd.to_datetime(c["entry_date"]).dt.normalize()
    if c.duplicated(KEYS).any():
        raise ValueError("hedge_commission.parquet has duplicated keys")
    d = d.merge(c, on=KEYS, how="left", validate="one_to_one")
    raw = ob.build_features(d, ONLINE_BAYES_L4_MODEL)
    ps = raw["premium_share"].to_numpy(float)

    ok = (d["h_status"] == "ok").to_numpy()
    has_c = d["comm_1c"].notna().to_numpy()
    has_h = d["H_corr"].notna().to_numpy()
    h_net = d["H_corr"].to_numpy(float) - d["comm_1c"].to_numpy(float)
    target_ok = ok & has_c & has_h & np.isfinite(h_net)
    funnel = {
        "events": int(len(d)),
        "h_status ok": int(ok.sum()),
        "H_corr present": int(has_h.sum()),
        "comm_1c present": int(has_c.sum()),
        "comm_1c present and h_status ok": int((has_c & ok).sum()),
        "H_net defined (target_ok)": int(target_ok.sum()),
        "dropped: no comm_1c": int((~has_c).sum()),
        "dropped: no comm_1c, of which h_status not ok": int((~has_c & ~ok).sum()),
        "U defined and positive": int((np.isfinite(ps) & (ps > 0)).sum()),
    }
    by_block = {
        b: {
            "events": int((d["block"] == b).sum()),
            "target_ok": int((target_ok & (d["block"] == b).to_numpy()).sum()),
            "no_comm": int((~has_c & (d["block"] == b).to_numpy()).sum()),
        }
        for b in l4lib.BLOCK_ORDER
    }
    print("[funnel]", json.dumps(funnel, indent=1))
    print("[funnel by block]", json.dumps(by_block))
    if (target_ok != (ok & has_c)).any() or (has_c != ok).any():
        raise AssertionError("commission coverage is not exactly the h_status ok set")

    out = pd.DataFrame(
        {
            "ticker": d["ticker"],
            "entry_date": d["entry_date"],
            "expiry": d["expiry"],
            "announce_date": d["announce_date"],
            "block": d["block"],
            "h_status": d["h_status"],
            "H_corr": d["H_corr"],
            "comm_1c": d["comm_1c"],
            "H_net": np.where(target_ok, h_net, np.nan),
            "residual_value": d["residual_value"],
            "U": ps,
            "U_pct": ps * ONLINE_BAYES_L4_MODEL.pct_per_unit,
            "m0": d["m0"],
            "target_ok": target_ok,
        }
    )
    means = {
        b: {
            k: float(out.loc[(out["block"] == b) & out["target_ok"], k].mean())
            for k in ("H_corr", "comm_1c", "H_net")
        }
        for b in l4lib.BLOCK_ORDER
    }
    print("[means, fraction of m0 per trade, target_ok rows]", json.dumps(means))
    m19 = means["2019-24"]
    if not (abs(m19["H_corr"] + 0.011941) < 5e-7 and abs(m19["comm_1c"] - 0.001398) < 5e-7):
        raise AssertionError(f"2019-24 means differ from the team lead's check: {m19}")

    # Attrition: the events without commission are exactly the h_status-not-ok events, so they
    # have no H_corr. The outcome-dependence test uses the outcomes they do carry, the stored
    # H and residual_value, against the other events of the same block.
    log_block_view(
        BLOCKS_VIEWED,
        panel="base_corrected",
        period="2025-26",
        outcome_family="hedged_hold_H_stored_and_residual_value",
        feature_family="attrition_no_commission",
        viewed_by="D0 step1_targets (attrition test, trial 3,134)",
        kind="trial",
    )
    drop = ~has_c
    blocks_with_drops = sorted(set(d.loc[drop, "block"]))
    att: dict[str, Any] = {"drop_blocks": blocks_with_drops, "drop_src": {}}
    att["drop_src"] = {str(k): int(v) for k, v in d.loc[drop, "src"].value_counts().items()}
    sub = d["block"].isin(blocks_with_drops).to_numpy()
    keys = d.loc[sub, "announce_date"].to_numpy()
    for col in ("H", "residual_value"):
        v = d[col].to_numpy(float)[sub]
        g = drop[sub]
        fin = np.isfinite(v)
        w = ttest_ind(v[g & fin], v[~g & fin], equal_var=False)
        ci = _diff_ci(v[fin], g[fin], keys[fin])
        att[col] = {
            "n_drop": int((g & fin).sum()),
            "n_rest": int((~g & fin).sum()),
            "mean_drop_pct": float(100 * v[g & fin].mean()),
            "mean_rest_pct": float(100 * v[~g & fin].mean()),
            "diff_pct": float(100 * ci.point),
            "diff_ci_pct": [float(100 * ci.low), float(100 * ci.high)],
            "clusters": int(ci.clusters),
            "welch_t": float(w.statistic),
            "welch_p": float(w.pvalue),
        }
        print(
            f"[attrition {col}] drops {att[col]['n_drop']} vs rest {att[col]['n_rest']} in "
            f"{blocks_with_drops}: mean {att[col]['mean_drop_pct']:+.3f} vs "
            f"{att[col]['mean_rest_pct']:+.3f} % of m0; difference {att[col]['diff_pct']:+.3f} "
            f"[{att[col]['diff_ci_pct'][0]:+.3f}, {att[col]['diff_ci_pct'][1]:+.3f}] "
            f"(date-clustered 95%, {ci.clusters} clusters); Welch t {w.statistic:+.3f}, "
            f"p {w.pvalue:.3f}"
        )
    tmp = OUT.with_suffix(".tmp.parquet")
    out.to_parquet(tmp, index=False)
    tmp.replace(OUT)
    RES.write_text(
        json.dumps({"funnel": funnel, "by_block": by_block, "means": means, "attrition": att},
                   indent=1) + "\n",
        encoding="utf-8",
    )  # fmt: skip
    a, b = att["H"], att["residual_value"]
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRIAL_FIELDS)
        if new:
            w.writeheader()
        w.writerow(
            {
                "trial_id": 3134,
                "idea": "D0 attrition: 35 events without comm_1c (all h_status not_reproduced, "
                "2025-26, Yahoo path)",
                "rule": "dropped minus kept mean, stored H and residual_value, same block; Welch t "
                "and date-clustered 95%",
                "block": "2025-26",
                "N": f"{a['n_drop']} vs {a['n_rest']}",
                "statistic": f"H {a['diff_pct']:+.3f} % of m0 (Welch p {a['welch_p']:.3f}); "
                f"residual_value {b['diff_pct']:+.3f} % of m0 (Welch p {b['welch_p']:.2g})",
                "interval": f"H [{a['diff_ci_pct'][0]:+.3f}, {a['diff_ci_pct'][1]:+.3f}]; "
                f"residual_value [{b['diff_ci_pct'][0]:+.3f}, {b['diff_ci_pct'][1]:+.3f}]",
                "verdict": "H: no detectable dependence (N=35, underpowered); residual_value: "
                "drops differ (exploratory)",
            }
        )
    print(f"written {OUT.name} ({len(out)} rows), {RES.name} and trial 3,134")


if __name__ == "__main__":
    main()
