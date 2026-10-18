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
- `python -m earnings_iv_crush.ops.orient` reports the largest count found in the hash records.
- **Open item:** rebuild the count as one tracked ledger file (`docs/ROADMAP.md`). Until then,
  quote "about 1,500" and use 1,532 as the conservative deflation input.

Under no edge, the expected best per-trade Sharpe from a search this size is about +0.43.

## 2. Closed directions

Each row is closed: do not spend effort on it again without a new mechanism and a new
pre-registration. Verdicts are per trade, date-clustered 95% intervals, on the stated block.
Evidence paths are under `research/` unless marked.

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

### Execution and cost

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| Better fills on the fixed 15:59 book | worth about +0.007 Sharpe | measured cost 1.7871% per side | `execution/findings/` and `outputs/research/fills_rescore.csv` |
| Causal spread gate, megacap | no net premium left | gated -0.0347 [-0.1443, +0.0827] (2013-18, N=316), -0.0070 [-0.1031, +0.1073] (2019-24, N=372) | `execution/findings/cost_levers.md` |
| Spread gate, broad 2025-26 | fails at the touch | gated Sharpe -0.224; gated events carried no gross premium | `selection/findings/final_earnings_set.md` |
| Entry-spread filter on DoltHub | invalid, not failed | adapter lookback made 54.1% of pairs use the entry chain as the exit chain | `execution/findings/dolthub_defect.md` |
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

### Away from earnings, and other markets

| Direction | Verdict | Key figure | Evidence |
|---|---|---|---|
| P2 de-eventised term slope (DoltHub) | kill rule fires | touch -7.79% [-18.06%, +2.23%] of premium, N=2,972 name-months | `off_earnings/findings/p2_term_slope.md` |
| SPY macro-release straddles | not testable on DoltHub | N=5 | `off_earnings/findings/spy_macro.md` |
| Index VRP timing | does not survive post-2008 | t +0.24 to -1.42 | `off_earnings/findings/pivot_verdicts.md` |
| PEAD on SUE | directionally positive, not established | DSR 0.0597 against 16 trials | same |
| Deribit BTC macro events | ordinary variance premium, no event surplus | paired +0.079% [-0.275%, +0.440%], N=116 | `other_markets/findings/deribit_macro.md` |
| Kalshi tail selling | loses at the touch | -2.03% per bet [-4.07%, +0.21%], N=383 | `other_markets/findings/kalshi_tails.md` |
| Kalshi maker | does not replicate | -1.37% on 81 unseen series, 39 fills | `other_markets/findings/kalshi_replication.md` |
| India (NSE), Brazil (B3) | no gross signal / inside the spread | India negative gross at every cut; Brazil +6.4% gross inside a 24% spread | `docs/reference/RESEARCH_RECORD.md` 6.6 |

## 3. Still open

Two lines are least explored. The first is selection scored on the residual-value component of
P&L rather than realised P&L, which rewards selling larger options: the section 2.1 peer
candidates failed, but the scoring approach itself has had one test. The second is the
liquidity-provider side. Resting both legs failed its markout gate, but the split by arm left
the exit alone (broad exit-only +0.68% of margin, where spreads are 2.4 times wider) untested as
its own hypothesis, and the forward paper book now measures fills on real order lifecycles.
Both are on [`ROADMAP.md`](ROADMAP.md). Anything not listed above is open.

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
