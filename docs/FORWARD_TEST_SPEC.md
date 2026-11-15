# Forward Test Specification: Unconditional Paper Book at Mid

Author: Jordan Odorico

## Amendments and build status

Amended 2026-10-18 when the session pass was built. The rule, the ladder, the guards and the
verdict criteria are unchanged.

1. **Order log format.** The log is `outputs/live/order_events.csv`, appended one line at a time,
   not a parquet file: a parquet append rewrites the file and loses the log if the process dies
   mid-write. The schema in section 6 is unchanged.
2. **Shakedown limits.** The pass starts at 3 names a day and 5 contracts a leg
   (`LiveConfig.max_names_per_day`, `max_contracts_per_leg`) and moves to the values in section 4
   only after the operational go in section 9 (`docs/decisions/0005-shakedown-limits.md`).
3. **Baseline figures.** The section 1 figures (+0.49% net, Sharpe +0.043 on N=1,221) come from
   the 2025-26 ledger later found biased upward by outcome-dependent attrition (corrected
   unconditional Sharpe -0.087 [-0.142, -0.031], N=1,492, still an upper bound). The +0.65%
   threshold is a paired improvement over the backtest basis on the same trades, so its
   definition does not depend on the baseline level.
4. **Ticket status.** Built and tested (`tests/live/test_ladder.py`, `test_session.py`): T1
   order-event log (`live/order_events.py`), T2 ladder engine (`live/ladder.py`), T3 HALT, T4 entry
   booking from fills, T5 separate dry stores, T9 filters and funnel (`live/session.py`), T10
   schedule and module drivers, T11 no-bid exit legs. Open: T6, T7, T8, T12, T13
   (`docs/ROADMAP.md`).

## 1. Purpose, scope and success criteria

**Purpose.** Every liquidity-taking version of the earnings straddle fails net of the bid-ask
spread: the unconditional 2025-26 book earns gross +3.44% return on margin (RoM) per trade but
only +0.49% net, per-trade Sharpe +0.043, date-clustered 95% CI [-0.026, +0.120], N=1,221.
The forward test asks one question the backtest cannot answer: when the same unconditional rule
is traded leg by leg with limits that start at the mid and walk toward the touch, how much of
the 2.95 points of RoM that the taker pays (gross minus net; per-trade cost over margin has mean
2.96% and standard deviation 0.70%) does the book recapture, measured on real broker order lifecycles rather than
on a cost model?

**Hypothesis.** A mid-seeking time ladder, finishing in the minutes before the 15:59 ET mark
the backtest uses, recaptures enough of the spread to move the per-trade result materially. The
pre-stated threshold is a paired improvement of at least +0.65% of margin per trade over the
backtest cost basis on the same trades. That figure is about 22% of the 2.95% cost drag, and is
what lifts per-trade Sharpe from roughly zero to 0.10 given a per-trade standard deviation of
11.4% of margin.

**In scope.** The unconditional rule on the validated broad universe, paper account only, legs
(not combination orders), session-aware one-session hold, the guards and limits in sections 4
and 5, a complete order-event log, daily broker reconciliation, monitoring, and the two-stage
verdict in sections 9 and 10.

**Out of scope.** Any selector (the matched random null remains the bar for those), combination
orders, which would be a separate forward-only arm, real money, and any change to the research
scoring path.

**Success criteria, in order.**

1. *Operational go* (section 9): 20 consecutive sessions with zero reconciliation breaks and
   100% of order lifecycles logged. Until this holds, no P&L figure from the book is reported.
2. *P&L verdict* (section 10): not before about 600 completed trades. The verdict passes if
   the date-clustered 95% CI on the mean paired improvement lies above zero and the point
   estimate is at least +0.65% of margin. A season-level futility stop ends the test early if
   the upper CI bound falls below +0.65%.
3. *Evidence condition* (section 11): paper fills count as evidence only on real-time OPRA
   quotes. On the default delayed feed, the book can satisfy criterion 1 only.

## 2. The rule

**Selection.** `LiveConfig.selection_rule = "unconditional"`: every event on the validated
universe (`UNIVERSE_PATH`, the 346-name broad block) whose entry session is today, subject only
to the filters in section 5 and the limits in section 4. No signal enters the ordering of
candidates.

