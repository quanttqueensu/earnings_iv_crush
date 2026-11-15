# Freeze note: early_in_industry, 2026-11-13

Written before any held-out outcome is read. The held-out block (hedged event hold, announcement
years 2019 to 2024) has not been opened by this lane for any feature.

## Provenance

This hypothesis was not stated in advance. Round 1 trial 1,749 stated the opposite (late
reporters, whose peers have mostly reported, are over-priced) and failed on discovery with the
wrong sign: Delta -0.057 [-0.120, +0.007], null percentile 2.6. The early-reporter hypothesis is
the mirror, formed from the discovery data (`diag1.log`: monotone across peer-share quintiles) and
scored on discovery as trial 1,759. It is therefore a discovery-derived hypothesis, and the
held-out read below is its only out-of-sample test.

## Hypothesis and mechanism

The seller of the event straddle keeps more residual value on names that report before most of
their industry group. Mechanism accepted before the read: the first reporters of an industry are
priced for two things at once, their own news and the unresolved industry and season-wide news
that nobody has yet seen, and buyers of event protection pay a premium for that common
uncertainty (Savor and Wilson 2016 document a risk premium for early announcers because their
news is informative about the aggregate). Later reporters are priced after peers have printed;
the option market marks their implied move down on the peer read-through, but the remaining
name-specific surprise is under-priced, which is the wrong-sign result of trial 1,749. The
mechanism predicts the effect follows order within the industry, not the calendar date, and
discovery agrees descriptively (events early in the calendar quarter but not early in their
industry: mean cell-residual y -0.064, N=144).

Nearest closed rows: sequential season state (prior realised errors in the season, sign flips),
`season_pos` inside the 375-model zoo (calendar position on megacap), concurrent filers, peer
shock tail gates. This differs in the feature (share of industry-group peers reported, from the
Compustat reporting calendar) and the outcome (tenor-matched residual value on the hedged hold).

## Specification (exactly trial 1,759, code `round2.py`, `lib.py`, `build_features.py`)

- Panel: hedged event hold, status ok, as loaded by the frozen non-price scorer.
- Feature `peer_share`: among Compustat firms in the same GICS industry group (first four digits,
  static latest code) whose fiscal quarter end is within 31 days of the event's own, excluding the
  name, the share with report date strictly before the entry session. At least five peers.
  Timestamp: the session before entry.
- Treated: bottom causal tercile of `peer_share` (breakpoints from strictly earlier announcement
  dates, 200-event burn-in).
- Outcome y: hedged-hold P&L per unit of entry premium, net at the touch. Delta is the
  treated-count-weighted mean of treated minus control within implied-move tercile by tenor cell.
- Inference: bootstrap over announcement dates, 5,000 draws, seed 0; t is Delta over the bootstrap
  standard deviation; null percentile of the treated per-trade Sharpe of H among 5,000
  same-count random draws within cell.

## Held-out read

- Primary, trial 1,770: block 2019 to 2024. Confirmatory pass needs the interval above zero,
  t at least 3 and null percentile at least 95. Anything else is a failure and is reported as
  such; the numbers of a failed read are not findings.
- Secondary, trial 1,771, same read: the within-name version of trial 1,761 (outcome less the
  name's mean over strictly earlier events, at least four). It cannot rescue a failed primary; it
  says whether a pass is position in the season or a fixed property of the names that report
  early.

## Power

Discovery: Delta +0.124, bootstrap standard deviation 0.047, 686 treated of 2,162. The held-out
block has roughly twice the events, so the standard deviation should be near 0.035 and the
smallest effect that reaches t of 3 is about 0.10. The discovery estimate was selected as the best
of 17 trials and will have shrunk; a true effect of half the discovery size would not pass. The
statistic is a difference in means within cell, valid whatever the sign of the book mean.

## Known limits

GICS codes are the latest per name, not point in time. The peer set uses realised report dates of
firms that had already reported, which were public at entry; the denominator assumes every peer
with that fiscal quarter end reports eventually. Treated events tilt to financials and
industrials (32% and 23% of treated on discovery); the sector-neutral contrast on discovery was
+0.131 [+0.025, +0.256] with null percentile 90.1 (trial 1,764). The treated mean of H on
discovery is still negative at the touch (-0.52% of margin), so a pass would establish a relative
selector, not a profitable book.
