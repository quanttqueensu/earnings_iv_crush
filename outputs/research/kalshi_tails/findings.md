# Selling the tails of Kalshi scheduled-release distributions: not tradable at the touch

Pre-registration `_private/kalshi_macro_tails_prereg.md`. Script: `scripts/research_kalshi_tails.py`.
Free data: Kalshi public API (settled events, ladder markets, hourly candles).

Seven US release series (CPI headline, core, year-on-year and core year-on-year, payrolls, initial
and continuing claims); 3,052 ladder contracts, 2,508 with a snapshot one hour before close, 1,209
passing the liquidity filter (traded in the prior 24 hours, two-sided quote). Rule: buy the
favourite side of any contract at 90% or more, at the touch, taker fee `0.07 p (1 - p)`.

| | bets | events | mean return per bet [CI] | win rate | mean price paid | win minus price [CI] |
|---|---|---|---|---|---|---|
| all | 383 | 191 | -2.03% [-4.07%, +0.21%] | 0.963 | 0.968 | -0.47% [-2.66%, +1.36%] |

Returns averaged within each event before averaging across events; event-clustered 95% intervals,
5,000 draws. **Primary criterion fails; mechanism check fails.** By series the point estimates are
negative for every series except core CPI year-on-year (33 bets, all won); jobless claims, the part
outside prior work, returns -4.1% per bet.

Calibration diagnostic: across 285 releases, 15.1% of realised values fell in the outer 10% tails of
the implied distribution (snapshot mids), against 20% if calibrated, roughly two standard errors
low if releases were independent (they are not: headline and core CPI print together). The tails
look slightly rich at the mid, which is the direction a favourite-longshot bias predicts, but the
touch plus the taker fee costs more than that. This agrees with Diercks, Katz and Wright (2026) on
calibration and with the Polymarket evidence that the bias is not tradable after costs, and matches
the equity-options result: a premium visible at the mid that a liquidity taker gives back.

Capacity is thin: median 24-hour volume on the contracts bet is about 1,500 contracts, many tail
contracts never traded in the day before the release, and 544 markets had no candles at all.
