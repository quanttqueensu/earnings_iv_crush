# Pivot research dossier

Specifications extracted from source papers, not from recall. Each entry records what the original
did, what it reported, where it is weakest, and what this version would add. Candidates whose
differentiation answer is "nothing" are marked replication-only and excluded from the test queue.

Numbering follows the approved plan. Status labels: **verified** (source PDF read this session),
**partial** (abstract and secondary sources only).

---

## Cross-cutting findings

Three facts emerged that apply across candidates and change the test design.

### 1. The options-anomaly literature rests on a cost assumption this project has already measured

Every large reported option-return anomaly in this dossier handles transaction costs the same two
ways, and both are contradicted by measurement already in hand.

Saretto argues (verified) that the average volume-weighted quoted bid-ask spread on near-ATM
options with 30 to 60 days to expiry is **8.0%**, and that profitability survives because "the
effective spread is generally lower than the quoted one, so that the actual cost should be lower
than 8%". Vasquez handles it differently (verified): "to avoid paying high transaction costs more
than once, options are held until maturity", so the spread is crossed once rather than twice.

The fills study run on this project measured 34,672 prints against their prevailing consolidated
spreads and found **median price improvement of zero, with 54% of prints paying the full touch**.
That is a direct empirical contradiction of the first assumption at fixed-time execution. The second
assumption, hold-to-maturity, was independently rediscovered here as the conditional-exit result and
is sound, but it converts the trade into a different risk object with post-event directional
exposure.

**This is the differentiation answer for the entire Tier B family.** These are not replications. The
contribution is re-scoring documented option anomalies on measured rather than assumed execution,
using a measurement the original authors did not have. A negative result is publishable and useful;
a positive one is a genuine finding.

### 2. Two of the scheduled candidates are not independent tests

Vasquez reports (verified) that the slope of the volatility term structure has a **46.3%**
correlation with `HV - IV1M`, the Goyal and Saretto anomaly measure, and 29.2% with
`idioVol - IV1M`. Candidates #6 and #7 are therefore close to the same bet. They must be tested
jointly, with the incremental contribution of each reported, or the trial ledger will overstate how
many independent shots were taken.

### 3. Sample-period overlap is severe

Saretto runs January 1996 to June 2005; Vasquez uses OptionMetrics from 1996; Hann, Kim and Zheng
run 1996 to 2017; Bollerslev, Tauchen and Zhou run January 1990 to December 2007. The free option
data available here (DoltHub, roughly 2019 to late 2024) **does not overlap any of them**. Every
options-based test below is therefore an out-of-sample test on a later regime, not a replication.
That is a strength for inference and a weakness for power, and it must be stated in any writeup.

---

## #3 Index VRP timing (scheduled first)

**Status: verified.** Bollerslev, Tauchen & Zhou, *Expected Stock Returns and Variance Risk Premia*,
RFS 22(11), 2009.

- **Signal.** Variance risk premium as `IV_t - RV_t`. `IV_t` is the **squared VIX** index, monthly,
  representing risk-neutral variance at fixed 30-day maturity, taken directly from CBOE. `RV_t` is a
  model-free realised variance built from the summation of **five-minute** intraday S&P 500 squared
  returns over the month.
- **Specification.** Predictive regression of scaled h-period excess returns on the variance
  difference, h from 1 to 24 months, monthly observations, overlapping. Standard errors follow
  Hodrick (1992) rather than Newey-West, on the grounds that summing regressors backwards is more
  reliable than summing residuals forwards for overlapping data.
- **Sample.** January 1990 to December 2007.
- **Reported effect.** Monthly horizon R² "just above 1%". **Quarterly horizon: robust t = 2.86,
  adjusted R² = 6.82%.** Significant at six months, tapering thereafter. Combining the variance
  difference with the P/E ratio lifts the monthly R² to 3.77%, exceeding the sum of the individual
  R² values.
- **Weakest link, flagged by the authors themselves.** Boudoukh, Richardson and Whitelaw show that
  with persistent predictors and overlapping returns, R² rises roughly proportionally with the
  horizon **by construction**, absent any true increase in predictability. The headline result is a
  peak in R² at exactly the horizon where this artefact is growing. The authors note the caution;
  they do not fully neutralise it.
- **Feasibility constraint, material.** The paper states the results depend crucially on realised
  variance from **high-frequency intraday rather than daily** data. Five-minute S&P 500 data is not
  available at zero spend here. Daily-return-based RV is a documented downgrade, so the replication
  will be attenuated by construction and any weakening cannot be interpreted as decay.
