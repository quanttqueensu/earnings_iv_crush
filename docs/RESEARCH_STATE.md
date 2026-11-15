# Research state

The trial count, every direction that is closed and the number that closed it, and the figures
that must never be quoted. Read this before proposing anything: most ideas that sound new here
have been tested. Update it in the same commit as the trial it records.

## 1. Trial count

Every strategy-level Sharpe in this project is read against the number of configurations tried,
because the more that are tried the higher the best one scores by chance (the Deflated Sharpe
Ratio, Bailey and Lopez de Prado 2014). Abandoned branches count.

- **Last count fixed in a hash record: 1,498**, after the P1 skew test
  (`outputs/research/prereg_p1_skew_reaction.json`, `dsr_trial_count`, declared 2026-10-15).
- Declared after that record, not yet consolidated into one number: date shift (1), the frozen
  ML ratio predictor (9, of which one confirmation), its second confirmation (1), the 15:59 model
  zoo (375 walk-forward strategies, reported as one zoo verdict), the nested walk-forward (1), and
  the section 2.1 peer test (3, declared earlier at 1,489). Earlier working notes put the total at
  about 1,506 and at about 1,532; they disagree, and nothing on disk resolves the difference.
- The hedged-hold, jump-richness, post-event-equity and inversion studies added 12 trials on top
  of 1,532 (`outputs/research/prereg_2026-10-21-inversion-confirm.json`, `dsr_trial_count` 1,544). The
  1,532 base inherits the disagreement above.
- Declared 2026-11-10, verdicts unsigned: five pre-event directional trials on the stock (1,593
  to 1,597, `outputs/research/prereg_2026-11-10-pre-event-direction.json`) and five non-price
  selectors on the hedged hold (1,598 to 1,602,
  `outputs/research/prereg_2026-11-10-nonprice-selectors-hedged-hold.json`), and one 8-K
  news-flow selector (1,603, `outputs/research/prereg_2026-11-10-8k-newsflow-hedged-hold.json`).
  All eleven fail at discovery. Later the same night: three tests on the hackathon panels
  (1,604 to 1,606), Wikipedia attention (1,607), a megacap replication of the pre-announced
  selector (1,608) and two lottery-stock direction trials (1,609 to 1,610); none passes its
  frozen rule. Hash records `outputs/research/prereg_2026-11-10-*.json`; rows for section 2 await
  the analyst's signature.
- Declared 2026-11-11, verdicts unsigned: five selectors on the hedged hold (1,611 to 1,615:
  monthly expiry, penny-tick threshold, low idiosyncratic volatility, stable earnings surprises,
  macro release on the reaction session;
  `outputs/research/prereg_2026-11-11-exogenous-cost-and-stability.json`). All five fail at
  discovery.
- Declared 2026-11-12, verdicts unsigned: seven pre-event tail-gate trials (1,616 to 1,622,
  `outputs/research/prereg_2026-11-12-tail-event-signals.json`), all failing discovery; a
  move-size forecast (1,623) that passes on option term-structure information, not the non-price
  information it was framed around; and five sizing schemes (1,624 to 1,628) whose primary
  statistic was ill-posed for a negative-mean book, so no verdict is informative
  (`outputs/research/prereg_2026-11-12-move-forecast-and-sizing.json`). Both findings were
  corrected after an independent post-run review.
