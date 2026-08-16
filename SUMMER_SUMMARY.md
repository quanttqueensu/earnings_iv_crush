# Summer Progress Summary: Earnings IV Crush

**Jordan Odorico**
**Period:** 25 May to 16 August 2026

## TL;DR

Over the summer this project scored 1,476 configurations of a short earnings
straddle across twelve years of quote-marked option data, rejected the
selection rule it spent three months refining on evidence that rule itself
generated, and came out with two findings that point in opposite directions.
The volatility premium around earnings is real, survives on data nothing was
fitted to, and clears cost by a small margin. The term-structure filter built
to find the best events is a jump-magnitude selector, not a mispricing
detector, and it loses to picking events at random. A scheduled job on
GitHub's servers has been recording a forward book since 11 August.

The infrastructure is the part that carries forward: 645 tests, nine data
sources behind one interface, an execution study of 34,672 real prints, and a
pre-registration discipline that is what turned the negative result up in the
first place.

## 1. What Was Built

**The Crush Book** (full detail in [`STRATEGY.md`](STRATEGY.md)) sells a
short-dated at-the-money straddle into a scheduled earnings announcement and
buys it back the following session. It has three parts: an **event engine**
that resolves which announcements are tradeable and on what session, a
**selector** that decides which of those events to take, and a **cost floor**
that was measured rather than assumed.

Around it sits the machinery that makes an answer trustworthy: chain
acquisition from seven providers behind one interface, quote-based marking off
OPRA consolidated bid and offer, a volatility inverter validated against an
independent reference to 1e-10, profit attribution into theta, vega and spot,
date-clustered bootstrap inference, a Deflated Sharpe correction against every
configuration ever tried, and an integrity audit that hashes the source data
behind each of 2,062 events.

| | |
|---|---|
| Package | 72 modules, 16,551 lines |
| Whole tree | 307 Python modules, 64,033 lines |
| Tests | 645 across 69 files, green, no network required |
| Result artefacts | 657 files, across 28 distinct research-run days |
| Configurations scored | 1,476, recorded in a trial ledger |
| Metered data spend | about $36, every pull priced before it ran |

## 2. Proof of Multiple Agents Tested

This was not one idea built once. Each stage below was implemented, scored on
real market data, and kept or killed before the next one started. Roughly 220
distinct configurations sit on disk; the eight stages are the design arc
through them.

| Stage | Design | Outcome |
|---|---|---|
| 1 (late May) | Short straddle on 45 mega-caps, skew gate, marks taken from daily closes | **Rejected.** The closes were being treated as mids. Every figure from this stage is superseded and the repo still carries them under a `_SUPERSEDED` suffix rather than deleting them. |
| 2 (June) | Re-mark the whole book off OPRA consolidated best bid and offer, sampled once a minute at 15:59 ET | **Adopted as the marking basis.** This is the stage where the real numbers appeared. Pre-registered with the direction deliberately not predicted; one of five acceptance gates failed as written and the amendment is on file. |
| 3 (June) | Move gate: trade only when the implied move exceeds a fitted fair move | **Rejected.** Fails its own out-of-sample test. Disabled in the frozen configuration (`use_move_gate = False`) rather than quietly dropped. |
| 4 (late June) | Term-structure gate: trade only when front-week minus back-month at-the-money IV sits in the top 20% of its own past distribution | **Adopted and frozen** at q = 0.80, on a causal expanding quantile. Held this position for three months. Falsified at Stage 8. |
| 5 (July) | Defined-risk vehicles: iron fly at three wing multiples, two calendar constructions | **Rejected.** On 158 matched events the naked straddle gives +0.004 against -0.152 for a vega-balanced calendar and -0.569 for a one-to-one calendar. The pre-paid wing costs about 2.4% of margin against a total cost budget under 1%. |
| 6 (July) | Cross-market: the same rules on Indian single-name options (NSE) and Brazilian ones (B3) | **Rejected, and closed.** India shows no gross edge at any threshold from q = 0.50 to 0.95 across 960 events. Brazil shows a genuine +6.4% gross signal at 68.9% hit over 61 trades, consumed whole by a roughly 24% quoted spread and turning to -7.0% net. Two of the three canonical ways an edge dies, in one experiment. |
| 7 (July) | Backward extension to 2013 to 2018 as a true holdout, frozen spec, nothing retuned | **Did not replicate.** Per-trade Sharpe -0.005 against +0.117 on 2019 to 2024. Pooled N = 391, past the 356 the pre-registered power calculation demanded, so the sample-size objection closed here. |
| 8 (August) | Clean 2025-26 block, 2,037 events, built after the search had already concluded and pre-registered before the first data request | **Selector falsified.** The frozen gate returns -3.1% net on margin with a date-clustered interval excluding zero on the wrong side, and loses to a participation-matched random gate. Its gross return is 0.07%, so cost is not the explanation. Detail in Section 3.2. |

