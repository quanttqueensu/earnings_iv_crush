# L2 execution and cost: evidence dossier

Basis of every figure unless the entry says otherwise: per trade, % of m0 (0.20 times the 15:59
parity forward plus the 15:59 straddle bid), net at the touch, not annualised. Intervals are
date-clustered 95% percentile intervals (`protocol.date_clustered_ci`, 5,000 draws, seed 0).
The outcome is `H_corr` of `L1-corrections/base_corrected.parquet` (netted, early call
assignment, financing), except B8, which compares strangles with the straddle on `H_net` (netted
only), as the netted strangle function is valued. Discovery is 2013-18 and held-out 2019-24. The hedged_hold outcome on
2019-24 had already been viewed by other feature families, so every 2019-24 read below is
exploratory as well as held-out. 2025-26 is exploratory. Every number traces to a json or log in
this folder; `diagnosis.log` holds each declaration, written before its computation.

All levers re-value one recorded path. `build_paths.py` imports L1's `build_base.py` and records
the inputs of every `H_corr` valuation. Re-valuing them reproduces `H_corr` exactly on 9,315
events (8,236 hedged; `build_paths.log`). Changing one input therefore isolates one lever.

Equity-cost convention. Every figure here charges the stock hedge max(closing half-spread, 1 bp)
of traded notional per order (`equity_cost_floor_bps`, `config.py:556`, `hedged_hold.py:455`).
The 1 bp is a floor, not an addition; briefs that say "half-spread plus 1 bp" misdescribe the
code. `H_corr` charges no stock commission. Only B1's like-for-like arm, B10 and B11 charge one;
the per-event Tiered charge is in `hedge_commission.parquet` (B10).

## B1 Closing-auction hedging (trials 2,892 to 2,895): invalid comparison as declared

**Nearest closed work.** The hedged hold charges max(CRSP closing half-spread, 1 bp) per side at
each hedging close. E1's mirror arm (2,691) closed intraday hedging of the short. Nothing has
priced the auction before. No auction data exist on disk, so the auction impact a is a declared
grid and every figure here is assumption-based.

**Headline, like for like.** Both arms pay IB Tiered's per-order commission (recalled), and
the continuous arm also pays a USD 0.003 take fee. At an auction impact a = 0.5 bp the MOC hedge
gains +0.095 [+0.082, +0.112] on 2013-18 (N = 2,640, 675 dates) and +0.095 [+0.086, +0.106] on
2019-24 (N = 5,113, 850 dates). The break-even auction impact a* is +2.26 bp [+1.85, +2.82] and
+2.87 bp [+2.59, +3.21]: the auction wins for any impact below about 1.85 bp (2013-18) and
2.59 bp (2019-24), the lower bounds. The mean half-spread charged today is 2.03 bp per side
[1.62, 2.58] on 2013-18 and 2.75 bp [2.46, 3.08] on 2019-24. This is a statistic switch, so it
is reported, not counted as a pass. B1's commission is uncapped (the file is frozen); IB's 1%
cap lowers the Tiered charge by about 0.004% of m0 on 2013-18 (B10), on both arms.

**As declared: invalid comparison (fee asymmetry).** The declared arm paid the auction cost plus
IB's MOC charges and commission, against `H_corr`, which pays no commission. That asymmetry,
not the auction, decides the sign, so the declared result is not read as a fail.
- At a = 0.5 bp and N = 1: -0.109 [-0.127, -0.088] (2013-18), -0.029 [-0.039, -0.016] (2019-24)
  and +0.036 [+0.029, +0.043] (2025-26, exploratory, constant 3 bp Yahoo half-spread).
- a* at N = 1 as declared: -0.03 bp [-0.46, +0.53] on 2013-18 and +1.70 bp [+1.39, +2.06] on
  2019-24. The declared kill rule (a* < 0.5 bp) fired on discovery. The 2019-24 and 2025-26
  reads were made after it fired, once the asymmetry had been found.

**Tracking error.** The ratio has to be set from a 15:50 price, simulated at the hold's own sigma.
It changes the mean by -0.011 [-0.032, +0.010] (2013-18), -0.024 [-0.048, +0.000] (2019-24) and
+0.050 [+0.011, +0.091] (2025-26, exploratory). The variance ratios are 1.0013 [0.9979, 1.0048]
and 1.0087 [1.0045, 1.0133] (and 1.0068 [1.0012, 1.0132] on 2025-26); the 2019-24 ratio's interval excludes 1, so tracking adds a small
but real variance (under 1%). Each figure rests on a single simulated draw of the pre-cutoff
price (seed 0), so the intervals cover event and date sampling, not the simulation.

