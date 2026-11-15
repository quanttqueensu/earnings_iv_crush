"""
score_heldout.py
Lane D2 frozen held-out scorer. Refuses to run unless freeze_D2.md hashes itself correctly and
every file it names (this script, d2lib.py, d2net.py, frozen_config.json, search_log.csv) still
has the recorded sha256. Then it walks forward over the block with a refit at each quarter
start (train on expiry before the quarter start, early-stop on the last year of the window,
refit on the full window), fits the frozen Gaussian-mixture configuration and the frozen
Student-t secondary as 5-seed ensembles, and scores both against the L4 champion and baseline on
identical events. The frozen economic rule (trade when the quadrature mean of H_net is above 0)
is scored on H_net and residual_value against the unconditional book, the tight-spread-per-date
screen and the matched random null.

Blocks. ``--block 2019-24`` reads outcomes entered before 2025 only; ``--block 2025-26`` is the
exploratory read, allowed only after the 2019-24 output exists. Each block is read once: the
scorer refuses to overwrite an output already on disk. ``--synthetic`` runs the identical code
path on synthetic data (no real row, no hash check, nothing written beside the lane's files
except under synthetic_check/).

Basis. Log scores are nats per event, log density of H_net in % of m0. Book means are % of m0
per trade, net at the touch, not annualised. Intervals are date-clustered 95% (announce_date
clusters, 5,000 draws, seed 0).

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/score_heldout.py \
        --block 2019-24
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import d2lib  # noqa: E402
import d2net  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

FREEZE = HERE / "freeze_D2.md"
FROZEN = HERE / "frozen_config.json"
HASHED = ("score_heldout.py", "d2lib.py", "d2net.py", "frozen_config.json", "search_log.csv")
SELF_RE = re.compile(r"freeze_self_sha256: ([0-9a-f]{64})")
BLOCKS = {
    "2019-24": ("2019-01-01", "2025-01-01", pd.Timestamp("2025-01-01")),
    "2025-26": ("2025-01-01", "2026-10-01", None),
}
SYNTH = ("2017-01-01", "2019-01-01")


# ── freeze verification ──────────────────────────────────────────────────────


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_self_hash(text: str) -> str:
    """sha256 of the freeze note with its own hash replaced by 64 zeros."""
    return hashlib.sha256(SELF_RE.sub("freeze_self_sha256: " + "0" * 64, text).encode()).hexdigest()


def verify_freeze() -> dict[str, Any]:
    """Raise unless the freeze note's self-hash and every recorded file hash reproduce."""
    text = FREEZE.read_text(encoding="utf-8")
    m = SELF_RE.search(text)
    if not m or m.group(1) != freeze_self_hash(text):
        raise RuntimeError("freeze_D2.md does not hash to its recorded self-hash")
    block = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not block:
        raise RuntimeError("freeze_D2.md holds no hash block")
    rec = json.loads(block.group(1))
    for name in HASHED:
        got = sha(HERE / name)
        if rec["sha256"].get(name) != got:
            raise RuntimeError(f"{name} changed since the freeze: {got[:12]}")
    print(f"[freeze] verified: self {m.group(1)[:12]}; {', '.join(HASHED)}")
    return rec


# ── fitting ──────────────────────────────────────────────────────────────────

_EV: pd.DataFrame | None = None


def _init(path: str) -> None:
    global _EV
    _EV = pd.read_pickle(path)


def _fit_quarter(args: tuple[d2lib.Fold, dict[str, Any], tuple[int, ...]]) -> pd.DataFrame:
    fold, cfgd, seeds = args
    assert _EV is not None
    cfg = d2net.Config(
        **{**cfgd, "hidden": tuple(cfgd["hidden"]), "drop_inputs": tuple(cfgd["drop_inputs"])}
    )
    out, info = d2net.run(_EV, [fold], cfg, seeds)
    out["epochs"] = json.dumps(info[0]["epochs"])
    out["n_train_full"] = info[0]["n_full"]
    return out


def walk_forward(
    ev: pd.DataFrame, folds: list[d2lib.Fold], cfgd: dict[str, Any], seeds: tuple[int, ...],
    workers: int, tmp: Path,
) -> pd.DataFrame:  # fmt: skip
    ev.to_pickle(tmp)
    try:
        with ProcessPoolExecutor(workers, initializer=_init, initargs=(str(tmp),)) as ex:
            parts = list(ex.map(_fit_quarter, [(f, cfgd, seeds) for f in folds]))
    finally:
        tmp.unlink()
    return pd.concat(parts, ignore_index=True)


