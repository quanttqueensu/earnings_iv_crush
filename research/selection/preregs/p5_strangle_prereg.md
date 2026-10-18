# Pre-registration: P5, short strangle at plus or minus one implied move

## Hypothesis

Selling the wings instead of the centre trades less gap convexity near the money: an announcement
move smaller than the implied move leaves both legs worthless, and the strangle's margin per unit of
premium differs from the straddle's. If out-of-the-money event options are priced richer relative to
their expected payoff than the at-the-money straddle (the earnings smile is often concave before the
event: Alexiou, Goyal, Kostakis and Rompolis, Review of Finance 2025), the strangle may earn more per
unit of margin. Counter-argument (the handbook's prior: low): it is still a liquidity-taking
structure, and out-of-the-money options carry wider spreads relative to premium.

## Scope and data

- Events: the 2025-2026 scored ledger `outputs/research/oos_2026_ledger.csv` (1,221 events), so
  every strangle pairs with its straddle trade.
- Chains: the 15:59 ET consolidated quotes in `data/cache/backfill_chains` on the entry and exit
  sessions; the straddle's expiry from the ledger.
- Strikes: with F the parity forward at entry (P1's construction) and m the ledger's
  `implied_move`, the call strike is the lowest listed strike at or above F(1 + m) and the put strike
  the highest at or below F(1 - m), each with a two-sided usable quote at entry and exit (P1's usable
  rule). Otherwise the event is dropped and counted.
- Prices: sold at the entry bids, bought back at the exit asks (the touch), as the ledger's straddle.
  USD 0.65 per contract per leg each way.
- Margin (Reg-T, short strangle): the larger of the two legs' naked requirements plus the other
  leg's premium; a leg's naked requirement is premium + max(0.20 S - out-of-the-money amount,
  0.10 S), per share times 100, with S the parity forward at entry.
- Return on margin (RoM) = (credit - exit cost - commissions) / margin, per trade.

## Primary hypothesis and decision rule

Pass requires both, date-clustered bootstrap on entry date, 5,000 draws, seed 0, 95% intervals:
(i) mean net strangle RoM > 0 with the interval above zero; and
(ii) mean paired difference (strangle net RoM minus the same event's ledger `net_rom`) > 0 with the
interval above zero.
Kill (handbook rule) if (ii) fails. Per-trade Sharpe with the deflated Sharpe ratio against 1,505
trials.

## Secondary, descriptive only

The mid arm; the entry half-spread as a share of premium for strangle and straddle; RoM by implied
move tercile; worst ten trades.

## What is not allowed

No change to strike rule, prices, margin or sample after any outcome is seen. Amendments are dated,
hashed and reported beside the original.
