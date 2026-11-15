# Lane C: the volatility premium left after the announcement

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log`, `descriptive_levels.log`,
held-out logs and freeze note. Every figure is from those files.

## Verdict

Nothing survived the held-out read, and no book is net positive at the touch. The diffusive
premium left in the held straddle after the reaction close is close to zero once hedging and
delivery costs are paid, so there is nothing rich for a hold-or-close rule to find. Holding beats
buying back because it saves the exit half-spread, not because of a post-event volatility premium.
One by-product matters for every hedged-hold figure: the stored H overcharges the expiry unwind by
about 0.23% of m0 per trade (trial 1,856, an accounting approximation that needs the analyst's
sign-off). Trials 1,841 to 1,856; 1,857 to 1,870 unused.

## Split and basis

Discovery: entry dates 2013-18. Held-out: 2019-24, read once after
`freeze_2026-11-13_post-event-vrp.md` (frozen 12:44:46 local; held-out logs 12:45:05 and 12:45:31).
2025-26 is unusable because the CRSP stock paths end in 2024. Both blocks' hedged-hold levels were
already known. The lane's block statement says no volatility-forecast feature had been read
against this outcome on 2019-24; that is not quite true, because lane A's frozen bias-corrected
HAR buy-back rule (trial 1,796) was read on 2019-24 at 12:38, six minutes before this lane froze.
Both failed, so no verdict changes, but 2019-24 is not clean for HAR features on H minus B.

Universe: front contract status ok in the hedged-hold study, at least one hedging session left, a
two-sided reaction-close quote and an invertible implied vol. Figures are per trade in % of m0,
date-clustered 95% intervals.

## Where the hold's money comes from (descriptive)

| Component | 2013-18 (N=2,391) | 2019-24 (N=4,240) |
|---|---|---|
| Jump part: sold bid minus reaction-close mid | +1.42 [+1.11, +1.74] | +1.28 [+0.99, +1.57] |
| Diffusive part, gross at the mid | +0.51 [+0.30, +0.72] | +0.14 [-0.15, +0.42] |
| Diffusive part, net of hedge and disposal costs | +0.15 [-0.06, +0.36] | -0.22 [-0.51, +0.07] |
| Exit half-spread saved by holding | +1.52 | +1.58 |
| Hold minus buy-back | +1.76 [+1.51, +2.02] | +1.43 [+1.12, +1.73] |

These are not book levels. The universe needs a two-sided reaction quote, which drops the large
moves: on 2019-24 the 1,473 dropped events average H -6.92% of m0 against +0.98% for those kept.
Every rule holds the dropped events, so the paired comparisons are unaffected, but the H levels
here (+1.47 and +0.98) flatter the book.

## Results

| Trial | Rule or test | Block | Effect | 95% CI | t | Null pct | Label |
|---|---|---|---|---|---|---|---|
| 1,841 | Close when post-event IV minus HAR forecast is in the bottom tercile | 2013-18 | -0.32 vs hold | [-0.44, -0.21] | -5.7 | 82.3 | Fail |
| 1,843 | Close when the gap over the implied move is in the top tercile | 2013-18 | -0.66 vs hold | [-0.78, -0.53] | -10.5 | 38.7 | Fail |
| 1,847 | HAR forecast sorts the diffusive part with IV held fixed | 2013-18 | +0.23 | [-0.55, +0.98] | 0.6 | 70.6 | Fail; the sort came from the IV level |
| 1,850 | At entry, keep rich pre-event diffusive IV over HAR | 2013-18 | -1.37 level | [-2.09, -0.65] | -3.7 | 13.3 | Fail |
| 1,855 | Walk-forward forecast of the net diffusive part, top minus bottom tercile | 2013-18 | +1.02 | [+0.39, +1.60] | 3.32 | 100 | Frozen (discovery-derived) |
| 1,855 | Same, frozen | 2019-24 | +0.16 | [-0.64, +0.95] | 0.40 | 58.2 | Fail |
| 1,851 | Close where forecast diffusive part plus closing cost is negative, vs hold | 2019-24 | +0.014 | [-0.022, +0.052] | 0.75 | 100 | Fail |
| 1,856 | Let assignment net the stock hedge at expiry (accounting) | 2013-18 | +0.24 | [+0.24, +0.25] | | | Descriptive |
| 1,856 | Same | 2019-24 | +0.23 | [+0.23, +0.23] | | | Descriptive |

Two trials repeat lane A's, which were scored before the two lanes agreed a scope split: 1,841
repeats lane A's 1,782 and 1,843 repeats its 1,795, differing in causal terciles rather than fixed
thresholds, IV from the mid rather than the ask, the megacap file and the two-sided-quote
universe. They are not independent evidence. Lane A's perfect-foresight ceiling on the full blocks,
-0.13% [-0.56, +0.30] and +0.10% [-0.25, +0.45] of m0 after the netting correction below (it was
-0.30% and -0.06% before), caps every hold-or-close trial here.

Trial 1,851's null percentile of 100 is mechanical, as are the 99 to 100 of 1,845, 1,853 and 1,854: the rule closes short-dated, near-the-money
events that are cheap to close (exit half-spread about 0.31% of m0), and closing them is about
break-even. Its paired effect is what counts.

## Iteration story

Round 1: the forecasts sorted the realised volatility premium by 8 to 12 vol points, but much of
that is mechanical, since post-event IV sits in both signal and outcome. On P&L they sorted the
diffusive part by less than the exit half-spread, so every close paid a spread to avoid a smaller
loss. The worst hold-gain events clustered on market-wide dates (late October 2016, November 2013,
January 2014), systematic volatility that a single-name HAR cannot see. Round 2: with IV fixed, HAR
added nothing; including one-sided reaction quotes did not rescue the gap rule, because big-gap
events lose in the jump part, which is sunk by the reaction close; moving the forecast to entry
selected names with worse jumps. Rounds 3 and 4: one walk-forward model with the closing cost as
its threshold, the strongest honest version, tied always-hold; a safety margin and the VIX state
converged to the same break-even. The model's pure predictability of the diffusive part passed
discovery and was frozen with the rule. Held-out, the tercile pattern was flat (-0.37, -0.11,
-0.21%): discovery's spread came from 2013-18 having the larger premium.

## The accounting point (trial 1,856)

The stored H unwinds the whole stock hedge at the expiry close and also charges 5 bp to dispose of
the delivered stock. At expiry, assignment of the short in-the-money leg delivers shares that the
hedge already holds, so only the mismatch has to trade. Recomputing that one term adds about 0.23
to 0.24% of m0 per trade. It is approximate, with the last hedge ratio rebuilt from the
reaction-close IV and the CRSP close, and it does not make any known net book positive: the
combined 15:45 entry and hedged hold sits at -1.0 to -1.2% of m0 on its clean blocks before
netting. Lane A checked the correction independently on the full blocks, rebuilding the stored
last hedge exactly (+0.22% of m0 per trade, [+0.21, +0.23]); its H stays at -0.82% and -1.05%.
Quote lane A's figures: this lane's +0.24% and +0.23% sit on the two-sided-quote universe with an
approximate hedge ratio, and their t of 55 and 190 reflects an accounting term with almost no
variance, not significance. The gain varies by event, and the buy-back has no expiry leg, so the
correction moves every hold-against-buy-back comparison, including trial 1,851, by about the same
+0.22%. The analyst adopted it on 2026-11-13; it is in the package as
`HedgedHoldConfig.net_assignment` (`HEDGED_NET`).

## Use for the project

The post-event leg is not a source of alpha: what the hold earns over a buy-back is the spread it
avoids. Improvements to the held book have to come at or before entry, which matches lane A.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneC-post-event-vrp\report.md
