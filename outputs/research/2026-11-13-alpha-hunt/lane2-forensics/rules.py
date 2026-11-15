"""
rules.py
Rule definitions for lane2-forensics. Each rule returns (flag, defined) over a ledger frame and
carries the mechanism and predicted sign written before it was scored. Thresholds on continuous
features are causal percentiles (strictly earlier announcement dates, 200-event burn-in) computed
over the whole ledger so that a held-out event's cut uses only earlier events.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lib import causal_pct


def add_pcts(d: pd.DataFrame) -> pd.DataFrame:
    for c in ("spread_pct", "peer_z_mean_5s", "im_rel_own", "dolvol_126d", "vix", "im_over_hist"):
        d[f"{c}_cp"] = causal_pct(d[c], d["announce_date"])
    return d


def fin(x: pd.Series) -> np.ndarray:
    return np.isfinite(x.to_numpy(float))


# id: (name, mechanism, sign, round, function -> (flag, defined))
RULES = {
    1659: ("cheap premium: implied move <= 0.85x median of own last 8 implied moves",
           "jump risk is a property of the name, the premium floats with market vol; a cheap print is under-insured",
           -1, 1, lambda d: (d["im_rel_own"] <= 0.85, fin(d["im_rel_own"]))),
    1660: ("small cap: market equity below the 90th cross-sectional percentile",
           "thin option market and less pre-disclosure, so larger surprise per unit of premium",
           -1, 1, lambda d: (d["me_pct"] < 0.90, fin(d["me_pct"]))),
    1661: ("wide entry quote: straddle spread in the causal top quintile (reference, closed spread gate)",
           "the touch cost is paid twice; a wide entry quote predicts a wide exit quote",
           -1, 1, lambda d: (d["spread_pct_cp"] >= 0.8, fin(d["spread_pct_cp"]))),
    1662: ("peer shock, continuous: mean standardised reaction of same-industry reporters in the prior 5 sessions in the causal top quintile",
           "an industry shock under way raises dispersion of the next reporter; differs from failed T1 (30 days, binary 2x implied, panel peers)",
           -1, 1, lambda d: (d["peer_z_mean_5s_cp"] >= 0.8, fin(d["peer_z_mean_5s_cp"]))),
    1663: ("late report: 5 or more days later than the same quarter a year earlier",
           "delays signal unresolved accounting or bad news, a larger surprise than priced",
           -1, 1, lambda d: (d["yoy_shift_d"] >= 5, fin(d["yoy_shift_d"]))),
    1664: ("fiscal fourth-quarter report",
           "annual guidance is issued with the fourth quarter, a second source of jump",
           -1, 1, lambda d: (d["fiscal_q4"] == 1, fin(d["fiscal_q4"]))),
    1665: ("amended 10-K or 10-Q filed in the prior 365 days",
           "a restatement proxy: reporting quality in question raises surprise variance",
           -1, 1, lambda d: (d["e_amend_form_365d"] == 1, d["e_def"] == 1)),
    1666: ("52-week extreme: prior close within 2% of the range top or bottom",
           "positioning is one-sided at an extreme, so the reaction is larger than priced",
           -1, 1, lambda d: ((d["pos_52w"] >= 0.98) | (d["pos_52w"] <= 0.02), fin(d["pos_52w"]))),
    1667: ("session switched against the name's habit (before open versus after close)",
           "an unusual release time signals an unusual release",
           -1, 1, lambda d: (d["session_switch"] == 1, fin(d["session_switch"]))),
    1668: ("merger filing (425, S-4, DEFM14A, tender forms) in the prior 180 days",
           "a report inside a pending deal carries deal-break and re-rating risk",
           -1, 1, lambda d: (d["e_merger_form_180d"] == 1, d["e_def"] == 1)),
    1669: ("unusual weekday: none of the last 8 reports fell on this weekday",
           "report timing unusual for the name signals an unusual release",
           -1, 1, lambda d: (d["dow_same_share"] == 0, fin(d["dow_same_share"]))),
    # round 2: written after reading round 1 (see report)
    1670: ("cheap premium outside the wide-quote quintile",
           "same as 1,659, with the cost driver removed so that the effect must come from the move",
           -1, 2, lambda d: (d["im_rel_own"] <= 0.85, fin(d["im_rel_own"]) & (d["spread_pct_cp"] < 0.8))),
    1671: ("rich premium: implied move >= 1.20x median of own last 8 implied moves",
           "mirror of 1,659: when the name's premium is above its habit the seller is over-insured (winner selection)",
           +1, 2, lambda d: (d["im_rel_own"] >= 1.20, fin(d["im_rel_own"]))),
    1672: ("cheap premium against a stressed tape: im_rel_own <= 0.85 and VIX above its causal median",
           "premium below habit while market risk is above habit is the purest under-insurance",
           -1, 2, lambda d: ((d["im_rel_own"] <= 0.85) & (d["vix_cp"] >= 0.5), fin(d["im_rel_own"]) & fin(d["vix_cp"]))),
    1673: ("premium fell since the last report: implied move <= 0.80x the previous event's",
           "a faster-moving version of 1,659 that needs one prior event only",
           -1, 2, lambda d: (d["im_prev"] <= 0.80, fin(d["im_prev"]))),
    1674: ("liquid name: dollar volume in the causal top quintile",
           "deep option markets lose less to the touch and carry more pre-disclosure (winner selection, cost driver)",
           +1, 2, lambda d: (d["dolvol_126d_cp"] >= 0.8, fin(d["dolvol_126d_cp"]))),
    1678: ("late report outside the wide-quote quintile",
           "as 1,663 with the cost driver removed; round 1 showed no move difference (ratio 0.74 against 0.73)",
           -1, 2, lambda d: (d["yoy_shift_d"] >= 5, fin(d["yoy_shift_d"]) & (d["spread_pct_cp"] < 0.8))),
    1679: ("small cap outside the wide-quote quintile",
           "as 1,660 with the cost driver removed; round 1 showed no move difference (ratio 0.73 against 0.76)",
           -1, 2, lambda d: (d["me_pct"] < 0.90, fin(d["me_pct"]) & (d["spread_pct_cp"] < 0.8))),
    # round 3
    1675: ("premium relative to own habit, bottom versus top causal quintile of im_rel_own (flag = bottom, scored against top only)",
           "dose-response check of 1,659 and 1,671",
           -1, 3, lambda d: (d["im_rel_own_cp"] <= 0.2, fin(d["im_rel_own_cp"]) & ((d["im_rel_own_cp"] <= 0.2) | (d["im_rel_own_cp"] >= 0.8)))),
    1676: ("cheap premium and no peer has reported in the prior 30 days",
           "cheap premium is most dangerous when no peer has yet revealed the industry state",
           -1, 3, lambda d: ((d["im_rel_own"] <= 0.85) & (d["peer_n_30d"] == 0), fin(d["im_rel_own"]) & fin(d["peer_n_30d"]))),
    1677: ("frozen candidate form: implied move <= 0.90x median of own last 8 implied moves",
           "as 1,659 at a looser cut, to test threshold sensitivity before freezing",
           -1, 3, lambda d: (d["im_rel_own"] <= 0.90, fin(d["im_rel_own"]))),
    1680: ("health-care sector (GICS 35)",
           "8 of the 20 worst case files are health care: trial, reimbursement and product news is released with results and is binary",
           -1, 3, lambda d: (d["gics2"] == "35", d["gics2"].notna().to_numpy())),
    1681: ("implied move at most 0.45x the largest of the name's last 8 reactions",
           "the jump losers in the case files were priced at a third to a half of a move the name had already shown",
           -1, 3, lambda d: (d["im_over_histmax"] <= 0.45, fin(d["im_over_histmax"]))),
}