- 2026-11-13, two exploratory alpha hunts with unhashed freeze notes: 117 variants in five lanes
  (1,629 to 1,771 and 1,644b; `outputs/research/2026-11-13-alpha-hunt/SUMMARY.md`) and 228 trial
  numbers in ten lanes (1,781 to 2,036 in reserved blocks, 2,051 to 2,080 and 2,081;
  `outputs/research/2026-11-13-alpha-hunt-2/SUMMARY.md`), 345 in all. One row per lane in
  `research/ledger/trials.csv` (regime `exploratory-unhashed`) and their block views in
  `blocks.csv`. Unused reserved numbers are not trials. Declared 2026-11-13 under P16 to P21: the
  resting-entry confirmation, trials 1,779 and 1,780 (renumbered from 1,629 and 1,630 by amendment
  01, `outputs/research/prereg_2026-11-13-maker-entry-confirmation.json`), both passing.
  The twenty-lane niche hunt (other markets, 2026-11-13) reserved 2,082 to 2,681, thirty per lane
  (`outputs/research/2026-11-13-niche-hunt/RESERVED_TRIAL_IDS.md`), and used 158 of them in 15
  lanes (`outputs/research/2026-11-13-niche-hunt/SUMMARY.md`); one `exploratory-unhashed` row per
  lane in `research/ledger/trials.csv` and 28 block views in `blocks.csv`. Reserved 2026-11-14 for
  the five-lane earnings-adjacent hunt: 2,682 to 2,831, thirty per lane
  (`outputs/research/2026-11-14-earnings-adjacent-hunt/RESERVED_TRIAL_IDS.md`), of which 43 were
  used (`outputs/research/2026-11-14-earnings-adjacent-hunt/SUMMARY.md`); one
  `exploratory-unhashed` row per lane in `research/ledger/trials.csv` and 25 block views in
  `blocks.csv`. Reserved 2026-11-14 for the slate tests: 2,832 to 3,131
  (`outputs/research/2026-11-14-slate-tests/RESERVED_TRIAL_IDS.md`), of which 51 were used
  (`outputs/research/2026-11-14-slate-tests/SUMMARY.md`; for deflation the Bayesian density model
  also carries at least 800 searched configurations); one `exploratory-unhashed` row per lane plus
  one team-lead row in `research/ledger/trials.csv` and 54 block views in `blocks.csv`.
  Reserved 2026-11-15 for the deep-learning programme: 3,132 to 3,231
  (`outputs/research/2026-11-15-deep-learning/RESERVED_TRIAL_IDS.md`), of which 41 were used
  (`outputs/research/2026-11-15-deep-learning/SUMMARY.md`; for deflation the networks also carry
  41 and 24 searched configurations); one `exploratory-unhashed` row per lane plus one team-lead
  row in `research/ledger/trials.csv` and 19 block views in `blocks.csv`. Next free: 3,232.
- `python -m earnings_iv_crush.ops.orient` reports the largest count found in the hash records.
- **Open item:** rebuild the count as one tracked ledger file (`docs/ROADMAP.md`). Until then,
  quote "about 1,500" and use 1,532 as the conservative deflation input.

Under no edge, the expected best per-trade Sharpe from a search this size is about +0.43.

## 2. Closed directions

Each row is closed: do not spend effort on it again without a new mechanism and a new
pre-registration. Verdicts are per trade, date-clustered 95% intervals, on the stated block.
Evidence paths are under `research/` unless marked.

The 2026-11 exploratory programmes keep their lane folders under `outputs/research/`, which is
shared through the R2 bucket rather than git. Each programme's summary is also tracked as a dated
findings note:

- `research/selection/findings/2026-11-13-alpha-hunt.md` and `2026-11-13-alpha-hunt-2.md`;
- `research/other_markets/findings/2026-11-13-niche-hunt.md`;
- `research/timing/findings/2026-11-14-earnings-adjacent-hunt.md`;
- `research/selection/findings/2026-11-14-idea-slate.md`;
- `research/execution/findings/2026-11-14-slate-tests.md`;
- `research/selection/findings/2026-11-15-deep-learning.md`.

### The term-structure selector

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Term gate q=0.80 | does not carry forward | broad 2025-26 Sharpe -0.210 [-0.347, -0.058], N=232, loses to matched random | `frozen_selector/` |
| Why it fails | selects jump size, not mispricing | 91% of its top-minus-bottom gap is premium collected (+0.0385 of +0.0422); residual value moves the wrong way (-0.0082) | `selection/findings/reverse_alpha.md` |
| `jump_richness` latent variable | look-ahead artefact | causal 2013-18 Sharpe -0.184 [-0.326, -0.033] | `selection/findings/reverse_alpha.md` |
| Move, skew, kurtosis, curvature gates | fail out of sample | skew DSR 0.00 out of sample; curvature -0.164 | `frozen_selector/findings/skew_validation.md` |
| VRP, vol-premium, trailing-RV overlays | no incremental lift | ordering only, `agent_comparison.csv` | `frozen_selector/agent_comparison.py` |

