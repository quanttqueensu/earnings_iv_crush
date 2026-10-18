"""
research_ml_ratio_confirm2.py
Second, separately declared confirmation of the frozen ML ratio model on July-August 2026 events.

``research/selection/preregs/ml_ratio_confirm2_prereg.md``. Features come from the same Alpaca code path that built
the 2025-2026 features; outcomes from the cached 15:59 chains with zero-bid exit legs kept at
ask / 2, as in ``audit_oos_2026_attrition.py``. The model, threshold and features are frozen.

Usage:
    python research/selection/research_ml_ratio_confirm2.py --features
    python research/selection/research_ml_ratio_confirm2.py --score
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import research.frozen_selector.score_oos_2026 as led_mod  # noqa: E402
from earnings_iv_crush.data.real_events import build_execution_events  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from research.frozen_selector.audit_oos_2026_attrition import _parse_lenient  # noqa: E402
from research.selection.research_date_shift import shifts  # noqa: E402
from research.selection.research_ml_ratio import FEATURES, _derive  # noqa: E402
from scripts.build.build_broad_oos_2025 import _fetch_chain, _fetch_prices  # noqa: E402

PREREG = Path("research/selection/preregs/ml_ratio_confirm2_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_ml_ratio_confirm2.json")
LEDGER = Path("outputs/research/backfill_ledger.csv")
PRIOR = Path("outputs/research/events_broad_oos_2025.parquet")
MODEL = Path("outputs/research/ml_ratio/model.pkl")
FROZEN = Path("outputs/research/ml_ratio/frozen.json")
OUT = Path("outputs/research/ml_ratio_confirm2")
FEATS = OUT / "features.parquet"
N_BOOT = 5000
SEED = 0


def _check() -> None:
    pj = json.loads(PREREG_JSON.read_text())
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != pj["prereg_sha256"]:
        raise SystemExit("pre-registration hash mismatch")
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != pj["model_sha256"]:
        raise SystemExit("frozen model hash mismatch")


def features() -> None:
    _check()
    OUT.mkdir(parents=True, exist_ok=True)
    led = pd.read_csv(LEDGER, parse_dates=["announce_date", "entry_date", "exit_date"])
    cal = led[["ticker", "announce_date"]].copy()
    cal["session"] = np.where(led["entry_date"] == led["announce_date"], "amc", "bmo")
    parts = []
    for i, (t, sub) in enumerate(cal.groupby("ticker"), start=1):
        try:
            ev = build_execution_events(sub, fetch_chain=_fetch_chain, fetch_prices=_fetch_prices)
        except Exception as exc:  # noqa: BLE001
            print(f"  {t}: build failed ({type(exc).__name__})", flush=True)
            continue
        if not ev.empty:
            parts.append(ev)
        if i % 25 == 0:
            print(f"  {i} names, {sum(len(p) for p in parts)} events", flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(FEATS, index=False)
    print(f"  features built for {len(out)} of {len(cal)} events", flush=True)


def outcomes(ev: pd.DataFrame) -> pd.DataFrame:
    led = pd.read_csv(LEDGER, parse_dates=["announce_date", "entry_date", "exit_date"])
    rows, drops = [], {}
    for _, e in led.iterrows():
        t = str(e["ticker"])
        ch_in, ch_out = led_mod._cached(t, e["entry_date"]), led_mod._cached(t, e["exit_date"])
        s_in, s_out = float(e["spot_entry"]), float(e["spot_exit"])
        built = led_mod._straddle(ch_in, s_in) if ch_in is not None else None
        if built is None:
            drops["entry"] = drops.get("entry", 0) + 1
            continue
        straddle_in, implied_move, strike, expiry = built
        d = _parse_lenient(ch_out) if ch_out is not None else None
        leg = None if d is None else d[(d["strike"] == strike) & (d["expiry"] == expiry)]
        if leg is None or not {"C", "P"} <= set(leg["right"]):
            drops["exit"] = drops.get("exit", 0) + 1
            continue
        exit_v = float(
            leg[leg["right"] == "C"]["mid"].iloc[0] + leg[leg["right"] == "P"]["mid"].iloc[0]
        )
        credit = straddle_in * led_mod.CONTRACT_MULTIPLIER
        margin = led_mod.regt_straddle_margin(s_in, strike, straddle_in, 1)
        rows.append(
            {
                "ticker": t,
                "entry_date": e["entry_date"],
                "rom": (credit - exit_v * led_mod.CONTRACT_MULTIPLIER - led_mod.COST * credit)
                / margin,
                "y_mark": abs(s_out / s_in - 1.0) / implied_move,
            }
        )
    print(f"  outcome drops: {drops}", flush=True)
    return pd.DataFrame(rows)


def score() -> None:
    _check()
    frozen = json.loads(FROZEN.read_text())
    model = pickle.loads(MODEL.read_bytes())
    new = pd.read_parquet(FEATS)
    new["entry_date"] = pd.to_datetime(new["entry_date"])
    prior = pd.read_parquet(PRIOR)
    prior["entry_date"] = pd.to_datetime(prior["entry_date"])
    both = pd.concat([prior.assign(_new=False), new.assign(_new=True)], ignore_index=True)
    d = _derive(both, shifts())
    d = d[d["_new"]].reset_index(drop=True)
    d["pred"] = model.predict(d[FEATURES])
    d["sel"] = d["pred"] <= frozen["threshold"]
    o = outcomes(d)
    j = d.merge(o, on=["ticker", "entry_date"], how="inner")
    print(f"  events with features {len(d)}, with outcomes {len(j)}", flush=True)
    j.to_csv(OUT / "events.csv", index=False)
    keys = j["announce_date"].dt.strftime("%Y-%m-%d").to_numpy()
    rom, sel = j["rom"].to_numpy(), j["sel"].to_numpy()

    def diff(ix: np.ndarray) -> float:
        k = ix.astype(int)
        a, b = rom[k][sel[k]], rom[k][~sel[k]]
        return float(a.mean() - b.mean()) if len(a) and len(b) else float("nan")

    lo, hi = cluster_bootstrap_ci(
        np.arange(len(j), dtype=float), keys, diff, n_boot=N_BOOT, seed=SEED
    )
    yv = j["y"].to_numpy()
    rlo, rhi = cluster_bootstrap_ci(
        np.arange(len(j), dtype=float),
        keys,
        lambda ix: float(spearmanr(j["pred"].to_numpy()[ix.astype(int)], yv[ix.astype(int)])[0]),
        n_boot=N_BOOT,
        seed=SEED,
    )
    res: dict[str, Any] = {
        "n": len(j),
        "n_selected": int(sel.sum()),
        "selected_mean_rom": float(rom[sel].mean()),
        "unselected_mean_rom": float(rom[~sel].mean()),
        "difference": float(rom[sel].mean() - rom[~sel].mean()),
        "difference_ci": [float(lo), float(hi)],
        "spearman": float(spearmanr(j["pred"], yv)[0]),
        "spearman_ci": [float(rlo), float(rhi)],
    }
    res["pass"] = bool(lo > 0 and res["selected_mean_rom"] > 0)
    res["verdict"] = "PASS" if res["pass"] else "FAIL"
    print(json.dumps(res, indent=1))
    json.dump(res, open(OUT / "summary.json", "w"), indent=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--features", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.features:
        features()
    if a.score:
        score()


if __name__ == "__main__":
    main()
