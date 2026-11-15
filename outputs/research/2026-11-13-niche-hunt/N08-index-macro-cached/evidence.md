# N08 index-macro-cached: evidence dossier

SPY, QQQ and IWM options around scheduled US macro releases (CPI, payrolls and PCE at 08:30 ET;
FOMC statements at 14:00 ET), priced on the cached Databento OPRA 15:59 and 10:00 snapshots
(`data/cache/index_chains`, 2016-01-04 to 2026-10-30, zero spend). All figures are real data,
per trade, in units of the entry mid premium (P0) unless stated, net at the touch, with
date-clustered 95% intervals (`protocol.date_clustered_ci`, mean, 5,000 draws, seed 0). Every
result is exploratory: see "Contamination" below.

## Hypothesis, scope and success criteria

Hypothesis: index ETF options overprice the variance of a scheduled macro release, and because
index ETF spreads are a far smaller share of premium than single-name spreads, a seller can keep
the premium net of the touch. Scope: SPY primary, QQQ and IWM secondary; discovery 2016-2024,
held-out 2025-01 to 2026-10. Pass rule, written in `diagnosis.log` entry 0 before any outcome:
event-book mean above zero with its interval excluding zero, and event-minus-matched-control mean
above zero with its interval excluding zero. Controls: the same trade on nights without CPI,
payrolls, FOMC or PCE, same weekday and days to expiry, within 60 sessions, at least five.

## Verdict

Not viable. The release is priced rich at the mid, and the richness is concentrated where theory
puts it (short tenors, CPI), but no configuration passed discovery and the frozen best one kept
about nothing on held-out data: SPY book +0.76% of premium [-16.3, +17.1], paired +5.1%
[-13.2, +23.2], N=20 (trial 2,312), -0.02% of margin per trade. The surplus that exists is
small against a per-trade standard deviation of about half the premium, and about 10 to 12
qualifying events a year cannot resolve it in any useful time.

## Prior work

- Closest paper: Londono and Samadi, "The Price of Macroeconomic Uncertainty: Evidence from Daily
  Option Expirations", Federal Reserve IFDP 1376, June 2023 (verified at source, abstract and
  introduction). Daily SPX expirations spanning CPI, FOMC, payrolls and GDP releases against
  neighbouring expirations: at-the-money options spanning releases are up to 7.5% more expensive,
  and variance risk premia for FOMC-spanning options are 44% larger than for controls. Implied
  measures only; no traded straddle and no bid-ask cost in the pages read. This lane's mid result
  (trial 2,307: event straddles about 11% of premium richer than matched nights after the hold)
  is the same phenomenon measured as a trade on SPY.
- Wright, "Event-day Options", NBER w28306 (2020; Journal of Time Series Analysis 2025), read at
  source by a research subagent: CME weekly E-mini S&P 500 options at settlement prices, payrolls
  2011-2020 and FOMC 2017-2020 against non-event days. FOMC event-day variance premium 0.248 (SE
  0.076) against extra implied variance 0.241; payrolls premium 0.204 (SE 0.100) against 0.423,
  units one-day variance in percentage points squared as read. No bid-ask, no trade P&L. On this
  evidence the FOMC extra variance is almost all premium and payrolls about half.
- DeSimone and Laux (OptionMetrics, 2018): index straddle premia concentrated around macro
  announcements, sign reversed on FOMC days (abstract only; magnitudes and price basis not found).
- Windmar (Lund University working paper, 2025), delta-neutral straddles around macro
  announcements: lower returns on FOMC, CPI and PPI days than on all days, so sellers earn more on
  announcement days. Recalled from a practitioner summary; not read at source; cost treatment
  unknown.
