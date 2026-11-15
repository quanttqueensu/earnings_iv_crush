# Post-score review: resting entry confirmation (trials 1,779 and 1,780)

Reviewer: quant-reviewer agent, post-score slate gate (`docs/PROTOCOL.md` P21). Inputs:
`prereg.md` (SHA-256 aeee3fcc), `amendment_01_renumber.md` (6f6277c9), `review_pre.md`,
`study.py`, the freeze records and run log under `outputs/research/`, and the scored files
`outputs/research/2026-11-13-maker-entry-confirmation/{results.json, events.parquet}`. Every
figure below was recomputed read-only from those files with `protocol.date_clustered_ci` and
`date_clustered_pvalue` (5,000 draws, seed 0) and a CR1 date-clustered t. The scorer was not
re-run and no data was pulled. All results are real data (Databento OPRA `cmbp-1`, 2023-03-28 to
2024-12-31). Unit throughout: per trade (per event), fraction of m0 = 0.20 x forward + entry bid,
gross of commission, one contract per leg.

## Verdict

Both trials pass their frozen criterion, and the criterion was applied exactly as frozen. The
result confirms the sign of 53aa4898 on an unseen block, not its size: the effect is about a
quarter of the size 53aa4898 found, and the two intervals do not overlap. The lever is real but
small. It adds about 0.02 to the per-trade Sharpe of the hedged hold, which leaves the sign of the
book unchanged, and neither trial measures the gain over the entry the paper book actually uses
(the 15:45 mid-first ladder). On this evidence the paper book changes nothing except its planning
figures, which still carry +0.89%.

## 1. Scorer integrity

Supported. The scorer that ran is the frozen scorer plus the logged renumbering and nothing else.

- `study.py` now hashes to 9598c72c, the scorer hash in the amendment record and in both rows of
  `.runs.jsonl` (the `code_change_pre_unblind` at 17:07:14Z and the single `unblinded_run` at
  17:46:38Z, `rerun_reason` null).
- Restoring line 79 to `TRIALS = {"A": 1629, "B": 1630}` (CRLF preserved) reproduces the frozen
  scorer hash 5879d968 byte for byte. The only change is that constant and its trailing comment,
  which label output and do not enter the event set, fills or statistics.
- The prereg (aeee3fcc), the amendment (6f6277c9) and the three frozen inputs (events parquet
  26409320, `research_flow_liquidity.py` 315e2f1e, `research_fills_study.py` e59bece6) match
  their records.
- The block was unseen at the freeze. The earliest tick file was written at 17:02:21Z, 15 seconds
  after the freeze at 17:02:06Z. The pull completed with no failures and no cap halt, spending
  USD 0.1844 against an estimate of USD 0.1844 for 1,712 requests (`pull_status.json`). There is
  exactly one unblinded run.

## 2. Numbers in the run summary

Supported. Every figure in the summary matches the files to the digits quoted. Funnel: window
1,956, status ok 1,712; no missing, empty or early-close tick files (no ok event falls on an
early-close day); 9 events per trial dropped as `leg_unquoted`. The 9 are the same events in both
trials, so each drop is a missing 15:00 quote, which is decided before the order exists and so
cannot depend on the outcome. That is 0.5% of events, against the 1.4% the prereg expected from
the 14:55 window.

