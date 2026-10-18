# Walk-forward model zoo: the broad-universe edge was a data-source artefact

## Hypothesis, scope and success criteria

An exploratory search, run without a pre-registration at the owner's request: can any machine-learned
model, trained only on earlier years, rank earnings events so that the short straddles it selects
earn more than those it rejects? Grid: 125 configurations across eleven families (ridge, lasso,
elastic net, Huber, PLS, k-nearest neighbours, SVR, random forest, extra trees, gradient boosting,
neural network, plus logistic and boosted classifiers), three targets (realised/implied, net return
on margin, probability of a loss) and three selection thresholds, so 375 strategies. Each model is
refit every year from 2016 to 2026 on all earlier years and predicts the next year. Data: 3,484
events (1,794 megacap 2013-2024, 1,491 attrition-corrected broad 2025-2026, 199 broad July-August
2026), thirty features known at entry. Outcome: net return on margin per trade. Success, informally:
a selected-minus-rejected gap that holds across blocks and years, and that survives on features a
trader could compute at the 15:59 entry.

## First run: features as stored

| Measure | Value |
|---|---|
| Strategies with selected beating rejected | 96% of 375 |
| Median gap, selected minus rejected | +3.2 points of margin per trade |
| Equal-weight ensemble of all models, gap | +4.0 points [+3.0, +5.1] |
| Ensemble, megacap 2016-2024 | +0.34 [-0.83, +1.54] (no skill) |
| Ensemble, broad 2025-2026 | +6.9 [+5.2, +8.5] |
| Ensemble, broad July-August 2026 | +8.8 [+6.6, +11.1] |

The edge sat entirely in the broad blocks. It survived controls for premium size (within every
implied-move quintile), tenor, attrition and the year split, so it was not the "sell the bigger
option" artefact. It was carried mostly by the 25-delta skew (rank correlation with net RoM -0.41 in
2025, -0.25 in 2026, -0.01 on megacaps).

## The diagnosis

The broad features were built from Alpaca daily bars, whose "close" for each contract is its last
trade of the day: possibly after 15:59, or days stale for illiquid strikes. The megacap features were
built from 15:59 consolidated quotes. On the same broad events:

| Check | Value |
|---|---|
| Alpaca 25-delta skew vs 15:59-quote skew, rank correlation | 0.09 |
| Net RoM vs Alpaca skew | -0.35 |
| Net RoM vs 15:59-quote skew | -0.02 |
| Alpaca implied move vs 15:59 implied move | 0.84 (the at-the-money level agrees; the wings do not) |

No code leak was found: the price windows end at entry and no next-day bar is read. But last-trade
prices of mixed age are not what a trader sees at 15:59.

## Second run: broad features rebuilt from the 15:59 quotes

Every broad feature was recomputed from the cached 15:59 Databento chains (implied volatility inverted
from each quote's mid against the expiry's parity forward) with the same feature code, and the full
zoo was re-run. (A first attempt silently reused the old features because worker processes did not
inherit the changed path; it was caught by its byte-identical output and discarded.)

| Measure | Alpaca features | 15:59 features |
|---|---|---|
| Strategies with selected beating rejected | 96% | 63% |
| Median gap, selected minus rejected | +3.2 | **+0.15** |
| Median Spearman, prediction vs realised/implied | +0.23 | +0.05 |
| Ensemble gap, all events | +4.0 [+3.0, +5.1] | **+0.31 [-0.55, +1.17]** |
| Ensemble gap, broad 2025-2026 | +6.9 | +0.63 [-0.8, +2.0] |
| Ensemble gap, broad July-August 2026 | +8.8 | **-2.75 [-5.0, -0.1]** |

## Verdict

**No model shows a tradable edge.** On features a trader could compute at the 15:59 entry, the zoo's
selections are indistinguishable from chance across 375 strategies, consistent with every earlier
selector in the programme. The apparent edge came from features built on end-of-day last-trade
prices.

## Third run: the full 15:59 history, 2013-2026

