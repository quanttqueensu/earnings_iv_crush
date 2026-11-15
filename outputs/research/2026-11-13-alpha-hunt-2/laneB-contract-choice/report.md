# Lane B: which contract to sell into the event

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log`, `score_held.log`,
`diag_strangle.log` and the two freeze notes. The five fingerprints in each freeze note were
re-hashed and match; the held-out read (13:14:48 local) followed the freeze (13:11:18 local).

## Verdict

Two contract rules held up on held-out 2019-24, and neither makes the book positive at the touch.
Choosing the contract recovers 0.2 to 0.55% of m0 per trade; the best book still loses 0.66%. This
is cost recovery, not alpha. The strike rule (trial 1,819) was frozen before the read and passed
at t 5.7. Its freeze called 2019-24 clean for this outcome after checking trials 1,555, 1,557 and
1,560, none of which is in `blocks.csv`; but 1,560 had already scored on 2019-24 a 15:59 choice of
the cheaper-quoted construction, paired against H at the touch (+0.10% [+0.01, +0.17]), and 1,557
scored strike placement against H. The feature differs, the outcome family does not, so its
confirmatory status is contested: read conservatively, it is a strong held-out replication of a
known effect. Trials 1,811 to 1,826
(1,820 has a correction row); 1,827 to 1,840 unused.

## Split and basis

Discovery 2013-18, held-out 2019-24, by entry year on CRSP stock paths; 2025-26 not built.
Universe: status-ok events of the hedged-hold study (7,753). Each alternative contract is priced
by the same frozen builders as the base trade (front ATM straddle, delta-hedged at every close,
held to expiry), and rebuilding the ATM straddle reproduces the stored H on all 7,753 events.
Figures are per trade, in units of the base trade's m0 (0.20 times forward plus the 15:59 bid
premium), net at the touch, paired against H, with date-clustered 95% intervals.

## Held-out results (2019-24)

| Trial | Rule | N | Effect vs H | 95% CI | t | Null pct | Book level | Label |
|---|---|---|---|---|---|---|---|---|
| 1,819 | Sell the straddle at whichever of the ATM strike and its two neighbours has the narrowest 15:59 quote; hedge the strike change's delta with stock over the event night | 5,092 | +0.21% | [+0.14, +0.28] | 5.7 | 100 | -1.05% [-1.45, -0.65] | Held-out pass, confirmatory status contested; cost recovery |
| 1,826 | Strangle with wings at half the implied move, each wing moved one strike when that narrows the quote per unit of vega, sized to the straddle's entry vega | 5,041 | +0.55% | [+0.40, +0.71] | 7.0 | n/a | -0.66% [-1.09, -0.26] | Exploratory; cost recovery |

Rule 1,819 switches strike on 44% of events. On those it saves 0.52% of m0 of entry half-spread
and gives back 0.15% at settlement. Discovery had +0.10% [+0.01, +0.19], t 2.2; the held-out
effect is twice that.

Rule 1,826 is exploratory because trial 1,557 already scored a strangle against H on 2019-24 and
the wing width, the wing rule and the equal-vega statistic were chosen after reading discovery.
Of its +0.55%, the vol-tight wing rule adds +0.24% [+0.15, +0.33] over plain half-move wings.
Both arms settle under the old expiry convention (full hedge unwind plus 5 bp disposal), which
the strangle incurs at a different rate from the straddle, so part of the +0.55% is an accounting
difference until both are re-valued under the adopted netting.

Rule 1,819's matched null is easy to beat, because a random neighbour is usually wider (null
median -0.12%), so its null percentile adds little beyond the t. The rule's eligibility needs the
neighbour's reaction-session quotes, a negligible look-ahead (29 arms), and the fill assumes the
15:59 snapshot is executable at size.

Attrition: the 19 events with no listed neighbour and the 72 with no half-move wing average H of
-3.0% and -4.9% of m0 against -1.2% for covered events. Covering them would lower both levels by
about 0.05%. The rules never drop an event the base book trades, so the paired effects are not
flattered.

## Why the strangle keeps more, and why it still loses

At equal vega the strangle earns more at the mid than the straddle (+0.87% against +0.69% of m0
on discovery), so the event premium sits more in the wings than at the money, consistent with
trial 1,557. On discovery the strangle book decomposes as +0.81% at the mid, -0.80% entry
half-spread and -0.40% hedging, fees and disposal, for -0.39%. The worst 1% of events (24, moves
of two to six implied moves) carry 149% of the loss; without them the book is +0.19%. That tail
is the event-night jump on the same expiry, and no choice of strike or width removes it.

## Iteration story

Round 1: choosing the tighter-quoted strike saved spread, but the strike step's direction on the
unhedged event night swamped it (1,811 +0.04%, interval across zero; 1,812 +0.17%, t 1.9). Always
switching to the neighbour cost 0.36% (1,813), because the ATM quote is usually the tightest.
Strangles beat the straddle on a margin-matched basis at t of about 4, but on a losing book a
smaller position can simply lose less. The monthly expiry paid more spread per unit of capital
and earned nothing extra (1,817, -0.24%). Round 2: hedging the strike step's delta over the event
night halved the interval and showed about 0.07% of round 1's gain was luck (1,819). The per-leg
version (1,820) mostly picked a one-strike strangle, a structure effect. At equal vega the
strangle's advantage survived (1,822, +0.32%), so it is pricing, not scale. Round 3: choosing the
straddle or strangle per event added 0.02% over always choosing the strangle (1,824), and measuring
strike spreads per unit of vega changed nothing (1,825).

Process note: the first logged null percentile for 1,820 was a NaN bug, corrected in a dated
second row. `results_disc_1819_1820.json` still holds the bad value;
`results_disc_1818_1820.json` replaces it.

## Use for the project

Both levers are plain execution choices that the paper book can adopt without a selector: sell the
tightest of the three central strikes, and consider a vega-matched half-move strangle with
spread-aware wings. Neither closes the gap alone. A strangle sized to equal vega carries more
notional than the straddle, so its margin and tail need checking before any sizing decision.
Whether they stack with the 15:45 entry and the expiry netting correction (lanes A and C) is an
open question that needs its own frozen test, and 2019-24 is now spent for contract choice.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneB-contract-choice\report.md
