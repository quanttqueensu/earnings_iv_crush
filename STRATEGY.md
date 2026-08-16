# The Crush Book

A rule-based short-volatility book around scheduled earnings announcements:
single-name US equity options only, one round trip per announcement.

## 1. Purpose and Scope

This document specifies a rule-based strategy that sells a short-dated
at-the-money straddle into a scheduled earnings announcement and closes it the
following session, and reports what happened when that specification was tested
on twelve years of quote-marked option data plus a clean block nothing was
fitted to.

The rest of the document covers why the trade should work (Section 3), the
exact rules (Section 4), the data and execution assumptions behind every number
(Section 5), how it actually performed (Section 6), where its limits are
(Section 7), how to run it (Section 8), what is still open (Section 9), and
where the code lives (Section 10).

## 2. Executive Summary

The book has three parts:

- **The event engine.** Decides which announcements are tradeable, on what
  session, at what strike and expiry. Roughly half the work in this project
  sits here, because getting the session wrong turns a one-day volatility trade
  into a two-day directional one.
- **The selector.** Decides which of the tradeable events to take. The shipped
  selector ranks front-week minus back-month at-the-money implied volatility
  against its own strictly-earlier history and trades only the top 20%.
- **The cost floor.** 11.6% of premium round trip, derived from a measurement
  of 34,672 real prints rather than an assumption.

Over 2013 to 2024, on the frozen specification, quote-marked and un-retuned,
the gated book returns a per-trade Sharpe of +0.056 across 391 events with a
date-clustered 95% interval of [-0.042, +0.180]. On a clean 2025-26 block that
no configuration was ever fitted to, the same gate returns **-3.12% on margin
with an interval of [-0.347, -0.058], and loses to selecting events at
random**. Its gross return there is +0.07%, so cost does not explain it.

**The selector should be treated as falsified. The premium should not.** On the
same clean block the unconditional book, which takes every eligible event with
no selection at all, returns +3.44% gross and +0.49% net at a 61.0% hit rate
over 1,221 events. That is small and its interval contains zero, but it is
positive and it is the part worth building on.

This document keeps the gate specified in full, because it is what the
twelve-year record was produced with and because a falsified rule that is
documented is more useful than one that is quietly deleted.

## 3. Why the Trade Should Work

Two documented facts underpin the rules.

**Scheduled announcements are priced as jumps.** An option spanning an earnings
date has to cover a known-date, unknown-magnitude move. The market prices that
by lifting implied volatility on the expiry that contains the announcement, and
by lifting it hardest on the nearest expiry, since a fixed jump is a larger
fraction of a shorter option's total variance. Once the number is public the
jump resolves and that component of implied volatility disappears within a
session. Patell and Wolfson (1981) documented the pattern; Dubinsky, Johannes,
Kaeck and Seeger (2019) give the modern option-pricing treatment.

The crush itself is not in doubt and this project measured it directly: implied
volatility falls on **98.1% of 989 events**, by a mean of 48.65 volatility
points.

**A crush is not the same thing as a profit.** Whoever is short the straddle
collects the decline in implied volatility and pays for the realised move. The
seller is being compensated for carrying overnight gap risk that cannot be
hedged, because the position is observed at the close before and the close
after, with nothing tradeable in between. The whole question is whether the
compensation exceeds the risk, and an efficiently priced announcement is one
where it does not.

Every rule below is a version of that single tradeoff. Attribution confirms the
mechanism is the one named: vega is the largest positive leg under both path
orderings (+$355k and +$328k), the spot leg is the largest negative one (-$402k
and -$281k), and the correlation between measured crush and net return is
+0.734, so roughly 54% of return variance is the crush itself. The negative
spot leg is the gap, and it is what takes the premium back.

## 4. Model Specification

This section is the exact rulebook. It is pinned in
`earnings_iv_crush/frozen.py` and enforced by `tests/test_frozen_constants.py`,
so a change to any constant below fails the test suite.

