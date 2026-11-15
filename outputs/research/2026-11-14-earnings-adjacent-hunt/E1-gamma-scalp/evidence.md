# E1 gamma scalp: long, intraday-hedged straddle on the reaction session

## Hypothesis, scope and success criteria

After the overnight crush, the stock keeps discovering its price on the reaction session. If the
stock's intraday realised variance exceeds what the post-crush quotes charge, a long straddle
hedged intraday earns it, and intraday mean reversion would raise a frequent rebalancer's take
above close-to-close sampling. Scope: data already on disk, zero spend. Success: a positive mean
net P&L at the touch with a date-clustered 95% interval excluding zero on discovery, confirmed
once on a held-out block. The primary, its controls, the pass rule and the kill rule were written
in `diagnosis.log` (entries 2 and 3) before any outcome was computed.

## Verdict

Not viable at the touch. The frozen primary (trial 2,682) loses -11.66% of the debit per trade
[-13.01, -10.24] on discovery (N=578, 193 reaction dates) and -19.82% [-21.37, -18.24] held-out
(N=682, 128 dates), per trade, net at the touch. The kill rule fired on discovery: the gross P&L
at the mid is positive, +0.86% of debit [+0.46, +1.26], but the round-trip option touch is 10.57%
of debit (18.36% on the all-broad held-out block). The trade fails by an order of magnitude, and
it fails even at the option mids once the stock hedge is paid. Twelve trial numbers were used
before the freeze (2,682 to 2,693), and a thirteenth (2,694) after it for a basis correction; the
frozen rule's discovery t is about -16.5.

The m0 figures were corrected after the outcomes were computed (diagnosis.log entry 7). The
2025-26 ledger's `spot_entry` is a dividend-back-adjusted close (`research/chains.py::_spot_table`
calls `yf.download(auto_adjust=True)`), and the first run built m0 and the attrition check on it.
Every m0 figure below uses the D0 15:59 parity forward instead. The primary is on the debit basis,
which never used that spot, so the verdict and the pass/fail are unchanged.

## Data and what it can and cannot test

Reaction-session intraday data exists only in `data/cache/flow/*_exit.parquet`: Databento OPRA
cmbp-1 for the two contracts the book sold (call and put on the 15:59 entry strike), D+1 15:00 to
16:00 ET, for megacap_2023_2024 (243 events) and broad_2025_2026 (1,220). `broad_2023_2024` holds
entry-day files only, which forced the split amendment in diagnosis entry 3. The `_pre` files give
the same two contracts over the three full sessions before the report, which supplies a matched
control hour (D-1, same strike, same clock). There are no intraday stock prices anywhere in the
caches; the stock is the put-call-parity forward of the cached strike. Three limits follow and
bound every number here:

1. Only the last hour of the reaction session is observable. D+2 and D+5 horizons with intraday
   hedging are not testable on disk.
2. The only contract is the held strike, which after the reaction is off the money (median
   |straddle delta| 0.66 at 15:01). A fresh at-the-money straddle cannot be bought on this data.
   On 2025-26 the strike was also off the money at the 15:59 entry: the ledger chose it as at
   the money on the adjusted spot, so on the true forward ln(F/K) has deciles 10/25/50/75/90 of
   -0.13/+0.44/+1.40/+2.85/+4.60%, a mean |ln F/K| of 2.02% and 61% of events beyond 1% (the
   strike sits a median 1.4% below the money; N=1,220). Megacap 2023-24, which used an unadjusted
   spot, is off only by strike spacing: -1.83/-0.65/+0.17/+1.02/+1.90%, mean 1.17% (N=243). The
   entry offset adds to the reaction move's effect on delta on up-moves and offsets it on
   down-moves.
3. Stock half-spreads are not observed; stock legs pay an assumed 3 bp plus 1 bp.

## Method

Buy the held straddle at the 15:01:00 ask on D+1 (the first clean minute of the file), hedge in
the stock on a 5-minute clock, sell at the 15:59:00 bid. The hedge ratio is the Black straddle
delta on the parity forward, with the straddle-mid IV and calendar time to the 16:00 expiry close
(ACT/365), both observed 30 seconds before each rebalance and executed at the forward at the
rebalance time. The lag exists because a noisy proxy that sets both the ratio and the trade price
creates a spurious scalping gain of about gamma times the noise variance per rebalance;
`test_lib.py` shows the bias on synthetic paths without the lag and its removal with it. A leg
without a bid at exit would be sold at zero (none occurred). Option legs pay the quoted touch
plus USD 0.65 per contract per leg (`HEDGED_NET`). Intervals are `date_clustered_ci` with the
mean as statistic, resampling reaction dates. The basis is the debit (asks plus fees), the long's
capital; the same means on m0 (0.20 times the D0 15:59 parity forward plus the 15:59 bids) are
given for comparison with the book.