**Timing.** `SESSION_AWARE_TIMING=1`, which matches the backtest's one-session hold: an `amc`
name is entered on the announcement day and exited the next session; a `bmo` name is entered the
session before and exited on the announcement day. The legacy fixed offset holds two sessions in
every case and must not be used for this book.

**Instrument.** The front expiry strictly after the exit date (section 5.2), at the listed
strike nearest spot at the entry snapshot. The exit closes the stored strike and expiry, never a
re-picked strike; the harness already enforces this (`tests/live/test_w0_safety.py`).

**Sizing.** `pnl.size_contracts` at 5% of `GlobalConfig.account_size` ($250,000) in modelled
Reg-T margin, so contract counts match the backtest. Return on margin is reported on the
modelled Reg-T basis, as in the backtest, and also on the broker's reported initial margin,
which a probe put at 2.18 to 2.37 times the model. On the 2025-26 block this rule gives a median
of 3 contracts per leg (90th percentile 11, 99th 27) and sizes 108 of 1,221 events (8.8%) to
zero, because one contract of a high-priced name exceeds 5% of the account. Those events are
logged with reason `sized_zero` and not traded; ticket T8 decides whether a one-contract floor
is adopted, since dropping expensive names is a known bias (state of record, open assumption 7).

### 2.1 The time ladder

The backtest marks entry and exit on the 15:59 ET consolidated quote. The ladder therefore
finishes before 15:59, with every order cancelled by 15:58:00, so no forward fill comes from a
book the backtest never saw. Option spreads narrow through the trading day rather than following
the equity U-shape (Chan, Chung and Johnson 1995), so a ladder late in the session also trades
in the tightest part of the day.

| Time (ET) | Action |
|---|---|
| 15:20:00 | Scheduled start: session guard, gateway check, calendar confirmation (section 5.3), chain snapshots, filters, sizing, limits |
| 15:40:00 | Candidate list frozen; broker position reconciliation (section 8) for every exit due |
| 15:45:00 | Rung 0: every leg at mid |
| 15:47:30 | Rung 1: 25% of the way from mid to the touch |
| 15:50:00 | Rung 2: 50% |
| 15:52:30 | Rung 3: 75% |
| 15:55:00 | Rung 4: the touch (bid for a sell, ask for a buy) |
| 15:56:30 | Sweep: every unfilled exit leg is re-priced once through the displayed ask |
| 15:58:00 | Cancel every working order; re-read status after `exit_cancel_settle_s` |
| 15:59:00 | NBBO snapshot of every held leg, filled or not (the counterfactual basis) |

Entry legs sell, walking from mid down toward the bid; exit legs buy, walking from mid up
toward the ask. Each rung re-quotes the leg. A failed re-quote holds the resting order rather
than walking a stale book, and a leg whose own book is crossed, has no offer or has no bid is
not priced. Every limit is rounded to a legal tick away from the far touch
(`ib_orders.round_to_tick`). All entry and exit legs run concurrently in one ladder engine, so
an exit day with many names does not push entries out of the window.

**Sweep.** The touch rung bids the displayed ask. On a delayed feed that ask is about fifteen
minutes old and can sit under the real offer, which is how the first transmitted exit
(2026-11-10) bought back its call and left its put short. At 15:56:30 every exit leg still
unfilled is therefore re-priced once to the displayed ask plus the larger of
`exit_sweep_frac` (20%) of the ask and `exit_sweep_min` (0.10 per share), rounded up to 0.05
below 3.00 and 0.10 above so the order is legal in every option class. The broker fills a
marketable limit at the real offer, so the allowance bounds the price rather than setting it. A
leg whose order was rejected with nothing filled gets one fresh order at the sweep; a leg that
cannot be re-quoted is priced from the last book the ladder read; a leg never quoted is not
priced. Entry legs never sweep. A fill at the sweep is recorded as not filled at the limit, and
on any feed other than real time it is operational evidence only (section 11).

**Legging.** If one leg of an entry fills and the other does not by 15:58:00, the filled leg
is bought back at the sweep price before 15:59:00 and the event is logged as
`legged_flattened`. An exit still incomplete after the sweep has its working orders cancelled
and raises an alarm. The next session buys back only what is still short, provided the
broker's position equals the ledger quantity less the exit fills in the order-event log, and
books the exit at the blended price. A naked single leg carries more directional risk than the
straddle, so the operator is paged either way.

