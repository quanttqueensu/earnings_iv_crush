"""score_heldout.py: the single held-out read for N09, written before the freeze note.

Primary (the only configuration that passed discovery):
  T2330  FOMC, short F1 from settle(D-1) to settle(D), sized by 1 / trailing 20-session SD of daily
         front-month returns (causal). Pass: net per sigma lower bound > 0 AND surplus per sigma
         lower bound > 0, at the primary cost, held-out 2017-01-01 to 2026-11-12.
Secondary, declared before the read, exploratory and not findings (both failed discovery):
  T2322  the same trade unscaled (post-publication replication of Fernandez-Perez et al. 2017);
  T2328  VVIX log change on FOMC days minus controls.

Refuses to run if the freeze note is missing or its recorded scorer hash does not match.

Usage
-----
    python scripts/score_heldout.py
"""

from __future__ import annotations

import hashlib
import json
import re

import pandas as pd

import score_round2 as R2
import vxlib as V

FREEZE = V.LANE / "freeze_heldout.md"


def _check_freeze() -> None:
    if not FREEZE.exists():
        raise SystemExit("freeze_heldout.md missing: refuse to read the held-out block")
    text = FREEZE.read_text(encoding="utf-8")
    m = re.search(r"score_heldout\.py SHA-256: ([0-9a-f]{64})", text)
    own = hashlib.sha256(open(__file__, "rb").read()).hexdigest()
    if not m or m.group(1) != own:
        raise SystemExit("scorer hash does not match the freeze note")


def main() -> None:
    _check_freeze()
    _, _, days, _, _ = V.load()
    t, f = V.event_table("fomc", V.HELD_FOMC, 1, V.COST.primary_rt)
    r = R2.front_daily_returns()
    ts = R2.scaled(t, r, days)
    stress = (ts["gross_pts"] - V.COST.stress_rt) / ts["entry_price"] / ts["sigma"]
    prim = {
        "funnel": {**f, "with_sigma": len(ts)},
        "net_ret_per_sigma": V.ci(ts["net_ret"], ts["date"]),
        "surplus_per_sigma": V.ci(ts["surplus"], ts["date"]),
        "net_per_sigma_stress": V.ci(stress, ts["date"]),
        "sharpe_scaled": V.ci(ts["net_ret"], ts["date"], stat=V.per_trade_sharpe),
    }
    prim["passed"] = bool(prim["net_ret_per_sigma"]["low"] > 0
                          and prim["surplus_per_sigma"]["low"] > 0)
    s22 = V.summarise(t, V.COST.primary_rt, V.COST.stress_rt)
    s22["passed_rule"] = V.passes(s22)
    tv, fv = V.index_event_change("fomc", V.HELD_FOMC, "VVIX")
    s28 = {"funnel": fv, "vvix_logchg": V.ci(tv["chg"], tv["date"]),
           "vvix_surplus": V.ci(tv["surplus"], tv["date"])}
    out = {"T2330_primary": prim, "T2322_secondary": s22, "T2328_secondary": s28}
    ts.to_csv(V.LANE / "logs/heldout_T2330.csv", index=False)
    t.assign(yr=pd.to_datetime(t["date"]).dt.year).to_csv(V.LANE / "logs/heldout_T2322.csv",
                                                          index=False)
    (V.LANE / "logs/heldout.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
