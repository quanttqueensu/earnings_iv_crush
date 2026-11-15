"""
r6_holdout_1851.py
Held-out read (entry 2019-24) of trial 1,851 as frozen in freeze_2026-11-13_post-event-vrp.md,
with the universe funnel and an attrition comparison.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/r6_holdout_1851.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lanec_lib as L
import round3 as r3


def main() -> None:
    raw = pd.read_parquet(L.HERE / "panel.parquet")
    e = pd.read_parquet(L.HERE / "entry_panel.parquet")
    e = e[e["year"].between(2019, 2024)]
    raw = raw[raw["year"].between(2019, 2024)]
    ok = raw[raw["lc_status"] == "ok"]
    key = ["ticker", "entry_date"]
    dropped = e.merge(ok[key], on=key, how="left", indicator=True)
    dropped = dropped[dropped["_merge"] == "left_only"]
    print(f"held-out funnel: status-ok {len(e)}; n_hedge>=1 {int((e['n_hedge'] >= 1).sum())}; "
          f"two-sided {len(raw)}; lane-ok {len(ok)}")
    print(f"  attrition: H lane-ok {100 * ok['H'].mean():+.3f}% vs dropped {100 * dropped['H'].mean():+.3f}% "
          f"of m0 (N {len(dropped)}); G dropped (n_hedge>=1) "
          f"{100 * (dropped.loc[dropped['n_hedge'] >= 1, 'H'] - dropped.loc[dropped['n_hedge'] >= 1, 'B']).mean():+.3f}%")
    p = r3.features(L.load())
    p["pred_D"] = r3.walk_forward_pred(p, "D_net")
    m = (p["block"] == "heldout") & p["pred_D"].notna()
    blk = p[m]
    close = (blk["pred_D"] + blk["exit_half"] + 2 * r3.FEE / blk["m0"] < 0).to_numpy()
    res = L.hold_or_close(blk, close)
    eff = res["effect"]
    ok_ = eff["low"] > 0 and eff["t"] >= 3 and res["null_pct"] >= 95
    sec = (f"closed {res['n_closed']}; G closed {100 * res['G_closed']:+.3f}% kept "
           f"{100 * res['G_kept']:+.3f}%; rule level {L.fmt(res['level_rule'])}%; always-hold "
           f"{L.fmt(res['level_hold'])}%; corr(pred, D_net) "
           f"{np.corrcoef(blk['pred_D'], blk['D_net'])[0, 1]:+.3f}")
    print(f"[1851 held-out] {L.fmt(eff)} null pct {res['null_pct']:.1f} -> "
          f"{'pass' if ok_ else 'fail'}\n    {sec}")
    L.log_trial({"trial_id": 1851, "hypothesis": "walk-forward forecast hold-or-close (frozen)",
                 "mechanism": "as frozen in freeze_2026-11-13_post-event-vrp.md",
                 "block": "2019-24", "n": eff["n"], "effect": eff["point"], "ci_low": eff["low"],
                 "ci_high": eff["high"], "t": eff["t"], "null_pct": res["null_pct"],
                 "basis": r3.BASIS_RULE, "verdict": ("pass" if ok_ else "fail") + " held-out",
                 "secondary": sec})


if __name__ == "__main__":
    main()
