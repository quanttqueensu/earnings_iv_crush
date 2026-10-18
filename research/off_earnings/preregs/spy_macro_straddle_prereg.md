# Pre-registration: SPY straddles across scheduled macro releases

## Hypothesis

Index option prices embed a premium for scheduled macro announcement risk. The literature reports
that S&P 500 straddles lose money on data-release days (CPI, payrolls), so the seller earns, and earn
money on FOMC days, so the buyer earns (Londono and Samadi, Federal Reserve IFDP 2023, daily SPX
expirations spanning releases; a University of Delaware dissertation on SPX delta-neutral straddles
around announcements; OptionMetrics practitioner work reporting the same FOMC sign flip). The
earnings programme failed because single-name spreads absorb the premium. SPY at-the-money spreads
are a small fraction of premium, so if the macro premium exists it may survive the touch. This is the
classical-market analogue of the Deribit macro pilot, which failed on BTC options (N=116).

Closest prior work and the difference: the papers above measure premia with mid prices or SPX
settlement on dedicated daily expiries. This test uses the free DoltHub SPY chains, whose shortest
listed expiry is usually one to three weeks out, so the event is a small share of the straddle's
variance; it prices every trade at the touch; and it compares each event with tenor- and
regime-matched ordinary days so the generic daily variance premium is separated from the event
premium.

## Scope and data

- Underlying: SPY. Chains: DoltHub `dolthub/options`, one end-of-day snapshot per trading day,
  2019-01-02 to the last date the source carries for SPY (believed late 2024). The snapshot is the
  source's end-of-day quote; its exact time stamp is not documented. Entry and exit use the same
  snapshot convention, so the bias is common to event and control days.
- Release calendar: `data/cache/spy_macro/releases.csv`, SHA-256
  f0c36526a4d31c9164af3bdc1e21271367a1867181d4bc8ad2963a0fde272e8b, frozen before any price was
  pulled. CPI (71) and payrolls (72) release dates from the BLS archive pages; FOMC decision days
  (47 scheduled meetings, second day of each meeting, unscheduled 2020 meetings excluded) from the
  Federal Reserve calendar pages. Three dates carry both CPI and FOMC (2019-12-11, 2020-06-10,
  2024-06-12): they count in the data-release book and are excluded from the FOMC-only book.
- Not in the calendar: PPI, GDP, retail sales, Fed speeches. Some control days therefore carry minor
  releases, which biases the event-minus-control difference toward zero (conservative).

## Trade construction

- Event day D: a release date that is a trading day. Entry at the D-1 snapshot (the previous trading
  day), exit at the D snapshot. CPI and payrolls print at 08:30 ET on D and FOMC at 14:00 ET on D, so
  every release falls inside the holding window.
- Strike: the strike minimising |call mid - put mid| at entry among strikes with both legs quoted
  (put-call parity locates the forward without an external spot). Expiry: the shortest listed expiry
  strictly after D. The same contracts are priced at exit; a trade is dropped if either leg lacks a
  two-sided quote at entry or exit (logged in the funnel).
- Quotes are usable when 0 < bid <= ask. Mid = (bid + ask) / 2.
- Returns per unit of entry mid premium P0 = call mid + put mid:
  - long, touch: (call bid + put bid at exit - call ask - put ask at entry) / P0;
  - short, touch: (call bid + put bid at entry - call ask - put ask at exit) / P0;
  - mid arms (gross): the same with mids, reported beside the touch arms.
- Control days: every trading day C in the sample with no release in the calendar on C, priced
  identically (entry at C-1, exit at C).
- Matched control for an event: the mean return of control days whose expiry tenor at entry (in
  calendar days) is within 3 days of the event's tenor and whose date is within 60 trading days of
  the event. Events with fewer than 5 matched controls are dropped from the paired statistic (funnel).

## Primary hypotheses and decision rule

Two families, each tested at 97.5% (Bonferroni over the two):

- **A1, data releases (CPI or payrolls), short straddle at the touch.** Pass requires both:
  (i) mean short touch return per trade > 0 with the 97.5% bootstrap interval above zero; and
  (ii) mean paired difference (event short touch return minus its matched control) > 0 with the
  97.5% interval above zero.
- **A2, FOMC only, long straddle at the touch.** Pass requires the same two conditions for the long
  touch return and the paired long difference.

Each event is its own date, so the bootstrap resamples events (equivalently dates): 5,000 draws,
seed 0, percentile intervals. Per-trade Sharpe is reported with the deflated Sharpe ratio against
1,497 prior programme trials plus the trials declared in this session (two here).

A family that passes (i) but not (ii) is recorded as "generic variance premium, not event-specific"
and does not pass. A family that fails (i) is closed.

## Secondary, descriptive only

Results by event type (CPI, payrolls, FOMC), by year, at the mid, and the event-day realised SPY move
against the entry straddle's implied daily move. Tail risk: worst five trades and the largest
drawdown of the event book in units of P0. None of these can rescue a failed primary.

## Mechanism check

For a passing family the realised move on event days must sit on the side the trade needs: for A1,
mean |exit forward - entry forward| / entry forward on release days below the implied event-day move
from the matched-control-adjusted premium; for A2, above it. If the P&L sign and the move evidence
disagree, the result is reported as unexplained and does not pass.

## What is not allowed

No change to strike rule, expiry rule, control matching, window or cost basis after prices are seen.
Any amendment is dated, hashed and reported beside the original.
