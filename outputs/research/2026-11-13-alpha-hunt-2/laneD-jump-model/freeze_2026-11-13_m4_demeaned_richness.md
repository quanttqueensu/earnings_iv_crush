# Freeze: M4 demeaned residual richness, held-out read

Written 2026-11-13T17:41Z, before any held-out outcome is computed. No outcome in 2013-18 or
2025-26 has been read in this lane.

## Provenance

Discovery-derived. The signal's final form came from four rounds on discovery 2019-24: the
over-dispersed M1 and M2, the 250-session normaliser of M3, the causal recalibration of M4, the
ratio form and the trailing cross-sectional demeaning (both chosen after reading discovery bins).
No block is clean for this feature family (`research/ledger/blocks.csv`: own_history and
term_structure_jump features viewed on the hedged_event_hold panel for 2015-19, 2016-24, 2020-24
and 2025-26; the 2026-10-20 jump-richness study read 2013-18). Whatever it scores, the label is
exploratory.

## Signal (computable at 15:59 on the entry session)

M4 jump model (`lib.run_model_log` with `hyper_m3.json`, recalibrated by `round4.recalibrate`):
log-space empirical Bayes forecast of the reaction-session move scale from the name's decayed
announcement history (half-life 16 announcements), shrunk to its two-digit SIC industry and the
cross-section (kappa 16, kappa_ind 40), elasticity 0.5 to the 250-session daily vol ending the
session before entry, then a causal Mincer-Zarnowitz recalibration (5-year half-life). Model-fair
straddle: the pooled empirical shape of standardised moves before the event's year, scaled by the
forecast, plus Black diffusion at the market's two-expiry diffusive variance over the rest of the
tenor. R_ratio = front 15:59 mid / model-fair value - 1. R_dm = R_ratio minus the median R_ratio of
events in the prior 91 calendar days (at least 30). Treated: top tercile of R_dm with breakpoints
from strictly earlier dates (min 200 prior events).

## Test

Primary (trial 1,897): held-out 2013-18, within-cell treated-minus-control buy-back residual value
yb = B m0 / mid0 (net at the touch, per unit premium), cells implied-move tercile x tenor. Pass:
date-clustered 95% interval above zero and cell-matched random-null percentile >= 95.
Second held-out read (1,898): the same on 2025-26.
Secondary (1,899): the hedged hold, y = H m0 / mid0, 2013-18, same rule.
Right driver (1,900): primary on 2013-18 inside implied-move x tenor x jump-share x half-spread
cells; reported, not a pass condition.

Discovery reference: yb +0.0556 [+0.0119, +0.1002], t 2.46, null 99.7, N 4,633, treated 1,576.
Selected book level reported beside every read (H and B, % of m0, net at touch).

## Code and data fingerprints (SHA-256, first 16 hex)

lib.py BCCF1832E52D65C9; selector.py 7FA3519A31CA67B4; round3.py B933CFEF3A1C3D5E; round4.py
AEB4CA9C6BED48AA; fit_calib2.py E09CE60EE4FA0569; build.py F477FF6F7B107FA8; rich_m4.parquet
0CBDBA0B02FBB7EF.