| | A (15:00 static mid vs 15:59:00 bid) | B (1-min re-peg vs 15:45:00 bid) |
|---|---|---|
| N, dates, tickers | 1,703, 266, 276 | 1,703, 266, 276 |
| Mean, 95% CI | +0.00217 [+0.00154, +0.00278] | +0.00236 [+0.00195, +0.00278] |
| t (CR1), bootstrap p | 6.78, 0.0002 (floor of 1/5,000) | 11.25, 0.0002 (floor) |
| Per-event SD | 0.0113 | 0.0078 |
| Quote-only mean, CI, t | +0.00120 [+0.00052, +0.00182], 3.57 | +0.00161 [+0.00122, +0.00199], 8.07 |
| Strict minus quote-only | +0.00098 [+0.00082, +0.00115] | +0.00075 [+0.00062, +0.00091] |
| Drift, half-spread | -0.00484, +0.00701 | -0.00355, +0.00591 |
| Both legs, any leg filled | 71.8%, 98.7% | 84.6%, 95.8% |
| Median, share negative | +0.00269, 34.6% | +0.00220, 29.5% |
| Leave-one-ticker-out range | +0.00210 to +0.00224 | +0.00231 to +0.00241 |
| 2023, 2024 | +0.00238 (N 749), +0.00201 (N 954) | +0.00261, +0.00217 |

Parity-offset terciles (A): low +0.0029 [+0.0022, +0.0037], mid +0.0017 [+0.0008, +0.0026],
high +0.0019 [+0.0008, +0.0030]; high minus low -0.0011 [-0.0024, +0.0003]. Fill audit: 24 of
2,903 strict leg fills (0.8%) came from a print above the prevailing ask.

## 3. Criteria applied as frozen

Supported. The code computes `passes = CI low > 0 and t >= 3 and BH pass`, which matches the
success criterion in the prereg. With both p-values at the 0.0002 floor, BH at 5% across two
trials passes both (thresholds 0.025 and 0.05). Both also clear their advisory LOND alphas, 0.0304
and 0.0076. The bootstrap p cannot go below its floor, but the normal p from t (1.2e-11 and
2.3e-29) survives even a Bonferroni correction across all 1,780 trials (threshold about 2.8e-5).
The kill clause, "passes only under the print-based fill rule", is not triggered, because both
quote-only intervals exclude zero. That reading is descriptive, since quote-only was never a
criterion.

## 4. Claims

| # | Claim | Label | Status |
|---|---|---|---|
| C1 | Trial A (1,779) passes: resting at the 15:00 mid improves entry over the 15:59:00 bid by +0.00217 [+0.00154, +0.00278] of m0 per trade, t 6.78, N 1,703 | confirmatory | supported with caveat (C1a to C1d) |
| C2 | Trial B (1,780) passes: one-minute re-pegging improves entry over a plain 15:45:00 cross by +0.00236 [+0.00195, +0.00278], t 11.25, N 1,703 | confirmatory | supported with caveat (C1a to C1d, C2a) |
| C3 | 53aa4898 is confirmed on an unseen block | confirmatory | supported for the sign only; the magnitude is not supported (section 5) |
| C4 | The pass survives a quote-only fill rule | descriptive | supported: A +0.00120 [+0.00052, +0.00182], B +0.00161 [+0.00122, +0.00199] |
| C5 | The half-spread is the driver | descriptive | supported: the improvement is the baseline half-spread less adverse drift; drift gives back 69% (A) and 60% (B) of the half-spread on filled legs, close to the F1 5-minute markout of -0.68 of the half-spread |
| C6 | The strike look-ahead does not carry the effect | descriptive | supported with caveat: the improvement does not rise with the 15:00 parity offset, but the diagnostic is indirect and its interval admits +0.0003, so the prior allowance of about 0.001 stands as an upper-bound adjustment |
| C7 | Print-based fills are a negligible share (24 of 2,903 above the ask) | descriptive | not supported as a reading of fill quality: the count is the narrow audit; the strict minus quote-only gap is 45% of the A effect and 32% of the B effect |
| C8 | Re-pegging (B) beats the static rest (A) | exploratory | not supported: the baselines differ (15:45 against 15:59), the contrast was not pre-registered, and the improvement per filled leg is equal (0.00128 against 0.00131 of m0) |
| C9 | The lever changes the economics of the paper book | descriptive | not supported (section 6) |

Caveats attached to C1 and C2:

