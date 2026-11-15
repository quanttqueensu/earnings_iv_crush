# Runbook: the paper book

How to set up, run, stop and check the forward paper book. The rules it trades are in
[`FORWARD_TEST_SPEC.md`](FORWARD_TEST_SPEC.md); this file is the operating manual. Everything
here is the Interactive Brokers **paper** account. The harness refuses every live-account port
(7496, 4001, 4003) in code.

## 1. One-time setup

1. **Gateway.** Install IB Gateway (or TWS), log in to the paper account, and in
   Configure > Settings > API: enable socket clients, untick "Read-Only API", note the port
   (Gateway paper 4002, TWS paper 7497). Add 127.0.0.1 to trusted IPs.
2. **Environment.** `pip install -e ".[dev]"`, then copy `.env.example` to `.env` and set
   `FINNHUB_API_KEY` and `SEC_USER_AGENT`. Set `IB_PORT` if the gateway is not on 7497.
3. **Market data.** Without the OPRA top-of-book subscription the account sees quotes 15
   minutes late. The book still runs, but its fills then measure the gap between stale and live
   quotes rather than the spread captured, and count only toward the operational go (spec
   section 11). Every order event records the market-data type in force.
4. **Schedule.** Windows: Task Scheduler runs `scripts\run_paper_daily.ps1` on weekdays at
   15:20 exchange time; untick "Start the task only if the computer is on AC power" and keep the
   machine awake. Linux: `deploy/` runs the same pass in containers from cron (`deploy/README.md`).

## 2. The daily pass

`python -m scripts.paper_trade_ibkr session [--transmit]`, started at 15:20 ET.

| ET | What happens |
|---|---|
| 15:20 | Session guard (closed day or 13:00 early close: skip). Gateway check. Calendar votes from Finnhub, Nasdaq and Yahoo; a name trades only if two agree on date and session. |
| 15:20-15:44 | Due exits are qualified on their stored strike and expiry; a transmitting exit checks the broker holds both short legs. Entries are admitted in hash order up to the cap, priced on the first expiry after the exit date, filtered for ex-dividend dates and sized. The funnel is printed. |
| 15:45-15:55 | One ladder for every leg: rung 0 at mid, then 25%, 50%, 75% of the way to the touch, then the touch. |
| 15:56:30 | Unfilled exit legs re-priced once through the ask; a sweep the broker cancels at its price cap is re-placed once under the cap, after the cancel is confirmed (up to 30 s). Entry orders still resting are cancelled, so their cancels are final before any buy-back. |
| 15:58 | Every working order cancelled; status re-read until the broker confirms the entry cancels (up to 30 s). A legged entry is bought back through the ask. |
| 15:59 | NBBO of every leg recorded, filled or not. Fills booked. |

Without `--transmit`, or without the `_private\TRANSMIT_OK` marker the drivers check, the pass
is a dry run: same clock and prices, every intended order logged with `transmit=False`, nothing
sent, and all stores written under `outputs/live/dry/`.

## 3. Switches

| File | Effect |
|---|---|
| `_private/TRANSMIT_OK` | The drivers pass `--transmit`. Create it only after reading a clean dry run. An agent never creates it. |
| `outputs/live/STOP` | No new entries; exits still run, so the book can always be flattened. Raises an alarm each day it is present. |
| `outputs/live/HALT` | Nothing transmits on any path; working orders are cancelled at the next rung. For incidents in which the ladder itself is suspect. |

## 4. Records

| File | Contents |
|---|---|
| `outputs/live/order_events.csv` | Every order state change, written before the harness acts on it (spec section 6). The primary record. |
| `outputs/live/intended_trades.csv` | Every candidate and admitted event with its decision, reason and outcome, filled or not. |
| `outputs/live/open_positions.parquet` | Open positions, booked from fills. |
| `outputs/live/forward_ledger_nostop.parquet`, `forward_ledger_stop.parquet`, `forward_reconciliation.parquet` | Closed trades in the backtest's ledger schema, with the cost reconciliation. |
| `outputs/live/entry_heartbeat.parquet` | One row per pass: candidates, priced, admitted, entered. |
| `_private/logs/paper_daily_<date>.log` | The driver log (Windows). |

`python -m earnings_iv_crush.ops.orient` reads all of these and the switches. `/book-status` in
Claude Code does the same with commentary.

## 5. When something goes wrong

Any line beginning `ALARM:` makes the driver exit non-zero.

| Alarm | Meaning | Do |
|---|---|---|
| `entry legged_open` | One entry leg filled, the buy-back did not: the account holds a naked leg | Close the leg by hand in TWS at once; record the resolution in the intended-trades log |
| `exit incomplete` | An exit did not fully close even after the 15:56:30 sweep | Check broker positions. The next session's ladder buys back only what is still short, provided the broker's position equals the ledger quantity less the exit fills in the order-event log, and books the exit at the blended price with a `resumed_exit` reason. Until then the account holds a naked leg. If you close it by hand, record it with `reconcile-exit` (below) |
| `exit unfilled; position still open` | No leg of a due exit filled | The straddle is still short, a day past its rule. The next pass retries; check quotes were arriving (see the 10197 row) |
| `exit not placed (broker_mismatch...)` | The broker does not hold the legs the ledger expects, after allowing for earlier exit fills in the order-event log | A leg was closed outside the harness. Record it: `python -m scripts.paper_trade_ibkr reconcile-exit --ticker T --leg P --qty N --price X --reason "..."`. It checks the broker agrees, appends one dated fill row, books the exit when both legs are accounted for, and sends nothing. Never edit the ledger by hand |
| `broker holds ... which no open ledger position explains` | An option position exists that the ledger does not know: a lost entry booking, a leg left by a failed flatten, or a hand trade | Close it in TWS unless it is deliberate; the harness will never exit it |
| `order still working after the ladder, now cancelled` | An order outlived the 15:58 cancel | It has been cancelled; check the order log for a late fill on that contract |
| `market data was cut by a competing live session` | IB error 10197: the paper login lost its quotes because the same user was signed in to live IBKR | Stay signed out of live TWS, web and mobile from 15:15 to 16:00 ET |
| `... booking failed` | An order filled but the ledger write raised | The fills are in the order log; the next pass books a completed exit from them without sending an order |
| `candidates today and none admitted` | Every candidate was filtered or failed to price | Read the funnel; a data or entitlement fault is likely |
| `ladder reached ... after the latest start` | The pass began too late to run the ladder | Nothing was sent; find why the task started late |
| `HALT present` / `STOP present` | A switch is on | Intended, or forgotten? |

No order is ever placed from a monitoring command. A manual close in TWS is recorded in the
intended-trades log with the reason, the same day.

## 6. Known gaps

The specification's tickets not yet built: T6 (the 15:59:30 and 16:15 reconciliation job), T7
(sector map and the 4-per-sector cap), T8 (the full limits with a broker what-if margin check),
T12 (the paired-improvement forward report) and T13 (a single fresh retry after a reject).
Calendar dates use weekday arithmetic, so a position whose exit falls on a market holiday exits
on the next regular session; check positions around holidays. All are on
[`ROADMAP.md`](ROADMAP.md).