**Guards around the ladder.** A transmitting pass reports any option position at the broker
that no open ledger position explains, any exit that did not fill at all, any order still
working after the cancel (which it cancels), and a pass whose market data was cut by a
competing live session (IB error 10197). One position's fault never stops another's exit, and
an entry that fails to price never stops the exits.

**Schedule change.** The current driver starts at 15:35, which leaves no room for a 13-minute
ladder after snapshots and confirmation. The start moves to 15:20 ET on both hosts:
`deploy/crontab` becomes `20 15 * * 1-5`, and the Windows Task Scheduler trigger for
`IVCrushPaperDaily` moves to 15:20 local exchange time. The 25 minutes before rung 0 cover up to
40 chain snapshots at IB pacing limits, with margin for one gateway reconnect.

## 3. Session guards

`deploy/session_check.py` classifies the day on the NYSE calendar: exit status 0 for a regular
session, 10 for exchange closed, 11 for a 13:00 early close. Both drivers run it before anything
connects. On 10 the pass logs and exits cleanly. On 11 it skips: the ladder window falls after
the early close, and positions due that day exit on the next regular session, which holds those
positions one session longer than the backtest. Those trades carry a flag `early_close_hold` and
are reported separately. The Windows driver (`scripts/run_paper_daily.ps1`) gained this guard in
the review that accompanies this specification. Before it, Task Scheduler ran the pass on
exchange holidays.

The run date is the New York date whatever clock the host keeps
(`paper_trade_ibkr.exchange_today`), so a host on another time zone cannot enter or exit a day
early or late.

## 4. Hard limits in code

The limits live in `LiveConfig` (`earnings_iv_crush/config.py`) as named fields with their
rationale in the docstring, following the file's conventions: frozen dataclass, env-var
overrides only where an operator has a reason to change them, and no override for anything that
protects the account. A limit that binds is logged per candidate with a reason code and counted
in the heartbeat.

| Field | Proposed value | Env override | Rationale |
|---|---|---|---|
| `max_names_per_day` | 12 | `MAX_NAMES_PER_DAY` | On the 2025-26 block, entries per day have median 3, 90th percentile 17, maximum 31. A cap of 12 binds on 34 of 199 entry days and keeps 81.7% of trades, and holds concurrent positions in the ladder window (entries plus same-day exits) to about 24 against an uncapped 95th percentile of 33. |
| `max_contracts_per_leg` | 20 | none | A fat-finger guard. Return on margin is scale-free, so the cap changes no reported figure except through integer rounding; it binds on 2.2% of 2025-26 events. |
| `max_margin_frac` | 0.60 of broker net liquidation | none | Measured on the broker's reported initial margin after a what-if order, not on the model. At about 2.3 times the modelled 5%, one name costs roughly 11.5% of a $250,000 account, so the book needs a paper account with net liquidation of at least $1,000,000 (the IBKR paper default, recalled and to be confirmed on the account). At 60% that admits about 20 concurrent positions. Positions due to exit today count until their exit fills. |
| `max_per_sector_per_day` | 4 | none | Earnings cluster by sector (the large banks report on the same morning), and same-sector names on one day share one macro gap. Applied through `engine.risk.cap_concentration`. Ticket T7 must extend the sector map first: it covers only the 50 megacaps, and an unmapped name must raise, not fall into a shared "Unknown" bucket that the cap would throttle as one sector. |

**Ordering when a limit binds.** Candidates are admitted in a deterministic order that is
independent of any outcome or signal: ascending SHA-256 of `ticker + entry_date`. Admission
stops at the first candidate that would breach the margin cap rather than skipping to smaller
names, which would tilt the book toward cheap options. Under the null of no selection effect the
capped book has the same expected per-trade return as the unconditional population. It does,
however, reweight the book toward quiet days, so the report shows the capped and uncapped
populations side by side using the free radar record.

## 5. Event filters

Each filter writes a reason code, and the daily funnel (candidates, confirmed, filtered by each
reason, sized, admitted, filled) is printed and stored. A filter that removes every candidate on
a day with candidates raises an alarm.

### 5.1 Ex-dividend

A short American call that is in the money before an ex-dividend date can be assigned early,
which turns the straddle into a short stock position overnight. Skip the event if an ex-dividend
date falls on any session from the entry date through the exit date inclusive. Source: the IB
dividend schedule (generic tick 456 on the underlying), cross-checked against the free Nasdaq
dividend calendar. If the dividend schedule cannot be read, skip with reason `exdiv_unknown`;
never assume no dividend.

