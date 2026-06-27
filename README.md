# Earnings IV-Crush

[![CI](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml)

**Harvesting the post-earnings implied-volatility crush with a filtered cross-sectional short straddle.**

Short pre-earnings ATM straddles, traded only on names that pass two cross-sectional gates,
benchmarked against an unfiltered control that sells every straddle. The edge comes from
*selection*, not from blanket selling: the average earnings straddle is roughly fairly priced
net of costs, so the strategy trades only the subset of events where the event premium is
measurably rich.

## Strategy

Sell single-name ATM straddles one day before a scheduled earnings announcement and hold into
the post-event implied-volatility collapse, on a $250k Reg-T account. Enter at the
pre-announcement close; exit one daily close after the print, marked on live time value rather
than intrinsic settlement. Two gates decide whether an event is traded:

1. **Term gate.** The front-week-minus-back-month ATM IV term spread sits at or above the
   **75th percentile** of an expanding, backward-looking cross-sectional distribution built
   from strictly earlier events. A steep front-week structure is the market's statement that
   the event is unusually feared.
2. **Move gate.** The option-implied event move is at least **1.20x** a regression fair move
   estimated walk-forward from the underlying's history. This keeps only events whose priced
   move looks rich against a statistical baseline.

A 25-delta skew gate was tested and **rejected** (it removes trades without improving the
Sharpe). Defined-risk iron-fly and short-calendar variants replace the naked straddle in
adverse regimes. The **Agent 0** baseline is an unfiltered short ATM straddle, used as the
control so the gates are tested against participation rather than against zero.

## Research status

The strategy has been run on a genuine multi-year out-of-sample sample: **1,051 earnings events
across 45 mega-cap names over 2019-2024**, priced off Databento OPRA daily option bars with IV
inverted locally via Black-Scholes, and **every trade marked on its real two-leg straddle
closes** (call close plus put close, at entry and exit). All strategy-versus-control comparisons
are frequency-neutral (per-trade Sharpe and a size-matched control subsample), which removes the
bias that otherwise penalises a selective filter for trading fewer events.

- **The edge is the term gate overlaid with the move gate.** At a central cost assumption
  (a 4% quoted spread crossed at the half, ~2% round-trip), the **term+move** book returns an
  annualised Sharpe of **+2.04** (137 trades, win rate 73.8%, positive in all six years),
  against an unfiltered control that is **negative net of cost** (-0.82). The move gate earns
  its place *conditional on the term gate*: it concentrates the book into a smaller, richer
  subset.
- **The skew gate is rejected.** Term+skew is worse than term alone; term+skew+move buys a
  marginal Sharpe gain over term+move only by halving the sample, so it is dropped in favour
  of the larger, simpler book.
- **The result is a plateau, not a lucky cut.** Sweeping the term percentile over
  {0.70, 0.75, 0.80} and the move ratio over {1.10, 1.20, 1.30} leaves the per-trade Sharpe
  positive in all nine cells (+0.106 to +0.161).
- **The cost is measured, not assumed.** The consolidated closing NBBO spread on these straddle
  legs is **5.9%** (median, IQR [4.2%, 12.5%]). Under realistic half-spread execution this puts
  the honest annualised Sharpe near **+1.6**; the clean Sharpe-2 figure holds only under the
  more optimistic 2% round-trip assumption. The edge survives to roughly a 6% round-trip cost.

The honest state of the evidence: the point estimate is firm and positive every year, but with
137 trades on one mega-cap universe the bootstrap 95% interval still grazes zero
([-0.033, +0.410] per trade). The remaining work is confirmatory: a broad-universe replication
on the multi-year source and a forward paper test that converts a backtest costed off closing
quotes into observed fills. The full account, with figures, is in
[`paper/iv_crush_main.tex`](paper/iv_crush_main.tex) and
[`docs/methodology_and_results.md`](docs/methodology_and_results.md).

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
| [`paper/`](paper/) | The research paper and figures |
| [`tests/`](tests/) | Test suite (mirrors `earnings_iv_crush/`) |
| [`data/`](data/) | Raw and processed pulls (git-ignored) |

All tunable parameters (account size, costs, the 1.20x / 75th-percentile thresholds, risk
limits, regime cut-offs) live in [`earnings_iv_crush/config.py`](earnings_iv_crush/config.py) as
two frozen dataclasses; the domain modules re-export the individual fields under their
established names.

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
through the metered OPRA pipeline and documented end to end in the paper and methodology
document; raw pulls and generated outputs are git-ignored.

`scripts/paper_trade_ibkr.py` drives the IBKR paper harness against a running TWS/IB Gateway,
the natural next evidence step and the forward test the paper calls for.

## Author

Jordan Odorico. Built for QUANTT (Queen's University Algorithmic and Network Trading Team).
