# Pre-registration: quote-based re-mark of the mega-cap book

Written before any quote data was pulled. Every figure below is from the existing
close-marked book. Nothing in this document may be revised after the re-marked
numbers are seen; revisions belong in a dated appendix that says what changed and why.

## 1. Frozen specification

Established empirically by `scripts/research_gate_reconciliation.py` and the mark-mode
sweep, not from recollection. Four gate implementations and two marking paths were
scored on one common event file; the combination below is the only one that reproduces
the project's published headline, and it does so to six decimal places.

| Component | Frozen choice |
|---|---|
| Events | `outputs/research/events_megacap_databento.parquet` (session-corrected, 2026-07-20) |
| Preparation | `market_validate._prepare` (sort by announce_date+ticker, market marks, walk-forward fair-move fit, `index >= MIN_HIST`, `fair.notna()`) |
| Gate | `validate_skew_oos.expanding_high_term_mask` at q=0.80 (pooled expanding quantile of `iv_term_spread` over strictly-earlier announce dates, `>=`, MIN_HIST prior) |
| Marks | `engine.marks.mark_straddle` with the intrinsic repair **enabled** (`IVCRUSH_MARK` unset) |
| Ledger | `market_validate._ledger(defined_risk=False, costs=MEGACAP_COST)`, `MEGACAP_COST = CostModel(bid_ask_pct=0.04, cross_fraction=0.5)` |
| Sizing | `size_contracts(ACCOUNT_SIZE=250_000, ..., fraction=0.05)` |
| Outcome | `return_on_margin`, per-trade basis |
| Sharpe | `mean / std(ddof=1)`, unannualised |

`q = 0.80` is not re-searched. No gate parameter, cost parameter or sizing parameter
moves as part of the re-mark. If any does, the run is a new trial family and must be
declared as one.

## 2. Baseline being replaced

| Marks | Event file | N | Hit | Per-trade Sharpe |
|---|---|---|---|---|
| raw | pre-session-fix `.bak` | 192 | 67.7% | **+0.115773** |
| repaired | pre-session-fix `.bak` | 192 | 65.6% | +0.060432 |
| raw | current | 198 | 68.7% | +0.148065 |
| **repaired** | **current** | **198** | **66.7%** | **+0.087393** |

The published headline of +0.115773 is row one: computed with the intrinsic repair
disabled, on an event file since corrected. It is superseded twice over and is not the
comparison baseline. `run_broad_oos_verdict.py` hardcodes it as `BASE_SHARPE`, and it
propagates into roughly twelve artifacts; all of those are stale.

**The baseline for this exercise is N=198, per-trade Sharpe +0.087393, hit rate 66.7%.**

## 3. Hypothesis

The close-marked book prices options off last *trades*, which on a thin strike may be
hours stale and which violate the `|S - K|` floor on 20.1% of exits, concentrated in the
large-move tercile where an understated buyback flatters the short. Marking instead off
consolidated quotes (`cbbo-1m`, 15:59 ET) should remove that error.

The direction is **not** predicted. The repair already applied costs 0.061 of Sharpe, so
a further fall is plausible; equally, real quotes may be tighter than the repair's
conservative `intrinsic + 2 x OTM` reconstruction, which would raise it. Registering no
directional expectation is deliberate: a hypothesis that predicts both outcomes predicts
nothing, and the value here is the reduction in measurement error, not the sign.

## 4. Primary outcome and decision rule

Primary: per-trade Sharpe on `return_on_margin` under the frozen spec, with a clustered
bootstrap 95% CI resampling whole `entry_date` clusters (announcement-date clustering,
5,000 draws, seed 0).

Declared in advance:

- **Continue** if the quote-marked per-trade Sharpe is positive and its clustered CI
  lower bound is above -0.05. The project proceeds to Stage 2 (backward extension).
- **Kill** if the point estimate is at or below zero, or the CI lower bound is below
  -0.15. The strategy is written up as a negative result and the book is closed.
- **Inconclusive** otherwise: report honestly, do not spend further, and state the N
  required to resolve it rather than pursuing it.

Sample size required for a one-sided 95% result, computed from the current baseline
under Lo (2002) `SE = sqrt((1 + S^2/2)/N)`: at S=+0.087393 that is **N=356**, so 158
trades beyond the present 198. At the baseline the standard error is 0.0712, z=1.23 and
the one-sided p is **0.110**. Stated now so it cannot be reverse-engineered later.

Note for the record, because it is the clearest illustration of why the repair matters:
the *unrepaired* current book (+0.148065, N=198) would already clear a one-sided 95% bar,
needing only N=125. The strategy's apparent significance under raw marks is manufactured
by prints that cannot have traded.

## 5. Secondary outcomes

Reported but not decision-bearing, and not permitted to substitute for the primary if
the primary disappoints:

- Intrinsic-violation rate before and after (acceptance gate, see §6).
- Driver attribution: theta vs vega vs spot, via `scripts/run_driver_attribution.py`,
  path-ordered both ways with the residual reported. The paper's current vega-dominant
  claim is hardcoded in `make_paper_figures.py` and traces to no artifact.
- Measured half-spread per event, replacing the assumed `CostModel.bid_ask_pct = 0.08`.
- Snapshot vs 15:45-15:59 window-median mark disagreement, as a staleness statistic.
- PSR, and DSR against the recorded trial-family count.

## 6. Acceptance gates on the data itself

These are checks on whether the re-mark is trustworthy, evaluated before any Sharpe is
read. Failing any of them means the pull is rejected, not that the result is bad.

1. Exit-side intrinsic violations fall from 20.1% to under 2%.
2. Put-call parity holds on the reconstructed straddles within a stated tolerance.
3. Coverage: every one of the 1,051 events is accounted for as quoted, dropped-crossed,
   dropped-wide or dropped-no-quote. Retention below 70% raises rather than proceeds,
   mirroring `wrds_panel.IBES_LINK_MIN_RETAIN`.
4. Snapshot and window-median marks agree within 5% on the majority of events.
5. Post-event ATM IV falls for the majority of events measured ATM-to-ATM.

## 7. Multiple-testing accounting

The re-mark is **not** a new trial family: the specification is frozen above, the
parameters are inherited, and the only thing that changes is the price series the same
spec is evaluated on. The trial count for the deflated Sharpe therefore stays at its
existing value and is not reset by this exercise. Improving a measurement is not a
search, provided the search space is not reopened, which §1 forbids.

If the re-marked result is disappointing and any parameter is subsequently moved, that
is a new family and the DSR denominator increases accordingly. Recorded here so the
temptation is on the record before it arises.

## 8. What is not being done

No gate re-tuning. No universe widening. No new event classes. No machine learning. No
alternative data. Stage 2 (2013-2019 extension) and Stage 3 (`cmbp-1` fills study) are
not authorised by this document and each requires its own decision after Stage 1.
