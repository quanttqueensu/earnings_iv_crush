# The macro-release crush in BTC options: no event premium beyond the ordinary one

Pre-registration `_private/deribit_macro_event_prereg.md`, amendment 01 (delivery-price paging
defect, fixed before any return-dependent change). Script: `scripts/research_deribit_macro.py`.
Free data: Deribit public trade history (marks, prices, initiator side), daily `btc_usd` delivery
prices; release times from Kalshi event close times.

Short BTC straddle on the daily expiry spanning each CPI, payrolls or FOMC release since 2023-01-01,
entered one hour before the release at the mark less the measured seller's discount, settled at the
next 08:00 UTC delivery price, against the identical trade a week earlier on a day with no release.

| slice | pairs | event return on notional | control | event hit | paired difference [CI] |
|---|---|---|---|---|---|
| all | 116 | +0.192% | +0.112% | 0.629 | +0.079% [-0.275%, +0.440%] |
| CPI | 43 | +0.391% | +0.161% | 0.674 | +0.230% [-0.374%, +0.848%] |
| FOMC | 30 | -0.189% | -0.113% | 0.467 | -0.077% [-0.743%, +0.575%] |
| payrolls | 43 | +0.258% | +0.220% | 0.698 | +0.038% [-0.543%, +0.628%] |

Event-clustered 95% intervals, 5,000 draws. **Primary criterion fails.** The mechanism check
(implied excess variance over the control minus realised excess) is +0.00014, CI
[-0.00007, +0.00036], not significant. Net taker buying before the release has no relation to the
event return (Spearman +0.003).

Reading: selling a release-spanning BTC straddle earns about what selling one on an ordinary day
earns (+8.9% of premium on event days), which is the general BTC variance premium. Scheduled macro
releases are not priced with a measurable surplus in BTC options, unlike earnings in single-name
equity options, where the implied move is about twice the median realised move. Median seller's
discount to mark 5.7% of the option's value; the fill estimate is a median over taker sells, not a
quote, and the daily-expiry book thins out away from the money.
