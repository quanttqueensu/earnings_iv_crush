# Summer Progress Summary: Earnings Volatility

**Jordan Odorico**
**Period:** 25 May to 16 August 2026

This is the narrative account of the summer: what was built, in what order, and what each stage
taught us. For what the project is and what the terms mean, start with [`README.md`](../README.md),
which carries a glossary in Section 11. For the exact trading rules and the full result set, see
[`STRATEGY.md`](STRATEGY.md).

## TL;DR

Over the summer this project grew from a relatively simple earnings-volatility idea into a full options research and execution platform.

The original idea was to sell short-dated volatility around earnings announcements and use the shape of the implied-volatility term structure to identify the best opportunities. That led to more than **1,400 tested configurations**, multiple strategy designs, twelve years of quote-level US options data, extensions into international markets, and a direct study of more than **34,000 real option market prints**.

The biggest takeaway from the summer is that the underlying earnings-volatility effect is there. On a completely untouched 2025-26 dataset, the unconditional short-straddle book produced a **61.0% hit rate, +3.44% gross return on margin and +0.49% net return on margin across 1,221 events**. The per-trade Sharpe is **+0.043 with a date-clustered 95% interval of [-0.027, +0.120], which contains zero**, so this is a starting point rather than a finished result, but it is a real one on data nothing was fitted to.

What did not hold up was the original term-structure filter used to choose which earnings events to trade. On that same clean dataset it returned **-3.12% net on margin at a per-trade Sharpe of -0.210, with a date-clustered 95% interval of [-0.347, -0.058] that excludes zero on the wrong side, and it lost to selecting events at random at a matched trade count**. Its gross return was **+0.07%**, so the problem is not trading costs. The filter was finding events where the market charged for a large move, and those turned out to be the events where the large move actually happened.

That changes the direction of the project, but in a useful way. Instead of spending the year trying to improve the same filter, the next phase is focused on **execution-aware selection, alternative holding periods, better measures of relative mispricing, and new volatility signals**. Several of those directions are already built far enough to begin testing immediately.

At the same time, the infrastructure is largely in place: **645 automated tests, multiple historical and live data sources behind one interface, US option coverage from 2013 to 2026, a paper-trading connection to Interactive Brokers, and a cloud-based forward recorder designed to build a timestamped live history throughout the year.**

The summer was about building the platform and figuring out where the opportunity actually is. The goal for the year is to turn that into a strategy we would be comfortable putting forward as a complete systematic options book.

## 1. What Was Built

The project started with one fairly narrow question: **is the volatility priced into options before earnings systematically larger than what ends up being realised?**

By August, it had become much broader than a single backtest.

The core system now handles the full process:

* builds and checks an earnings calendar;
* downloads and normalises option chains from multiple providers;
* marks options using real bid/ask quotes rather than closing-price approximations;
* calculates implied volatility, Greeks, P&L and transaction costs;
* runs different strategy and selection rules through the same backtesting framework;
* tests alternative option structures, exits and holding periods;
* compares results across US and international markets;
* records every configuration tested so results can be compared properly;
* connects to Interactive Brokers for paper execution; and
* runs a scheduled cloud process designed to build a forward paper record.

The codebase has also grown substantially, to roughly 64,000 lines of Python across 307 modules,
carrying 645 automated tests and 657 result artefacts, with US option coverage from 2013 to 2026.
The full breakdown is in [`README.md`](../README.md) Section 9.

The main benefit of this is that the project does not need to start over every time the strategy changes. The data, execution, testing and backtesting infrastructure is already there. New ideas can now be plugged into the same system and compared on the same basis.

## 2. How the Strategy Developed

This was not one strategy built in May and polished until August. The design changed repeatedly as more data became available and different assumptions were tested.

