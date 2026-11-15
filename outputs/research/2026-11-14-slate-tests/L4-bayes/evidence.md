# L4 sequential Bayesian model: evidence dossier

Panel: `L1-corrections/base_corrected.parquet` (9,350 events, sha256 checked on every read by
`l4lib.load`). Real data throughout; the synthetic checks live in `pipeline_check.log` and the
tests only. Basis: `H_corr` and `residual_value` per trade in % of m0, net at the touch on L1's
basis, not annualised; log scores are mean per-event log predictive densities in nats per event.
Intervals are 95% percentile intervals resampling announcement dates (5,000 draws, seed 0) unless
called credible. Discovery is 2013-18 with rolling-origin scoring of 2015-18. 2019-24 is already
viewed for the hedged-hold outcome family and `block_is_clean` is False for `hedged_event_hold
2025-26` (`diagnosis.log` entry 3, item 6), so every held-out number below is exploratory. The
declarations, the iteration round and the round-2 choice are timestamped in `diagnosis.log`
entries 1 to 5; the freeze is `freeze_online_bayes.md` (self-hashed, with the scorer, package
module, lane helpers, panel and `search_log.csv` hashed). Search count: 800 configurations on
2015-18 (568 for `H_corr`, 232 for `residual_value`), plus one round-2 variant.

## M1 density forecast of H_corr (trials 3,012 to 3,014)

**Nearest closed studies.** The 375-strategy model zoo and the nested walk-forward
(`selection/findings/ml_zoo.md`: no selection skill, gap +0.03 points [-0.46, +0.53]); lane E's
walk-forward boosted trees with cost features removed (`laneE-walk-forward-model/report.md`, fails
held-out, +0.031 of premium [-0.016, +0.077]); lane D's empirical-Bayes jump model. Those score a
point forecast or a sort. This test scores the whole predictive density sequentially, with a
proper scoring rule (Gneiting and Raftery, JASA 2007, recalled), against a baseline that shares
the likelihood and the name level, so the difference isolates what the 15:59 features add. The
sequential conjugate machinery is the dynamic linear model of West and Harrison (1997, recalled)
with a robust scale-mixture update (West 1981, recalled).

**Result.** Champion minus baseline: 2015-18 (fit block, best of the search) +0.0143 [+0.0071,
+0.0218], N 1,806 on 489 dates; 2019-24 +0.0139 [+0.0080, +0.0195], N 5,113 on 872 dates, positive
in all six years (+0.019, +0.023, +0.010, +0.023, +0.006, +0.007); 2025-26 +0.0231 [+0.0134,
+0.0331], N 1,562 on 232 dates. The minimum detectable difference for 2019-24, computed on
discovery before the read, was 0.0065. Calibration: 90% coverage 0.890 [0.880, 0.900] in 2019-24
and 0.908 [0.893, 0.922] in 2025-26; PITs below 0.05 and above 0.95 5.3% and 5.7% (2019-24), 3.8%
and 5.4% (2025-26). Both pass the declared rule, exploratory (`heldout_results.json`,
`trials.csv`).

**Mechanism.** The gain has two layers. The larger one is the likelihood: the champion models the
loss ratio `-H/U` (U the premium sold at the 15:59 bid) through a Yeo-Johnson transform of power
0, so a loss is the log of its payout ratio, with Student-t errors (30 degrees of freedom). The
best model of `H` itself scored -3.760 on 2015-18, with 9.9% of PITs below 0.05 and 0.5% above
0.95; the champion scores -3.699 with 5.4% and 4.7% (`search_log.csv`). The baseline shares that
likelihood, so the trial difference is the features' layer only. Three features carry it, with
stable signs at the end of 2018, 2024 and the run: half-spread +0.066 [+0.055, +0.077], implied
move -0.042 [-0.060, -0.025], tenor (`log1p_dte`) +0.065 [+0.040, +0.089] at the end of the run
(posterior credible intervals, model scale, positive worse for the seller;
`insight_numbers.json`). The term spread excluded zero at the end of 2018 (+0.041 [+0.003,
+0.078]) and sits at -0.009 [-0.030, +0.013] at the end, the same decay that sank the term
selector. Round 2 shows which driver carries the held-out gain: without the two cost features the
model keeps +0.0213 of the +0.0231 (M3 below). The features explain about 4% of the variance of
the transformed outcome (linear predictor sd 0.107 against residual scale 0.511, 2019-24). The
wide 26-feature set, the industry level and feature forgetting did not beat the declared choice
by more than the 1e-4 tie margin on discovery.