Inputs were reconciled before use (`recon.log`): the grid's 15:59 straddle mids equal the ledger's
`straddle_entry` and `straddle_exit` on all 1,220 shared events. The parity forward sits +8.4 bp
above the CRSP close on megacap D+1 (median +8.8 bp, N=239), +5.0 bp at three days or fewer to
expiry and +10.9 bp beyond, the size of the interest carry, so it is an unbiased stock proxy up
to carry inside an hour. The lag-1 autocorrelation of its 5-second changes has median -0.013,
so proxy noise is small at that scale.

## Results (per trade; discovery unless stated)

| Trial | Rule or statistic | Basis | Effect | 95% CI | N |
|---|---|---|---|---|---|
| 2,682 | Primary, 5-minute clock | % debit, net touch | -11.66 | [-13.01, -10.24] | 578 |
| 2,694 | Same rule, corrected m0 | % m0, net touch | -2.31 | [-2.59, -2.01] | 578 |
| 2,682 C1 | Gross at the mid | % debit | +0.86 | [+0.46, +1.26] | 578 |
| 2,682 | Round-trip option touch | % debit | 10.57 | [9.07, 11.97] | 578 |
| 2,682 C2 | 5-minute clock minus static hedge, net | % debit | -0.08 | [-0.30, +0.13] | 578 |
| 2,682 C3 | Same rule on D-1, net / gross at mid | % debit | -6.82 / +0.63 | [-7.64, -5.91] / [+0.40, +0.89] | 575 |
| 2,684 to 2,686 | 1-min clock, 15-min clock, 0.10 delta band | % debit, net | -12.04, -11.46, -11.59 | each about ±1.35 | 578 |
| 2,687 | No lag (noise check) minus primary | % debit | +0.06 | [+0.01, +0.12] | 578 |
| 2,688 | 10 bp plus 1 bp stock touch | % debit, net | -13.96 | [-15.30, -12.54] | 578 |
| 2,689 | D+1 minus D-1, gross at mid, paired | % debit | +0.23 | [-0.27, +0.72] | 575 |
| 2,690 | \|delta\| < 0.25 at entry | % debit, net | -13.02 | [-15.55, -10.50] | 91 |
| 2,692 | Rebalancing gain gross of stock cost, 5-min vs static, D+1 / D-1 | % debit | +0.24 / +0.15 | [-0.01, +0.48] / [+0.07, +0.23] | 578 / 575 |
| 2,691 | Mirror: short hold hedged from 15:01 vs first hedge at 15:59 (corrected m0, 2,694) | % m0, net | -0.31 | [-0.48, -0.14] | 578 |
| 2,693 | Fade the reaction 15:01 to 15:59 in the stock | bp, gross / net of 2 x 4 bp | +6.6 / -1.4 | [+0.0, +13.0] / [-8.0, +5.0] | 578 |
| 2,682 held-out | Frozen primary, 2025-07 to 2026-06 | % debit, net touch | -19.82 | [-21.37, -18.24] | 682 |
| 2,682 held-out | Gross at the mid; round-trip touch | % debit | +0.21; 18.36 | [-0.15, +0.56] | 682 |
| 2,694 held-out | Frozen rule, corrected m0 (denominator only, second computation on the read block) | % m0, net touch | -4.30 | [-4.70, -3.89] | 682 |

Funnels: discovery 640 to 578; dropped events moved somewhat more (|reaction| 4.71% against
4.36% on the corrected spot, N=60 and 578), so the scored book slightly under-represents the
widest-quoted large movers and is if anything flattered. Held-out 823 to 682 (dropped 4.93%
against kept 4.32%, N=141 and 682). The first run reported 6.0% against 4.6% for discovery, an
artefact of the adjusted spot. By universe on discovery (`discovery_by_block.log`): megacaps pay a 4.70% round trip and
earn +0.18% gross (net -6.45%, N=236); broad names pay 14.62% and earn +1.33% (net -15.26%,
N=342). Stock costs are 1.31% of debit, mostly the opening and closing hedge of an off-the-money
straddle, which is why the trade loses even at the option mids.

## Reading the mechanism

The gross term is the right sign and is generic, not post-event. The held straddle's mid falls
less over the session's last hour than the stock's realised moves pay, which is the intraday leg
of the day-night pattern in Muravyev and Ni (2020): positive open-to-close delta-hedged returns at
the mid, gross of costs. Under a calendar-time Black convention it appears as a rise in implied
vol over the hour (+1.87 points [+0.54, +3.78]), with the gamma-minus-theta remainder near zero
(-0.14% [-1.19, +0.59]); that split depends on the time convention and should not be read as a
volatility view. The same hour on D-1 earns about as much (+0.63% gross), and the paired
difference (+0.23% [-0.27, +0.72]) does not separate post-event discovery from an ordinary day.