| Stage | Design | What Came From It |
| --- | --- | --- |
| **1, late May** | Initial short earnings straddle using large-cap US names and daily option data | Built the first event engine, P&L framework, cost model and backtesting system. Also showed that daily closing prices were not good enough for serious options work: they were being treated as mid-prices, which is not what they are. |
| **2, June** | Rebuilt the strategy using OPRA bid/ask quotes around a fixed execution time | **Major infrastructure upgrade.** Quote-based marking became the standard for the rest of the project and gave a much more realistic picture of execution. |
| **3, June** | Tested an implied-move filter designed to identify especially overpriced earnings events | **Dropped.** It did not improve out-of-sample results. This was the first strong indication that finding a "large" implied move is different from finding a mispriced one. |
| **4, late June** | Term-structure strategy using the spread between front-week and longer-dated implied volatility | Became the main summer strategy and was frozen before extending the sample. It was strong enough on 2019-2024 (per-trade Sharpe +0.117, N = 198) to justify much deeper testing, and it drove most of the summer research. |
| **5, July** | Extended the frozen strategy backwards to 2013, then tested alternative structures, markets and exits: iron flies, calendars, India, Brazil, and a dedicated study of real execution costs | Narrowed the project substantially. The backward extension was a true holdout and returned **-0.005 per-trade Sharpe on 193 trades**, against +0.117 on the original block. Pooled over twelve years the book gives **+0.056 on 391 trades with a clustered interval of [-0.042, +0.180]**. Iron flies, calendars and both international markets were ruled out without spending the year on them. |
| **6, August** | Broad clean 2025-26 test, plus new exit and selection experiments | **This is the important pivot.** The base earnings-volatility premium remained visible, but the term-structure selector did not, and it lost to a random selector at a matched trade count. The project now moves from "find high-volatility earnings events" toward "find genuinely mispriced and executable earnings events." |

That last distinction is the biggest thing learned this summer.

The original selector was very good at finding earnings announcements where the options market was charging for a large move. The problem is that those stocks also tended to actually make larger moves. Median implied against median realised move was 6.75% versus 3.17% across all events, a ratio of 2.1, but 7.45% versus 6.21% on the filtered book, a ratio of 1.2. In other words, it was finding **risk**, not necessarily **overpricing**.

That gives the project a much clearer problem to solve going into the year.

**One thing to be explicit about.** Recording 1,476 configurations is a measure of how much ground was covered, but it is also a multiple-testing problem, and it works against every in-sample result in this document. Against a family that size, the expected maximum Sharpe from a set of strategies with **no edge at all is +0.429**, well above the +0.056 the twelve-year book achieved. Every in-sample figure here is deflated against that count, and the trial ledger is written so the count is hard to understate: abandoned branches still cost deflation, and a grid has to declare its full set of combinations. That correction is the main reason the summer's headline strategy is not being carried into the year unchanged.

## 3. Where the Strategy Stands Now

The twelve-year record on the frozen summer strategy is honestly weak. Across 391 trades from 2013 to 2024 it gives a per-trade Sharpe of +0.056 with a clustered interval containing zero, the true holdout block returns essentially nothing, and the deflation described above removes what is left. That is the result that pushed the project to look elsewhere.

The more encouraging result entering the year is actually the simplest version of the strategy.

On the clean 2025-26 dataset, built after the main summer search was already complete, the
**unconditional** short earnings straddle produced the figures quoted at the top of this document:
a 61.0% hit rate and +0.49% net on margin across 1,221 events, at a per-trade Sharpe of +0.043 with
a date-clustered 95% interval of [-0.027, +0.120]. That interval contains zero, so this is not a
proven edge and I am not presenting it as one. The point is that there appears to be something
worth working with **before adding any sophisticated selection model at all**, on data that no
configuration was ever fitted to. For comparison, the frozen term-structure filter applied to the
same events returned **-3.12%** at a per-trade Sharpe of -0.210, whose interval of
[-0.347, -0.058] excludes zero on the wrong side, and a random selector taking the same number of
trades from the same pool beat it. The side-by-side table is in
[`STRATEGY.md`](STRATEGY.md) Section 6.3.

That gives us a much better starting point for the year.

Rather than asking whether earnings volatility exists, the project can now focus on the parts that appear to matter most:

**Which events are actually mispriced?**

**Which events are cheap enough to trade?**

**When should the position be closed?**

**Can the same volatility signals work away from the earnings gap itself?**

Those are much more targeted questions than where the project started in May.

### Execution looks especially important

One of the biggest projects this summer was a separate study of where option trades actually fill.

Using **34,672 real option market prints matched to their prevailing bid and ask**, the project measured where trades were actually filling instead of assuming that every strategy could trade at the midpoint. Median price improvement came out at exactly zero, only 21.2% of prints executed at or better than the mid, and 54.3% paid the full spread.

