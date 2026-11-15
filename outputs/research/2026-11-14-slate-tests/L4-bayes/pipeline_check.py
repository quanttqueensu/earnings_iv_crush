"""
pipeline_check.py
Stage-1 pipeline check for lane L4: builds the declared features on the real 15:59 panel, joins
the base event panel's keys and timestamps, and runs the sequential model on SYNTHETIC outcomes
planted on the real features, dates and names. No outcome column is read.

Columns read: keys, timestamps and the RAW_COLUMNS of ``online_bayes`` from the lane E panel;
keys, ``expiry`` and ``src`` from the base event panel. Nothing else.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/pipeline_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research import online_bayes as ob  # noqa: E402

PANEL = ROOT / "outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/panel.parquet"
EVENTS = ROOT / "outputs/research/2026-11-02-parity-leg-choice/events.parquet"
KEYS = ["ticker", "entry_date"]
PLANT = (-0.5, 1.0, -0.5)  # synthetic intercept and two feature effects, in residual-sd units
SEED = 0


def main() -> None:
    cols = KEYS + ["expiry", "announce_date"] + [c for c in ob.RAW_COLUMNS if c != "ticker"]
    p = pd.read_parquet(PANEL, columns=cols)
    e = pd.read_parquet(EVENTS, columns=KEYS + ["expiry", "src"])
    d = p.merge(e, on=KEYS, how="left", validate="one_to_one", indicator=True, suffixes=("", "_e"))
    print(f"[join] panel {len(p)}, events {len(e)}, matched {int((d['_merge'] == 'both').sum())}")
    if (d["_merge"] != "both").any():
        raise ValueError("panel rows without a base event")
    if not (d["expiry"] == d["expiry_e"]).all():
        raise ValueError("expiry disagrees between panels")
    d = d.sort_values(KEYS, kind="stable").reset_index(drop=True)
    raw = ob.build_features(d)
    z, n_prior = ob.causal_standardise(raw[list(ob.FEATURES)], d["entry_date"], 200)
    v = ob.causal_variance_weight(
        raw["premium_share"].to_numpy(), d["entry_date"], "premium_share", 200
    )
    ok = z.notna().all(axis=1)
    print(
        f"[standardise] usable {int(ok.sum())} of {len(d)}; first usable entry "
        f"{d.loc[ok, 'entry_date'].min().date()}"
    )
    print("[standardise] causal z, mean and sd over usable rows (features only):")
    print(z[ok].agg(["mean", "std"]).T.round(3).to_string())
    X = np.column_stack([np.ones(len(d)), z.to_numpy(float)])
    rng = np.random.default_rng(SEED)
    mean = PLANT[0] + PLANT[1] * X[:, 1] + PLANT[2] * X[:, 2]
    noise = np.sqrt(np.where(np.isfinite(v), v, 1.0)) * rng.standard_normal(len(d))
    frame = pd.DataFrame(
        {
            "entry_date": d["entry_date"],
            "settle_date": d["expiry"],
            "name": d["ticker"],
            "cluster": d["announce_date"],
            "y": mean + noise,
            "v": v,
        }
    )
    cfg = ob.OnlineBayesConfig(prior_sigma=1.0)
    names = ["intercept", *ob.FEATURES]
    run = ob.run_online(frame, X, cfg, coef_names=names)
    loc = run.state.m[: len(names)]
    sd = np.sqrt(run.state.b / run.state.a * np.diag(run.state.C)[: len(names)])
    print("[synthetic] final posterior, planted (-0.5, +1.0, -0.5, 0, ...):")
    for k, nm in enumerate(names):
        print(f"    {nm:24s} {loc[k]:+.3f} (sd {sd[k]:.3f})")
    g = run.gauge
    print(
        f"[synthetic] gauge rows {len(g)}; last P(mean > 0) raw {g['p_mean_pos'].iloc[-1]:.3f}, "
        f"with design effect {g['p_mean_pos_deff'].iloc[-1]:.3f} (deff {g['deff'].iloc[-1]:.2f})"
    )
    s = run.events["scored"]
    print(
        f"[synthetic] scored {int(s.sum())}; 90% coverage {run.events.loc[s, 'covered'].mean():.3f}; "
        f"PIT {ob.pit_histogram(run.events.loc[s, 'pit'].to_numpy(), 10)['counts']}"
    )
    print("SYNTHETIC OUTCOMES ONLY: no real outcome was read.")


if __name__ == "__main__":
    main()
