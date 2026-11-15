# Freeze note: empirical-Bayes name selector on 0-1 day event straddles, held-out block

Written 2026-11-13T17:24Z, before any 2019-24 outcome was read by this lane. Trial 2,078.

## Provenance

Discovery-derived. The EB selector on residual value was pre-specified by the lane brief; the
restriction to 0-1 day tenors follows the round 3 diagnosis and the round 4 discovery
persistence (trial 2,071). On discovery the selector itself (trial 2,072) was unpowered and
failed: N 296, 63 treated, +0.083 premiums [-0.206, +0.355], null pct 58.4. It goes to the
held-out block because that is the only block with enough 0-1 day events to test it (1,743
events), not because discovery supported it.

## Hypothesis and mechanism

As in `freeze_J23_persistence.md`: where the straddle has at most a day of life after the
reaction session, a name's own record of residual value estimates a persistent over-pricing of
its event, and the names with the highest shrunken record keep more residual value than
tenor-matched peers.

## Rule (code path of trial 2,072, `r4_exit_and_short.py`, unchanged)

Universe: events with 0-1 day tenor and an assigned causal cell. Track record: residual value y
(H per unit mid premium, net at touch) of the same name's 0-1 day events whose expiry is
strictly before the entry session; at each entry date cell means (cells with at least 20 resolved
events), 1st/99th winsorisation, sigma2 (pooled within-name variance) and tau2 (method of
moments, floored at zero) are re-estimated from resolved events only; shrunken effect
B (mean) with B = tau2 / (tau2 + sigma2 / n), towards zero. Treated: top quintile, cuts from
strictly earlier dates' signals once 100 exist. History may include 2013-18 events.

## Scoring on 2019-24

Within-cell treated minus untreated mean of y, date-clustered bootstrap (5,000, seed 0),
tenor-matched (cell) random null on the treated mean of y, distinct names treated, the contrast
without the five largest contributing names, and the treated level of H on m0 net at touch with
its date-clustered interval.

Pass: CI lower bound above zero and null percentile at least 95. Exploratory label whatever the
result (discovery-derived). A pass carried by five or fewer names (contrast without the top five
at or below zero) is reported as fragile, not as a finding.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneJ-name-persistence\freeze_J28_short_eb_selector.md
