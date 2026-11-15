"""r8_coverage_check.py: is the positive H+E45 level on broad 2025-26 a coverage artefact? (real data)

r7 found the 15:45 entry plus hedged hold net positive on broad 2025-26, but only on the 463 of
1,597 events whose tick-panel contract matches the hold table's contract, and those events were
already better on the hold alone. This script:
  1. classifies why each event lacks a same-contract 15:45 quote (no tick row, strike differs,
     expiry differs);
  2. compares covered and uncovered events on pre-entry features (tenor, implied move, spread);
  3. reweights the covered events to the full block's tenor x implied-move x spread composition
     (cells fixed from pre-entry features only) and re-reads the H and H+E45 levels;
  4. reports the full-block level estimate H(all) + mean E45 lift, the lift taken within cells.

Basis: fraction of m0 (0.20 x forward + 15:59 bid premium), net, per trade; date-clustered 95%
intervals clustered on exit date as in r7. Descriptive: every block here was viewed.

Usage
-----
    python r8_coverage_check.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import ROOT, ci, fmt, load_ticks

RES = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"


def main() -> None:
    e = pd.read_parquet(RES / "events_confirm_2025_26.parquet")
    e = e[(e["status"] == "ok") & e["B"].notna() & e["H"].notna()].drop_duplicates(["ticker", "entry_date"]).copy()
    e = e[e["entry_date"] >= "2025-01-01"]
    t = load_ticks()
    t = t[t["block"] == "broad_2025_2026"][["ticker", "entry_date", "strike", "expiry", "en_two_15:45",
                                            "en_bid_15:45", "en_bid_15:59"]]
    t["expiry"] = pd.to_datetime(t["expiry"])
    e = e.merge(t, on=["ticker", "entry_date"], how="left", suffixes=("", "_t"))
    has_row = e["strike_t"].notna()
    same_k = e["strike"] == e["strike_t"]
    same_x = e["expiry"] == e["expiry_t"]
    two = e["en_two_15:45"].fillna(False).astype(bool)
    e["why"] = np.select(
        [~has_row, has_row & ~same_x & same_k, has_row & same_x & ~same_k, has_row & ~same_x & ~same_k,
         same_k & same_x & ~two, same_k & same_x & two],
        ["no tick row", "expiry differs", "strike differs", "both differ", "15:45 not two-sided", "covered"],
        default="other")
    print(f"funnel: broad 2025-26 hold events {len(e)}")
    print(e["why"].value_counts().to_string())

    e["dte"] = (pd.to_datetime(e["expiry"]) - pd.to_datetime(e["entry_date"])).dt.days
    e["implied_move"] = e["mid0"] / ((e["m0"] - e["s0"]) / 0.20)
    e["hs"] = (e["mid0"] - e["s0"]) / e["mid0"]  # half-spread as a share of mid, from the 15:59 bid
    cov = e["why"] == "covered"
    print("\npre-entry medians, covered vs not:")
    for c in ("dte", "implied_move", "hs"):
        print(f"  {c:13s} {e.loc[cov, c].median():.4f} | {e.loc[~cov, c].median():.4f}")
    print("\nH level by coverage reason (fraction of m0, net):")
    for w, g in e.groupby("why"):
        if len(g) >= 20:
            print(f"  {w:20s} {fmt(ci(g['H'], g['exit_date']))}")

    # cells from pre-entry features only, cut on the full block
    e["c_dte"] = pd.cut(e["dte"], [-1, 1, 4, 9, 10_000], labels=["0-1d", "2-4d", "5-9d", "10d+"])
    e["c_im"] = pd.qcut(e["implied_move"], 3, labels=False, duplicates="drop")
    e["c_hs"] = pd.qcut(e["hs"], 3, labels=False, duplicates="drop")
    e["cell"] = e["c_dte"].astype(str) + "|" + e["c_im"].astype(str) + "|" + e["c_hs"].astype(str)
    k = e[cov].copy()
    k["e45"] = (k["en_bid_15:45"] - k["s0"]) / k["m0"]
    full_w = e["cell"].value_counts(normalize=True)
    cov_w = k["cell"].value_counts(normalize=True)
    k["w"] = k["cell"].map(full_w / cov_w)
    missing = full_w.index.difference(cov_w.index)
    print(f"\ncells: {e['cell'].nunique()} in full block, {k['cell'].nunique()} with covered events; "
          f"full-block weight in cells with no covered event {100*full_w[missing].sum():.1f}%")

    rng = np.random.default_rng(20261113)
    dates = k["exit_date"].to_numpy()
    ud = np.unique(dates)
    idx = {d: np.flatnonzero(dates == d) for d in ud}

    def wboot(col: str) -> tuple[float, float, float]:
        x, w = k[col].to_numpy(float), k["w"].to_numpy(float)
        pt = float(np.sum(w * x) / np.sum(w))
        draws = []
        for _ in range(4000):
            s = np.concatenate([idx[d] for d in rng.choice(ud, size=len(ud), replace=True)])
            draws.append(np.sum(w[s] * x[s]) / np.sum(w[s]))
        lo, hi = np.percentile(draws, [2.5, 97.5])
        return pt, float(lo), float(hi)

    k["HE"] = k["H"] + k["e45"]
    print("\ncovered events reweighted to the full block composition (fraction of m0 x 100):")
    for col in ("H", "e45", "HE"):
        p, lo, hi = wboot(col)
        print(f"  {col:4s} {100*p:+.2f} [{100*lo:+.2f}, {100*hi:+.2f}] N={len(k)}")
    print("  (unweighted for reference) H", fmt(ci(k["H"], k["exit_date"])), "| HE", fmt(ci(k["HE"], k["exit_date"])))

    # full-block estimate: H on every event plus the E45 lift imputed by cell mean (covered events)
    lift = k.groupby("cell")["e45"].mean()
    e["e45_imp"] = e["cell"].map(lift).fillna(k["e45"].mean())
    e.loc[cov, "e45_imp"] = k["e45"]
    e["HE_imp"] = e["H"] + e["e45_imp"]
    print("\nfull block, H on all events plus cell-imputed 15:45 lift:")
    print("  H     ", fmt(ci(e["H"], e["exit_date"])))
    print("  H+E45 ", fmt(ci(e["HE_imp"], e["exit_date"])), "(interval ignores imputation error, so it is too narrow)")


if __name__ == "__main__":
    main()
