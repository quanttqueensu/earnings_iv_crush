# Earnings IV Crush

[![CI](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml)

A systematic options project built around one question:

**Does the volatility priced into single-name options before earnings exceed the risk that actually shows up, and can that difference be captured after real trading costs?**

The strategy sells short-dated at-the-money straddles around scheduled earnings announcements. The summer work built the infrastructure to test that idea properly, including quote-level option data, transaction-cost measurement, multiple strategy variants, and an Interactive Brokers paper-execution layer.

Two versions of that trade appear throughout these documents, and it is worth separating them at the outset:

* **The current baseline** is the *unconditional* short earnings straddle, which takes every eligible event with no selection rule at all. This is what new work is measured against.
* **The frozen summer specification** is that same trade filtered by a term-structure gate at the 80th percentile. It is not carrying forward in that form, and is kept fully documented because it is what the twelve-year record was produced with and it remains the comparison the next selector has to beat.

The underlying earnings-volatility effect remains interesting, and the next stage is focused on **finding genuine mispricing, improving execution, and testing better ways to manage the position after earnings.**

## 1. Project Overview

The basic trade is simple.

Immediately before a scheduled earnings announcement, the strategy sells a short-dated at-the-money call and put. Selling both together is a *straddle*: it makes money if the stock stays still and loses money if it moves a long way in either direction.

After the announcement, *implied volatility*, which is the amount of future movement the option's price implies the market is expecting, normally falls sharply as the uncertainty around the event disappears. That fall is the "crush" in the project name.

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

The frozen selector worked off the slope between short-dated and longer-dated implied volatility, on the reasoning that a steep slope means the market is charging heavily for the announcement specifically. Broader out-of-sample testing showed it was picking large moves rather than overpriced ones, which is the specific thing the next version has to fix.

The system around it stays.

**A note on annualisation.** Every Sharpe figure here is per-trade unless a factor is stated beside it. Annualising a Sharpe means multiplying by the square root of the number of observation periods in a year, and the period has to match the series the ratio was computed on (Lo, 2002). This book's observation is a trade rather than a day, so nothing is hard-coded: `engine/stats.py::infer_periods_per_year` reads the realised rate off each series' own calendar span, which lands near √35 for a book trading about that often. The familiar √252 is correct for a daily return series and wrong here by roughly threefold, which is a mistake this project made once and now has a regression test against.

Where the question is what a committed dollar earns rather than whether the signal selects, `engine/stats.py::calendar_sharpe` builds the daily series directly, charges zero to every session the book is flat, and annualises that by √252. The two agree for a book holding one position at a time and diverge when positions overlap, which they do, because earnings cluster into four windows a year. That function's docstring sets out the relationship in full.

## 2. Where the Strategy Stands

The simplest version of the strategy is currently the most interesting starting point.

On a clean 2025-26 dataset that no configuration was fitted to, the **unconditional short earnings straddle** produced:

| Metric | Result |
| --- | ---: |
| Events | 1,221 |
| Hit rate | **61.0%** |
| Gross return on margin | **+3.44%** |
| Net return on margin | **+0.49%** |
| Per-trade Sharpe, 95% CI | +0.043, date-clustered [-0.027, +0.120] |

Every term in that table is defined in Section 11.

The interval runs from a negative number to a positive one. That means the data cannot rule out that the true result is zero or worse, so this is **not being treated as a finished profitable strategy**.

It is a baseline.

The important part is that the underlying book remained positive before adding a complicated selector.

The original term-structure rule did not.

On the same clean block:

| Book | Net RoM | Gross RoM | Per-trade Sharpe | 95% CI on the Sharpe |
| --- | :--: | :--: | :--: | :--: |
| Unconditional | **+0.49%** | **+3.44%** | +0.043 | [-0.027, +0.120] |
| Frozen term selector | **-3.12%** | +0.07% | **-0.210** | **[-0.347, -0.058]** |

Picking events at random, at the same number of trades, also beat the frozen rule.

That result changed the direction of the project.

The term-structure signal was successfully finding earnings announcements where the market expected a large move. The problem was that those companies also tended to actually make large moves.

The selector was identifying **risk magnitude**, not necessarily **mispricing**.

The next version of the strategy is being built around that distinction.

The full result set, including the twelve-year record and the attribution behind it, is in [`STRATEGY.md`](documentation/STRATEGY.md) Section 6.

## 3. How the Strategy Developed

The project went through six distinct stages between May and August, and most of what it now knows came from things that were built and then discarded.

Daily option closing prices turned out to be unusable and were replaced with real bid/ask quotes in June. An implied-move filter was built and dropped. A term-structure selector became the main summer specification in late June and was frozen before deeper testing. July extended the history back to 2013, tested alternative structures and international markets, and measured execution cost directly. August tested everything on a clean, untouched block and produced the pivot described above.

Across the full 2013-24 quote-marked book, the frozen summer strategy produced **391 trades and +0.056 per-trade Sharpe**, with a clustered interval of **[-0.042, +0.180]**.

That is not strong enough to carry forward as the final strategy, particularly after accounting for how many configurations were tested.

The useful result is that the project now knows much more precisely **what needs to improve**.

The stage-by-stage account, with what each stage produced and why it was kept or dropped, is in [`SUMMER_SUMMARY.md`](documentation/SUMMER_SUMMARY.md) Section 2.

## 4. Execution Matters

One of the largest pieces of work this summer was measuring what option execution actually looks like.

Rather than assuming trades could be filled at the midpoint between the bid and the ask, the project matched **34,672 real option market prints** to their prevailing consolidated bid and ask.

At the fixed execution window studied:

* median price improvement was **0.0%**;
* only **21.2%** of prints traded at or better than the midpoint;
* **54.3%** paid the full touch, meaning they bought at the ask or sold at the bid; and
* the measured half-spread was roughly **1.79% per side**.

That changes how the strategy should be designed.

Execution cost is not something to subtract after finding a signal. For short-dated earnings options, it should be part of the signal itself.

The next strategy generation will therefore test **liquidity and spread filters before deciding whether an event is worth trading**.

## 5. What Comes Next

Five directions going into the year, in the order they are being prioritised. The full case for each, with the evidence behind it, is in [`STRATEGY.md`](documentation/STRATEGY.md) Section 7.

1. **Execution-aware selection.** None of the 1,476 recorded configurations ever started by asking whether the option itself was cheap enough to trade. The execution dataset now makes that possible. The first comparison will be an unconditional earnings book with liquidity and spread requirements against the original term-structure strategy at the same participation rate.
2. **Find mispricing rather than large moves.** The original selector was good at finding large expected moves. The next one needs to find situations where the price of the move looks wrong, which is a harder measurement problem than it first appears and is the main open research question going into the year.
3. **Revisit the exit.** The current baseline closes the straddle the session after earnings, which means crossing the option spread twice. Holding closer to expiry cuts the estimated round-trip break-even from roughly **11.6% of premium to about 5.8%**. It also changes what the position is, because it keeps directional exposure after the announcement.
4. **Separate the signal from earnings.** The same type of term-structure signal has been documented away from earnings by Vasquez (2017). Running it with the announcement removed separates "the signal is empty" from "the earnings event was the problem". The builder is already written and runs on free data.
5. **Use information from earlier reporters.** Hann, Kim and Zheng (2019) show that option markets react when peer companies in the same industry report first, but test no trading strategy. Whether the market has fully updated the next company's earnings volatility after seeing its peers is an open and largely uncrowded question.

## 6. Multiple Testing

The repository records **1,476 tested configurations**.

That number shows the amount of ground covered, but it is also a statistical problem: trying hundreds of combinations makes it increasingly likely that something will look good by accident. With a search family this large, the expected best Sharpe from a set of strategies with **no real edge at all is about +0.43**, well above the +0.056 the twelve-year frozen book produced.

The project therefore keeps a trial ledger that counts abandoned configurations rather than pretending failed branches never existed, and every strategy-level Sharpe is read against that search history.

This is another reason the first selector is not being carried into the year unchanged.

## 7. Data and Execution Assumptions

The main US historical results use OPRA consolidated bid and ask quotes through Databento. OPRA is the feed that consolidates quotes from every US options exchange, so a quote from it reflects the whole market rather than one venue.

Option marks are taken from the last valid two-sided quote at or before **15:59 ET** on the relevant session.

The universe is US single-name equity options. The broader system also connects to:

* WRDS datasets through the QUANTT R2 mirror;
* Alpaca;
* Finnhub;
* SEC EDGAR;
* DoltHub;
* London Strategic Edge;
* yfinance;
* FRED; and
* Interactive Brokers for paper execution.

Credentials live only in a git-ignored `.env`.

`.env.example` lists the required variable names without storing any credentials.

Historical option coverage currently reaches back to **2013**, with additional equity and earnings datasets extending much further.

The rules that stop the backtest using information it would not have had at the time are specified in [`STRATEGY.md`](documentation/STRATEGY.md) Section 5.

## 8. Forward Recording and Paper Execution

Historical backtests are only one part of the project.

A GitHub Actions workflow has also been built to create a forward paper record. After the market close, it can:

1. pull upcoming earnings announcements;
2. snapshot the relevant option chains;
3. record qualifying positions;
4. mark positions when their exit session arrives; and
5. commit the updated book back to GitHub as `paper-radar[bot]`.

The point of running this in the cloud is that the resulting record is externally timestamped rather than recreated later after seeing the outcome.

The recorder was deployed in August and is still being hardened, so the forward record starts from a short base and is expected to grow through the year rather than to carry weight yet.

There is also a separate **Interactive Brokers paper-execution layer**, which turns strategy output into paper orders under a set of safety controls: dry-run by default, explicit transmission controls, protection against connecting to live trading ports, a kill switch, account and position checks, and a rule preventing a one-legged straddle from being transmitted.

Three workflows are meant to run beside one another through the year: historical research, where new ideas are tested against the existing baseline on the same engine; the cloud forward book, which accumulates a timestamped record as new announcements occur; and IBKR paper execution once a strategy version is ready for it. The goal is to stop treating the backtest as the entire project.

## 9. Codebase

What a clone carries:

| | |
| --- | ---: |
| Package modules | 71 |
| Lines of package Python | 16,417 |
| Research entry points | 17 |
| Automated tests | 626 |
| Lines of test Python | 8,102 |

What the wider project has produced, most of which is generated locally rather than carried in the repository:

| | |
| --- | ---: |
| Research and result artefacts | 661 |
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
* `documentation/`, the project documents;
* `outputs/`, result artefacts; and
* `.github/workflows/`, continuous integration.

A file-level map of the modules that matter most is in [`STRATEGY.md`](documentation/STRATEGY.md) Section 10.

## 10. Running the Project

Python 3.10+.

```bash
git clone https://github.com/quanttqueensu/earnings_iv_crush.git
cd earnings_iv_crush

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
python -m pytest -q
```

The test suite runs on synthetic fixtures and does not require paid data or network access. A correct environment reports 622 passed and 4 deselected out of 626 collected. The four deselected are marked `live` and hit real networks.

Then watch the pipeline actually run, which also needs no credentials:

```bash
python scripts/demo_pipeline.py
```

This prices a synthetic event panel through the same valuation, cost model and reporting contract every real result goes through. The generator prices announcement risk fairly by construction, so the gross book comes back near zero and the gap to the net book is the cost stack. It is a wiring check and a worked example, not a result, and it is labelled as such on every line. [`documentation/INFRASTRUCTURE.md`](documentation/INFRASTRUCTURE.md) Section 2.2 explains what to look at.

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

Before running a new research question of your own, read [`STRATEGY.md`](documentation/STRATEGY.md) Section 9. It sets out the protocol every result in this project is expected to follow.

## 11. Glossary

Terms used across all three documents.

| Term | Meaning |
| --- | --- |
| **At-the-money (ATM)** | The option whose strike price is closest to where the stock is currently trading. |
| **Straddle** | A call and a put on the same stock, same strike, same expiry. Selling one profits if the stock stays still. |
| **Implied volatility (IV)** | The amount of future movement an option's price implies the market expects, quoted as an annualised percentage. |
| **Implied move** | How far the option market expects the stock to move over the announcement, in percent, read off the straddle price. |
| **Term structure / term spread** | How implied volatility differs across expiry dates. The spread used here is front-week IV minus back-month IV. |
| **Hit rate** | The share of trades that made money. It says nothing about size, so a high hit rate with a few large losses can still lose overall. |
| **Premium** | The cash received for selling the options. |
| **Return on margin (RoM)** | Profit divided by the capital a broker requires to hold the position. The project's standard denominator, because it is what actually ties up money. |
| **Reg-T margin** | The US regulatory margin formula, approximated here as 20% of the stock price plus the premium received. |
| **Gross vs net** | Gross is before trading costs. Net is after the bid/ask spread and commissions. On short-dated options the gap between the two is large. |
| **Mid, touch, half-spread** | The mid is the midpoint of the bid and ask. Paying the touch means buying at the ask or selling at the bid. The half-spread is the distance from mid to either side, and is what a trade costs if it crosses. |
| **Sharpe ratio** | Average return divided by the standard deviation of returns: how much return was earned per unit of variability. Higher is better; roughly 1.0 is generally considered good for a live strategy. |
| **Per-trade vs annualised Sharpe** | Per-trade Sharpe uses one trade as the unit. Annualising any Sharpe means multiplying by the square root of the observations in a year, with the period matching the series it was computed on (Lo, 2002). For a trade-unit series that is the square root of trades per year, derived from the data rather than fixed; √252 is the daily figure and would inflate a book like this more than threefold. See the note at the end of Section 1. |
| **Date-clustered 95% interval** | The range the true result plausibly sits in. It is clustered because many earnings land on the same day and are not independent observations, which a naive interval would ignore. An interval containing zero means the result cannot be distinguished from no edge. |
| **Deflated Sharpe** | A Sharpe ratio adjusted for how many configurations were tested before finding it. It answers the question "would a strategy this good have shown up anyway, by chance, given how much we searched?" |
| **In-sample, out-of-sample, holdout** | In-sample data is what the strategy was designed on. Out-of-sample data is what it was not. A holdout is data deliberately withheld until the rules were frozen, and it is the only honest test. |
| **Participation-matched random selector** | A benchmark that picks the same number of events, from the same pool, at random. It is the fair comparison for a selection rule, because it holds everything fixed except the rule itself. |
| **Vega, theta, spot** | The three sources of profit and loss here. Vega is sensitivity to implied volatility, theta is the value lost to time passing, spot is sensitivity to the stock price itself. |
| **Pre-registration** | Writing down the hypothesis, the exact test and the criterion for calling it a failure, before running it. It is what stops a result being reinterpreted after the fact. |

## 12. Documents

This README is the front door. Everything else lives in [`documentation/`](documentation), one
document per job.

| Document | Answers |
| --- | --- |
| **This README** | What is the project, where does it stand, how do I run it, and what do the terms mean. |
| [`STATUS.md`](documentation/STATUS.md) | Where the project stands right now and what is still open. One page. |
| [`INFRASTRUCTURE.md`](documentation/INFRASTRUCTURE.md) | How the system is built and how to work in it: onboarding, the data sources and their APIs, the codebase, the automated jobs, the scripts and the tests. Maintained through the year. |
| [`SUMMER_SUMMARY.md`](documentation/SUMMER_SUMMARY.md) | How the project developed over the summer, what each stage taught us, and what success looks like this year. |
| [`STRATEGY.md`](documentation/STRATEGY.md) | The exact trading rules, the data and execution assumptions, the full results, and what still needs validating. |

New members should start with [`INFRASTRUCTURE.md`](documentation/INFRASTRUCTURE.md) Section 2,
which takes a clone to a green test suite with no credentials.

Academic references are collected at the end of [`STRATEGY.md`](documentation/STRATEGY.md).
