"""
score_heldout.py
Lane D1 frozen held-out scorer. Refuses to run unless ``freeze_D1.md`` verifies (its own
sha256 and those of this script, the model code, the frozen configuration and the development
search log). Walks forward over the block with a refit at every quarter start on events whose
expiry is before it (early stopping on the last 365 days of the window), as a 5-seed density
ensemble, and writes the per-event cards, the log-score comparison against L4 on ``H_net``, the
economic comparison of the declared rule (trade when the quadrature predictive mean of
``H_net`` is above zero) against the unconditional book, the tight-spread-per-date screen and
the matched random null, on ``H_net`` and on ``residual_value``, and channel occlusion.

Each (configuration, block) is read once: if its result file exists the script stops. 2019-24
is read first; 2025-26 (exploratory) only after the 2019-24 result exists.

Basis: log scores are nats per event, densities per unit of % of m0, Jacobian included; book
figures are means per trade in % of m0, net at the touch, not annualised; intervals are
date-clustered 95% on announcement dates.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D1-surface-net/score_heldout.py \
        --which primary --block 2019-24
"""

from __future__ import annotations

import argparse
import hashlib
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
FREEZE = HERE / "freeze_D1.md"
FROZEN = HERE / "frozen_config.json"
OUT = HERE / "heldout"
BLOCKS = {
    "2019-24": ("2019-01-01", "2025-01-01"),
    "2025-26": ("2025-01-01", "2026-10-01"),
}
#: Channel groups for occlusion, matched on D0's channel names (lower case substrings).
OCCLUSION_GROUPS = {"iv": ("iv",), "spread": ("spread", "spr"), "size": ("size", "sz")}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def frozen_files() -> dict[str, Path]:
    return {
        "scorer_sha256": Path(__file__).resolve(),
        "d1lib_sha256": HERE / "d1lib.py",
        "d1data_sha256": HERE / "d1data.py",
        "d1eval_sha256": HERE / "d1eval.py",
        "frozen_config_sha256": FROZEN,
        "search_log_sha256": HERE / "search_log.csv",
    }


def verify_freeze() -> dict[str, str]:
    raw = FREEZE.read_bytes()
    cut = raw.rfind(b"\nself_sha256: ")
    if cut < 0:
        raise ValueError("freeze note has no self_sha256 line")
    body, tail = raw[: cut + 1], raw[cut + 1 :].decode().strip()
    if hashlib.sha256(body).hexdigest() != tail.split(": ", 1)[1]:
        raise ValueError("freeze note changed after it was hashed")
    text = body.decode("utf-8")
    got: dict[str, str] = {}
    for name, path in frozen_files().items():
        line = [ln for ln in text.splitlines() if ln.startswith(f"{name}: ")]
        if len(line) != 1:
            raise ValueError(f"freeze note lacks {name}")
        want = line[0].split(": ", 1)[1].strip()
        if _sha(path) != want:
            raise ValueError(f"{path.name} does not match {name} in the freeze note")
        got[name] = want
    print(f"[freeze] verified {FREEZE.name} and {len(got)} hashed files")
    return got


def occlusion_channels(names: tuple[str, ...], mask_ch: int) -> dict[str, tuple[int, ...]]:
    out = {}
    for g, subs in OCCLUSION_GROUPS.items():
        idx = tuple(
            i
            for i, c in enumerate(names)
            if i != mask_ch and any(s in c.lower() for s in subs)
        )
        if not idx:
            raise ValueError(f"no channel matches occlusion group {g} in {names}")
        out[g] = idx
    flat = [i for v in out.values() for i in v]
    if len(flat) != len(set(flat)):
        raise ValueError(f"occlusion groups overlap: {out}")
    return out


# ── walk-forward ─────────────────────────────────────────────────────────────


