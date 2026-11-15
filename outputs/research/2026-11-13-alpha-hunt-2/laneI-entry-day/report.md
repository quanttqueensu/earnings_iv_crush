# Lane I: selling the event straddle on an earlier day

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log`, `heldout_read.log` and
freeze note. The freeze note's SHA-256 was re-hashed and matches `freeze_sha256.txt`; it was
written (12:58:55 local) before the held-out chains were pulled (12:59:23 onwards), and the
scorer checks the hash before reading.

## Verdict

Entering the hedged hold earlier does not sell the event premium at a better price. It is fair or
worse at the mid and worse at the touch by about 0.8 to 1.5% of m0 per trade. The one held-out
pass is the cost check, which confirms that an early sale loses. Resting a passive early offer
cannot be tested on end-of-day data. All data were free DoltHub chains; no spend. Trials 2,021 to
2,036; 2,037 to 2,050 unused.

## Split and basis

Discovery: 904 hedged-hold events on tickers A to CHD, entry 2019-02 to 2024-12. Their pre-event
DoltHub chains had been viewed by the vega run-up study, so discovery is not clean. Held-out: a
seeded random sample of 900 events (seed 20261113) on tickers after CHD over the same span, whose
pre-event chains had never been pulled; 898 have a valid standard sale. The level of H on 2020-24
had been viewed descriptively; the early-minus-standard outcome had not.

Arms: S0 is the standard sale, the front ATM straddle at the Databento 15:59 bid on the entry day.
Dk sells the same expiry at the DoltHub end-of-day bid k sessions earlier, at that day's ATM
strike. D0 is the same-day DoltHub quote, a source control. Every arm is delta-hedged at every
close to the session before expiry and settles at intrinsic, with the standard costs. The lane's
replica of the hedged-hold H reconciles to the stored value on all 1,803 events, and every DoltHub
pull pins the exact date with exits marked from Databento and CRSP, so an entry chain cannot pair
with itself. Figures are
per trade, in the standard m0, net at the touch, with date-clustered 95% intervals and a
date-cluster sign-flip null.

## Held-out results

| Trial | Comparison | N | Effect | 95% CI | t | Null pct | Label |
|---|---|---|---|---|---|---|---|
| 2,034 | Sell 2-3 sessions early, minus S0 | 378 | -0.81% | [-1.50, -0.21] | -2.45 | 0.3 | Fail, wrong sign |
| 2,035 | Sell 2-3 sessions early, minus same-source D0 | 209 | +0.09% | [-0.61, +0.77] | 0.25 | 59.4 | Fail |
| 2,036 | Sell 7-10 sessions early, minus S0 (cost check) | 815 | -1.52% | [-2.24, -0.83] | -4.23 | 0.0 | Pass: early entry loses |

All three are discovery-derived and exploratory. At the mid, the held-out early sale is also worse:
-0.59% [-1.29, 0.00] at 2-3 sessions and -0.85% [-1.58, -0.16] at 7-10, where discovery had
+0.13% and -0.20%, both spanning zero. So part of the held-out deficit is the event-variance run-up
that the early seller gives away, not only the crossing cost.

Coverage: DoltHub omits expiries inside about a week, so at small k only long-dated fronts
survive, and those have S0 levels 1 to 2.5 points of m0 below the uncovered events (D2: 205
covered, -3.08% against -0.80%). The comparisons pair events within the covered set, so this moves
book levels, not the paired effects. Events with any empty snapshot do not differ in outcome
(S0 +0.40% of m0 [-1.91, +2.52] held-out, +0.41% [-1.28, +2.20] discovery).

## Iteration story

Round 1: early minus S0 grew more negative with k (-0.18%, -0.54%, -0.88% of m0, the last t -3.0),
while early minus the same-source D0 was flat. DoltHub's end-of-day half-spread is about 20% wider
than Databento's 15:59 quote on the same contract, with mids that agree, so part of the deficit was
quote source. Round 2: a source-neutral modelled fill still lost 0.61% [-1.21, -0.01], because the
early sale crosses its spread on a larger premium (0.27 against 0.22 of m0). Selecting early days
on rich event pricing or low realised-to-implied vol picked events no better than random (null
percentiles 30.9 and 38.5), and leaving the run-up unhedged added variance, not return. Round 3:
the remaining advantage of an early day is time to rest a passive offer. A static limit at the
early mid was picked off (fills on 42% of events, -1.73% against S0); a limit pegged to the entry
implied vol was worse (79% fills, -2.87%), because the straddle's IV rises with the calendar alone
as tenor shrinks around a fixed event variance. With end-of-day snapshots a fill is only visible as
a quote-through, so the resting book can never beat that day's bid: passive early entry needs
intraday prints over the run-up window and is not tested here.

## Use for the project

Keep the entry on the event day. The open question this lane cannot answer, a passive offer
resting through the run-up, needs the D0 maker studies' tick data extended back several sessions,
which is a metered pull.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneI-entry-day\report.md