## M2 density forecast of residual_value (trials 3,017 to 3,019)

**Nearest closed study.** The residual-value scoring line (state of record, section 2.1), where
selectors are sorted on residual value; no closed study forecasts its density.

**Result.** Champion (wide features, SIC-division level, Student-t 4, premium-share weights)
minus baseline: 2015-18 +0.281 [+0.252, +0.312], N 1,806 (fit block); 2019-24 +0.287 [+0.262,
+0.311], N 5,113; 2025-26 +0.216 [+0.173, +0.259], N 1,562. Coverage 0.881 (2019-24) and 0.857
(2025-26), with 8.8% and 11.1% of PITs below 0.05. Passes, exploratory.

**Mechanism.** Residual value is the extrinsic value left at exit, and it is set largely by
tenor beyond the event, which the baseline does not see. A difference of this size is the
features recovering a mechanical quantity, not an economic forecast, and the under-coverage says
the left tail is still too thin. It is reported for completeness and not used for selection.

## B1 the selected book (trials 3,015, 3,016, 3,020, 3,021)

**Nearest closed studies.** The causal spread gate (`execution/findings/cost_levers.md`;
`selection/findings/final_earnings_set.md`, gated Sharpe -0.224 on broad 2025-26) and the term
selector (`frozen_selector/`, -0.210 [-0.347, -0.058], N 232). The L4 rules differ by acting on a
predictive probability or mean from a model updated after every settlement, not on a fixed
threshold.

**Result.** Against the date-stratified random null (same count on each date):

| Rule, block | Selected | Mean H_corr | Per-trade Sharpe | Null percentile, median | Sel. minus unsel. H |
|---|---|---|---|---|---|
| P(H>0)>0.5, 2019-24 | 3,741 of 5,113 | -0.55 [-1.01, -0.11] | -0.041 [-0.073, -0.008] | 100.0, -1.06 | +2.40 [+1.68, +3.17] |
| E[H]>0, 2019-24 | 1,800 of 5,113 | +0.10 [-0.60, +0.82] | +0.007 [-0.039, +0.057] | 100.0, -0.86 | +1.99 [+1.16, +2.87] |
| P(H>0)>0.5, 2025-26 | 980 of 1,562 | +1.18 [+0.20, +2.17] | +0.081 [+0.014, +0.155] | 100.0, +0.30 | +2.93 [+1.78, +4.16] |
| E[H]>0, 2025-26 | 496 of 1,562 | +2.38 [+1.05, +3.78] | +0.151 [+0.064, +0.255] | 100.0, +0.62 | +3.36 [+1.86, +4.87] |

Selection passes in every block; the economic read fails on 2019-24 and passes on 2025-26, all
exploratory.

**Mechanism.** The selection is mostly the spread. On 2019-24 the P-rule gap by L1 component is
premium +2.56, settlement -0.90 and hedge +0.64 (`decomposition.json`, exploratory): selected
events keep more of their premium at the bid and give part of it back at settlement, which is
what a tight spread does. The decision correlates -0.60 with the half-spread's contribution and
-0.40 with the tenor's, and the rule takes 1,956 of the 1,986 events in the tightest causal
half-spread tercile. The closed spread gate (half-spread below its causal median) on the same
events gives -0.38 [-0.90, +0.15] (N 2,842) in 2019-24 and +1.35 [+0.20, +2.47] (N 609) in
2025-26, overlapping the P rule's selection by 71% and 61%; the counts differ, so this is
descriptive, not a paired test. The selected-minus-unselected residual value (+4.2 to +4.4 in
every held-out book) is the tenor preference read through a quantity that tenor sets, and it
survives inside spread terciles (+3.8 to +6.3 in 2019-24), so it is not separate evidence. The
2025-26 profit sits in a block with a positive pool mean (+0.09), Yahoo hedging at an assumed
3 bp half-spread and 232 dates. The expected-value rule ranks on a Monte Carlo mean (2,000 common
draws) of a quantity whose true mean is minus infinity under a power-0 transform with t errors,
so it is a rule on a trimmed mean, not on an expectation.

## M3 round 2: the champion without cost features (trials 3,022 and 3,023)

