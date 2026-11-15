"""
search.py
Lane D2 development search: each configuration of the declared grid (diagnosis.log entry [1],
stage 1; stage 2 configurations are declared in a later entry before they run) is fitted with
2 seeds on the 2016, 2017 and 2018 rolling-origin folds and scored against the L4 champion and
baseline on identical events. One row per configuration is appended to search_log.csv as it
finishes, with its fold scores; per-event outputs go to search/<config_id>.parquet.

Only rows entered before 2019 are read (d2lib.load_real(heldout=False)). Real data.

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/search.py --stage 1
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import d2lib  # noqa: E402
import d2net  # noqa: E402
import pandas as pd  # noqa: E402

SEARCH_SEEDS = (0, 1)
LOG = HERE / "search_log.csv"
OUT = HERE / "search"
BUDGET = 24
WEAK = {"weight_decay": 1e-4, "dropout": 0.0}
STRONG = {"weight_decay": 1e-2, "dropout": 0.2}


def stage1() -> list[tuple[str, d2net.Config]]:
    out: list[tuple[str, d2net.Config]] = []
    i = 1
    for K in (1, 2, 3):
        for hid in ((16,), (32, 32)):
            for rname, reg in (("weak", WEAK), ("strong", STRONG)):
                nm = f"gm{K}_{'x'.join(map(str, hid))}_{rname}"
                out.append((f"c{i:02d}", d2net.Config(head="gm", K=K, hidden=hid, name=nm, **reg)))
                i += 1
    for hid in ((16,), (32, 32)):
        for rname, reg in (("weak", WEAK), ("strong", STRONG)):
            nm = f"t_{'x'.join(map(str, hid))}_{rname}"
            out.append((f"c{i:02d}", d2net.Config(head="t", K=1, hidden=hid, name=nm, **reg)))
            i += 1
    return out


def stage2() -> list[tuple[str, d2net.Config]]:
    path = HERE / "stage2_configs.json"
    if not path.exists():
        raise FileNotFoundError("stage2_configs.json is written (and declared) before stage 2")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        (
            r["config_id"],
            d2net.Config(
                **{
                    **r["config"],
                    "hidden": tuple(r["config"]["hidden"]),
                    "drop_inputs": tuple(r["config"].get("drop_inputs", ())),
                }
            ),
        )
        for r in rows
    ]


_EV: pd.DataFrame | None = None
VERIFY = False


def _init(verify: bool) -> None:
    global _EV, VERIFY
    _EV = pd.read_pickle(HERE / "search" / "_dev_frame.pkl")
    VERIFY = verify


def score_config(cid: str, cfg: d2net.Config) -> dict[str, Any]:
    """Fit and score one configuration on the three development folds."""
    assert _EV is not None
    ev = _EV
    out, info = d2net.run(ev, d2lib.dev_folds(), cfg, SEARCH_SEEDS)
    rows = out["row"].to_numpy()
    sc = d2lib.scored_set(ev, rows, out["d2_log_score"].to_numpy())
    out["scored"] = sc
    out["l4_model_log_score"] = ev["l4_model_log_score"].to_numpy()[rows]
    out["l4_base_log_score"] = ev["l4_base_log_score"].to_numpy()[rows]
    keep = [c for c in out.columns if not c.startswith("mix_")]
    if not VERIFY:
        out[keep].assign(ticker=ev["ticker"].to_numpy()[rows],
                         entry_date=ev["entry_date"].to_numpy()[rows]).to_parquet(
            OUT / f"{cid}.parquet")  # fmt: skip
    rec: dict[str, Any] = {"config_id": cid, "name": cfg.name, **cfg.as_dict()}
    rec["hidden"] = "x".join(map(str, cfg.hidden))
    s = out[sc]
    for f in d2lib.dev_folds():
        g = s[s["fold"] == f.label]
        rec[f"n_{f.label}"] = len(g)
        rec[f"d2_{f.label}"] = round(float(g["d2_log_score"].mean()), 5)
        rec[f"gain_vs_l4_{f.label}"] = round(
            float((g["d2_log_score"] - g["l4_model_log_score"]).mean()), 5
        )
    rec["n_pooled"] = len(s)
    rec["d2_pooled"] = round(float(s["d2_log_score"].mean()), 5)
    rec["l4_model_pooled"] = round(float(s["l4_model_log_score"].mean()), 5)
    rec["l4_base_pooled"] = round(float(s["l4_base_log_score"].mean()), 5)
    rec["gain_vs_l4_pooled"] = round(rec["d2_pooled"] - rec["l4_model_pooled"], 5)
    rec["gain_vs_l4_base_pooled"] = round(rec["d2_pooled"] - rec["l4_base_pooled"], 5)
    for sd in SEARCH_SEEDS:
        rec[f"seed{sd}_pooled"] = round(float(s[f"seed{sd}_log_score"].mean()), 5)
    rec["epochs"] = json.dumps([i["epochs"] for i in info])
    rec["n_train_full"] = json.dumps([i["n_full"] for i in info])
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--verify", action="store_true", help="re-run into search_log_verify.csv")
    a = ap.parse_args(argv)
    global LOG
    if a.verify:
        LOG = HERE / "search_log_verify.csv"
    cfgs = stage1() if a.stage == 1 else stage2()
    done = set(pd.read_csv(LOG)["config_id"]) if LOG.exists() else set()
    n_prior = len(done)
    todo = [(c, g) for c, g in cfgs if c not in done]
    if n_prior + len(todo) > BUDGET:
        raise ValueError(f"search budget {BUDGET} exceeded: {n_prior} done + {len(todo)} new")
    OUT.mkdir(exist_ok=True)
    ev = d2lib.load_real(heldout=False, note=f"search stage {a.stage} (rolling origin 2016-18)")
    ev.to_pickle(OUT / "_dev_frame.pkl")
    print(f"[search] stage {a.stage}: {len(todo)} configurations to run, {n_prior} logged")
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.verify,)) as ex:
        futs = {ex.submit(score_config, c, g): c for c, g in todo}
        for fu in as_completed(futs):
            rec = fu.result()
            rec = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "stage": a.stage, **rec}  # fmt: skip
            pd.DataFrame([rec]).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
            print(
                f"[search] {rec['config_id']} {rec['name']}: pooled {rec['d2_pooled']:+.4f} "
                f"vs L4 {rec['l4_model_pooled']:+.4f} (gain {rec['gain_vs_l4_pooled']:+.4f}); "
                f"folds {[rec[f'gain_vs_l4_{y}'] for y in d2lib.DEV_YEARS]}",
                flush=True,
            )
    (OUT / "_dev_frame.pkl").unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