- Ederington and Lee (1996, JFQA) and Beber and Brandt (2006) show implied volatility falling after
  scheduled releases in rates and currency options (recalled; the lane N05 owns the Treasury side).
  Muravyev and Ni (2020, JFE) put the index option premium overnight and note that spreads swamp
  an overnight strategy for most investors (recalled via the project's frozen pre-registration).
- Practitioner: Rhoads (Substack) reports the SPX straddle exceeding the CPI-day move on 75% of
  one year's releases; Risk.net reports 0DTE SPX volume spiking on CPI days from late 2022
  (both recalled from search summaries; small samples or paywalled).
- Crowding: the existence of a release premium in index options is documented and widely traded
  (0DTE CPI flow is a known retail and dealer theme). No paper found measures it as a traded
  straddle net of the touch on ETF options, which is the gap this lane filled. The answer is that
  little survives.

## Mechanism and timing

Buyers are hedgers and short-dated speculators who pay for protection over the release
(Londono and Samadi document higher volume in spanning expirations). The 08:30 releases land
while cash equities are closed; until 19 October 2026 SPY, QQQ and IWM options were also closed
then, so a seller who wants out after the release first meets the 09:30 open, when spreads are
widest. In this data the release-morning reset is not complete at 10:00: the 15:59 to 10:00 short
earns nothing at the mid over clean nights on short tenors (trial 2,309, -0.16% of P0), while the
same contract held to expiry earns +11.5% at the mid (2,307). The FOMC statement at 14:00 is
mid-session; its intraday short (10:00 to 15:59) has a surplus of +4.5% (t 0.9) whose sign
depends on one tail day (2024-12-18, -286% of P0).

Half-spread against premium (the brief's bar): SPY front straddle median half-spread 0.48% of P0
at 15:59 and 0.90% at 10:00 (2016-24, release nights), 0.41% on contracts of at most three days,
against 4 to 6% per half-spread on the single-name hedged books. The spread is an order of
magnitude smaller, but so is the release premium per unit of premium, because the straddle
carries ordinary sessions as well as the event.

## Tradability at Interactive Brokers

- Product: SPY, QQQ and IWM options (OPRA, multi-listed, physically settled American style, daily
  expiries on SPY since late 2022). Regular hours 09:30 to 16:15 ET for these ETF classes (Cboe
  technical specification, verified). Since 19 October 2026 Cboe Options (C1) runs a pre-market
  session 07:30 to 09:25 ET in these five ETFs and 24 stocks, limit orders only (Markets Media and
  the Cboe extended-hours FAQ, verified). That puts the 08:30 release inside an option session for
  the first time. Whether IB routes customer orders to that session is not verified.
- Commissions, IBKR Pro: USD 0.65 per contract up to 10,000 contracts a month at premiums of USD
  0.10 or more, falling to USD 0.15 above 100,000; USD 1.00 minimum per order; no commission on
  US exercise and assignment (IB pages via search, verified at snippet level; IB's site refuses
  direct fetches). The pilot charged USD 0.65 per contract per side.
- Market data: OPRA Top of Book (L1) at USD 1.50 a month on IB's market-data page (verified at
  snippet level; tier labelling unclear). A paper user can share the live user's subscriptions (IB TWS API documentation on
  interactivebrokers.github.io, verified by the subagent). Without it IB quotes are about fifteen minutes late.
- Margin (Reg-T): short broad-based ETF option, 100% of premium plus 15% of the ETF value less any
  out-of-the-money amount, minimum 10% (IB knowledge base, verified at snippet level). A short
  straddle is charged the larger leg's requirement plus the other leg's premium (IB page, recalled
  at snippet level). The pilot's margin basis (P0 plus 15% of the forward) follows this.

## Data route

Already on disk at zero cost: `data/cache/index_chains` (Databento OPRA cbbo-1m, minutes 15:59
and 10:00, every session 2016-01-04 to 2026-10-30, whole-dollar strikes within 5% of the close,
expiries within ten calendar days strictly after the snapshot date). Limits: no same-day (0DTE)
quotes, so a release-day expiry can only be settled, not bought back; no quote between 15:59 and
10:00, so the post-release reset cannot be timed; no pre-market quotes (the Cboe session began
19 October 2026). A forward test of a pre-market buy-back needs live quotes; a historical one does
not exist anywhere before October 2026. Daily ETF bars for hedging and settlement come from
Yahoo (free; `yahoo_ohlc.parquet`).

