# L2 execution and cost: evidence dossier

Basis of every figure unless the entry says otherwise: per trade, % of m0 (0.20 times the 15:59
parity forward plus the 15:59 straddle bid), net at the touch, not annualised. Intervals are
date-clustered 95% percentile intervals (`protocol.date_clustered_ci`, 5,000 draws, seed 0).
The outcome is `H_corr` of `L1-corrections/base_corrected.parquet` (netted, early call
assignment, financing). Discovery is 2013-18 and held-out 2019-24. The hedged_hold outcome on
2019-24 had already been viewed by other feature families, so every 2019-24 read below is
exploratory as well as held-out. 2025-26 is exploratory. Every number traces to a json or log in
this folder; `diagnosis.log` holds each declaration, written before its computation.

All levers re-value one recorded path. `build_paths.py` imports L1's `build_base.py` and records
the inputs of every `H_corr` valuation. Re-valuing them reproduces `H_corr` exactly on 9,315
events (8,236 hedged; `build_paths.log`). Changing one input therefore isolates one lever.

## B1 Closing-auction hedging (trials 2,892 to 2,895)

**Nearest closed work.** The hedged hold charges max(CRSP closing half-spread, 1 bp) per side at
each hedging close. E1's mirror arm (2,691) closed intraday hedging of the short. Nothing has
priced the auction before. No auction data exist on disk, so the auction impact a is a declared
grid and every figure here is assumption-based.

**Result as declared.** The MOC arm pays a plus IB's MOC charges in place of the half-spread,
compared with `H_corr` at one contract. It fails.
- 2013-18 (N = 2,640, 675 dates), at a = 0.5 bp: -0.109 [-0.127, -0.088].
- 2019-24 (N = 5,113, 850 dates): -0.029 [-0.039, -0.016].
- 2025-26 (exploratory, constant 3 bp Yahoo half-spread): +0.036 [+0.029, +0.043].
- The break-even auction cost a* at N = 1 is -0.03 bp [-0.46, +0.53] on 2013-18 and +1.70 bp
  [+1.39, +2.06] on 2019-24. The kill rule (a* < 0.5 bp) fired on discovery.

**Like for like (a statistic switch, not a pass).** Here both arms pay the same commission per
order, and the continuous arm also pays a USD 0.003 take fee.
- At a = 0.5 bp: +0.095 [+0.082, +0.112] (2013-18) and +0.095 [+0.086, +0.106] (2019-24).
- a* is +2.26 bp [+1.85, +2.82] and +2.87 bp [+2.59, +3.21]. The mean half-spread charged
  today is 2.03 bp per side [1.62, 2.58] on 2013-18.

**Tracking error.** The ratio has to be set from a 15:50 price, simulated at the hold's own sigma.
It changes the mean by -0.011 [-0.032, +0.010] (2013-18) and -0.024 [-0.048, +0.000] (2019-24).
The variance ratios are 1.0013 [0.9979, 1.0048] and 1.0087 [1.0045, 1.0133], so it is negligible.

**Mechanism.** By construction the change sits entirely in `c_equity_cost` (and in `c_hedge` for
the tracking variant). The declared comparison fails because of an asymmetry the brief carried
in: `H_corr` charges the hedge a half-spread but no stock commission. At one contract the hedged
hold sends about 7.1 stock orders per hedged event, each paying at least IB Tiered's USD 0.35
minimum. Priced that way they cost -0.204% of m0 [-0.220, -0.189]. That is twice the whole
half-spread charge on the hedging closes (-0.100 [-0.117, -0.087]). Once both arms pay that
commission, the auction saves about 0.1% of m0 per trade in every block. The saving survives
any auction impact up to about 2.3 to 2.9 bp per side, but it is a cost recovery on a book that
loses about 1% of m0 per trade.

## B10 Fee arithmetic (trials 2,896 to 2,900)

