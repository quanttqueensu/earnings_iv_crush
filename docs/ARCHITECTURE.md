# Architecture

How the code is arranged, how a trade is valued, how a result is reported, and how the tests
guard it. What the system trades and has decided is in [`SYSTEM.md`](SYSTEM.md); how to run it
is in the [README](../README.md).

## 1. Layout

```
earnings_iv_crush/        the installable package (pip install -e .)
  config.py               single source of truth: frozen dataclasses, every number named
  frozen.py               the frozen specification and its reconciliation targets
  data/                   one module per source, the provider registry, the R2 cache sync
  engine/                 pricing, marks, P&L, costs, statistics, attribution, risk
  strategy/               selection rules and gates
  baseline/               the unconditional control book
  research/               shared research infrastructure: marks, gates, chains, protocol
  live/                   the paper book: connection, market data, orders, ladder, session
  ops/                    orient, the state report
scripts/                  stable entry points (demo, research run, paper book, reports)
scripts/build/            data builders, several metered
research/<line>/          closed studies, frozen, with their preregs and findings
research/_template/       the starting point for a new study
tests/                    the suite, offline on synthetic data
docs/                     the documents; docs/INDEX.md says which owns which question
deploy/                   the cloud host for the paper book
data/                     the trading universe and the cache manifest; caches are git-ignored
outputs/                  generated artefacts, git-ignored except the named few
```

## 2. The package

`config.py` holds every parameter as a field of a frozen dataclass with its rationale in the
docstring: `GlobalConfig` (account, pricing, costs, data windows), `StrategyConfig` (the
filter, sizing and risk parameters) and `LiveConfig` (the paper book). Only `LiveConfig` reads
the environment, so a stray variable can never change a backtest. `frozen.py` mirrors the subset
that defines the frozen specification, is cross-checked against `config.STRATEGY` at import, and
carries the targets `assert_reconciles` checks a run against.

`data/providers.py` binds a market to its chain, calendar and spot sources as one triple, so no
provider branching leaks into run logic. The live universe is US single-name options only.

### Which modules are the live path

| Live path | |
|---|---|
| `strategy/filters.py` | The selector; `expanding_gate_rank` is the frozen gate. |
| `engine/pnl.py` | The reference valuation. Everything reconciles to `build_trade`. |
| `engine/marks.py`, `engine/quotes.py` | Marking and quote hygiene. |
| `engine/costs.py` | The measured cost stack. |
| `engine/screen.py`, `engine/stats.py`, `engine/event_study.py` | The reporting contract, Sharpe-family statistics, the cluster bootstrap. |
| `research/market_marks.py`, `research/gates.py`, `research/chains.py` | Market-marked straddle ledgers, causal masks, quote-marked chain fetch and parse. |
| `research/protocol.py` | Pre-registration freeze and verify, date-clustered intervals, the matched null. |
| `baseline/agent0.py` | The unconditional control. |
| `live/` | The paper book (section 6). |

| Closed arm, kept so its result reproduces | Why it closed |
|---|---|
| `strategy/fair_move_model.py` | Feeds the implied-versus-fair move gate, which failed out of sample. |
| `strategy/structures.py`, `strategy/regime.py`, `engine/structured_ledger.py` | Iron flies and calendars; the wings cost more than the whole cost budget. |

Every closed module says so in its own docstring. One that does not is a defect.

## 3. How a trade is valued

`engine/pnl.py::build_trade` is the reference implementation. The entry credit and the exit
value are each computed from the straddle at the strike and expiry actually sold, and P&L is
credit minus exit value minus costs, over margin. Margin is the Reg-T approximation, 20% of spot
plus the premium per share, times the multiplier and contracts.

The rule this file exists for: **check any new estimator against `build_trade` on the same events
before trusting it, and never compare two return series without confirming they share a
denominator.** An earlier forward estimator priced the buy-back at intrinsic, as if the option
expired on the exit date. It omitted the premium still in the contract (55.1% of the entry credit
on average over 912 events) and turned a mean RoM of -0.114 into +0.193. It also used premium as
the denominator where the book uses margin.

## 4. The cost model