- **Differentiation.** Two things. First, extend the sample: `cboe_all.cboe` carries VIX from
  1986-01-02 to 2026-06-30, roughly **19 additional years** beyond the original window, including
  2008, 2020 and the post-2020 regime. Second, test the Boudoukh critique directly by reporting the
  horizon profile against a persistence-matched placebo, which the original did not do.
- **Verdict: proceed.** Primary value is harness validation. If the screen cannot recover a
  quarterly-horizon peak on the original window, the screen is wrong.

---

## #1 PEAD / SUE (scheduled second)

**Status: verified**, via *The Post-Earnings Announcement Drift: An Anomalous Anomaly*, a sceptical
re-examination, rather than Bernard and Thomas (1989) directly.

- **Signal.** Standardised unexpected earnings. Firms sorted into SUE deciles using cutoffs from the
  **prior** quarter's SUE distribution, explicitly to avoid the look-ahead bias that ranking on the
  current quarter's distribution would inject.
- **Sample.** 1985 Q1 to 2014 Q2, 118 quarters. Drift measured over the 13 weeks following
  announcement.
- **Classic reported effect.** Bernard and Thomas: top-minus-bottom SUE decile roughly 4.2% over 60
  trading days, NYSE and AMEX, 1974 to 1986.
- **Weakest link, and it is severe.** The re-examination finds the **monotonic drift pattern does not
  persist**. The SUE percentile with the most negative news experiences the *least* negative drift of
  all percentiles in the bad-news decile. A refined strategy buying percentile 99 and selling
  percentile 3 returns roughly 10% per quarter, but the authors state plainly: "we know of no reason
  to predict ex-ante that SUE Percentile 3 should result in the most negative drift."
- **This is the same failure mode that killed the IV-crush book**: the best-looking cell selected
  ex post from a grid, with no prior reason to expect it. Treat that 10%/quarter figure as
  uninvestable and never quote it.
- **Differentiation.** Weak as a plain replication. The defensible version is to run it as a
  **pre-registered monotonicity test** rather than a long-short: does drift increase monotonically in
  SUE, with the ordering fixed in advance. That converts a crowded anomaly into a falsifiable
  statement and directly exercises the trial ledger.
- **Verdict: proceed, but reframed.** Not as an alpha candidate. As a test of whether the equity path
  through `wrds_panel` and `event_study.car` produces correct, well-powered results on a known effect.

---

## #6 IV term-structure slope, de-eventised (scheduled third)

**Status: verified.** Vasquez, *Equity Volatility Term Structures and the Cross-Section of Option
Returns*, draft of 16 May 2014.

- **Signal.** Slope defined as `IV_LT - IV_1M`, the long-term minus short-term implied volatility.
  `IV_1M` is the average of the one-month at-the-money call and put implied volatilities.
- **Construction.** Monthly sort of firms into deciles on the slope. Decile portfolios contain
  one-month ATM options. **Options are held until maturity**, explicitly so the large transaction
  cost is paid once rather than twice.
- **Universe and sample.** OptionMetrics Ivy DB, from 1996.
- **Reported effect.** Lowest-slope decile: **-9.2% average monthly straddle return.** Highest-slope
  decile: **+7.3%.** Long-short: **+16.5% per month, t = 10.02.** Carhart, coskewness and cokurtosis
  alphas are close to the raw returns. Robust across periods, horizons, moneyness, weighting schemes,
  and alternative slope definitions.
- **Direct relevance to the dead project.** A high front-week-minus-back-month term spread is a
  *negative* slope in this convention. The IV-crush book sold straddles on exactly those names, which
  is Vasquez's **short leg**. The gate direction was correct. What the book added was the earnings
  event, and with it the announcement gap risk that makes single-name event variance fairly priced.
- **Weakest link.** A gross long-short return of 16.5% per month at t = 10.02 against an 8% quoted
  round-trip spread is the entire question. The paper resolves it by holding to maturity, which
  halves the crossing but does not eliminate it, and does not measure realised fills.
- **Correlation caveat.** 46.3% correlated with the Goyal-Saretto `HV - IV1M` measure. Not an
  independent test from #7.
- **Differentiation, and it is the strongest on the list.** This is the single experiment that
  separates two hypotheses the project cannot currently distinguish: *the term signal is empty* versus
  *the earnings event was the problem*. Same signal, same direction, same `term_panel.py` code, event
  removed. Combined with measured-execution rescoring, it also tests the literature's cost assumption
  on the exact anomaly where that assumption is doing the most work.
- **Verdict: proceed. Highest-information candidate.**

---

## #13 Volatility information transfer (scheduled fourth)

**Status: verified.** Hann, Kim & Zheng, *Intra-industry Information Transfers: Evidence from Changes
in Implied Volatility around Earnings Announcements*, Review of Accounting Studies (2019), draft of
October 2018.

