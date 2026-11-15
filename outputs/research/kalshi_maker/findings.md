# Kalshi favourites bought as a maker: the sign turns, the interval does not clear

Pre-registration `_private/kalshi_maker_prereg.md`. Script: `scripts/research_kalshi_maker.py`.
Same 383 candidates as the taker test (`../kalshi_tails/`); only the side of the spread changes.
A resting bid at the best bid from the snapshot to close counts as filled only when a later trade
prints strictly through it. Maker fee `0.0175 p (1 - p)`.

| same candidates | bets traded | mean return per bet [CI] | mean price paid | win rate |
|---|---|---|---|---|
| taker, at the ask | 383 | -2.03% [-4.07%, +0.21%] | 96.1c | 0.963 |
| maker, resting at the bid | 66 filled (17.2%) | +1.64% [-2.20%, +6.92%] | 93.7c | 0.955 |

Returns averaged within each event first; event-clustered 95% intervals, 5,000 draws; 50 events
with a fill. **Primary criterion fails** (interval contains zero). Mechanism check fails on its first
half: win rate minus price paid +1.76 points, CI [-3.71, +6.09]. Adverse selection is mild and not
significant: filled favourites won 95.5% of the time against 96.5% for unfilled candidates,
difference CI [-7.10, +3.96] points.

Reading: the only test in the programme whose point estimate changes sign for the right reason,
buying 2.4 cents cheaper at a quarter of the fee, and the one most consistent with the cross-market
finding that the premium accrues to the side providing liquidity. It is not evidence yet: 66 fills
over 50 releases cannot resolve a 1.6% edge, and the strictly-through rule understates fills, so the
realised fill rate of a live order would be higher and its adverse selection unmeasured here.
Capacity is small: median through-volume at the resting price about 330 contracts.