## Kill criterion and forward test

Kill: the frozen rule's held-out paired surplus is below its discovery value by more than half and
the held-out book level is within one standard error of zero, both now true. A forward paper test
would sell the SPY straddle expiring at most three days out at the 15:59 bid before each CPI
release, hedge at closes and settle, with real-time OPRA quotes; at about 12 events a year and a
per-trade standard deviation near 0.54 of premium, resolving a 5% surplus at two standard errors
needs about 460 events (decades) and the discovery-sized 11% about 95 events (eight years). Not worth a slot unless pooled with other release types or other underlyings,
or unless the new pre-market session lets the seller exit within minutes of the release at a
spread that the 10:00 data cannot show.

## What the project had already done on this cache (read first)

- The frozen index study `research/off_earnings/2026-11-01-index-event-crush` scored amendment 03
  of the SPY macro pre-registration on this cache (`outputs/research/2026-11-01-index-event-crush/
  summary.json`): A1, short SPY across CPI and payrolls close-to-close, 2019-24 +4.27% of P0
  (97.5% interval [-2.70, +10.86], N=138), FAIL; on 2016-18 and 2025-26 pooled -6.23%
  [-15.85, +1.52], N=110. A2, long across FOMC, 2019-24 +2.48% [-11.14, +19.60], N=44, FAIL;
  pooled 2016-18 and 2025-26 -13.91% [-20.13, -7.02], N=35. Unconditional overnight short (B3,
  15:59 to 10:00) on SPY 2019-24: -2.50% [-3.38, -1.63], N=1,499; at the mid +0.08%.
- `docs/RESEARCH_STATE.md` section 2 still reads "SPY macro-release straddles: not testable on
  DoltHub, N=5". That row is stale: the cache test exists and failed. It should cite the index
  study's A1 and A2 results.
- This lane's new angles: the release-overnight split (15:59 to 10:00), the FOMC intraday hold
  (10:00 to 15:59), the release-day expiry settled, the hedged hold to expiry on release nights,
  the tenor gradient, and the implied-against-realised event variance. None of these was printed
  by an earlier study.

## Pilot results (block D, 2016-2024 entries)

| Trial | Trade | N | Book, % of P0 | Paired vs controls | Verdict |
|---|---|---|---|---|---|
| 2,292 | SPY short, 15:59 to 10:00 across CPI or payrolls | 204 | -1.86 [-4.52, +0.69] | +0.80 [-1.97, +3.41] | Fail |
| 2,293 | SPY short, 10:00 to 15:59 on FOMC day | 71 | -0.50 [-11.24, +7.05] | +4.46 [-6.60, +12.33] | Fail |
| 2,294 | SPY release-day expiry sold at 15:59, settled, 5 bp disposal | 171 | -3.04 [-14.09, +7.41] | +2.69 [-8.71, +13.82] | Fail |
| 2,296 | QQQ as 2,292 | 203 | -1.32 [-3.53, +0.81] | +2.51 [+0.28, +4.74] | Surplus on a losing book |
| 2,305 | SPY 2,292 contract hedged at closes to expiry (HEDGED_NET) | 204 | +4.69 [-2.45, +11.54] | +2.33 [-4.87, +9.29] | Fail |
| 2,307 | As 2,305, expiry at most 3 days after entry | 90 | +9.38 [-2.31, +20.46] | +10.88 [-0.69, +21.96] | Fail, frozen as best |
| 2,310 | QQQ, as 2,307 with PCE | 102 | +6.14 [-4.27, +16.38] | +11.36 [+0.94, +21.33] | Surplus only |

All twenty trials, with the secondary tickers and the long FOMC side, are in `trials.csv`.

Mechanism read (trial 2,295, descriptive): on SPY release nights the implied extra variance from
the 15:59 two-expiry term split is 4.14e-5 [2.37e-5, 6.01e-5] against a realised extra variance,
15:59 to 10:00, of 2.55e-5 [0.51e-5, 4.98e-5], N=202. The release is priced at about 1.6 times
its realised size at the point estimates; the intervals overlap.

