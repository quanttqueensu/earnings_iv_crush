# Pre-registration: pre-event signals for earnings tail moves

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-12-tail-event-signals.json`.
Scorer: `research/selection/2026-11-12-tail-event-signals/study.py`.

## Hypothesis

The short event straddle loses most of its money on a few events whose reaction exceeds twice the
implied move. On the megacap panel (2013-24, N=1,794) those events are 4.3% of the sample, lose
31.9% of margin on average, and removing them turns the mean net return on margin from -0.59% to
+0.82%. No option-surface feature already in the project ranks them (AUC 0.48 to 0.55). The
hypothesis is that information outside the option surface, available before entry, raises the
probability of such an event beyond what the implied move already prices, so that skipping flagged
events raises the book's mean return.

Seven trials, numbers 1,616 to 1,622:

- **T1, peer shock.** A same-industry peer that reported in the 30 days before entry moved more
  than twice its own implied move. Motivated by FMC (about -26% on 2026-10-29/30) preceding CTVA
  (-22%, 2.5x implied, 2026-11-11) on the same Brazilian credit cause. Related closed test:
  section 2.1 trial B scored the mean residual value on megacaps with return-cluster and SIC-2
  peers and failed; this trial scores the tail on the broad panel with GICS industry peers.
- **T2, distress by Ohlson O-score** (Ohlson, JAR 1980), the free proxy for the issuer's credit
  spread.
- **T3, distress by Altman Z-score** (Altman, JF 1968), the second credit proxy.
- **T4, falling price.** Price far below its 52-week high (George and Hwang, JF 2004 use the same
  ratio for anchoring).
- **T5, earnings variability.** Unstable past earnings imply a wider distribution of surprises.
- **T6, own tail history.** The name had a tail event among its last eight panel events.
- **T7, flag count.** Two or more of T1 to T6 set, among events with all six defined.

## Data and blocks

- Events: `outputs/research/2026-11-02-hedged-event-hold/events.parquet` (status `ok`) for
  2015-2024 and `events_confirm_2025_26.parquet` (status `ok`) for 2025-26. Announcement date and
  permno from `outputs/research/2026-10-20-hedged-hold/features.parquet` joined on ticker and
  entry date.
- Implied move `im = mid0 / F0`, `F0` the front forward. Realised `abs_move` = |reaction-day close
  / F0 - 1|. Ratio `r = abs_move / im`. **Tail** if `r > 2`.
- Money outcome: `B`, the next-day buy-back at the touch (sell at bid, buy back at ask, fees),
  net, fraction of margin `m0`. This is the live book's trade. Events with `B` undefined are kept
  for the tail statistic and dropped for the money statistic.
- Characteristics: `~/FIAM_Hackathon_2026/temp/chars_final_with_names.parquet` (monthly, 2015-01
  to 2026-08, used under the user's standing permission), row for the event's permno at the latest
  `eom` strictly before the entry date and no more than 62 days before it. Accounting variables in
  this file carry the source's own reporting lag.
- Blocks by entry date: **discovery 2015-2019, validation 2020-2024, confirmation 2025-26.**
- Outcomes viewed before: the tail share and option-feature AUCs on the megacap panel, today; the
  2025-26 hedged-hold aggregates by block and under the selectors of trials 1,593 to 1,615. None
  split by any variable below against the tail.

## Specification

- **T1.** Peers: other panel names with the same 6-digit GICS industry (first six digits of
  `gics`) at the event's characteristics month. Treated if any peer event has entry date in
  `[d - 30, d - 1]` calendar days and exit date strictly before `d` (its reaction is known) and
  `r > 2`. Defined if the industry has at least one other panel name.
- **T2.** Percentile of `o_score` within all rows of the characteristics file at that `eom`.
  Treated if at least 0.80.
- **T3.** Percentile of `z_score` likewise. Treated if at most 0.20.
- **T4.** Percentile of `prc_highprc_252d` likewise. Treated if at most 0.20.
- **T5.** Percentile of `earnings_variability` likewise. Treated if at least 0.80.
- **T6.** The name's previous eight panel events with exit date strictly before `d`; treated if
  any has `r > 2`. Defined with at least four previous events.
- **T7.** Treated if two or more of T1 to T6 are set; defined only where all six are defined.
- Cross-sectional quintile cut-offs are the project's standing rule; nothing was swept.

## Primary statistics and inference

For each trial on each block:

1. **Tail lift** `L` = tail rate among treated / tail rate among untreated.
2. **Money gap** `G` = mean `B` treated minus mean `B` untreated (fraction of margin).

Date-clustered percentile bootstrap on entry date (`protocol.date_clustered_ci`), 5,000 draws,
seed 0. Funnel per trial (events, defined, treated, tails among treated).

Secondary, unable to rescue a failure: (a) the matched random null for the gate, the mean `B` of
the kept book (untreated) against 5,000 random skips of the same count from the same defined pool
(`protocol.matched_random_null`, statistic the mean), reported as a percentile; (b) right driver,
mean premium `mid0 / m0` and mean implied move for treated and untreated, so a gap carried by the
gate skipping richer premium rather than avoiding tails is visible. The target is the tail, not
the residual value, by design: this is a skip gate, not a premium selector.

## Success criterion

- **Discovery (2015-2019):** the 95% interval of `L` lies wholly above 1 **and** the 95% interval
  of `G` lies wholly below 0. A miss on either closes the trial.
- **Validation (2020-2024)**, only for trials that pass discovery: the same two conditions.
- **Confirmation (2025-26)**, only for trials that pass validation: `L > 1` and `G < 0` as point
  estimates; intervals reported, as this block is expected to be underpowered.
- A trial that passes all three is a candidate gate for a forward pre-registration, not a change
  to the live book.

## Trial accounting

Seven trials, numbers 1,616 to 1,622. Next free number after this record: 1,623.
