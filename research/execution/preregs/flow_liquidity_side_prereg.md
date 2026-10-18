# Pre-registration: the liquidity-provider side, measured from signed option trades

Frozen before any trade data for this test is pulled. SHA-256 recorded in
`outputs/research/prereg_flow_liquidity_side.json`.

## Status

Opened on the project owner's explicit instruction after the final earnings set failed. Every
earnings test so far, and the Kalshi and Deribit pilots, took liquidity; the common finding is a
premium visible at the mid that the taker pays away. These two tests are the only ones aimed at
the other side of the spread. Two trials; DSR against 1,497 (1,495 plus the Kalshi tails and
Deribit pilots).

## Data

Databento OPRA `cmbp-1` (every trade with the prevailing consolidated quote) on the two contracts
each event trades, windows in America/New_York time built by localise-and-convert and verified on
return: (a) from 09:30 two sessions before entry to 16:00 on the entry session; (b) 15:00 to 16:00
on the exit session. Hard spend cap $10.00; estimate before the pull $2.12 for the broad block.

Blocks: **discovery** the 2025-2026 broad ledger (`oos_2026_ledger.csv`, 1,221 events), never used
for any flow signal; **validation** the 2023-2024 events of the megacap panel's discovery block
(`reverse_alpha/panel.parquet`, entries on or after 2023-03-28, the first `cmbp-1` date).

## F1. Resting orders instead of crossing

**Mechanism.** Liquidity takers pay the full touch (zero median price improvement in 34,672 prints
on the megacap book), and market makers earn the spread. A resting order at the mid earns part of
it when it fills; the risk is adverse selection, fills concentrating where the price is about to
move against the order.

**Rule.** Per leg, at 15:00 on the entry session post a sell at that leg's mid (from the prevailing
quote at 15:00); it fills if any trade on that leg after 15:00 and up to 15:59:59 prints strictly
above the limit. Unfilled legs cross at the 15:59 bid. On the exit session post a buy at the leg's
15:00 mid, filled if a trade prints strictly below it; unfilled legs cross at the 15:59 ask. Strictly
through, so queue position never has to be assumed.

**Outcome.** Return on margin per event against the same events always crossing at 15:59.

**Success (discovery, then validation).** The resting book's per-trade Sharpe has a date-clustered
95% CI excluding zero and positive, **and** the paired improvement over always-crossing has a CI
excluding zero. **Mechanism check (adverse selection)**: the mean return of events where the entry
order filled passively is not significantly below that of events where it did not (difference CI
not entirely negative). A pass that fails this check is reported as unexplained.

## F2. Customer demand pressure as the selector

**Mechanism.** Retail buys options before earnings and overpays (de Silva, So and Smith 2026); market
makers charge for inventory risk, and past order imbalance predicts option returns better than any
other common predictor (Muravyev 2016). Heavier net customer buying should mark richer options.

**Signal.** Net signed volume on the two traded contracts from window (a) start to 15:00 on the entry
session: trades above the prevailing mid are buys, below are sells, at the mid are excluded;
`imbalance = (buys - sells) / (buys + sells)` in contracts. Sell when high. Events with fewer than
10 signed contracts are ineligible.

**Outcome.** Net return on premium (a unit that selling a larger option does not raise mechanically),
with return on margin reported.

**Success.** Discovery: Spearman(decile, mean outcome) at least +0.60 and the top-minus-bottom-quintile
difference with a date-clustered CI excluding zero. **Mechanism check**: Spearman(imbalance, implied
move) below 0.30, so the signal is not the priced move restated. Validation, only after a discovery
pass: causal q=0.80 book (expanding quantile of strictly earlier events, minimum 25) beats a
participation-matched random null, CI on the Sharpe difference excluding zero.