That work made it clear that execution cannot be treated as a small adjustment at the end of the backtest. For short-dated options, it can be one of the largest drivers of whether an otherwise interesting signal survives.

This is also why one of the first priorities this year will be to build **liquidity and execution cost directly into the selection process**, rather than selecting a trade first and worrying about cost afterward.

### There are already promising next-step results

A few of the follow-up experiments from the summer are especially interesting, with the caveat below attached to both.

The standard summer strategy crosses the spread once to enter and again to exit the position the session after earnings. An alternative **hold-to-expiry** design cuts that round-trip cost roughly in half, from 11.6% of premium to about 5.8%.

In the current testing, a conditional hold-to-expiry version returned **+17.3% versus -4.4% for the next-session exit** on the same out-of-sample comparison, with the difference remaining positive under clustered inference (mean advantage +3.1%, interval [+0.007, +0.057], Wilcoxon p = 0.008).

The same is true on execution. On one matched book, **mid-seeking exits scored +12.6% versus +0.4% when every trade was forced to cross the full spread**.

**The caveat on both:** the specific cut being reported was chosen in sample. The out-of-sample comparison is real, but the decision about which version to look at was not made blind, so neither of these is a clean holdout result yet. Re-testing them on a properly frozen specification is one of the first jobs of the year, not a formality.

Together, those results point toward a fairly clear idea:

> The next improvement may come less from predicting which earnings announcement has the biggest volatility premium and more from being smarter about **which trades are inexpensive enough to take and how the position is managed once it is open.**

That will be one of the main themes of the next phase.

## 4. Real History and Forward Testing

The summer was mainly a research and infrastructure build, so the forward record is only beginning now.

A scheduled process has been deployed through GitHub Actions that snapshots option chains around
upcoming earnings, records candidate positions, marks them when their exit date arrives and commits
the resulting book back to the repository. [`README.md`](../README.md) Section 8 describes the
mechanism.

The important part is that the forward history is being written by a scheduled cloud job rather than manually on a laptop. That gives the project a dated external record that cannot simply be recreated later after seeing what happened.

The record is deliberately young: it starts from a short base and is expected to grow through the year rather than to carry weight yet. Whatever gaps it accumulates are recorded in the book itself rather than repaired quietly, because a forward record with undocumented gaps is not worth much.

A separate **Interactive Brokers paper-trading system** is also built, with layered safety controls designed to prevent accidental live routing, and can turn strategy output into paper orders.

The goal over the year is to move from a project dominated by historical testing to one with a meaningful **forward paper history** sitting beside it.

A handful of trades will not prove anything. A full academic year of timestamped trades, implementation changes and execution data will be much more useful.

## 5. What I Think the Best Opportunities Are Now

The summer narrowed the project considerably, and I think that is a good thing.

There are now several directions that can be given to individual analysts and tested in parallel rather than having everyone work on small variations of the same filter.

What follows is why each of these five was chosen and what it is meant to settle. The exact
specification of each, with the evidence behind it, is in [`STRATEGY.md`](STRATEGY.md) Section 7.

### 1. Build an execution-aware selector

Every major summer strategy selected trades using market or volatility signals.

None of the 1,476 recorded configurations started by asking:

> **Is this option cheap enough to trade?**

That is a striking gap given that cost turned out to be the binding constraint, and we now have the
execution dataset needed to close it. This is the first test of the year because it settles quickly,
runs on data already on disk, and would tell us whether three months of selection work was pointed
in the wrong direction.

### 2. Find mispricing rather than volatility

The original selector largely identified events where a large move was expected.

The next generation of signals should try to identify where the **price of that risk looks wrong**, rather than simply where the risk itself is large.

There is a concrete measurement problem underneath this. When the filtered book's apparent advantage was decomposed in July, roughly **91% of it came from selling a physically larger option** rather than a more expensive one, and the residual term where genuine overpricing would show up moved the wrong way. Any new signal has to be scored on that residual, or it will keep rediscovering that large options are large. That makes this a measurement-design problem before it is a signal problem.

That opens up work around residual volatility value, peer-relative pricing, historical event behaviour, surprise information and cross-sectional models.

