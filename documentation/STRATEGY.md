# The Crush Book

A rule-based short-volatility book around scheduled earnings announcements:
single-name US equity options only, one round trip per announcement.

## 1. Purpose and Scope

This document specifies the strategy and reports what happened when that
specification was tested on twelve years of quote-marked option data plus a
clean 2025-26 block that nothing was fitted to.

It covers why the trade should work (Section 3), the exact rules (Section 4),
the data and execution assumptions behind every number (Section 5), how it
performed (Section 6), where it goes next (Section 7), what still needs
validating (Section 8), the protocol any new result has to follow (Section 9),
and where the code lives (Section 10).

It assumes you have read [`README.md`](../README.md), which introduces the project
and defines every term used here in its Section 11 glossary. The narrative of
how the strategy reached this specification is in
[`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md); setup and run instructions are in the
README.

## 2. Executive Summary

The book has three parts:

- **The event engine.** Decides which announcements are tradeable, on what
  session, at what strike and expiry.
- **The selector.** Decides which of those events to take.
- **The cost floor.** 11.6% of premium round trip, measured from roughly 35k
  option market quotes rather than assumed.

**The underlying earnings-volatility effect is clear, and the simplest
unconditional implementation is the most useful baseline going into the year.**
Implied volatility falls on 98.1% of 989 events, attribution puts vega as the
largest positive leg, and on the clean 2025-26 block the unconditional book
returns **+3.44% gross and +0.49% net on margin across 1,221 events at a 61.0%
hit rate**. Its 95% interval is [-0.027, +0.120] and contains zero, so it is a
baseline rather than a finished strategy, but it is a positive one on data no
configuration ever touched.

**The original term-structure selector did not survive the clean block and is
being rebuilt rather than extended.** It returns -3.12% there, with an
interval of [-0.347, -0.058] that excludes zero on the wrong side, and it loses
to a participation-matched random selector. Its gross return is +0.07%, so cost
is not the explanation: it was identifying events where a large move was
expected, and those turned out to be the events where the large move happened.

That diagnosis is what the next selector is built on. The problem is not that
selection cannot work, it is that this rule selected on the size of the move
rather than on the price charged for it, and Section 7 sets out how the next one
is scored so it cannot repeat the error.

The selector stays fully specified below, because it is what the twelve-year
record was produced with and it is the benchmark its replacement has to beat.

## 3. Why the Trade Should Work

**Scheduled announcements are priced as jumps.** An option spanning an earnings
date has to cover a known-date, unknown-magnitude move. The market prices that
by lifting implied volatility on the expiry containing the announcement, hardest
on the nearest expiry, since a fixed jump is a larger share of a shorter
option's total variance. Once the number is public the jump resolves and that
component disappears within a session. Patell and Wolfson (1981) documented the
pattern; Dubinsky, Johannes, Kaeck and Seeger (2019) give the modern
option-pricing treatment. This project measured it directly: implied volatility
falls on **98.1% of 989 events**, by a mean of 48.65 volatility points.

**A crush is not the same thing as a profit.** Whoever is short the straddle
collects the decline in implied volatility and pays for the realised move. The
seller is compensated for carrying overnight gap risk that cannot be hedged,
because the position is observed at the close before and the close after with
nothing tradeable in between. The whole question is whether the compensation
exceeds the risk, and an efficiently priced announcement is one where it does
not.

Every rule below is a version of that tradeoff. Attribution confirms the
mechanism is the one named: vega is the largest positive leg under both path
orderings, the spot leg is the largest negative one, and the correlation between
measured crush and net return is +0.734. The negative spot leg is the gap, and
it is what takes the premium back.

## 4. Model Specification

The exact rulebook, pinned in `earnings_iv_crush/frozen.py` and enforced by
`tests/test_frozen_constants.py`, so changing any constant fails the suite.

```
                   ONE EVENT = ONE EARNINGS ANNOUNCEMENT
   ┌─────────────────────────────────┬──────────────────────────────────┐
   │       T-1  ENTRY  15:59 ET      │      T+1  EXIT  15:59 ET         │
   │  sell 1 ATM straddle, front-    │  buy it back off THAT session's  │
   │  week expiry, strike nearest    │  own chain, same strike, same    │
   │  to spot at the close           │  expiry, NOT at intrinsic        │
   └─────────────────────────────────┴──────────────────────────────────┘

    SELECTOR: front-week IV minus back-month IV, ranked against its own
    strictly-earlier history.  FROZEN AT q = 0.80  ->  BEING REBUILT (6.3)
    The unconditional book, no selector at all, is the current baseline.

    COST FLOOR: 11.6% of premium, round trip. Measured, not assumed.
    P&L = credit - buyback - costs        Denominator = Reg-T margin
```

| Parameter | Value | Meaning |
|---|:--:|---|
| `term_spread_pctl` | 0.80 | Trade only when the term spread sits at or above the 80th percentile of its own past distribution |
| `use_move_gate` | False | The implied-versus-fair-move filter was tested and dropped; it fails its own out-of-sample test |
| `min_hist` | 25 | Minimum prior events before the threshold is computed at all |
| Vehicle | naked short ATM straddle | The only structure positive net of asymmetric cost |
| Entry | last session before, 15:59 ET | |
| Exit | first session after, 15:59 ET | |
| `sizing_fraction` | 0.05 | Margin per position as a fraction of a 250,000 account |

### 4.1 The Event Engine

1. **Build the calendar.** Announcement dates come from Finnhub or from
   Compustat `fundq.rdq` via a WRDS mirror, with a before-open or after-close
   field. That field decides the entry session, and getting it wrong means
   holding through the announcement twice or not at all.
2. **Cross-check the session two of three.** The vendor's field is checked
   against SEC EDGAR 8-K Item 2.02 acceptance timestamps and a third source
   before a session is trusted. A filing accepted at 16:31 ET is an after-close
   print regardless of what the calendar says.
3. **Pick the expiry.** Nearest listed expiry strictly after the announcement,
   because a shorter option carries a larger share of the jump.
4. **Pick the strike.** Nearest listed strike to spot at the entry close.
   At-the-money maximises vega, which is the leg the thesis is about, and
   minimises the directional exposure that is not.
5. **Guard against corporate actions.** An overnight move that is really a
   split, special dividend or spin-off is rejected rather than booked as an
   announcement move.

### 4.2 The Selector

**Score.** Front-week at-the-money implied volatility minus back-month
at-the-money implied volatility. A steep term structure means the market is
charging a lot for the event specifically, over and above the name's ordinary
volatility.

**Rank causally.** The threshold at event *i* uses only events with a strictly
earlier announcement date, on an expanding window, with at least 25 prior
events before any threshold exists. This is not a technicality: an earlier
version used the full-sample 80th percentile, which is look-ahead and was worth
roughly 0.05 of per-trade Sharpe on its own. The `min_hist` floor exists
because a rolling quantile with no minimum-periods guard once produced an
all-NaN threshold on thin history and silently rejected every event, so a real
run "worked" and took zero trades.

**Trade the top 20%.** q = 0.80 was chosen on a grid over 2019 to 2024 and then
frozen. It sits on a broad flat region rather than a spike, which is the only
reason to trust a chosen parameter, though Section 8 covers what the grid cost
in multiple-testing terms.

Section 6.3 covers why this rule is being rebuilt rather than extended.

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
multiplier and contract count. See Section 8 on its calibration.

## 5. Data and Execution Assumptions

Rules designed to stop the book using information it would not have had:

- Option marks are **OPRA consolidated best bid and offer**, sampled once a
  minute, snapshotted at the last quote at or before 15:59 ET. Both sides are
  genuine quotes; a one-sided quote never becomes a mid.
- The exit is marked off **the exit session's own chain**, at the strike and
  expiry actually sold.
- Signals use only data dated strictly before the entry close.
- Costs are charged at the measured 1.7871% per side plus commission on all four
  legs.
- One contract per event, so return on margin is invariant to sizing.
- An event is dropped, with a stated reason and a printed funnel, rather than
  filled with a fallback, whenever the chain is missing, the spot is missing, or
  either leg is unquoted.

An earlier forward estimator incorrectly treated the exit as intrinsic value
rather than the price of the remaining option. That defect materially overstated
returns and has been removed. All valuation paths now reconcile to
`engine/pnl.py::build_trade`, with regression tests preventing the shortcut from
returning.

## 6. Results

### 6.1 The Twelve-Year Book

Frozen specification, quote-marked, nothing retuned between blocks. The 2013 to
2018 block was built after the first was scored and is a true holdout.

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

The annualisation factor above is not a chosen constant. A Sharpe annualises by
the square root of the observations in a year, and the period has to match the
series the ratio was computed on (Lo, 2002); the unit here is a trade, so
`infer_periods_per_year` reads the realised rate off each block's own calendar
span, which is why the two blocks carry 5.929 and 5.976 rather than a shared
figure. The daily convention √252 ≈ 15.87 is correct for a daily series and
wrong for this one: an earlier version applied it to a book firing 35 times a
year and inflated a headline Sharpe 3.2 times.
`tests/engine/test_annualisation_regressions.py` fails if anything defaults back
to it.

The complementary basis is `calendar_sharpe`, which builds the daily series,
charges zero to every session the book is flat and annualises by √252. That
measures what committed capital earns rather than whether the signal selects.
The two coincide for a book holding one position at a time and diverge when
positions overlap, which happens here because earnings cluster into four windows
a year and several straddles share exit dates.

Two things bound this result. The Deflated Sharpe is the binding one: against
1,476 recorded configurations the expected maximum Sharpe from a family with no
edge is +0.429, well above the +0.056 achieved. And two calendar years, 2014 and
2022, contribute $32,505 against a twelve-year total of $29,596, so the
aggregate rests on a handful of periods.

### 6.2 Attribution

| Leg | Ordering: theta first | Ordering: spot first |
|---|:--:|:--:|
| Vega | +$355,325 | +$327,603 |
| Theta | +$137,359 | +$43,959 |
| Spot | -$401,692 | -$280,570 |

Vega is the largest positive leg under both orderings, which is what the thesis
requires and is not automatic. An earlier version held through the front expiry,
which made the book theta-dominated at +$68,500 theta against +$1,900 vega while
the thesis was about vega. The verdict was meaningless until exit timing was
fixed.

### 6.3 The Clean Out-of-Sample Block

`events_broad_oos_2025.parquet`, 2,037 events across 346 names, January 2025 to
June 2026, constructed after the 1,476-configuration search had concluded.
Pre-registered with both kill criteria at
`outputs/research/prereg_oos_2026.json` before the first data request.

| Book | N | Hit | Gross RoM | Net RoM | Per-trade Sharpe | Clustered 95% CI |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Unconditional | 1,221 | 61.0% | +3.44% | +0.49% | +0.043 | [-0.027, +0.120] |
| **Term gate, q = 0.80** | 232 | 46.6% | **+0.07%** | **-3.12%** | **-0.210** | **[-0.347, -0.058]** |
| Random, matched | 224 | 64.3% | +4.11% | +1.18% | +0.105 | [-0.030, +0.270] |

**The original selector does not carry forward.** It is negative, its interval
excludes zero on the wrong side, and a participation-matched random selector
beats it by 3.66 points of return on margin with a clustered interval of
[-0.064, -0.009]. A matched random null is the only fair benchmark for a
selector, because it holds trade count and eligible pool fixed and varies only
the rule.

**What the broader testing showed.** Cost is not the explanation. The gross
column is the diagnostic: 3.44% unconditional against 0.07% gated. The gate was
selecting events where there was no premium to collect. The mechanism is visible
in the moves: median implied against median realised is 6.75% versus 3.17%
unconditionally, a ratio of 2.1, and 7.45% versus 6.21% on the gated book, a
ratio of 1.2. A steep term structure does identify events where the market
charges a large implied move. Those are also the events where the large move
happens.

Two earlier and independent results agree, which is why this reads as a finding
rather than an unlucky block. A July decomposition found roughly 91% of the
gated book's apparent advantage came from selling a physically larger option
rather than a more expensive one, with the residual-value term moving the wrong
way. And the frozen threshold applied to the 2013-2018 holdout returned -0.184,
interval [-0.326, -0.033]. Three independent blocks, one conclusion: the
term-structure signal measures jump magnitude, not mispricing.

Attrition bounds this: 1,221 of 2,037 events scored, with 606 dropped because
the exit leg was unquoted at the strike actually sold, so survivors tilt toward
more liquid names. The gated book's five worst names carry 44.8% of its loss.

### 6.4 Fifteen Selectors on One Basis

Fifteen selectors were also rescored on one common ledger, so that events, marks,
costs and denominator were identical in every row and only the selection rule
changed. Tightening the term gate raised the hit rate monotonically, from 22.6%
unconditional to 30.2% at the tightest threshold, and the skew and kurtosis
overlays improved on the term gate alone. None of that ordering carried over to
the clean quote-marked block in Section 6.3, and the two disagree on whether the
gate beats a matched random null. That ledger reprices exits from inverted
implied volatilities rather than marking them off traded prices, which runs
systematically more negative and is the likely reason, but it has not been
demonstrated and the comparison is not settled. Reproduce with
`python scripts/agent_comparison.py`.

## 7. Where the Strategy Goes Next

Ranked by what each would teach us. Section 6.3 puts the selection problem
first.

1. **Build an execution-aware selector.** Run the unconditional book with only a
   liquidity and cost screen against the frozen gate on a matched sample. It
   uses data already on disk and settles in a week whether the last three months
   of selection work pointed the wrong way. None of the 1,476 configurations
   ever gated on cost, despite a 34,672-print spread study being available to
   build a per-name spread percentile from. Mid-seeking exits score +12.6%
   against +0.4% at a full cross on the same book.
2. **Find mispricing rather than magnitude.** Since 91% of the gated book's
   apparent advantage was selling a physically larger option, and the
   residual-value term moves the wrong way, any new selector has to be scored on
   that residual rather than on realised profit or it will keep rediscovering
   size. This is a measurement-design problem before it is a signal problem.
3. **Revisit the exit.** Holding to expiry takes the round-trip break-even from
   11.6% to roughly 5.8%. A conditional hold already returns +17.3% against
   -4.4% for the next-session exit out of sample, with a clustered interval on
   the difference of [+0.007, +0.057] and Wilcoxon p = 0.008. The specific cut
   was chosen in sample, so this needs freezing and revalidating rather than
   extending. It also converts the trade into a different risk object carrying
   post-event directional exposure, which has to be measured.
4. **Separate the signal from the event.** The term gate is the
   event-conditional special case of an anomaly that works away from earnings.
   Vasquez (2017) reports a long-short of +16.5% per month at t = 10.02 sorting
   on the same slope in the same direction, held to maturity; this book sells
   his short leg. Running the signal with the event removed separates "the
   signal is empty" from "the announcement is what makes it fairly priced". The
   builder is written and smoke-tested and runs on free data.
5. **Price what peers already revealed.** Hann, Kim and Zheng (2019) establish
   across 3,030 firms and 217 four-digit industries that a first announcer's
   implied volatility change predicts its peers'. They test no trading strategy
   at all. Whether the implied move charged to a company reporting later is
   stale with respect to information its peers already released is a tradeable
   question the options literature has not absorbed.

**Directions we are not prioritising.** Geographic expansion: India shows no
gross edge at any threshold across 960 events, and Brazil's genuine +6.4% gross
signal sits inside a roughly 24% quoted spread. More events: the power
calculation demanded 356 gated trades and 391 arrived. Better fills: measured,
worth 0.007 of per-trade Sharpe. Defined-risk structures: the wing costs more
than the entire cost budget.

## 8. Current Constraints and What Still Needs Validation

The main remaining implementation risks are broker-margin calibration, stale
entry spot on some events, capacity and market impact, and the absence of an
intraday path. Return-on-margin levels should therefore be treated as relative
research measures rather than deployable portfolio returns, and the forward book
is still far too young to provide evidence in either direction.

In more detail:

- **Margin calibration.** `0.20 × spot + premium` has never been checked against
  a broker statement, and a probe suggests IB charges 2.18 to 2.37 times the
  modelled figure. Comparisons between books on the same convention are sound;
  absolute levels are not. Annual return on account works out at 0.99%.
- **Stale entry spot.** The absolute log difference exceeds 2% on 16.9% of 1,790
  priced events, and on 27.4% of the 391 gated ones. A partial correction moves
  pooled Sharpe from +0.056 to +0.045. This is the largest unrepaired item and
  the first thing a sceptic should attack.
- **Multiple testing.** 1,476 configurations were scored, so every in-sample
  result here is read against an expected maximum Sharpe of +0.429 under no
  edge. The trial ledger counts abandoned branches for exactly this reason.
- **No intraday path.** The position is observed exactly twice, which is why a
  stop-loss cannot be tested: the only post-entry mark is already past the gap.
- **Integer sizing** drops the highest-priced names, a selection on price level
  correlated with volatility.

## 9. Research Protocol

Every result in this document was produced under the following rules, and any
new result is expected to follow them. Setup and the commands themselves are in
[`README.md`](../README.md) Section 10.

1. **Pre-register first.** Write the hypothesis, the exact specification, the
   inference method, the success criterion and the kill criterion before the
   first data request. A test whose criteria are written afterwards can always be
   reinterpreted into a success.
2. **Declare the trial in the ledger,** including branches you abandon. Every
   Sharpe in this project is read against that count, so an undeclared trial
   flatters everything else.
3. **Check the machinery before trusting it.** `python -m pytest -q` must be
   green, and `python scripts/validate_screen.py` must reproduce N = 391,
   Sharpe +0.055992 and the interval [-0.0421, +0.1803] from cache. Both are free
   and fast, and neither result is meaningful if they are not.
4. **Reuse `engine/` rather than reimplementing valuation.** Score through
   `engine.screen.score_signal`, which enforces the reporting contract of N, hit
   rate, per-trade Sharpe, clustered interval and a stated annualisation factor.
   The exit-marking defect in Section 5 came from a separate estimator; that is
   the failure mode this rule exists to prevent.
5. **Cap any metered pull.** Metered requests take a hard `--cap` in dollars,
   price themselves with a free metadata call before downloading anything, and
   reserve against the cap atomically so concurrent workers cannot jointly
   overshoot.

## 10. Code Map

| Path | Role |
|---|---|
| `earnings_iv_crush/config.py`, `frozen.py` | Single source of truth. Frozen dataclasses, every field documented, every magic number named. Nothing else defines a default. |
| `earnings_iv_crush/engine/pnl.py` | The reference valuation, `build_trade`. Everything must reconcile to it. |
| `earnings_iv_crush/engine/screen.py` | The reporting contract: N, hit rate, per-trade Sharpe, clustered interval, stated annualisation factor. |
| `earnings_iv_crush/engine/stats.py` | Date-clustered bootstrap, Deflated Sharpe, probabilistic Sharpe. |
| `earnings_iv_crush/data/` | 34 modules, one per source, plus `providers.py`, a market registry so no provider branching leaks into run logic. |
| `earnings_iv_crush/strategy/` | The selection rules. |
| `earnings_iv_crush/live/` | The IBKR broker layer. |
| `scripts/run_research.py` | Main research run. |
| `scripts/validate_screen.py` | Rebuilds the settled verdict from cache; the fastest integrity check. |
| `scripts/agent_comparison.py` | The fifteen-selector comparison in Section 6.4. |
| `scripts/score_oos_2026.py` | The Section 6.3 re-score. |
| `outputs/research/` | 657 artefacts. Superseded ones carry a `_SUPERSEDED` suffix rather than being deleted. |
| `outputs/research/audit/` | Per-event SHA-256 lineage over source data, config, costs, marks, P&L and quotes for 2,062 events, plus an independent reconstruction that imports nothing from the package. |

The two `outputs/research/` rows are generated locally and are git-ignored, so
they are described here but do not arrive with a clone. Publishing them is the
onboarding task noted in [`README.md`](../README.md) Section 10.

Invariant-pinning tests, each naming the defect it guards in its own docstring:
`test_adversarial_invariants.py` (metamorphic rather than expected-value:
deleting post-entry records must not change any entry quantity; halving prices
and strikes while doubling contracts must give an identical return; scrambling
outcomes must not change any pre-event selection quantity),
`test_frozen_constants.py`, `test_annualisation_regressions.py`,
`test_fills_rescore_attainability.py`, `test_trial_ledger.py`,
`test_greeks_reference.py`.

## References

- Patell, J. M., & Wolfson, M. A. (1981). "The Ex Ante and Ex Post Price Effects
  of Quarterly Earnings Announcements Reflected in Option and Stock Prices."
  *Journal of Accounting Research*, 19(2). The original documentation of implied
  volatility rising into an announcement and collapsing after it.
- Dubinsky, A., Johannes, M., Kaeck, A., & Seeger, N. J. (2019). "Option Pricing
  of Earnings Announcement Risks." *Review of Financial Studies*, 32(2). The
  modern treatment of a scheduled announcement as a priced jump; the basis for
  using the nearest expiry after the announcement.
- Goyal, A., & Saretto, A. (2009). "Cross-Section of Option Returns and
  Volatility." *Journal of Financial Economics*, 94(2). The cost assumption this
  project tested and could not reproduce at fixed-time execution.
- Muravyev, D., & Pearson, N. D. (2020). "Options Trading Costs Are Lower Than
  You Think." *Review of Financial Studies*, 33(11). The counterweight; why the
  honest statement is a band rather than a point.
- Vasquez, A. (2017). "Equity Volatility Term Structures and the Cross-Section of
  Option Returns." *Journal of Financial and Quantitative Analysis*, 52(6). The
  term-slope anomaly away from earnings; the basis for Section 7 item 4.
- Hann, R. N., Kim, H., & Zheng, Y. (2019). "Intra-Industry Information
  Transfers: Evidence from Changes in Implied Volatility Around Earnings
  Announcements." *Review of Accounting Studies*, 24. Peer implied-volatility
  transfer, established but never traded; the basis for Section 7 item 5.
- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe Ratio."
  *Journal of Portfolio Management*, 40(5). The multiple-testing correction
  applied throughout Section 6.
- Bakshi, G., Kapadia, N., & Madan, D. (2003). "Stock Return Characteristics,
  Skew Laws, and the Differential Pricing of Individual Equity Options." *Review
  of Financial Studies*, 16(1). The model-free skew and kurtosis measures used as
  overlay selectors in Section 6.4.
- Lo, A. W. (2002). "The Statistics of Sharpe Ratios." *Financial Analysts
  Journal*, 58(4). The derivation of the square-root-of-time annualisation rule
  and of where it fails; the basis for annualising by the series' own realised
  observation rate rather than by a fixed calendar constant.
