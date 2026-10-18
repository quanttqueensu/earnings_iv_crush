"""
validate_pead_car_harness.py
Does the conditioner study's CAR harness reproduce PEAD where PEAD is known to live?

The conditioner run found no drift in the 311 option-covered names. That has two possible
causes and they demand opposite conclusions:

  a) the harness is wrong, and the null is an artefact;
  b) the harness is right, and drift is genuinely absent in large, heavily-optioned names.

This script settles it by running the SAME CAR construction on the SAME calendar window
(2019-2024) over the FULL CRSP universe rather than the option-covered subset. If
sue_sigma sorts drift there and not in the option names, the harness is sound and the
subset is the finding. If it sorts nowhere, the harness is the problem.

Usage:
    python research/off_earnings/validate_pead_car_harness.py [--sample N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OUT = Path("outputs/research")
K = 60
ENTRY_LAG = 1
N_BINS = 3
SEED = 0


def car_for(events: pd.DataFrame) -> pd.DataFrame:
    """Identical construction to research_pead_iv_conditioners._forward_car."""
    want = set(events["permno"].astype(int))
    lo = int(events["day0_ordinal"].min())
    hi = int(events["day0_ordinal"].max()) + K + 5
    f = pq.ParquetFile(OUT / "panel_daily.parquet")
    parts = []
    for i in range(f.metadata.num_row_groups):
        g = f.read_row_group(i, columns=["permno", "ordinal", "ret_adj", "mktrf"]).to_pandas()
        g = g[g["permno"].isin(want) & g["ordinal"].between(lo, hi)]
        if len(g):
            parts.append(g)
    daily = pd.concat(parts, ignore_index=True).dropna(subset=["ordinal"])
    daily = daily.sort_values(["permno", "ordinal"])
    daily["ex"] = daily["ret_adj"] - daily["mktrf"].fillna(0.0)
    lut = {
        int(p): (g["ordinal"].to_numpy(), g["ex"].to_numpy()) for p, g in daily.groupby("permno")
    }

    cars = []
    for permno, d0 in zip(events["permno"], events["day0_ordinal"], strict=False):
        pair = lut.get(int(permno))
        if pair is None:
            cars.append(np.nan)
            continue
        o, x = pair
        a = int(d0) + ENTRY_LAG
        v = x[(o >= a) & (o < a + K)]
        v = v[np.isfinite(v)]
        cars.append(float(np.prod(1.0 + v) - 1.0) if len(v) >= K * 0.6 else np.nan)
    out = events.copy()
    out["car_fwd"] = cars
    return out


def spread(df: pd.DataFrame, col: str) -> dict:
    d = df.dropna(subset=[col, "car_fwd"]).copy()
    q = d["anndats"].dt.to_period("Q")
    d["bin"] = d.groupby(q)[col].transform(
        lambda s: (
            pd.qcut(s, N_BINS, labels=False, duplicates="drop") if s.notna().sum() >= 15 else np.nan
        )
    )
    d = d.dropna(subset=["bin"])
    top = d[d["bin"] == d["bin"].max()]["car_fwd"].to_numpy()
    bot = d[d["bin"] == d["bin"].min()]["car_fwd"].to_numpy()
    t = stats.ttest_ind(top, bot, equal_var=False)
    return {
        "n": len(d),
        "n_top": len(top),
        "n_bot": len(bot),
        "mean_top": top.mean(),
        "mean_bot": bot.mean(),
        "spread": top.mean() - bot.mean(),
        "t": t.statistic,
        "p": t.pvalue,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sample", type=int, default=12000, help="events to draw from the full universe"
    )
    args = ap.parse_args()

    ev = pd.read_parquet(OUT / "panel_events.parquet")
    ev["anndats"] = pd.to_datetime(ev["anndats"])
    ev = ev[(ev["anndats"] >= "2019-01-01") & (ev["anndats"] <= "2024-10-02")].copy()
    ev = ev[(ev["stdev"] > 0) & ev["actual"].notna() & ev["meanest"].notna()]
    ev["sue_sigma"] = (ev["actual"] - ev["meanest"]) / ev["stdev"]
    print(f"full-universe firm-quarters 2019-2024: {len(ev)}  permnos {ev['permno'].nunique()}")

    if len(ev) > args.sample:
        ev = ev.sample(args.sample, random_state=SEED).sort_values("day0_ordinal")
        print(f"  sampled {len(ev)} for tractability")

    print("computing CARs on the full universe...")
    ev = car_for(ev)
    ev = ev.dropna(subset=["car_fwd"])
    print(f"  usable: {len(ev)}")

    full = spread(ev, "sue_sigma")
    print()
    print("FULL UNIVERSE, same window, same harness:")
    for k, v in full.items():
        print(f"  {k:10s} {v:+.5f}" if isinstance(v, float) else f"  {k:10s} {v}")

    # split by whether the name is in the option-covered universe
    merged = pd.read_parquet(OUT / "pead_iv_merged.parquet")
    opt_permnos = set(merged["permno"].astype(int))
    inopt = ev[ev["permno"].astype(int).isin(opt_permnos)]
    outopt = ev[~ev["permno"].astype(int).isin(opt_permnos)]
    print()
    for lab, sub in [("option-covered names", inopt), ("NON option-covered names", outopt)]:
        if len(sub) < 100:
            print(f"{lab}: only {len(sub)} events, skipped")
            continue
        s = spread(sub, "sue_sigma")
        print(
            f"{lab:26s} n={s['n']:6d}  spread={s['spread']:+.4f}  t={s['t']:+.3f}  p={s['p']:.4f}"
        )

    print()
    print("If the full universe shows drift and the option-covered names do not, the")
    print("harness is sound and the subset is the finding, not the bug.")


if __name__ == "__main__":
    main()
