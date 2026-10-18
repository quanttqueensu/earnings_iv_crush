# Pre-registration: selling the tails of Kalshi scheduled-release distributions

Frozen before any snapshot price for this test is pulled. SHA-256 recorded in
`outputs/research/prereg_kalshi_macro_tails.json`. A pilot in a new market; it does not bear on
the earnings verdict.

## The analogy, and where it breaks

A ladder of Kalshi "at least X" contracts on a scheduled number (CPI, payrolls, jobless claims)
prices the market's cumulative distribution for that number, as an option chain prices one for a
stock. At the release the distribution collapses to a point: the analogue of the IV crush. Selling a
straddle is short both tails of the move distribution; here the equivalent is to buy the favourite
side of every contract priced at 90% or more, i.e. to bet against both tails of the release.

## Mechanism

A favourite-longshot bias: low-priced contracts win less often than their price implies, high-priced
ones slightly more often. Documented on Kalshi across 300,000+ contracts (Burgi, Deng and Whelan
2025, CEPR DP20631) and attributed to over-weighting of small probabilities, the same preference
that makes retail overpay for short-dated options. **Counter-evidence, stated before the test:**
Diercks, Katz and Wright (NBER w34702, 2026) find Kalshi macro densities well calibrated for CPI,
PCE, unemployment, payrolls, GDP and the funds rate; on Polymarket the bias is not reliably tradable
after costs (arXiv 2609.12878). Weekly and continuing jobless claims are outside the NBER study's
coverage. A null is the expected outcome.

## Universe

Every settled event, all history the API returns, in series `KXJOBLESSCLAIMS`, `KXCONTCLAIMS`,
`KXCPI`, `KXCPICORE`, `KXCPIYOY`, `KXCPICOREYOY`, `KXPAYROLLS`, restricted to markets with
`strike_type` `greater_or_equal` or `greater` (ladder contracts). Markets and candlesticks from the
live or `/historical/` namespace as the API's cutoff dictates.

## Snapshot and trade

- **Snapshot**: the last hourly candle ending at least one hour before the market's `close_time`.
  Quote fields `yes_bid.close`, `yes_ask.close`.
- **Liquidity filter**: the market must show positive volume in the 24 hourly candles up to the
  snapshot, and `0 < yes_bid < yes_ask < 1`.
- **Rule**: if `yes_bid >= 0.90`, buy YES at `yes_ask`; if `yes_ask <= 0.10`, buy NO at
  `1 - yes_bid`. Otherwise no trade. Held to settlement.
- **Cost**: taker fee `0.07 * p * (1 - p)` per contract at the price paid, orders of 100 contracts so
  per-order rounding is under 0.01 cent per contract.
- **Return per bet**: `(payoff - p - fee) / (p + fee)`, payoff 1 if the side bought wins, else 0.

## Success criterion

Mean return per bet, averaged within each event first so one event with many contracts does not
dominate, positive with an event-clustered 95% bootstrap CI (5,000 draws, seed 0) excluding zero.

**Mechanism check**: the favourites' realised win rate exceeds the mean price paid for them, with an
event-clustered CI on the difference excluding zero. A pass without it is reported as unexplained.

Diagnostics, reported either way: the per-series split (claims series are the differentiated part);
the distribution of each release's realised value within its implied CDF (probability integral
transform), which is uniform if the density is calibrated and concentrated in the middle if the
tails are overpriced; bet counts and volume, which bound capacity.
