# Project Status

**Jordan Odorico**

The current state of the project in one page: what works, what is open, and what the next
stage is set up to produce. Everything else is detail underneath it.

## Where the project is

The summer built a working options research platform and used it to test one strategy hard
enough to learn precisely where it breaks. The earnings volatility effect is real and
measurable: implied volatility falls on 98.1% of 989 events. Selling every eligible event
indiscriminately on a clean 2025-26 block returns +0.49% net on margin across 1,221 trades,
at a per-trade Sharpe of +0.043 whose interval contains zero. The term-structure filter
built to improve on that made it worse, and lost to random selection.

So the platform is finished and the selector is being rebuilt. That is a better position
than it sounds, because the expensive part is the platform, and the failure came with a
diagnosis rather than a shrug: the filter was selecting events where the market charged a
large implied move, and those are the events where the large move happens. Selecting on
mispricing rather than on magnitude is the pivot the next stage is built around.

## What is working now

| | |
| --- | --- |
| Test suite | 626 tests, green, no network or paid data required |
| Continuous integration | Green on every commit to main |
| Twelve-year book | Reproducible from cache in one command, N = 391, Sharpe +0.055992 |
| Clean 2025-26 block | Scored, pre-registered before the first data pull |
| Execution costs | Measured from roughly 35k option market quotes |
| Broker layer | Interactive Brokers paper execution built, dry-run by default |
| Research protocol | Pre-registration, trial ledger and one scoring path enforced by tests |

## What is open

Stated plainly, because the point of a status document is the second list.

1. **A fresh clone cannot reproduce the research.** The caches and result artefacts are
   git-ignored, so a new member can run the test suite and nothing else. Closing this means
   either publishing the cached inputs or shipping a small fixture set, and it is the first
   onboarding job.
2. **The margin model has never been checked against a broker statement.** A probe suggests
   the broker charges 2.2 to 2.4 times the modelled figure. Comparisons between books are
   unaffected, since they share the convention, but absolute return levels are research
   measures rather than deployable ones, and every document says so.
3. **Entry spot is stale on a minority of events.** The recorded entry price falls back to
   the previous session's close on 16.9% of priced events, and on 27.4% of the gated ones.
   A partial correction moves the pooled Sharpe from +0.056 to +0.045. This is the largest
   unrepaired item in the book and the first thing a sceptic should attack.
4. **Multiple testing bounds every in-sample number.** 1,476 configurations were scored.
   Against a search family that size the expected best Sharpe under no edge at all is
   +0.429, well above anything the frozen book achieved, which is why the next selector has
   to be pre-registered and tested once rather than searched.

## What the next stage is set up to produce

Five research directions are specified in `STRATEGY.md` Section 7, ranked by what each
would settle. Two can start immediately: the execution-aware selector runs entirely on data
already on disk, and the builder for testing the volatility signal away from earnings is
written, smoke-tested and runs on free data.

The infrastructure does not need to be built again. Time goes into the strategy rather than
the plumbing, which is the main argument for taking this project forward.

## Where to read next

| Time | Read |
| --- | --- |
| Three minutes | This document |
| Twenty minutes | [`README.md`](../README.md), the project, its status, setup, and a glossary of every term used |
| Joining the project | [`INFRASTRUCTURE.md`](INFRASTRUCTURE.md), which takes a clone to a green test suite and explains the data sources, the codebase and the automated jobs |
| An hour | [`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md) for how the project developed, then [`STRATEGY.md`](STRATEGY.md) for the rules, the full results and the constraints |