Intraday mean reversion is present at the 1 to 5 minute scale: 1-minute forward returns have lag-1
autocorrelation of -0.11 (D+1) and -0.13 (D-1). On the tradeable, lag-guarded hedge it is worth
+0.15 to +0.29% of debit gross over a static hedge, about one fortieth of the option round trip,
and the stock touch on the extra rebalances eats it. The mirror is mostly direction: hedging the
short hold from 15:01 loses because reactions partly reverse in the last hour (+6.6 bp gross on
D+1 against -0.6 bp on D-1), a pattern consistent in sign with So and Wang (2014) on liquidity
provision around announcements, though their reversals are daily. At an assumed 4 bp a side it is
not tradeable, and it is a statistic switch from this lane's primary.

## How this differs from the closed work

Alpha hunt 2 lane C measured the short's diffusive premium hedged at daily closes from the reaction
close to expiry (net -0.22% of m0 [-0.51, +0.07], 2019-24). This lane is the long side, hedged
intraday inside the reaction session, which is where Muravyev and Ni locate the positive return a
close-hedged book cannot see. It confirms the sign of that gross return and shows the touch is about
12 times larger on discovery (10.57% against +0.86%) and about 90 times held-out (18.36% against
+0.21%). Lane A managed the short after the gap; nothing here changes its
conclusion that the short's loss is sunk in the gap, and the mirror adds that hedging the hold
earlier on D+1 costs about 0.3% of m0. The post-announcement straddle held to expiry was unhedged
and held for weeks.

## Prior work

Muravyev and Ni (2020, JFE 136(1)): S&P 500 option delta-hedged returns average -0.7% a day, about
-1% close to open and +0.3% open to close, at the mid and gross; a similar pattern in equity
options (abstract read at RePEc; verified). A practitioner summary of the working paper says the
spread defeats a daily round trip (verified, secondary). Jones and Shemesh (2018, JF 73(2)): option
returns are lower over non-trading periods (verified, abstract). Patton and Verardo (2012, RFS
25(9)): betas estimated from intraday prices rise on announcement days and revert in two to five
days (verified, abstract). Bandi and Russell (2008) and Zhang, Mykland and Ait-Sahalia (2005) on
noise in high-frequency realised variance (verified, abstracts), which is the reason for the lag
guard. Bakshi and Kapadia (2003) on delta-hedged gains (recalled, project reference list). I found
no study that measures an intraday gamma scalp on single-name options around earnings net of the
touch; that absence is a search result, not proof. The idea is not crowded in print, and this
lane's numbers say why: the touch on a post-event single-name straddle is far larger than the
intraday gross.

## Tradability at IB and what a pull would buy

The live harness trades option combos at 15:59 and has no stock-hedge path; a scalp needs an
intraday stock order loop, real-time OPRA and equity data (without them IB quotes are about
fifteen minutes late) and per-share stock commissions on every rebalance. None of that is worth
building on this evidence. A full-session and multi-day version (D+1 open to D+5, intraday hedges,
the post-move at-the-money strike) is cheap to pull: the whole existing flow pull, about three
sessions and an hour of two legs on 1,464 events, cost USD 5.15 (`outputs/research/flow_liquidity/
findings.md`), so five sessions on four legs would be of order USD 15 to 20 (an extrapolation from
that actual spend, to be priced with the free cost call). It is not recommended: the gross take
per session would have to be several times the last hour's to cover one round trip of 10 to 18%
of debit, and Muravyev and Ni's overnight leg is negative, so holding across nights gives back
what the sessions earn.

## The 2025-26 spot defect

The 2025-26 ledger's spots are dividend-back-adjusted closes (confirmed by the team lead at
`research/chains.py::_spot_table`). On this lane's 1,220 broad events the D0 15:59 parity
forward sits above `spot_entry` by a median of +1.36% (mean +1.93%, 90th percentile +4.47%),
falling by entry quarter from +3.22% (2025Q1) to +0.66% (2026Q2) (`correct_m0.log`). Against
CRSP on megacap D+1 the same forward agrees to within carry, so the forward is the correct
reference. Any m0, move or moneyness figure built on that ledger's spots inherits the gap. The
corrected m0 is higher by a median 1.05%, and it moved this lane's m0 figures by about 0.05
points.

## Files

Scripts: `extract.py`, `lib.py`, `test_lib.py`, `recon.py`, `run.py`, `diag.py`, `heldout.py`,
`correct_m0.py` (its log is `correct_m0.log`; the corrected events are
`cache/events_m0fix.parquet`).
Logs: `extract.log`, `extract_funnel.json`, `recon.log`, `recon_crsp.log`, `primary_discovery.log`,
`variants_discovery.log`, `diag.log`, `discovery_by_block.log`, `block_check.log`, `heldout.log`.
Records: `diagnosis.log`, `trials.csv`, `sources.csv`, `freeze_2026-11-14_e1.md`,
`blocks_viewed.csv`. The `cache/` folder holds quote grids derived from licensed data and is
git-ignored; rebuild with `extract.py` (about 40 minutes, no spend).

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-14-earnings-adjacent-hunt\E1-gamma-scalp\evidence.md