Alongside the design arc, fifteen selection rules were recomputed through a
single scorer on a single 912-event ledger, so that events, marks, costs and
denominator are identical in every row and only the rule changes. The full
table is in [`STRATEGY.md`](STRATEGY.md) Section 6.4. Read it for the ordering
between rows, not for the levels: that ledger reprices exits from inverted
implied volatilities, a basis that runs systematically more negative than
traded marks (+0.137 against -0.347 on the same 239 events).

Every configuration ever tried, including the abandoned ones, is declared in a
trial ledger, because an abandoned branch still costs multiple-testing
deflation. `tests/test_trial_ledger.py` fails if a grid declares less than its
full Cartesian product.

## 3. Results

### 3.1 The Twelve-Year Book

Frozen specification, quote-marked, nothing retuned between blocks. Net of a
measured 1.7871% half-spread per side plus commission, exits marked off the
exit session's own chain.

| Period | Trades | Hit | Per-trade Sharpe | Clustered 95% CI | Ann. Sharpe | Max DD |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| In-sample, 2019-2024 | 198 | 69.2% | +0.117 | [-0.027, +0.327] | +0.70 | -$14,936 |
| Holdout, 2013-2018 | 193 | 61.1% | **-0.005** | [-0.134, +0.153] | -0.03 | -$24,300 |
| **Pooled, 2013-2024** | **391** | **65.2%** | **+0.056** | **[-0.042, +0.180]** | **+0.33** | **-$24,300** |

Annualised figures use √(trades per year) = √35.2 ≈ 5.93, not √252 ≈ 15.87. An
earlier version of this project used √252 on a book that fires 35 times a year,
which inflated a headline Sharpe by 3.2 times and produced a figure of +2.04
that stood for about ten days before review caught it. Every scaled number in
this repository now states its factor beside it, and
`tests/engine/test_annualisation_regressions.py` fails if anything defaults to
√252.

Three objections a sceptic should raise, all of which land. The Deflated Sharpe
is the binding one: against 1,476 recorded configurations, the expected maximum
Sharpe from a family with no edge at all is +0.429, far above the +0.056
achieved. The worst drawdown is 9.4 times annualised profit, which is not an
allocatable shape regardless of significance. And two years alone, 2014 and
2022, contribute $32,505 against a twelve-year total of $29,596.

### 3.2 The Clean Out-of-Sample Block

`events_broad_oos_2025.parquet` holds 2,037 events across 346 names from
January 2025 to June 2026. It was constructed after the 1,476-configuration
search had already concluded, so no parameter in the frozen specification was
chosen with reference to any observation in it. It is the only genuinely
untouched block the project has.

The specification, the success criterion and both kill criteria were written to
`outputs/research/prereg_oos_2026.json` before the first data request,
including a commitment that the result would be reported whichever way it came
back. A clean block loses its value the moment its reporting becomes
conditional on its sign.

| Book | N | Hit | Gross RoM | Net RoM | Per-trade Sharpe | Clustered 95% CI |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Unconditional | 1,221 | 61.0% | +3.44% | **+0.49%** | +0.043 | [-0.027, +0.120] |
| **Term gate, q = 0.80 frozen** | 232 | 46.6% | **+0.07%** | **-3.12%** | **-0.210** | **[-0.347, -0.058]** |
| Random, participation-matched | 224 | 64.3% | +4.11% | +1.18% | +0.105 | [-0.030, +0.270] |

The gate is negative and its interval excludes zero on the wrong side. Random
selection at a matched trade count beats it by 3.66 points of return on margin,
clustered interval [-0.064, -0.009], which also excludes zero. That triggers
the second kill criterion registered before the pull.

