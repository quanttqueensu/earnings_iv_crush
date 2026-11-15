# Lane G: index and sector ETF options on mega-cap earnings nights

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log` and round logs. Every
figure is from those files.

## Verdict

Nothing survived the held-out read, and no book is net positive at the touch. QQQ options price
the mega-cap earnings night at about what it delivers, so there is no event premium to sell,
however cheap the spread. Every result is exploratory: the frozen index study
`research/off_earnings/2026-11-01-index-event-crush` (family B2) had already scored short QQQ on
mega-cap nights against controls on the same blocks (P, M and C) and failed. Trials 1,961 to
1,984; 1,985 to 1,990 unused.

## Data at zero spend

SPY, QQQ and IWM come from the already-paid Databento cache: 15:59 and 10:00 snapshots, every
session from 2016-01-04 to 2026-10-30, expiries within ten calendar days, about 2,700 sessions each,
with one to three dropped trades per ticker. XLK and SMH are not in that cache. DoltHub has XLK on
only 3 of 8 sampled sessions in 2022 and 2024 (nearest expiry 11 to 17 days out) and QQQ on none
of 11, so a one-night sector-ETF trade cannot be priced for free and the test ran on QQQ. The QQQ
front straddle's median half-spread is 0.56% of premium at 15:59 in 2019-24 (0.37 to 0.46% in
2025-26) and 1.4 to 2.1% at 10:00.

Controls: non-event nights with the same weekday and days to expiry, prior-close VIX within 15%,
within 60 sessions. Margin is premium plus 15% of the forward. Figures are per trade, net at the
touch.

## Results

**The event is priced fairly (trial 1,961, descriptive).** On block M, the implied extra variance
for the night, read from the term structure, exceeds matched controls by 6.3e-5 [3.6e-5, 9.0e-5]
(N=79); the realised extra one-night variance is 9.3e-5 [1.5e-5, 17.9e-5]. P: 4.8e-5 implied
against 5.0e-5 realised (N=40); C: 6.5e-5 against 6.6e-5 (N=32). Both are about twice what
independent single-name jumps would imply: the market prices a correlated, sector-wide jump, and
that is what happens.

| Trial | Trade | Block | Effect | 95% CI | Null pct | Label |
|---|---|---|---|---|---|---|
| 1,962 | Short QQQ front straddle on heavy-weight nights, vs controls | M | -0.21% of margin | [-1.60, +1.00] | 34.2 | Fail |
| 1,970 | Short QQQ front, 15:59 to 10:00, vs controls | M | +0.08% of margin | [-0.33, +0.46] | 71.0 | Fail; level -0.30% |
| 1,980 | Long QQQ 10:00 to 15:59 after a release with an overnight gap of at least 0.61% (discovery-derived) | M | +8.3% of debit | [+0.0, +17.3] | 97.2 | Frozen |
| 1,980 | Same, frozen | C (held-out) | +3.1% of debit | [-8.6, +16.0] | 74.4 | Fail; level -0.7% |
| 1,984 | Release effect after gap, VIX, tenor and weekday controls | C (held-out) | +0.0% of debit | [-9.2, +9.8] | n/a | Fail |

## Iteration story

Round 1: short QQQ on heavy-weight nights failed. The worst events were sector sell-offs
(2024-07-23, GOOGL and TSLA, lost 15% of margin; 2022-04-28, AAPL and AMZN), so a mega-cap miss
moves the whole sector and that tail is priced. The long side failed too: B2's "realised far above
implied" came from multi-day premium that dilutes the one-night part, and measured from the term
structure the gap disappears. The IWM placebo showed an earnings-season confound (t -2.9 on M).
Round 2 differenced against IWM, shortened the hold and settled at the next-day expiry: all flat or
negative, and two or more reporters on a night is worse, not better. Round 4 found the long
straddle from 10:00 to 15:59 on the session after a release (+4.7% of debit on M) carried by a few
continuation days (2024-08-01 META, 2020-07-23 TSLA and MSFT, 2022-04-29 AAPL and AMZN, 2023-07-27
META); its round-4 scorer printed blocks C and P beside M, so trial 1,977's held-out read was spent.
Round 5 conditioned on the overnight gap, which on M reached +8.3%. The same gap rule on non-event
days earned +3.9% (trial 1,983), so volatility clustering carries part of it. Frozen and read once
on C, it failed. That read was not clean: round 4 had already printed C for 1,977, and the gap
split was glimpsed on every block during diagnosis.

## Use for the project

Index event nights have no premium to sell. The only reproducible pattern, continuation variance
the session after a release, is volatility clustering on a handful of days and does not hold out.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneG-index-event-vol\report.md
