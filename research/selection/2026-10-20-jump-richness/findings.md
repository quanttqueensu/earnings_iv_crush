# Ex-diffusive implied jump against a causal jump forecast

Draft for the analyst's signature. The numbers and the verdict apply the frozen criteria
mechanically.

## Hypothesis, scope and success criteria

Events whose implied announcement jump, isolated by the two-expiry split, is large relative to
a HAR-style forecast from the name's prior announcement moves carry more residual value on the
next-session short straddle. Pre-registration `prereg.md` (71bd7a70...) and amendment 01
(58fdf265..., frozen before any outcome: zero-bid exit legs marked at half the ask rather than
dropped). Pass: top-minus-bottom tercile R_adj lower bound above zero in discovery (2013-2018) and
validation (2019-2024), and the top tercile at the 95th percentile of the matched random null.
Real data: OPRA 15:59 chains, CRSP, IBES announcement dates.

## Results

| Measure | Discovery 2013-2018 |
|---|---|
| Events with a front quote / outcome / signal | 7,773 / 7,581 / 6,726 (both blocks) |
| Exit legs marked at half the ask | 1,976 legs on 1,967 events (both blocks) |
| Tercile-assigned events | 2,041 |
| Top minus bottom R_adj (fraction of margin) | -0.0013 [-0.0037, +0.0013] |
| Top tercile net RoM at the measured cost | -0.28%, matched-null percentile 84.2 |

Control, the next-session front straddle on the same events at the measured cost (1.2714% entry,
3.0182% exit of the mid): -0.53% per trade [-0.95%, -0.13%], N=2,536 (2013-2018), and -0.43%
[-0.77%, -0.10%], N=5,045 (2019-2024).

## Verdict

Fails discovery; closed, validation not run. Removing the diffusive part of the implied move does
not rescue own-history richness. A quarter of exit legs carried a zero bid, which confirms that
any next-session ledger dropping them would have been biased.
