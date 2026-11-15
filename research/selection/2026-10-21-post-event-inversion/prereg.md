# Pre-registration: an inverted post-event term structure predicts outperformance

Frozen before any 2019-2024 outcome for this signal is computed. Changes after an outcome is
viewed require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-10-21-post-event-inversion.json`.
Scorer: `research/selection/2026-10-21-post-event-inversion/study.py`.

## Provenance of the hypothesis

This hypothesis was formed after viewing a discovery result, and says so. The 2026-10-20
post-event equity study (E2) declared that an inverted post-event structure predicts
underperformance. On 2013-2018 the declared long-short lost -0.91% per 20-day position
[-1.64%, -0.18%], N=486, and the gross decile table had the lowest-slope decile at +1.40% against
+0.13% for the highest. E2 is closed as declared. This is a new hypothesis with the opposite sign,
tested once on the block E2 never touched.

## Hypothesis

Names whose implied term structure is still inverted at the close of the reaction session (the
14-45 day expiry richer than the expiry at least 21 days later) outperform names with the most
upward-sloping structure over the next 20 trading days. Candidate mechanisms, not separated by
this test: a premium for bearing unresolved idiosyncratic uncertainty as it resolves, or
short-term reversal after large reaction moves that the inversion proxies for. The second is a
confound, so it is controlled for explicitly below.

## Data and blocks

Identical to the E2 specification in `research/selection/2026-10-20-post-event-equity/prereg.md`
(signal `post_slope`, 20-day market-adjusted return from the exit-date CRSP close, half-spread
round-trip cost floored at 1 bp, causal deciles from strictly earlier exit dates, minimum 300).
Test block: exit dates 2019-01-01 to 2024-12-31, never viewed for this signal. 2013-2018 is the
block the hypothesis came from and is reported only as such.

## Specification

Long the lowest-slope decile, short the highest-slope decile. Position return: signed
market-adjusted return minus the round-trip cost.

Confound control (declared, secondary): the reaction-session return R (CRSP return on the exit
date) is computed for every event. (a) The primary long-short is repeated within terciles of
|R| (causal breakpoints as above) and the three within-tercile means are averaged. (b) An OLS of
the 20-day market-adjusted return on the slope decile rank, R and |R| across all assigned
events in the block, with standard errors clustered by exit date, reports the slope-rank
coefficient.

## Primary statistic and inference

Mean net return per 20-day position, cluster bootstrap on exit dates, 5,000 draws, seed 0;
per-position Sharpe; DSR against 1,543 trials.

## Success criterion

Primary: lower bound above zero on 2019-2024. The result is called promising only if, in
addition, the within-|R|-tercile average is positive and the slope-rank coefficient in (b) is
negative (lower slope, higher return) with a clustered t below -2. Otherwise a primary pass is
reported as "consistent with reversal, not established as a term-structure effect".

## Kill criterion

Primary lower bound at or below zero on 2019-2024 closes the idea.

## Trial accounting

One trial. Count after: 1,543 (1,542 after the hedged-hold second wave, plus this).
