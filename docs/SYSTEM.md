# System

What the project trades, how it runs, what the evidence says, and what has been decided. This
file owns those four questions; every other document links here rather than restating them.
Figures below carry their basis, N and source so each can be checked. For live state (open
positions, switches, data present, trial count) run `python -m earnings_iv_crush.ops.orient`
instead of reading a number here.

## 1. The trade

Sell the at-the-money straddle on a single US name at the 15:59 ET close of the last session
before a scheduled earnings announcement, and buy the same strike and expiry back at the 15:59
close of the first session after it. One overnight gap, no hedge. Size on a Reg-T approximation
(`0.20 x spot + premium` per share, times the multiplier and contracts), 5% of a USD 250,000
account per position. The headline unit is net return on margin (RoM) per trade.

The session decides the bracket. An after-close (`amc`) announcement is entered on the
announcement day and exited the next session; a before-open (`bmo`) announcement is entered the
session before and exited on the announcement day. A name whose session is unknown is skipped,
never guessed.

The mechanism is real and measured: at-the-money implied volatility falls on 98.1% of 989
quote-marked events, by a mean of 48.65 volatility points (0.4865 in the engine's decimal
units). Driver attribution reconciles to realised P&L with zero residual, and vega is the
largest positive leg under both path orderings (theta first: vega +USD 355,325, theta
+USD 137,359, spot -USD 401,692 on the megacap book). The whole problem is monetising it.

## 2. What the evidence says

Every figure is per trade, net of the stated cost basis, with a date-clustered bootstrap 95%
interval (5,000 draws, seed 0) unless the row says otherwise.

| Book | Block | N | Result | Basis and source |
|---|---|---|---|---|
| Term gate q=0.80 | Megacap 2013-2024, pooled | 391 | Sharpe +0.056 [-0.042, +0.180] | quote marks, 2.0% per side; `outputs/research/fills_rescore.csv` |
| Term gate q=0.80 | Broad 2025-26 | 232 | Sharpe -0.210 [-0.347, -0.058] | net RoM, 11.6% round trip; upper bound, see below |
| Matched random | Broad 2025-26 | 224 | Sharpe +0.105 [-0.030, +0.270] | same; upper bound |
| Unconditional, attrition-corrected | Broad 2025-26 | 1,492 | Sharpe -0.087 [-0.142, -0.031] | zero-bid exit legs at ask/2; still an upper bound; `research/frozen_selector/findings/oos_2026_attrition_audit.md` |
| Unconditional | Broad 2013-2024 | 7,765 | net -2.13% RoM [-2.42%, -1.86%], gross +0.57% [+0.29%, +0.83%]; negative net in all twelve years | 15:59 chains, 11.6% round trip; `research/selection/findings/ml_zoo.md` |
| Unconditional | Megacap 2013-2024 | 1,794 | net -0.59% RoM [-1.11%, -0.06%], gross +1.65% [+1.12%, +2.18%] | same source |

**The 2025-26 ledger was biased upward.** It dropped an event whenever an exit leg showed a zero
bid, which happens after large moves, so attrition depended on the outcome (dropped events had a
realised-over-implied ratio of 0.85 against 0.65 kept). The often-quoted unconditional +0.043
[-0.026, +0.120] on 1,221 events came from that ledger; corrected, it is -0.087 on 1,492, and
the remaining unmarkable events also lean to large moves, so even that is an upper bound. Every
figure from that ledger inherits the bias. The megacap 2013-24 panel does not show it.

**What every test since has found.** A premium is visible at the mid and a liquidity taker pays
it away. The median implied move on the broad block is 2.1 times the median realised (6.75%
against 3.17%) and the gross unconditional book is positive, yet every liquidity-taking version
fails net: selectors, gates, sizing, holds, structures and other markets (the closed list is in
[`RESEARCH_STATE.md`](RESEARCH_STATE.md)). Resting orders on the liquidity-provider side improve
return on margin by about 2 points per trade on the broad block, but the fills are adversely
selected (5-minute markout -0.68 of the half-spread) and the result does not hold on the
megacap book (`research/execution/findings/flow_liquidity.md`).