**Why it fails is the useful part, and cost is not the answer.** Look at the
gross column: the unconditional book earns 3.44% before costs and the gated
book earns 0.07%. The gate selects events where there was no premium to collect
in the first place. The mechanism shows up in the moves. Unconditionally the
median implied move is 6.75% against a median realised move of 3.17%, a ratio
of 2.1. On the gated book it is 7.45% against 6.21%, a ratio of 1.2. The gate
successfully finds events where the market charges a large implied move. It
also finds events where that large move turns out to be deserved.

Two earlier results agree, which is why this reads as a finding rather than an
unlucky block. Decomposing the gated book's apparent advantage in July showed
roughly 91% of it came from selling a physically larger option rather than an
overpriced one, with the residual-value term, where genuine overpricing would
appear, moving the wrong way. And the frozen causal threshold applied to the
2013-2018 holdout returned -0.184 with an interval of [-0.326, -0.033]. Three
independent blocks, one conclusion.

What survives is the unconditional book: +3.44% gross, +0.49% net, 61.0% hit
across 1,221 events. Its interval contains zero, so that is not a profitable
strategy either and it is not presented as one on a single block. The summary
is that the volatility premium around earnings shows up unconditionally on
clean data and the selection rule actively destroys it.

**Bounds on this result.** Attrition is severe and not random: 1,221 of 2,037
events scored, with 606 dropped because the exit leg was not quoted at the
strike actually sold, so the surviving sample tilts liquid. The gated book's
five worst names carry 44.8% of its total loss across 120 names and 92 dates,
and the clustered interval handles date clustering but not name concentration.
One data request failed (USB, 19 January 2026) and that event is absent.
Estimated spend before the pull was $8.6902 against $6.5348 actual, on a hard
$15 cap; the estimate ran 25% high because it extrapolated from the first 40
chains of a sorted job list instead of a random sample.

### 3.3 The Cost Measurement

This is the artefact most likely to outlive the strategy. Most published
options-anomaly work assumes its execution costs on the argument that realised
spreads beat quoted spreads. Using Databento consolidated quotes, 34,672 usable
prints from 3.2 million records across 162 windows in the 15:30 to 15:59 ET
band, each matched to its prevailing quote:

- Median price improvement: **exactly 0.0%**
- Fills at the bid 25.6%, at the ask 28.7%, near the mid 21.2%
- **54.3% pay the full touch**
- Size-weighted fill location 0.282

Goyal and Saretto (2009) argue profitability survives an 8.0% quoted spread
because "the effective spread is generally lower than the quoted one". At
fixed-time execution, on this measurement, it is not. Muravyev and Pearson
(2020) are the honest counterweight and find realised costs materially below
quoted ones on liquid US names, so the truthful statement is that the discount
is a band, and at a fixed 15:59 execution this measurement puts it at zero.

Rescoring the twelve-year book on the measured cost rather than the assumed 2%
moves pooled Sharpe from +0.056 to +0.063 and one-sided p from 0.134 to 0.107.
The interval still contains zero. Execution is worth about 0.007 of per-trade
Sharpe, which closed the "better fills will save it" explanation.

One arm of that study reports 0.7611% per side, 2.35 times tighter than the
rest. It is a selection artefact: trades cluster where the book happens to be
tight, and a strategy executing at a fixed time cannot select into those
moments. It is the highest-Sharpe row in the file, which is exactly why
`tests/test_fills_rescore_attainability.py` fails if anything promotes it.

## 4. Real History

Nothing here is simulated. Every result is computed on vendor market data.

| Block | Events | Names | Period | Source |
|---|:--:|:--:|---|---|
| US mega-cap | 1,051 | 45 | Jan 2019 to Dec 2024 | Databento OPRA quotes |
| US backward extension | 955 | 50 | 2013 to 2018 | Databento OPRA quotes |
| US broad | 2,381 | 346 | Feb 2024 to Dec 2025 | Alpaca chains |
| US broad, clean out-of-sample | 2,037 | 346 | Jan 2025 to Jun 2026 | Databento OPRA |
| India | 1,358 | 200 | Jul 2024 to Jun 2026 | NSE UDiFF bhavcopy |
| Brazil | 135 | 27 | Feb 2025 to May 2026 | B3 COTAHIST |
| Post-earnings drift | 38,834 | broad | 1996 to 2024 | WRDS CRSP and IBES |
| Index variance premium | 420 months | index | 1990 to 2024 | CBOE and CRSP |