Where the money goes. On the 10:00 buy-back the release night is richer than clean nights at the
mid (+0.87% of P0 against -0.06%), but the median half-spread is 0.48% of P0 at 15:59 and 0.90%
at 10:00 and commissions are a median 0.72% of P0 (USD 0.0065 per share on four legs against a
median USD 3.60 straddle), so the round trip costs about 2.7% of P0: the single-name failure in
miniature. Holding hedged to expiry removes the second crossing, and the surplus then rises
monotonically as tenor falls (paired, by calendar days to expiry: 2 days +12.2%, 3 +8.3%, 4
-1.2%, 6 -7.8%, 8 -22.2%; N 59, 31, 80, 24, 10; `s02c_diag.log`). That is the pattern a fixed
release variance diluted by ordinary sessions predicts. The 10:00 buy-back captures none of it at
the mid (2,309: -0.16% of P0), so the reset happens after 10:00 on the release day and through
the next session, which is consistent with the close-to-close A1 result being better than the
overnight one.

Robustness of 2,307 on discovery (`s02e_robust_2307.log`): positive in 6 of 9 years; dropping any
one year leaves the paired point between +8.1% and +13.6%; skew -1.09; per-trade standard
deviation 0.54 of P0; on margin (P0 plus 15% of the forward) +0.40% per trade. Under the tenor
cap every discovery event is a CPI release, because Friday payrolls never have an expiry within
three days.

## Held-out read (trial 2,312, block H, read once)

Frozen in `freeze_2026-11-13_cpi-short-tenor-hedged-hold.md` (body SHA-256 b9eeba67...,
scorer `s03_heldout.py` 77c10537...). SPY: N=20, book +0.76% [-16.26, +17.12], paired +5.09%
[-13.24, +23.16], per-trade Sharpe +0.02, -0.02% of margin per trade. FAIL. Secondary: QQQ book
-6.36%, paired +0.11%; IWM book +8.46%, paired +11.16% [-8.95, +29.99]; SPY with PCE added (N=32)
book +4.88%, paired +13.69% [-2.70, +30.80]. The sign of the surplus holds on SPY and IWM, its size
halves on SPY, and the level a seller keeps is near zero.

## Contamination and attrition

- Input provenance: the hedge path and settlement closes behind trials 2,304 to 2,312 (including
  the frozen 2,307 and the held-out 2,312) came from a fresh yfinance pull of Yahoo daily bars,
  whose robots.txt disallows automated clients. The file has been deleted; the scored outputs are
  left unedited and flagged (`diagnosis.log` entry 5, note row in `trials.csv`). A compliant
  rebuild uses the cache's own 15:59 parity forwards or CRSP closes from the project's R2 mirror.
  Trials 2,292 to 2,303 do not depend on it.

- Block H was partly viewed before this lane: the index study's amendment 03 printed
  close-to-close CPI and payroll shorts and FOMC longs on 2016-18 and 2025-26 pooled. The tenor cap
  was chosen after a discovery split. Every number here is exploratory.
- Attrition: T1 rows inherit the frozen study's funnel (SPY 2,701 of 2,723 sessions priced at the
  10:00 exit; drops are missing snapshots on half-days and 1 to 2 missing exit asks per ticker).
  T2 SPY 2,703 of 2,724 (20 half-day exits, 1 missing entry). T4 8,098 of 8,098 T1 rows hedged.
  Six calendar dates fall on non-sessions and are dropped, including three Good Friday payroll
  releases (2021-04-02, 2023-04-07, 2026-04-03) and a Good Friday PCE (2024-03-29), which land
  while US option markets are closed for three days. Release-event attrition after matching: 6 of
  210 SPY T1 events lack five controls.
- Not modelled: early assignment (SPY options are American; the hedged hold assumes none before
  expiry), pin risk at expiry, after-hours moves between 16:00 and the exercise cut-off, and the
  margin cost of the hedge beyond the `HEDGED_NET` convention.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N08-index-macro-cached\evidence.md
