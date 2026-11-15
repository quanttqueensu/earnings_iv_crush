"""
step2_benchmark.py
D0 step 2: the L4 benchmark re-run on ``H_net``. Runs the frozen L4 champion
(``ONLINE_BAYES_L4_MODEL``) and its baseline (``ONLINE_BAYES_L4_BASELINE``) through L4's own
design (``l4iter.Design``, imported, not edited) on ``H_net = H_corr - comm_1c`` from
``targets.parquet``, after first reproducing L4's stored ``H_corr`` run event for event.

Outputs, in this folder:

- ``l4_inputs.parquet``: keys plus the prior predictive quantities only (no outcome-derived
  column), for the model (``m_``) and the baseline (``b_``);
- ``l4_scores.parquet``: keys plus the per-event log score in ``H_net`` space with the Jacobian,
  PIT and 90% coverage, for both;
- ``step2_results.json`` and trial rows 3,132 (2019-24) and 3,133 (2025-26, exploratory).

Basis: ``y`` is ``H_net`` per trade in % of m0, net at the touch, not annualised. The log score
is a log density per unit of % of m0 (add ln 100 for a density per unit fraction of m0); the
model-minus-baseline difference is unit-free. Intervals are date-clustered 95% on announcement
dates (``protocol.date_clustered_ci``, 5,000 draws, seed 0).

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D0-surface/step2_benchmark.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
L4 = ROOT / "outputs" / "research" / "2026-11-14-slate-tests" / "L4-bayes"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(L4))

import l4iter  # noqa: E402
import l4lib  # noqa: E402
import score_heldout as l4score  # noqa: E402

from earnings_iv_crush import config as C  # noqa: E402
from earnings_iv_crush.research.protocol import log_block_view  # noqa: E402

TARGETS = HERE / "targets.parquet"
L4_RUN = L4 / "run_H_corr.parquet"
BLOCKS_VIEWED = HERE / "blocks_viewed.csv"
TRIALS = HERE / "trials.csv"
TRIAL_FIELDS = ["trial_id", "idea", "rule", "block", "N", "statistic", "interval", "verdict"]
TRIAL_IDS = {"2019-24": 3132, "2025-26": 3133}
SLATE_H_CORR = (0.0139, 0.0080, 0.0195)  # slate-tests trial 3,013, L4 heldout_results.json
REPRO_TOL = 1e-9  # nats; the re-run must give L4's stored H_corr log scores to rounding
KEYS = ["ticker", "entry_date", "expiry", "announce_date", "block"]
INPUT_COLS = [
    "pred_loc",
    "pred_scale",
    "pred_df",
    "pred_q",
    "pred_s2",
    "p_pos",
    "pred_median_y",
    "name_effect_at_entry",
    "n_settled_at_entry",
    "scored",
]
SCORE_COLS = ["log_score", "pit", "covered", "scored"]


def _trial(row: dict[str, Any]) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRIAL_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def main() -> None:
    t0 = time.time()
    mcfg, bcfg = C.ONLINE_BAYES_L4_MODEL, C.ONLINE_BAYES_L4_BASELINE
    d = l4iter.load_all()
    D = l4iter.Design(d)

    # Reproduction: the stored L4 H_corr run, event for event (blocks already viewed by L4).
    log_block_view(
        BLOCKS_VIEWED,
        panel="base_corrected",
        period="2013-26",
        outcome_family="hedged_hold_H_corr",
        feature_family="online_bayes_iteration_round_1",
        viewed_by="D0 step2_benchmark (reproduction of L4 run_H_corr, not a trial)",
        kind="descriptive",
    )
    y_corr = l4lib.target(d, "H_corr", mcfg)
    rm0 = D.run(mcfg, y_corr, with_features=True, quiet=False)
    stored = pd.read_parquet(L4_RUN, columns=["ticker", "entry_date", "m_log_score"])
    stored["entry_date"] = pd.to_datetime(stored["entry_date"]).dt.normalize()
    if not (
        stored[["ticker", "entry_date"]].to_numpy() == d[["ticker", "entry_date"]].to_numpy()
    ).all():
        raise AssertionError("event order differs from L4's run_H_corr.parquet")
    a, b = rm0.events["log_score"].to_numpy(), stored["m_log_score"].to_numpy()
    if not np.array_equal(np.isfinite(a), np.isfinite(b)):
        raise AssertionError("scored sets differ from L4's stored run")
    gap = float(np.nanmax(np.abs(a - b)))
    print(f"[repro] H_corr model log scores vs L4 stored: max abs gap {gap:.3e} nats")
    if gap > REPRO_TOL:
        raise AssertionError(f"reproduction gap {gap} above {REPRO_TOL}")

    # The benchmark on H_net.
    t = pd.read_parquet(TARGETS)
    t["entry_date"] = pd.to_datetime(t["entry_date"]).dt.normalize()
    if not (t[["ticker", "entry_date"]].to_numpy() == d[["ticker", "entry_date"]].to_numpy()).all():
        raise AssertionError("targets.parquet order differs from the L4 load order")
    unit_l4 = D.frame(mcfg, y_corr, "none")["unit"].to_numpy(float)
    if not np.allclose(unit_l4, t["U_pct"].to_numpy(float), rtol=0, atol=1e-12):
        raise AssertionError("targets U_pct differs from L4's transform unit")
    for blk in ("2013-18", "2019-24", "2025-26"):
        log_block_view(
            BLOCKS_VIEWED,
            panel="base_corrected",
            period=blk,
            outcome_family="hedged_hold_H_net",
            feature_family="online_bayes_iteration_round_1",
            viewed_by="D0 step2_benchmark (L4 champion re-run on H_net)"
            + (f", trial {TRIAL_IDS[blk]:,}" if blk in TRIAL_IDS else ""),
            kind="trial",
        )
    y = t["H_net"].to_numpy(float) * mcfg.pct_per_unit  # NaN on the 35 dropped events
    rm = D.run(mcfg, y, with_features=True, quiet=False)
    rb = D.run(bcfg, y, with_features=False, quiet=False)
    disc = l4iter.score(rm, d, l4iter.discovery_mask(d, D.usable, y))
    print(f"[H_net] discovery 2015-18 model mean log score {disc['mean_log_score']:+.5f}")
    res: dict[str, Any] = {"repro_max_gap_nats": gap, "discovery_model": disc, "blocks": {}}
    for blk in ("2013-18", "2015-18", "2019-24", "2025-26"):
        res["blocks"][blk] = l4score.score_block(d, rm, rb, blk, "H_net")

    keys = d[KEYS].copy()
    inputs = keys.copy()
    scores = keys.copy()
    for tag, run in (("m", rm), ("b", rb)):
        for c in INPUT_COLS:
            inputs[f"{tag}_{c}"] = run.events[c].to_numpy()
        for c in SCORE_COLS:
            scores[f"{tag}_{c}"] = run.events[c].to_numpy()
    inputs["usable"] = D.usable
    inputs["v"] = D.v(mcfg)
    inputs["U_pct"] = unit_l4
    for name, frame in (("l4_inputs", inputs), ("l4_scores", scores)):
        tmp = HERE / f"{name}.tmp.parquet"
        frame.to_parquet(tmp, index=False)
        tmp.replace(HERE / f"{name}.parquet")
    (HERE / "step2_results.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8"
    )
    for blk, tid in TRIAL_IDS.items():
        r = res["blocks"][blk]
        _trial(
            {
                "trial_id": tid,
                "idea": "D0 L4 benchmark re-run on H_net (frozen champion vs frozen baseline)",
                "rule": "mean per-event log predictive score in H_net space, model minus baseline",
                "block": blk,
                "N": r["N"],
                "statistic": f"{r['diff_mean']:+.5f} nats per event",
                "interval": f"[{r['diff_low']:+.5f}, {r['diff_high']:+.5f}]",
                "verdict": ("pass" if r["pass"] else "fail")
                + (
                    " (exploratory; 2019-24 viewed before)"
                    if blk == "2019-24"
                    else " (exploratory)"
                ),
            }
        )
    r = res["blocks"]["2019-24"]
    print(
        f"[benchmark] 2019-24 H_net gain {r['diff_mean']:+.4f} [{r['diff_low']:+.4f}, "
        f"{r['diff_high']:+.4f}] nats per event, N={r['N']}; slate-tests H_corr "
        f"{SLATE_H_CORR[0]:+.4f} [{SLATE_H_CORR[1]:+.4f}, {SLATE_H_CORR[2]:+.4f}]"
    )
    print(
        f"written l4_inputs.parquet, l4_scores.parquet, step2_results.json in {time.time() - t0:.0f}s"
    )


if __name__ == "__main__":
    main()