Option marks are OPRA consolidated best bid and offer sampled once a minute,
snapshotted at the last quote at or before 15:59 ET. That feed reaches back to
2013-04-01, which covers the whole sample. Both sides of every quote are
genuine, so nothing in the marking path silently substitutes a close for a mid.

### 4.1 The Automated Recorder

Backtests are cheap to produce and easy to overstate. A scheduled job runs on
GitHub's servers at 21:15 UTC every weekday, after the New York close in both
daylight and standard time. It pulls the earnings calendar, snapshots
at-the-money straddles for names reporting within six days, marks any position
due to close off that position's own exit session, and **commits its own book
back to this repository as `paper-radar[bot]`**.

That last part is why it runs in the cloud and not on a laptop: the record is
timestamped by a third party in a public commit history, so it cannot be
back-dated or quietly revised. It needs no broker, no capital and no paid data.

It is built to fail loudly. It refuses to commit an empty book when events were
due and none could be captured, because a green run that persists nothing looks
exactly like a quiet calendar. It hard-fails if its seed file is missing, since
without it every name records as overlay status "unknown" and the book silently
becomes a different book. And it checks the on-disk header against the code's
schema before writing, because appending to a frame read off an older header
once dropped an exit mark and its provenance from the first live trade while
still writing a plausible return.

**The live book currently holds zero completed trades.** It was restarted on 11
August when provenance stamping was added, and two positions are open. Two
bounded trades are not evidence in either direction and are not presented as
such. The forward evidence that does exist is a 199-event backtest over late
June to mid-August, unconditional across the broad universe, which returns
+2.96% gross and -0.03% net: the edge exists gross and is consumed almost
exactly by the 11.6% round trip, on a window nothing was fitted to.

There is also an IBKR paper-trading harness with layered safety rails: dry-run
by default, an explicit `--transmit` flag, a marker file that must exist, a
hard guard that refuses the live TWS and Gateway ports outright, a kill-switch
sentinel, and a rule that nothing transmits unless both straddle legs qualify
so a one-legged straddle is impossible. It has not been armed.

## 5. What I Got Wrong

Three defects changed a conclusion. Each is here with the rule it produced,
because the rule is the transferable part.

**A valuation shortcut inverted a book's sign.** Both forward paths scored a
closed short straddle as `1 - |realised move| / implied move`. That prices the
buy-back at intrinsic, as though the option expired on the exit date. It does
not: expiry sits one to two sessions later, so closing the short costs
intrinsic plus the premium still in the contract. On the 912-event canonical
ledger that unpaid premium averages 55.1% of the entry credit, and the
estimator turns a mean return on margin of -11.42% into +19.28%. It inverts the
sign, it does not merely inflate it. It also quietly changed the denominator
from margin to premium, so the number was never comparable to the settled
verdict. It surfaced only because the backfill returned about +15.7% per trade
against a settled mean of +0.83%, which was too good to be true against
something already known. *Rule: a valuation shortcut that removes a cost is
always flattering. Check any new estimator against the reference implementation
on the same events, and never compare two return series without confirming they
share a denominator.*

**Annualising a 35-trade book by √252.** Covered in Section 3.1. *Rule: the
scaling factor comes from the data's own cadence, not from convention.*

**A fail-loud alarm that failed silent.** The recorder's empty-book alarm
counted already-held positions as events it had failed to open, so re-running a
fully booked day exited non-zero, and in the workflow a non-zero exit skips the
commit step. The day's book would never have been saved. *Rule: an alarm must
be computed over exactly the population that could have triggered the condition
it claims to detect.*

Smaller ones, recorded rather than buried. A term filter using a rolling
30-event quantile with no minimum-periods guard produced an all-NaN threshold
on thin history and rejected every event, so a real run "worked" and took zero
trades. A comparison zero-filled the filtered book on 83 days it deliberately
did not trade, manufacturing a spurious result in the filter's favour. A gate
threshold was once computed from the full sample instead of causally, worth
about 0.05 of per-trade Sharpe. Each now has a test that fails if it returns.

