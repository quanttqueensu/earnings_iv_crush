# Pre-registration: hedge-hold the daily index straddle instead of buying it back

Frozen before any hedged-hold outcome on index options is computed. Record:
`outputs/research/prereg_2026-11-02-index-hedged-hold.json`. Scorer:
`research/off_earnings/2026-11-02-index-hedged-hold/study.py`.

## Hypothesis

The frozen index study's B1 (sell the ATM straddle on the shortest expiry strictly after the next
session, at the 15:59 bids; buy it back at the next session's 15:59 asks) earns +1.4% to +1.9% of
premium per session at the mid in every block and loses it at the touch. The single-name hedged
event hold showed that replacing the buy-back with a stock hedge held to expiry recovers the exit
half-spread (exit lever confirmed in three blocks). Index options also lose value as they age, mostly
overnight (Muravyev and Ni, JFE 2020, delta-hedged S&P 500 options), so holding the same straddle
hedged to expiry collects the remaining sessions' premium without a second option crossing.
Hypothesis: on SPY the hedged hold beats the buy-back, and its own net return is positive.

## Data

- Trades: every B1 trade (exit snapshot 15:59) scored `ok` in
  `outputs/research/2026-11-01-index-event-crush/priced_trades.parquet` (frozen study, full panel),
  same contract and sale.
- ETF prices: Yahoo Finance daily bars (free), `auto_adjust=False`; level = Close (no split in SPY,
  QQQ or IWM in the window is required; a split inside a hold drops the trade, counted); total
  return = ratio of Adj Close.
- Blocks as frozen: P 2016-18, M 2019-24 (discovery), C 2025-01 to 2026-10.

## Specification

Arm IH, per share, with `hedged_hold.hedged_short_straddle`: sale at `c0b + p0b`, mid credit `p0`,
strike as traded; hedging closes are the ETF closes from the entry session through the last session
before expiry; hedge volatility fixed at the entry straddle implied volatility (`straddle_iv(p0,
fwd0, K, t)`, ACT/365); equity half-spread floored at 1 bp; settle at intrinsic on the ETF close of
the expiry session (the last session on or before expiry), 5 bp disposal when in the money;
commission USD 0.65 per contract on the two entry legs only. Return unit: the entry mid premium `p0`,
as in the frozen study; a secondary unit is margin `p0 + 0.15 x fwd0`.

## Statistics (circular block bootstrap, 10 sessions, 5,000 draws, seed 0, as frozen)

- P1: mean `IH - B1` per trade (unit p0, B1 = frozen `short_touch_net`), SPY, block M.
- P2: mean IH per trade, SPY, block M; per-trade Sharpe reported.

## Criterion

PASS if P1 and P2 are both > 0 with intervals excluding zero in M, and the pooled P+C mean IH is
> 0 with its interval excluding zero. "Exit lever only" if P1 passes and P2 fails. QQQ and IWM are
secondary and cannot rescue SPY.

## Secondary

Skew, worst five trades, share of P&L from the worst 1%, DSR against 1,556 trials, per-trade Sharpe
on margin, by days to expiry.

## Trial accounting

One trial: 1,555 + 1 = 1,556.
