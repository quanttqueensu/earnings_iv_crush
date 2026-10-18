# Forecasting the crush: real skill, no monetisation

Tested whether the IV crush can be forecast from at-entry features and traded, rather than
proxied by a selection gate. Regenerated after a measurement hazard was found and gated; the
numbers below supersede the pre-gate version of this note.

## The question

All 1,476 recorded trials on this book asked the same thing: which events should I short?
Term spread, move gate, skew, curvature, smile concavity, vol-of-vol, micro grids, parameter
grids. Every one is a threshold rule on event selection. Since vega is the largest positive
leg and the crush *is* the vega leg, a different axis exists: forecast the magnitude of the
crush and sort on the forecast. A forecast is a different object from a threshold.

## 1. The mechanism is confirmed, and strongly

On correctly marked data the crush is the P&L. Short-straddle return on premium against
realised crush, 1,019 trades, 49 names, 2013-2018:

**corr(crush, net return) = +0.7342**

The crush explains roughly 54% of the variance in the straddle's return. Vega is not just
directionally right, it is the dominant term. Mean crush +0.3046 with IV falling on 89.8% of
events, consistent with the project's headline.

## 2. The measurement hazard, and the gate that now blocks it

The first run produced an apparently excellent result: 4,556 trades, monotone terciles, top
tercile +9.47% net with a date-clustered CI of [+0.066, +0.120] excluding zero across 484
distinct dates. It was entirely an artefact.

The event tables re-pick the ATM strike at exit, so `iv_exit` describes a contract the book
does not hold. A crush variable computed naively as `(iv_entry - iv_exit) / iv_entry`
therefore stops measuring the vol collapse and starts measuring the move. Auditing every
event table:

| Table | n | Frac IV fell | corr(crush, \|move\|) |
|---|---|---|---|
| `events_megacap_databento` | 1,051 | 0.337 | **-0.6466** |
| `events_megacap_databento_oos` | 877 | 0.343 | -0.6249 |
| `events_megacap_full` | 454 | 0.253 | -0.0721 |
| `events_broad_full` | 2,381 | 0.881 | +0.4145 |
| `events_broad_oos_2025` | 2,017 | 0.865 | +0.4262 |
| `events_broad_v2` | 363 | 0.901 | +0.4331 |
| `events_megacap_v2` | 456 | 0.893 | +0.3804 |
| **`events_megacap_quotes_2013_2018`** | **1,117** | **0.900** | **+0.0349** |

Two distinct signatures. The Databento megacap tables show IV *rising* on two thirds of
events, against the project's established 98.1% fall, correlated -0.65 with the absolute
move. Since the straddle return is itself a function of the move, a crush variable correlated
-0.65 with the move makes any sort on predicted crush a sort on predicted move, and the
tercile ordering follows mechanically. The broad tables keep the right sign and carry +0.42,
which may be economically real. The clean 2013-2018 quote-marked table, at +0.035, is the
only one where the crush is a genuinely separate quantity.

The script now **raises** rather than pooling silently on any table where IV falls on fewer
than 80% of events. Three tables are excluded by name with their measured failure rates
recorded in the source.

**The tables are not broken for their intended purpose.** The exit ATM IV is a real quantity.
But any calculation treating `iv_entry - iv_exit` as the vega the book captures is measuring
something else.

## 3. Result after the gate

Expanding-window OLS of realised crush on `implied_move`, `bkm_kurt`, `vol_premium`,
`iv_term_spread` and `trailing_rv`, strictly prior events only, benchmarked against the
prevailing mean. Fitted on the discovery tables, then frozen and applied without refitting to
the untouched 2013-2018 block. Cost charged exactly once at 11.6% of premium. Intervals
resample whole announcement dates.

### Discovery sample, 4,265 events across four tables

| Tercile | n | Dates | Net | Hit | Sharpe | Date-clustered CI | Mean crush |
|---|---|---|---|---|---|---|---|
| 0 | 1,425 | 239 | +0.0247 | 0.624 | +0.088 | [+0.003, +0.046] | +0.170 |
| 1 | 1,418 | 292 | +0.1583 | 0.796 | +0.604 | [+0.139, +0.177] | +0.336 |
| 2 | 1,422 | 286 | +0.2100 | 0.897 | +1.063 | [+0.195, +0.225] | +0.531 |

**Discard these numbers.** The four tables show unconditional books at +10% to +17% net per
trade at 72-84% hit rates. That is not credible against the settled +0.055992 pooled verdict,
so the tables are optimistically marked and the +0.2100 is not a result.

### Frozen coefficients on the untouched 2013-2018 block

| Tercile | n | Dates | Net | Hit | Sharpe | Date-clustered CI | Mean crush |
|---|---|---|---|---|---|---|---|
| 0 | 348 | 255 | -0.2770 | 0.379 | -0.338 | [-0.369, -0.198] | +0.115 |
| 1 | 330 | 247 | -0.1603 | 0.542 | -0.227 | [-0.237, -0.090] | +0.340 |
| 2 | 341 | 274 | **-0.0908** | 0.578 | -0.145 | [-0.161, -0.023] | +0.464 |

**The forecast carries real transferable skill.** Predicted-versus-realised crush correlation
on the untouched block is **+0.1663**, up from -0.012 before the gate, and mean realised
crush rises monotonically across terciles from +0.115 to +0.464. Coefficients fitted on one
six-year window and one universe order the crush correctly on a disjoint six-year window.
That is not noise.

**Nothing clears costs.** Every holdout tercile is negative net. The best is -0.0908 with an
interval of [-0.161, -0.023] that excludes zero on the wrong side.

## 4. Orthogonality

Dropping `iv_term_spread` from the feature set leaves the discovery terciles essentially
unchanged (+0.0165 / +0.1592 / +0.2173), so the forecast is not the term gate wearing a new
hat. Residualising the forecast on `iv_term_spread` **breaks** the monotonicity (+0.1428 /
+0.0835 / +0.1662), which says the term component and the remainder are not cleanly separable
and the joint object is doing the work.

## Verdict

Sound in mechanism, dead in practice on current evidence. The crush drives the P&L
(r = +0.7342) and it is genuinely forecastable out of sample (+0.1663 predicted-realised
correlation on frozen coefficients, monotone terciles). Neither fact is worth anything,
because forecasting the crush better does not make the trade profitable: the crush is not the
constraint. The gap risk and the 11.6% round trip are.

## Reproduce

    python scripts/research_crush_forecast.py --phase all

Marking basis is Black-Scholes from each table's own implied volatilities, so absolute levels
are model marks and inflated; the ordering is the read. Cost is charged exactly once and is
never double-counted through `CostModel` as well.