**Mechanism.** By construction the change sits entirely in `c_equity_cost` (and in `c_hedge` for
the tracking variant). The declared comparison fails because of an asymmetry the brief carried
in: `H_corr` charges the hedge a half-spread but no stock commission. At one contract the hedged
hold sends about 7.1 stock orders per hedged event, each paying at least IB Tiered's USD 0.35
minimum. Priced that way the hedging-close orders cost -0.204% of m0 [-0.220, -0.189] on
2013-18, twice the half-spread charged there (-0.100 [-0.117, -0.087]). On 2019-24 the ratio is
about 1.2 (-0.124 [-0.131, -0.117] against -0.105 [-0.117, -0.097]). Once both arms pay that
commission, the auction saves about 0.1% of m0 per trade in every block. The saving survives
any auction impact up to about 2.3 to 2.9 bp per side, but it is a cost recovery on a book that
loses about 1% of m0 per trade.

## B10 Fee arithmetic (trials 2,896 to 2,900)

**Nearest closed work.** `HedgedHoldConfig.fee_per_contract_leg` = USD 0.65, never checked against
a schedule. Two figures were read at the source by this lane and saved (`sources/`); two more
were read by the team lead and relayed; Interactive Brokers' pages refuse automated clients, so
every IB figure is recalled. `sources.csv` lists each claim with its URL and status.

| Item | Figure | Status |
|---|---|---|
| NYSE non-tier MOC order executed in the closing auction | USD 0.0010 per share (LOC 0.0011) | verified, NYSE Price List 2026 (last updated 2026-11-02), excerpt saved |
| Cboe Options (C1) customer, under 100 contracts, removing liquidity | USD 0.00 (USD 0.18 at 100 or more) | verified, Cboe Fees Schedule (2026-11-09), excerpt saved |
| Nasdaq Closing Cross MOC/LOC, tiers A to G | USD 0.0008 to 0.0016 per share | lead relay (read 2026-11-15), not verified here |
| Cboe BZX options customer, penny class | remove USD 0.48, add rebate USD 0.25 to 0.52 | lead relay (read 2026-11-15), not verified here |
| IBKR Pro Fixed options | USD 0.65 per contract, USD 1.00 per order minimum, fees included | recalled |
| IBKR Pro Tiered options, lowest tier | USD 0.65 per contract plus clearing USD 0.02 and regulatory about USD 0.03 | recalled |
| Maker-taker venue, penny class (as modelled) | take USD 0.50, rebate USD 0.25 | recalled; the relayed BZX figures are close (0.48, 0.25 base) |
| IBKR Pro stock, Fixed / Tiered | USD 0.005 per share (min 1.00) / USD 0.0035 per share (min 0.35) plus pass-through; both capped at 1% of trade value | recalled |
| SEC Section 31 / FINRA TAF on sales | USD 27.80 per million of sale value (fiscal 2024) / USD 0.000166 per share sold | recalled; bounded, not charged |

**Option commission.** Each line is the change against the assumed fee, at N = 1, entering as a
single combo order (`b10_<block>.json`; trials 2,896 to 2,898).
- Fixed changes nothing: 0.000 in every block.
- Tiered taking on C1: -0.008 [-0.009, -0.008] (2013-18) and -0.006 [-0.006, -0.006] (2019-24).
- Tiered taking on a maker-taker venue: -0.091 [-0.094, -0.088] and -0.065 [-0.068, -0.063].
- Tiered resting with the rebate: +0.033 [+0.032, +0.034] and +0.024 [+0.023, +0.025]. This
  applies only to a resting entry that fills.

**The omitted stock commission (trials 2,899 and 2,900).** One marketable order per nonzero
rebalance, including the netted expiry residual, with IB's 1% cap. Re-run at 02:54 to 02:57 from
the code on disk (diagnosis [22], [24]).