# ── scoring ──────────────────────────────────────────────────────────────────


def _ci(v: np.ndarray, keys: np.ndarray) -> dict[str, Any]:
    c = date_clustered_ci(v, keys, np.mean)
    return {"mean": round(c.point, 5), "ci": [round(c.low, 5), round(c.high, 5)], "N": c.n,
            "clusters": c.clusters}  # fmt: skip


def forecaster(ev: pd.DataFrame, gm: pd.DataFrame, tt: pd.DataFrame, seeds: tuple[int, ...]):
    """Log-score comparisons on identical events (both D2 heads, L4 champion and baseline)."""
    rows = gm["row"].to_numpy()
    if not (tt["row"].to_numpy() == rows).all():
        raise AssertionError("the two heads predicted different events")
    sc = d2lib.scored_set(ev, rows, gm["d2_log_score"].to_numpy())
    sc &= np.isfinite(tt["d2_log_score"].to_numpy())
    e = ev.iloc[rows[sc]]
    keys = e["announce_date"].to_numpy()
    d2 = gm["d2_log_score"].to_numpy()[sc]
    t2 = tt["d2_log_score"].to_numpy()[sc]
    l4m = e["l4_model_log_score"].to_numpy(float)
    l4b = e["l4_base_log_score"].to_numpy(float)
    yr = e["year"].to_numpy()
    res: dict[str, Any] = {"N_scored": int(sc.sum()), "N_predicted": int(rows.size)}
    res["levels"] = {k: round(float(v.mean()), 5) for k, v in
                     (("d2_gm", d2), ("d2_t", t2), ("l4_model", l4m), ("l4_base", l4b))}  # fmt: skip
    res["gm_minus_l4_model"] = _ci(d2 - l4m, keys)
    res["gm_minus_l4_base"] = _ci(d2 - l4b, keys)
    res["t_minus_l4_model"] = _ci(t2 - l4m, keys)
    res["l4_model_minus_base"] = _ci(l4m - l4b, keys)
    res["gm_minus_t"] = _ci(d2 - t2, keys)
    by: dict[str, Any] = {}
    for y in np.unique(yr):
        m = yr == y
        by[str(y)] = {"gm_minus_l4": _ci((d2 - l4m)[m], keys[m]),
                      "t_minus_l4": round(float((t2 - l4m)[m].mean()), 5)}  # fmt: skip
    res["by_year"] = by
    res["years_positive_gm"] = int(sum(v["gm_minus_l4"]["mean"] > 0 for v in by.values()))
    res["n_years"] = len(by)
    seed_gain = [float((gm[f"seed{s}_log_score"].to_numpy()[sc] - l4m).mean()) for s in seeds]
    res["seed_gm_minus_l4"] = [round(g, 5) for g in seed_gain]
    res["seed_sd"] = round(float(np.std(seed_gain, ddof=1)), 5)
    # Staleness: D2 refits at quarter starts, L4 after every expiry. Gain by month of quarter.
    mq = ((e["entry_date"].dt.month.to_numpy() - 1) % 3) + 1
    res["gm_minus_l4_by_month_of_quarter"] = {
        str(k): _ci((d2 - l4m)[mq == k], keys[mq == k]) for k in (1, 2, 3)
    }
    res["occlusion_change_vs_full"] = {
        c[4:-10]: _ci(gm[c].to_numpy()[sc] - d2, keys)
        for c in gm.columns
        if c.startswith("occ_") and c.endswith("_log_score")
    }
    e_all = ev.iloc[rows]
    res["funnel"] = {
        "predicted (inputs defined, entered in block)": int(rows.size),
        "with H_net": int(np.isfinite(e_all["h"].to_numpy(float)).sum()),
        "and L4 champion and baseline scored": int(
            (np.isfinite(e_all["h"].to_numpy(float)) & e_all["m_scored"].eq(True).to_numpy()
             & e_all["b_scored"].eq(True).to_numpy()).sum()
        ),  # fmt: skip
        "scored by every model (identical events)": int(sc.sum()),
    }
    return res, sc


