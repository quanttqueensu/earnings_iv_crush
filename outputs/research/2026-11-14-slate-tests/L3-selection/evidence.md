# L3 selection and other markets: evidence dossier

Panel: `L1-corrections/base_corrected.parquet` (9,350 events). Every figure is per trade, in % of
m0 (0.20 times the 15:59 parity forward plus the 15:59 straddle bid), net at the touch on L1's
basis, not annualised. Intervals are 95% percentile intervals resampling reaction-session dates
(5,000 draws, seed 0). Selectors are read on `residual_value` and `H_corr` side by side against the
participation-matched random null (statistic the mean). Discovery is 2013-18. The 2019-24 block has
already been viewed for both outcome families on this event set, and 2025-26 carries the
`hedged_event_hold 2025-26 *` row, so no read in this lane beyond discovery is clean. Shared code is
`lib.py`; the declarations and their timestamps are in `diagnosis.log`.

## C1 implied borrow from 15:59 parity

**Nearest closed study.** The parity-forward premium as a predictor of the stock reaction
(`research/selection/findings/parity_spread.md`, no effect, N=1,654). This test differs in its
target (residual value and the hedged hold) and its signal, which is spot-free: the borrow implied
by the ratio of the front and a back parity forward, b = r - ln(F2 / (F1 - D_gap)) / (T2 - T1),
with r the federal funds rate and D_gap causally projected dividends. Closest published work: Ofek,
Richardson and Whitelaw (JFE 2004), recalled.

**Build and a defect caught before scoring.** 9,348 of 9,350 events give a borrow, and the front
forward reconciles to the panel's `front_fwd` (median gap 0.52 bp). Dividend payers read a median
borrow of -0.74% a year with projected dividends and -0.81% with realised ones (`c1_describe.json`),
so projection error is not the cause; an American call's early-exercise value lifts the parity
forward of any expiry spanning an ex-date. The signal is therefore defined only on the 4,663 events
with no projected ex-date in the window (amendment A1, logged before any outcome). On those, borrow
is median +0.08% a year, 90th percentile +2.5%: this large-cap panel is almost entirely general
collateral.

**Trial 2,952 fails discovery.** Excluding the top causal decile (N=119 of 2,640, mean borrow
4.9%) changes residual value by +0.516 [-0.532, +1.625] (null percentile 86.3) and H_corr by +0.335
[-1.745, +2.548] (percentile 63.9). Held-out not read.

**Which component carries it.** Against the selected set, the excluded decile collects 1.34 points
more premium and pays 1.42 points more settlement, and the two nearly cancel. Its hedge P&L is 0.19
points worse (selected minus excluded +0.19) and its financing differs by 0.004 points, because
H_corr charges general-collateral borrow on every short hedge. That contrast is confounded.
Amendment A1 leaves every dividend payer, and every dividend-free event still in burn-in, in the
selected set, so only 1,050 of the 2,521 selected events carry a bin. The excluded decile is
therefore compared with a payer-heavy set, and its larger premium and settlement may mark non-payers
against payers rather than a volatility sort within comparable names. An exploratory check that
compares the excluded decile with the binned dividend-free events only (N=1,169, 1,050 kept;
`c1_describe.json`, not pre-registered) shrinks the premium gap to 0.82 points (selected minus
excluded -0.82 [-2.26, +0.61]) and the settlement gap to 0.86 (+0.86 [-2.39, +4.36]), both intervals
spanning zero, so roughly two-fifths of the premium gap above is the payer mix. On that comparison
H_corr moves by -0.09 [-2.25, +2.08]. The fail verdict does not rest on this reading. The cost read
prices directly the borrow that the financing line omits: re-valuing 3,865 dividend-free 2013-24
events at max(25 bp, implied borrow) through L1's own builder (which reproduces H_corr exactly on
the 2,286 events at or below general collateral) moves H_corr by -0.013% [-0.016, -0.010] on
average, -0.085% in the top decile and -0.144% [-0.220, -0.082] on the 125 events above 5% borrow.
Borrow is a real cost the valuation omits, but in this universe its mean is about a seventy-fifth of
the lane's 1% bar and even the over-5% events cost about a seventh of it, so it neither selects nor
moves the book; it would matter for a broader universe with genuine specials.

