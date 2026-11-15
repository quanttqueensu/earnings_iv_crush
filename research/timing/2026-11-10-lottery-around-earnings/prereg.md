# Pre-registration: lottery-like stocks before and after the earnings announcement

Frozen before any outcome for the declared blocks is computed. Record:
`outputs/research/prereg_2026-11-10-lottery-around-earnings.json`.
Scorer: `research/timing/2026-11-10-lottery-around-earnings/study.py`.

## Hypothesis

Speculative demand for lottery-like stocks peaks ahead of earnings and unwinds afterwards. Liu,
Wang, Yu and Zhao (working paper 2018, "Time-varying demand for lottery: speculation ahead of
earnings announcements") report that lottery-like stocks beat non-lottery stocks by about 52
basis points over the five days before the announcement and give back about 80 over the five
days after. Two trials:

- **LP, run-up.** Long lottery-like and short non-lottery names over the five sessions ending at
  the entry close earns a positive net return.
- **LR, reversal.** Short lottery-like and long non-lottery names from the entry close through
  the reaction session and the four sessions after it earns a positive net return.

## Data and blocks

Events, prices and SPY hedge as in `research/timing/2026-11-10-pre-event-direction` (its
`events.parquet` and price cache). Characteristics from
`~/FIAM_Hackathon_2026/temp/chars_final_with_names.parquet`, read in place. Blocks by exit date:
discovery 2015-18, validation 2019-24, confirmation 2025-26. Outcomes viewed before: the
one-night return has been split by eleven signals in two studies today, none of them a lottery
measure; the five-session windows before and after have not been computed for any signal. IVOL
and MAX were tested as selectors of option P&L, not of the stock return.

## Specification

- Lottery score: mean of the monthly cross-sectional percentiles of `ivol_ff3_21d`,
  `iskew_ff3_21d` and `rmax1_21d`, and of one minus the percentile of `prc`; at least three of
  the four. These are four of the paper's five proxies (jackpot probability is not in the panel).
  Taken at the latest month end at least 8 calendar days before the entry date and no more than
  53 days before it, so it predates the run-up window.
- Causal quintiles (`hedged_hold.causal_bins`, 200-event burn-in). Lottery-like is the top
  quintile, non-lottery the bottom.
- With `e` the entry session and `x` the exit session in the price series of the name, `P` the
  adjusted close and `M` SPY: `R_pre = P[e]/P[e-5] - 1 - (M[e]/M[e-5] - 1)` and
  `R_post = P[x+4]/P[e] - 1 - (M[x+4]/M[e] - 1)`.
- LP: long top, short bottom, outcome `R_pre`. LR: short top, long bottom, outcome `R_post`.
- Cost 12 basis points per position, round trip. No parameter swept.

## Primary statistic and inference

Mean net return per position over both legs, date-clustered bootstrap on exit date, 5,000 draws,
seed 0. Secondary, unable to rescue: legs separately, megacap and broad separately, gross.

## Success criterion

Per trial: discovery interval lower bound above zero, then validation the same, then confirmation
mean above zero.

## Kill criterion

A discovery miss closes the trial. An interval wholly below zero is reported as the opposite sign
and not rescued.

## Trial accounting

Two trials: LP 1,609 and LR 1,610.
