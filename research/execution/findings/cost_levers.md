# The two remaining cost levers: both fail their pre-registered criteria

Pre-registration `research/execution/preregs/cost_levers_prereg.md` (SHA-256 in `../prereg_cost_levers.json`),
amendment 01 made before any outcome was viewed. Two trials; DSR against 1,491. Scripts:
`scripts/research_conditional_hold.py`, `scripts/research_spread_gate.py`.

## Test H: conditional hold to expiry, 2013-2018 validation

Rule: hold to the front expiry unless the event's implied move is at or above the causal
expanding 0.70 quantile of earlier events, in which case exit at the next session close.
Measured 15:59 cost basis (entry 1.2714%, exit 3.0182% of premium; assigned shares flattened at
2 basis points of strike). Harness reproduced the stored next-session and hold Sharpes to six
decimals before any new figure was computed.

| population | N (held) | next-session Sharpe | conditional Sharpe [CI] | mean advantage [CI] |
|---|---|---|---|---|
| frozen 2013-2018 book, causal cut (primary) | 193 (87) | +0.0143 | +0.0256 [-0.1025, +0.1837] | +0.0018 [-0.0045, +0.0087] |
| frozen book, block percentile (look-ahead, comparison only) | 193 (135) | +0.0143 | +0.0126 | +0.0001 [-0.0111, +0.0116] |
| every 2013-2018 event, CRSP as-traded settlement | 926 (625) | -0.0367 | -0.0520 [-0.1156, +0.0173] | -0.0028 [-0.0075, +0.0019] |

Return on margin per trade, date-clustered 95% intervals, 5,000 draws. **Primary criterion
fails**: the advantage interval contains zero. The 2023-2024 evidence for the rule (+0.0313 of
margin, n=66) was scored on the legacy basis that charged an 8.55% exit half-cross; at the
measured 3.0182% there is far less to save by not buying back, and what remains is within noise.
Gap risk on assigned shares and pin risk are not modelled and would weigh further against
holding.

## Test S: causal spread gate, both megacap blocks

Rule: trade when expected round-trip cost (current entry half-spread plus the name's mean prior
exit half-spread, both relative to mid) is at or below the causal median of earlier events.
Net return charged at each event's own quoted touch.

| block | book | N | Sharpe [CI] | hit | gross at mid | expected cost | null percentile |
|---|---|---|---|---|---|---|---|
| 2013-2018 | gated | 316 | -0.0347 [-0.1443, +0.0827] | 0.585 | +0.0040 | 0.048 | 91st |
| 2013-2018 | ungated | 808 | -0.0916 [-0.1574, -0.0184] | 0.559 | +0.0054 | 0.084 | |
| 2019-2024 | gated | 372 | -0.0070 [-0.1031, +0.1073] | 0.624 | +0.0057 | 0.036 | 94th |
| 2019-2024 | ungated | 707 | -0.0594 [-0.1263, +0.0168] | 0.594 | +0.0050 | 0.066 | |

**Primary criterion fails on both blocks**: neither gated interval excludes zero. The gate does
what it is built to do, cutting expected cost by about 45% and lifting per-trade Sharpe by about
0.05 in both blocks, ranking at the 91st and 94th percentiles of 1,000 participation-matched
random draws. The efficiency counter-hypothesis is not clearly supported (gross premium at the
mid falls in one block and rises in the other). What the gate cannot do is create premium: on the
quoted touch the cheapest half of the book still nets approximately zero.

## Consequence under the decision rule

Both levers fail, so the binding decision rule in section 2.0 of the state of record applies: the
single-name earnings straddle stops being the vehicle, and work moves to scheduled-event
volatility elsewhere, starting with the Deribit macro-event pilot.

## Artefacts

| File | Content |
|---|---|
| `conditional_hold.csv` | test H, both populations, both cost bases |
| `spread_gate.csv` | test S, gated and ungated books per block |