Chosen after the 2019-24 read, fixed in advance to one variant, read on 2025-26 only
(`round2.py`, `diagnosis.log` entry 5). Exploratory.

**Result.** The frozen champion without `log_half_spread` and `log_depth`, against the frozen
baseline: +0.0213 [+0.0149, +0.0278], N 1,562 on 232 dates. The full champion beats it by +0.0018
[-0.0065, +0.0098]. Its P(H>0)>0.5 book selects 1,195 of 1,562 at +0.64 [-0.21, +1.51], 99.2nd
percentile of the date-stratified null (median +0.26).

**Mechanism.** The density gain is carried by the implied move and the tenor, not by the cost
features, so the forecaster is not the spread gate in disguise. The book's economics are the
opposite: removing the spread costs about half the 2025-26 selected mean and the interval now
includes zero. The model forecasts outcomes better without the spread, but makes money, where it
does, through the spread.

## F4 the gauge and a mean monitor (no trial; monitoring)

**Nearest prior work.** Wald's sequential probability ratio test and always-valid inference
(Johari et al., OR 2022, recalled), listed in the idea slate. The gauge here is a Bayesian
posterior probability with a Kish design-effect inflation, not a sequential test with error
control.

**Result.** The declared gauge (baseline intercept posterior, design effect 1.37 at the end)
reads, under the transform, P(the median trade gains). It was above 0.5 on all 579 update dates
and said "promote" on 558, the first on 2014-02-18; the final intercept is -0.056 [-0.071, -0.041]
on the loss scale (`heldout_results.json`). The event-weighted mean of settled `H_corr` ends at
-0.97 [-1.26, -0.68], N 9,009, analytic date-clustered interval, and was above zero only on the
first update date with one trade settled (`gauge_book_mean.csv`). The round-2 mean monitor,
using the Gaussian component because the t mean does not exist, puts P(book mean > 0) between
9e-16 and 3e-12 on all 71 update dates of 2025-26, with a typical-trade mean of -1.64 to -1.36
(`round2_results.json`, `round2_mean_monitor.csv`).

**Mechanism.** The median trade keeps part of its premium; the mean is dragged down by the
settlement tail (M1, C1). A gauge on the median promotes a book that loses money on average. Any
stop or promote rule for the paper book has to be stated on the mean, or on a quantile chosen for
the purpose, and the declared gauge should not be used as specified.

## C1 trade cards and the twenty largest surprises (no trial)

**Result.** `trade_cards.parquet` and `trade_cards.csv` hold one row for each of the 9,350 events
(57 columns: forecast, decision, outcome and its L1 components, robust weight, coefficient
shifts). Of the 8,834 scored events, the twenty largest surprises by normalised quantile residual
are all losses beyond the forecast (13 in 2019-24, 6 in 2013-18, 1 in 2025-26; 20 dates, 18
names). Settlement explains 74% of their excess loss over the pool mean; they collected less
premium (12.8 against 20.4% of m0), had shorter tenor (`log1p_dte` 0.76 against 1.66) and lost
6.7 points on the hedge against zero for the pool (`trade_cards_summary.md`).

**Mechanism.** The surprises are gap moves on short-dated, thinly priced straddles, where the
premium is small relative to the move and the delta hedge is stale across the gap. The robust
update down-weighted them (median weight 0.72 against 1.02 for the pool), but the largest single
coefficient shift among them was still 0.0039, above the pool's 99th percentile of 0.0027. The
model learns from these events without being moved much by any one of them, which is what the
scale mixture is for.

## Forward mode

`python -m earnings_iv_crush.research.online_bayes --forward --state posterior_frozen.npz`, with and
without `--dry`, prints N=0 and exits
with code 2 on this machine, because no forward ledger exists (`forward_check.log`). The order
path is not imported (`diagnosis.log` entry 1, with tests).

## What could not be verified

- The West (1981), West and Harrison (1997), Gneiting and Raftery (2007), Dunn and Smyth (1996)
  and Yeo and Johnson (2000) citations are recalled, not checked at source.
- `block_is_clean` was not re-run in this session; the 2025-26 status rests on the team lead's
  statement in entry 3.
- L1's financing and hedge spreads on the Yahoo-hedged 2025-26 block are taken as given.
- `blocks_viewed.csv` holds two identical round-2 rows for 2025-26 from a rerun of the same
  script; the read is one.

Absolute path of this note:
`C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-14-slate-tests\L4-bayes\evidence.md`