```
                   ONE EVENT = ONE EARNINGS ANNOUNCEMENT
   ┌─────────────────────────────────┬──────────────────────────────────┐
   │       T-1  ENTRY  15:59 ET      │      T+1  EXIT  15:59 ET         │
   │  sell 1 ATM straddle, front-    │  buy it back off THAT session's  │
   │  week expiry, strike nearest    │  own chain, same strike, same    │
   │  to spot at the close           │  expiry, NOT at intrinsic        │
   └─────────────────────────────────┴──────────────────────────────────┘

    SELECTOR: front-week IV minus back-month IV, ranked against its own
    strictly-earlier history.  FROZEN AT q = 0.80  ->  FALSIFIED (6.3)
    What currently survives is the unconditional book, no selector at all.

    COST FLOOR: 11.6% of premium, round trip. Measured, not assumed.
    P&L = credit - buyback - costs        Denominator = Reg-T margin
```

| Parameter | Value | Meaning |
|---|:--:|---|
| `term_spread_pctl` | 0.80 | Trade only when the term spread sits at or above the 80th percentile of its own past distribution |
| `use_move_gate` | False | The implied-versus-fair-move filter was tested and dropped; it fails its own out-of-sample test |
| `min_hist` | 25 | Minimum prior events before the threshold is computed at all |
| Vehicle | naked short ATM straddle | The only structure positive net of asymmetric cost (Section 7) |
| Entry | last session before, 15:59 ET | |
| Exit | first session after, 15:59 ET | |
| `sizing_fraction` | 0.05 | Margin per position as a fraction of a 250,000 account |

### 4.1 The Event Engine

1. **Build the calendar.** Announcement dates come from Finnhub's free tier or
   from Compustat `fundq.rdq` via a WRDS mirror, and carry a before-open or
   after-close field. That field decides the entry session, and getting it
   wrong is not a rounding error: entering on the wrong side of an after-close
   print means holding through the announcement twice or not at all.
2. **Cross-check the session two of three.** The vendor's field is checked
   against SEC EDGAR 8-K Item 2.02 acceptance timestamps and a third source
   before a session is trusted. A filing accepted at 16:31 ET is an after-close
   print regardless of what the calendar says.
3. **Pick the expiry.** The nearest listed expiry strictly after the
   announcement. A shorter option carries a larger share of the jump, so the
   crush is concentrated there.
4. **Pick the strike.** Nearest listed strike to spot at the entry close.
   At-the-money maximises vega, which is the leg the thesis is about, and
   minimises the directional exposure that is not.
5. **Guard against corporate actions.** An overnight move that is really a
   split, a special dividend or a spin-off is rejected rather than booked as an
   announcement move.

### 4.2 The Selector, and Why It Is Frozen at q = 0.80

**Score.** Front-week at-the-money implied volatility minus back-month
at-the-money implied volatility. A steep term structure means the market is
charging a lot for the event specifically, over and above the name's ordinary
volatility, which is the intuition the gate was built on.

**Rank causally.** The threshold at event *i* is computed only from events with
a strictly earlier announcement date, on an expanding window, with at least 25
prior events before any threshold exists. This is not a technicality: an
earlier version used the full-sample 80th percentile, which is look-ahead, and
that alone was worth roughly 0.05 of per-trade Sharpe. `min_hist = 25` exists
because a rolling quantile with no minimum-periods guard once produced an
all-NaN threshold on thin history and silently rejected every event, so a real
run "worked" and took zero trades.

**Trade the top 20%.** q = 0.80 was selected on a grid over 2019 to 2024 and
then frozen. It sits on a broad, flat region rather than a spike, which is the
only reason to trust a chosen parameter at all, but see Section 7 on what the
grid cost in multiple-testing terms.

**What went wrong with it.** Section 6.3. In short, a steep term structure
identifies events where the market charges a large implied move, and those turn
out to be the events where a large move actually happens. The gate selects risk
magnitude, not mispricing. This is the central open problem in Section 9.

### 4.3 The Cost Floor

The straddle is crossed twice, four legs in total, and single-name option
spreads are wide. Cost is not a haircut on this strategy, it is the binding
constraint, so it was measured rather than assumed.

| Component | Value | Source |
|---|:--:|---|
| Commission | $0.65 per contract per fill, four fills round trip | IBKR Pro schedule |
| Assumed half-spread | 2.00% per side | Original specification |
| **Measured half-spread** | **1.7871% per side** (entry 1.2714%, exit 3.0182%) | `outputs/research/fills_study.csv` |
| Flat break-even | **11.6% of premium, round trip** | Derived; the canonical figure |

