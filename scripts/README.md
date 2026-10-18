# Scripts

Stable entry points. Run them from the repository root; each docstring carries its full usage.
Closed research studies live under [`../research/`](../research/README.md), not here.

## No credentials, no cache

| Script | What it does |
|---|---|
| `demo_pipeline.py` | The whole valuation and scoring path on synthetic events. The day-one check. |
| `run_research.py` | The end-to-end research run against the unconditional control; synthetic by default, `--real` uses live sources. |
| `run_backtest.py` | A small backtest demo: filtered strategy against the control. |
| `run_sensitivity.py` | Filter-threshold sensitivity sweep with a walk-forward check. |

## Needs the research cache (`python -m earnings_iv_crush.data.sync pull`)

| Script | What it does |
|---|---|
| `validate_screen.py` | Rebuilds the twelve-year book and checks it reproduces N=391 and the frozen per-trade Sharpe. The fastest integrity check. |
| `make_summer_story_figures.py` | Renders the figure set used in the summer documents. |

## Needs keys

| Script | What it does |
|---|---|
| `smoke_test.py` | Pulls one small sample from each wired data source. |

## The paper book (IB paper gateway)

| Script | What it does |
|---|---|
| `paper_trade_ibkr.py` | `session` is the daily pass (run as `python -m scripts.paper_trade_ibkr session`); `enter` previews, `exit` and `forward-exit` are manual tools. Dry run unless `--transmit`. See [`../docs/RUNBOOK.md`](../docs/RUNBOOK.md). |
| `run_paper_daily.ps1` | Windows Task Scheduler driver, 15:20 ET on weekdays. |
| `forward_report.py` | Significance report for the forward book. |
| `sweep_term_panel.py` | Accrues the term-spread panel the legacy `term_q80` rule reads. |
| `live_quote_snapshot.py` | Snapshots live paper-account quotes on megacap straddles. |
| `ib_margin_probe.py` | Compares modelled Reg-T margin with what the broker charges. |
| `ibkr_slippage.py` | Samples quoted option slippage from the TWS API. |

## Data builders: `build/`

Several are **metered** (Databento): they price the request first and take a hard `--cap` in
dollars. Never run one without the team lead's agreed budget ([`../docs/DATA.md`](../docs/DATA.md)).

| Script | What it does |
|---|---|
| `build/build_calendar.py` | Historical earnings calendar from free sources, cross-checked against SEC filings. |
| `build/build_wrds_events.py` | Calendar with before-open or after-close session from the WRDS mirror. |
| `build/build_event_panel.py` | Point-in-time earnings-event panel from the WRDS mirror. |
| `build/wrds_vs_databento_events.py` | Reconciles the WRDS calendar against the Databento and Finnhub one. |
| `build/build_databento_calendar.py` | Calendar for the Databento backtest. |
| `build/build_databento_events.py` | Reconstructs events from OPRA daily chains. Metered. |
| `build/build_oos_events.py` | Rebuilds the event set from cached Databento chains only (no spend). |
| `build/build_quote_marked_chains.py` | Re-marks the megacap book on consolidated quotes. Metered. |
| `build/build_quote_events_2013_2018.py` | Extends the book back to 2013 on quote marks. Metered. |
| `build/build_broad_oos_2025.py` | Prices the 2025-26 broad-universe block. Metered. |
| `build/pull_broad_history.py` | 15:59 chains for the broad universe, 2013-2024. Metered. |
| `build/build_broad_history_events.py` | Features and outcomes for the broad 2013-2024 events. |
| `build/remark_cbbo.py` | Re-marks each event's straddle on one-minute consolidated quotes. Metered. |
| `build/measure_spread.py` | Measures the real at-the-money round-trip spread. Metered. |
| `build/fetch_chains.py` | Pre-warms the option-chain cache for a universe. |