**Nearest closed work.** `HedgedHoldConfig.fee_per_contract_leg` = USD 0.65, never checked against
a schedule. The schedule figures are below. Only two were read at the source. Interactive
Brokers' pages could not be read by an automated client, so every IB figure is recalled.

| Item | Figure | Status |
|---|---|---|
| NYSE non-tier MOC order executed in the closing auction | USD 0.0010 per share | verified, NYSE Price List 2026 (last updated 2026-11-02) |
| Cboe Options (C1) customer equity option, under 100 contracts, removing liquidity | USD 0.00 | verified, Cboe Exchange Fees Schedule (2026-11-09) |
| IBKR Pro Fixed options | USD 0.65 per contract, USD 1.00 per order minimum, fees included | recalled |
| IBKR Pro Tiered options, lowest tier | USD 0.65 per contract plus clearing USD 0.02 and regulatory about USD 0.03 | recalled |
| Maker-taker venue, penny class | take USD 0.50, rebate USD 0.25 | recalled |
| IBKR Pro stock, Fixed / Tiered | USD 0.005 per share (min 1.00) / USD 0.0035 per share (min 0.35) plus pass-through | recalled |

**Option commission.** Each line is the change against the assumed fee, at N = 1, entering as a
single combo order.
- Fixed changes nothing: 0.000 in every block.
- Tiered taking on C1: -0.008 [-0.009, -0.008] (2013-18) and -0.006 (2019-24).
- Tiered taking on a maker-taker venue: -0.091 [-0.094, -0.088] and -0.065.
- Tiered resting with the rebate: +0.033 [+0.032, +0.034] and +0.024. This applies only to a
  resting entry that fills.

**The omitted stock commission.** The stock commission is the larger item.

| Stock commission | 2013-18 | 2019-24 | 2025-26 (exploratory) |
|---|---|---|---|
| Tiered, N = 1 | -0.224 [-0.241, -0.209] | -0.141 [-0.149, -0.134] | -0.108 [-0.118, -0.099] |
| Fixed, N = 1 | -0.527 [-0.569, -0.488] | -0.323 [-0.341, -0.305] | -0.248 [-0.272, -0.225] |
| Tiered, N = 5 | -0.098 [-0.104, -0.092] | -0.066 [-0.069, -0.063] | -0.050 [-0.054, -0.047] |

Adding the cheaper stock schedule and Tiered-C1 option fees moves the corrected level as follows:
- 2013-18: -0.983 to -1.215 [-1.669, -0.755] at N = 1, and to -1.086 at N = 5;
- 2019-24: -1.194 to -1.341 [-1.740, -0.950] at N = 1, and to -1.262 at N = 5.

**Mechanism.** The option schedule is a rounding error, at most a few hundredths of m0 unless the
order takes on a maker-taker venue. The hedge's order count is the real fee item. It is fixed per
order, so it falls with size (N = 5 cuts it by more than half) and with fewer rebalances. A delta
band attacks it directly (laneA-hold-exit's 0.10 band was +0.016%. If, as here, its valuation priced no stock
commission, that understates the band's value; this was not checked). This is a correction to the cost basis of every
lane, sent to the team lead.

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
and financing net -0.42 and -1.10. That is the same sign as the always-later control, which
loses on the diffusive leg of a longer contract, not on the touch. So the touch is where the
choice is made, but the longer tenor's mid-level loss carries the outcome.

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

The hedge as a whole does matter for variance. `c_hedge` has a correlation of -0.69 (2013-18)
and -0.72 (2019-24) with premium plus settlement, and var(H) is about half of var(premium plus
settlement). A one-close tilt of the ratio is simply too small to move it. That most of the
remaining var(H) is the unhedged announcement gap is a conjecture: it was not decomposed here.

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
60 to 69%. The gain is the half-spread net of drift. It comes from waiting when the spread is
wide: the always-15:00 control does worse than the rule on both years.

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
counter-argument expected. The forecast's term-structure information (1,623) does not reliably
reach the strangle's P&L once its wings are priced at the touch.
