# Pre-registration: exogenous cost instruments, stability and macro overlap as selectors for the hedged event hold

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-11-exogenous-cost-and-stability.json`.
Scorer: `research/selection/2026-11-11-exogenous-cost-and-stability/study.py`.

## Hypotheses

The closed spread gates failed because a tight spread is a property of the name, and tight names
carry no gross premium. X1 and X2 vary the cost of the cross from outside the name. X3 and X4 test
the analyst's proposal that calm, predictable companies stay inside the priced range. X5 tests
whether a macro release on the reaction session leaves the seller more.

- **X1, monthly expiry.** When the front expiry the book sells is the standard monthly (third
  Friday), quotes are tighter than on a weekly for the same name, by the accident of where the
  release falls in the calendar. The seller keeps more residual value at the touch.
- **X2, penny tick.** Option classes in the Penny Interval Program quote in USD 0.01 below a
  premium of USD 3 and USD 0.05 at or above it. Events whose average leg mid is just below USD 3
  cross a finer grid than events just above.
- **X3, low idiosyncratic volatility.** The seller keeps more on the calmest names. This is the
  mirror of the closed IVOL trial (Cao and Han, JFE 2013, which predicts the opposite).
- **X4, stable earnings surprises.** The seller keeps more on names whose recent quarterly
  surprises against consensus were small.
- **X5, macro overlap.** The seller keeps more when the reaction session carries a scheduled CPI,
  payrolls or FOMC release.

Nearest closed rows: the megacap and broad spread gates, IVOL and MAX on the hedged hold, analyst
disagreement (trial 1,591), the fundamentals composite (1,605), and the index macro-event studies.

## Data and blocks

- Outcome, cells, loader and statistics: the hedged event hold exactly as in
  `research/selection/2026-11-10-nonprice-selectors-hedged-hold`, whose module this study imports.
- X1 and X2 use only the ledger's own `expiry` and `mid0`.
- X3 uses the stored `ivol` of `outputs/research/2026-11-02-ivol-max-hedged-hold/events.parquet`
  (market-model residual volatility from returns strictly before entry).
- X4 uses IBES `surpsum` quarterly EPS (`actual`, `surpmean`, both on the same split basis),
  linked by the WRDS IBES-CRSP link on permno. IBES ends in 2024.
- X5 uses `data/cache/index_events/macro_releases_2016_2026.csv` (kinds cpi, nfp, fomc).
- Blocks by announcement date. X1, X2, X3: discovery 2013-18, validation 2019-24, confirmation
  2025-26. X4: discovery 2013-18, validation 2019-24. X5: discovery 2016-18, validation 2019-24,
  confirmation 2025-26.
- Outcomes viewed before: the hedged-hold outcome has been split by tenor, implied move, IVOL and
  MAX deciles (top decile reported, bottom not read), and the selectors of trials 1,593 to 1,610.
  It has not been split by expiry type, leg price, surprise history or macro dates.

## Specification

- X1: treated if `expiry` is a Friday with day of month 15 to 21, or a Saturday with day 16 to 22
  (the pre-2015 monthly convention). All events are defined.
- X2: `leg = mid0 / 2`. Defined if `2.0 <= leg <= 4.0`; treated if `leg < 3.0`. The band is one
  dollar either side of the threshold and is not swept. The ledger does not record which classes
  are in the programme, so the contrast is diluted, which works against the hypothesis.
- X3: causal quintiles of `ivol` (`hedged_hold.causal_bins`, 200-event burn-in); treated if in the
  bottom quintile.
- X4: `u = |actual - surpmean| / max(|surpmean|, 0.10)` per quarter; `stab` is the median `u`
  over the last 8 quarterly announcements dated strictly before the entry date, at least 6
  required. Causal quintiles of `stab`; treated if in the bottom quintile.
- X5: treated if `exit_date` (the reaction session) is the date of a cpi, nfp or fomc release.

## Primary statistic and inference

Delta (treated minus untreated residual value per unit of premium, within implied-move tercile and
tenor cell) and the cell-matched null exactly as in the imported study; date-clustered bootstrap,
5,000 draws, seed 0.

## Success criterion

Discovery Delta interval lower bound above zero and null percentile at least 95; then the same on
validation; then, where a confirmation block exists, confirmation Delta above zero and treated
mean H above zero.

## Kill criterion

A miss on either discovery condition closes the trial. An interval wholly below zero is reported
as the opposite sign and is not rescued.

## Limits stated in advance

X1 and X2 are not randomised: monthly expiries cluster in particular reporting weeks, and leg
price co-moves with share price. The tenor and implied-move cells absorb part of this and no more.
The universe is ex-post. The ledger keeps only events with a scoreable hedged hold.

## Trial accounting

Five trials, numbers 1,611 to 1,615.
