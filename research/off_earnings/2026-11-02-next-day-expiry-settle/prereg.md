# Pre-registration: sell the next-day-expiry index straddle at the close and let it settle

Frozen before any outcome of this trade is computed. Record:
`outputs/research/prereg_2026-11-02-next-day-expiry-settle.json`. Scorer:
`research/off_earnings/2026-11-02-next-day-expiry-settle/study.py`.

## Hypothesis

Index option premium is earned overnight (Muravyev and Ni, JFE 2020). The frozen index study's B1
(sell the shortest expiry strictly after the next session at the 15:59 bids, buy back at the next
15:59 asks) is positive at the mid (+1.4% to +1.9% of premium per session) and loses it at the touch;
stream 8 showed that holding those longer contracts hedged to expiry adds more convexity loss than
the saved exit spread. The contract that needs neither an exit crossing nor extra days is the one
expiring on the next session: sold at 15:59 on t, it carries the night and the next session and
settles at intrinsic on the t+1 close. Short-dated index options are found to be overpriced for
buyers (Bandi, Fusari and Renò 2023; Beckmeyer, Branger and Gayda 2023; Vilkov 2024 on 0DTE).
Hypothesis: on SPY, the next-day-expiry ATM straddle sold at the 15:59 bids and settled at intrinsic
earns a positive mean net.

Closest closed work: B1 and B3 (one-session and overnight buy-back, fail at the touch), stream 8
(hedged hold of the B1 contract, fail), index VRP timing (post-2008, fail). None sells the contract
that expires on the next session and settles without an exit trade.

## Data

- Quotes: `data/cache/index_chains/{T}_{t}_1559.parquet` (Databento OPRA cbbo-1m, the approved
  pull), parsed by the frozen `load_chain`.
- Sessions: the dates with a 15:59 snapshot for the ticker, in order; t+1 is the next one.
- Contract: expiry exactly equal to t+1; skip the day if none (counted). ATM strike as in the frozen
  `build_trade`: two-sided pairs only, strike minimising `|C_mid - P_mid|`; forward
  `K + C_mid - P_mid`.
- Settlement: Yahoo Close of the ETF on t+1 (`auto_adjust=False`); a split in the window drops the
  day (none expected).

## Trade

Net per share: `c0b + p0b - |S1 - K| - 2 x 0.0065 - 5 bp x S1 x 1[S1 != K]`. Unit: entry mid premium
`p0` (as in the frozen index study); secondary on margin `p0 + 0.15 x fwd0`.

## Statistics and criterion

Circular block bootstrap, 10 sessions, 5,000 draws, seed 0 (frozen `block_ci`), series in time
order. Blocks P 2016-18, M 2019-24, C 2025-01 to 2026-10.

PASS if, on SPY, the M mean is > 0 with its interval excluding zero, and the P and C means are each
> 0. Otherwise FAIL. QQQ and IWM are secondary and cannot rescue SPY. Per-trade Sharpe reported.

## Secondary

Mean at the mid (`p0 - |S1 - K|`); weekday and calendar-gap splits (Friday entries carry a weekend);
skew and worst 1%; paired against B1 on the same entry dates; DSR against 1,565 trials.

## Trial accounting

One trial: 1,564 + 1 = 1,565.