| Component | Value | Source |
|---|---|---|
| Commission | USD 0.65 per contract per fill, four fills per round trip | broker schedule |
| Measured half-spread | 1.7871% of premium per side (entry 1.2714%, exit 3.0182%) | the fills study, `research/execution/` |
| Round-trip break-even | 11.6% of premium | derived; the canonical figure |

The measurement matched 34,672 prints to their prevailing consolidated quote in the 15:30 to
15:59 ET window: median price improvement 0.0%, 21.2% at or better than the mid, 54.3% at the
full touch. A trade-conditional arm of the same study reports a spread 2.35 times tighter and
**is never quoted**: trades cluster where the book is tight, which a strategy executing at a
fixed time cannot choose. `tests/test_fills_rescore_attainability.py` fails if it is promoted.

## 5. The reporting contract

`engine/screen.py::score_signal` is the single scoring contract. Every candidate returns N, hit
rate, per-trade Sharpe, a date-clustered interval and its annualisation factor as a field, and it
raises rather than return a degenerate result. Conventions (full rules in
[`PROTOCOL.md`](PROTOCOL.md)):

- **Annualisation** uses `stats.infer_periods_per_year`, the series' own observation rate. For
  a book trading about 35 times a year that is about the square root of 35, not of 252.
  `tests/engine/test_annualisation_regressions.py` forbids a defaulted 252.
- **Capital basis.** `stats.calendar_sharpe` reindexes onto every session, charges zero to flat
  days and annualises by the square root of 252. It answers what a committed dollar earns, and
  diverges from the trade-unit figure when positions overlap.
- **Clustering and multiple testing.** Intervals resample announcement dates. Strategy-level
  Sharpes are read against the trial count with the Deflated Sharpe Ratio.

## 6. The paper book

`scripts/paper_trade_ibkr.py session` over `earnings_iv_crush/live/`:

| Module | Job |
|---|---|
| `ib_connection.py` | Connect on a paper port only; the live ports are refused in code. |
| `ib_market.py` | Qualify the underlying, list the option grid, snapshot strikes, quote legs, read the dividend tick. |
| `session.py` | The daily pass: 2-of-3 calendar confirmation, exit and entry plans, filters, admission order, booking from fills, the intended-trades log. |
| `ladder.py` | The clock-driven mid-to-touch ladder for every leg, the legging rule, the hard cancel, the 15:59 NBBO record. |
| `order_events.py` | The append-only order-event log and the lifecycle completeness check. |
| `ib_orders.py` | Leg qualification, tick rounding, broker position reads, the manual managed buy-back. |
| `paper_book.py` | Open positions and ledgers in the backtest's schema. |
| `forward_test.py` | The forward exit's ledger rows and cost reconciliation. |

The clock and the quote source are injected, so the whole schedule runs offline in tests.
Operation is in [`RUNBOOK.md`](RUNBOOK.md); the specification in
[`FORWARD_TEST_SPEC.md`](FORWARD_TEST_SPEC.md).

## 7. Tests

`python -m pytest -q` runs the suite offline on synthetic data; tests marked `live` hit networks
and are deselected by default. CI (`.github/workflows/ci.yml`) runs ruff, black, mypy over the
package and the suite on every push and pull request.

The invariant suites each name the defect they guard in their docstring; follow that convention:

- `test_adversarial_invariants.py`, metamorphic: deleting post-entry records changes no entry
  quantity (look-ahead); halving prices and strikes while doubling contracts leaves returns
  unchanged (split basis); scrambling outcomes changes no selection quantity.
- `test_frozen_constants.py`, `test_term_gate_regressions.py`: the frozen specification.
- `test_annualisation_regressions.py`: no defaulted square root of 252.
- `test_fills_rescore_attainability.py`: the selection-biased cost arm stays unquoted.
- `test_preregistrations.py`: every recorded pre-registration hash matches its shipped text.
- `test_docs.py`: every document is indexed, links resolve, never-quote figures stay out.
- `tests/live/`: the paper book's safety, ladder and session properties on fake gateways.
- `test_demo_pipeline.py`: the day-one demo cannot be tuned until it shows an edge.