### Selection on mispricing

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Name persistence overlay, executable marks | lift indistinguishable from zero | out-of-sample delta +0.0037 [-0.011, +0.018] | `selection/research_name_persistence_exec.py` |
| Own-history richness (clean IV) | fails out of sample | | `selection/findings/clean_iv.md` |
| Section 2.1 peer-informed selection (A, B, C) | all three fail discovery | | `selection/findings/section21_peer.md` |
| P1 put skew predicts the stock reaction | wrong sign | decile gap -0.58 points [-2.30, +1.18], N=1,580 | `selection/findings/p1_skew_reaction.md` |
| Parity-forward premium predicts the reaction | no effect | gap -0.01 points [-1.72, +1.72], N=1,654 | `selection/findings/parity_spread.md` |
| Frozen ML ratio predictor | fails the second confirmation | Jul-Aug 2026 selected minus unselected +1.31% [-0.93%, +3.80%], N=199; the earlier broad pass came from leaked Alpaca end-of-day features | `selection/findings/ml_ratio_confirm2.md` |
| 375-strategy model zoo on 15:59 features | no selection skill | 49.6% beat their rejected events; ensemble gap +0.03 points [-0.46, +0.53] over 9,529 events | `selection/findings/ml_zoo.md` |
| Nested walk-forward | noise-fitting | gap +0.64 points [+0.01, +1.26], positive in 5 of 10 years, selected book -1.18% per trade | `selection/findings/ml_zoo.md` |
| Earnings-date shifts (Johnson and So 2018) | sign reversed | on-time minus delayed -0.66% [-1.92%, +0.64%]; advanced dates +2.24% [+0.32%, +4.12%] on 174 events is secondary and forward-testable only | `selection/findings/date_shift.md` |
| Retail ownership from 13F | fails discovery | decile Spearman +0.24 | `selection/findings/final_earnings_set.md` |
| Risk-normalised sizing | no block improves | | `selection/findings/final_earnings_set.md` |
| Sequential season state | sign flips across blocks | -0.0334 vs +0.0916 | `selection/findings/season_state_and_earnings_covariance.md` |
| Earnings covariance, firm-weighted | reporter count is sufficient | load slope +315 [-2,877, +3,498] with count control | same |
| Forward-variance reset | not measurable on obtainable strips | 0 of 75 events converge | `selection/findings/forward_variance_reset.md` |
| Crush forecasting | real skill, no monetisation | | `selection/findings/crush_forecast.md` |
| P5 short strangle against the straddle | no difference | paired +0.42% [-1.04%, +1.53%], N=94, sample biased by exit attrition | `selection/findings/p5_strangle.md` |
| Cross-sectional long-short | the long leg pays its own crush | edge only in the top quintile | `docs/reference/RESEARCH_RECORD.md` 6.4 |
| Ex-diffusive implied jump over a causal jump forecast (two-expiry split) | fails discovery | top minus bottom R_adj -0.0013 [-0.0037, +0.0013], N=2,041, null percentile 84.2 | `selection/2026-10-20-jump-richness/findings.md` |
| Post-event 25-delta put skew predicts the next 20 sessions | fails discovery | -0.28% per position [-0.96%, +0.36%], N=451 | `selection/2026-10-20-post-event-equity/findings.md` |
| Post-event term slope predicts the next 20 sessions | sign reversed | -0.91% [-1.64%, -0.18%], N=486 (2013-18) | same |
| Reversed slope: inverted names outperform | fails validation and confirmation | long-short 2019-24 +0.37% [-0.29%, +1.02%], N=1,137; beta-hedged 2025-26 +0.18% [-1.08%, +1.37%], N=210, underpowered | `selection/2026-10-21-post-event-inversion/findings.md` |

### Execution and cost

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Better fills on the fixed 15:59 book | worth about +0.007 Sharpe | measured cost 1.7871% per side | `execution/findings/` and `outputs/research/fills_rescore.csv` |
| Causal spread gate, megacap | no net premium left | gated -0.0347 [-0.1443, +0.0827] (2013-18, N=316), -0.0070 [-0.1031, +0.1073] (2019-24, N=372) | `execution/findings/cost_levers.md` |
| Spread gate, broad 2025-26 | fails at the touch | gated Sharpe -0.224; gated events carried no gross premium | `selection/findings/final_earnings_set.md` |
| Entry-spread filter on DoltHub | invalid, not failed | adapter lookback made 54.1% of pairs use the entry chain as the exit chain | `execution/findings/dolthub_defect.md` |
| Resting entry, hedged hold (53aa4898, 2025-26) | passes, conditional on a block partly seen; size not confirmed | +0.89% [+0.77, +1.01] of m0 vs the 15:59:00 cross, N=1,136; do not quote as the lever's size | `outputs/research/2026-11-02-maker-entry-hedged-hold/results.json` |
| Resting entry confirmation (1,779, 1,780; 2023-24, unseen) | both pass; sign confirmed, size about a quarter of 53aa4898; economically small | static mid vs 15:59:00 cross +0.217% [+0.154, +0.278] of m0, t 6.78; re-pegged vs plain 15:45 cross +0.236% [+0.195, +0.278], t 11.25; N=1,703; quote-only fill rule +0.12% and +0.16%; 60 to 69% of the half-spread given back to drift | `research/execution/2026-11-13-maker-entry-confirmation/review_post.md` |
| Resting orders (maker F1) | fails the markout gate in both blocks | broad +2.06% [+1.82, +2.32], markout -0.68; megacap +0.48%, markout -0.93 | `execution/findings/flow_liquidity.md` |
| Demand pressure (F2) | fails discovery | | same |
| Calendars, iron fly, disaster wings | net negative | wing about 2.4% of margin against a 0.6-0.95% budget | `docs/reference/RESEARCH_RECORD.md` 6.2 |