### 5.2 Expiry before exit

Select the front expiry strictly after the exit date. If the only event-bracketing expiry is on
or before the exit date, skip with reason `expiry_le_exit`. Exiting on expiry day risks pin and
automatic exercise if the exit is incomplete. The backtest kept these events: 14 of 1,221 on the
2025-26 block (1.1%) expire on the exit date, 13 of them on a Friday weekly expiry and 9 of them
`amc` names entered on the announcement day. That deviation is recorded and the two populations are reported both ways.

### 5.3 Earnings date and session confirmed on the day

An announcement entered on the wrong day, or in the wrong session, holds the position across no
print or across two. On the entry day, between 15:20 and 15:40, the date and session (`bmo` or
`amc`) must agree in at least two of three independent sources:

1. the Finnhub calendar (the current source);
2. the Nasdaq earnings calendar for that date;
3. the company's own announcement, read from an SEC EDGAR 8-K or press release
   (`data/edgar_sessions.py` is the starting point for session times).

Fewer than two agreeing sources means skip with reason `calendar_unconfirmed`. Sources that
disagree on the session are logged with each source's answer. Unknown is never resolved by
guessing.

## 6. Order-event log

Every state change of every order is appended to `outputs/live/order_events.parquet`, one row
per event, written before the harness acts on that event. The log is the primary record. The
ledgers are derived from it and must reconcile to it.

| Column | Type | Meaning |
|---|---|---|
| `event_id` | string | UUID4 for this row |
| `run_id` | string | UUID4 for the pass; joins to the heartbeat |
| `ts_utc` | timestamp[ns, UTC] | Harness clock when the event was observed |
| `ts_broker` | timestamp[ns, UTC] | Broker timestamp from the execution or status message; null if none |
| `session_date` | date | Exchange date of the pass |
| `ticker` | string | Underlying |
| `position_key` | string | `ticker|entry_date|strike|expiry`; joins entry and exit lifecycles |
| `leg` | string | `C` or `P` |
| `con_id` | int64 | IB contract id |
| `strike` | float64 | Strike |
| `expiry` | date | Expiry |
| `purpose` | string | `entry`, `exit`, `flatten` (legging repair) |
| `side` | string | `BUY` or `SELL` |
| `order_id` | int64 | IB order id; constant across modifications |
| `perm_id` | int64 | IB permanent id |
| `rung` | int8 | 0 to 4; null for status-only events |
| `cross_frac` | float64 | Fraction of the way from mid to the touch for this rung |
| `event` | string | `submit`, `modify`, `status`, `fill`, `cancel_req`, `cancel_ack`, `reject`, `hold_stale_quote`, `skip_bad_book`, `nbbo_1559` |
| `status` | string | IB order status after the event (`PendingSubmit`, `Submitted`, `PreSubmitted`, `Filled`, `Cancelled`, `ApiCancelled`, `Inactive`) |
| `order_qty` | int32 | Total order quantity |
| `limit_price` | float64 | Working limit after rounding |
| `fill_qty` | int32 | Quantity of this execution; 0 for non-fill events |
| `fill_price` | float64 | Price of this execution; null for non-fill events |
| `cum_filled` | int32 | Cumulative filled quantity on the order |
| `avg_fill_price` | float64 | Broker average fill price on the order |
| `remaining` | int32 | Quantity still working |
| `commission` | float64 | From the commission report; null until it arrives |
| `nbbo_bid`, `nbbo_ask` | float64 | Leg touch at the event, from the streaming quote |
| `nbbo_bid_size`, `nbbo_ask_size` | int32 | Sizes at the touch |
| `nbbo_ts_utc` | timestamp[ns, UTC] | Quote timestamp, which exposes staleness |
| `market_data_type` | int8 | 1 real time, 3 delayed, 4 delayed-frozen |
| `underlying_bid`, `underlying_ask` | float64 | Underlying touch at the event |
| `reason` | string | Reject text, skip reason or alarm text |
| `transmit` | bool | Whether the order was transmitted; false rows are dry-run intents |

**Completeness rule.** An order lifecycle is complete when it has a `submit` row and a terminal
row (`Filled`, `Cancelled`, `ApiCancelled` or `Inactive`), with `cum_filled` on the terminal row
equal to the sum of `fill_qty` on its fills and equal to the broker's executions for that
`order_id` (`reqExecutions`). The share of complete lifecycles is the second operational go
metric. A `nbbo_1559` row exists for every held or intended leg on every entry and exit day,
filled or not.

