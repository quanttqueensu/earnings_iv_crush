# Pre-registration: earnings-date shifts and the short earnings straddle

## Hypothesis

Firms that report later than their usual schedule tend to carry worse and more surprising news;
firms that report earlier tend to carry good news (Johnson and So, JFQA 2018, "Time will tell:
information in the timing of scheduled earnings news"; Bagnoli, Kross and Watts, JAR 2002, on late
reporting). If option prices do not fully reflect the extra uncertainty a delay signals, delayed
announcements realise larger moves relative to the implied move, and the short straddle on them
earns less than on on-time announcements. Excluding delayed events from the short book would then
raise its return without selecting on premium size (design input 3: a selector should raise the
realised/implied ratio's gap, not the implied move).

Closest prior work and the difference: Johnson and So study stock returns and analyst forecasts; the
option-market question here (whether the implied move prices the delay) is, to my knowledge, not
tested on traded, quote-marked straddles net of cost. The signal is information the programme has
never used.

## Signal (known before entry)

For each event, the reporting lag L = report date (Compustat `rdq`) minus fiscal period end
(`datadate`), and the same-quarter lag one year earlier L_prev (same `gvkey`, same `fqtr`). The shift
is s = L - L_prev in calendar days. Report dates are scheduled and announced weeks in advance, so s
is public at the entry close. Events are matched to Compustat by ticker with |rdq - announce_date|
at most 3 days; unmatched events are dropped and counted.

Groups: **delayed** s >= +5; **on-time** |s| <= 2; **advanced** s <= -5 (secondary). The +5 margin
absorbs the one-to-two-day weekday drift of a same-weekday schedule. The thresholds were fixed after
inspecting the distribution of s on both blocks (no outcome viewed): megacap 2013-2024, 267 delayed
and 1,287 on-time of 1,792 matched; broad 2025-2026, 369 delayed and 1,385 on-time of 2,028.

## Blocks and outcomes

- **Block M**: the 2013-2024 megacap panel `outputs/research/reverse_alpha/panel.parquet`, outcome
  `return_on_margin` (net, frozen cost model, quote-marked), with `realised_move` and
  `implied_move`.
- **Block B**: the 2025-2026 broad block re-marked for exit-leg attrition,
  `outputs/research/oos_2026_attrition_audit/events.csv`, outcome `net_rom` (11.6%-of-premium cost),
  with `realised_over_implied`.
Neither block has been used for any date-shift signal.

## Primary hypothesis and decision rule

Per block, D = mean net RoM of on-time events minus mean net RoM of delayed events (per trade). Pass
requires all of:
1. Pooled across blocks (events stacked, date-clustered bootstrap on announcement date, 5,000
   draws, seed 0): D > 0 with the 95% interval above zero.
2. D > 0 in each block separately (point estimate).
3. Mechanism: mean realised/implied of delayed events exceeds that of on-time events, pooled, with
   the 95% interval of the difference above zero.
4. Trading-rule check against a matched null: excluding delayed events from the unconditional book
   raises the pooled mean net RoM by more than the 95th percentile of 1,000 random exclusions of the
   same number of events within the same block (seed 0).

DSR against 1,510 trials for the excluded-delayed book's per-trade series.

## Secondary, descriptive only

Advanced versus on-time; D per block with intervals; the shift as a continuous variable (Spearman
of s with net RoM and with realised/implied); BMO versus AMC.

## What is not allowed

No change to thresholds, matching, blocks, outcomes or tests after any outcome is seen. Amendments
are dated, hashed and reported beside the original.
