# Earnings IV Crush

[![CI](https://github.com/jordanodorico/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/jordanodorico/earnings_iv_crush/actions/workflows/ci.yml)

A systematic options project built around one question:

**Does the volatility priced into single-name options before earnings exceed the risk that actually shows up, and can that difference be captured after real trading costs?**

The current strategy sells short-dated at-the-money straddles around scheduled earnings announcements. The summer work built the infrastructure to test that idea properly, including quote-level option data, transaction-cost measurement, multiple strategy variants, forward recording, and an Interactive Brokers paper-execution layer.

The original summer selector is no longer the final direction of the project. The underlying earnings-volatility effect remains interesting, and the next stage is focused on **finding genuine mispricing, improving execution, and testing better ways to manage the position after earnings.**

## 1. Project Overview

The basic trade is simple.

Immediately before a scheduled earnings announcement, the strategy sells a short-dated at-the-money call and put. After the announcement, implied volatility normally falls sharply as the uncertainty around the event disappears.

Across 989 measured earnings events, implied volatility fell **98.1% of the time**, by an average of **48.65 volatility points**.

The question is whether enough of that volatility was overpriced beforehand to compensate for:

* the realised earnings move;
* the bid/ask spread;
* commissions;
* the remaining value of the options when the trade is closed; and
* the occasional very large overnight gap.

That is what the rest of the system is designed to measure.

The project now has three main pieces:

1. **Event engine:** determines which companies are reporting, when the announcement occurs, and which trading sessions count as entry and exit.
2. **Strategy layer:** decides which events to trade, which option structure to use, and when to exit.
3. **Execution and measurement layer:** marks the actual option chain, applies trading costs, calculates P&L, and compares different strategy versions on the same basis.

The summer strategy used the slope between short-dated and longer-dated implied volatility as its main selector. That rule has now been retired as the primary direction after broader out-of-sample testing.

The system around it stays.

Every Sharpe figure in this repository is per-trade unless a factor is stated. The book trades roughly 35 times a year, so the defensible annualisation factor is √35.2 ≈ 5.93, not √252 ≈ 15.87.

## 2. Where the Strategy Stands

The simplest version of the strategy is currently the most interesting starting point.

On a clean 2025-26 dataset that no configuration was fitted to, the **unconditional short earnings straddle** produced:

| Metric | Result |
| --- | ---: |
| Events | 1,221 |
| Hit rate | **61.0%** |
| Gross return on margin | **+3.44%** |
| Net return on margin | **+0.49%** |
| Per-trade Sharpe | +0.043 |
| Date-clustered 95% interval | [-0.027, +0.120] |

The interval contains zero, so this is **not being treated as a finished profitable strategy**.

It is a baseline.

The important part is that the underlying book remained positive before adding a complicated selector.

The original term-structure rule did not.

On the same clean block:

| Book | Net RoM | Gross RoM | 95% interval |
| --- | :--: | :--: | :--: |
| Unconditional | **+0.49%** | **+3.44%** | [-0.027, +0.120] |
| Frozen term selector | **-3.12%** | +0.07% | **[-0.347, -0.058]** |

A participation-matched random selector also beat the frozen rule.

That result changed the direction of the project.

The term-structure signal was successfully finding earnings announcements where the market expected a large move. The problem was that those companies also tended to actually make large moves.

The selector was identifying **risk magnitude**, not necessarily **mispricing**.

The next version of the strategy is being built around that distinction.

## 3. How the Strategy Developed

This was not one model written in May and tuned until August.

Different parts of the strategy were built, tested, kept, or dropped as the data improved.

| Stage | Design | What Came From It |
| --- | --- | --- |
| **1, late May** | Large-cap short earnings straddle using daily option data | Built the original event engine, P&L ledger, margin model and backtester. Also showed that daily closes were not a reliable substitute for executable option marks. |
| **2, June** | Rebuilt the book using OPRA consolidated bid/ask quotes around a fixed execution time | **Adopted.** Quote-based marking became the standard for the project. |
| **3, June** | Implied-move filter designed to identify unusually expensive earnings events | **Dropped.** Did not improve out-of-sample performance. |
| **4, late June** | Term-structure selector based on front-week versus longer-dated implied volatility | Became the main summer specification and was frozen before deeper testing. The 2019-24 block produced +0.117 per-trade Sharpe across 198 trades. |
| **5, July** | Backward US extension, iron flies, calendars, India, Brazil and execution-cost work | The true 2013-18 holdout returned -0.005 Sharpe across 193 trades. Alternative structures and international versions also narrowed the list of directions worth continuing. |
| **6, August** | Clean 2025-26 broad-universe test | **Main pivot.** The unconditional premium remained visible while the frozen selector failed against both the baseline and matched random selection. |

Across the full 2013-24 quote-marked book, the frozen summer strategy produced **391 trades and +0.056 per-trade Sharpe**, with a clustered interval of **[-0.042, +0.180]**.

That is not strong enough to carry forward as the final strategy, particularly after accounting for how many configurations were tested.

The useful result is that the project now knows much more precisely **what needs to improve**.

## 4. Execution Matters

One of the largest pieces of work this summer was measuring what option execution actually looks like.

Rather than assuming trades could be filled at the midpoint, the project matched **34,672 real option market prints** to their prevailing consolidated bid and ask.

At the fixed execution window studied:

* median price improvement was **0.0%**;
* only **21.2%** of prints traded at or better than the midpoint;
* **54.3%** paid the full touch; and
* the measured half-spread was roughly **1.79% per side**.

That changes how the strategy should be designed.

Execution cost is not something to subtract after finding a signal. For short-dated earnings options, it should be part of the signal itself.

The next strategy generation will therefore test **liquidity and spread filters before deciding whether an event is worth trading**.

## 5. What Comes Next

There are five main directions going into the year.

### 5.1 Execution-aware selection

None of the original 1,476 recorded configurations started by asking whether the option itself was cheap enough to trade.

The execution dataset now makes that possible.

The first comparison will be an unconditional earnings book with liquidity and spread requirements against the original term-structure strategy at the same participation rate.

### 5.2 Find mispricing rather than large moves

The original term selector was good at finding large expected moves.

The next selector needs to find situations where the **price of the move looks wrong**.

That includes work around:

* residual volatility value;
* peer-relative pricing;
* historical earnings behaviour;
* earnings surprise information;
* cross-sectional models; and
* company and industry context.

### 5.3 Revisit the exit

The current baseline closes the straddle the session after earnings.

That means crossing the option spread twice.

Holding closer to expiry cuts the estimated round-trip break-even from roughly **11.6% of premium to about 5.8%**.

One conditional version tested this summer returned **+17.3% versus -4.4% for the next-session exit** on the later comparison.

The specific cutoff was selected in sample, so this is not a clean holdout result yet. It is a direction to freeze and validate properly.

### 5.4 Separate the signal from earnings

The same type of term-structure signal has been documented away from earnings.

That creates a useful experiment:

**Does the volatility signal work when the overnight earnings gap is removed?**

The basic builder for this test is already written and can run on free data.

### 5.5 Use information from earlier reporters

Companies reporting earnings later in an industry may already have information embedded in the option-market reaction to peers that reported first.

That raises a different type of pricing question:

**Has the market fully updated the next company's earnings volatility after seeing what happened to its peers?**

This is one of the directions intended for a dedicated analyst this year.

## 6. Multiple Testing

The repository currently records **1,476 tested configurations**.

That number shows the amount of ground covered, but it is also a statistical problem.

Trying hundreds of combinations makes it increasingly likely that something will look good by accident.

The project therefore keeps a trial ledger that counts abandoned configurations rather than pretending failed branches never existed, and strategy-level Sharpe results are evaluated using Deflated Sharpe against that search history.

For context, with a search family this large, the expected maximum Sharpe from a collection of strategies with no real edge is approximately **+0.43**, which is well above the +0.056 produced by the twelve-year frozen book.

That is another reason the first selector is not being carried into the year unchanged.

## 7. Data and Execution Assumptions

The main US historical results use OPRA consolidated bid and ask quotes through Databento.

Option marks are taken from the last valid two-sided quote at or before **15:59 ET** on the relevant session.

The broader system also connects to:

* WRDS datasets through the QUANTT R2 mirror;
* Alpaca;
* Finnhub;
* SEC EDGAR;
* DoltHub;
* NSE India;
* B3 Brazil;
* London Strategic Edge;
* yfinance;
* FRED; and
* Interactive Brokers for paper execution.

Credentials live only in a git-ignored `.env`.

`.env.example` lists the required variable names without storing any credentials.

Historical option coverage currently reaches back to **2013**, with additional equity and earnings datasets extending much further.

## 8. Forward Recording and Paper Execution

Historical backtests are only one part of the project.

A GitHub Actions workflow has also been built to create a forward paper record.

After the market close, it can:

1. pull upcoming earnings announcements;
2. snapshot the relevant option chains;
3. record qualifying positions;
4. mark positions when their exit session arrives; and
5. commit the updated book back to GitHub as `paper-radar[bot]`.

The point of running this in the cloud is that the resulting record is externally timestamped rather than recreated later after seeing the outcome.

The recorder was deployed in August and is still being hardened. It has been interrupted since 13 August by a schema mismatch between the deployed script and ledger, costing two scheduled runs. Those gaps are documented rather than backfilled.

There is also a separate **Interactive Brokers paper-execution layer**.

The IBKR integration includes:

* dry-run by default;
* explicit transmission controls;
* protection against connecting to live trading ports;
* a kill switch;
* account and position checks; and
* a rule preventing a one-legged straddle from being transmitted.

The goal throughout the academic year is to build a growing forward paper record alongside the historical work.

## 9. Codebase

| | |
| --- | ---: |
| Python modules | 307 |
| Lines of Python | 64,000+ |
| Package modules | 72 |
| Automated tests | 645 |
| Research/result artefacts | 657 |
| Recorded configurations | 1,476 |
| Option prints in execution study | 34,672 |

The package is split broadly into:

* `data/`, market data, earnings calendars and provider adapters;
* `engine/`, pricing, P&L, statistics, attribution and risk;
* `strategy/`, selection rules and strategy logic;
* `live/`, broker and paper-execution infrastructure;
* `baseline/`, the unconditional benchmark;
* `scripts/`, individual research entry points;
* `tests/`, regression, invariance and integrity tests;
* `outputs/`, result artefacts; and
* `.github/workflows/`, CI and forward recording.

## 10. Running the Project

Python 3.10+.

```bash
git clone https://github.com/jordanodorico/earnings_iv_crush.git
cd earnings_iv_crush

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
python -m pytest -q
```

The test suite runs on synthetic fixtures and does not require paid data or network access.

If the suite passes, the environment is ready.

**A note on the research entry points.** `outputs/` and the on-disk data caches are git-ignored, so the scripts below need datasets that are not carried in the repository. A fresh clone can run the test suite but cannot yet reproduce the research numbers. Getting a new member from a green suite to a reproducible result is an onboarding task for the start of the year, either by publishing the cached inputs or by shipping a small fixture set.

```bash
# Rebuild the settled twelve-year result from the cached quote marks
python scripts/validate_screen.py

# Main research pipeline (requires API credentials)
python scripts/run_research.py --real

# Compare fifteen selectors on one scoring basis
python scripts/agent_comparison.py
```

With the cache present, `validate_screen.py` reproduces:

* N = 391 trades;
* per-trade Sharpe = +0.055992; and
* clustered interval = [-0.0421, +0.1803].

## 11. Operating Cadence

The project is moving toward three parallel workflows during the year.

### Historical research

New strategy ideas are specified, tested and compared against the existing baseline using the same P&L and execution engine.

### Forward paper book

The cloud recorder snapshots upcoming events and builds a timestamped history as new earnings announcements occur.

### IBKR paper execution

Once a strategy version is ready for forward execution, the Interactive Brokers layer can be used to translate selected trades into paper orders under the existing safety controls.

The goal is for the historical backtest, cloud forward book and broker paper record to increasingly run beside one another rather than treating the backtest as the entire project.

## 12. What Success Looks Like This Year

By the end of the academic year, the target is to have:

* a stable and continuously growing forward paper record;
* an execution-aware baseline strategy;
* a properly frozen test of alternative exit rules;
* a rebuilt selector focused on relative mispricing;
* multiple analyst-owned strategy branches;
* at least one volatility strategy tested outside the earnings event;
* more live execution observations around the earnings window; and
* a final strategy specification tested without repeatedly tuning against the same holdout.

The advantage going into the year is that most of the basic infrastructure is already built.

The next stage is about improving the strategy.

## 13. Documents

* [`STRATEGY.md`](STRATEGY.md), full strategy logic, results, assumptions and open questions.
* [`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md), how the project developed over the summer and where it is going next.
* [`HIRING.md`](HIRING.md), open project roles and expectations.

A longer technical research record exists in `docs/research_handoff.md` but is not currently published to this repository.

## 14. GitHub

**Primary repository:** `github.com/jordanodorico/earnings_iv_crush`

The QUANTT organisation fork should be kept synced with the primary repository before onboarding begins.

## References

* Bakshi, G., Kapadia, N., & Madan, D. (2003). *Stock Return Characteristics, Skew Laws, and the Differential Pricing of Individual Equity Options.* Review of Financial Studies.
* Dubinsky, A., Johannes, M., Kaeck, A., & Seeger, N. J. (2019). *Option Pricing of Earnings Announcement Risks.* Review of Financial Studies.
* Goyal, A., & Saretto, A. (2009). *Cross-section of Option Returns and Volatility.* Journal of Financial Economics.
* Muravyev, D., & Pearson, N. D. (2020). *Options Trading Costs Are Lower Than You Think.* Review of Financial Studies.
* Vasquez, A. (2017). *Equity Volatility Term Structures and the Cross Section of Option Returns.* Journal of Financial and Quantitative Analysis.
* Hann, R. N., Kim, H., & Zheng, Y. (2019). *Intra-industry Information Transfers: Evidence from Changes in Implied Volatility Around Earnings Announcements.* Review of Accounting Studies.
