# Technical Infrastructure and Onboarding

**Jordan Odorico**

This describes the whole system: what the strategy is, where every number comes from, how the
code is arranged, what runs without anyone touching it, and how a new member gets from an
empty folder to a green test suite.

This is a living document. Sections are numbered and self-contained so any one of them can be
rewritten without disturbing the rest. Section 13 explains how to amend it and records every
amendment made.

| | |
|---|---|
| 1 | The strategy in one page |
| 2 | Onboarding |
| 3 | Repository layout |
| 4 | Codebase architecture |
| 5 | Data sources and APIs |
| 6 | How a trade is valued |
| 7 | The cost model |
| 8 | Statistics and reporting contract |
| 9 | What runs without anyone touching it |
| 10 | Scripts |
| 11 | Testing |
| 12 | Known limitations |
| 13 | Amending this document |

---

## 1. The strategy in one page

The project sells the volatility premium priced into single-name equity options ahead of
scheduled earnings announcements.

Implied volatility on the front-week option rises into a scheduled announcement and falls
sharply once the result is public. That rise is compensation for carrying announcement risk.
The trade takes the other side: sell a short-dated at-the-money straddle shortly before the
announcement, close it shortly after, and collect the difference between the volatility that
was priced and the move that actually happened.

Two books run side by side, and confusing them is the most common early mistake:

- **The unconditional book** takes every eligible event with no selection rule. It is the
  current baseline and the thing new work has to beat.
- **The frozen specification** is the same trade filtered by a term-structure gate. It is
  pinned in `earnings_iv_crush/frozen.py` and enforced by `tests/test_frozen_constants.py`.
  It did not survive out-of-sample testing and is being rebuilt, but it stays fully specified
  because the twelve-year record was produced with it.

The frozen specification:

| Parameter | Value | Meaning |
|---|---|---|
| `term_spread_pctl` | 0.80 | Trade only when front-week minus back-month at-the-money implied volatility sits at or above the 80th percentile of its own past distribution |
| `use_move_gate` | False | The implied-versus-fair-move filter was tested and dropped; it fails its own out-of-sample test |
| `min_hist` | 25 | Minimum prior events before the gate threshold is computed at all |
| Vehicle | Naked short ATM straddle | The only structure positive net of asymmetric cost |
| Entry | Last session before the announcement, 15:59 ET | |
| Exit | First session after, 15:59 ET | |
| `sizing_fraction` | 0.05 | Margin per position as a fraction of the account |

The gate is causal everywhere: the threshold at event *i* is computed only from events with a
strictly earlier announcement date. This matters more than it sounds. An earlier version used
the full-sample 80th percentile, which is look-ahead, and that alone was worth roughly 0.05 of
per-trade Sharpe.

Where the research currently stands is in [`STATUS.md`](STATUS.md). The rules and the full
result set are in [`STRATEGY.md`](STRATEGY.md).

## 2. Onboarding

### 2.1 Day one, with no credentials at all

Everything in this section works with no API keys and no paid data.

```bash
git clone https://github.com/quanttqueensu/earnings_iv_crush.git
cd earnings_iv_crush

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
python -m pytest -q
```

The suite runs on synthetic fixtures and needs no network. A correct environment reports
**604 passed, 6 skipped, 4 deselected** out of 614 collected. The deselected four are marked
`live` and hit real networks; the six skips need research artefacts that are not carried in
the repository. Any other number means the environment is wrong, not that the tests are
flaky.

Then confirm the code meets the standard the continuous integration job enforces:

```bash
python -m ruff check .
python -m black --check .
python -m mypy earnings_iv_crush
```

All three must pass before any push.

### 2.2 Reading order

Read in this order. Each assumes the ones above it.

1. [`../README.md`](../README.md). What the project is and what every term means. The Section
   11 glossary defines every piece of options jargon used anywhere in this repository, so read
   it before deciding you are missing background.