| Stock commission | 2013-18 (N = 2,640) | 2019-24 (N = 5,113) | 2025-26 (N = 1,562, exploratory) |
|---|---|---|---|
| Tiered, N = 1 | -0.220 [-0.236, -0.205] | -0.140 [-0.147, -0.132] | -0.107 [-0.117, -0.098] |
| Fixed, N = 1 | -0.481 [-0.515, -0.448] | -0.305 [-0.321, -0.289] | -0.238 [-0.260, -0.216] |
| Tiered, N = 5 | -0.098 [-0.104, -0.092] | -0.066 [-0.069, -0.063] | -0.050 [-0.054, -0.047] |
| Fixed orders on which the cap binds, N = 1 | 10.6% | 5.4% | 4.1% |
| SEC and FINRA bound (not charged) | -0.009 [-0.010, -0.009] | -0.009 [-0.009, -0.008] | -0.009 [-0.009, -0.008] |

Before the cap, Fixed at N = 1 was -0.527 and Tiered -0.224 on 2013-18; the cap binds mostly on
Fixed, whose USD 1.00 minimum exceeds 1% of small orders in low-priced names. Per-event figures
for Tiered are in `hedge_commission.parquet` (9,315 events; `hedge_commission.README.txt`).

One plan, Tiered on stock and Tiered-on-C1 on options, moves the corrected level as follows (an
account is on one plan, so the earlier per-event cheaper-of-two headline is withdrawn):
- 2013-18: -0.983 to -1.211 [-1.665, -0.750] at N = 1, and to -1.089 [-1.541, -0.629] at N = 5;
- 2019-24: -1.194 to -1.340 [-1.739, -0.948] at N = 1, and to -1.266 [-1.663, -0.874] at N = 5.

**Mechanism.** The option schedule is a rounding error, at most a few hundredths of m0 unless the
order takes on a maker-taker venue. The hedge's order count is the real fee item, carried by the
per-order minimum: at one contract an order is under 100 shares unless the delta moves by more
than one, so the USD 0.35 minimum, not the per-share rate, sets the charge. It therefore falls with size (N = 5 cuts it by
more than half) and with fewer rebalances, which B11 tests: a 0.30 band recovers +0.130 [+0.058,
+0.203] on 2019-24 at one contract. The SEC and FINRA fees are an
order of magnitude smaller and do not change any reading. This is a correction to the cost basis
of every lane, sent to the team lead.

## B6 Per-event expiry choice (trial 2,901)

**Nearest closed work.** The later-expiry hedged hold (2026-11-02), a fixed rule, closed FRONT
EXPIRY. Dubinsky et al. (RFS 2019) give the two-expiry split. B6 chooses per event at entry: it
sells the later expiry (the first 7 to 60 days after the front) when its touch per unit of event
premium (Black-76 straddle value with the split's event variance minus without it) is below the
front's.

The later contract reproduces the closed study's stored L on every event (gap at most 2.0e-16 of
m0).

**Result.** It fails in both blocks. Figures are on the front's m0.

| | 2013-18 | 2019-24 |
|---|---|---|
| Events (dates) | 2,640 (675) | 5,113 (850) |
| Later expiry chosen | 195 (7.4%) | 381 (7.5%) |
| Paired gain over the front | +0.031 [-0.025, +0.085] | +0.001 [-0.059, +0.056] |
| Matched-null percentile | 97.8 | 99.6 |
| Always-later control | -0.443 [-0.712, -0.175] | -1.042 [-1.380, -0.716] |

The rule beats a random expiry switch, which loses money, but it does not beat the front.

**Mechanism.** On the switched events the front's touch is wide: 1.81% of m0 against 0.97% for
the later expiry in 2013-18, and 2.28% against 1.17% in 2019-24. The rule duly saves 0.84 and
1.11 of m0 at entry. The rest of the longer hold gives it back: premium, settlement, hedge P&L
and financing net -0.42 and -1.10. The always-later control loses too, so the longer tenor's
other components carry the outcome, not the touch; which component inside them dominates was
not decomposed here.

Caveats. The front and later arms are not risk-matched: a later straddle carries more premium
and vega per unit of the front's m0, so the paired gain mixes the lever with a change of
exposure. The matched null is a random expiry switch with a negative median, so a high null
percentile shows only that the rule loses less than switching at random, not that the choice
adds value.

## B2 Minimum-variance delta (trial 2,902)