A capped Databento pull (OPRA cbbo-1m, the 15:59 minute; USD 20.87 spent against a USD 30 cap
inside a USD 45 budget; every request priced with `get_cost` before it was sent) added the entry
and exit chains for the broad universe's 2013-2024 earnings events (`scripts/pull_broad_history.py`,
calendar from Compustat `rdq` with IBES session times, untimed and intraday sessions excluded).
`scripts/build_broad_history_events.py` built features and outcomes from those chains on the same
basis as everything else (15:59 quotes, zero-bid exit legs kept at ask / 2, 11.6%-of-premium cost):
7,773 events, losing only 15 to an absent exit leg. The full table has 11,257 events.

**Unconditional book first (no model).** Net and gross return on margin per trade, date-clustered
95% intervals:

| Block | N | Net | Gross (cost added back) | Net per-trade Sharpe |
|---|---|---|---|---|
| Broad 2013-2024 | 7,765 | -2.13% [-2.42%, -1.86%] | +0.57% [+0.29%, +0.83%] | -0.19 |
| Megacap 2013-2024 | 1,794 | -0.59% [-1.11%, -0.06%] | +1.65% [+1.12%, +2.18%] | -0.05 |
| Broad 2025-2026 | 1,461 | -1.12% [-1.87%, -0.36%] | +1.81% [+1.08%, +2.58%] | -0.08 |
| Broad July-August 2026 | 197 | +0.06% [-0.81%, +1.11%] | +3.20% | +0.01 |

The broad-name short straddle loses net in every one of the twelve years 2013-2024; its gross premium
is about a quarter of the cost of trading it.

**Zoo on the full history (375 strategies, walk-forward 2016-2026, 9,529 out-of-sample events):**

| Measure | Value |
|---|---|
| Strategies with selected beating rejected | 49.6% of 353 non-degenerate |
| Median gap, selected minus rejected | -0.09 points |
| Median Spearman, prediction vs realised/implied | +0.13 |
| Equal-weight ensemble gap | +0.03 [-0.46, +0.53] |
| Ensemble gap by block | broad 2013-24 0.00; megacap +0.38; broad 2025-26 +0.10; July-August 2026 -1.00 (all intervals span zero) |
| Ensemble selected book, net per-trade Sharpe | -0.16 |

The models rank realised/implied modestly and stably (Spearman about +0.13 every year), but the
ranking does not reach P&L: selected and rejected events lose almost the same. That pattern is the
mechanical denominator effect (the implied move sits in the target's denominator) rather than
mispricing. The best single strategy (Huber regression on net RoM, top 70%) has a gap of +1.7 points
that is positive in 10 of 11 years, but its selected book still loses -1.17% per trade and it is the
maximum of 353 tries.

**Nested walk-forward (`scripts/research_ml_nested.py`).** The choice among all 375 candidates is
made out of sample: for each test year the candidate with the best mean selected-minus-rejected gap
over the previous three years is refit on all earlier years and applied blind.

| Measure | Value |
|---|---|
| Pooled gap, 9,529 out-of-sample events | +0.64 points [+0.01, +1.26] |
| Years with a positive gap | 5 of 10 (2016 +3.9, 2020 +1.9, 2021 +1.5, 2022 +2.6, 2023 +0.3; 2017 -0.5, 2018 -3.8, 2019 -4.0, 2024 -3.9, 2025 -5.3) |
| Inner gap of the chosen candidate | +1.5 to +4.9 points each year, shrinking to +0.6 out of sample |
| Selected book | -1.18% of margin per trade, per-trade Sharpe -0.09 |
| Chosen families | k-nearest neighbours and Huber regression on net RoM |

A pooled interval that barely clears zero, a coin-flip year record and the shrinkage from inner to
outer gap mark it as noise-fitting, not a durable edge; and the selected book still loses money.

## Consequences

1. Any feature built from Alpaca chains (`build_broad_oos_2025.py`, `events_broad_oos_2025.parquet`)
   should not be used to select trades. It is acceptable only where the at-the-money level matters
   (the implied move agrees at 0.84).
2. The frozen ML ratio model's 2025-2026 broad pass (`ml_ratio`) used the same Alpaca features and
   should be read in this light; its July-August confirmation had already failed.
3. The 15:59 broad features (`broad_features_1559.parquet`) are the basis to use from now on, and
   the 2013-2024 broad pull now running is built on the same 15:59 quotes.

## Reproduction

```
python scripts/research_ml_zoo.py --build
python scripts/research_ml_zoo.py --run
python scripts/research_ml_zoo_1559.py --features
python scripts/research_ml_zoo_1559.py --run
```
