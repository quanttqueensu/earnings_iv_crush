"""
corrections.py
Corrections to the 2026-11-12 move-forecast and sizing study. Not a trial.

Three things, all recorded so every figure in ``findings.md`` traces to a file:

1. Part A as frozen. ``study.py`` fitted M0 on every training event; ``prereg.md`` says both
   models are fitted and scored on the same events. M0 is refitted on the common sample.
2. Attribution of the Part A gain, requested by the post-run review: the term-structure event
   share (option information) against the non-price inputs. Descriptive, labelled as such.
3. The descriptive figures quoted in the first findings draft without a logged source (per-event
   means, price-quintile and busy-day splits).

Usage
-----
    python research/selection/2026-11-12-move-forecast-and-sizing/corrections.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import study as s  # noqa: E402

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

OUT = s.OUT / "corrections.json"
NON_PRICE = [c for c in s.M1_COLS if c not in ("log_im", "jump_share")]
VARIANTS = {
    "M1_as_frozen": s.M1_COLS,
    "im_plus_jump_share": ["log_im", "jump_share"],
    "M1_without_jump_share": ["log_im"] + NON_PRICE,
}


def walk_forward_common(ev: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Out-of-sample predictions from the given inputs, fitted on the M1-defined sample only."""
    pred = pd.Series(np.nan, index=ev.index)
    full = ev["m1_defined"]
    for yr in range(s.FIRST_OOS_YEAR, int(ev["year"].max()) + 1):
        tr = (ev["exit_date"] < pd.Timestamp(f"{yr}-01-01")) & full
        te = (ev["year"] == yr) & full
        b = s._ols(ev.loc[tr, cols].to_numpy(), ev.loc[tr, "y"].to_numpy())
        pred[te] = s._pred(b, ev.loc[te, cols].to_numpy())
    return pred


def main() -> None:
    ev = s.add_history(s.attach_chars(s.load_events()))
    ev, _ = s.walk_forward(ev)  # sets m1_defined exactly as the scorer did
    m0 = walk_forward_common(ev, ["log_im"])
    out: dict[str, object] = {"label": "correction and descriptive attribution, not a trial"}
    part_a: dict[str, object] = {}
    for name, (lo, hi) in s.A_BLOCKS.items():
        b = (ev["year"] >= lo) & (ev["year"] <= hi) & ev["m1_defined"] & m0.notna()
        e0 = (ev.loc[b, "y"] - m0[b]) ** 2
        blk: dict[str, object] = {"n": int(b.sum())}
        for vname, cols in VARIANTS.items():
            pv = walk_forward_common(ev, cols)
            gain = date_clustered_ci(
                (e0 - (ev.loc[b, "y"] - pv[b]) ** 2).to_numpy(), ev.loc[b, "entry_date"], np.mean
            )
            blk[vname] = [gain.point, gain.low, gain.high]
            print(f"A {name} {vname:24s} MSE gain over common-sample M0 {gain}")
        part_a[name] = blk
    out["part_a_common_sample_m0"] = part_a

    d = ev[(ev["year"] >= 2016) & (ev["year"] <= 2024)].copy()
    d["price_q"] = pd.qcut(d["front_fwd"], 5, labels=False)
    n_date = d.groupby("entry_date")["ticker"].transform("size")
    d["busy_q"] = pd.qcut(n_date.rank(method="first"), 4, labels=False)
    desc: dict[str, object] = {}
    for basis in ("r_meas", "r_touch"):
        m = date_clustered_ci(d[basis].to_numpy(), d["entry_date"], np.mean)
        desc[basis] = {
            "per_event_mean": [m.point, m.low, m.high, m.n, m.clusters],
            "by_price_quintile": d.groupby("price_q")[basis].mean().round(5).tolist(),
            "by_busy_quartile": d.groupby("busy_q")[basis].mean().round(5).tolist(),
        }
        print(f"descriptive 2016-24 {basis}: mean {m}")
    desc["busy_quartile_events_per_date"] = (
        n_date.groupby(d["busy_q"]).agg(["min", "max"]).to_numpy().tolist()
    )
    out["descriptive_2016_2024"] = desc
    OUT.write_text(json.dumps(out, indent=2, default=float))
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