### Timing and holding

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Conditional hold to expiry, frozen on 2013-18 | fails | mean advantage +0.0018 of margin [-0.0045, +0.0087], N=193 | `execution/findings/cost_levers.md` |
| Post-announcement straddle held to expiry | fails net | net RoM -1.41% [-3.23%, +0.20%], N=1,888 | `timing/findings/post_event_vrp.md` |
| Post-announcement overpricing | underpowered, controls disagree | 119/110 pairs against 1,200 designed | `timing/findings/post_announcement_overpricing.md` |
| Pre-announcement vega run-up (D-5 to D-1) | loses at the touch | -11.72% [-13.09%, -10.34%] of premium, N=922 | `timing/findings/vega_runup.md` |
| Hard stop | cannot fire inside the gap | one overnight mark | |
| Delta-hedged short straddle held to expiry, pre-event (20-45 and 46-120 days) and post-event (14-45 days) | fails discovery at the touch | net RoM -0.36% [-0.59%, -0.14%] (N=2,230), -0.39% [-0.73%, -0.10%] (N=2,428), -0.36% [-0.53%, -0.19%] (N=2,604); positive at the mid, one half-spread is 4-6% of premium | `timing/2026-10-20-hedged-hold/findings.md` |
| HAR, GARCH and post-event slope selectors on the hedged hold | fail discovery | top minus bottom vol points per vega between -0.73 and +0.16, every interval spans zero | same |

### The 2026-11-13 alpha hunts (exploratory)

Both hunts froze with unhashed notes, so every row is exploratory, and the hunts' process
failures are listed in their summaries. Effects are per trade, net at the touch, date-clustered
95% intervals, in m0 (0.20 times forward plus the 15:59 bid) unless stated; "book" is the level of
the chosen book. Hedged-hold figures use the expiry convention frozen before 2026-11-13; the
adopted netting (`HEDGED_NET`) lifts the hold by +0.22% of m0 [+0.21, +0.23] on 2013-24 and
leaves the buy-back unchanged. Evidence paths are under
`outputs/research/2026-11-13-alpha-hunt/` (round 1) and `outputs/research/2026-11-13-alpha-hunt-2/`
(round 2).

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Market state (SPY near its 52-week high, VIX) as a selector | fails held-out | +0.031 of premium [-0.001, +0.064], N=5,713 (2019-24) | `lane1-macro/report.md` |
| Forensic, liquidity and size flags | reproduce the closed spread gate | discovery screens only | `lane2-forensics/report.md` |
| Event richness against own history (R5) | reverses on held-out | discovery +0.071 [+0.010, +0.131] of premium, held-out 2020-24 -0.013 | `lane3-surface-flow/report.md` |
| Calendar and cross-section niche features | fail; early-in-industry fails held-out | +0.029 of premium [-0.009, +0.066], N=4,550 (2019-24) | `lane5-niche/report.md` |
| Decisions after the announcement on the hedged hold (buy-back, partial unwinds, stops, delta bands, HAR buy-back) | closed: the loss is sunk in the gap | best held-out rule, 0.10 delta band, +0.016% [+0.000, +0.033] (2019-24); perfect-foresight hold-or-buy-back ceiling after netting -0.13% [-0.56, +0.30] (2013-18) and +0.10% [-0.25, +0.45] (2019-24) | `laneA-hold-exit/report.md` |
| Post-event diffusive premium, as a hold-or-close rule or an entry signal | fails held-out; the premium is about zero net of hedging | forecast top minus bottom +0.16% [-0.64, +0.95], N=4,203 (2019-24); net diffusive part -0.22% [-0.51, +0.07] | `laneC-post-event-vrp/report.md` |
| Tightest-quoted of the three central strikes, event-night delta matched (1,819) | held-out pass, cost recovery; confirmatory status contested (trial 1,560 viewed the outcome family) | +0.21% [+0.14, +0.28], t 5.7, N=5,092 (2019-24); book -1.05% | `laneB-contract-choice/report.md` |
| Half-move strangle with spread-aware wings at equal vega (1,826) | exploratory cost recovery; not yet re-valued under netting | +0.55% [+0.40, +0.71], t 7.0, N=5,041 (2019-24); book -0.66% | same |
| Walk-forward boosted trees on round 1's features, cost features removed | fails held-out | +0.031 of premium [-0.016, +0.077], t 1.32 (2022-24) | `laneE-walk-forward-model/report.md` |
| Re-pegged resting bid on the buy-back | passes on broad 2026, fails on megacaps; loses to the hedged hold | +0.81% [+0.63, +1.00], N=419; megacap +0.02% [-0.19, +0.23], N=243; resting buy-back minus hold -1.74% [-2.43, -0.98] | `laneF-resting-exit/report.md` |
| Index options on mega-cap earnings nights (QQQ) | priced fairly; fails | implied extra night variance 6.3e-5 against realised 9.3e-5 (2019-24, N=79); post-release long +3.1% of debit [-8.6, +16.0] (2025-26, not clean) | `laneG-index-event-vol/report.md` |
| FDA advisory committees and mega-cap product events (DoltHub) | fail; pilot, N under 20 | committee short -0.058 [-0.138, -0.009], N=18; event minus controls +0.004 [-0.052, +0.040], N=16 (2022-24) | `laneH-other-scheduled-events/report.md` |
| Selling the event straddle 2 to 10 sessions early | loses | 7-10 sessions early minus standard -1.52% [-2.24, -0.83], N=815; 2-3 sessions -0.81% [-1.50, -0.21], N=378 (2019-24, unseen names) | `laneI-entry-day/report.md` |
| Residual value as a persistent property of a name | fails held-out | persistence r +0.011 [-0.234, +0.271]; selector +0.002 of premium [-0.122, +0.126] (2019-24) | `laneJ-name-persistence/report.md` |