**Citation.** Hull, J. and White, A. (2017), "Optimal delta hedging for options", Journal of
Banking and Finance 82, 180-190. Recalled, not read at the source in this run.

**Nearest closed work.** laneA-hold-exit's delta bands. Nothing has used a smile-dynamics delta.

**Data constraint.** The backfill cache holds only entry and reaction-day chains: 0 of 2,640
discovery events have a chain on the next session. The Hull-White regression was therefore fitted
on event-night pairs (494,885 options on 2,640 events, expiries after the front, |delta| 0.05 to
0.95, at least 14 days to expiry).
- Calls: a -0.127, b -0.120, c +0.178.
- Puts: a -0.065, b +0.164, c -0.106.
- These cut squared hedge error by 9.7% and 16.3% in-sample on the event night.

At the reaction close the fitted adjustment lowers the hedge by 0.075 shares per straddle-share
on average.

**Result.** It fails. The primary is the variance ratio, because on a negative-mean book a lower
variance makes per-trade Sharpe more negative.
- 2013-18: 1.0016 [0.9985, 1.0047], paired mean -0.018 [-0.051, +0.014].
- 2019-24: 1.0020 [0.9983, 1.0056], paired mean -0.027 [-0.072, +0.019].

**Mechanism.** The whole change is in `c_hedge` (-0.018 and -0.027), with `c_equity_cost` at
-0.001 to -0.002. Two things defeat it.
- The coefficients describe how the smile moves on the announcement, not over the post-event
  days the hedge spans.
- The change is a 0.075-share shift at one close, so its P&L is one session's stock return on
  that shift. The per-event sd of H is 11.2% (2013-18) and 12.7% (2019-24) of m0.

Caveats. 2013-18 is in-sample to the coefficient fit, so only 2019-24 is out of sample for the
coefficients. The fit uses options with at least 14 days to expiry, but it is applied to the
front straddle at the reaction close, a tenor the regression never saw.

## B4 Capacity of the passing levers (trials 2,903 and 2,904)

**Rule beyond the top of book (declared).** Only the top level of the book is on disk. Each
further multiple of the displayed size fills one tick (USD 0.01 under USD 3, else 0.05) lower.
A resting 1,779 order fills up to the volume traded above its limit plus the bid size that
reaches it. Both levers reproduce their frozen N = 1 figures exactly.

| Paired gain, % of m0 | N = 1 | N = 5 | N = 10 | N = 25 |
|---|---|---|---|---|
| 1,779 resting entry, 2023-24 (N = 1,703, 266 dates) | +0.217 [+0.154, +0.278] | +0.069 [+0.007, +0.129] | +0.029 [-0.032, +0.087] | +0.054 [-0.008, +0.112] |
| 1,819 tight strike, 2019-24 (N = 5,092) | +0.209 [+0.138, +0.283] | +0.189 [+0.118, +0.262] | +0.162 [+0.091, +0.234] | +0.076 [+0.004, +0.152] |
| 1,819 tight strike, 2013-18 (N = 2,550) | +0.099 [+0.011, +0.185] | +0.087 [-0.000, +0.173] | +0.069 [-0.018, +0.155] | +0.014 [-0.077, +0.102] |

The 1,819 gain is on the pre-netting settlement, but the entry concession does not depend on
it.

**What size costs the book itself.** Selling N straddles at the 15:59 bid on the ladder costs:
- 1,819 sample, 2019-24: -0.082 at N = 5, -0.200 at N = 10 and -0.580 at N = 25. The ATM
  straddle shows fewer than N contracts at the bid on 34%, 46% and 72% of events.
- 1,779 sample: -0.036, -0.091 and -0.278.

**Mechanism.** The resting lever is a queue lever: at N = 5 the mean share of contracts filled
falls from 0.85 to 0.74. The unfilled part then pays the ladder, so two-thirds of the N = 1 gain
is gone by five contracts. The strike lever is a choice between displayed quotes, so it degrades
slowly. But the tighter strike often shows less size (at N = 25 the chosen strike is short of
size on 79% of events against 72% for K0), and by 25 contracts most of the gain is gone. Both
levers are one-lot to few-lot effects, and the book's own entry concession grows faster than
either lever with size.

Caveats. The resting fill assumes the order is first in the queue at its limit, so the 1,779
figures are upper bounds. Depth beyond the top level is assumed (one tick per multiple of the
displayed size), not observed. In the ladder, each ATM leg's bid is taken as half the straddle
bid. The ladder rule is declared, not calibrated.

