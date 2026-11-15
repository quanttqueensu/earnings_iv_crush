# Pre-registration: build the hedged short straddle from its cheaper parity legs

Frozen before any leg-choice outcome is computed. Record:
`outputs/research/prereg_2026-11-02-parity-leg-choice.json`. Scorer:
`research/execution/2026-11-02-parity-leg-choice/study.py`.

## Hypothesis

Under the hedged event hold (prereg 3e80d470) the position is held to expiry, delta-hedged and
settled at intrinsic, so only its terminal payoff and the hedge matter. By put-call parity a short
ATM straddle (short call, short put) has the same payoff and the same total delta as two short
calls plus one long share. Selling the second call at its bid and buying the share at its ask
instead of selling the put at its bid changes the entry proceeds by

`adv = (C_bid - P_bid) - (S_ask - K) - S_ask x r x tau + D`,

where `r` is the 13-week Treasury bill yield, `tau` the calendar time to expiry (ACT/365) and `D` the
dividends paid on the share before expiry. `adv` is known at entry up to `D`. The rule takes the
two-call construction when `adv > 0` and the ordinary straddle otherwise, so its gain is `adv+`.
Hypothesis: the mean of `adv+` is positive in every block, and adding it lifts arm H.

Mechanism: the put and call half-spreads differ event by event, and parity deviations that reflect
a scarce borrow or a missed dividend appear as a put priced off the call. Closest prior work: the
parity-forward premium as a stock-return predictor is closed (`selection/findings/parity_spread.md`,
no effect); Cremers and Weinbaum (JFQA 2010) document parity deviations. This study uses the
deviation only to choose the cheaper construction of a fixed trade, never to select events.

## Data

- Events: `ok` events of arm H, 2013-24 (`events.parquet`) and 2025-26
  (`events_confirm_2025_26.parquet`) of the hedged event hold; strike, expiry and m0 as frozen.
- Leg quotes: the entry chain `data/cache/backfill_chains/{ticker}_{entry}.parquet`, last record at
  or before 15:59 ET for the frozen strike and expiry. Events whose `C_bid + P_bid` differs from the
  frozen `s0` by more than 1 cent are dropped and counted.
- Share: CRSP closing ask on the entry date (2013-24); Yahoo close x (1 + 3 bp) for 2025-26, as
  amendment 01 of the hedged hold. The share is assumed bought at the closing ask while the options
  are sold at the 15:59 bids, a one-minute mismatch that is disclosed.
- Rate: Yahoo `^IRX` close on the entry date, divided by 100.
- Dividends: an event with any cash dividend from the session after entry through expiry is
  excluded from the primary (the paper book already skips ex-dividend windows; a dividend also
  opens early exercise of the short calls). CRSP: total return differs from price return by more
  than 1e-6 on a session. Yahoo: a `Dividends` action in the window. Counted.
- Blocks: discovery 2013-18, validation 2019-24, confirmation 2025-26 (by reaction date).

## Statistics (date-clustered by reaction date, 5,000 draws, seed 0)

- P1: mean `adv+ / m0` per trade per block, with its interval. Share of events where the two-call
  construction is chosen.
- P2: per-trade Sharpe of `HP = H + adv+ / m0` per block, with its interval.

## Criterion

- PARITY LEVER if P1 intervals exclude zero above in discovery and validation, and the 2025-26 point
  is > 0.
- BOOK PASS if, in addition, P2's validation interval excludes zero above and its discovery and
  confirmation points are > 0.
- Attrition: mean H of excluded (dividend or quote mismatch) against kept events per block; a gap
  above 0.5% of m0 flags the block.

## Secondary

`adv+` by implied-move tercile and by year; the put-minus-call half-spread; capital: the two-call
construction holds one more share than the straddle at entry, which is reported as extra notional
per m0.

## Trial accounting

One trial: 1,559 + 1 = 1,560.