### Away from earnings, and other markets

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| P2 de-eventised term slope (DoltHub) | kill rule fires | touch -7.79% [-18.06%, +2.23%] of premium, N=2,972 name-months | `off_earnings/findings/p2_term_slope.md` |
| SPY macro-release straddles | not testable on DoltHub (N=5); re-run on the cached Databento chains by amendment 03, fails | short CPI/payrolls, at the touch, per trade on premium: +4.27% [-2.70, +10.86] (97.5%), N=138 (2019-24); long FOMC +2.48% [-11.14, +19.60], N=44 | `off_earnings/findings/spy_macro.md`; `outputs/research/2026-11-01-index-event-crush/summary.json` |
| Index VRP timing | does not survive post-2008 | t +0.24 to -1.42 | `off_earnings/findings/pivot_verdicts.md` |
| PEAD on SUE | directionally positive, not established | DSR 0.0597 against 16 trials | same |
| Deribit BTC macro events | ordinary variance premium, no event surplus | paired +0.079% [-0.275%, +0.440%], N=116 | `other_markets/findings/deribit_macro.md` |
| Kalshi tail selling | loses at the touch | -2.03% per bet [-4.07%, +0.21%], N=383 | `other_markets/findings/kalshi_tails.md` |
| Kalshi maker | does not replicate | -1.37% on 81 unseen series, 39 fills | `other_markets/findings/kalshi_replication.md` |
| India (NSE), Brazil (B3) | no gross signal / inside the spread | India negative gross at every cut; Brazil +6.4% gross inside a 24% spread | `docs/reference/RESEARCH_RECORD.md` 6.6 |

### The 2026-11-13 niche hunt: other markets (exploratory)