- **Design.** Identify the **first announcer** in each industry-quarter. Match to industry peers
  announcing **at least 10 trading days after** the first announcer. Test the association between the
  change in the first announcer's implied volatility and the change in peers' implied volatility
  around the initial release.
- **Sample.** 3,030 unique firms, **217 industries at the 4-digit SIC level**, 1996 to 2017.
  Implied volatility from exchange-traded option prices.
- **Reported effect.** Significantly positive association between first-announcer and peer IV
  changes. Transfer is stronger for **long-duration options**, when the announcer has higher earnings
  quality, reports positive news, or is a bellwether, and during periods of greater macroeconomic
  uncertainty. Between 25% and 35% of first announcers show *increases* in implied volatility, so the
  transfer is not uniformly uncertainty-resolving.
- **Critical gap, and it is the opportunity.** The paper establishes **association only**. It is an
  accounting paper about information transfer and **tests no trading strategy and no return
  predictability**. The tradeable question, whether the implied move charged to the later reporter is
  stale with respect to peer information already revealed, is not asked.
- **Differentiation.** Genuine. The accounting literature has established the mechanism exists; the
  options literature has not absorbed it into a return prediction. The existing prototype
  `scripts/prototypes/peer_transfer.py` already frames it as the tradeable question.
- **Feasibility constraint.** The original uses OptionMetrics across 217 industries. Free data here
  is DoltHub 2019-2024 broad, or the 50-name local Databento cache. The 50-name cache gives too few
  names per industry to define a first announcer meaningfully, so this requires the DoltHub panel and
  should follow #6 in build order.
- **Verdict: proceed. Least crowded candidate on the list.**

---

## #2 Earnings announcement premium

**Status: verified.** Frazzini & Lamont, *The Earnings Announcement Premium and Trading Volume*,
NBER w13090.

- **Effect.** Announcement-month premium of **0.44% per month**. Expected announcers minus expected
  non-announcers: **38 basis points per month** in the base specification, rising to **153 basis
  points per month** in the strongest construction. Present consistently **since 1927**.
- **Volume conditioning.** Stocks with high past announcement-period volume earn the highest premium.
  Low volume-concentration stocks earn 74 bp against 39 bp for high concentration, a difference of
  35 bp. The forecastable spread between high and low groups is roughly 93 bp per month.
- **Decomposition.** Roughly 60 bp accrues around the announcement and a further 60 bp after, with
  21 bp in the three days around the print itself.
- **Weakest link.** The premium is concentrated in small, high-attention, high-volume names, which is
  where borrow and market-impact costs bite hardest. The paper does not net trading costs against the
  cross-sectional strategy at the capacity a real book would need.
- **Differentiation.** Moderate. The honest version tests whether the premium survives the
  `event_study.equity_roundtrip_cost_bps` model at realistic size, in the post-2007 sample the paper
  does not cover.
- **Verdict: queue after the first four.**

---

## #10 Implied-volatility changes

**Status: partial.** An, Ang, Bali & Cakici, *The Joint Cross Section of Stocks and Options*, JF
69(5), 2014. PDF retrieved but not yet parsed for exact construction.

- **Effect as reported in secondary sources.** Stocks with large increases in call implied volatility
  over the previous month have high future returns; decile spread approximately **1% per month**,
  persisting up to six months. The relation runs in both directions.
- **Differentiation.** The trading leg is equities, so the measured option-touch problem does not
  bind. That makes this the most execution-viable of the Tier B set.
- **Verdict: queue. Extract full specification before testing.**

---

## Candidates not yet extracted

Specifications still to pull before these enter the queue: #4 analyst dispersion (Diether, Malloy &
Scherbina 2002), #5 volatility-managed overlay (Moreira & Muir 2017 plus the Cederburg et al.
real-time critique), #8 put-call parity deviations (Cremers & Weinbaum 2010), #9 volatility smirk
(Xing, Zhang & Zhao 2010), #11 delta-hedged gains (Bakshi & Kapadia 2003), #12 risk-neutral moments,
#14 implied correlation (Driessen, Maenhout & Vilkov 2009), #15 pre-announcement run-up, #17 variance
term premium (Dew-Becker et al. 2017), #19 VIX futures carry.

## Excluded

- **#20 dealer gamma.** DoltHub carries no open interest and OPRA definitions would be metered.
  Blocked by the no-spend constraint, not by merit.
- **#18 dispersion.** Disqualified by the measured touch cost; leg count multiplies the one thing
  known to be binding.
- **Tail/jump risk premium.** Crowded, and the payoff shape is the one the drawdown work already
  flagged as unallocable at 9.4 times annualised profit.