2. [`STATUS.md`](STATUS.md). Where the project stands right now and what is open. One page.
3. [`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md). How the project got here, stage by stage, with
   what was kept and what was discarded.
4. [`STRATEGY.md`](STRATEGY.md). The exact rules, the data and execution assumptions, the full
   results and the constraints.
5. This document, then `earnings_iv_crush/config.py` and `earnings_iv_crush/frozen.py`, which
   carry every parameter and the reason it holds its value.

### 2.3 Adding a credential

Copy `.env.example` to `.env` and fill in the values you have. `.env` is git-ignored and must
stay that way. Every source is optional: the package degrades to keyless providers rather than
failing, so partial credentials are a normal state.

Never paste a key into a chat, a settings file, a permissions file, or a commit. If a key is
ever exposed, rotate it. Deleting the message does nothing, because the key has already been
transmitted.

### 2.4 Running your first research question

The protocol exists because this project has already produced results it had to withdraw. It
is set out in full in [`STRATEGY.md`](STRATEGY.md) Section 9. In short:

1. **Pre-register before you write the test.** Hypothesis, exact specification, inference
   method, success criterion, and the criterion that would kill the idea. Writing the kill
   criterion afterwards is how a negative result becomes a positive one.
2. **Declare the trial.** Every configuration tried raises the multiple-testing charge against
   every result reported, including the ones abandoned. `engine/alpha_adjudication.py` holds
   the ledger that records them.
3. **Write the script in `scripts/`, reusing `engine/`.** Do not reimplement valuation. If the
   engine cannot express your idea, extend the engine.
4. **Score through `engine.screen.score_signal`.** It enforces the reporting contract in
   Section 8 and refuses to return a degenerate result quietly.
5. **Report the result even when it kills the idea.** Most do. That is the job.

### 2.5 House rules

- Explicit staging only. Never `git add -A` or `git add .`.
- Every quantitative claim carries N, a dispersion measure, and the basis of any scaled number.
- A gate, filter or join that can silently produce an empty or degenerate result must raise,
  warn, or print a funnel. It must never return quietly.
- Superseded results are marked or removed in the same change that supersedes them.
- A push is not finished until continuous integration is green.

## 3. Repository layout

```
earnings_iv_crush/     the installable package
  data/                one module per source, plus the provider registry
  engine/              pricing, marks, P&L, statistics, attribution, risk
  strategy/            selection rules and gates
  live/                broker and paper-execution layer
  baseline/            the unconditional control book
  util/                shared helpers
  config.py            single source of truth for every parameter
  frozen.py            the frozen specification and its reconciliation targets
scripts/               entry points, one per research question
tests/                 the test suite
documentation/         this document, STATUS, STRATEGY, SUMMER_SUMMARY
data/                  the richness seed; caches are git-ignored
outputs/paper/         the forward paper book, committed by the recorder
.github/workflows/     ci.yml and paper_radar.yml
```

Two things are deliberately absent from a clone. Research artefacts under `outputs/research/`
and the on-disk data caches are git-ignored, because they are large and partly vendor-derived.
The consequence is stated plainly in [`../README.md`](../README.md) Section 10: a fresh clone
runs the test suite but cannot yet reproduce the research numbers. Closing that gap is an
onboarding task for the start of the year.

## 4. Codebase architecture

Installable package, `pip install -e .`, Python 3.10 or later. Continuous integration runs on
3.12.

| Part | Files | Lines |
|---|---:|---:|
| `earnings_iv_crush/` | 71 | 16,342 |
| `scripts/` | 15 | |
| `tests/` | 72 | 7,980 |

Package sub-structure: `data/` 32 modules, `engine/` 20, `strategy/` 6, `live/` 6,
`baseline/` 2, `util/` 2.

`config.py` is the single source of truth: frozen dataclasses, every field documented, every
magic number named, environment-variable overrides where sensible. Nothing else defines a
default. `frozen.py` mirrors the subset of those constants that define the frozen
specification, cross-checked against `config.STRATEGY` at import so the two cannot silently
disagree, and carries the reconciliation targets a research script can assert against before
its own results are believed.

`data/providers.py` is a market registry binding each market to a chain, calendar and spot
triple, so no provider branching leaks into run logic.

## 5. Data sources and APIs

Credentials live only in a git-ignored `.env` at the repository root. `.env.example` lists the
variable names with no values. Nothing below records a key; the last column names the
environment variable only.

Module paths in the two tables are relative to the package, so `data/vix.py` means
`earnings_iv_crush/data/vix.py`. The top-level `data/` directory is a different thing: it holds
the richness seed and the git-ignored caches.

### 5.1 Metered or licensed

| Source | Module | Supplies | Env var |
|---|---|---|---|
| Databento OPRA | `data/databento_quotes.py` | The primary historical option source. Consolidated best bid and offer sampled once a minute, available from 2013-04-01, which covers the whole sample. The mark is the last two-sided quote at or before 15:59 ET. | `DATABENTO_API_KEY` |
| Databento OPRA | `data/databento_options.py` | Daily bars with local Black-Scholes inversion. Retained for comparison; superseded as the marking basis. | same |
| London Strategic Edge | `data/lse_options.py`, `data/lse_intraday.py` | Daily and one-minute option bars. Trade prices, no bid or ask. Free but keyed and heavily rate-limited. | `LSE_API_KEY` |
| WRDS via Cloudflare R2 mirror | `data/wrds_r2.py`, `data/wrds_panel.py` | Read-only S3 parquet mirror. Compustat and IBES for the earnings calendar, CRSP for equity spot, a point-in-time surprise panel, Fama-French factors. | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET` |
| Interactive Brokers | `live/ib_market.py`, `live/ib_orders.py` | Live chain snapshots, underlying quotes, order placement. Paper account only. | `IBKR_HOST`, `IBKR_ACCOUNT`, `IBKR_CLIENT_ID`, `IBKR_MKT_DATA_TYPE` |

The largest data gap is that the R2 mirror holds no OptionMetrics; it was never ingested. The
mirror therefore re-sources only the calendar and the equity spot, and every option mark still
comes from Databento. Point-in-time OptionMetrics implied volatilities would need the WRDS
PostgreSQL path, which requires an account the project does not have.

### 5.2 Free

| Source | Module | Supplies | Env var |
|---|---|---|---|
| Alpaca free tier | `data/alpaca_options.py` | Contract universe and daily option bars from about February 2024. No implied volatility or greeks on the free tier, so volatility is inverted locally. | `ALPACA_KEY`, `ALPACA_SECRET` |
| Finnhub free tier | `data/earnings.py` | Live earnings calendar with the before-open / after-close field, cross-checked against SEC EDGAR acceptance times and Yahoo before a session is trusted. | `FINNHUB_API_KEY` |
| DoltHub | `data/dolthub_options.py` | US dated chains from roughly 2019 to late 2024 with real bid and ask and publisher-computed greeks. Public SQL over HTTP. | none |
| NSE India UDiFF bhavcopy | `data/nse_options.py` | Indian single-name options. Settlement price, open interest and underlying in one file. | none |
| B3 Brazil COTAHIST | `data/b3_options.py` | Brazilian single-name options, with genuine best bid and offer. | none |
| yfinance | `data/options.py`, `data/equities.py` | Current chains and daily equity bars. The forward recorder's snapshot source. | none |
| FRED | `data/vix.py` | VIX and VIX3M. | `FRED_API_KEY`, optional |
| SEC EDGAR | `data/sec_edgar.py` | Ticker to CIK map, 8-K Item 2.02 filings with session, reported diluted EPS via XBRL. | `SEC_USER_AGENT` |
| Tiingo | `data/equities.py` | Equity OHLCV, with yfinance as the keyless fallback. | `TIINGO_API_KEY` |

### 5.3 Cost discipline on metered pulls

Every metered request is priced before anything is downloaded, using the vendor's own free
cost-estimate endpoint. Every entry point takes a hard `--cap` in dollars and reserves against
it atomically before each pull, so concurrent workers cannot jointly overshoot.

One measured result is worth carrying forward: the consolidated quote stream is roughly five
times cheaper per event than daily bars, which is counter-intuitive until you notice that
daily bars bill one row per participating venue per symbol-day while the consolidated stream
is a single feed. Estimate before the pull, reconcile after, and explain any gap.

## 6. How a trade is valued

This section exists because it is where the project's most expensive mistake lived, and
because anyone writing a new estimator has to check it against the reference implementation
first.

### 6.1 The reference implementation

`earnings_iv_crush/engine/pnl.py`, function `build_trade`. Everything else must reconcile to
it. The entry credit and the exit value are each computed from the straddle at the strike and
expiry actually sold, and P&L is the credit less the exit value less costs, divided by margin.

Margin is a Reg-T approximation, 20% of spot plus the premium per share, times the contract
multiplier and the contract count.

### 6.2 The defect that hid in it

The forward recorder and a recent-window backtest both scored a closed short straddle as
`1 - |realised move| / implied move`. That prices the buy-back at intrinsic, as though the
option expired on the exit date. It does not: expiry sits one to two sessions later, so
closing the short costs intrinsic **plus the premium still in the contract**, and none of that
was charged.

On the 912-event canonical ledger the unpaid premium averages 55.1% of the entry credit, and
the estimator turns a mean return on margin of -0.114 into +0.193. It inverts the sign; it
does not merely inflate it. It also silently changed the denominator, using premium where the
settled book uses margin, so the two numbers were never comparable in the first place.

It surfaced only because the backfill returned about +15.7% per trade against a settled pooled
mean of +0.83%, which was too good to be true against a result already in hand.

### 6.3 The rule this produced

A valuation shortcut that removes a cost is always flattering. Check any new estimator against
`pnl.build_trade` on the same events before trusting it, and never compare two return series
without first confirming they share a denominator. Both forward paths now mark the exit off
the exit session's own chain at the strike and expiry actually sold. The retired estimator is
kept as a labelled diagnostic column and excluded from every reported figure.
`tests/test_paper_radar_provenance.py` fails if this regresses.

## 7. The cost model

| Component | Value | Source |
|---|---|---|
| Commission | $0.65 per contract per fill, four fills per straddle round trip | Broker schedule |
| Assumed half-spread | 2.00% per side | Original specification |
| Measured half-spread | 1.79% per side | The fills study |
| Flat break-even | 11.6% of premium, round trip | Derived, the canonical figure |

The measurement behind the third row is the most valuable single artefact in the project.
Using consolidated quotes, roughly 35k usable prints across 162 windows in the 15:30 to 15:59
ET band were each matched to their prevailing quote:

- median price improvement exactly 0.0%;
- 21.2% of prints traded at or better than the mid;
- 54.3% paid the full touch.

A trade-conditional arm of the same study reports a spread 2.35 times tighter. **It must never
be quoted.** It is a selection artefact: trades cluster where the book happens to be tight,
and a strategy executing at a fixed time cannot select into those moments.
`tests/test_fills_rescore_attainability.py` fails if anything promotes it, and every row of
the rescore artefact carries an attainability flag.

The first version of this study passed timezone-naive timestamps, which the vendor read as
UTC, so it measured 11:30 to 12:00 ET and labelled the result 15:59. The faulty artefacts are
preserved on disk with a `_SUPERSEDED_utc_window` suffix rather than deleted.

## 8. Statistics and reporting contract

`engine/screen.py` is the single scoring contract. Every candidate, whether an event book or a
calendar-rebalanced sort, returns N, hit rate, per-trade Sharpe, a date-clustered interval, and
the annualisation factor as a field on the result rather than a convention a reader has to
infer. It raises rather than returning a degenerate result.

Three conventions matter enough to state here.

**Annualisation.** Sharpe is reported per-trade by default, which is unambiguous. Any
annualised figure states its factor, and the factor comes from the series' own cadence:
`stats.infer_periods_per_year` reads the realised observation rate off the calendar span
rather than assuming one. For a book firing about 35 times a year that is roughly √35, not
√252. Using √252 once inflated a headline Sharpe by a factor of 3.2.
`tests/engine/test_annualisation_regressions.py` fails if anything defaults to √252.

**The capital-allocation basis.** `stats.calendar_sharpe` answers the different question of
what a committed dollar earns: it reindexes onto every exchange session, charges zero to the
days the book is flat, and annualises by √252. It coincides with the trade-unit figure for a
book holding one position at a time and diverges when positions overlap, which they do,
because earnings cluster into four windows a year.

**Clustering and multiple testing.** Intervals are date-clustered, because many earnings land
on the same day and are not independent observations. Every strategy-level Sharpe is read
against the recorded trial count, using the Deflated Sharpe Ratio. With the search family this
project has accumulated, the expected best Sharpe under no edge at all is about +0.43, which
is above anything the frozen book achieved. That is why the next selector has to be
pre-registered and tested once rather than searched.

## 9. What runs without anyone touching it

### 9.1 The forward paper recorder

`scripts/paper_radar.py`, scheduled by `.github/workflows/paper_radar.yml`.

Runs at 21:15 UTC Monday to Friday, deliberately after the 16:00 ET close year-round. Needs no
broker, no capital and no metered data: the earnings calendar comes from Finnhub's free tier
and the chains from yfinance, which carries real bid and ask. Two passes per run. The entry
pass snapshots the at-the-money straddle for names reporting within six days. The exit pass
re-fetches the chain and marks the same strike and expiry that was sold, off that position's
own exit session rather than the run date, so a missed run cannot measure a multi-day move and
book it as the announcement move.

The job commits its own book back to the repository as `paper-radar[bot]`. That is the point
of running it in the cloud rather than on a laptop: the record is timestamped by a third party
in a public commit history and cannot be back-dated.

Four design decisions are worth knowing, each of which exists because of a specific failure:

- It **fails rather than commits an empty book** when events were due and none could be
  snapshotted, because the chain source is rate-limited from datacenter addresses and a green
  run that persists nothing is indistinguishable from a quiet calendar.
- A **seed guard** hard-fails if `data/rich_set.csv` is missing, because without it every name
  records as overlay status "unknown" and the book silently becomes an unconditional one.
- A **schema check** refuses to proceed if either book's on-disk header differs from the
  code's. Appending a dictionary to a frame read off an older header silently drops every key
  that header does not name, which once cost the exit mark and its provenance from a live
  trade while still writing a plausible-looking return.
- A **configuration check** skips the whole job cleanly when no calendar key is set, so a
  clone that has not been set up does not accumulate daily red runs it cannot fix.

Every ledger row carries `source`, which is `live` only from the recorder, and `mark_source`,
which is `quote` or `intrinsic_fallback`, the latter excluded from every reported figure.
The loader raises rather than appending to a populated ledger with no `source` column.
Backfilled rows live under `outputs/research/` and are never merged into the live book.

To run it on a repository of your own, enable Actions and add `FINNHUB_API_KEY` as a
repository secret. Chains and spot need no key.

### 9.2 Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request: `ruff check`, `black --check`,
`mypy` over the package, then `pytest`. A push is not finished until it is green.

### 9.3 The broker harness

`scripts/paper_trade_ibkr.py` with `earnings_iv_crush/live/`. Safety is layered: dry-run by
default, then an explicit transmit flag, then a marker file that must exist on disk, then a
hard paper-port guard that refuses the live ports outright, then a kill-switch sentinel, and
finally a rule that nothing transmits unless both straddle legs qualify, so a one-legged
straddle cannot be sent. If neither paper port is listening the driver logs a skip and exits
zero, because a silently failing scheduled task is worse than none.

## 10. Scripts

Entry points live in `scripts/`, one per research question, each with argparse and a usage
block in its docstring. The ones carried in the repository:

| Script | Purpose |
|---|---|
| `run_research.py` | The main research run. `--real` uses live sources. |
| `validate_screen.py` | Rebuilds the settled book from cached marks and checks it reproduces N=391 and a per-trade Sharpe of +0.055992. The fastest integrity check on the whole machinery. |
| `agent_comparison.py` | Scores every selection rule through one scorer on one basis, so the only thing differing between rows is the rule. |
| `score_oos_2026.py` | Re-scores the clean 2025-26 block on the settled basis. |
| `run_extension_verdict.py` | Scores the 2013-2018 extension on the frozen specification, without re-tuning. |
| `validate_skew_oos.py` | The skew lever re-run causally out of sample. |
| `market_validate.py` | Out-of-sample validation on market-marked straddles rather than a model round trip. |
| `paper_radar.py` | The forward recorder. See Section 9.1. |
| `paper_trade_ibkr.py` | The broker harness. See Section 9.3. |
| `backfill_forward_window.py` | The recent-window backtest twin of the recorder. Metered; takes `--cap`. |
| `build_rich_seed.py` | Builds the richness seed the recorder depends on. |
| `run_backtest.py`, `run_sensitivity.py`, `fetch_chains.py`, `smoke_test.py` | Backtest, sensitivity sweep, chain fetch, and a fast end-to-end smoke check. |

Scripts that depend on research artefacts under `outputs/research/` will not run in a fresh
clone until those artefacts are published. `smoke_test.py` and the test suite are the two
things guaranteed to work on day one.

## 11. Testing

614 tests collected across 72 files. Four are marked `live`, hit real networks, and are
deselected by default.

The invariant-pinning suites each name the defect they guard in their own docstring, which is
the convention to follow when adding one:

- `test_adversarial_invariants.py` is metamorphic rather than expected-value. Deleting records
  dated after entry must not change any entry quantity, which catches look-ahead. Halving
  prices and strikes while doubling contracts must give an identical return, which catches the
  split-basis defect. Scrambling post-event outcomes must not change any pre-event selection
  quantity. Disagreeing duplicate records must raise instead of silently picking a row, and a
  one-sided quote must never become a mid.
- `test_frozen_constants.py` pins the specification and rejects a wrong-percentile baseline.
- `test_annualisation_regressions.py` forbids a defaulted √252.
- `test_fills_rescore_attainability.py` stops the selection-biased cost arm being reported.
- `test_paper_radar_provenance.py` stops the live book absorbing an after-the-fact trade.
- `test_trial_ledger.py` makes the multiple-testing count hard to understate: abandoned
  branches still cost deflation, a grid declares its full Cartesian product, and redeclaring a
  label with a different specification raises.
- `test_greeks_reference.py` validates the volatility inverter against an independent
  reference.

## 12. Known limitations

Stated here so nobody has to rediscover them.

1. **A fresh clone cannot reproduce the research.** Caches and result artefacts are
   git-ignored. Closing this means publishing the cached inputs or shipping a fixture set, and
   it is the first onboarding job.
2. **The margin model has never been checked against a broker statement.** A probe suggests
   the broker charges between 2.2 and 2.4 times the modelled figure. Comparisons between books
   are unaffected, since they share the convention, but absolute return levels are research
   measures rather than deployable ones.
3. **Entry spot is stale on a minority of events.** The recorded entry price falls back to the
   previous session's close on 16.9% of priced events. A partial correction moves the pooled
   Sharpe from +0.056 to +0.045. This is the largest unrepaired item in the book and the first
   thing a sceptic should attack.
4. **Multiple testing bounds every in-sample number.** See Section 8.
5. **One adversarial invariant does not run in a clone.** The expanding term gate it exercises
   still lives in the research scripts rather than in the package, so that case skips with a
   stated reason. Promoting it into `strategy/` would let the invariant travel with the code.

## 13. Amending this document

This document is expected to change through the year. It describes a system that is still
being built, and a technical document that has drifted from the code is worse than none,
because it is trusted.

**When to amend.** Any change to the frozen specification, a data source added or removed, a
new automated job, a defect found in valuation or reporting, or a limitation closed or
discovered. If you had to read the code to answer a question this document should have
answered, that is also a reason to amend it.

**How to amend.** Edit the section in place rather than appending a correction elsewhere, so
there is only ever one description of any given thing. Keep the section numbering stable, since
other documents link to it. Then add a row to the log below. Amend the log in the same commit
as the change it describes, so the two cannot separate.

**What not to put here.** Results belong in [`STRATEGY.md`](STRATEGY.md), current state in
[`STATUS.md`](STATUS.md), and narrative in [`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md). This
document covers how the system is built and how to work in it.

| Date | Section | Change |
|---|---|---|
| 2026-08-15 | All | First issue. |
| 2026-08-15 | 6.2 | Exit-marking defect documented after it was found and fixed in both forward paths. |
| 2026-08-15 | 9.1 | Forward recorder documented after deployment; schema guard and seed guard added. |
| 2026-08-16 | All | Rewritten for publication. Counts corrected to what the repository actually carries rather than the local tree; reading order repointed at published documents; data-source tables reconciled against the shipped modules. |
| 2026-08-16 | 9.1 | Configuration check added, so an unconfigured clone skips the recorder cleanly instead of failing daily. |
| 2026-08-16 | 12 | Limitation 5 added: one adversarial invariant skips in a clone because the gate it exercises is not yet in the package. |
