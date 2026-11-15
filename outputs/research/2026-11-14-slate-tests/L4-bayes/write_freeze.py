"""
write_freeze.py
Lane L4: writes ``freeze_online_bayes.md`` for the iteration round's champions, after checking
that ``config.py``'s frozen instances equal the search's best configurations. It re-runs each
champion pair on 2013-18 only to report the discovery log-score difference (trials 3,012 and
3,017, fit block) with its date-clustered interval and the minimum detectable difference for
2019-24, then hashes the scorer, the module, the lane helpers, the panel and the search log,
and finally the note itself.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/write_freeze.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4iter  # noqa: E402
import l4lib  # noqa: E402
import score_heldout as sh  # noqa: E402

from earnings_iv_crush import config as C  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

POWER_Z = float(norm.ppf(0.975) + norm.ppf(0.80))
DISC_TRIAL = {"H_corr": 3012, "residual_value": 3017}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _icc_deff(x: np.ndarray, keys: np.ndarray) -> float:
    _, inv = np.unique(keys, return_inverse=True)
    cnt = np.bincount(inv).astype(float)
    return ob._kish_deff(cnt, np.bincount(inv, weights=x), np.bincount(inv, weights=x * x))[1]


def discovery(tname: str, best: dict[str, Any], d_all: pd.DataFrame) -> dict[str, Any]:
    mname, bname = sh.FROZEN[tname]
    mcfg, bcfg = getattr(C, mname), getattr(C, bname)
    for inst, key in ((mcfg, "model"), (bcfg, "baseline")):
        want = {k: v for k, v in best[key].items() if k not in ("group_level", "score")}
        if json.dumps(ob.describe_config(inst), sort_keys=True) != json.dumps(want, sort_keys=True):
            raise ValueError(f"{tname} {key}: config.py differs from search_best")
    d = d_all[d_all["block"] == "2013-18"].reset_index(drop=True)
    D = l4iter.Design(d)
    y = l4lib.target(d, tname, mcfg)
    mask = l4iter.discovery_mask(d, D.usable, y)
    rm = D.run(mcfg, y, with_features=True, group_level=best["model"]["group_level"])
    rb = D.run(bcfg, y, with_features=False, group_level=best["baseline"]["group_level"])
    sm, sb = l4iter.score(rm, d, mask), l4iter.score(rb, d, mask)
    for s, key in ((sm, "model"), (sb, "baseline")):
        if abs(s["mean_log_score"] - float(best[key]["score"])) > 1e-9:
            raise ValueError(f"{tname} {key} does not reproduce its search score")
    diff = (rm.events["log_score"] - rb.events["log_score"]).to_numpy()[mask]
    keys = d["announce_date"].to_numpy()[mask]
    ci = date_clustered_ci(diff, keys, np.mean)
    deff = _icc_deff(diff, keys)
    sd = float(diff.std(ddof=1))
    full = l4iter.load_all()
    n_next = int(((full["block"] == "2019-24") & (full["h_status"] == "ok")).sum())
    yr = d["entry_date"].dt.year.to_numpy()[mask]
    return {
        "trial": DISC_TRIAL[tname],
        "N": ci.n,
        "clusters": ci.clusters,
        "diff": [ci.point, ci.low, ci.high],
        "diff_median": float(np.median(diff)),
        "diff_by_year": {int(k): float(diff[yr == k].mean()) for k in np.unique(yr)},
        "sd": sd,
        "deff": deff,
        "mde_2019_24": POWER_Z * sd * float(np.sqrt(deff / n_next)),
        "n_2019_24_ok": n_next,
        "model": sm,
        "baseline": sb,
    }


def main() -> None:
    d_all = l4iter.load_all()
    log = pd.read_csv(HERE / "search_log.csv")
    frozen: dict[str, Any] = {}
    disc: dict[str, Any] = {}
    for tname in sh.FROZEN:
        best = json.loads((HERE / f"search_best_{tname}.json").read_text(encoding="utf-8"))
        frozen[tname] = {"model": best["model"], "baseline": best["baseline"]}
        disc[tname] = discovery(tname, best, d_all)
        frozen[tname]["search_rows"] = int((log["target"] == tname).sum())
    hashes = {
        "scorer_sha256": _sha(HERE / "score_heldout.py"),
        "module_sha256": _sha(Path(ob.__file__).resolve()),
        "l4lib_sha256": _sha(HERE / "l4lib.py"),
        "l4iter_sha256": _sha(HERE / "l4iter.py"),
        "base_sha256": _sha(l4lib.BASE),
        "search_log_sha256": _sha(HERE / "search_log.csv"),
    }
    lines = [
        "# Freeze note: L4 sequential Bayesian model, iteration round 1",
        "",
        f"Written {datetime.now(timezone.utc).isoformat(timespec='seconds')} after the "
        "discovery search and before any held-out outcome of this round was computed.",
        "",
        "## Hypothesis, scope and success criteria",
        "",
        "Hypothesis: a sequential conjugate model of the per-trade hedged-hold outcome on 15:59 "
        "features forecasts its distribution better than the same model with only an intercept "
        "and a name effect. Scope: the base panel's 9,350 events, outcomes from "
        "`L1-corrections/base_corrected.parquet`, per trade, net at the touch, % of m0. "
        "Primary pass (declared in `diagnosis.log` entry 1): the mean per-event log-score "
        "difference, model minus baseline, above zero with the date-clustered 95% lower bound "
        "above zero, on 2019-24 and on 2025-26 separately. Kill: the 2019-24 point estimate at "
        "or below zero. Both held-out blocks were viewed for this outcome family before this "
        "lane, so every held-out number is exploratory. Book rules (entry 4): P(H_corr > 0) > "
        "0.5 and the predictive mean above zero, each against a date-stratified random null "
        "(pass at the 95th percentile) and with its mean's interval for the economic read.",
        "",
        "## Champions (selected by discovery log score alone)",
        "",
    ]
    for tname, f in frozen.items():
        r = disc[tname]
        lines += [
            f"### {tname}",
            "",
            f"Search rows for this target in `search_log.csv`: {f['search_rows']} (model and "
            "baseline classes together).",
            "",
            f"- Model: `{json.dumps(f['model'])}`",
            f"- Baseline: `{json.dumps(f['baseline'])}`",
            f"- Discovery (trial {r['trial']}, fit block, in sample for the search): mean "
            f"log-score difference {r['diff'][0]:+.5f} nats per event, date-clustered 95% "
            f"[{r['diff'][1]:+.5f}, {r['diff'][2]:+.5f}], N {r['N']}, {r['clusters']} dates; "
            f"median {r['diff_median']:+.5f}; by year "
            f"{json.dumps({k: round(v, 5) for k, v in r['diff_by_year'].items()})}.",
            f"- Calibration on discovery, model: 90% coverage {r['model']['coverage90']:.3f}, "
            f"PIT below 0.05 {r['model']['pit_lo5']:.3f}, above 0.95 {r['model']['pit_hi5']:.3f}"
            f"; baseline {r['baseline']['coverage90']:.3f}, {r['baseline']['pit_lo5']:.3f}, "
            f"{r['baseline']['pit_hi5']:.3f}.",
            f"- Power: minimum detectable difference on 2019-24 (N {r['n_2019_24_ok']}, 80% "
            f"power, 5% two-sided, design effect {r['deff']:.2f}) {r['mde_2019_24']:.5f} nats "
            "per event. The discovery difference is the best of the search, so it is biased "
            "upwards; the held-out read is the unbiased one.",
            "",
        ]
    lines += [
        "## Frozen configuration",
        "",
        "```json",
        json.dumps(frozen, indent=2, default=str),
        "```",
        "",
        "## Hashes",
        "",
        *[f"{k}: {v}" for k, v in hashes.items()],
        "",
    ]
    body = ("\n".join(lines)).encode("utf-8")
    note = body + f"self_sha256: {hashlib.sha256(body).hexdigest()}\n".encode()
    (HERE / "freeze_online_bayes.md").write_bytes(note)
    (HERE / "discovery_fit.json").write_text(json.dumps(disc, indent=2) + "\n", encoding="utf-8")
    sh.verify_freeze()
    print("written and verified freeze_online_bayes.md; discovery_fit.json")


if __name__ == "__main__":
    main()
