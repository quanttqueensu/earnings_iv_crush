# Earnings Volatility Research: Open Roles

**Jordan Odorico**

## The trade

Implied volatility on a single-name option climbs into a scheduled earnings
announcement and drops once the result is out. Whoever is short collects the
difference. The question is whether that compensation exceeds the risk it pays
for, and whether anything survives the cost of trading it.

Over the summer the machinery to answer that on real quote data was built, and
then used: twelve years of OPRA consolidated quotes, multiple historical and
live data sources behind one interface, 645 tests, 1,476 recorded
configurations.

Start with [`README.md`](README.md) for the project and the terminology, then
[`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md) for how it developed and
[`STRATEGY.md`](STRATEGY.md) for the rules and the full results.

## What we found, and why that makes this worth joining

The premium is real. On a 2025-26 block nothing was fitted to, selling every
eligible event indiscriminately returns +3.44% gross and +0.49% net on margin
across 1,221 trades at a 61% hit rate.

The filter is not. On that same block the term-structure gate the project spent
three months refining returns -3.12% at a per-trade Sharpe of -0.210, whose 95%
interval excludes zero on the wrong side, and random selection at a matched
trade count beats it. Gross
return is +0.07%, so cost is not the culprit. The gate finds events where the
market charges a large implied move, and those turn out to be events where the
large move happens.

In May the question was whether selling earnings volatility pays. It is now
sharper: the premium is there, so what identifies an event where it is
overpriced? One wrong answer is eliminated and the apparatus to test the next
one is built. That is a better place to start a year than a vague thesis.

## What makes this project unusual

Most published options-anomaly work assumes its execution costs. This one
measured them. Across 34,672 consolidated prints matched to their prevailing
quotes, median price improvement is exactly zero, 21.2% execute at or better
than the mid, and 54.3% pay the full touch. That contradicts an assumption a
large class of published strategies depends on, and it disqualifies whole
families of idea before anyone spends a term building them.

It also exposes the gap in our own work: all 1,476 configurations gated on
signal variables and not one gated on cost, despite that spread study sitting
on disk. It is the first thing a new team should fix.

## Where the research goes

**Replace the selector.** Run the unconditional book with only a liquidity and
cost screen against the frozen gate on a matched sample. The data is on disk
and it settles in a week whether three months of selection work pointed the
wrong way.

**Find a selector that detects mispricing instead of size.** 91% of the gated
book's apparent advantage came from selling a physically larger option, while
the residual-value term, where genuine overpricing shows, moves the wrong way.
A new signal has to be scored on that residual or it will keep rediscovering
size.

**Cross the spread once.** Holding to expiry takes the round-trip break-even
from 11.6% to about 5.8%. A conditional hold already returns +17.3% against
-4.4% for the next-session exit, with a clustered interval on the difference of
[+0.007, +0.057]. It carries overnight directional exposure, which has to be
measured.

**Separate the signal from the event.** Vasquez (2017) reports a long-short of
+16.5% per month at t = 10.02 sorting on the same term slope in the same
direction away from earnings, held to maturity; this book sells his short leg.
Running the signal with the event stripped out is the most informative
experiment available. The code is written and it runs on free data.

## Roles

Three openings, roughly six to eight hours a week. No options background
assumed for any of them; every term used across these documents is defined in
[`README.md`](README.md) Section 11.

**Quantitative Research Analyst**, one or two positions. Own a direction end to
end: pre-registration, build, run, report. You state the hypothesis and the
kill criterion before you see any output, because that is how we avoid fooling
ourselves; five pre-registered tests on file show the shape.
*Needs:* Python and pandas, an introductory statistics course, and the
willingness to report a result that kills your own idea.
*Helps:* options pricing, econometrics, prior research experience.

**Data and Infrastructure Analyst**, one position. Own the pipelines: chain
acquisition and normalisation, the earnings calendar, caching, cost-capped
metered pulls, and the continuous integration that keeps 645 tests green. The
scheduled cloud recorder sits here.
*Needs:* Python, willingness to learn git properly rather than by copying
commands, and the instinct that a process returning a silent empty result is
worse than one that crashes.
*Helps:* GitHub Actions, SQL, prior work with market data.

**Execution and Microstructure Analyst**, one position. Own the cost side: what
a fill actually costs, how spreads behave around events, and which strategies
survive contact with those numbers. Clearest path to a differentiated result,
because the measurement already in hand contradicts a widely cited paper.
*Needs:* Python, genuine interest in market plumbing, comfort with tick-level
datasets.
*Helps:* OPRA data, order types, broker APIs.

## What we expect, and what you get

One team meeting and one written update per research cycle. Every result
carries its sample size, its dispersion and the basis of any scaled figure.
That standard is the main thing you will learn here.

You own a research direction, not a ticket queue. Your name is on what you
produce. The codebase is typed, tested, linted and continuously integrated, and
anyone who wants a written reference describing specifically what they built
will get one.

## Timeline

**Weeks 1 to 3.** Environment running, suite green, the research record read, a
first contribution merged. None of it needs paid data.

**Weeks 4 to 8.** First owned direction, pre-registered and tested. Two
experiments are ready to start on day one.

**Weeks 9 to 16.** Second cycle, informed by the first.

**Throughout.** A scheduled job on GitHub's servers snapshots option chains
after every close and commits its own book back to this repository, so the
forward record is timestamped by a third party and cannot be back-dated. It is
a multi-year instrument and will not be conclusive this academic year, which is
worth saying plainly.

## Applying

Tell us about something you measured that gave you a result you did not expect,
and what you did next. That is more informative than a transcript.
