"""
cost_floor.py
Cost floor at IB for a short at-the-money straddle on a CME weekly FX option held to the 09:00 CT
expiry (lane N07, design D4 in `../diagnosis.log`).

Not a quote measurement: the half-spread is a scenario in ticks, because no free source of CME
FX option quotes exists. Tick sizes and contract sizes are from the CFTC copy of CME submission
22-440 (2022); the IB commission is from IB's futures commission page; the CME exchange fee is the
non-member Globex rate in the same CFTC filing and may have changed since.

Usage
-----
    python -I scripts/cost_floor.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Contract:
    name: str
    notional: float  # units of foreign currency per contract
    tick: float  # option premium tick, USD per unit of foreign currency
    spot: float  # level used to size a typical premium
    on_vol_event: float  # a typical quoted overnight event vol, from the verified wraps
    fut_tick: float  # futures tick, for closing the exercised futures


CONTRACTS = [
    # EUR: 0.0001 tick (0.00005 below 0.0005 premium); futures tick 0.00005.
    Contract("EUR (6E) Thursday weekly, ECB", 125_000, 0.0001, 1.16, 13.5, 0.00005),
    # JPY quoted in USD per yen; option tick 0.000001 per yen = 12.50 USD on 12.5m yen
    # (0.0000005 below 0.000005 premium); futures tick 0.0000005 (recalled).
    Contract("JPY (6J) Friday weekly, BoJ", 12_500_000, 0.000001, 1 / 152.0, 12.0, 0.0000005),
]

IB_COMMISSION = 0.85  # USD per contract, IBKR Pro fixed and tiered up to 1,000 a month
CME_FEE_NON_MEMBER = 1.60  # USD per contract, CME Globex non-member, CME submission 22-440
EXERCISE_FEE = 0.65  # USD, "Exe|Asn|Future From", non-member, same filing
STRADDLE_K = np.sqrt(2.0 / np.pi)


def main() -> None:
    rows = []
    for c in CONTRACTS:
        premium_per_unit = STRADDLE_K * c.on_vol_event / 100 * np.sqrt(1 / 365) * c.spot
        premium_usd = premium_per_unit * c.notional
        fees_entry = 2 * (IB_COMMISSION + CME_FEE_NON_MEMBER)
        # One leg finishes in the money and becomes a futures position that must be closed:
        # exercise fee, one futures commission and exchange fee, half a futures tick.
        exercise_close = EXERCISE_FEE + IB_COMMISSION + CME_FEE_NON_MEMBER + 0.5 * (
            c.fut_tick * c.notional)
        for width_ticks in (1, 2, 4):
            half_spread = 2 * 0.5 * width_ticks * c.tick * c.notional
            total = half_spread + fees_entry + exercise_close
            rows.append({
                "contract": c.name, "on_vol_event": c.on_vol_event,
                "premium_usd_per_straddle": round(premium_usd, 2),
                "quoted_width_ticks_per_leg": width_ticks,
                "half_spread_usd": round(half_spread, 2),
                "half_spread_share": round(half_spread / premium_usd, 4),
                "fees_and_exercise_usd": round(fees_entry + exercise_close, 2),
                "total_cost_share_of_premium": round(total / premium_usd, 4),
            })
    df = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / "cost_floor.csv", index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
