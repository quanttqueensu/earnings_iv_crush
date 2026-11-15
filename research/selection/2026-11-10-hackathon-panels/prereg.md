# Pre-registration: three tests on the hackathon filing and characteristics panels

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-10-hackathon-panels.json`.
Scorer: `research/selection/2026-11-10-hackathon-panels/study.py`.

## Hypothesis

- **P1, pre-announced releases, extended history.** A scheduled release preceded by an Item 2.02
  8-K 3 to 44 days earlier earns the seller more residual value per unit of premium (Rogers,
  Skinner and Van Buskirk, JAE 2009). Trial V3 of the non-price selectors study had this sign on
  2019-21 with 87 treated events and could not pass; this is the same hypothesis on every block
  that trial did not read.
- **P2, fundamentals composite.** Events on names that the option-return literature marks as
  rich to sell (high cash, cash-flow variance, share issuance, external financing and distress;
  low price, profit margin and profitability; Zhan, Han, Cao and Tong, RFS 2022) earn the seller
  more residual value per unit of premium.
- **P3, mispricing direction.** Names with a high composite mispricing score rise against the
  market across the announcement and names with a low score fall, because anomaly returns
  concentrate on earnings days (Engelberg, McLean and Pontiff, JF 2018).

## Data and blocks

- Filing panel: `~/FIAM_Hackathon_2026/temp/8k_20150101_20260831_identified.parquet` (373,139
  8-K filings, 2015-01 to 2026-08, with permno, items and filing date; no acceptance time).
- Characteristics: `~/FIAM_Hackathon_2026/temp/chars_final_with_names.parquet` (monthly, 2015-01
  to 2026-08, 6,561 permnos). Both were supplied for another project and are read in place;
  nothing from them is copied into this repository.
- P1 and P2 outcome, cells and loader: the hedged event hold, exactly as in
  `research/selection/2026-11-10-nonprice-selectors-hedged-hold`, whose module this study imports.
- P3 outcome: the one-night market-adjusted return `R` in
  `outputs/research/2026-11-10-pre-event-direction/events.parquet`, cost 12 basis points per
  position.
- P1 block: one pooled test on announcement dates 2015-04-01 to 2018-12-31 and 2022-01-01 to
  2026-08-31. The years 2019-21 are excluded because V3 read them. This trades the three-step
  rule for power: about 300 treated events are expected against 87.
- P2 and P3 blocks: discovery 2015-18, validation 2019-24, confirmation 2025-26.
- Outcomes viewed before: as listed in the two studies named above, plus their results. No
  outcome has been split by any column of either panel.

## Specification

- **P1.** Treated if the panel holds a filing for the event's permno with form `8-K`, not an
  amendment, items including `2.02`, and filing date between 44 and 3 calendar days before the
  announcement date. Scored only if the permno has a panel filing at least 120 days before the
  announcement. Window as in V3; the filing date replaces the acceptance date because the panel
  carries no acceptance time.
- **Characteristic timing.** The row at the latest month end strictly before the entry date and
  no more than 45 days before it. Each characteristic is first converted to its percentile among
  all panel stocks in that month.
- **P2.** `S` = mean percentile of `cash_at`, `ocfq_saleq_std`, `chcsho_12m`, `netis_at` and
  `o_score`, and of one minus the percentile of `prc`, `ebit_sale` and `ope_be`; at least six of
  the eight required. The eight are the abstract's list less analyst dispersion, which was tested
  separately and failed. Causal quintiles of `S` (200-event burn-in); treated if in the top.
- **P3.** `M` = mean percentile of `mispricing_mgmt` and `mispricing_perf`, both required, in the
  panel's own orientation (higher taken as more underpriced; recalled from the panel's source
  documentation, not verified). Causal quintiles; long the top, short the bottom.
- No parameter was swept.

## Primary statistic and inference

P1 and P2: Delta and the cell-matched null as in the non-price selectors study. P3: mean net
return per position as in the pre-event direction study. Date-clustered bootstrap, 5,000 draws,
seed 0. Secondary and unable to rescue: P1 by sub-block (2015-18, 2022-24, 2025-26) and pooled
with 2019-21; legs of P3.

## Success criterion

P1: pooled Delta interval lower bound above zero and null percentile at least 95. P2: the same
two conditions on discovery, then on validation, then confirmation Delta and treated mean H above
zero. P3: discovery interval lower bound above zero, then validation the same, then confirmation
mean above zero.

## Kill criterion

P1: a miss on either pooled condition closes the idea, including its earlier right-signed
reading. P2, P3: a miss at discovery closes the trial. An interval wholly below zero is reported
as the opposite sign and not rescued.

## Trial accounting

Three trials: P1 1,604, P2 1,605, P3 1,606.