Every row is exploratory (158 trials, freeze notes not filed as pre-registrations, several held-out
blocks already viewed). "Settle" and "index" rows are gross ceilings at settlement or an index mid,
not tradeable levels. Paths are under `outputs/research/2026-11-13-niche-hunt/`; `SUMMARY.md` lists
the review corrections and the robots.txt breaches, none of which a verdict depends on.

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| SPY short-tenor straddle into CPI and payrolls, hedged to an expiry within 3 days (cached chains) | fails held-out at the touch; tenor cap chosen after a split | book +0.76% of premium [-16.3, +17.1], paired +5.1% [-13.2, +23.2], N=20 (2025-26); the 2,313 parity-forward rebuild is biased by ex-dividend dates, not cited | `N08-index-macro-cached/` |
| SPY/QQQ/IWM sold 15:59 before an 08:30 release, bought at 10:00 | loses at the touch | -1.86% [-4.52, +0.69], N=204 (2016-24); round trip about 2.7% of premium | same |
| ADRs and foreign reporters, earnings straddle | fails held-out; wider touch than US names | -7.26% of m0 [-10.68, -3.71], N=38 (2026); minus matched US -1.29 points [-5.79, +3.18] | `N15-adr-overnight-reporters/` |
| ForecastEx against Kalshi, and ForecastEx favourites | both fail held-out | gap -$0.039 per contract [-0.154, +0.077], N=58; favourites -$0.007 [-0.061, +0.029], N=91 (2026) | `N11-forecastex-event-contracts/` |
| Short front VIX future on FOMC days (published trade) | decayed after publication | -0.028 SD [-0.339, +0.244], N=78 (2017-26), net of one assumed tick | `N09-vix-complex/` |
| Deribit monthly-expiry Friday straddle; crypto catalysts | fails held-out; discovery pass was a statistic switch | +0.154 of premium [-0.186, +0.469], N=46 (2023-26); catalysts N=14 | `N10-crypto-scheduled/` |
| Natural gas EIA storage day | event variance gone after 2018 (settle) | -0.13 ordinary days [-0.36, +0.16], N=174 weeks (2019-24) | `N03-natgas-storage/` |
| WTI and USO around the EIA petroleum report | no seller surplus (index); USO net loses | USO -8.16% of premium [-9.18, -7.23], N=187 (2021-26) | `N04-crude-eia-opec/`, `N17-commodity-etf-options/` |
| Treasury vol (TLT, VXTLT) around CPI, payrolls, FOMC | fails held-out (index) | pooled +0.60% of 30-day premium [-0.69, +1.79], N=181 (2021-26) | `N05-treasuries-macro/` |
| SOFR option variance around FOMC (Atlanta Fed tracker) | uninformative, underpowered by construction | -3.60% [-11.51, +3.01], N=15 (2025-26), synthetic settle marks | `N06-sofr-fomc/` |
| Gold and silver around macro releases | fails held-out (index) | GLD +0.02 ordinary days [-0.61, +0.61], N=147 (2022-26) | `N12-metals-macro/` |
| ICE softs around WASDE | fails held-out (settle) | cotton variance ratio 1.27 [0.84, 1.90], N=113 (2014-26) | `N13-softs-ice/` |
| Country ETFs around Copom and elections | priced, not paid (index) | Copom +0.6% of weekly premium [-19.8, +23.3], N=23 | `N16-country-etf-politics/` |
| Bank stress-test nights | event too small | +0.51 ordinary sessions [-0.03, +1.16], N=150 bank-nights on 15 nights (2020-26) | `N14-bank-stress-tests-and-regulatory/` |

### The 2026-11-14 earnings-adjacent hunt (exploratory)

Every row is exploratory (43 trials, freeze notes not filed as pre-registrations; the E1 and E2
held-out blocks share events with the `hedged_event_hold 2025-26 *` row). Per trade, net at the
touch, date-clustered 95%, held-out figures. Paths are under
`outputs/research/2026-11-14-earnings-adjacent-hunt/`; `SUMMARY.md` lists the review corrections.

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Long gamma scalp on the reaction session (buy the held straddle at 15:01, hedge every 5 minutes, sell at 15:59) | fails; the option touch is about twelve times the gross | -19.82% of debit [-21.37, -18.24], N=682 (2025-07 to 2026-06); reaction hour no richer than D-1 at the mid | `E1-gamma-scalp/` |
| Hedging the short hold intraday on the reaction session instead of at the close | costs money (discovery only) | -0.31% of m0 [-0.48, -0.14], N=578 | same |
| Pre-event signed ATM option flow as a stock-direction signal, either sign; as a straddle selector | fails held-out; reversal adopted after discovery | against the flow +0.094% of notional [-0.452, +0.631], N=419 (2025-26); selector null percentile 73 | `E2-informed-flow/` |
| Non-reporting peers after a same-industry report: stock continuation, buying peer variance | fails; transfer complete by the reaction close | continuation -9.94 bp [-15.48, -4.54], N=9,779 (2019-24); peer variance ratio 0.86 [0.74, 1.01] against about 3.4 needed | `E3-spillover/` |
| Pinning on the post-earnings expiry; strike choice by an open-interest proxy | no pinning; strike choice null | pin gap +0.91 points [-0.32, +2.15], N=5,649; switch gain -0.071% of m0 [-0.199, +0.059], N=552 (2019-24) | `E4-expiry-mechanics/` |
| Ex-dividend failure-to-exercise windfall for writers | a market-maker trade (dividend play), not reachable at the touch | literature and 104 cached cum-dividend name-days; see the valuation note in section 3 | same |
| Pre-announcement reversal; announcement premium (stock) | both fail; premium about one round trip wide | reversal +0.155% [-0.204, +0.521], N=1,315; premium +0.037% [-0.181, +0.264], N=3,204 (2022-24) | `E5-literature-and-practice/` |
| Report session (after-close against pre-open) as a hedged-hold selector | fails; post-event variance difference absent | +1.54% of premium in residual value [-1.14, +4.20], N=1,955, null percentile 77 (2019-24) | same |

### The 2026-11-14 slate tests (exploratory)

Every row is exploratory: 51 trials, freeze notes not filed as pre-registrations, 2019-24 already
viewed for nearly every outcome family, and `block_is_clean` False for `hedged_event_hold 2025-26`.

