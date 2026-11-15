"""
explore_gain.py
Lane D1, exploratory and descriptive, chosen after the 2019-24 read: where the frozen
network's log-score gain against L4 sits. Reads the held-out cards written once by
``score_heldout.py``; fits nothing. For each event it rebuilds the Gaussian version of L4 (L4's
z location and scale) and compares its quadrature mean and sd of H_net with the network's, then
reports the gain against L4 by tercile of the sd ratio, the premium share and the tenor, and
the gain of the Gaussian L4 itself against L4 (the head-shape part alone).

Basis: nats per event, H_net space; means and sds in % of m0 per trade. Date-clustered 95%.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D1-surface-net/explore_gain.py primary
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import d1lib
import numpy as np
import pandas as pd

from earnings_iv_crush.research.protocol import date_clustered_ci, log_block_view

HERE = Path(__file__).resolve().parent


def main(which: str, block: str = "2019-24") -> None:
    p = HERE / "heldout" / f"cards_{which}_{block}.parquet"
    c = pd.read_parquet(p)
    stamp = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    log_block_view(
        HERE / "blocks_viewed.csv",
        panel="D1 held-out cards",
        period=block,
        outcome_family="H_net_log_density_and_book",
        feature_family="dl_surface_network",
        viewed_by=f"D1 explore_gain {which} (loaded {stamp})",
        kind="descriptive",
    )
    n = len(c)
    g = d1lib.Predictive(
        np.ones((n, 1)), c[["m_pred_loc"]].to_numpy(), c[["m_pred_scale"]].to_numpy()
    )
    y, u = c["y"].to_numpy(), c["U_pct"].to_numpy()
    mg = d1lib.predictive_moments(g, u)
    lsg = d1lib.logscore_y(y, u, g)
    cl = c["announce_date"].to_numpy()
    gain = c["log_score"].to_numpy() - c["m_log_score"].to_numpy()
    out = {"label": "EXPLORATORY: chosen after the held-out read", "N": n}

    def iv(v: np.ndarray, k: np.ndarray = cl) -> list[float]:
        r = date_clustered_ci(v, k, np.mean)
        return [round(r.point, 4), round(r.low, 4), round(r.high, 4)]

    out["gaussian_L4_minus_L4"] = iv(lsg - c["m_log_score"].to_numpy())
    out["network_minus_gaussian_L4"] = iv(c["log_score"].to_numpy() - lsg)
    ratio = np.log(c["sd"].to_numpy() / mg["sd"])
    out["log_sd_ratio_network_over_gaussian_L4"] = {
        "mean": round(float(ratio.mean()), 4),
        "sd": round(float(ratio.std()), 4),
    }
    out["mean_shift_network_minus_gaussian_L4_pct"] = {
        "mean": round(float((c["mean"] - mg["mean"]).mean()), 3),
        "sd": round(float((c["mean"] - mg["mean"]).std()), 3),
    }
    for name, v in (("sd_ratio", ratio), ("premium_pct_m0", u), ("tau_front_days", None)):
        if v is None:
            continue
        q = pd.qcut(v, 3, labels=False)
        out[f"gain_by_tercile_{name}"] = {int(k): iv(gain[q == k], cl[q == k]) for k in range(3)}
    print(json.dumps(out, indent=1))
    (HERE / f"explore_gain_{which}_{block}.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
