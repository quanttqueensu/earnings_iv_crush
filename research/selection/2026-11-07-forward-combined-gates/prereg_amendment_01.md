# Amendment 01: tenor-matched scoring for the forward combined gates

Amends `prereg.md` (record `outputs/research/prereg_2026-11-07-forward-combined-gates.json`, sha256
209a0282). Frozen before any forward outcome exists: the paper book's first transmitting session is
2026-11-09 and no transmitted trade has been entered, let alone exited. Record:
`outputs/research/prereg_2026-11-07-forward-combined-gates-amendment-01.json`.

## Reason

The pairwise tercile study scored on 2026-11-07 (`research/selection/2026-11-07-pairwise-tercile-gates`)
found that residual value is largely a measure of option tenor: its rank correlation with days from
the exit session to the front expiry is -0.70 over 9,350 broad events (2013-2026), and the term
spread, one of this study's features, correlates -0.49 with the same quantity. A gate correlated
with tenor therefore beats a random null on residual value without any mispricing. Within tenor
buckets the pairwise lift shrank from about +3.5 to +0.2 to +0.6 points of margin per trade
(`outputs/research/2026-11-07-pairwise-tercile-gates/tenor_diagnostic.log`). The original scoring
would have read that composition effect as selection skill.

## Changes

1. **Tenor buckets.** Each scored trade is assigned to a bucket by calendar days from its exit date
   to its front expiry: 0-1, 2-4, 5-9, 10 or more. The bucket edges are the ones used in the
   diagnostic, fixed here.
2. **Matched null within tenor.** The participation-matched random null draws, in each bucket, as
   many trades as the gate selected in that bucket (5,000 draws, seed 0), and compares the mean.
3. **Difference within tenor.** The selected-minus-unselected difference is the mean of
   within-bucket differences weighted by the selected count, over buckets with at least two
   selected and two unselected trades; its interval is a date-clustered bootstrap (announcement
   dates resampled, 5,000 draws, seed 0).
4. **Second outcome.** The same tenor-matched null is also computed on net return on margin.

## Verdict rule, replacing the original

No verdict before 150 selected scored trades. A gate passes only if all four hold: the
tenor-matched null percentile on residual value is at least 95, the lower bound of the
within-tenor difference in residual value is above zero, the tenor-matched null percentile on net
return on margin is at least 95, and the selected mean net return on margin is above zero.
Anything else at that point is a FAIL. Hypotheses, features, causal ranks, warm-up and trial count
are unchanged.
