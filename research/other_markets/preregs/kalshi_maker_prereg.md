# Pre-registration: Kalshi favourites bought as a maker, not a taker

Frozen before any Kalshi trade for this test is pulled. SHA-256 recorded in
`outputs/research/prereg_kalshi_maker.json`. Companion to `kalshi_macro_tails_prereg.md`.

## Why

Buying release-ladder favourites at the ask lost 2.03% per bet (CI [-4.07%, +0.21%], N=383) although
the tails looked slightly rich at the mid (15.1% tail outcomes against 20%). Makers on Kalshi earn
more than takers (Burgi, Deng and Whelan 2025) and pay a quarter of the fee. This test holds the
candidate set fixed and changes only the side of the spread.

## Mechanism and its counter

Resting at the bid buys the favourite a tick or more cheaper and at a quarter of the fee, which is
larger than the measured mid-price edge. The counter is adverse selection: a resting bid on a
favourite is hit when an informed taker sells it, i.e. when the favourite is more likely to lose.
Whether fills concentrate in losers is the mechanism check.

## Candidates

Exactly the 383 bets of the taker test: same series, snapshot (last hourly candle ending at least one
hour before close), liquidity filter and 90% threshold (`outputs/research/kalshi_tails/bets.csv`).

## Order and fill

- YES favourite (`yes_bid >= 0.90`): rest a buy of YES at `yes_bid` from the snapshot to close.
  Filled if a trade with `taker_side == "no"` prints at a YES price strictly below `yes_bid`.
- NO favourite (`yes_ask <= 0.10`): rest a buy of NO at `1 - yes_ask`. Filled if a trade with
  `taker_side == "yes"` prints at a YES price strictly above `yes_ask`.
- Strictly through, so queue position is never assumed. Unfilled orders do not trade.
- Maker fee `0.0175 * p * (1 - p)` at the price paid. Held to settlement.

## Success criterion

Mean return per filled bet, averaged within each event first, positive with an event-clustered 95%
CI (5,000 draws, seed 0) excluding zero.

**Mechanism check**: filled bets' win rate minus price paid is positive with a CI excluding zero, and
the filled bets' win rate is not significantly below the unfilled candidates' (difference CI not
entirely negative). Fill rate and filled volume reported as the capacity bound.