## B5 Entry minute by causal spread state (trial 2,905)

**Nearest closed work.** Lane 4's fixed entry clocks (1,593 to 1,615), the closed event-level
spread gate, and 1,779.

**Rule.** Sell at the first minute in 15:00 to 15:58 whose relative straddle spread is below the
name's median over strictly earlier events (at least two). Otherwise sell at the 15:59:00 bid. The
panel is the broad 2023-24 entry tick files on CRSP-struck contracts. 549 of 1,712 events are in
burn-in.

**Result.** Discovery fails. The held-out block meets the declared rule, but this is a lead, not
a finding.

| | 2023 (discovery) | 2024 (held-out, exploratory) |
|---|---|---|
| Events (dates) | 213 (38) | 950 (149) |
| Paired gain | +0.053 [-0.059, +0.161] | +0.089 [+0.008, +0.167] |
| Timing-null percentile | 100 | 100 |
| Always-first-minute control | -0.112 [-0.224, -0.011] | -0.015 [-0.129, +0.087] |

**Mechanism.** About 92 to 94% of events enter early, at a median of 15:00, so the rule is "sell
at 15:00 unless the spread is wide". On early entries the half-spread saved is +0.109 (2023)
and +0.274 (2024), and the mid drifts against the seller by -0.052 and -0.177. The straddle's mid
rises into the close, so earlier sales are at a lower mid, as in 1,779, where drift took back
60 to 69%. The gain is the half-spread net of drift.

Caveats. The 15:59 benchmark here is the 15:59:00 tick of the entry tick files, whereas `H_corr`
uses the cbbo-1m 15:59 record; the two were never reconciled. The 2024 interval gives t of about
2.2, below the bar of t at least 3 with Benjamini-Hochberg control across the lane's 15 trials,
and discovery has N = 213 on only 38 dates. It is not a finding.

## B8 Strangle width from the 1,623 move forecast (trial 2,906)

**Nearest closed work.** 1,826 and 1,815 (IM/2 strangles), P5 (strangle against straddle, no
difference), and 1,623 (the M1 forecast of log |move| beats the implied-move-only M0 out of
sample).

**Rule.** The half-width is 0.5 IM exp(yhat_m1 - yhat_m0), against the IM/2 strangle. Both are
valued with the netted `hedged_short_strangle` on the recorded path. That function reproduces
the straddle at equal strikes to 2.8e-14 USD per share.

**Result.** It fails. The 2019-24 gain does not replicate on 2025-26.

| | 2016-18 (discovery) | 2019-24 (held-out, exploratory) | 2025-26 (exploratory) |
|---|---|---|---|
| Events (dates) | 898 (272) | 3,627 (691) | 1,083 (198) |
| Primary: forecast width minus IM/2 | +0.018 [-0.114, +0.151] | +0.087 [+0.023, +0.152] | -0.163 [-0.288, -0.032] |
| Forecast strangle minus straddle (`H_net`) | +0.000 [-0.273, +0.263] | +0.192 [+0.070, +0.315] | -0.118 [-0.406, +0.176] |
| IM/2 strangle minus straddle | -0.018 [-0.262, +0.228] | +0.105 [-0.007, +0.224] | +0.045 [-0.183, +0.284] |

Notes on the table:
- The 2025-26 read uses L1's rebuilt Yahoo paths and the frozen rule unchanged (`b8_2025.py`).
- The strangles are one contract per share. They carry less premium and vega than the
  straddle, so the comparison with the straddle is not risk-matched.
- Events that settle on the reaction session have no hedge path and are excluded (159, 558
  and 79).

**Mechanism.** M1 forecasts slightly larger moves than M0 (median width ratio 1.13, 1.07 and
1.07). The wider strangle always sells less premium: -1.01, -0.29 and -0.37% of m0. Settlement
saved offsets it by +0.98, +0.39 and +0.16. Only on 2019-24 does settlement saved exceed premium
forgone. The width trades premium against settlement close to one for one, as the idea slate's
counter-argument expected, and the 1,623 forecast does not reliably tilt that trade in the
strangle's favour.

Caveats. The wings are hedged at the ATM sigma, not at their own implied vols, so the strangle's
hedge ignores the skew. All three columns are on `H_net`, not `H_corr`.