The exit half-spread is 2.4 times the entry half-spread. That asymmetry is what
kills every defined-risk variant: a pre-paid wing costs about 2.4% of margin
against a total cost budget under 1%.

Margin is a Reg-T approximation, `0.20 × spot + premium per share`, times the
multiplier and the contract count. It has never been validated against a broker
statement, and a probe against IB's own initial margin found the ratio sits
between 2.18 and 2.37 times the modelled figure. Comparisons between books on
the same convention are sound; absolute levels are not. This is disclosed again
in Section 7 because it bounds every return figure in the document.

## 5. Data and Execution Assumptions

Rules designed to stop the book using information it would not have had:

- Option marks are **OPRA consolidated best bid and offer**, sampled once a
  minute, snapshotted at the last quote at or before 15:59 ET. Both sides are
  genuine quotes. A one-sided quote never becomes a mid.
- The exit is marked off **the exit session's own chain**, at the strike and
  expiry actually sold. Not at intrinsic, and not off the run date. See the
  defect note below, because this cost the project its worst error.
- Signals use only data dated strictly before the entry close.
- Costs are charged at the measured 1.7871% per side plus commission on all
  four legs.
- One contract per event, so return on margin is invariant to sizing.
- An event is dropped, with a stated reason and a printed funnel, rather than
  filled with a fallback, whenever the chain is missing, the spot is missing,
  or either leg is unquoted.

**The exit-marking defect, kept here because anyone writing a new estimator
will be tempted by the same shortcut.** Both forward paths once scored a closed
straddle as `1 - |realised move| / implied move`. That prices the buy-back at
intrinsic, as though the option expired on the exit date. It does not: expiry
sits one to two sessions later, so closing the short costs intrinsic **plus the
premium still in the contract**. On the 912-event canonical ledger that unpaid
premium averages 55.1% of the entry credit, and the estimator turns a mean
return on margin of -11.42% into +19.28%. It inverts the sign. It also quietly
changed the denominator from margin to premium, so the number was never
comparable to anything else in the project. The reference implementation is
`engine/pnl.py::build_trade`, everything must reconcile to it, and
`tests/test_paper_radar_provenance.py` fails if this regresses.

## 6. Results

### 6.1 The Twelve-Year Book

Frozen specification, quote-marked, nothing retuned between blocks. The 2013 to
2018 block was built after the first block was scored and is a true holdout.

| Period | Trades | Names | Hit | Mean RoM | Per-trade Sharpe | Clustered 95% CI | One-sided p |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 2019-2024, in-sample | 198 | 36 | 69.2% | +1.71% | **+0.117** | [-0.027, +0.327] | 0.050 |
| 2013-2018, holdout | 193 | 30 | 61.1% | -0.08% | **-0.005** | [-0.134, +0.153] | 0.530 |
| **Pooled** | **391** | **39** | **65.2%** | **+0.83%** | **+0.056** | **[-0.042, +0.180]** | **0.134** |

| | 2019-2024 | 2013-2018 | Pooled |
|---|:--:|:--:|:--:|
| Annualised Sharpe | +0.696 | -0.032 | +0.328 |
| Annualisation factor | 5.929 | 5.976 | √(trades/yr) |
| Trades per year | 35.2 | 35.7 | 35.4 |
| Total P&L | +$35,491 | -$5,896 | +$29,596 |
| Max drawdown | -$14,936 | -$24,300 | -$24,300 |
| Profit factor | 1.397 | 0.951 | 1.141 |
| Deflated Sharpe | 0.000113 | 7.4e-10 | ≈ 0 |

**On annualisation.** The factor is √(trades per year) = √35.2 ≈ 5.93, not
√252 ≈ 15.87. An earlier version of this project used √252 on a book that fires
35 times a year, inflating a headline Sharpe by 3.2 times and producing a
figure of +2.04 that stood for about ten days. Every scaled number here states
its factor beside it and
`tests/engine/test_annualisation_regressions.py` fails if anything defaults to
√252. The comparison between blocks was always fair; the levels were not.