## 6. Where This Goes

Six directions, ranked by what they would teach us. Section 3.2 reorders the
list: the first two attack selection, now the demonstrated problem, and the
next two attack cost, which binds the premium that remains. Full versions in
[`STRATEGY.md`](STRATEGY.md) Section 9.

1. **Replace the selector, testing the obvious null first.** Run the
   unconditional book with only a liquidity and cost screen against the frozen
   gate on a matched sample. The data is already on disk and it settles in a
   week whether three months of selection work pointed the wrong way.
2. **Find a selector that detects mispricing instead of size.** Any new signal
   has to be scored on the residual-value term or it will keep rediscovering
   that large options are large. A measurement-design problem before it is a
   signal problem.
3. **Cross the spread once instead of twice.** Holding to expiry takes the
   round-trip break-even from 11.6% to roughly 5.8%. A conditional hold already
   returns +17.3% against -4.4% for the next-session exit out of sample, on a
   cut chosen in sample, with a clustered interval on the difference of
   [+0.007, +0.057] and Wilcoxon p = 0.008.
4. **Select on cost, not only on signal.** All 1,476 configurations gated on
   signal variables and not one gated on cost, despite a 34,672-print spread
   study sitting on disk. Mid-seeking exits score +12.6% against +0.4% at a
   full cross on the same book.
5. **Separate the signal from the event.** Vasquez (2017) reports a long-short
   of +16.5% per month at t = 10.02 sorting on the same term slope in the same
   direction away from earnings, held to maturity; this book sells his short
   leg. Running the signal with the event stripped out separates "the signal is
   empty" from "the announcement is what makes it fairly priced". The builder
   is written and smoke-tested and runs on free data.
6. **Price what peers already revealed.** Hann, Kim and Zheng (2019) establish
   across 3,030 firms and 217 industries that a first announcer's implied
   volatility change predicts its peers'. They test no trading strategy at all.
   Least crowded idea on the list.

**Four doors are closed and should not be reopened.** Geographic expansion:
India has no gross signal and Brazil's sits inside its spread. More events: the
power calculation demanded 356 gated trades and 391 arrived. Better fills:
measured, worth 0.007 of Sharpe. Defined-risk structures: the wing costs more
than the entire budget.

## 7. Development Timeline

Dated commit history from this repository, independently verifiable rather than
self-reported. Note that commits understate the work by roughly half: research
runs, outputs and working notes are deliberately not version-controlled, and
149 of about 300 Python files have never been committed. By source-file
modification the project has **34 active days** across the period, which is the
honest effort record.

| Date | Milestone |
|---|---|
| 2026-05-25 | Project started: event engine, P&L ledger, margin and cost stack |
| 2026-05-31 | First commits: transaction-cost model, bootstrap and Deflated Sharpe, full Greek attribution, defined-risk variants, walk-forward harness |
| 2026-06-01 | Real Alpaca chains wired in; central frozen configuration as the single source of truth |
| 2026-06-19 | Restructured into an installable package; continuous integration on every push |
| 2026-06-20 | IBKR paper-trading harness with layered safety rails |
| 2026-06-23 | Databento multi-year backtest |
| 2026-06-28 | Annualisation corrected (√252 removed); term-only q = 0.80 adopted as the frozen baseline |
| 2026-07 | Execution study (34,672 prints), cross-market adapters, backward extension to 2013 |
| 2026-07-26 | Settled on quote-marked data: the twelve-year verdict, event study, cross-market adapters |
| 2026-08-11 | Cloud recorder deployed, plus four defects fixed that would have silenced it |
| 2026-08-12 | Exit-marking defect found and fixed in both forward paths |
| 2026-08-15 | Clean 2025-26 block pre-registered and scored; frozen selector falsified |

Reproducing the headline result end to end, with no paid credentials:

```bash
pip install -e ".[dev]"
python -m pytest -q                   # 645 tests, no network required
python scripts/validate_screen.py     # rebuilds N=391, +0.055992, [-0.0421, +0.1803]
python scripts/agent_comparison.py    # the fifteen-agent table
```