## B11 Delta band with stock commission (trials 2,907 to 2,916)

**Nearest closed work.** laneA-hold-exit (2026-11-13 alpha-hunt-2), trial 1,787: a 0.10 band,
read once on 2019-24 at +0.016% [+0.000, +0.033] of m0. It charged only the half-spread, so a
band could save at most the equity cost. B11 differs in one mechanism: every nonzero stock order
also pays IBKR Tiered with the 1% cap (recalled), so the order count becomes a cost driver.

**Rule (diagnosis [23]).** Hedge to the Black-Scholes target at the reaction close; at each later
hedging close re-set to the target only when it differs from the position held by more than the
band; the netted expiry residual always trades. Valued through `hedged_short_straddle` with
`hedge_ratios`, so equity cost, assignment and financing follow the package. Both arms pay the
same commission, so the comparison is like for like. Band 0 reproduces `H_corr` to 5.6e-17 of m0
in every block. Grid 0.02 to 0.30 shares per straddle-share, champion chosen on 2013-18 at one
contract, then frozen (`freeze_b11_band.md`) and read once on 2019-24.

| Paired gain over band 0, % of m0 | 2013-18 (discovery) | 2019-24 (held-out, exploratory) | 2025-26 (exploratory) |
|---|---|---|---|
| Events (dates) | 2,640 (675) | 5,113 (850) | 1,562 (238) |
| Band 0.10, N = 1 | +0.084 [+0.060, +0.108] | not read | not read |
| Band 0.30 (champion), N = 1 | +0.123 [+0.042, +0.204] | +0.130 [+0.058, +0.203] | +0.139 [+0.023, +0.250] |
| Band 0.30, N = 5 | +0.040 [-0.040, +0.121] | +0.083 [+0.011, +0.155] | +0.103 [-0.011, +0.213] |
| Variance ratio, band 0.30 over band 0, N = 1 | 1.033 [1.021, 1.045] | 1.022 [1.007, 1.038] | 1.016 [1.002, 1.029] |
| Stock orders per event, band 0.30 / band 0 | 2.70 / 6.67 | 2.64 / 5.98 | 2.69 / 5.99 |
| Level with commission, band 0.30, N = 1 | | -1.204 [-1.609, -0.810] | |

Discovery at one contract, the other bands: 0.02 +0.012 [+0.009, +0.016], 0.05 +0.034 [+0.024,
+0.044], 0.20 +0.106 [+0.053, +0.159]; variance ratios 0.999 up to 0.10 and 1.009 at 0.20.

**Result.** The champion meets the pass rule's form on 2019-24 and keeps its sign on 2025-26.
Because the 2019-24 hedged-hold outcome had been viewed by earlier studies, the held-out read is
exploratory, not a clean confirmation. It is a cost recovery: the book with commission stays at
-1.204 [-1.609, -0.810] on 2019-24.

**Mechanism.** On 2019-24 at one contract the gain splits into commission saved +0.063 [+0.058,
+0.068], equity cost saved +0.018 [+0.016, +0.019], and a change in hedge P&L of +0.042 [-0.029,
+0.113]. The first two are mechanical: the band cuts orders from about six to under three per
event, and at one contract each order costs the USD 0.35 minimum. The hedge P&L term is not
distinguishable from zero in any block. Its sign is positive in 2019-24 and 2025-26 and negative
in 2013-18 (-0.015 [-0.096, +0.065]); any story for it is untested. At five contracts the
commission saved falls to +0.016, as the minimum binds less. The cost of the band is variance,
about 2% of var(H) at 0.30, against none below 0.10. Lane A's 0.10 band gained +0.016 on 2019-24 with no
commission; here the same band gains +0.084 on 2013-18 once commission is charged. The blocks
differ, so the two are not a paired comparison, but the split shows where the difference comes
from: lane A's closed verdict did not price the commission channel.

Caveats. The champion is the edge of the grid: the discovery gain was still rising at 0.30, so
the optimum may be wider still, up to hedging once at the reaction close. Wider bands were not
scored, and 2019-24 is now spent for this family, so any wider band can only be read on
2025-26 as exploratory. Every commission figure rests on recalled IB rates. The 2025-26 block
uses a constant 3 bp Yahoo half-spread, so its equity cost saved is set by that assumption.
