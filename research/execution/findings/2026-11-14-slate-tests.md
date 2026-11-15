# Slate tests, 2026-11-14 to 15: summary

Artefacts (lane folders, scripts, logs and per-event files) are in `outputs/research/2026-11-14-slate-tests/`, which is shared through the R2 bucket, not git: `python -m earnings_iv_crush.data.sync pull --only outputs/research`. Paths below are relative to that folder unless they start at the repository root.

The programme tested the runnable ideas of `outputs/research/2026-11-14-idea-slate/IDEAS.md` and
built a sequential Bayesian model of per-trade P&L. Rules are in `BRIEF.md` and `LANES.md`; trial
numbers were reserved in `RESERVED_TRIAL_IDS.md` before any lane started. Four lanes ran:

- L1, valuation corrections;
- L2, execution and cost;
- L3, selection and other markets;
- L4, the Bayesian model, with a card for every trade.

An independent review checked the files, not the conclusions.

Everything is exploratory. Freeze notes hash themselves and their scorers but were not filed as
pre-registrations. The 2019-24 block had been viewed before for nearly every outcome family, and
`block_is_clean` is False for `hedged_event_hold 2025-26`. All data are real: CRSP, the cached
Databento chains and ticks, Alpaca daily bars, FRED and free public fee schedules. No paid pull was
made.

**Basis, unless a row says otherwise.** Per trade, % of m0 (0.20 times the 15:59 parity forward
plus the 15:59 straddle bid), net at the touch, not annualised. Intervals are date-clustered 95%.

## Verdict

No idea produced a tradeable edge.

- **The book is negative.** The corrected book loses about 1.0 to 1.3% of m0 per trade on
  2013-24, and slightly more once the stock commission it never charged is added.
- **What survives is cost recovery.** The tight-strike and strangle levers survive netting, a
  0.30 delta band recovers the new commission, and closing-auction hedging would save a little.
  None comes close to the gap.
- **The Bayesian model learns real structure about the distribution of outcomes.** Its density
  forecast beats its baseline on 2019-24, in every year. But the trades it selects do not make
  money beyond what a tight-spread screen gives.

## The corrected book

From `L1-corrections/CORRECTIONS.md`, with the hedge commission from
`L2-execution/hedge_commission.parquet`. IB Tiered pricing is recalled, not verified.

| Block | `H` as stored | `H_corr` (netted, early call exercise, financing) | Net of commission, 1 contract | N |
|---|---|---|---|---|
| 2013-18 | -1.04 [-1.49, -0.57] | -0.98 [-1.43, -0.52] | -1.20 [-1.66, -0.74] | 2,640 |
| 2019-24 | -1.27 [-1.68, -0.87] | -1.19 [-1.59, -0.80] | -1.33 [-1.73, -0.94] | 5,113 |
| 2025-26 | -0.05 [-0.86, +0.71] | +0.09 [-0.72, +0.85] | -0.02 [-0.83, +0.74] | 1,562 |

Correction sizes, paired, for 2013-18 and 2019-24:

| Correction | 2013-18 | 2019-24 |
|---|---|---|
| Netting | +0.22 | +0.22 |
| Early call exercise before ex-dates | -0.09 | -0.08 |
| Financing | -0.08 | -0.07 |
| Stock commission | -0.22 | -0.14 |

- **Early call exercise.** This is an upper bound on the writer's cost, since it assumes every
  holder exercises optimally. It sits inside the bound the earnings-adjacent hunt gave.
- **The paper book's ex-date skip.** The events it drops are better than the ones it keeps, by
  +1.36 [+0.21, +2.50] in 2013-18. Pricing assignment instead of skipping is no worse.
- **The equity cost convention.** It is max(half-spread, 1 bp), a floor. Earlier briefs and the
  2026-11-14 SUMMARY describe it as half-spread plus 1 bp.

## Results by idea

