"""
fit_discovery.py
Lane L4: fit the sequential model's hyperparameters on 2013-18 only, for H_corr and for
residual_value. Scores every configuration of the declared grids (120 with features, 40 without)
by mean per-event log predictive density, selects the best of each, and reports the selected
pair's discovery log-score difference (trials 3,012 and 3,017) with the power for 2019-24.

Only 2013-18 events are passed to the model, so no later outcome is computed on.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/fit_discovery.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4lib  # noqa: E402

from earnings_iv_crush.config import ONLINE_BAYES  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci, log_block_view  # noqa: E402

BLOCK = "2013-18"
TIE = 1e-4  # declared: ties within this go to the earliest configuration in grid order
POWER_Z = float(norm.ppf(0.975) + norm.ppf(0.80))


def _mean_ls(run: ob.OnlineRun, mask: np.ndarray) -> float:
    return float(run.events.loc[mask, "log_score"].mean())


def _pick(rows: list[dict]) -> int:
    best = max(r["mean_log_score"] for r in rows)
    return next(i for i, r in enumerate(rows) if r["mean_log_score"] >= best - TIE)


def _icc_deff(x: np.ndarray, keys: np.ndarray) -> float:
    _, inv = np.unique(keys, return_inverse=True)
    cnt = np.bincount(inv).astype(float)
    s1 = np.bincount(inv, weights=x)
    s2 = np.bincount(inv, weights=x * x)
    return ob._kish_deff(cnt, s1, s2)[1]


def fit(d: pd.DataFrame, tname: str, X: np.ndarray, raw: pd.DataFrame, usable: np.ndarray) -> dict:
    y = l4lib.target(d, tname, ONLINE_BAYES)
    t0 = time.time()
    model_rows, base_rows = [], []
    runs: dict[str, ob.OnlineRun] = {}
    for i, cfg in enumerate(ob.grid(ONLINE_BAYES, with_features=True)):
        r = ob.run_online(
            l4lib.frame(d, y, raw, usable, cfg), X, cfg, coef_names=l4lib.COEFS, quiet=True
        )
        sc = r.events["scored"].to_numpy() & np.isfinite(r.events["log_score"].to_numpy())
        model_rows.append(
            {
                **ob.describe_config(cfg),
                "mean_log_score": _mean_ls(r, sc),
                "n_scored": int(sc.sum()),
            }
        )
        runs[f"m{i}"] = r
        if i == 0:
            print(f"  [{tname}] first configuration in {time.time() - t0:.1f}s")
    for i, cfg in enumerate(ob.grid(ONLINE_BAYES, with_features=False)):
        r = ob.run_online(
            l4lib.frame(d, y, raw, usable, cfg),
            X[:, :1],
            cfg,
            coef_names=l4lib.COEFS[:1],
            quiet=True,
        )
        sc = r.events["scored"].to_numpy() & np.isfinite(r.events["log_score"].to_numpy())
        base_rows.append(
            {
                **ob.describe_config(cfg),
                "mean_log_score": _mean_ls(r, sc),
                "n_scored": int(sc.sum()),
            }
        )
        runs[f"b{i}"] = r
    print(
        f"  [{tname}] {len(model_rows)} + {len(base_rows)} configurations in "
        f"{time.time() - t0:.0f}s"
    )
    gm = pd.DataFrame(model_rows).assign(kind="model")
    gb = pd.DataFrame(base_rows).assign(kind="baseline")
    pd.concat([gm, gb]).to_csv(HERE / f"grid_{tname}_2013-18.csv", index=False)
    im, ib = _pick(model_rows), _pick(base_rows)
    rm, rb = runs[f"m{im}"], runs[f"b{ib}"]
    sc = (
        rm.events["scored"]
        & rb.events["scored"]
        & rm.events["log_score"].notna()
        & rb.events["log_score"].notna()
    ).to_numpy()
    diff = (rm.events["log_score"] - rb.events["log_score"]).to_numpy()[sc]
    keys = d["announce_date"].to_numpy()[sc]
    ci = date_clustered_ci(diff, keys, np.mean)
    deff = _icc_deff(diff, keys)
    sd = float(diff.std(ddof=1))
    n_next = int(
        (usable & (d["block"] == "2019-24").to_numpy() & (d["h_status"] == "ok").to_numpy()).sum()
    )
    mde = POWER_Z * sd * float(np.sqrt(deff / n_next))
    ev = rm.events.loc[sc]
    sel = ev["decide"].to_numpy(bool)
    out = {
        "target": tname,
        "block": BLOCK,
        "model": {**model_rows[im], "grid_index": im},
        "baseline": {**base_rows[ib], "grid_index": ib},
        "diff_mean": ci.point,
        "diff_low": ci.low,
        "diff_high": ci.high,
        "N": ci.n,
        "clusters": ci.clusters,
        "diff_median": float(np.median(diff)),
        "diff_sd": sd,
        "deff_diff": deff,
        "n_2019_24_usable": n_next,
        "mde_2019_24": mde,
        "coverage90": float(ev["covered"].mean()),
        "n_selected": int(sel.sum()),
        "search_count": len(model_rows) + len(base_rows),
        "model_runner_up_gap": float(
            sorted(r["mean_log_score"] for r in model_rows)[-1]
            - sorted(r["mean_log_score"] for r in model_rows)[-2]
        ),
    }
    print(
        f"  [{tname}] selected model {ob.describe_config(ob.grid(ONLINE_BAYES, with_features=True)[im])}"
        f" mean log score {model_rows[im]['mean_log_score']:.4f}; baseline "
        f"{ob.describe_config(ob.grid(ONLINE_BAYES, with_features=False)[ib])} "
        f"{base_rows[ib]['mean_log_score']:.4f}\n"
        f"  [{tname}] {BLOCK} log-score difference (model minus baseline, per event, nats) "
        f"{ci}; median {out['diff_median']:+.4f}; sd {sd:.4f}; design effect {deff:.2f}\n"
        f"  [{tname}] power: MDE for 2019-24 (N usable {n_next}, 80% power, 5% two-sided) "
        f"{mde:.4f} nats per event\n"
        f"  [{tname}] in-block 90% coverage {out['coverage90']:.3f}; decide trade "
        f"{out['n_selected']} of {len(ev)}"
    )
    return out


def main() -> None:
    d_all = l4lib.load()
    d = d_all[d_all["block"] == BLOCK].reset_index(drop=True)
    print(f"[fit] discovery events {len(d)} ({BLOCK}); later blocks are not passed to the model")
    X, usable, raw = l4lib.design(d, ONLINE_BAYES)
    res = {}
    for tname, fam in (("H_corr", "hedged_hold_H_corr"), ("residual_value", "residual_value")):
        log_block_view(
            l4lib.BLOCKS_VIEWED,
            panel="base_corrected",
            period=BLOCK,
            outcome_family=fam,
            feature_family="online_bayes_1559_cost_structure",
            viewed_by="L4 fit_discovery (trials 3,012 and 3,017)",
            kind="trial",
        )
        res[tname] = fit(d, tname, X, raw, usable)
    (HERE / "discovery_fit.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print("written discovery_fit.json")


if __name__ == "__main__":
    main()