## 7. P&L basis and the paired improvement

For every intended trade *i* (every admitted event, filled or not) the book computes two
figures, both in RoM on modelled Reg-T margin:

- **Realised:** credit from the entry fills minus cost of the exit fills minus commissions,
  over margin. An event whose entry did not fill has realised RoM of zero. A legged-and-flattened
  entry books the round trip on the filled leg.
- **Backtest basis:** the same event priced as the backtest prices it, selling both legs at the
  15:59 bid on the entry day and buying them at the 15:59 ask on the exit day, from the
  `nbbo_1559` rows, minus the same commission model.

The paired improvement is realised minus backtest basis. Counting unfilled events at zero
realised return keeps adverse selection in the measure: if mid-seeking orders fill mainly on the
events that go against the seller, as the Kalshi maker test found, the paired improvement shows
it. A filled-only comparison would hide it.

## 8. Broker reconciliation

**Before any exit transmits** (already in code): the broker must hold at least the ledger's
short quantity on both legs of the stored contract, or the exit is not sent and an alarm is
raised.

**Daily, after 15:59:00 and again at 16:15 ET**, the harness compares three records:

1. broker positions (`reqPositions`), by `con_id` with signed quantity;
2. the open-positions store, derived from the order-event log;
3. broker executions for the session (`reqExecutions`) against `fill` rows in the log.

A **reconciliation break** is any of: a broker position with no ledger position; a ledger
position the broker does not hold, or holds in a different quantity; an execution with no `fill`
row, or the reverse; a fill price differing by more than $0.005; or a commission report missing
after 16:15. Every break is written to `outputs/live/reconciliation_breaks.parquet` (date,
`con_id`, broker quantity, ledger quantity, kind, resolution, resolved_by) and raises an alarm.
A break stays open until it has a recorded resolution. The 20-session operational counter
resets on any break.

The ledger is written from broker confirmations only. A transmitted entry is booked from its
fills, never from the model price, and a dry run never writes to the store that transmitting
exits read (tickets T4 and T5 close the two gaps the review found here).

## 9. Monitoring, alarms and operational go

**Heartbeat.** Each pass appends to `entry_heartbeat.parquet` the funnel from section 5, orders
submitted, lifecycles completed, breaks found, and the market-data type in force.

**Alarms.** Any line starting `ALARM:` makes the cloud driver exit non-zero and send a
healthcheck failure with the log tail. The Windows driver logs the exit code and must gain the
same failure ping (ticket T10). Alarm conditions: every candidate failed to price; any
reconciliation break; an incomplete or legged exit; any exception in an exit (the pass continues
with the remaining positions and exits non-zero); a market-data type other than the one
configured; a quote older than 60 seconds at a rung; a reject from the broker; a missing
`nbbo_1559` row; a pass that did not start by 15:25 ET on a regular session (a dead-man check
from the health service); and the kill switch present on a scheduled day, so a forgotten switch
does not idle the book unnoticed.

**Kill switches.** `outputs/live/STOP` blocks new entries and leaves exits running, so the book
can always be flattened. A second switch, `HALT` (ticket T3), stops every transmission,
including exits, for incidents in which the ladder itself is suspect.

**Operational go criterion.** 20 consecutive regular sessions with zero reconciliation breaks
and 100% of order lifecycles complete under the rule in section 6. Sessions with no orders count
only if the heartbeat shows the pass ran. The go is recorded with the run ids of the 20
sessions.

## 10. P&L verdict and futility stop

**Timing.** No P&L verdict before about 600 completed trades. At the 2025-26 rate of about 200
events per quarterly season, less the 12-name cap (81.7% kept), the filters and zero-sized names,
600 trades takes about four seasons.

**Effective N.** Trades entered on the same date share the overnight market move, so they are
not independent. On the 2025-26 block the one-way ANOVA intra-cluster correlation of net RoM by
entry date is 0.144. With the 12-name cap the size-weighted mean cluster size is 8.5, giving a
design effect of 1 + (8.5 - 1) x 0.144 = 2.09. So 600 trades carry the information of about 287
independent trades, and one season of about 166 carries about 80. Uncapped, the block's 1,221
trades are worth about 444. These are planning figures from returns. The paired-improvement
series will have its own correlation, which is measured and reported at every review.

