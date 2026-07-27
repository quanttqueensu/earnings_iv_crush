# Earnings IV-Crush

[![CI](https://github.com/jordanodorico/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/jordanodorico/earnings_iv_crush/actions/workflows/ci.yml)

**A quote-marked test of whether the post-earnings volatility crush can be harvested, and the
event-study and execution-measurement engine built to settle it.**

## The finding

The earnings volatility crush is real, large, and correctly attributed. Implied volatility falls
on **98.1% of 989 events**, with a mean at-the-money decline of **0.4865 vol points**, and a Greek
decomposition confirms the position's profit is carried by vega rather than theta under both
attribution orderings. That is the mechanism the strategy claims, and it holds.

The crush is nonetheless **not monetisable at the observed scale**. A term-structure-gated short
straddle returns a per-trade Sharpe of **+0.1173** over 2019-2024 (N = 198, one-sided p = 0.050),
but the same machinery run backwards over 2013-2018 returns **-0.0053** (N = 193, p = 0.530).
Pooled, the sample reaches **N = 391**, past the 356 trades the pre-registered power calculation
demanded, and the estimate is **+0.0560** with a clustered 95% confidence interval of
**[-0.0421, +0.1803]**. Deflated against the **1,476 configurations actually searched**, the
Deflated Sharpe Ratio is **0.0001**.

The honest reading is that the original positive result is consistent with selection over a large
specification search rather than a persistent edge. The premium is not larger than the gap risk
borne to collect it, which is what an efficiently priced announcement should look like. That is a
finding about the market, not a failure of the test.

**All Sharpe figures on this page are per-trade.** The book trades roughly 34 times a year, so the
defensible annualisation factor is √(trades/yr) ≈ 5.8, not √252 ≈ 15.9; the latter inflates the
per-trade figure roughly threefold. An earlier version of this project made exactly that error, and
the regression test that now prevents it lives in
[`tests/engine/test_annualisation_regressions.py`](tests/engine/test_annualisation_regressions.py).

## What was tested

Short a one-overnight at-the-money straddle on a large-cap US equity immediately before a scheduled
earnings announcement, closed the following session, on a $250k Reg-T account. The unconditional
version of that trade is roughly fairly priced net of costs, which is the established result and the
project's null. Any edge therefore has to come from selection.

The selector is the **term gate**: enter only when the front-week-minus-back-month at-the-money IV
term spread sits at or above the 80th percentile of an expanding, backward-looking cross-sectional
distribution built from strictly earlier events. The economic claim is that a steep front confirms
the premium is concentrated in the event itself, so what is sold is genuinely event variance rather
than a level of volatility that persists after the print.

Everything is scored against an unfiltered control (**Agent 0**) that trades the identical economics
on every event, so the gate is tested against participation rather than against zero. Beating zero by
declining to trade is trivial. All comparisons are frequency-neutral, using per-trade Sharpe and a
size-matched control subsample, which removes the bias that otherwise penalises a selective filter
for trading fewer events.

Two further gates were tested and **rejected**: a 25-delta skew gate removes trades without improving
the Sharpe, and a move gate looked additive in sample but fails its own out-of-sample test. The
vehicle is the naked short straddle; defined-risk iron-fly (1.5x wings) and short-calendar variants
were tested on real chains and are net-negative. The single-name earnings tail cannot be capped by a
live stop, because the book holds one overnight and the single post-entry mark already sits on the
far side of the gap, leaving a stop order no intraday mark to fire against. A pre-paid protective
wing is fairly priced and costs more than the tail it removes, so the tail is handled by sizing.

## Evidence

### Execution was measured, not assumed

The obvious objection to a marginal net result is that the cost model is wrong. It was therefore
measured directly rather than argued about: **34,672 trade prints** were located inside their
prevailing consolidated spreads. Median price improvement is **zero**, **54% of prints pay the full
touch**, and rescoring the book on measured rather than assumed spreads moves the pooled Sharpe from
+0.0560 to **+0.0629**, worth roughly seven thousandths of Sharpe and leaving the interval across
zero. Execution is not the missing lever.

One measurement trap is worth recording, because it inverts the conclusion if missed.
Trade-conditional spreads look 2.35x tighter than the fixed-time book, but that is a selection
artefact: trades cluster where the book is already tight, and a strategy that acts at a fixed time
cannot select into those moments. Scoring on it is the highest-Sharpe reading available and is
invalid.

### Cross-market replication is negative

The gate was ported to two free historical single-name option panels to ask whether the effect is
structural or specific to US microstructure. Adding a market costs one adapter plus an earnings
calendar, because the chain fetcher is an injected dependency.

- **India (NSE) is the decisive test and it is negative.** Over 120 names and 960 events, gross
  return-on-margin is negative at every threshold from the 50th to the 95th percentile; the least-bad
  cell is roughly -0.4% **gross**, before any cost exists. The result is invariant across the top-30,
  91-name and 120-name panels. There is no execution assumption that rescues a negative gross edge.
- **Brazil (B3) has a gross signal that is uninvestable.** Over 61 trades the gate is positive gross
  (+6.4% total return, 68.9% hit rate, +2.1% return-on-margin) and beats the control on every
  frequency-neutral read. COTAHIST bid-ask on these names runs around **24%**, the round-trip drag is
  13.4% of total return, and the book flips to -7.0% total and -2.4% return-on-margin. The tradeable
  single-name cross-section is five to fifteen heavily correlated names, so the effective number of
  independent bets collapses.

The three markets are the three canonical ways a backtest edge dies: no signal at all (India), a
signal entirely inside the spread (Brazil), and a signal that survives costs but not statistics (US).

### Risk shape

Maximum drawdown is **$24,300, or 9.4 times the annualised profit**, and the entire pooled result
rests on two calendar years. Even taking the point estimate at face value, that is not an allocable
risk profile.

## Limitations

Stated rather than buried, because they change how the result should be read.

- **Survivorship bias, and it favours the strategy.** The universe is today's mega-caps carried
  backwards; 2013 membership was not knowable and firms that fell out are absent by construction.
  Correcting it with point-in-time reconstitution would be expected to make the negative result more
  negative. For this reason the backward extension should not be described as a clean out-of-sample
  test: it is the same selection applied to more history.
- **Session asymmetry between blocks.** The extension snaps entry and exit onto real trading sessions
  and so retains 24 Berkshire events the 2019-2024 build silently dropped. Pooling is defensible only
  with that stated.
- **Unresolved exit inversions.** 61 events in the extension block, 5.4% of it, could not invert an
  exit implied volatility and were marked at entry IV, booking no crush. The bias is mildly downward.
- **Cost measurement is regime-local.** The execution study reaches only 2023-2024 across 81 events
  and 27 names. Single-name option spreads tightened materially over the decade, so transferring it
  backwards flatters the early block. No market impact and no assignment risk are modelled.
- **Metered data spend** was capped at $100 and came to approximately **$26.70** all-in.

## What this does not settle

The negative result closes one specification, not the question. The lines that remain open, and that
the machinery in this repository exists to run:

1. **Is the mechanism tradeable as relative value rather than outright?** The gate demonstrably
   forecasts the size of the crush without forecasting reward. A signal with predictive power on the
   dependent variable but not on the risk-adjusted return is the standard setup for a cross-sectional
   long-short, which this study never tested: it only ever ran an outright short-volatility book.
2. **Does the trade pay anywhere the idiosyncratic gap is smaller?** The finding is that announcement
   premium compensates announcement gap risk at roughly fair value in single names. Aggregate
   earnings-season volatility exposure carries the same crush with a materially thinner single-name
   gap, which is a different risk-premium question rather than a rerun of this one.
3. **What does the term structure actually price?** The gate carries information about event risk in
   every market examined. Characterising what it forecasts, as an event-study object in its own
   right, is a cleaner question than whether a straddle monetises it, and the
   [`engine/event_study.py`](earnings_iv_crush/engine/event_study.py) and
   [`data/wrds_panel.py`](earnings_iv_crush/data/wrds_panel.py) machinery was built for it.
4. **Point-in-time universe reconstitution.** The single largest known bias in the current result,
   and the one improvement that would make the twelve-year sample genuinely clean.

Two candidate explanations for the weak result are closed and should not be reopened: a larger
sample, which arrived and did not change the verdict, and better execution, which was measured
directly and is worth roughly 0.007 of per-trade Sharpe.

## What is reusable here

Independent of the verdict, the repository is a working event-study and execution-measurement stack:

- A **market-agnostic backtest engine**: the term gate, surface maths, cost model and significance
  stack all run off a canonical chain schema and a `ticker, announce_date, session` calendar, so a
  new market is one adapter plus a calendar.
- **Chain adapters behind a market registry** (Databento OPRA daily bars and consolidated BBO, NSE
  bhavcopy, B3 COTAHIST, LSE, Alpaca), with a corporate-action overnight-move guard and a
  checkpointing panel builder.
- **Quote-aware marking** that survives per-contract staleness, plus the diagnostics that catch it.
- A **significance stack** with bootstrap and block-bootstrap intervals, Probabilistic and Deflated
  Sharpe, and cluster-robust standard errors.
- A **point-in-time event panel** from IBES/CRSP/Fama-French, with Fama-French-Carhart alpha and
  delisting-aware cumulative abnormal returns.
- **544 tests**, including regression guards on the three errors that previously produced false
  positives: annualisation basis, term-gate look-ahead, and trade-conditional spread selection.

## Repository layout

| Path | Contents |
| --- | --- |
| [`earnings_iv_crush/config.py`](earnings_iv_crush/config.py) | Central `GlobalConfig` / `StrategyConfig`: every tunable parameter in one place |
| [`earnings_iv_crush/data/`](earnings_iv_crush/data/) | Intake facade, market registry and providers (Databento OPRA bars and quotes, NSE, B3, LSE, Alpaca, earnings calendars, FRED VIX, SEC, GICS sectors), WRDS point-in-time panel, session overrides, per-event features, term-spread panel |
| [`earnings_iv_crush/strategy/`](earnings_iv_crush/strategy/) | Fair-move model, the gates, trade structures (iron fly, calendar), VIX regime selector, strategy book |
| [`earnings_iv_crush/engine/`](earnings_iv_crush/engine/) | Quote selection and hygiene, staleness-aware marking, Greeks and P&L attribution, cost model, risk and sizing, event study, alpha adjudication, statistics, backtester, simulator, structured ledger, equity curves, tearsheet |
| [`earnings_iv_crush/baseline/`](earnings_iv_crush/baseline/) | Agent 0 unfiltered control |
| [`earnings_iv_crush/live/`](earnings_iv_crush/live/) | IBKR paper-trading harness (connection, market data, orders, paper book) |
| [`scripts/`](scripts/) | Entry points: smoke test, demo backtest, research runner, sensitivity sweep, chain fetcher, IBKR paper trade |
| [`tests/`](tests/) | Test suite, mirroring `earnings_iv_crush/` |
| [`data/`](data/) | Raw and processed pulls (git-ignored) |

All tunable parameters live in [`earnings_iv_crush/config.py`](earnings_iv_crush/config.py) as two
frozen dataclasses; the domain modules re-export the individual fields under their established names.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; use source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"       # editable install of the earnings_iv_crush package + dev tools
copy .env.example .env        # then fill in your keys
```

FRED VIX, yfinance equities and yfinance option chains work with no key. The keys in
[`.env.example`](.env.example) unlock the rate-limited or higher-quality providers (Finnhub earnings
calendar, SEC EDGAR user agent, Tiingo, Alpaca historical surfaces, and the Databento OPRA data that
produces the headline study). Keys are read by
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
```

`run_research.py` validates the harness wiring on a planted-edge event set: the full cost stack, the
significance comparison, the regime structure mix and the vega/gamma/theta/delta attribution, writing
a tearsheet to `outputs/research/`. `--real` swaps in the live pipeline for a read on real edge, and
`--market {us,india,brazil}` selects the chain adapter and calendar through the provider registry.

The multi-year quote-marked study behind the **Evidence** section runs through the metered OPRA
pipeline. Raw pulls and generated outputs are git-ignored, and the one-off analysis runners that
produced the published figures are kept out of the package rather than shipped as library code, so
the figures above are reported here rather than reproducible from a clean clone without data access.

## Author

Jordan Odorico. Built for QUANTT (Queen's University Algorithmic and Network Trading Team).