def walk_forward(
    spec: d1lib.ModelSpec,
    D: Any,
    folds: list[d1eval.Fold],
    seeds: list[int],
    device: str,
    occl: dict[str, tuple[int, ...]],
    partial: Path | None = None,
) -> pd.DataFrame:
    """Per-event cards over the folds; refit per fold; occlusion predictions alongside."""
    ev = D.ev
    y_all = ev["y"].to_numpy()
    u_all = ev["U_pct"].to_numpy()
    frames = []
    for f in folds:
        t0 = time.time()
        if f.score.size == 0:
            print(f"[wf] {f.origin.date()}: no events to score")
            continue
        fr = d1lib.fit_two_stage(spec, D.inp, f.train, f.val, seeds, device)
        y, u = y_all[f.score], u_all[f.score]
        pred = d1lib.predict_ensemble(fr, D.inp, f.score, device)
        sc = d1lib.score_rows(pred, y, u)
        cols = ["ticker", "entry_date", "expiry", "announce_date", "block", "year", "y", "rv",
                "half_spread", "U_pct", d1data.L4_LOC, d1data.L4_SCALE, d1data.L4_SCORE_MODEL,
                d1data.L4_SCORE_BASE]
        e = ev.iloc[f.score][cols].copy()
        e["refit_date"] = f.origin
        e["n_train"] = f.train.size
        e["best_epochs"] = "|".join(str(x) for x in fr.best_epochs)
        for k, v in sc.items():
            e[k] = v
        for j, (n, r) in enumerate(zip(fr.nets, fr.nrms, strict=True)):
            pj = d1lib.predict(n, r, D.inp, f.score, device)
            e[f"log_score_seed{j}"] = d1lib.logscore_y(y, u, pj)
            if pj.eligible:
                e[f"mean_seed{j}"] = d1lib.predictive_moments(pj, u)["mean"]
        for g, chs in occl.items():
            po = d1lib.predict_ensemble(fr, D.inp, f.score, device, occlude=chs)
            so = d1lib.score_rows(po, y, u)
            e[f"log_score_occl_{g}"] = so["log_score"]
            e[f"decide_occl_{g}"] = so["decide"]
        frames.append(e)
        if partial is not None:
            pd.concat(frames, ignore_index=True).to_parquet(partial)
        print(f"[wf] refit {f.origin.date()}: train {f.train.size}, val {f.val.size}, scored "
              f"{f.score.size}, epochs {e['best_epochs'].iloc[0]}, decide "
              f"{int(sc['decide'].sum())}, {time.time() - t0:.1f} s", flush=True)
    return pd.concat(frames, ignore_index=True)


