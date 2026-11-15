# 2025-2026 straddle ledger: outcome-dependent attrition overstates the unconditional book

## What was checked

The canonical 2025-2026 ledger (`outputs/research/oos_2026_ledger.csv`, built by
`scripts/score_oos_2026.py`) scores 1,221 of 2,037 calendar events. Its chain parser
(`backfill_forward_window._parse_chain`) keeps a contract only when both bid and ask are positive.
After a large announcement move, the far out-of-the-money leg of the sold straddle often shows a
zero bid with a live ask, so the event is dropped as "exit leg unquoted at the sold strike". A short
straddle loses most on exactly those events, so the attrition depends on the outcome.

Evidence of the dependence, from the event file's realised and implied moves:

| Group | Events | Mean realised / implied | Share with realised > implied |
|---|---|---|---|
| In the ledger | 1,221 | 0.649 | 22.3% |
| Dropped by the ledger | 816 | 0.852 | 33.2% |

## Re-marking with zero bids allowed

`scripts/audit_oos_2026_attrition.py` re-marks every event with the ledger's own rules (strike and
expiry from the entry chain, mid marks, 11.6%-of-premium round-trip cost, Reg-T margin, per-trade
Sharpe with a date-clustered bootstrap, 5,000 draws, seed 0), changing one thing: an exit leg with a
zero bid and a positive ask is kept at mid = ask / 2. It writes only to this directory. Spot prices
were re-pulled from yfinance, which has since lost a few delisted names, so the strict rebuild has
1,187 events rather than 1,221; it reproduces the published figure.

| Sample | N | Mean net RoM per trade | Per-trade Sharpe [95% CI] | Mean realised / implied |
|---|---|---|---|---|
| Strict ledger rule (reproduction) | 1,187 | +0.50% | +0.043 [-0.027, +0.119] | 0.60 |
| Recovered: exit leg had a zero bid | 305 | -7.64% | -0.432 [-0.576, -0.305] | 0.97 |
| **All marked** | **1,492** | **-1.17%** | **-0.087 [-0.142, -0.031]** | 0.67 |

Events still unmarkable after the change (545, including entry-side failures) have mean realised
over implied of 0.77 against 0.60 for the strict set, so they too lean toward large moves. The
corrected figure is therefore itself an upper bound: the unconditional short straddle on the
2025-2026 block loses money net of the canonical cost, with an interval that excludes zero.

Descriptive, the same correction on the frozen gate arms (per-trade Sharpe, date-clustered 95% CI):

| Arm | Strict rebuild | Corrected |
|---|---|---|
| Term gate q=0.80 | -0.193 [-0.329, -0.046], N=226 | -0.393 [-0.509, -0.276], N=305 |
| Matched random | +0.103 [-0.032, +0.272], N=220 | -0.030 [-0.133, +0.090], N=279 |

The term gate's selected events are disproportionately the zero-bid cases (79 of 305), consistent
with it selecting names whose announcement moves outrun the implied move.

## Consequences

1. The headline "unconditional +0.043 [-0.026, +0.120], N=1,221" in the project instructions and
   the state of record is biased upward by outcome-dependent attrition and should be replaced by the
   corrected figure, labelled as an upper bound.
2. Every figure computed from the same ledger inherits the bias: the term-selector headline
   (-0.2095), the "+3.44% of margin gross premium" on the broad block, and the per-name and
   gate studies on it. Their direction of error is the same (too favourable to the short book) but
   the size differs by subset and has not been measured here.
3. The 2013-2024 megacap panel was marked by a different pipeline (quote-marked `cbbo-1m` with
   stale-quote repair) and does not show the same tilt: on 2019-2024, the 212 calendar events
   missing from `reverse_alpha/panel.parquet` have mean realised over implied of 0.70 (24.5% above
   one) against 0.79 (31.1%) for the 839 kept, so its attrition, if anything, removes small moves.
4. The programme's summary sentence ("the premium is visible at the mid and paid away at the touch")
   needs qualifying for this block: on the corrected sample there is no premium to pay away.

## Fix

`_parse_chain` should keep a contract with a positive ask and a zero bid (marking it at ask / 2 or,
for a buy-back, at the ask), and every scorer should print the realised-over-implied ratio of
dropped versus kept events as a standing attrition check. That is a change to shared code and is
left for review; nothing canonical was overwritten.

## Reproduction

```
python scripts/audit_oos_2026_attrition.py
```