## C3 first reports after listing

**Nearest closed studies.** Own-history richness (`selection/findings/clean_iv.md`), R5 event
richness and name persistence (alpha hunt 2, lane J). C3 conditions on the absence of own history
rather than its content.

**Underpowered, not run.** Treated events are those within 365 days of the permno's earliest CRSP
`namedt`. The minimum detectable effect at 80% power, two-sided 5%, with standard deviations from
L1's descriptive 2013-18 view and a design effect of 1, is 3.87% of m0 on residual value and 8.73%
on H_corr (N=13 events on 6 names, 2013-18); 3.60% and 8.12% on 2019-24 (N=15 on 6 names); none in
2025-26. Allowing two years of listing (N=33 and 36) still leaves 2.4% on residual value. All exceed
the 1% bar, so no trial number was used and no treated outcome was read. Mechanism note: no outcome
was read, so no component is attributed. The panel is S&P 500 constituents, which rarely report
within a year of listing; the idea needs a small-cap universe whose options chains are not cached.

## C8 option-to-stock volume ratio on D-1

**Panel.** The broad panel holds only 38 events in 2013-24 on the 49 names with cached Alpaca daily
option bars, all on a single name (`c8_describe.json`), so C8 runs on the megacap hedged-hold panel.
Of its 1,794 events, 1,183 are valued; those 1,183 were re-settled through L1's
`build_base.build_one` with the closed megacap amendment's own front-row and exit readers
(`c8_megacap_panel.py`); all 1,183 reproduce the stored H exactly and all carry residual-value
marks. Stock volume comes from the local CRSP dsf slices, identified by price matching
(`c8_stock_volume.py`, 48 of 48 permnos). The megacap stale-entry-spot defect does not enter:
strike, forward and m0 come from the 15:59 entry chain's own parity forward (`megacap.front_row`),
and the stock leg reads CRSP closes reindexed on exact sessions from the reaction session onward,
failing the event rather than falling back (`spot_src` is CRSP on all 1,183). Attrition to the
scored set: 583 discovery events to 336 (436 with the feature, then burn-in) and 600 held-out events
to 562. The dropped discovery events' H_corr is 0.51 points below the kept events' and the dropped
held-out events' 0.66 points above.

**Nearest closed study and prior work.** E2's signed pre-event flow (fails held-out). C8 uses the
unsigned level of D-1 option volume relative to stock volume, from the prior complete session, so
the end-of-day leak rule holds. Roll, Schwartz and Subrahmanyam (JFE 2010) relate a high ratio to
larger absolute announcement returns; Garleanu, Pedersen and Poteshman (RFS 2009) relate end-user
demand to richer options (both recalled).

**Trial 2,953.** Selecting the top causal tercile passes its declared discovery rule: residual
value +1.234 [+0.570, +1.897], null percentile 99.9, N=336 (132 selected), with H_corr +0.978
[-0.831, +2.792]. Read once after `freeze_c8.md`, held-out 2019-24 gives residual value +0.852
[+0.359, +1.336], null percentile 99.9, but H_corr -0.295 [-2.444, +1.736] (percentile 39.5),
N=562 (232 selected), so the rule fails on its H_corr condition. The H_corr read is exploratory,
because the closed amendment 02 already read this block's hedged hold.

**Which component carries it.** Mostly residual tenor, not option demand. Every selected event has
one to four calendar days left after the reaction session, while the unselected set includes the
monthly-only listings (31 events in discovery, 22 in held-out) that leave 8 days or more and a
residual value of about -8 to -10.5% of m0, against about -2% for weekly tenors. A low ratio marks
those names. Inside tenor strata the contrast is +0.242 [-0.303, +0.755] on discovery and +0.225
[-0.191, +0.633] on held-out, both declared before the held-out read, so residual tenor carries
about 80% of the discovery lift (+1.234 to +0.242) and about three-quarters of the held-out lift
(+0.852 to +0.225). What remains is a within-weekly effect of about 0.2 points, not distinguishable
from zero and not excluded either. The 8-day-and-over stratum holds no selected event in either
block, so it adds nothing to the stratified contrast. In H_corr terms, the selected events collect
about 3.9 points more premium and pay 4.1 (discovery) to 5.3 (held-out) points more settlement;
their hedge P&L is about 1.1 points better. The net is noise. The residual-value metric rewards
short residual tenor by construction, which is a property of the contract listed, not of the event,
and the earlier closed monthly-expiry selector (trial 1,611) already tested that lever on the hedged
hold.