**Inference.** The mean paired improvement per trade, with a date-clustered bootstrap 95% CI
(5,000 draws, seed 0, resampling entry dates), matching the project's inference rules. No
annualisation. If an annual figure is ever needed, it uses the square root of the book's own
observed trades per year, stated beside it.

**Precision to expect.** The CI half-width is about 1.96 x sd / sqrt(N_eff). If fills are near
complete, the paired series varies only with execution, and the cost-over-margin standard
deviation (0.70%) suggests an sd of order 1% to 3%: about +/-0.12% to +/-0.35% at 600 trades,
and +/-0.22% to +/-0.66% per season. If many entries go unfilled, the zero-versus-taker pairs
pull the sd toward the 11.4% of a raw trade: about +/-1.3% at 600 trades, which could not
separate +0.65% from zero. The fill rate therefore decides whether the test can return a verdict
at all, and it is reported beside every interval.

**Futility stop.** At the end of each season (calendar quarter), compute the cumulative paired
improvement and its date-clustered CI. If the upper 95% bound is below +0.65% of margin, the
ladder cannot reach the threshold at any plausible remaining sample. The test stops, the result
is reported as is, and the book does not continue to 600 trades. There is no efficacy stop:
an early interval above +0.65% is reported as interim, and the verdict waits for 600 trades.
Looking four times inflates the false-stop rate slightly. That is accepted, because stopping only
saves operating effort and never declares success.

**Verdict.** Pass if, at 600 trades or more, the date-clustered CI on the mean paired
improvement excludes zero and the point estimate is at least +0.65% of margin, with the fill
rate, the legging rate and the result net of commissions all stated. Anything else is reported
as a failure of this execution lever, with the measured improvement and its interval.

## 11. Real-time data dependency (open owner decision)

The paper account runs on delayed data (`IB_MARKET_DATA_TYPE=4`; IBKR error 10089 confirms no
real-time entitlement). On delayed quotes the ladder prices against a book about 15 minutes old.
IB's paper engine then fills against the live market it simulates, so paper fills measure the
gap between stale and live quotes, not the spread captured. **Paper fills on delayed data are
not evidence for section 10.**

Real-time option quotes need IBKR's OPRA Top of Book (L1) subscription at USD 1.50 a month,
waived at USD 20 a month in commissions, which a paper account never generates (fee and waiver
verified on the IBKR market-data pricing page). A paper account does not hold subscriptions of
its own: it shares those of the linked live account once sharing is enabled in account
settings. That is recalled, not verified, and must be confirmed before purchase.

Until the owner decides, the book runs in operational mode: the full ladder, log and
reconciliation on delayed data, counting towards the operational go only. Every `order_events`
row carries `market_data_type`, and section 10 admits only rows with type 1.

## 12. Tickets

Each ticket is sized for one person, written so it can merge on its own, and closes with the
listed acceptance tests passing in `python -m pytest -q`, offline on fakes, plus ruff, black
(line length 100) and mypy clean on the files it touches. No ticket creates `TRANSMIT_OK` or
connects to a broker in tests.

**T1. Order-event log writer.** Module `live/order_events.py` with the section 6 schema, an
append that writes before the caller acts, and subscriptions to the IB order-status, execution,
commission and error events. Acceptance: a fake gateway driving submit, modify, partial fill,
fill, cancel and reject produces exactly the expected rows; the schema matches column for column;
the completeness checker flags a lifecycle with no terminal row and one whose `cum_filled`
differs from the sum of fills.

**T2. Concurrent ladder engine.** Generalise `place_managed_buyback` into one engine that runs
entry sells and exit buys concurrently on the section 2.1 schedule, with clock-driven rungs, the
legging rule and a hard cancel at 15:58:00. Acceptance: with a fake clock and gateway, rung
prices follow the schedule for both sides; nothing is working after 15:58:00 plus the settle
time; a legged entry is flattened and logged `legged_flattened`; a fill that races the cancel is
booked; an exception at any rung cancels everything working. The existing W0 and lifecycle tests
stay green.

**T3. HALT switch.** `LiveConfig.halt_file = "outputs/live/HALT"`, checked before every
transmission (entry, exit, flatten) and between rungs. Acceptance: with HALT present, no
`placeOrder` call occurs on any path; working orders are cancelled at the next rung; STOP alone
still lets exits transmit.