- **Basis.** Per trade, % of m0, net at the touch, date-clustered 95%. Figures are on the corrected
  valuation `H_corr` (netted, early call exercise, financing), which omits the stock commission
  unless stated.
- **Location.** Paths are under `outputs/research/2026-11-14-slate-tests/`. `SUMMARY.md` lists
  the review corrections.

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Closing-auction (MOC) stock hedge | cost recovery, assumption-based; declared comparison invalid (fee asymmetry) | like for like at 0.5 bp +0.095 [+0.086, +0.106], N=5,113 (2019-24); break-even impact at least 1.85 to 2.59 bp | `L2-execution/` |
| Minimum-variance (smile-adjusted) delta at the first hedge close | fails | variance ratio 1.0020 [0.9983, 1.0056] (2019-24) | same |
| Per-event expiry choice by touch per unit of event variance | fails | +0.001 [-0.059, +0.056] (2019-24) | same |
| Entry minute by causal spread state, 15:00 to 15:59 | fails discovery | +0.053 [-0.059, +0.161], N=213 (2023) | same |
| Strangle width from the move-size forecast (1,623) | fails, reverses | 2019-24 +0.087 [+0.023, +0.152]; 2025-26 -0.163 [-0.288, -0.032] | same |
| 0.30 delta band with stock commission | recovers the commission only, not an edge | +0.130 [+0.058, +0.203] (2019-24); before commission +0.067 [-0.005, +0.138], lane A's null | same |
| Implied borrow from 15:59 parity as a selector | fails discovery | residual value +0.516 [-0.532, +1.625], null percentile 86, N=2,640 | `L3-selection/` |
| D-1 option-to-stock volume (megacap) | fails held-out; tenor carries about 80% of the lift | held-out `H_corr` -0.295 [-2.444, +1.736], N=562 | same |
| First reports after listing; FINRA short interest | underpowered (N=13); blocked (no free source) | | same |
| ForecastEx S&P contracts against SPY-implied digitals | fails discovery | +0.044 [-0.044, +0.126] per contract, 62 trades | same |
| Same-session concentration cap | lowers risk only by trading less | | same |
| Sequential Bayesian (conjugate, t errors, log loss ratio) density forecast | forecasts better than its baseline; selected book fails economically | log score +0.0139 [+0.0080, +0.0195] nats per event, N=5,113 (2019-24); P(H>0)>0.5 book -0.55 [-1.01, -0.11]; 2025-26 gains are 85 to 88% a tight-spread screen | `L4-bayes/` |

### The 2026-11-15 deep-learning programme (exploratory)

Every row is exploratory: 41 trials, freeze notes not filed as pre-registrations, and 2019-24
already viewed for this outcome family.

- **Basis.** Log scores are the per-event log predictive density of `H_net` (`H_corr` less the
  one-contract hedge commission), in nats per unit of % of m0. Books are per trade, % of m0, net at
  the touch. Intervals are date-clustered 95%, and N=5,113 on 2019-24.
- **Location.** Paths are under `outputs/research/2026-11-15-deep-learning/`. `SUMMARY.md` lists
  the review corrections.

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Network on the full 15:59 chain grid (smile, spreads, sizes at 9 standardised strikes, two expiries) | the surface adds nothing | surface network minus its no-surface twin -0.0042 [-0.0103, +0.0012] (2019-24); channel occlusion at most 0.001 | `D1-surface-net/` |
| Deep density models (surface or tabular) against the L4 Bayesian model | the gain is L4's misspecified scale by tenor, not deep learning | networks +0.051 to +0.059 over L4; L4 rescaled by tenor tercile alone +0.0482 [+0.0386, +0.0574]; best network beyond that +0.011 [+0.005, +0.017] | `D2-tabular/`, `review/` |
| Trade when a density model's predictive mean is positive | fails economically: it is the tight-spread screen | D2 minus the tight-spread-per-date screen +0.03 [-0.52, +0.58] on `H_net`, 80% overlap; D1b +0.11 [-0.38, +0.60], 83% overlap | `D1-surface-net/`, `D2-tabular/` |

## 3. Still open

Two lines are least explored. The first is selection scored on the residual-value component of
P&L rather than realised P&L, which rewards selling larger options: the section 2.1 peer
candidates failed, but the scoring approach itself has had one test. The second is the
liquidity-provider side. Resting both legs failed its markout gate; the exit alone has since been
tested (alpha hunt lane F) and works on broad names, but the hedged hold beats any buy-back, so
the open part is the entry, where the resting-entry confirmation passed and the forward paper
book measures fills on real order lifecycles. Both are on [`ROADMAP.md`](ROADMAP.md).

