# Kalshi maker result does not replicate on unseen series

Pre-registration `research/other_markets/preregs/kalshi_maker_replication_prereg.md` (series list frozen and hashed before
any price was pulled). Script: `scripts/research_kalshi_replication.py`. 81 Kalshi Economics series
chosen by a mechanical settlement-source rule, every event of the original sample removed; rule,
snapshot, liquidity filter, pricing and fill rule unchanged from the original tests.

| book | bets | release dates | mean return per bet [CI] |
|---|---|---|---|
| maker (resting bid, strictly-through fills) | 39 (14.9% fill rate) | 26 | -1.37% [-6.89%, +6.16%] |
| taker (at the ask) | 262 | 117 | -1.33% [-3.17%, +0.67%] |
| maker, CPI release days excluded | 38 | 25 | -1.50% [-7.24%, +6.26%] |
| taker, CPI release days excluded | 221 | 97 | -1.96% [-4.05%, +0.38%] |

Averaged within release date first; date-clustered 95% intervals, 5,000 draws. **Primary criterion
fails; mechanism check fails.** Filled favourites' win rate minus price paid: -4.56 points
[-17.03, +6.03]. Adverse selection is now visible in the point estimate: filled favourites won 6.22
points less often than unfilled candidates [-19.19, +3.67].

Reading: the +1.64% per filled bet on the original seven series (66 fills) was most plausibly noise.
On new series the maker book loses like the taker book, and the fills that do happen lean toward
losers, the adverse selection the original test could not resolve. The Kalshi line is closed.
