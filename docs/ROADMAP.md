# Roadmap

Every open item, its status and its owner. Update the row in the same commit as the work. An
owner is whoever has said they are doing it; claim an item by putting your GitHub handle in the
Owner column in a pull request. Items are ranked within each section by value per hour.

Status: `open`, `claimed`, `in review`, `done` (remove a done row once its result is recorded in
[`RESEARCH_STATE.md`](RESEARCH_STATE.md) or [`SYSTEM.md`](SYSTEM.md)).

## 1. The paper book (operations outrank research while the book is not trading cleanly)

| ID | Item | Why | Done when | Owner | Status |
|---|---|---|---|---|---|
| B1 | Run the first 20 sessions and record the operational go | No P&L figure from the book means anything before it | 20 consecutive regular sessions, zero reconciliation breaks, 100% lifecycles complete (`order_events.check_completeness`) | | open |
| B2 | T6 reconciliation job: broker positions and executions against the logs at 15:59:30 and 16:15 ET | The go criterion is defined on reconciliation breaks | `scripts/reconcile_broker.py`, breaks file, 20-session counter; fakes for each break kind | | open |
| B3 | T12 forward report: paired improvement over the 15:59 backtest basis, date-clustered CI, effective N, fill and legging rates, type-1 data filter | It is the verdict instrument | `scripts/forward_report.py` extended; synthetic-book coverage test | | open |
| B4 | T13 reject handling: one fresh retry at the next legal tick | Non-penny classes reject 0.01 ticks | fake reject produces one reject row and one retry | | open |
| B5 | T8 full limits: broker what-if margin, stop-at-first-margin-breach, one-contract floor decision | Needed before relaxing the shakedown caps | parametrised boundary tests | | open |
| B6 | T7 sector map for the 346 names from SEC SIC codes; 4-per-sector cap | Same-sector names share one macro gap | every universe ticker maps; unmapped raises | | open |
| B7 | Holiday-aware brackets: replace weekday arithmetic with the NYSE calendar in `trade_dates_for_session` | An exit date on a holiday shifts the hold | test across Thanksgiving and Good Friday | | open |
| B8 | Move the pass to the cloud host in `deploy/` | A laptop on battery or asleep misses sessions | 10 sessions run unattended | | open |
| B9 | Decide on the OPRA real-time subscription (USD 1.50 a month on the linked live account) | Delayed-data fills are not P&L evidence | decision recorded in `decisions/` | team lead | open |

## 2. Research

| ID | Item | Why | First step | Owner | Status |
|---|---|---|---|---|---|
| R1 | Residual-value selector, new candidates | The one scoring approach aimed at mispricing rather than size; one test so far | Pre-register up to three causal candidates (for example a hierarchical per-name jump-size estimate, implied over causal realised move) scored on residual value, discovery 2019-24, validation 2013-18 | | open |
| R2 | Exit-only maker as its own hypothesis | Exit spreads are 2.4 times entry; the exit arm was the larger split in the F1 study | Pre-register on the cmbp-1 flow data already on disk; markout gate as in F1 | | open |
| R3 | Stale entry-spot repair on the megacap panel | 16.9% of events fall back one session; any new megacap result must use the repaired file | Rebuild the event file with a funnel on every fail-soft lookup, then a capped re-mark | | open |
| R4 | One trial-count ledger file | The record's two estimates disagree (about 1,506 and 1,532) | Reconstruct from the hash records and findings into `research/TRIALS.csv` with a test that it matches every record | | open |
| R5 | Advanced earnings dates, forward | Advanced dates beat on-time by +2.24% [+0.32%, +4.12%] on 174 events, a secondary result | Record the date-shift flag on every forward-book entry and test once the forward sample allows | | open |
| R6 | OptionMetrics access | Unlocks historical surfaces and open interest | Ask the R2 mirror maintainer whether `optionm_all` is licensed | team lead | open |

## 3. Team and data

| ID | Item | Owner | Status |
|---|---|---|---|
| D1 | Upload the research caches to the club R2 bucket (`python -m earnings_iv_crush.data.sync push`) and add the bucket name to `.env.example` | team lead with the mirror maintainer | open |
| D2 | Rotate the Databento API key at the portal | team lead | open |