def summarise(cards: pd.DataFrame, spec: d1lib.ModelSpec, block: str) -> dict[str, Any]:
    """The log-score comparison, seed dispersion, occlusion and the economic comparison."""
    c = cards
    have = np.isfinite(c["y"]) & np.isfinite(c[d1data.L4_SCORE_MODEL])
    print(f"[funnel {block}] predicted {len(c)}; with outcome {int(np.isfinite(c['y']).sum())}; "
          f"with L4 model score {int(np.isfinite(c[d1data.L4_SCORE_MODEL]).sum())}; "
          f"compared {int(have.sum())}")
    s = c[have]
    cl = s["announce_date"].to_numpy()
    yr = s["year"].to_numpy()
    out: dict[str, Any] = {"block": block, "spec": spec.to_dict(), "N_predicted": len(c)}
    out["vs_L4_model"] = d1eval.log_score_gain(
        s["log_score"].to_numpy(), s[d1data.L4_SCORE_MODEL].to_numpy(), cl, yr
    )
    out["vs_L4_baseline"] = d1eval.log_score_gain(
        s["log_score"].to_numpy(), s[d1data.L4_SCORE_BASE].to_numpy(), cl, yr
    )
    out["L4_model_vs_baseline"] = d1eval.log_score_gain(
        s[d1data.L4_SCORE_MODEL].to_numpy(), s[d1data.L4_SCORE_BASE].to_numpy(), cl, yr
    )
    g = out["vs_L4_model"]
    out["forecaster_pass"] = bool(g["gain"]["low"] > 0 and g["years_positive"] >= 4)
    seed_cols = sorted(k for k in s.columns if k.startswith("log_score_seed"))
    per_seed = [float((s[k] - s[d1data.L4_SCORE_MODEL]).mean()) for k in seed_cols]
    out["seed_gain_vs_L4"] = {"per_seed": [round(v, 5) for v in per_seed],
                              "sd": round(float(np.std(per_seed, ddof=1)), 5)}
    out["occlusion_change_in_log_score"] = {
        k.replace("log_score_occl_", ""): d1eval._iv(
            d1eval.date_clustered_ci((s[k] - s["log_score"]).to_numpy(), cl, np.mean), 5
        )
        for k in s.columns
        if k.startswith("log_score_occl_")
    }
    pit = s["pit"].to_numpy()
    out["calibration"] = {
        "coverage_90": round(float(((pit >= 0.05) & (pit <= 0.95)).mean()), 4),
        "pit_below_0.05": round(float((pit < 0.05).mean()), 4),
        "pit_above_0.95": round(float((pit > 0.95).mean()), 4),
    }
    if spec.eligible:
        pool = np.isfinite(c["y"]).to_numpy() & np.isfinite(c["rv"]).to_numpy()
        p = c[pool]
        dec = p["decide"].to_numpy(bool)
        econ = {}
        for name, col in (("H_net", "y"), ("residual_value", "rv")):
            econ[name] = d1eval.book_comparison(
                p[col].to_numpy(), dec, p["half_spread"].to_numpy(),
                p["entry_date"].to_numpy(), p["announce_date"].to_numpy(),
            )
        econ["selected_without_outcome"] = int(
            (c["decide"].to_numpy(bool) & ~np.isfinite(c["y"].to_numpy())).sum()
        )
        for gname in ("iv", "spread", "size"):
            k = f"decide_occl_{gname}"
            if k in p.columns:
                econ[f"decisions_changed_by_occluding_{gname}"] = int(
                    (p[k].to_numpy(bool) != dec).sum()
                )
        econ["economic_pass"] = bool(econ["H_net"].get("pass") and
                                     econ["residual_value"].get("pass"))
        out["economic"] = econ
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", choices=["primary", "secondary", "control_primary", "control_secondary"], required=True)
    ap.add_argument("--block", choices=list(BLOCKS), required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    verify_freeze()
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    spec = d1lib.ModelSpec(**frozen[a.which]["spec"])
    seeds = list(frozen["seeds"])
    OUT.mkdir(exist_ok=True)
    tag = f"{a.which}_{a.block}"
    res_path = OUT / f"results_{tag}.json"
    if res_path.exists():
        raise SystemExit(f"{res_path.name} exists: this block was read once already")
    if a.block == "2025-26" and not (OUT / f"results_{a.which}_2019-24.json").exists():
        raise SystemExit("2025-26 is read only after the 2019-24 result exists")
    D = d1data.load("heldout", with_2025=(a.block == "2025-26"), viewer=f"D1 {a.which}")
    if D.surf_sha != frozen["surfaces_sha256"]:
        raise ValueError("the surface file differs from the one the search used")
    lo, hi = BLOCKS[a.block]
    folds = d1eval.quarter_folds(D, lo, hi, d1lib.CFG.val_days)
    occl = occlusion_channels(D.channel_names, D.inp.mask_ch)
    print(f"[heldout] {tag}: {len(folds)} quarterly refits, seeds {seeds}, spec {spec}")
    partial = OUT / f"cards_{tag}.partial.parquet"
    cards = walk_forward(spec, D, folds, seeds, a.device, occl, partial)
    cards = cards[cards["block"] == a.block].reset_index(drop=True)
    final = OUT / f"cards_{tag}.parquet"
    cards.to_parquet(final)
    partial.unlink(missing_ok=True)
    res = summarise(cards, spec, a.block)
    res["utc_finished"] = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    res_path.write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
