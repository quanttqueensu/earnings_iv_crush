# Freeze: earlier entry into the hedged hold, held-out read

Written 2026-11-13 after the discovery trials 2,021 to 2,033 were scored and before any held-out
DoltHub chain was pulled. The held-out read is run once, with the code as it stands in this
folder (`pull.py --set heldout`, `build.py --set heldout`, `heldout.py`). Nothing below changes
after the pull.

## Provenance

All three trials are discovery-derived. Trials 2,034 and 2,035 restate the two least negative
discovery comparisons (2,021 and 2,024); they are the best of thirteen and were chosen after
viewing, so their discovery effects are biased upward. Trial 2,036 restates 2,023, the one
discovery result with t of magnitude 3 or more, to test whether the cost finding replicates.

## Block

Held-out: a seeded random sample (seed 20261113, N 900 before coverage) of 2026-11-02 hedged-hold
events with status ok, entry 2019-02-20 to 2024-12, on tickers alphabetically after CHD. Their
pre-event DoltHub chains have never been pulled or viewed. The level of the hedged hold H on
2020-24 has been viewed by earlier studies (descriptive); the early-minus-standard outcome has
not been viewed on any of these events. The sample is drawn by `pull.py` with the fixed seed;
no event is dropped by hand.

## Arms (unchanged from discovery)

S0: the standard sale, front ATM straddle at the Databento 15:59 bid on D0. Dk: the same expiry
sold at the DoltHub end-of-day bid k sessions earlier at that day's ATM strike. D0: the
same-day DoltHub quote. Every arm is delta-hedged at every close from its entry to the session
before expiry and settles at intrinsic, with the costs of `hedged_short_straddle`. A bin uses
each event's smallest available k in the bin. Unit: the standard m0, per trade, net at the touch.

## Trials

| Trial | Comparison | Hypothesis (alpha direction) | Pass |
|---|---|---|---|
| 2,034 | k2-3 minus S0 | selling 2-3 sessions earlier beats the standard sale | mean > 0, t >= 3, sign-flip null percentile >= 95 |
| 2,035 | k2-3 minus D0 | at a matched quote source, the earlier day gets the better price | mean > 0, t >= 3, null percentile >= 95 |
| 2,036 | k7-10 minus S0 | cost check: the deep early sale loses to the standard sale | mean < 0 with the date-clustered 95% interval below zero |

Intervals: `protocol.date_clustered_ci`, clustered on the reaction session. Null: date-cluster
sign flips of the paired differences (5,000 draws, seed 0). Also reported, not tested: each
book's level with its interval, coverage and the covered-against-uncovered S0 outcome for each
bin, paired gross-at-mid differences, and the same-day DoltHub/Databento spread calibration.

## Expectation stated before the read

From discovery, 2,034 and 2,035 should fail (point estimates within half a point of m0 of zero)
and 2,036 should pass. A pass of 2,034 or 2,035 would still be exploratory, because both are
discovery-derived and the held-out block is not clean for the H level.

## Mechanism

Selling earlier is fair at the mid (the event-variance run-up the early seller gives away is
offset by the extra diffusive decay collected), and the early sale crosses a spread on a larger
premium, so in units of m0 it pays more to enter. Spreads per unit of m0 are not narrower away
from the event.