**Three rows deserve care, and all three go against the book.** The Deflated
Sharpe is the binding objection: against 1,476 recorded configurations the
expected maximum Sharpe from a family with no edge at all is +0.429, far above
the +0.056 achieved. The worst drawdown is 9.4 times annualised profit, which
is not an allocatable shape regardless of significance. And two calendar years,
2014 and 2022, contribute $32,505 against a twelve-year total of $29,596, so
the aggregate rests on a handful of periods.

### 6.2 Attribution

| Leg | Ordering: theta first | Ordering: spot first |
|---|:--:|:--:|
| Vega | +$355,325 | +$327,603 |
| Theta | +$137,359 | +$43,959 |
| Spot | -$401,692 | -$280,570 |

Vega is the largest positive leg under both orderings, which is what the thesis
requires and is not automatic. An earlier version of the backtest held through
the front expiry, which made the book theta-dominated at +$68,500 theta against
+$1,900 vega while the thesis was about vega. The verdict was meaningless until
exit timing was fixed. Attribution is the check that the P&L is carried by the
driver the thesis names rather than by a confound that happens to co-move.

### 6.3 The Clean Out-of-Sample Block

`events_broad_oos_2025.parquet`, 2,037 events across 346 names, January 2025 to
June 2026, constructed after the 1,476-configuration search had already
concluded. Pre-registered with both kill criteria at
`outputs/research/prereg_oos_2026.json` before the first data request.

| Book | N | Hit | Gross RoM | Net RoM | Per-trade Sharpe | Clustered 95% CI |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Unconditional | 1,221 | 61.0% | +3.44% | +0.49% | +0.043 | [-0.027, +0.120] |
| **Term gate, q = 0.80** | 232 | 46.6% | **+0.07%** | **-3.12%** | **-0.210** | **[-0.347, -0.058]** |
| Random, matched | 224 | 64.3% | +4.11% | +1.18% | +0.105 | [-0.030, +0.270] |

The gate is negative, its interval excludes zero on the wrong side, and a
participation-matched random gate beats it by 3.66 points of return on margin
with a clustered interval of [-0.064, -0.009] that also excludes zero. A
matched random null is the only fair benchmark for a selector, because it holds
trade count and eligible pool fixed and varies only the rule.

**Cost is not the explanation.** The gross column is the diagnostic: 3.44%
unconditional against 0.07% gated. The gate selects events where there was no
premium to collect.

**The mechanism.** Median implied against median realised move is 6.75% against
3.17% unconditionally, a ratio of 2.1, and 7.45% against 6.21% on the gated
book, a ratio of 1.2. A steep term structure does identify events where the
market charges a large implied move. Those are also the events where the large
move happens.

Two earlier and independent results agree. A July decomposition of the gated
book's apparent advantage found roughly 91% of it came from selling a
physically larger option rather than an overpriced one, with the
residual-value term, where genuine overpricing would appear, moving the wrong
way. And the frozen causal threshold applied to the 2013-2018 holdout returned
-0.184 with an interval of [-0.326, -0.033]. Three independent blocks, one
conclusion: **the term-structure gate is a jump-magnitude selector, not a
mispricing detector.**

**Bounds.** Attrition is severe and not random: 1,221 of 2,037 events scored,
606 dropped because the exit leg was unquoted at the strike actually sold, 151
for no two-sided entry quote, 30 for a missing chain, 29 for a missing spot.
Survivors tilt liquid. The gated book's five worst names carry 44.8% of its
loss across 120 names and 92 dates; the clustered interval handles date
clustering, not name concentration. The threshold here is built from
within-block history, which is causally correct for a standalone block but not
identical to the settled book's implementation. One request failed (USB, 19
January 2026) and that event is absent.

### 6.4 Fifteen Selectors on One Basis

Roughly 220 distinct configurations sit on disk. As they sit there they are not
comparable: they mix per-trade with annualised Sharpe, return on premium with
return on margin, and gross with net. Reading a winner off that pile would
repeat a comparison error this project has already made once.

The table below recomputes fifteen selectors from a single 912-event ledger
through a single scorer. Events, marks, costs and denominator are identical in
every row; only the rule changes.

