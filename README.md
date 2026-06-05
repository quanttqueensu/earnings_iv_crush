# Earnings IV-Crush

**Earnings Implied Volatility Reversion via Filtered Cross-Sectional Vol-Crush**.

Short pre-earnings ATM straddles, traded only on names that pass a two-part cross-sectional
filter.

## Strategy

Sell single-name ATM straddles 1 to 3 days before an earnings announcement and hold into the
post-event implied-volatility collapse, on a $250k Reg-T account. An event is traded only when it
passes **both** gates:

1. **Rich implied move.** The market's implied event move is at least **1.20x** a regression-based
   fair move.
2. **Steep term structure.** Front-week minus back-month ATM IV is above the **75th percentile** of
   its trailing 30-day distribution.

Variants: iron fly when VIX > 25, calendar when the term structure dominates. The Agent 0 baseline
is a random, unfiltered short ATM straddle, used as the control.

### Why the edge exists

The naive sell-every-straddle trade does not survive costs (Khan & Khan 2024). The source of edge
is the cross-sectional filter (Cremers / Halling / Weinbaum), which closes a gap none of the cited
papers test directly. Demonstrating that the filtered book beats the unfiltered Agent 0 control,
net of costs, is the whole point of the project.

## Repository layout

| Path | Contents |
| --- | --- |
| [`src/config.py`](src/config.py) | Central `GlobalConfig` / `StrategyConfig` — every tunable parameter in one place |
| [`src/data/`](src/data/) | Intake facade, providers (Alpaca historical chains, Yahoo calendar, FRED, SEC), pipeline, per-event features, term-spread panel |
| [`src/strategy/`](src/strategy/) | Fair-move model, the two filters, trade structures (iron fly, calendar), VIX regime selector, strategy book |
| [`src/engine/`](src/engine/) | Greeks and P&L attribution, cost model, risk and sizing, statistics (Sortino, bootstrap, Deflated Sharpe), backtester, simulator, tearsheet |
| [`src/baseline/`](src/baseline/) | Agent 0 unfiltered control |
| [`src/util/`](src/util/) | Shared utilities (progress bar with live ETA) |
| [`scripts/`](scripts/) | Smoke test, demo backtest, enriched research runner |
| [`tests/`](tests/) | Test suite (mirrors `src/`) |
| [`data/`](data/) | Raw and processed pulls (git-ignored) |

All tunable parameters (account size, costs, the 1.20x / 75th-percentile filter thresholds, risk
limits, regime cut-offs) live in [`src/config.py`](src/config.py) as two frozen dataclasses; the
domain modules re-export the individual fields under their established names.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; use source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # then fill in your keys
```

FRED VIX, yfinance equities and yfinance option chains work with no key. The keys in
[`.env.example`](.env.example) unlock the rate-limited or higher-quality providers (Finnhub
earnings calendar, SEC EDGAR user agent, Tiingo, Alpaca historical surfaces). Keys are read by
[`src/data/config.py`](src/data/config.py); the file is git-ignored and only key names appear in
code.

## Running

```bash
python -m pytest                  # full suite. Live-network tests are deselected
                                  # by default; run them with -m live
python scripts/smoke_test.py      # probe each wired data source (keyless ones return rows,
                                  # keyed ones print SKIP until you add the key)
python scripts/run_backtest.py    # end-to-end demo on SYNTHETIC events
python scripts/run_research.py    # enriched SYNTHETIC run: net-of-cost strategy vs Agent 0
python scripts/run_research.py --real --term-gate panel \
    --cache outputs/research/events.parquet \
    --term-panel-cache outputs/research/panel.parquet
                                  # REAL run on Alpaca historical surfaces, with the
                                  # spec-faithful per-name trailing-30-day term gate.
                                  # A live progress bar shows elapsed time and ETA;
                                  # both caches make re-runs instant.
```

`run_research.py` (synthetic, default) validates the harness wiring on a planted-edge event set:
the full cost stack, the significance comparison (bootstrap CI, Deflated Sharpe), the regime
structure mix and the vega/gamma/theta/delta P&L attribution, writing a tearsheet to
`outputs/research/`. **`--real`** swaps in the live pipeline — Yahoo earnings dates, Alpaca
historical chains with locally inverted IV, and the per-name term-spread panel — for the first read
on real edge. It needs `ALPACA_KEY`/`ALPACA_SECRET` set and assembles a usable universe of events
(use `--tickers` and a full-year window so the term gate's trailing window warms up).

## Status

Code is green on synthetic data: the harness, filters, fair-move model, backtester and Agent 0
control all run and are tested. The engine now models the economics the thesis depends on:

- **Costs.** A configurable cost model (commission, exchange fee, bid-ask spread, slippage) books
  net-of-cost P&L, so the "filtered beats unfiltered net of costs" claim is testable rather than
  assumed.
- **Significance.** Sortino, profit factor, win/loss, drawdown duration, bootstrap Sharpe CIs, the
  Probabilistic and Deflated Sharpe ratios (the latter penalising filter-threshold selection bias),
  and a paired strategy-vs-control test.
- **Attribution.** Full Greeks and a vega/gamma/theta/delta decomposition of realised P&L, plus the
  once-at-close delta hedge, showing the edge is the vega (crush) leg.
- **Structures and regime.** Iron-fly and calendar variants, selected per event from the VIX level
  and term-structure premium, and routed through the structured ledger (`engine/structured_ledger.py`)
  so each variant books its own economics rather than falling back to the naked straddle.
- **Risk.** 1% NAV worst-case sizing, the 3x-premium stop, a 15% portfolio circuit breaker, and
  concentration caps by ticker and sector.
- **Fair-move model depth.** Fit diagnostics (R-squared, t-statistics), an optional ridge variant,
  and out-of-sample walk-forward evaluation.
- **Real data.** A `--real` pipeline assembles events from Alpaca's free historical option data
  (IV inverted locally via Black-Scholes), Yahoo earnings dates and FRED VIX. The term gate uses
  the spec's per-name trailing-30-day percentile from a daily surface panel.

Outstanding work before the readiness review:

- Real option data is Alpaca-free (daily closes back to ~Feb 2024, IV derived locally; no historical
  NBBO quotes). OptionMetrics/IvyDB via WRDS (clean 2020–2025 single-name surfaces) and a brokerage
  account for live chains are still pending a faculty sponsor.
- The fair-move model fits on the chain/price features available today; `eps_dispersion` (IBES/WRDS)
  and `oi_growth` (historical OI) come online with those sources.

## Attribution

Jordan Odorico, for QUANTT (Queen's University Algorithmic Network and Trading Team).
