# Earnings IV-Crush

[![CI](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml)

**Harvesting the post-earnings implied-volatility crush with a filtered cross-sectional short straddle.**

Short pre-earnings ATM straddles, traded only on names that pass a cross-sectional term gate,
benchmarked against an unfiltered control that sells every straddle. The edge comes from
*selection*, not from blanket selling: the average earnings straddle is roughly fairly priced
net of costs, so the strategy trades only the subset of events where the event premium is
measurably rich.

## Strategy

Sell single-name ATM straddles one day before a scheduled earnings announcement and hold into
the post-event implied-volatility collapse, on a $250k Reg-T account. Enter at the
pre-announcement close; exit one daily close after the print, marked on live time value rather
than intrinsic settlement. A single cross-sectional gate decides whether an event is traded:

1. **Term gate.** The front-week-minus-back-month ATM IV term spread sits at or above the
   **80th percentile** of an expanding, backward-looking cross-sectional distribution built
   from strictly earlier events. A steep front-week structure is the market's statement that
   the event is unusually feared. The 80th percentile is an interior stable node: neighbouring
   cut-offs from the 78th to the 82nd percentile sit within about 0.01 of its per-trade Sharpe,
   and the sharper 85th-percentile reading is an overfit spike rather than a higher plateau.

Two further gates were tested and **rejected**. A 25-delta skew gate removes trades without
improving the Sharpe. A move gate (the option-implied event move rich against a walk-forward
fair move) looked additive in sample but fails its own out-of-sample test, so it is not part of
the live book. The vehicle is the **naked short straddle**: defined-risk iron-fly (1.5x wings)
and short-calendar variants were tested on real option chains and are net-negative, so they do
not replace the straddle. A hard stop near -0.30 of margin is the only tail lever that helps,
and even it caps the single-name earnings tail without creating edge. The **Agent 0** baseline
is an unfiltered short ATM straddle, used as the control so the gate is tested against
participation rather than against zero.

## Research status

The strategy has been run on a genuine multi-year out-of-sample sample: **1,051 earnings events
across 45 mega-cap names over 2019-2024**, priced off Databento OPRA daily option bars with IV
inverted locally via Black-Scholes, and **every trade marked on its real two-leg straddle
closes** (call close plus put close, at entry and exit). All strategy-versus-control comparisons
are frequency-neutral (per-trade Sharpe and a size-matched control subsample), which removes the
bias that otherwise penalises a selective filter for trading fewer events.

- **The live book is the term gate at the 80th percentile, term-only.** On the full 2019-2024
  sample it places **192 trades** (about 34 per year) at a per-trade frequency-neutral Sharpe of
  **+0.12** (mean return on margin over its standard deviation), win rate 67.7%, with a bootstrap
  95% interval of **[-0.023, +0.315] that runs through zero**. On the 2019-2023 out-of-sample
  window the figures are 153 trades, per-trade Sharpe +0.12, interval [-0.041, +0.363]. The
  unfiltered control is negative net of cost.
- **Statistical significance is not established.** The Probabilistic Sharpe Ratio against zero is
  0.91 (full) / 0.89 (out-of-sample), below the 0.95 bar, and the Deflated Sharpe Ratio is below
  0.5 under every trial-count assumption (0.42 at the most generous, falling toward zero as the
  search space widens). Every bootstrap interval grazes zero. The honest verdict is directionally
  positive but not statistically significant, pending a forward paper test.
- **The edge lives in execution, not in the annualisation.** The book trades about 34 times a
  year, so the defensible annualisation factor is √(trades/yr) ≈ 5.8, not √252 ≈ 15.9; the latter
  inflates the per-trade Sharpe roughly threefold. The honest annualised Sharpe is about **0 if the
  spread is crossed on exit and at most +0.68** with disciplined mid-seeking fills. The whole edge
  is execution quality, not the signal.
- **The cost is measured and asymmetric.** Mean half-cross execution on the gated straddle legs is
  about **3.07% of premium at entry and about 8.55% at exit**, an **11.6% round-trip break-even**.
  The exit leg is the wider one, not a symmetric 5.9% on both sides. Crossing the full quoted
  spread takes the edge to zero; only patient mid-seeking exits preserve it.
- **The skew gate is rejected**, and the move gate is dropped on its out-of-sample failure, so the
  live book is the larger, simpler term-only structure.

The honest state of the evidence: the point estimate is positive across the sample, but with 192
trades on one mega-cap universe and every bootstrap interval through zero it is not separated from
zero at 95%. The result is directionally positive but not statistically significant. The remaining
work is confirmatory: a broad-universe replication on the multi-year source and a forward paper
test (built at [`earnings_iv_crush/live/forward_test.py`](earnings_iv_crush/live/forward_test.py))
that converts a backtest costed off closing quotes into observed fills.

## Repository layout

| Path | Contents |
| --- | --- |
| [`earnings_iv_crush/config.py`](earnings_iv_crush/config.py) | Central `GlobalConfig` / `StrategyConfig`: every tunable parameter in one place |
| [`earnings_iv_crush/data/`](earnings_iv_crush/data/) | Intake facade and providers (Databento OPRA chains, Alpaca surfaces, earnings calendar, FRED VIX, SEC, GICS sectors), pipeline, per-event features, term-spread panel |
| [`earnings_iv_crush/strategy/`](earnings_iv_crush/strategy/) | Fair-move model, the two gates, trade structures (iron fly, calendar), VIX regime selector, strategy book |
| [`earnings_iv_crush/engine/`](earnings_iv_crush/engine/) | Greeks and P&L attribution, cost model, risk and sizing, statistics (Sortino, bootstrap, Deflated Sharpe), backtester, simulator, structured ledger, capital-based equity curves, tearsheet |
| [`earnings_iv_crush/baseline/`](earnings_iv_crush/baseline/) | Agent 0 unfiltered control |
| [`earnings_iv_crush/live/`](earnings_iv_crush/live/) | IBKR paper-trading harness (connection, market data, orders, paper book) |
| [`scripts/`](scripts/) | Entry points: smoke test, demo backtest, research runner, sensitivity sweep, chain fetcher, IBKR paper trade |
| [`tests/`](tests/) | Test suite (mirrors `earnings_iv_crush/`) |
| [`data/`](data/) | Raw and processed pulls (git-ignored) |

All tunable parameters (account size, costs, the 80th-percentile term-only threshold with the
move gate disabled, risk limits, regime cut-offs) live in
[`earnings_iv_crush/config.py`](earnings_iv_crush/config.py) as two frozen dataclasses; the
domain modules re-export the individual fields under their established names.

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
earnings calendar, SEC EDGAR user agent, Tiingo, Alpaca historical surfaces, and the Databento
OPRA chains that produce the headline study). Keys are read by
[`earnings_iv_crush/data/config.py`](earnings_iv_crush/data/config.py); the file is git-ignored
and only key names appear in code.

## Running

```bash
python -m pytest                  # full suite. Live-network tests are deselected
                                  # by default; run them with -m live
python scripts/smoke_test.py      # probe each wired data source (keyless ones return rows,
                                  # keyed ones print SKIP until you add the key)
python scripts/run_backtest.py    # end-to-end demo on synthetic events
python scripts/run_research.py    # enriched synthetic run: net-of-cost strategy vs Agent 0
```

`run_research.py` (synthetic, default) validates the harness wiring on a planted-edge event set:
the full cost stack, the significance comparison (bootstrap CI, Deflated Sharpe), the regime
structure mix and the vega/gamma/theta/delta P&L attribution, writing a tearsheet to
`outputs/research/`. **`--real`** swaps in the live pipeline (earnings dates, historical chains
with locally inverted IV, and the per-name term-spread panel) for a read on real edge.

The multi-year, market-marked Databento study behind the **Research status** numbers is run
through the metered OPRA pipeline; raw pulls and generated outputs are git-ignored.

`scripts/paper_trade_ibkr.py` drives the IBKR paper harness against a running TWS/IB Gateway,
the natural next evidence step and the forward test the strategy calls for.

## Author

Jordan Odorico. Built for QUANTT (Queen's University Algorithmic and Network Trading Team).