def economics(ev: pd.DataFrame, gm: pd.DataFrame, sc: np.ndarray) -> dict[str, Any]:
    """The frozen rule (quadrature mean of H_net above 0) on the scored events."""
    rows = gm["row"].to_numpy()[sc]
    e = ev.iloc[rows]
    keys = e["announce_date"].to_numpy()
    sel = gm["pred_mean"].to_numpy()[sc] > 0
    tight = d2lib.tight_per_date(
        sel, e["half_spread"].to_numpy(float), e["entry_date"].to_numpy(), e["ticker"].to_numpy()
    )
    res: dict[str, Any] = {"rule": "trade if quadrature E[H_net] > 0", "n_pool": int(sc.sum())}
    res["H_net"] = d2lib.book(e["h"].to_numpy(float), sel, tight, keys, "H_net")
    res["residual_value"] = d2lib.book(e["rv"].to_numpy(float), sel, tight, keys, "rv")
    for k in ("H_net", "residual_value"):
        r = res[k]
        r["economic_pass"] = bool(r.get("beats_tight", False) and r.get("beats_null", False))
    res["pred_mean_quantiles"] = [round(float(q), 4) for q in
                                  np.quantile(gm["pred_mean"].to_numpy()[sc],
                                              [0.05, 0.25, 0.5, 0.75, 0.95])]  # fmt: skip
    res["selected_by_year"] = {
        str(y): int(sel[e["year"].to_numpy() == y].sum()) for y in np.unique(e["year"])
    }
    return res


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--block", choices=tuple(BLOCKS), default="2019-24")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    seeds = tuple(frozen["seeds"])
    if a.synthetic:
        outdir = HERE / "synthetic_check"
        outdir.mkdir(exist_ok=True)
        ev = d2lib.synthetic(n=4000, seed=5)
        folds = d2lib.quarterly_folds(*SYNTH)
        tag = "SYNTHETIC"
    else:
        verify_freeze()
        outdir = HERE
        if (HERE / f"heldout_{a.block}.json").exists():
            raise FileExistsError(f"the {a.block} read is already on disk; it is never repeated")
        if a.block == "2025-26" and not (HERE / "heldout_2019-24.json").exists():
            raise RuntimeError("2025-26 is read only after the 2019-24 read")
        lo, hi, max_entry = BLOCKS[a.block]
        ev = d2lib.load_real(heldout=True, note=f"score_heldout {a.block} (frozen)",
                             block=a.block, max_entry=max_entry)  # fmt: skip
        folds = d2lib.quarterly_folds(lo, hi)
        tag = a.block
    t0 = datetime.now(timezone.utc)
    print(f"[heldout {tag}] {len(folds)} quarterly refits x {len(seeds)} seeds, two heads")
    tmp = outdir / f"_frame_{tag}.pkl"
    gm = walk_forward(ev, folds, frozen["primary"], seeds, a.workers, tmp)
    tt = walk_forward(ev, folds, frozen["secondary_t"], seeds, a.workers, tmp)
    fc, sc = forecaster(ev, gm, tt, seeds)
    ec = economics(ev, gm, sc)
    res = {
        "label": tag if a.synthetic else f"{tag} REAL, exploratory (block viewed before by L4)",
        "started_utc": t0.isoformat(timespec="seconds"),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "folds": [f.label for f in folds],
        "staleness": "D2 refits at each quarter start; L4 updates after every expiry",
        "forecaster": fc,
        "economics": ec,
    }
    rows = gm["row"].to_numpy()
    cards = ev.iloc[rows][["ticker", "entry_date", "announce_date", "year", "half_spread",
                           "h", "rv", "U", "l4_model_log_score", "l4_base_log_score"]]  # fmt: skip
    cards = cards.reset_index(drop=True)
    for c in ("fold", "d2_log_score", "pred_mean", "pred_sd", "p_pos", "epochs", "n_train_full"):
        cards[c] = gm[c].to_numpy()
    for s in seeds:
        cards[f"seed{s}_log_score"] = gm[f"seed{s}_log_score"].to_numpy()
    for c in gm.columns:
        if c.startswith("occ_"):
            cards[c] = gm[c].to_numpy()
    cards["t_log_score"] = tt["d2_log_score"].to_numpy()
    cards["scored"] = sc
    cards["decide"] = sc & (cards["pred_mean"].to_numpy() > 0)
    cards.to_parquet(outdir / f"heldout_{tag}_events.parquet")
    (outdir / f"heldout_{tag}.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
