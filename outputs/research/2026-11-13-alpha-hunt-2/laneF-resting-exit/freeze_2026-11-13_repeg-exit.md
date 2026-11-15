# Freeze: re-pegged resting bid on the reaction-session buy-back

Written 2026-11-13 after discovery trials 1,931 to 1,950 and before any held-out outcome of this
lane was computed. Each held-out block is read once, with the code as it stands in `lib.py`,
`run.py` and `rounds.py` at this commit of the folder.

## Rule (trial 1,932 as scored on discovery)

On the reaction session, rest a buy limit on each leg of the straddle at its current mid, rounded
up to the penny schedule, re-priced at the top of every minute from 15:00 to 15:58 ET. A leg fills
when a trade prints at or below its limit or the ask falls to it (the brief's rule); fills are paid
at the limit. A leg still open at 15:59:00 lifts the 15:59:00 ask. Provenance: named in the lane
brief and stated before any outcome (not discovery-derived).

## Statistics, held-out blocks

- **H1 (primary):** mean paired improvement over the 15:59:00 ask buy-back, per trade, in m0,
  date-clustered 95% interval (5,000 draws, reaction-session clusters), t from date-clustered
  standard errors. Block: broad 2026 entries (ledger 419 events).
- **H2 (decomposition):** the same improvement minus the event's mean improvement from lifting
  the asks at a minute drawn uniformly from 15:00 to 15:58, with the percentile of the rule's mean
  in 2,000 random-minute draws. Measures liquidity provision net of the time-of-day spread pattern.
  The random-minute benchmark was chosen after the round-1 diagnosis (a measurement device, not a
  selector, but discovery-informed).
- Secondary held-out block, read the same way: megacap 2023-24 (243 events).
- Reported beside them, not gates: fill rates, filled-leg markouts, results by reaction gap
  relative to the implied move, the book level, the same-contract comparison with the hedged hold,
  and a coverage-reweighted mean.

## Pass criteria (both blocks reported; the broad block decides)

H1 mean > 0, interval excluding zero, t >= 3. H2 mean > 0 with interval excluding zero and
percentile >= 95. A pass is still **exploratory**: both blocks were already viewed for a resting
exit outcome by the F1 study (`research/execution/findings/flow_liquidity.md`), so no result here
can be confirmatory.

## Expectations stated before the read

Discovery: H1 +0.68% of m0 [+0.45, +0.90]; H2 +0.28% [+0.12, +0.43]. The 2026 half-spread at
15:00-15:45 is narrower than at 15:59 by less than in 2025, so H1 should shrink. Disclosure: the
path diagnosis (`diag_path.py`) printed the held-out blocks' mean quote paths, including the
taker ask at fixed minutes against 15:59:00 (2026: 15:00 ask -0.18% of m0 against 15:59:00, CI
spanning zero). That is a taker-clock outcome on the held-out blocks, though no resting fill or
rule outcome; it weakens the held-out read further. The hedged hold
comparison is expected to stay negative: on discovery the rule recovers about a third of H - B.