**T4. Entry booking from fills.** Write the open position from entry fills (credit equals the
sum of the leg fills), with `transmitted` and `entry_fill_ps` columns, and only after the ladder
completes. This is the precondition for `ENTRY_TRANSMIT_READY = True`. Acceptance: an unfilled
entry writes no open position; a filled one books the fill price, not the model value; flipping
the flag without T1 to T3 merged fails a test that checks for their presence.

**T5. Separate dry-run stores.** Dry-run entries and dry-mark exits write to `outputs/live/dry/`,
never to the stores that transmitting exits read, so a dry pass cannot mark a broker-held short
as closed. Acceptance: a dry forward-exit leaves the transmitting open store untouched; a
transmitting exit ignores dry-run positions.

**T6. Daily reconciliation job.** `scripts/reconcile_broker.py` runs the section 8 comparison at
15:59:30 and 16:15 ET and maintains the breaks file and the 20-session counter. Acceptance: fakes
for each break kind produce one break row each; a clean day produces none and advances the
counter; any break resets it.

**T7. Sector map for the broad universe.** Extend the sector labels to all 346 names from the
SEC SIC code (free, from the EDGAR submissions API) mapped to GICS-like sectors, frozen to a file.
Make an unmapped name raise inside the forward path. Acceptance: every universe ticker maps; on
the 2025-26 block the share of events the 4-per-sector cap would remove is computed and recorded
in the ticket; an unmapped ticker raises.

**T8. Hard limits in `LiveConfig`.** Add the section 4 fields with docstrings, the hash
ordering, the stop-at-first-margin-breach rule and a broker what-if margin check, and decide the
one-contract floor (owner sign-off). Acceptance: parametrised tests at each limit's boundary;
ordering is identical across runs and independent of signal columns; a candidate list over the
cap admits exactly the cap; the margin cap stops admission rather than skipping.

**T9. Event filters.** Ex-dividend, expiry-on-or-before-exit and two-of-three calendar
confirmation, with reason codes and the daily funnel. Acceptance: fixtures for each filter pass
and fail as specified; a missing dividend source skips with `exdiv_unknown`; one source alone, or
two disagreeing sources, skips with `calendar_unconfirmed`; a filter that empties a non-empty day
raises an alarm.

**T10. Schedule and drivers.** Move both schedules to 15:20 ET, add the dead-man ping and the
failure ping to the Windows driver, and make the Windows driver's Python steps run as modules
(`py -m scripts.paper_trade_ibkr`). At present the package is not installed into the scheduled
interpreter, so `py scripts\paper_trade_ibkr.py` fails on import. Acceptance: a text test asserts
both schedules start at 15:20 and the session guard runs first; the driver's steps import in a
clean shell on the scheduling machine.

**T11. No-bid legs at exit.** After a large gap the far out-of-the-money leg often shows no bid.
The exit quote currently defers the whole straddle, so such a position never exits through the
ladder. Price a buy-to-close from the ask alone (rungs between one tick and the ask) when the bid
is missing. Acceptance: a leg with bid missing and ask 0.05 is closed at or below 0.05; a leg with
no ask is still refused.

**T12. Forward report.** Extend `scripts/forward_report.py` with the section 7 paired
improvement, the date-clustered CI, the measured intra-cluster correlation and effective N, fill
and legging rates, the season futility check, and the type-1 data filter. Acceptance: on a
synthetic book with a known improvement the CI covers it at the nominal rate across seeds; rows
with delayed data are excluded from the verdict and counted.

**T13. Reject handling.** A rejected order (status `Inactive`, or an error code on the order)
is logged with its reason and never re-placed under the same order id. The leg is retried once
as a fresh order at the next legal tick schedule (0.05 or 0.10 for non-penny classes). Acceptance:
a fake reject on a 0.01-tick price produces one `reject` row and one fresh order at a 0.05 tick,
and no second reject loop.

**Order.** T1, T3 and T5 first; they are small and close the safety gaps. T2 and T4 next, then
T6, T8 and T9, and T7 alongside. T10 and T11 can go to anyone at any point. T12 must land before
the first season review.

## References

Chan, K., Chung, Y. P. and Johnson, H. (1995). The intraday behavior of bid-ask spreads for
NYSE stocks and CBOE options. *Journal of Financial and Quantitative Analysis* 30(3), 329-346.

Interactive Brokers, market data pricing (OPRA Top of Book L1 fee and commission waiver).
