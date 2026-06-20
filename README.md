# Earnings IV-Crush

[![CI](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml)

**Earnings implied-volatility reversion via a filtered cross-sectional vol-crush.**

Short pre-earnings ATM straddles, traded only on names that pass a cross-sectional term-structure
filter, benchmarked against an unfiltered control that sells every straddle.

## Strategy

Sell single-name ATM straddles one to three days before a scheduled earnings announcement and hold
into the post-event implied-volatility collapse, on a $250k Reg-T account. Two gates are evaluated
per event:

1. **Rich implied move.** The market's implied event move is at least **1.20x** a regression-based
   fair move.
2. **Steep term structure.** Front-week minus back-month ATM IV is above the **75th percentile** of
   the name's own trailing 30-day distribution.

Defined-risk iron-fly and short-calendar variants replace the naked straddle in adverse regimes.
The Agent 0 baseline is a random, unfiltered short ATM straddle, used as the control so the gates
are tested against participation rather than against zero.

## Research status

The strategy has been run on real data: 456 megacap events over 2024-2025, priced off Alpaca daily
option bars with IV inverted locally via Black-Scholes, net of an 8% bid-ask spread plus commission
and slippage. All strategy-versus-control comparisons are frequency-neutral (per-trade Sharpe and a
size-matched subsample of the control), which removes the bias that otherwise penalises a selective
filter for trading fewer events.

- **The term gate carries the edge.** Trading the term gate alone (281 trades) is the only arm
  whose size-matched Sharpe difference over the control excludes zero (95% CI **[+0.48, +2.86]**;
  per-trade Sharpe 0.71 vs the control's 0.60).
- **The move gate subtracts value.** Its out-of-sample per-trade Sharpe delta is roughly zero, and
  adding it to the term gate removes good trades for no improvement. The current recommendation is
  to drop it and trade the term gate alone.
- **The edge strengthens at breadth.** Re-run on a 346-name broad universe (525 filtered trades),
  the term-gated book roughly doubles the control's per-trade return at double its Sharpe
  (size-matched 95% CI [+4.24, +8.30]).
- **Structure matters.** Re-booking the term-gated events as a short calendar improves per-trade
  risk-adjusted return over the naked straddle while cutting exposure to the realised move.

Absolute annualised Sharpe levels are not credible: they come from annualising a sparse event-day
return series and from intraday netting. Those inflations apply equally to both books, so the
**relative**, frequency-neutral comparisons are the trustworthy output, not the levels. The data is
free-source only (Alpaca history reaches back to roughly February 2024, with no historical NBBO
quotes), so longer history and live chains are the natural next extensions.

## Repository layout

| Path | Contents |
| --- | --- |
| [`earnings_iv_crush/config.py`](earnings_iv_crush/config.py) | Central `GlobalConfig` / `StrategyConfig`: every tunable parameter in one place |
| [`earnings_iv_crush/data/`](earnings_iv_crush/data/) | Intake facade, providers (Alpaca historical chains, Yahoo calendar, FRED, SEC), pipeline, per-event features, term-spread panel |
| [`earnings_iv_crush/strategy/`](earnings_iv_crush/strategy/) | Fair-move model, the two filters, trade structures (iron fly, calendar), VIX regime selector, strategy book |
| [`earnings_iv_crush/engine/`](earnings_iv_crush/engine/) | Greeks and P&L attribution, cost model, risk and sizing, statistics (Sortino, bootstrap, Deflated Sharpe), backtester, simulator, structured ledger, capital-based equity curves and risk metrics, tearsheet |
| [`earnings_iv_crush/baseline/`](earnings_iv_crush/baseline/) | Agent 0 unfiltered control |
| [`earnings_iv_crush/util/`](earnings_iv_crush/util/) | Shared utilities (progress bar with live ETA) |
| [`scripts/`](scripts/) | Entry points: smoke test, demo backtest, research runner, sensitivity sweep, chain fetcher |
| [`tests/`](tests/) | Test suite (mirrors `earnings_iv_crush/`) |
| [`data/`](data/) | Raw and processed pulls (git-ignored) |

All tunable parameters (account size, costs, the 1.20x / 75th-percentile thresholds, risk limits,
regime cut-offs) live in [`earnings_iv_crush/config.py`](earnings_iv_crush/config.py) as two frozen
dataclasses; the domain modules re-export the individual fields under their established names.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; use source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"       # editable install of the earnings_iv_crush package + dev tools
copy .env.example .env        # then fill in your keys
```

This installs the project as the importable package `earnings_iv_crush`. Pinned runtime
dependencies are also listed in [`requirements.txt`](requirements.txt).

FRED VIX, yfinance equities and yfinance option chains work with no key. The keys in
[`.env.example`](.env.example) unlock the rate-limited or higher-quality providers (Finnhub
earnings calendar, SEC EDGAR user agent, Tiingo, Alpaca historical surfaces). Keys are read by
[`earnings_iv_crush/data/config.py`](earnings_iv_crush/data/config.py); the file is git-ignored and
only key names appear in code.

## Running

```bash
python -m pytest                  # full suite. Live-network tests are deselected
                                  # by default; run them with -m live
python scripts/smoke_test.py      # probe each wired data source (keyless ones return rows,
                                  # keyed ones print SKIP until you add the key)
python scripts/run_backtest.py    # end-to-end demo on synthetic events
python scripts/run_research.py    # enriched synthetic run: net-of-cost strategy vs Agent 0
python scripts/run_research.py --real --term-gate panel \
    --cache outputs/research/events.parquet \
    --term-panel-cache outputs/research/panel.parquet
                                  # real run on Alpaca historical surfaces, with the
                                  # per-name trailing-30-day term gate. A live progress
                                  # bar shows elapsed time and ETA; both caches make
                                  # re-runs instant.
```

`run_research.py` (synthetic, default) validates the harness wiring on a planted-edge event set:
the full cost stack, the significance comparison (bootstrap CI, Deflated Sharpe), the regime
structure mix and the vega/gamma/theta/delta P&L attribution, writing a tearsheet to
`outputs/research/`. **`--real`** swaps in the live pipeline (Yahoo earnings dates, Alpaca
historical chains with locally inverted IV, and the per-name term-spread panel) for a read on real
edge. It needs `ALPACA_KEY`/`ALPACA_SECRET` set and assembles a usable universe of events (use
`--tickers` and a full-year window so the term gate's trailing window warms up).

## Author

Jordan Odorico. Built for QUANTT (Queen's University Algorithmic and Network Trading Team).
