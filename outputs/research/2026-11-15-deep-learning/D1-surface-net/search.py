"""
search.py
Lane D1 development search: each configuration is fit on the rolling-origin folds 2016, 2017
and 2018 (train on events expiring before 1 January, early-stop on the last year of the
window, refit on the whole window), with 2 seeds averaged as a density ensemble, and scored
by the per-event log density of H_net (nats per event, Jacobian included) against L4's model
and baseline on the same events. One row per configuration goes to ``search_log.csv`` at once;
a configuration already in the log is never refit.

Development only: outcomes entered after 2018 are blanked at load and ``l4_scores`` rows after
2018 are not read. The budget is 40 configurations; the script refuses to exceed it.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D1-surface-net/search.py --round 1
    python .../search.py --round 2 --specs round2_specs.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import d1data
import d1eval
import d1lib
import numpy as np
import pandas as pd
import torch

HERE = Path(__file__).resolve().parent
LOG = HERE / "search_log.csv"
PRED_DIR = HERE / "dev_preds"
BUDGET = 40

REG = {
    "small": {"width": 32, "depth": 1, "dropout": 0.1, "weight_decay": 1e-3},
    "medium": {"width": 64, "depth": 2, "dropout": 0.2, "weight_decay": 1e-2},
    "heavy": {"width": 64, "depth": 2, "dropout": 0.5, "weight_decay": 1e-1},
}


def round1() -> list[dict[str, Any]]:
    """The 30 declared round-1 configurations (10 more are left for round 2)."""
    out: list[dict[str, Any]] = []
    for arch in ("mlp", "conv"):
        for reg in ("small", "medium", "heavy"):
            for lr in (1e-3, 3e-4):
                out.append({"variant": "b", "arch": arch, "head": "gmm", "K": 1, "lr": lr,
                            **REG[reg], "_reg": reg})
    for arch in ("mlp", "conv"):
        out.append({"variant": "b", "arch": arch, "head": "t", "K": 1, "lr": 1e-3,
                    **REG["medium"], "_reg": "medium"})
    for arch in ("mlp", "conv"):
        for K in (1, 2, 3):
            for reg in ("small", "medium"):
                out.append({"variant": "a", "arch": arch, "head": "gmm", "K": K, "lr": 1e-3,
                            **REG[reg], "_reg": reg})
        out.append({"variant": "a", "arch": arch, "head": "gmm", "K": 2, "lr": 1e-3,
                    **REG["heavy"], "_reg": "heavy"})
    for arch in ("mlp", "conv"):
        out.append({"variant": "a", "arch": arch, "head": "t", "K": 1, "lr": 1e-3,
                    **REG["medium"], "_reg": "medium"})
    return out


def spec_of(d: dict[str, Any]) -> d1lib.ModelSpec:
    return d1lib.ModelSpec(**{k: v for k, v in d.items() if not k.startswith("_")})


def evaluate(
    spec: d1lib.ModelSpec, D: Any, seeds: list[int], device: str, tag: str
) -> dict[str, Any]:
    """Fit and score one configuration on the development folds."""
    cfg = d1lib.CFG
    ev = D.ev
    row: dict[str, Any] = {}
    frames = []
    for f in d1eval.dev_folds(D, cfg.val_days):
        y0 = f.origin.year
        fr = d1lib.fit_two_stage(spec, D.inp, f.train, f.val, seeds, device)
        pred = d1lib.predict_ensemble(fr, D.inp, f.score, device)
        sc = d1lib.score_rows(pred, ev["y"].to_numpy()[f.score], ev["U_pct"].to_numpy()[f.score])
        e = ev.iloc[f.score][["ticker", "entry_date", "announce_date", "year", "y", "rv",
                              "half_spread", d1data.L4_SCORE_MODEL,
                              d1data.L4_SCORE_BASE]].copy()
        for k, v in sc.items():
            e[k] = v
        e["fold"] = y0
        frames.append(e)
        ok = np.isfinite(e["log_score"]) & np.isfinite(e[d1data.L4_SCORE_MODEL])
        row[f"n_train_{y0}"] = int(f.train.size)
        row[f"n_val_{y0}"] = int(f.val.size)
        row[f"n_scored_{y0}"] = int(ok.sum())
        row[f"ls_{y0}"] = round(float(e.loc[ok, "log_score"].mean()), 5)
        row[f"gain_l4_{y0}"] = round(
            float((e.loc[ok, "log_score"] - e.loc[ok, d1data.L4_SCORE_MODEL]).mean()), 5
        )
        row[f"gain_base_{y0}"] = round(
            float((e.loc[ok, "log_score"] - e.loc[ok, d1data.L4_SCORE_BASE]).mean()), 5
        )
        row[f"best_epochs_{y0}"] = "|".join(str(x) for x in fr.best_epochs)
        row[f"val_nll_{y0}"] = round(float(np.mean(fr.val_nll)), 5)
        row["n_params"] = fr.nets[0].n_params()
    allp = pd.concat(frames, ignore_index=True)
    ok = np.isfinite(allp["log_score"]) & np.isfinite(allp[d1data.L4_SCORE_MODEL])
    row["n_scored"] = int(ok.sum())
    row["n_no_l4_score"] = int((~ok).sum())
    row["ls_pooled"] = round(float(allp.loc[ok, "log_score"].mean()), 5)
    row["gain_l4_pooled"] = round(
        float((allp.loc[ok, "log_score"] - allp.loc[ok, d1data.L4_SCORE_MODEL]).mean()), 5
    )
    row["gain_base_pooled"] = round(
        float((allp.loc[ok, "log_score"] - allp.loc[ok, d1data.L4_SCORE_BASE]).mean()), 5
    )
    sel = allp["decide"].to_numpy(bool) & np.isfinite(allp["y"].to_numpy())
    row["dev_n_selected"] = int(sel.sum())
    row["dev_sel_mean_H"] = round(float(allp.loc[sel, "y"].mean()), 4) if sel.any() else np.nan
    PRED_DIR.mkdir(exist_ok=True)
    allp.to_parquet(PRED_DIR / f"{tag}.parquet")
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--specs", type=str, default=None, help="JSON list of round-2 specs")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    specs = round1() if a.round == 1 else json.loads((HERE / a.specs).read_text())
    done_ids = set(pd.read_csv(LOG)["config_id"]) if LOG.exists() else set()
    n_done = len(done_ids)
    D = d1data.load("dev")
    print(f"[search] round {a.round}: {len(specs)} specs; {n_done} already logged; "
          f"device {a.device}; surfaces sha {D.surf_sha[:12]}")
    for i, d in enumerate(specs):
        tag = f"r{a.round}_{i:02d}"
        if tag in done_ids:
            print(f"[search] {tag} already logged; skipped")
            continue
        if n_done >= BUDGET:
            raise RuntimeError(f"search budget of {BUDGET} configurations reached")
        spec = spec_of(d)
        t0 = time.time()
        row = {"config_id": tag, "utc": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
               "spec": json.dumps(spec.to_dict()), "reg": d.get("_reg", ""),
               "eligible": spec.eligible}
        row.update(evaluate(spec, D, list(range(d1lib.CFG.n_search_seeds)), a.device, tag))
        row["seconds"] = round(time.time() - t0, 1)
        pd.DataFrame([row]).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
        n_done += 1
        print(f"[search] {tag} {spec.variant}/{spec.arch}/{spec.head}{spec.K} {row['reg']} "
              f"lr {spec.lr}: gain vs L4 {row['gain_l4_pooled']:+.4f} "
              f"(folds {row['gain_l4_2016']:+.4f} {row['gain_l4_2017']:+.4f} "
              f"{row['gain_l4_2018']:+.4f}), vs base {row['gain_base_pooled']:+.4f}, "
              f"N {row['n_scored']}, {row['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