### 3. Revisit the exit

The project currently enters immediately before earnings and closes the following session.

That is only one possible design, and it is the expensive one, because it crosses the option spread
twice. The hold-to-expiry results in Section 3 are the most interesting thing the summer produced
outside the main verdict, subject to the in-sample caveat attached to them there. Different exit
rules, decay windows and post-event structures will be a major research track. Holding through the announcement also changes what the position is, since it carries directional exposure after the event, and that has to be measured rather than assumed away.

### 4. Separate the volatility signal from earnings

The steep term structure used this summer is related to a broader options anomaly that has been documented outside earnings. Vasquez (2017) sorts on the same slope in the same direction away from announcements and reports a large long-short return; our book was selling his short leg. So the direction was right. What we added was the announcement, and with it the overnight gap.

That gives us a clean experiment: run the same type of signal **without the announcement event**. If
it works there and not here, the earnings gap is the problem rather than the signal.

The builder for this is already written and can run on free data.

### 5. Use information from earlier reporters

Companies do not report earnings in isolation.

Hann, Kim and Zheng (2019) show that option markets react when peer companies in the same industry report first. They test no trading strategy at all. That creates an interesting question for this project:

> If one company has already revealed information about its industry, has the option market fully updated the price of the next company's earnings risk?

This is one of the directions I am most interested in exploring with a larger team, and it is the least crowded idea on the list.

## 6. What Success Looks Like This Year

The summer goal was to build and pressure-test the project.

The goal for the year is different.

By the end of the academic year I would like the project to have:

* a continuously growing forward paper-trading record;
* a fully execution-aware strategy baseline;
* several independently owned research branches being run by team members;
* a tested answer on whether holding closer to expiry improves the economics;
* a rebuilt selection model focused on relative mispricing;
* at least one volatility strategy tested outside the earnings event itself;
* a much larger set of live option execution observations;
* and a final strategy specification that has been tested without repeatedly tuning against the same holdout period.

The advantage going into the year is that very little of the basic infrastructure still needs to be built.

New members can spend their time on the strategy.

## 7. Development Timeline

The GitHub history provides a dated record of how the project developed over the summer. It understates the work by roughly half, because research runs, outputs and working notes are deliberately not version-controlled: 149 of about 300 Python files have never been committed. By source-file modification the project has 34 active days across the period.

| Date | Milestone |
| --- | --- |
| **25 May** | Project started; initial event engine, P&L ledger, margin and transaction-cost framework built |
| **31 May** | Bootstrap testing, Greek attribution, alternative option structures and first walk-forward tools added |
| **1 June** | Real option-chain data connected and central configuration system introduced |
| **19 June** | Codebase rebuilt as an installable package with continuous integration |
| **20 June** | Interactive Brokers paper-trading integration built |
| **23 June** | Multi-year Databento options backtest added |
| **28 June** | Annualisation convention corrected and the main term-structure specification frozen for deeper testing |
| **July** | Execution study, international extensions, alternative structures and backward US history tested |
| **26 July** | Twelve-year quote-marked US book completed |
| **11 August** | Automated cloud forward recorder deployed |
| **12 August** | Forward valuation system upgraded and reconciled against the main P&L engine |
| **15 August** | Clean 2025-26 dataset completed; summer selector superseded as the primary direction and next-stage research programme set |

Setup and the commands for rebuilding the headline numbers are in [`README.md`](../README.md) Section 10.

## Bottom Line

The project is in a very different place than it was in May.

At the beginning of the summer, it was essentially one hypothesis about selling earnings volatility.

Three months later, there is a working options research platform, twelve years of quote-level history, more than a thousand strategy configurations tested, a direct execution-cost dataset, multiple discarded strategy families, paper-trading infrastructure and a clear set of next experiments.

The original term-structure selector will not be the final strategy, but I do not think that makes the summer unsuccessful. If anything, finding that out now is what makes the next stage more interesting. It is also not just one bad test. Three separate datasets and two different analyses point in the same direction.

The underlying earnings-volatility effect is still the piece worth attacking. The difference going into the year is that we now have a much better idea of **where the current approach leaves money on the table, what needs to change, and the infrastructure to test those changes quickly.**

The next phase is about turning that foundation into a strategy we would actually want to trade.