- **C1a, fill model.** The strict rule counts any print above the limit as a fill, including
  complex-order legs and auction prints that would not have filled a resting single-leg order
  (OPRA here carries no condition codes). Neither rule models queue position. Quote-only assumes
  the order is first at its price whenever the bid reaches it, so it is the less optimistic rule,
  not a conservative one. Results are for a one-lot; size fills partially at the mid.
- **C1b, strike look-ahead.** The strike is chosen on the 15:59 chain while the order rests from
  15:00 (also from 15:00 to 15:45 in B), which favours the resting arm by an a-priori estimate of
  about 0.001 of m0. Every pass is an upper bound, as pre-registered.
- **C1c, most conservative reading.** Taking the quote-only rule and subtracting the full
  look-ahead allowance gives about +0.0002 for A, with a lower bound below zero, and about
  +0.0006 for B, with a lower bound near +0.0002. On that reading the A improvement cannot be told
  apart from zero, and the B improvement is a few hundredths of a percent of m0.
- **C1d, paper and delayed fills.** Nothing here is evidence about fills on the paper account.
  IB paper fills are simulated, and on a feed without a real-time subscription the quotes are
  about fifteen minutes late (CLAUDE.md landmine). The kill text in the prereg itself says
  promotion to the book needs real fills.
- **C2a, baseline is not the book.** The B baseline is a plain cross at the 15:45:00 bid. The paper
  book enters through a 15:45 to 15:55 ladder that starts at the mid (`docs/RUNBOOK.md`), which
  already recaptures part of that half-spread. The decision-relevant gain of a 15:00 pegged start
  over the ladder the book uses is smaller than +0.00236 and unmeasured.

## 5. The fourfold shrinkage from 53aa4898

53aa4898 found +0.0089 [+0.0077, +0.0101] (2025-26, N 1,136) and trial A finds +0.00217
[+0.00154, +0.00278], a ratio of 4.1 with intervals that do not overlap. Checked on the scored
files:

- **m0 basis: none.** On the 2025-26 events, the ratio of the tick-rebuilt m0 to the chain m0 has
  median 1.000. Re-expressed on the chain basis, the 53aa4898 mean is +0.00889.
- **Contract: none.** The 53aa4898 strike differs from the strike of the hedged-hold front
  straddle on 59% of its events (the expiry never differs). Its mean is +0.0100 where the
  contracts match and +0.0082 where they differ, so both groups sit about four times above this
  block.
- **Ticker composition: none.** On the 247 tickers the two blocks share, 2025-26 gives +0.0100
  (N 917) and 2023-24 gives +0.0021 (N 1,520).
- **Fill rate: the wrong sign.** Fills are more frequent here (1.71 legs per event, against 1.55).
  The whole shrinkage sits in the improvement per filled leg: 0.00573 of m0 there, 0.00128 here
  (4.5 times).
- **14:55 window: negligible.** Nine events.
- **Not separable with these files.** The candidates left are the market era, the sample
  construction of 53aa4898 (ledger attrition left 1,136 of 1,597 events, and F1 had already seen
  fills on that block), and any difference in the tick pipeline between the two pulls. The
  pattern points at a level break at the block boundary rather than a trend: 2023 gives +0.0024
  and 2024 gives +0.0020 here, while 2025 gives +0.0087 and 2026 gives +0.0092 in 53aa4898. A
  step at the boundary fits a sample or pipeline difference at least as well as a gradual market
  change. Running the drift and half-spread split on the 2025-26 tick files already on disk would
  show whether the old block had wider half-spreads or less adverse drift. That block is already
  viewed, so the run would be descriptive and needs no new trial.

Conclusion: the confirmation figure replaces 0.0089 as the size of the lever. 0.0089 should not
be quoted as the expected size of the lever.

## 6. Economic significance

