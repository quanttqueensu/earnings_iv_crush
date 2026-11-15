# Pre-registration: post-announcement drift after reactions larger than the implied move

Frozen before any post-reaction outcome is computed. Record:
`outputs/research/prereg_2026-11-02-implied-surprise-drift.json`. Scorer:
`research/timing/2026-11-02-implied-surprise-drift/study.py`.

## Hypothesis

Stocks drift after earnings in the direction of the announcement-day return (Brandt, Kishore,
Santa-Clara and Venkatachalam, 2008, earnings announcement return drift; Bernard and Thomas 1989 for
SUE). The option-implied move, priced the session before, is the market's own estimate of the
reaction's size. A reaction beyond it is a surprise in units the market set, independent of analyst
forecasts. Hypothesis: after reactions with `|R| > implied move`, a position in the direction of the
reaction, held from the reaction close for 20 sessions and hedged one-for-one with SPY, earns a
positive mean net of costs.

Closest closed rows: PEAD on SUE (directionally positive, not established), post-event 25-delta skew
and term slope as 20-session predictors (fail). This signal is the price reaction scaled by the
implied move; no row scales the reaction by the options. Stream 13 used only the reaction session;
no stream has observed post-reaction prices.

## Data

- Events: every event of `outputs/research/ml_zoo/events_full.parquet` (broad and megacap) with a
  finite positive `implied_move`.
- Prices: Yahoo Adj Close (total return); SPY Adj Close. Missing name or any needed session drops
  the event, counted (acquired names are lost; reported).
- `R = C1 / C0 - 1`, entry close to reaction close. Holding period: reaction close to the close 20
  sessions later (the stock's own trading calendar).

## Trade

Selected: `|R| > implied_move`. Net per trade: `sign(R) x [(P20 / P1 - 1) - (SPY20 / SPY1 - 1)] -
12 bp` (10 bp stock round trip, 2 bp SPY round trip).

## Statistics

Date-clustered by reaction date (5,000 draws, seed 0), per protocol. Holding windows overlap across
dates, so a second interval clustering by reaction calendar month is reported beside it and the
criterion uses the wider of the two.

## Criterion

PASS if the mean net is > 0 with the (wider) interval excluding zero in 2013-18 and in 2019-24, and
the 2025-26 point is > 0. Otherwise FAIL. Blocks by reaction year.

## Secondary

Unselected events (`|R| <= implied_move`) as a contrast; broad against megacap; up against down
reactions; 5- and 60-session horizons (descriptive); per-trade Sharpe.

## Trial accounting

One trial: 1,563 + 1 = 1,564.
