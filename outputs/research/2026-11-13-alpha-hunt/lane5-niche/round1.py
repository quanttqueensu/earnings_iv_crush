"""
round1.py
Round 1 of the lane5-niche hunt: ten mechanism-first selectors on the discovery block 2013-18.

Each trial states its mechanism and expected sign before scoring; treated is the group the
mechanism says is over-priced, so a positive Delta supports it.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt/lane5-niche/round1.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib

d = lib.load()
dates = d["announce_date"]
T = pd.Series(True, index=d.index)


def top(col: str, n: int = 5) -> tuple[pd.Series, pd.Series]:
    b = lib.causal_quantile_bins(d[col].to_numpy(float), dates, n)
    return pd.Series(b == n - 1, index=d.index), pd.Series(b >= 0, index=d.index)


def bottom(col: str, n: int = 5) -> tuple[pd.Series, pd.Series]:
    b = lib.causal_quantile_bins(d[col].to_numpy(float), dates, n)
    return pd.Series(b == 0, index=d.index), pd.Series(b >= 0, index=d.index)


d["spot"] = d["F0"]
trials = []
f, ok = top("peer_share", 3)
trials.append((1749, "late_in_industry", f, ok,
               "most same-industry-group peers with the same fiscal quarter end have reported "
               "before entry, so less news is left than the straddle prices; feature dated entry-1"))
trials.append((1750, "peer_week_3plus", d["peer_week"] >= 3, d["peer_week"].notna(),
               "three or more same-industry peers reported in the 7 days before entry; industry "
               "news is already in the price; feature dated entry-1"))
f, ok = top("crowd_all")
trials.append((1751, "crowd_high", f, ok,
               "top causal quintile of market-wide reporters on the announcement date: dealer "
               "capacity for event vol is spread thin and premium is richer; reporting calendar"))
f, ok = bottom("crowd_all")
trials.append((1752, "crowd_low", f, ok,
               "bottom causal quintile of reporters: a lone off-season print concentrates "
               "speculative option demand and is over-priced; reporting calendar"))
trials.append((1753, "not_fiscal_q4", d["fqtr"].isin([1, 2, 3]), d["fqtr"].notna(),
               "fourth-quarter prints carry annual guidance and move more than priced, so the "
               "seller keeps more on Q1 to Q3 prints; fiscal calendar"))
trials.append((1754, "friday_reaction", d["exit_wd"] == 4, T,
               "reaction session is a Friday: weekly buyers pay up for options with no life "
               "after the reaction; weekday known in advance"))
trials.append((1755, "holiday_before_expiry", d["holiday_to_expiry"], T,
               "a market holiday falls between the reaction and expiry: calendar-day pricing "
               "carries extra non-trading time the seller collects; exchange calendar"))
f, ok = bottom("spot")
trials.append((1756, "low_price", f, ok,
               "bottom causal quintile of share price: retail lottery demand for cheap-contract "
               "event options enriches the premium; entry forward at entry"))
f, ok = top("turnover_126d")
trials.append((1757, "high_turnover", f, ok,
               "top causal quintile of 126-day share turnover (month end before the entry "
               "month): attention-driven option buying enriches the premium"))
trials.append((1758, "weekend_gap", d["gap_days"] >= 3, T,
               "entry Friday, reaction Monday or later: the seller collects weekend decay priced "
               "at calendar time (Jones and Shemesh 2018); schedule"))

for tid, hyp, f, ok, mech in trials:
    try:
        lib.score(d, f.fillna(False), ok, "discovery", hyp=hyp, trial_id=tid, mechanism=mech)
    except ValueError as e:
        print(f"{hyp}: NOT SCORED, {e}")
    print()
