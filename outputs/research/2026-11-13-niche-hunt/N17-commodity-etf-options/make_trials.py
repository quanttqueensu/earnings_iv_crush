"""make_trials.py: assemble trials.csv from the discovery (run 4) and held-out result files.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N17-commodity-etf-options/make_trials.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
VIEWED = {"GLD", "SLV", "TLT"}  # held-out block read by N05 and N12 before this lane's freeze


def main() -> None:
    disc = pd.read_csv(HERE / "results_discovery.csv").assign(block="discovery 2009/2016-2020")
    held = pd.read_csv(HERE / "results_heldout.csv").assign(block="held-out 2021-01 to 2026-10")
    keep = ["trial", "family", "tenor", "block", "n", "event_share30", "event_lo", "event_hi",
            "surplus", "surplus_lo", "surplus_hi", "cost_rt_share", "net", "net_lo", "net_hi",
            "pass_S1", "pass_S2"]
    t = pd.concat([disc[keep], held[keep]]).rename(columns={
        "event_share30": "event_mid", "event_lo": "event_mid_lo", "event_hi": "event_mid_hi",
        "cost_rt_share": "cost_roundtrip_incl_commission"})
    etf = t["family"].str.split("_").str[0]
    pooled = t["family"].str.endswith(("MACRO", "WPSR"))
    t["status"] = "per-kind diagnostic, cannot pass a family"
    t.loc[pooled, "status"] = "pooled family"
    held_rows = t["block"].str.startswith("held")
    t.loc[held_rows & etf.isin(VIEWED), "status"] = "viewed block (N05, N12): descriptive only"
    t.loc[held_rows & (etf == "USO"), "status"] = "clean held-out test"
    t["basis"] = ("per trade (one report day, close to close), share of ATM straddle premium at "
                  "the stated tenor; event and surplus gross at the mid from Cboe index closes "
                  "(model-based); net after round-trip touch plus USD 0.65 per contract, "
                  "2026-11-13 14:33 ET snapshot; date-clustered 95% intervals")
    t = t.sort_values(["trial", "block"])
    t.to_csv(HERE / "trials.csv", index=False, float_format="%.5f")
    print(t[["trial", "family", "tenor", "block", "n", "surplus", "net", "net_lo", "status"]]
          .to_string(index=False))
    print(f"distinct trials: {t.trial.nunique()} ({t.trial.min()} to {t.trial.max()})")


if __name__ == "__main__":
    main()