| Selector | N | Names | Hit | Mean RoM | Per-trade Sharpe | 95% CI |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Unconditional | 912 | 45 | 22.6% | -11.42% | -0.642 | [-0.703, -0.590] |
| Random, participation-matched | 205 | 45 | 23.4% | -11.12% | -0.576 | [-0.771, -0.488] |
| Term gate q = 0.70 | 294 | 42 | 24.5% | -11.87% | -0.613 | [-0.713, -0.538] |
| Term gate q = 0.75 | 252 | 39 | 27.0% | -11.51% | -0.585 | [-0.689, -0.504] |
| **Term gate q = 0.80, frozen** | **205** | **37** | **29.3%** | **-10.80%** | **-0.576** | **[-0.688, -0.488]** |
| Term gate q = 0.85 | 156 | 30 | 30.1% | -11.12% | -0.571 | [-0.702, -0.468] |
| Term gate q = 0.90 | 106 | 23 | 30.2% | -10.02% | -0.607 | [-0.779, -0.456] |
| Volatility premium alone | 213 | 37 | 25.8% | -13.22% | -0.599 | [-0.698, -0.518] |
| Variance risk premium alone | 210 | 31 | 26.7% | -13.99% | -0.558 | [-0.657, -0.483] |
| Implied move alone | 213 | 32 | 23.5% | -17.41% | -0.646 | [-0.747, -0.562] |
| Low skew alone | 528 | 45 | 23.9% | -11.52% | -0.609 | [-0.689, -0.547] |
| Low kurtosis alone | 458 | 43 | 25.6% | -13.97% | -0.643 | [-0.724, -0.580] |
| Term q = 0.80 + low skew | 109 | 30 | 33.9% | -10.75% | -0.516 | [-0.653, -0.398] |
| Term q = 0.80 + low kurtosis | 169 | 34 | 31.4% | -10.62% | -0.580 | [-0.704, -0.468] |
| Term q = 0.80 + vol premium | 193 | 34 | 29.5% | -10.69% | -0.567 | [-0.681, -0.477] |

Reproduce with `python scripts/agent_comparison.py`.

**Read the ordering, not the level.** This ledger reprices exits from inverted
implied volatilities instead of marking them off traded prices, and that basis
runs systematically more negative: on the same 239 events, traded marks give
+13.7% where a Black-Scholes reprice gives -34.7%. The levels here are not
comparable to Sections 6.1 or 6.3 and must not be quoted against them.

On that reading, hit rate climbs monotonically with gate tightness, from 22.6%
unconditional to 29.3% frozen and 30.2% at q = 0.90, and the gate beats its
matched random null. **Section 6.3 contradicts that**, on a quote-marked basis,
and the two have not been reconciled. The working explanation is that an
inverted-IV basis penalises large-move events harder than traded marks do,
which would flatter a selector that picks for move size, but that has not been
demonstrated and it is an open item, not a settled reading.

## 7. Limits

- **The margin convention is unvalidated.** `0.20 × spot + premium`, never
  checked against a broker statement, with a probe suggesting IB charges 2.18
  to 2.37 times the modelled figure. Every return-on-margin level in this
  document is contingent on it.
- **Multiple testing dominates.** 1,476 configurations were scored. Against
  that family the expected maximum Sharpe with no edge at all is +0.429. Any
  in-sample selection in this project has to be read against that number.
- **Market impact and capacity are absent.** The execution study measures
  prevailing spreads, not what happens when this book's own order arrives.
- **There is no intraday path.** The position is observed exactly twice. This
  is why a stop-loss cannot be tested: the only post-entry mark is already past
  the gap.
- **Entry spot is stale on some events.** The absolute log difference exceeds
  2% on 16.9% of 1,790 priced events, and on 27.4% of the 391 gated ones
  against 13.9% of non-gated. A partial correction moves pooled Sharpe from
  +0.056 to +0.045. This is the largest unrepaired item and the first thing a
  sceptic should attack.
- **Integer sizing drops the highest-priced names**, a selection on price level
  that is correlated with volatility.
- **Return on margin is not a portfolio return.** Annual return on account is
  0.99%.
- **The live book has no completed trades.** Everything forward-looking here is
  a backtest and is labelled as one.

