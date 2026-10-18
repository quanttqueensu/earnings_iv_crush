# Pre-registration: P2, the de-eventised term-structure slope

Frozen before any outcome is computed and before any option chain for the sample is pulled.
Changes after an outcome is viewed require a dated amendment. SHA-256 recorded in
`outputs/research/prereg_p2_term_slope.json`. State of record section 2.4.

## Hypothesis

The slope of the implied-volatility term structure predicts straddle returns away from earnings
announcements. Vasquez (JFQA 2017) sorts on `IV_LT - IV_1M` and finds the highest-slope straddles
outperform the lowest-slope ones (long-short +16.5% per month, t = 10.02, held to maturity,
OptionMetrics 1996-2007 era). The earnings book sold straddles on Vasquez's short leg (front IV
far above the back) and every version of it failed after costs. Testing the same slope with the
announcement removed separates two readings: the signal is empty, or the announcement is what
makes the front leg fairly priced.

**Mechanism.** A front expiry priced well above the back reflects short-horizon demand for
volatility exposure (or a transient shock) that mean-reverts; market makers charge for absorbing
it, so a straddle on the front of a steep (negative-slope) term structure is rich and one on an
upward-sloping (positive-slope) structure is cheap. Away from scheduled events nothing
fundamental justifies the front premium, so it should be earned by the short leg and the long
leg should not pay it.

**Mechanism check.** At the mid, mean long-straddle return rises with the slope quintile:
Spearman(quintile, mean mid long-straddle return) at least +0.70. A pass of the primary
criterion whose mechanism check fails is reported as unexplained, not as a result.

## Scope

**Data.** Free DoltHub option chains, `post-no-preference/options`, table `option_chain`
(publisher bid, ask and implied volatility). Coverage probes before this freeze (row counts and
expiration dates on AAPL only, no prices) show data from January 2021 to the present and
exactly three listed expiries per snapshot, near 14, 28 and 49 days. This is therefore a
**short-dated construction** of the slope and must be labelled as such, never as a Vasquez
replication: there is no long-dated leg. Underlying closes from yfinance, un-adjusted for splits
with yfinance's split record so they sit on the strikes' contemporaneous basis. Zero spend.

**Universe.** The 70 names in `DEFAULT_UNIVERSE` of `scripts/pivot_vasquez_slope.py`, fixed in
advance (liquid optionable US large caps across sectors). META is queried as FB on dates before
2022-06-09. The list is today's large caps, so the sample carries survivorship by construction;
it is reported, not corrected.

**Sample period.** Formation on the last trading day of each month with data, January 2021 to
August 2026 inclusive (68 formation months), each snapshot resolved by stepping back at most
five calendar days from the month-end. Any formation month whose holding window cannot complete
within coverage is dropped and counted.

**Earnings exclusion.** A name-month is excluded if any earnings announcement falls on or between
the formation date and the traded straddle's expiry date, inclusive of both ends (an
after-close announcement on the formation date and a before-open one on the expiry date both
count). Announcement dates are the union of DoltHub `post-no-preference/earnings`
`earnings_calendar` and Compustat `fundq.rdq` from the R2 mirror where it covers the date: a
month is excluded if either source places an event in the window. Realised announcement dates
are used; scheduled dates are public weeks ahead, so this is not a material look-ahead.

## Specification

**Signal.** At formation, `slope = IV_back - IV_front`, Vasquez's sign: IV_front is the mean
implied volatility of the nearest-to-money call and put contracts with 7 to 20 days to expiry,
IV_back the same for 35 to 59 days (the builder's `_atm_iv`, nearest six contracts by
moneyness), moneyness measured against the formation close. A steep front (the earnings gate's
trigger) is a negative slope.

**Traded straddle and holding period.** The at-the-money straddle on the middle expiry (21 to 34
days), strike nearest the formation close among strikes where both the call and the put have
`ask > bid > 0`, bought or sold at formation and **held to expiry**, settled at intrinsic
`|S_T - K|` on the unadjusted close of the expiry date (the prior session if the expiry date is
not a trading day). Holding to expiry follows Vasquez and means one spread crossing. Holding
windows are about four weeks from consecutive month-ends, so overlap between consecutive
formations is at most a few days.

**Sort and legs.** Each formation month, eligible names (signal and traded straddle both
available, not excluded) are sorted into slope quintiles; a month with fewer than 10 eligible
names is skipped and counted. Long the top quintile (highest slope), short the bottom quintile.

**Two arms, side by side.**
- Mid: entry at the straddle mid.
- Full touch: the long leg pays the straddle ask (call ask plus put ask), the short leg receives
  the straddle bid. Settlement at intrinsic carries no further spread.

Per-trade returns on straddle premium: long `(payoff - P_entry) / P_entry`, short
`(P_entry - payoff) / P_entry`, with `P_entry` the arm's entry price. Commissions and exercise
or assignment costs are not charged; the touch arm is the cost basis.

**Primary statistic.** The long-short mean per trade on the full-touch arm: the pooled mean of
long-leg trade returns plus the pooled mean of short-leg trade returns (Vasquez's high-minus-low
in per-trade units, return on premium, one holding period of about four weeks, not annualised).
Interval: date-clustered percentile bootstrap resampling formation dates (all trades formed on a
date move together), 5,000 draws, seed 0.

**Matched null.** Within each formation month, slopes are randomly permuted across the eligible
names (leg sizes per month preserved) and the touch long-short statistic recomputed; 1,000 draws,
seed 0. Reported as the observed statistic's percentile.

**Deflation.** Monthly long-short series (one value per formation month, touch arm), its Sharpe
deflated against the programme's 1,497 recorded trials with `sr_trials_std` from
`outputs/research/performance_panel.csv`. This test is one trial (count 1,498 after it).

## Success and kill rule

**Pass** requires both: the full-touch long-short 95% CI lies entirely above zero, and the
observed full-touch statistic exceeds the 95th percentile of the matched null.

**Kill rule.** If the full-touch long-short interval includes zero, the short-dated
de-eventised slope is not monetisable by a liquidity taker on this data, and P2 closes. An
interval entirely below zero also fails and is reported as a reversed sign.

## Reported either way (no bearing on the verdict)

Mid-arm long-short with its clustered CI; quintile means of the long-straddle return on both
arms; hit rates; the funnel from the 4,760 ticker-months to scored trades; a clean-signal
subsample that also excludes any event inside the back leg's window (formation to 59 days),
since an event just beyond the hold inflates IV_back; and the DSR. Pre-stated counter-argument:
the mid-priced premium Vasquez reports is a liquidity-provision premium, and the fills study on
this project (median price improvement zero, 54.3% of prints at the full touch) predicts that a
taker pays it away, so a positive mid arm with a touch interval through zero is the expected
failure mode and would be the same finding as every other test in the programme.

## Prior work

Vasquez (JFQA 2017), the slope sort; Goyal and Saretto (JFE 2009), implied-minus-realised sorts
and their spread sensitivity; Dubinsky, Johannes, Kaeck and Seeger (RFS 2019), the announcement
component of the term structure this test removes; Alexiou et al. (RoF 2025) on option spreads
and anomaly returns. This version differs by excluding every name-month with an announcement in
the holding window, by using a 14-day against 49-day construction on free data from 2021, and by
reporting the full-touch arm as primary.

## Process

An eight-row smoke-test panel of the signal from an earlier build exists at
`outputs/research/pivot/vasquez_panel.parquet`; no outcome was ever scored from it and it is not
reused. No straddle return, settlement price or sort outcome for the sample has been computed or
viewed before this freeze.