**Execution is measured, not assumed.** 34,672 option prints matched to their prevailing
consolidated quote at the 15:30 to 15:59 ET window: median price improvement 0.0%, 21.2% at or
better than the mid, 54.3% at the full touch. Measured cost is 1.7871% of premium per side
(entry 1.2714%, exit 3.0182%), so a round trip costs about 11.6% of premium.

## 3. How it runs

Three activities run side by side.

1. **Research.** Closed studies are frozen under `research/<line>/` with their
   pre-registrations and findings. New studies follow [`PROTOCOL.md`](PROTOCOL.md) and are
   scored against the bars in section 5.
2. **The forward paper book.** One pass each regular session on an Interactive Brokers paper
   account (`python -m scripts.paper_trade_ibkr session`), driven by Task Scheduler on Windows
   or cron in `deploy/`. It runs the unconditional rule through the mid-to-touch order ladder of
   [`FORWARD_TEST_SPEC.md`](FORWARD_TEST_SPEC.md) and records every order event. Operations are
   in [`RUNBOOK.md`](RUNBOOK.md).
3. **Data.** Sources, licences, costs and the shared bucket are in [`DATA.md`](DATA.md).

The package layout and the engine are in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## 4. Standing decisions

Each has a decision record under [`decisions/`](decisions/).

1. **Paper only.** The forward book never trades real money. The connection refuses every
   live-account port. (0003)
2. **The forward book is the unconditional rule traded through the ladder.** It measures how much
   of the spread a mid-seeking ladder recaptures on real order lifecycles, which no backtest can
   answer. It is not a selector test. (0003, [`FORWARD_TEST_SPEC.md`](FORWARD_TEST_SPEC.md))
3. **Shakedown limits.** 3 names a day and 5 contracts a leg until 20 consecutive sessions run
   with zero reconciliation breaks; then the specification's 12 and 20. (0005)
4. **The paper radar is retired.** The IBKR book replaces it as the forward record. (0002)
5. **Licensed data never enters the repository.** Only the project's own aggregates do; raw
   vendor rows are shared through the club bucket. (0004)
6. **Main is the trunk.** Changes arrive by pull request with green CI; each version the paper
   book runs is tagged `paper-YYYY-MM-DD`. (0001)
7. **The decision rule of 2026-10-06 fired.** Both cost levers (conditional hold, causal spread
   gate) failed their pre-registered tests, so the single-name straddle as a taker vehicle is
   closed; work moved to the liquidity-provider side and other scheduled-event markets, which have
   since also failed as takers. See [`RESEARCH_STATE.md`](RESEARCH_STATE.md).

## 5. The bar any new result has to clear

- **A selector** beats the participation-matched random null on the same pool, with a
  date-clustered interval on the difference that excludes zero, on a block it was not fitted to.
- **An execution lever** improves the paired per-trade result by at least +0.65% of margin with
  an interval above zero (about 22% of the 2.95-point cost drag; the forward-test threshold).
- **Any in-sample Sharpe** is read against the trial count: with about 1,500 recorded trials the
  expected best per-trade Sharpe under no edge is about +0.43, so only a pre-registered test on
  untouched data carries weight.
- **Annualisation** uses the square root of the book's own trades per year, stated beside the
  figure (about 35 a year on the megacap book, so pooled +0.056 is about +0.33 annualised), never
  the daily square root of 252.

## 6. Open assumptions that could move a level

1. **Stale entry spot.** The entry spot falls back one session silently on 16.9% of 1,790 priced
   megacap events (27.4% of the 391 gated). A partial correction moved the pooled Sharpe from
   +0.0555 to +0.0454. Any new megacap result must be scored on the repaired file.
2. **Margin convention.** A probe suggests IB charges 2.18 to 2.37 times the modelled Reg-T
   figure. Comparisons between books are unaffected; absolute RoM levels are research measures.
3. **Capacity and impact.** Prevailing spreads are measured; the book's own impact is not.
4. **No intraday path.** Two observations per trade, so stops and intraday entries are untested.
5. **Cross-name dependence** beyond same-date clustering is not modelled.
6. **Integer sizing** drops the highest-priced names, a selection correlated with price level.