## F3 same-session concentration cap (risk read, not an edge trial)

**Nearest closed study.** The earnings-covariance study (`selection/findings/season_state_and_earnings_covariance.md`),
which found reporter count sufficient for the common component. F3 uses that result as a rule:
keep at most k events per entry session, chosen uniformly at random (200 seeded draws), one unit of
m0 per event, on `H_corr`.

**Risk, against exposure-matched baselines.** Units are % of one event's m0 per session; capped
figures are medians across draws (`f3_risk.json`, `f3_matched.json`). A capped book trades fewer
events, so its raw risk is set against two books at the same trade count: the uncapped book with
every event held at the size ratio n_cap / n_uncap ("scaled"), and the uncapped book thinned at
random across the whole block, ignoring sessions ("thinned", 200 draws).

| Block, book | Trades | Session sd: capped, scaled, thinned | Worst session: capped, scaled, thinned | Tail share |
|---|---|---|---|---|
| 2013-18 uncapped | 2,640 | 23.9 | -152 | 0.349 |
| 2013-18 cap 5 | 1,800 | 19.2, 16.3, 20.9 | -101, -104, -131 | 0.324 |
| 2013-18 cap 3 | 1,364 | 16.7, 12.3, 19.0 | -75, -79, -115 | 0.337 |
| 2019-24 uncapped | 5,113 | 37.9 | -291 | 0.405 |
| 2019-24 cap 5 | 2,543 | 24.4, 18.8, 27.8 | -175, -145, -178 | 0.356 |
| 2019-24 cap 3 | 1,870 | 20.7, 13.9, 24.6 | -118, -107, -155 | 0.356 |
| 2025-26 uncapped | 1,562 | 40.5 | -166 | 0.422 |
| 2025-26 cap 5 | 762 | 25.2, 19.8, 28.9 | -87, -81, -118 | 0.369 |
| 2025-26 cap 3 | 539 | 20.6, 14.0, 25.1 | -87, -57, -99 | 0.352 |

Tail share is the share of all losing-session P&L that comes from the worst 5% of sessions; it
does not change when every position is scaled, so the uncapped figure is its own scaled
baseline. The conservative reading is that the cap cuts risk only by trading less. At the same
exposure, holding every event at a smaller size gives a lower session sd than the cap in every
block and at both caps (by 2.9 to 6.8 points), and a smaller worst session except in 2013-18.
The cap does beat dropping the same number of trades at random on both measures in every block,
and it leaves a slightly less tail-concentrated loss distribution, so it is the better of the two
ways to trade less when position size cannot be cut (one-lot minimums); it is not a better use of
a given exposure. Drawdown is not used as a risk measure here: on a book whose mean is negative it
restates the mean times the trade count.

**Which component carries it.** Session sd grows with the count of reporters (2019-24: 19 for
one to three events, 54 for 11 to 20, 81 above 20; `f3_risk.log`), the common earnings-night move
of the closed covariance study. The cap removes exposure from exactly those sessions, but leaves
quiet sessions at full size with few events to diversify each other, which is why uniform
scaling does better at equal exposure. The per-trade mean shift is a separate, exploratory
effect of reweighting toward quiet sessions: uncapped means are -0.983 [-1.434, -0.523] on
2013-18, -1.194 [-1.591, -0.804] on 2019-24 and +0.087 [-0.718, +0.845] on 2025-26, and capped
minus uncapped at a cap of 5 is -0.019 [-0.205, +0.171], +0.299 [+0.037, +0.553] and +0.627
[+0.156, +1.075] (`f3_weighted.json`). On 2019-24 the shift comes from premium (+0.25 points)
more than settlement (+0.09); on 2025-26 from settlement (+0.87, smaller realised moves in quiet
sessions) partly offset by hedge P&L (-0.33) (`f3_matched.json`, points only). It is absent on
discovery and read on viewed blocks, so it is a lead for a declared session-size selector, not a
finding; the closed season-state study flipped sign across blocks.