## 8. Operating Cadence

The scheduled recorder needs no intervention: `.github/workflows/paper_radar.yml`
runs `scripts/paper_radar.py` at 21:15 UTC Monday to Friday and commits its own
book back to this repository as `paper-radar[bot]`.

To run research by hand:

1. `python -m pytest -q`, 645 tests, no network required. If this is not green,
   nothing below is trustworthy.
2. `python scripts/validate_screen.py`, rebuilds the settled book from cached
   marks and checks it reproduces N = 391, Sharpe +0.055992 and the interval
   [-0.0421, +0.1803]. Costs nothing and is the fastest way to confirm the
   machinery before trusting it on something new.
3. `python scripts/run_research.py --real`, the main research run.
4. Any metered pull takes a hard `--cap` in dollars, prices itself with a free
   metadata call before downloading anything, and reserves against the cap
   atomically so concurrent workers cannot jointly overshoot.

Before running a new research question: write the pre-registration first
(hypothesis, exact specification, inference method, success criterion, kill
criterion), declare the trial in the ledger, reuse `engine/` rather than
reimplementing valuation, and score through `engine.screen.score_signal`, which
enforces the reporting contract of N, hit rate, per-trade Sharpe, clustered
interval and a stated annualisation factor.

## 9. What Is Still Open

Ranked by what each would teach us. Section 6.3 puts the selection problem
first.

1. **Replace the selector, testing the obvious null first.** Run the
   unconditional book with only a liquidity and cost screen against the frozen
   gate on a matched sample. It uses data already on disk and settles in a week
   whether three months of selection work pointed the wrong way.
2. **Find a selector that detects mispricing instead of magnitude.** Since 91%
   of the gated book's apparent advantage was selling a physically larger
   option, and the residual-value term moves the wrong way, any new selector
   has to be scored on that residual rather than on realised profit or it will
   keep rediscovering size. A measurement-design problem before it is a signal
   problem.
3. **Cross the spread once instead of twice.** Holding to expiry takes the
   round-trip break-even from 11.6% to roughly 5.8%. On this book's own data a
   conditional hold already returns +17.3% against -4.4% for the next-session
   exit out of sample, on a cut chosen in sample, with a clustered interval on
   the difference of [+0.007, +0.057] and Wilcoxon p = 0.008. It converts the
   trade into a different risk object carrying post-event directional exposure,
   which has to be measured rather than assumed away.
4. **Select on cost, not only on signal.** All 1,476 configurations gated on
   signal variables. Not one gated on cost, despite a 34,672-print spread study
   from which a per-name spread percentile could be built. Mid-seeking exits
   score +12.6% against +0.4% at a full cross on the same book. The obvious
   counter-argument, that tight-spread names are the liquid mega-caps which may
   also be the most efficiently priced, is testable rather than fatal.
5. **Separate the signal from the event.** The term gate is the
   event-conditional special case of an anomaly that works away from earnings.
   Vasquez (2017) reports a long-short of +16.5% per month at t = 10.02 sorting
   on the same slope in the same direction, held to maturity; this book sells
   exactly his short leg. Running the same signal with the event removed
   separates "the signal is empty" from "the announcement is what makes it
   fairly priced". The builder is written and smoke-tested, runs on free data,
   and takes about seven hours checkpointed.
6. **Price what peers already revealed.** Hann, Kim and Zheng (2019) establish
   across 3,030 firms and 217 four-digit industries that a first announcer's
   implied volatility change predicts its peers'. They test no trading strategy
   at all. Whether the implied move charged to a company reporting later is
   stale with respect to information its peers already released is a tradeable
   question the options literature has not absorbed.

**Four doors are closed.** Geographic expansion: India shows no gross edge at
any threshold across 960 events, and Brazil's genuine +6.4% gross signal sits
inside a roughly 24% quoted spread. More events: the power calculation demanded
356 gated trades and 391 arrived. Better fills: measured, worth 0.007 of
per-trade Sharpe. Defined-risk structures: the wing costs more than the entire
cost budget.

## 10. Code Map

