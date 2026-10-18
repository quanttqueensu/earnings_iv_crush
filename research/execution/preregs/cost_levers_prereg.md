# Pre-registration: the two remaining cost levers, and the decision rule they feed

Frozen before either test below is computed. Nothing in this file may change after an
outcome is viewed; a change requires a separate dated amendment, and both are reported. The
SHA-256 of this file is recorded in `outputs/research/prereg_cost_levers.json`.

## Why these two

The announcement premium is present gross (+3.44% return on margin unconditionally on the
2025-26 block) and cost takes most of it (net +0.49%, per-trade Sharpe +0.043, CI
[-0.026, +0.120]). No price- or surface-based selector has survived out of sample. These two
tests attack the binding constraint directly and are the last free ones on the programme
(state of record, sections 2.2 and 2.3).

## Decision rule (binding, written before either result)

If test H fails its primary criterion **and** test S fails its primary criterion, the
single-name earnings straddle stops being the project's vehicle. Work moves to scheduled-event
volatility in another market, starting with the free Deribit macro-event pilot, carrying the
event decomposition, quote marking, cost measurement, causal gating and matched-null scoring
across unchanged. If either passes, the passing lever goes to its confirmation block before
anything else is started.

## Test H: conditional hold to expiry, validated on 2013-2018

**Hypothesis.** Holding the short straddle to its front expiry, except on events with the
largest priced moves, beats buying it back at the next session close, because it avoids
paying the exit spread and the post-event implied volatility that stays above the cleaned
level (`clean_iv/findings.md`, section 2).

**What has already been viewed on this block, stated so it is not mistaken for independence.**
The *unconditional* hold on the frozen 2013-2018 book was computed earlier
(`hold_decomposition.csv`): on the measured basis next-session exit per-trade Sharpe +0.0143,
hold -0.0451, mean paired difference -0.0116 of margin, with the extra-exposure component
-0.0186, CI [-0.0373, -0.0004]. The conditional rule's result on this block has not been
computed. The 2023-2024 evidence for the rule (+0.0313 of margin, n=66) was scored on the
legacy basis that charged an 8.55% exit half-cross; under the measured basis the exit cross is
3.0182%, so the prior evidence overstates the saving.

**Population, primary.** The frozen term-gated 2013-2018 book, 193 trades, per-trade inputs from
`outputs/research/hold_decomposition_trades.csv` (entry credit, next-session exit mark,
settlement intrinsic at expiry, contracts times multiplier, margin). Harness: the measured
basis must reproduce next-session Sharpe +0.014297 and hold -0.045105 or the run aborts.

**Population, secondary (reported, not decisive).** Every 2013-2018 event in
`reverse_alpha/panel.parquet`, settlement intrinsic at the front expiry recomputed from CRSP
as-traded closes (`equities.fetch_equity_ohlcv_crsp`), at the stored strike.

**Rule.** Exit at the next session close if the event's `implied_move` is at or above the causal
expanding 0.70 quantile of `implied_move` over strictly earlier events in the same block of the
panel (minimum 25 prior); otherwise hold to expiry. The 0.70 cut is the one chosen in sample
(`hold_holdout.csv`) and is not re-chosen. Events with fewer than 25 priors follow the
next-session exit. A second specification, the original block percentile (0.70 quantile of the
block's own implied-move distribution, which uses look-ahead within the block), is reported for
comparison with the 2023-2024 result only.

**Costs, primary (measured 15:59 basis).** Entry 1.2714% of entry premium. Next-session exit
3.0182% of exit premium. Held to expiry: no option exit cost; the in-the-money leg is assigned,
and flattening the shares is charged 2 basis points of strike times contracts times multiplier.
Weekend and overnight gap risk on assigned shares, and pin risk near the strike, are not
modelled and are stated as such beside the result.

**Costs, secondary.** Flat 11.6% of entry premium round trip for next-session exit, half of it
(5.8%) for a held position.

**Success criterion (primary).** On the 2013-2018 frozen book, the mean paired advantage of the
conditional book over next-session exit, in net return on margin on the measured basis, has a
date-clustered 95% CI (5,000 draws, seed 0) that excludes zero and is positive.

**Integrity checks that abort the run.** Any settlement intrinsic above half the strike (a
split-basis defect); any join that loses an event without being printed in the funnel.

## Test S: causal spread gate on both megacap blocks

**Hypothesis.** Declining events whose expected round-trip cost is high, using only cost
information available at entry, leaves a book whose premium survives net.

**Counter-hypothesis, pre-stated and tested either way.** Tight-spread names are the most
efficiently priced, so the gate removes premium along with cost. Reported as the gated book's
mean gross return on margin at the mid against the ungated book's.

**Population.** Every event in `reverse_alpha/panel.parquet` with entry and exit quotes on the
traded contract in `reverse_alpha/quotes.parquet`, scored per block: 2013-2018 and 2019-2024.

**P&L basis, primary.** Quoted touch, event by event: sell at the entry bid, buy back at the exit
ask, `(entry_bid - exit_ask) * contracts * 100 / margin`. A flat percentage cost would charge
every event alike and make a cost gate meaningless, so the primary basis must be event-specific.
The measured flat basis is reported as a diagnostic of whether the gate also selects on pricing.

**Signal.** Expected round-trip cost at entry:

    c_i = (entry_ask - entry_bid) / (entry_ask + entry_bid)
          + mean over the name's prior events of (exit_ask - exit_bid) / (exit_ask + exit_bid)

The first term is the current event's entry half-spread relative to mid, observable at 15:59.
The second uses only the name's earlier events whose exit session is before this entry, with at
least 3 such events; otherwise the event is ineligible.

**Rule.** Trade if `c_i` is at or below the causal expanding 0.50 quantile of `c` over strictly
earlier eligible events in the block (minimum 25 prior).

**Comparisons.** The ungated book (every eligible event), and a participation-matched random
null: 1,000 draws of the gated count from the eligible events, seed 0.

**Success criterion (primary).** On **each** block separately: the gated book's per-trade Sharpe of
touch-basis net return on margin has a date-clustered 95% CI excluding zero and positive, **and**
it exceeds the median Sharpe of the matched null.

## Trial accounting

Two trials, one per test. Base 1,489 after the section 2.1 pre-registration (three declared,
none yet run); DSR reported against 1,491. No cut, cost, window or population is varied after an
outcome is viewed.
