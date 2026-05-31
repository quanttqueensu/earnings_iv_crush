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
| [`src/data/`](src/data/) | Data intake facade, pipeline, per-event features |
| [`src/strategy/`](src/strategy/) | Fair-move model, the two filters, trade structures (iron fly, calendar), VIX regime selector, strategy book |
| [`src/engine/`](src/engine/) | Greeks and P&L attribution, cost model, risk and sizing, statistics (Sortino, bootstrap, Deflated Sharpe), backtester, simulator, tearsheet |
| [`src/baseline/`](src/baseline/) | Agent 0 unfiltered control |
| [`scripts/`](scripts/) | Smoke test, demo backtest, enriched research runner |
| [`tests/`](tests/) | Test suite (mirrors `src/`) |
| [`data/`](data/) | Raw and processed pulls (git-ignored) |

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
python -m pytest                  # full suite (156 tests). Live-network tests are
                                  # deselected by default; run them with -m live
python scripts/smoke_test.py      # probe each wired data source (keyless ones return rows,
                                  # keyed ones print SKIP until you add the key)
python scripts/run_backtest.py    # end-to-end demo on SYNTHETIC events
python scripts/run_research.py    # enriched run: net-of-cost strategy vs Agent 0, significance,
                                  # regime structure mix, P&L attribution, and a tearsheet
```

`run_backtest.py` runs the core chain (fit fair-move model, apply both filters, book the ledger,
score against Agent 0) on a synthetic event set with a planted edge. `run_research.py` adds the
full cost stack, the significance comparison (bootstrap CI, Deflated Sharpe), the regime structure
mix and the vega/gamma/theta/delta P&L attribution, writing a tearsheet to `outputs/research/`.
Both validate the harness wiring. **Neither is evidence of real edge:** that needs historical
option surfaces.

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
  and term-structure premium (VIX is now consumed).
- **Risk.** 1% NAV worst-case sizing, the 3x-premium stop, a 15% portfolio circuit breaker, and
  concentration caps by ticker and sector.
- **Fair-move model depth.** Fit diagnostics (R-squared, t-statistics), an optional ridge variant,
  and out-of-sample walk-forward evaluation.

Outstanding work before the readiness review:

- No real historical option surfaces collected yet. Alpaca keys are unset; OptionMetrics/IvyDB via
  WRDS and a brokerage account for live chains are pending.
- The fair-move model still fits on two of its five features on live data; `eps_dispersion`
  (IBES/WRDS) and `oi_growth` (historical OI) come online with those sources.
- The trade-structure variants are priced and regime-selected but not yet routed through the
  production ledger and backtester (the booked economics remain the naked straddle).

### Checkpoints

| Date | Deliverable |
| --- | --- |
| 31 May | Charter |
| 30 June | Pipeline + Agent 0 + crude backtest |
| 31 July | Walk-forward + sensitivity analysis |
| 22 August | Readiness review |

## Attribution

Jordan Odorico, for QUANTT (Queen's University Algorithmic Network and Trading Team).
