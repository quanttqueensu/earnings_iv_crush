# Project Status

**Jordan Odorico**

Read this first. It is the current state of the project in one page: what works, what
does not, what I need, and what the year is set up to produce. Everything else is
detail underneath it.

## Where the project is

The summer built a working options research platform and used it to test one strategy
hard enough to retire it. The earnings volatility effect is real and measurable: implied
volatility falls on 98.1% of 989 events. Selling every eligible event indiscriminately on
a clean 2025-26 block returns +0.49% net on margin across 1,221 trades, at a per-trade
Sharpe of +0.043 whose interval contains zero. The term-structure filter built to improve
on that made it worse, and lost to random selection.

So the platform is finished and the strategy is not. That is the honest summary, and it is
a better position than it sounds, because the expensive part is the platform.

## What is working now

| | |
| --- | --- |
| Test suite | 645 tests, green, no network or paid data required |
| Continuous integration | Green on every commit to main |
| Twelve-year book | Reproducible from cache in one command, N = 391, Sharpe +0.055992 |
| Clean 2025-26 block | Scored, pre-registered before the first data pull |
| Execution costs | Measured directly from 34,672 real option market prints |
| Broker layer | Interactive Brokers paper execution built, dry-run by default |
| Research protocol | Pre-registration, trial ledger and one scoring path enforced by tests |

## What is broken or unfinished

Stated plainly, because the point of a status document is the second list.

1. **The forward recorder is down.** It has failed since 13 August: the deployed script
   and the deployed ledger fell out of step and have to be redeployed together. Two
   scheduled runs are lost and will not be backfilled. The live book holds two open
   positions and no completed trades. This is the first thing I am fixing.
2. **A fresh clone cannot reproduce the research.** The caches and result artefacts are
   git-ignored, so a new member can run the test suite and nothing else. Closing this is
   an onboarding task and it needs the licensing decision below.
3. **The organisation fork is 14 commits behind** and carries none of the strategy,
   summary or hiring documents. Anyone reading it is reading the project as it stood in
   July.
4. **One result contradicts another.** A fifteen-selector comparison on an inverted-volatility
   basis says the term gate beats random selection; the clean quote-marked block says it
   loses. The documents say so rather than picking the flattering one. The likely cause is
   that the inverted basis penalises large-move events, which would flatter a selector that
   picks for move size, but that has not been demonstrated. It is roughly a half-day of work
   on data already on disk.
5. **The margin model has never been checked against a broker statement.** A probe suggests
   the broker charges 2.2 to 2.4 times the modelled figure. Comparisons between books are
   unaffected, since they share the convention, but absolute return levels are research
   measures rather than deployable ones, and every document says so.

## What I need

1. **Three analysts,** roughly six to eight hours a week: one or two on research, one on
   data and infrastructure, one on execution and microstructure. Roles and expectations are
   in `HIRING.md`. No options background is assumed for any of them.
2. **A standing data budget with a hard cap.** Historical option data is metered per
   request. Actual spend so far has been small, a few dollars, and every pull prices itself
   before downloading and reserves against a cap. What I need is a figure I can work inside
   without asking each time.
3. **A decision on publishing the cached research data.** This is what unblocks item 2 of
   the previous section. The event ledger is small enough to ship, but whether derived
   option data can be redistributed in a public repository depends on the vendor licence,
   which I have not read closely enough to answer myself. I need someone to confirm it
   before I publish anything.
4. **Point-in-time option data through the existing academic mirror, if it can be added.**
   The current mirror carries equity and earnings data but no options, so option marks come
   from the paid vendor. Adding the option dataset would remove most of the metered cost
   from the project.
5. **Write access to sync the organisation fork,** or someone to run the sync.

## What the year is set up to produce

Five research directions are specified in `STRATEGY.md` Section 7, ranked by what each
would settle. Two of them can start on day one: the execution-aware selector runs entirely
on data already on disk, and the builder for testing the volatility signal away from
earnings is written, smoke-tested and runs on free data.

The infrastructure that took the summer to build does not need to be built again. A new
member's time goes into the strategy rather than into the plumbing, which is the main
argument for taking this project into the year.

Alongside that, the forward paper record should accumulate a timestamped history that
cannot be reconstructed after the fact. It will not be conclusive within one academic year,
and it is worth saying so now rather than presenting it later as evidence it cannot yet be.

## Where to read next

| Time | Read |
| --- | --- |
| Three minutes | This document |
| Twenty minutes | [`README.md`](README.md), the project, its status, setup, and a glossary of every term used |
| An hour | [`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md) for how the project developed, then [`STRATEGY.md`](STRATEGY.md) for the rules, the full results and the constraints |
| Recruiting | [`HIRING.md`](HIRING.md) |
