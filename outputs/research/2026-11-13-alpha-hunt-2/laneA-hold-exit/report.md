# Lane A: decisions after the announcement on the hedged hold

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log`, `heldout.log` and
freeze note. Every figure is from those files.

## Verdict

No decision taken after the announcement makes the held book positive. The one rule that passed
its frozen held-out read (a 0.10 delta band on the hedge) is cost recovery of a few hundredths of
a per cent. Trials 1,781 to 1,798 (21 scored rows); 1,799 to 1,810 unused.

## Split and basis

Discovery 2013-18 by reaction-session year (N=2,640 hedged-hold events with status ok); held-out
2019-24 (N=5,113), read once after `freeze_2026-11-13_band-and-bias-buyback.md`. The outcomes H
and B are viewed on every block, so every result is exploratory at best. Decision time: the
reaction-session 15:59 option quotes and the CRSP close of that session. The HAR realised-vol
forecast uses CRSP returns up to entry with earlier reaction days blanked. Every figure is per
trade, in m0, net at the touch, with date-clustered 95% intervals.

## The ceiling, computed before any rule (descriptive)

Choosing hold or buy back event by event with perfect foresight (the larger of H and B) gives
-0.30% of m0 in 2013-18, -0.06% in 2019-24 and +0.68% in 2025-26. Always holding gives -1.04%,
-1.27% and -0.10%.

Correction after lane C's trial 1,856 (`check_assignment_netting.log`, descriptive). The stored H
unwinds the whole hedge at expiry and pays 5 bp disposal on the assigned share; under physical
assignment that share nets against the hedge. Netting adds +0.22% of m0 per trade
([+0.21, +0.23] in both blocks), taking H to -0.82% [-1.27, -0.35] in 2013-18 and -1.05%
[-1.45, -0.66] in 2019-24, and the perfect-foresight ceiling to -0.13% [-0.56, +0.30] and +0.10%
[-0.25, +0.45]. The earlier statement that the ceiling is negative even with perfect foresight is
withdrawn: it is indistinguishable from zero. The gain accrues only to held events, so a rule that
buys back gives it up on the events it closes; the rules below buy back rarely, so their paired
effects move by a few hundredths at most, and every realistic rule stays within 0.07% of H. If the stock never moved after the reaction
close, holding would collect all the remaining extrinsic value, a level of +4.0% of m0 (N=2,274);
the distance between that and the ceiling is realised post-reaction volatility, not a decision.

Where the loss sits: H is +4.3% on events whose reaction move is under half the implied move and
-7% to -42% above one implied move, while the post-reaction leg (B - H) is a flat -1.6% to -2.3%
in every move bin. The loss is the gap, and it is sunk before any post-announcement decision.

## Results

| Trial | Rule | Block | Effect vs H | 95% CI | t | Label |
|---|---|---|---|---|---|---|
| 1,781 | Buy back when remaining extrinsic is below the exit half-spread | 2013-18 | -0.31% | [-0.41, -0.21] | -6.2 | Fail |
| 1,782 | Buy back when IV at the ask is below a HAR forecast | 2013-18 | -0.12% | [-0.20, -0.04] | -3.1 | Fail |
| 1,783 | Close the in-the-money leg, hold the other | 2013-18 | -1.22% | [-1.36, -1.08] | -17.1 | Fail |
| 1,784 | Close the out-of-the-money leg, hold the other | 2013-18 | -0.68% | [-0.80, -0.57] | -11.5 | Fail |
| 1,787 | Rebalance only when delta drifts more than 0.10 (frozen) | 2019-24 | +0.016% | [+0.000, +0.033] | 2.0 | Exploratory, held-out pass; level -1.25% [-1.66, -0.86] |
| 1,796 | Buy back when IV at the ask is below a bias-corrected HAR forecast (frozen) | 2019-24 | -0.073% | [-0.112, -0.036] | -3.8 | Fail |
| 1,797 | Same with the second expiry's mid IV as the forecast (post hoc) | 2019-24 | +0.005% | [-0.02, +0.04] | 0.4 | Not in the freeze |

Stops lost 0.06% to 0.13%. Bands, rebalancing clocks and HAR-based hedge ratios moved H by 0.00%
to +0.04%: the equity hedging cost is only about 0.36% of m0, the ceiling of that family.

## Iteration story

Round 1 (15 trials): nothing beat always holding. The events where buying back would have won
(21%) differ in realised post-reaction volatility (0.31 against 0.19, annualised), but not in the
HAR forecast (0.240 against 0.241). Partial unwinds pay one leg's exit spread to give up that
leg's time decay, and by parity both legs carry the same extrinsic value, so both lose.

Round 2: correcting the HAR forecast's bias causally cut buy-backs from 374 to 44; using the
second expiry's IV fired on 58. Once the forecast is unbiased, the remaining option is almost
never cheap at the ask. The matched random null is the wrong bar for these rules: random
buy-backs cost the full mean B - H of about 2%, so any rule that buys back rarely clears it. The
bar that matters is always holding.

Held-out: the bias-corrected HAR rule failed because 117 of its 237 buy-backs fell in 2021. The
three-year HAR window still carried the 2020 crash, and a single global bias factor cannot fix a
regime-level error.

## What this rules out

Any improvement to the held book must act before or at entry: which events to sell, at what
price, in what contract. Decisions after the gap can recover at most the perfect-foresight
ceiling, which is about zero on 2013-24 even after the netting correction, and realistic rules
recover almost none of it.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneA-hold-exit\report.md