| Idea | Trials | Result | Verdict |
|---|---|---|---|
| A1 re-strike the 2025-26 ledger | 2,836-2,838 | mean ln(F/K) from +186 bp to +2.1 bp; per-trade Sharpe, frozen scorer (RoM at mids net of 11.6% of premium): unconditional +0.017 [-0.052, +0.090], N=1,312; term gate -0.325 [-0.462, -0.186], N=239 | the term gate is worse once struck correctly; 622 exit-unquoted drops are untested for outcome dependence |
| A2, A3 early call exercise, financing | (corrections) | see the table above | adopted into `H_corr` |
| A4 OCC special dividends | descriptive | under 0.01 on block means | negligible |
| A5 1,819 and 1,826 under netting | 2,832-2,835 | 1,819 +0.211 [+0.140, +0.284], N=5,092; 1,826 +0.495 [+0.340, +0.649], N=5,041 (2019-24) | both survive; 1,826's wing drops are worse events, correlated with a small implied move |
| A6 53aa4898 on correct strikes | 2,839-2,840 | +0.997 [+0.802, +1.200] on 464 of 1,136 events; in premium units 5.1% [4.0, 6.4] against 4.5% [3.7, 5.6] on the rest | lever survives; the subset inflates the m0-basis figure by about 10% |
| A7 trial count | descriptive | 2,185 on the 1,532 base before this programme | see accounting below |
| B1 closing-auction hedge | 2,892-2,895 | like for like at 0.5 bp: +0.095 [+0.086, +0.106] (2019-24); break-even impact at least 1.85 to 2.59 bp | assumption-based (no auction data); declared comparison invalid (fee asymmetry) |
| B2 minimum-variance delta | 2,902 | variance ratio 1.0020 [0.9983, 1.0056] (2019-24) | fails |
| B4 capacity | 2,903-2,904 | 1,779 falls to +0.069 at 5 lots (upper bound); 1,819 to +0.076 at 25 lots | levers shrink fast with size |
| B5 entry minute by spread state | 2,905 | +0.053 [-0.059, +0.161], N=213 | fails discovery |
| B6 per-event expiry choice | 2,901 | +0.001 [-0.059, +0.056] (2019-24) | fails |
| B8 strangle width from the move forecast | 2,906 | 2019-24 +0.087 [+0.023, +0.152]; 2025-26 -0.163 [-0.288, -0.032] | fails (reverses) |
| B10 fees | 2,896-2,900 | hedge commission -0.22, -0.14, -0.11 by block (Tiered, 1 contract) | cost-basis defect: `H_corr` omits it |
| B11 0.30 delta band with commission | 2,907-2,916 | +0.130 [+0.058, +0.203] (2019-24, read once); before commission +0.067 [-0.005, +0.138] | recovers the commission only; not an edge |
| C1 implied borrow | 2,952 | residual value +0.516 [-0.532, +1.625], null percentile 86 | fails discovery |
| C3 first reports after listing | none | N=13; minimum detectable effect 3.9% | underpowered |
| C8 D-1 option-to-stock volume | 2,953 | held-out `H_corr` -0.295 [-2.444, +1.736], N=562; tenor carries about 80% of the residual-value lift | fails held-out |
| C2 short interest | none | no free, unregistered source for 2013-18 | blocked |
| E5 ForecastEx index contracts | 2,954 | +0.044 [-0.044, +0.126] per contract, 62 trades | fails discovery |
| F3 session concentration cap | descriptive | lowers risk only by trading less | risk claim withdrawn |
| L4 Bayesian density (M1) | 3,012-3,014 | log score against the baseline: +0.0139 [+0.0080, +0.0195] nats per event, N=5,113 (2019-24); +0.0231 (2025-26); 90% coverage 0.890 | passes as a forecast, exploratory |
| L4 selected book | 3,015, 3,016, 3,020, 3,021 | 2019-24 P rule -0.55 [-1.01, -0.11], N=3,741, beats the null but loses; 2025-26 gains are 85 to 88% a tight-spread screen | fails economically |
| L4 residual-value density (M2) | 3,017-3,019 | +0.287 nats | tenor recovering a mechanical quantity |
| L4 round 2, no cost features | 3,022-3,023 | density gain unchanged; book +0.64 [-0.21, +1.51] | the money, where any, is the spread |

## What the Bayesian model says

These readings come from `L4-bayes/insight.md` and the trade cards.

- **What carries the forecast.** Three 15:59 features carry it, with stable signs:
  - option half-spread +0.066 [+0.055, +0.077];
  - implied move -0.042 [-0.060, -0.025];
  - tenor +0.065 [+0.040, +0.089].

  These are posterior coefficients on the model scale.
- **The term spread fades.** It was +0.041 at the end of 2018 and decays to -0.009
  [-0.030, +0.013], which is the term selector's failure seen from inside the model.