- **Per trade.** A gives +0.00217 of m0, about 0.9% to 1.2% of the entry straddle premium
  (ratio-of-means and mean-of-ratios). In dollars per one-lot straddle the mean is USD 8.20 and
  the median USD 5.00 (one 0.05 tick on one leg), or USD 5.74 at the median m0 of USD 26.40 per
  share. B gives a mean of USD 9.14. Under quote-only, A is about USD 3.2 at the median m0. The
  53aa4898 figure was a mean of USD 41.
- **Against the book.** On these 1,703 events the hedged hold (2019-24 discovery block, already
  viewed, descriptive) has a mean of -0.0090 of m0 and a per-trade SD of 0.126, a per-trade Sharpe
  of -0.071. Adding A gives -0.054. The lever moves per-trade Sharpe by about +0.017 and leaves
  the sign of the book unchanged. The H plus B figure (-0.053) mixes a 15:45 baseline with a 15:59
  book and is illustrative only. On peak Reg-T capital (about 2.8 m0 on the addendum basis;
  median peak hedge notional 3.57 m0 here), A is about +0.08% per trade. For scale, the exit
  lever is +1.7% to +2.8% of m0, about ten times larger.
- **Decision for the paper book.** No change to the order path follows from this result. The
  forward plan does need restating:
  `research/execution/2026-11-02-maker-entry-hedged-hold/forward_test_addendum.md` still uses
  +0.89% for the entry lever, an imputed book of +0.64% to +0.79% of m0, and an F-H2 power
  plan built on an expected difference "smaller than +0.89%". At the SD of this block (0.011) the
  F-H2 half-width at 300 events is about +/-0.36% of m0, against an effect over the plain cross of
  at most 0.24% and a smaller one over the ladder. As planned, F-H2 cannot detect the effect, and
  on delayed or simulated paper fills it would not be evidence even if it did.

## 7. First practitioner objections

1. "Your fills are prints, not your order." The strict rule fills on any print through the limit,
   and 45% of the A effect disappears under quote-only. The answer is C4. The objection still
   stands for queue position and for complex and auction prints, which need real order
   lifecycles to settle.
2. "You picked the strike at 15:59." Pre-registered, and C6 shows no dose-response. The
   allowance of about 0.001 is half the A effect, and under C1c A is not distinguishable from
   zero.
3. "Five dollars a straddle against a twelve-point SD." Correct (section 6). The lever is a cost
   refinement, not a source of return.
4. "Your baseline is a strawman." For B it partly is (C2a): the book already starts its ladder at
   the mid.
5. "The prior study said four times more." It did. Section 5 rules out m0, contract and ticker
   explanations and leaves block construction or era unresolved.

## 8. Bookkeeping (minor)

- `research/ledger/trials.csv` rows 66 and 67 (1,779 and 1,780) still read `pending`. They need
  the PASS verdicts.
- `docs/RESEARCH_STATE.md` has no row for 53aa4898, 1,779 or 1,780, although the prereg said they
  would be entered. The amendment notes that the 117 alpha-hunt variants also lack rows.
- The amendment record has `n_trials_declared` 1,780, the cumulative count, while the base record
  has 2, the slate size. Same field, two meanings.
- The prereg power plan assumed SD 0.0205. The realised SD is 0.0113, which gave more power, so
  nothing follows.
- The study folder holds a stray `__pycache__`.

## 9. Checklist

The result passes the annualisation check (no annualised figure), selectivity (paired on
identical events), provenance (real data, figures traced to logged files), silent degradation
(the funnel is complete and the drops are pre-order) and in-sample against out-of-sample (one
unseen block, no parameter fitted, the trial count is recorded). It carries caveats on fill
realism (C1a, C1d), look-ahead (C1b, C6) and attribution (C5 is consistent with the claimed
driver). It does not support the magnitude claim of 53aa4898 (C3) or any change to the economics
of the paper book (C9). One new failure class for the ledger, matching no existing entry: a lever
measured against a counterfactual baseline that the live book does not use (a plain cross where
the book ladders from the mid), so the measured gain overstates the gain that matters for the
decision.