The 2026-11-13 hunts leave two candidates that only a forward block can settle, because every
historical block is now viewed for them: a structural empirical-Bayes jump model whose richest
tercile passed on held-out 2013-18 (+0.101 of premium [+0.037, +0.173], t 2.91) and failed its
replication on 2025-26 (+0.050 [-0.021, +0.119]), with a megacap replication too small to read;
and the stacked execution book (15:45 or resting entry, tightest strike or spread-aware strangle,
hedged hold with assignment netting), whose levers were measured separately on different blocks.

The niche hunt leaves three markets untested at the touch because no free intraday option quotes
exist: CBOT weekly Treasury options into payrolls, CPI and FOMC (the fixed 1/64 tick is the
structural argument); CBOT grain options into USDA reports; and SOFR options into FOMC. Each needs
a metered CME pull, and none has real-data evidence. Two zero-cost ideas are untested: ForecastEx
daily index contracts against digitals implied by the cached SPY and QQQ chains, and exits in the
Cboe pre-market session (07:30 to 09:25 ET, since 2026-10-19), which needs forward quotes.

The earnings-adjacent hunt found two valuation defects that are open corrections, not closed
directions. First, the 2025-26 ledger (`outputs/research/oos_2026_ledger.csv`) picks its strike
against a dividend-adjusted spot (`earnings_iv_crush/research/chains.py::_spot_table`), so the sold
strike sits below the 15:59 parity forward by a mean ln(F/K) of +188 bp (N=1,220; megacap +17 bp);
the effect on the 2025-26 headline figures is unmeasured. Second, the hedged-hold valuation credits
the writer with dividends that early exercise would take, overstating H by up to about +0.08 to
+0.11% of m0 per trade (an upper bound; the paper book skips ex-date holds). Whether settlement uses
the unadjusted strike on OCC-adjusted special dividends is unchecked.

The slate tests measured those corrections and found a third (`2026-11-14-slate-tests/SUMMARY.md`):

1. **Re-struck 2025-26 ledger.** The re-struck ledger (`L1-corrections/oos_2026_ledger_restrike.csv`)
   centres the strike at a mean ln(F/K) of +2.1 bp. On the frozen scorer (per-trade Sharpe, RoM
   at mids net of 11.6% of premium):

   | Book | Re-struck | N |
   |---|---|---|
   | Unconditional | +0.017 [-0.052, +0.090] | 1,312 |
   | Term gate | -0.325 [-0.462, -0.186] | 239 |

   Its 622 exit-unquoted drops are untested for outcome dependence. The 2025-26 headline should be
   re-quoted from this file once that test is done.
2. **Early call exercise and financing.** Both are now valued in `H_corr`: -0.09 and -0.08 of m0
   in 2013-18. The special-dividend class is under 0.01 of m0.
3. **Stock commission on the hedge, new.** The hedged hold charges none. IB Tiered at one
   contract (recalled) costs -0.22, -0.14 and -0.11 of m0 per trade by block
   (`L2-execution/hedge_commission.parquet`). The equity cost is max(half-spread, 1 bp), a floor,
   not half-spread plus 1 bp as several earlier briefs say.

The commission and the 0.30 delta band are cost corrections to adopt together, before any new
level is quoted.

Anything not listed above is open.

## 4. Figures that must never be quoted

Each is wrong for a stated reason. `tests/test_docs.py` fails if one appears in a current
document, and `tests/test_fills_rescore_attainability.py` guards the execution arm.

| Figure | Why it is wrong |
|---|---|
| Annualised Sharpe +2.04, CI [+4.24, +8.30] | the daily square root of 252 applied to an event book firing about 35 times a year |
| +0.115773 on N=192 | unrepaired marks on a superseded event file |
| +0.023504 | 2013-18 sample missing every name that split |
| Trade-conditional execution arm, 0.7611% per side, +0.096571 | selection-biased: trades cluster where the book is tight, which a fixed-time strategy cannot choose |
| `broad_oos_2025_verdict.csv` (0.85395) | gross, at mid, Black-Scholes-inverted marks |
| `broad_verdict*.csv` | computed before the annualisation fix |
| `dolthub_sp500_persistence.csv` | universe alphabetically truncated (A to CHD) |
| `agent_comparison.csv` levels | exits repriced from inverted volatilities; read the row ordering only |
| Radar `ret_intrinsic_proxy` column, any `intrinsic_fallback` row | exit priced at intrinsic, which omits the premium left in the contract |
| Unconditional 2025-26 +0.043 [-0.026, +0.120], N=1,221, as a headline | outcome-dependent attrition; quote the corrected -0.087 (N=1,492) and say it is an upper bound |