| Path | Role |
|---|---|
| `earnings_iv_crush/config.py`, `frozen.py` | Single source of truth. Frozen dataclasses, every field documented, every magic number named. Nothing else defines a default. |
| `earnings_iv_crush/engine/pnl.py` | The reference valuation, `build_trade`. Everything must reconcile to it. |
| `earnings_iv_crush/engine/screen.py` | The reporting contract: N, hit rate, per-trade Sharpe, clustered interval, stated annualisation factor. |
| `earnings_iv_crush/engine/stats.py` | Date-clustered bootstrap, Deflated Sharpe, probabilistic Sharpe. |
| `earnings_iv_crush/data/` | 34 modules, one per source, plus `providers.py`, a market registry so no provider branching leaks into run logic. |
| `earnings_iv_crush/strategy/` | The gates. |
| `earnings_iv_crush/live/` | The IBKR broker layer. |
| `scripts/run_research.py` | Main research run. |
| `scripts/validate_screen.py` | Rebuilds the settled verdict from cache; the fastest integrity check. |
| `scripts/agent_comparison.py` | The Section 6.4 table. |
| `scripts/score_oos_2026.py` | The Section 6.3 re-score. |
| `scripts/paper_radar.py` | The scheduled recorder. |
| `outputs/research/` | 657 artefacts. Superseded ones carry a `_SUPERSEDED` suffix and self-documenting columns rather than being deleted. |
| `outputs/research/audit/` | Per-event SHA-256 lineage over source data, config, costs, marks, P&L and quotes for 2,062 events, plus an independent reconstruction that imports nothing from the package. |

**Invariant-pinning tests**, each naming the defect it guards in its own
docstring: `test_adversarial_invariants.py` (metamorphic, not expected-value:
deleting post-entry records must not change any entry quantity; halving prices
and strikes while doubling contracts must give an identical return; scrambling
outcomes must not change any pre-event selection quantity),
`test_frozen_constants.py`, `test_annualisation_regressions.py`,
`test_fills_rescore_attainability.py`, `test_paper_radar_provenance.py`,
`test_trial_ledger.py`, `test_greeks_reference.py`.

## References

- Patell, J. M., & Wolfson, M. A. (1981). "The Ex Ante and Ex Post Price
  Effects of Quarterly Earnings Announcements Reflected in Option and Stock
  Prices." *Journal of Accounting Research*, 19(2). The original documentation
  of implied volatility rising into an announcement and collapsing after it;
  the basis for the whole trade.
- Dubinsky, A., Johannes, M., Kaeck, A., & Seeger, N. J. (2019). "Option
  Pricing of Earnings Announcement Risks." *Review of Financial Studies*,
  32(2). The modern treatment of a scheduled announcement as a priced jump;
  the basis for using the nearest expiry after the announcement (Section 4.1).
- Goyal, A., & Saretto, A. (2009). "Cross-Section of Option Returns and
  Volatility." *Journal of Financial Economics*, 94(2). The cost assumption
  this project tested and could not reproduce at fixed-time execution
  (Section 4.3).
- Muravyev, D., & Pearson, N. D. (2020). "Options Trading Costs Are Lower Than
  You Think." *Review of Financial Studies*, 33(11). The counterweight; why
  the honest statement is a band rather than a point.
- Vasquez, A. (2017). "Equity Volatility Term Structures and the Cross-Section
  of Option Returns." *Journal of Financial and Quantitative Analysis*, 52(6).
  The term-slope anomaly away from earnings; this book sells his short leg,
  which is the basis for the de-eventised test in Section 9.
- Hann, R. N., Kim, H., & Zheng, Y. (2019). "Intra-Industry Information
  Transfers: Evidence from Changes in Implied Volatility Around Earnings
  Announcements." *Review of Accounting Studies*, 24. Peer implied-volatility
  transfer, established but never traded; the basis for Section 9 item 6.
- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe Ratio."
  *Journal of Portfolio Management*, 40(5). The multiple-testing correction
  applied throughout Section 6 and the binding objection in Section 7.
- Bakshi, G., Kapadia, N., & Madan, D. (2003). "Stock Return Characteristics,
  Skew Laws, and the Differential Pricing of Individual Equity Options."
  *Review of Financial Studies*, 16(1). The model-free skew and kurtosis
  measures used as overlay selectors in Section 6.4.