- **The likelihood mattered more than the features.** A log transform of the loss ratio with
  t(30) errors carried most of the improvement. The wide feature set, an industry level and
  discounting all tied the declared set.
- **The largest surprises.** The twenty largest are all losses. Settlement explains 74% of their
  excess loss, and they are short-tenor, low-premium events.
- **The book gauge.** As specified, it measured the probability that the median trade gains,
  not the mean. That gauge stayed above 0.5 throughout while the book mean ended at -0.97
  [-1.26, -0.68]. Any stop or promote rule must be on the mean.
- **The expected-value rule.** The champion's predictive mean is minus infinity, so its
  "expected-value" rule is really a cut on the median net of dispersion. Its selection size is set
  by the Monte Carlo draw count.

## Review corrections

These are the findings of the independent review, applied here. The lanes' own files are left as
written.

1. **L4 trials 3,016 and 3,021.** Read "fails as a selector; the 2025-26 gains are a tight-spread
   screen", not "pass". A selector taking the same number of tightest-spread events per date
   shares 88% and 85% of events and earns +1.00 [+0.11, +1.89] and +1.96 [+0.71, +3.21] on its
   own.
2. **L4 rule names.** Trials 3,020 and 3,021 are a median-minus-dispersion cut, not an
   expected-value rule.
3. **L1 process.** L1 has no freeze notes. Four of its scripts were saved after their runs and
   not re-run. Its `blocks_viewed.csv` times record when rows were written, not when blocks were
   read. The A1 mechanism numbers and the A5 vega-matched netting figures trace to no file and are
   not cited here.
4. **A6 basis.** The lever should be read in premium units, because the subset is selected.
5. **A1 attrition.** The 622 exit-unquoted drops have no outcome-dependence test.
6. **L4 records.**
   - `round2.py` was edited between its two 2025-26 reads.
   - `decompose_selection.py` and `trade_cards.py` re-read the held-out blocks without block rows.
   - The spread-gate comparison is a scored rule without a trial number. It is charged as 3,073.
7. **L2 statistic switch.** It reused 2,893 for B1's like-for-like statistic switch, which is
   charged as 3,072.
8. **L4 gauge cause.** The gauge failure comes from the round-1 transform, not from the declared
   gauge as such.
9. **L4 monitor.** Its round-2 mean monitor is cumulative from 2013 and reaches -94,573 on one
   date. Do not quote it.
10. **Annualised Sharpes.** `L1-corrections/a1_results.json` holds annualised Sharpes; none is
    quoted anywhere.
11. **New failure classes.** Three:
    - a baseline that omits a fee biases a declared A-against-B comparison and fires its kill rule;
    - a decision threshold set on a Monte Carlo mean of a quantity with no finite mean;
    - log timestamps that are not a clock, or scripts saved after the run that produced their
      outputs.

## Trial accounting

Trial numbers charged:

| Source | Trials | Numbers |
|---|---|---|
| L1 | 9 | 2,832 to 2,840 |
| L2 | 25 | 2,892 to 2,916 |
| L3 | 3 | 2,952 to 2,954 (2,955 named, never scored) |
| L4 | 12 | 3,012 to 3,023 |
| Team lead | 2 | 3,072, 3,073 (review items 6 and 7) |
| **Total** | **51** | |

For deflation, L4's density model should be charged its search: 800 configurations at least,
since its first discovery runs predate `search_log.csv`. One `exploratory-unhashed` row per lane is
appended to `research/ledger/trials.csv` and the lanes' block views to `blocks.csv` by
`ledger_entries.py`.

## What is left

- **The unconditional book.** Nothing here moves it to zero.
- **Corrections to carry forward.**
  - Adopt the stock commission and the delta band together into the valuation. Both are cost
    corrections, computable without reading outcomes.
  - Re-quote the 2025-26 headline from the re-struck ledger.
  - Restate the stale 2025-26 headline (-0.2095 and +0.043) wherever it is still quoted; it
    came from the defective strike.
- **Forward candidates.** Two remain, and neither has a clean historical block:
  - the stacked execution book (resting entry, tight strike or netted strangle, a delta band, a
    closing-auction hedge);
  - the Bayesian density model as a forecaster, monitored on the mean.

Both need a forward pre-registration.