## C2 short interest (FINRA): blocked

**Nearest closed studies.** The lottery and idiosyncratic-volatility selectors and the distress
tail screens, which proxy the same squeeze risk with price data.

**Why it was not run.** FINRA publishes Rule 4560 short interest twice a month for exchange-listed
and OTC equities, but the free archive files (from 2014) contain OTC securities only. Exchange-listed
history is in the interactive grid and the Consolidated Short Interest API, both limited to five
rolling years (from about late 2021). The API serves only registered credentials, and the site
terms bar storing content for later use without FINRA's consent (`sources.csv`). No permitted,
credential-free source covers the discovery block for this panel's names, so C2 is recorded as
blocked and no trial number was used. The NYSE product is, as recalled and not checked, a paid feed, and Nasdaq and Yahoo are excluded
by the brief. Mechanism note: none attributed, as nothing was scored. If the team registers a FINRA
API account, about three years of 2022-24 plus 2025-26 could be read, which would support only a
single-block exploratory read.

## E5 ForecastEx FES and FNQ against SPY and QQQ digitals

**Nearest closed study and prior work.** N11 compared ForecastEx with Kalshi and tested
ForecastEx favourites (both fail held-out). E5 uses an independent reference, the digital implied
by the cached ETF option chains, on the financial daily contracts. The closest prior evidence is
the favourite-longshot literature on event contracts (Burgi, Deng and Whelan 2026, verified by
N11); no study comparing these contracts with option-implied digitals was found.

**Data and design.** The pairs and daily prices CSVs come from ForecastEx's public bucket, which
has no robots.txt and needs no registration (`sources.csv`, `e5_fetch.py`; 19 MB kept after
filtering to FES and FNQ). FES resolves on the CME E-mini S&P 500 lead-month daily settlement at
about 16:00 ET. The cached chains omit the same-day expiry, so each contract dated d is observed on
d-1 against the ETF expiry dated d at 15:59. The ES and SPY levels differ by a basis not on disk,
so the digital is aligned on the contract ladder's own median. The test is therefore of the
ladder's shape, not its level. ForecastEx publishes trades, not quotes, so the last trade plus the
USD 0.01 fee stands in for the touch. Two amendments were made on liquidity counts before any
outcome was read. E5-A1 widened the window to [12:00, 15:59] ET and set a floor of 30 priced
dates. E5-A2 moved the split to discovery 2025-04 to 2026-03 and held-out 2026-04 to 2026-10,
because 2025 alone had too few ladders.

**Trial 2,954 (FES) fails discovery.** The rule buys whichever side the aligned digital values
above its cost by more than 0.02. It makes +0.044 USD per USD 1 contract [-0.044, +0.126], net of
fee, on 62 trades over 32 dates, at the 92.1 percentile of a random-side null whose median is
-0.009. The held-out block was not read. Trial 2,955 (FNQ) has 19 priced dates, under the floor,
and was not scored.

**Which component carries it.** The rule leans on one pattern, ForecastEx YES prices sitting
above the option-implied probability: on average +0.015 above the aligned SPY digital on 137
contracts, and 44 of the 62 trades buy NO. The SPY digital also forecasts slightly better (Brier
0.1449 against 0.1485). This is the favourite-longshot tilt N11 found on other ForecastEx products,
but the touch proxy and the 0.01 fee consume most of it, and 278 of 391 contract dates have no
ladder to align at all. The binding constraint is liquidity, not the data rule. The 2026-04 to
2026-10 block is far more liquid and is still unviewed for this rule, so a pre-registered read of
it is the one clean next step. It needs a quote history (for example the IB ForecastTrader feed in
the paper account) before any fill claim.
