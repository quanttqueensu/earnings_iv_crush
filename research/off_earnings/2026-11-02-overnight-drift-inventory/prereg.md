# Pre-registration: overnight index drift after intraday selling (dealer inventory)

Frozen before any overnight return is computed in this project. Record:
`outputs/research/prereg_2026-11-02-overnight-drift-inventory.json`. Scorer:
`research/off_earnings/2026-11-02-overnight-drift-inventory/study.py`.

## Hypothesis

US equity index returns accrue mostly overnight (Cliff, Cooper and Gulen 2008; Lou, Polk and
Skouras 2019, JFE). Boyarchenko, Larsen and Whelan (2023, RFS, "The overnight drift") attribute
the drift to intermediaries absorbing intraday selling and being paid to carry the inventory
overnight; the drift is largest after the index falls during the session. Hypothesis: on SPY, a
long position bought at the close auction on sessions whose intraday return falls in the bottom
causal tercile, and sold at the next open, earns a positive mean net, and the tercile rule beats
random selection of the same number of sessions.

Closest closed rows: index VRP timing (options, fails post-2008) and PEAD (single names). No row
uses the underlying's overnight return. Directional, no options traded.

## Data

- Sessions: every date with a `data/cache/index_chains/{T}_{t}_1559.parquet` snapshot (the
  approved Databento pull), 2016-01-04 to 2026-10-30, and a Yahoo row on t and on the next
  Yahoo session t+1.
- Signal, causal at 15:59: `r_id = F / O_t - 1`, where `O_t` is the Yahoo Open on t (known at
  09:30) and `F` the 15:59 parity forward from the nearest expiry in the snapshot: two-sided
  pairs only, strike minimising `|C_mid - P_mid|`, `F = K + C_mid - P_mid`. A missing snapshot or
  no two-sided pair drops the session, counted.
- Tercile breakpoints: `causal_bins(..., n_bins=3, min_prior=250)` on strictly earlier sessions
  per ticker. Seed history before the first scored session: Yahoo `Close / Open - 1` from
  2010-01-04 to 2015-12-31 (uses the official close, prior to every scored session, so no
  outcome leaks).
- Outcome: Yahoo unadjusted prices (`auto_adjust=False`). `ON = (O_{t+1} + D_{t+1}) / C_t - 1`,
  with `D_{t+1}` the cash dividend whose ex-date is t+1 (the holder at the close receives it). A
  split on t+1 drops the session.

## Trade

Selected sessions (bottom tercile, bin 0): buy at the close auction on t, sell at the opening
auction on t+1. Net per trade `ON - 1 bp` (round trip, auction fills carry no spread; the
charge covers impact and fees). Unit: fraction of notional, per trade.

## Statistics and criterion

Circular block bootstrap, 10 sessions, 5,000 draws, seed 0 (the frozen index-study `block_ci`),
series in time order. Blocks P 2016-18, M 2019-24, C 2025-01 to 2026-10.

PASS if, on SPY, all three hold:
1. the selected book's M mean net is > 0 with its interval excluding zero;
2. the selected book's P and C means are each > 0;
3. pooled over all SPY scored sessions, the selected mean net beats `matched_random_null` (mean
   statistic, 5,000 draws, seed 0) at percentile >= 95.

Otherwise FAIL. QQQ and IWM are secondary and cannot rescue SPY.

## Secondary (descriptive)

Unconditional overnight book; middle and top terciles; costs 0 and 2 bp; agreement of the 15:59
forward signal with Yahoo `Close / Open - 1`; per-trade Sharpe and the annual figure of the
daily P&L series (flat on unselected days, factor from 252 sessions per year, stated); weekday
split; worst 1%.

## Trial accounting

One trial: 1,565 + 1 = 1,566.
