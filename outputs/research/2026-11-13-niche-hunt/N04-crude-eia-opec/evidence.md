# N04 crude-eia-opec: evidence dossier

Market: NYMEX WTI crude options (monthly LO and the Monday to Friday weeklies), Brent options,
and USO options as a vehicle, around the EIA Weekly Petroleum Status Report (WPSR), the API
survey, OPEC and OPEC+ meetings, and the monthly IEA and OPEC reports. Every claim is labelled
verified (read at the source), recalled, or conjecture; the URLs are in `sources.csv`. Trial
numbers 2,172 to 2,177 are used (`trials.csv`); the reasoning trail is `diagnosis.log`.

## 1. What was scored, in one paragraph

No free history of WTI option quotes is available under the brief's rules, so no touch-level
test was possible. A free pricing test was possible: Cboe's OVX (30-day implied volatility of
USO options, computed from bid-ask midpoints) against realised WTI settlement moves, on EIA
Wednesdays against the same week's Tuesday. On 2009-2019 discovery (N=302 weeks) the 30-day
options assign a Wednesday about 4% more volatility than a Tuesday, while Wednesdays deliver
about 21% larger absolute moves. That gives no surplus for a seller, and the buyer's surplus has
an interval spanning zero. The frozen held-out read (2021-2024 on futures, N=98; 2021-2026 on
spot, N=178) fails for both sides, and the realised EIA excess there is only 0.11 to 0.18 of an
ordinary day. Everything here is gross and at the mid.

## 2. Prior work

| Work | Sample | Effect | Costs measured | Label |
|---|---|---|---|---|
| Sharma (2017), UGA MSc thesis under B. Karali | NYMEX crude, heating oil, natural gas; settlement-based nearest-the-money IV from CRB; 1998-07-01 to 2013-06-05; 777 WPSR reports | Crude IV log change on WPSR days -0.407% against +0.365% on non-announcement days (t -4.13, Table 6); regression coefficient -0.597 (Table 8). Return volatility up on WPSR days (+0.155 on 1.242, absolute deviation, Table 7) | No | verified |
| Miao, Ramchander, Wang and Yang (2018), J. Futures Markets | CL futures and CME end-of-day options; 2003-06-16 to 2011-12-30; 446 releases | Directional: options and futures move with the inventory surprise; near-the-money options most sensitive | No | verified |
| Horan, Peterson and Mahar (2004), Energy Journal 25(3) | Crude futures options around OPEC meetings | IV drifts up before, falls about 3% the first day and 5% over five days; little drop for bi-annual conferences | No | recalled (abstract via search summary) |
| OptionMetrics blog (2025) | 57 OPEC meetings since 2005, 30-day WTI IV | Average IV decline during meetings is small | No | verified text, tables unread |
| Nazer and Pescatori (2022), IMF WP 2022/183 | 101 OPEC meetings 1987-2019 | Realised volatility on the announcement day 2.2 to 3.1 points above the control median | No | verified |
| Prokopczuk, Symeonidis and Wese Simen (2017), JBF | 21 commodities, options 2008-2011 | Variance risk premium negative in nearly all markets; unconditional, not event-specific | No | recalled |
| Luo and Kang (2014), working paper | 5-minute CL futures | EIA release raises jumps and intraday volatility at 10:30; pre-release leakage | No | verified |

The closest paper to the trade is Sharma (2017): it shows the scheduled implied-volatility drop
on WPSR days in crude options, but measures it on settlement prices, on monthly options, and
never compares implied with realised event variance or prices a trade. None of these works
measures costs. The idea is not crowded in the literature. The likelier reason is the event's
small size (section 6) than an unexploited gap; that reading is conjecture.

## 3. Mechanism and event timing

- WPSR: Wednesday 10:30 ET, inside both the Globex session and the 09:00-14:30 ET NYMEX day
  session; holiday weeks move to Thursday, 12:00 ET in the 2026-27 schedule (verified, EIA
  schedule page). The API survey lands Tuesday about 16:30 ET, after the settlement and the ETF
  close but inside Globex (recalled). A Tuesday-settle to Wednesday-settle window contains
  both.
- Unlike after-close earnings, the WPSR lands mid-session: a seller can be flat before the
  release, and the market trades continuously through it. The jump is small. This lane measured
  the WPSR Wednesday's extra realised variance at 0.52 [0.19, 0.92] of an ordinary Tuesday
  (2009-2019, N=302 weeks, settle to settle, T2175), falling to 0.11 [-0.34, 0.86] (2021-2024,
  N=98) and 0.18 [-0.31, 0.98] (2021-2026, spot, N=178). The excess is tail-carried: the median
  squared-move ratio is 1.05 to 1.07. For comparison, lane N03 measures the gas storage Thursday
  at 0.71 [0.44, 1.04] ordinary days (`../N03-natgas-storage/diagnosis.log`, entry 2), and
  single-name earnings are many ordinary days.
- Who would pay: hedgers buying short-dated protection over the report. CME listed Wednesday
  weeklies in 2023 for exactly this use (recalled, CME page blocked). Weekly WTI option ADV is
  over 21k contracts (2024, verified, CME-sponsored article), so the demand exists. Whether it
  overpays is the open question below.
- OPEC and OPEC+: decisions arrive at irregular times, increasingly at weekend virtual
  meetings of the voluntary-eight group (recalled), which would make them the closest crude
  analogue to after-close earnings, with the Friday close to Sunday-evening Globex reopen gap.
  The UAE's announced exit from OPEC and OPEC+, effective 1 May 2026 (Wikipedia, secondary),
  changes the regime for any post-2026 sample.

## 4. Tradability at Interactive Brokers

| Item | Value | Label |
|---|---|---|
| Products | NYMEX CL options: monthly LO and weeklies expiring every weekday (Mon/Wed since 31 July 2023, Tue/Thu since 22 July 2024, Fri older); Micro WTI (MCL) options with weeklies | rule terms verified (CFTC filing 24-158); launch dates recalled |
| Contract | 1,000 bbl, tick USD 0.01 = USD 10, American, exercises into CL futures, four weeks listed, at least 20 strikes at USD 0.25 either side of ATM, expires at the close of trading on its day | verified (CFTC filing) |
| Event against expiry | The Wednesday weekly expires on the WPSR day after the 10:30 release; a straddle sold at Tuesday's settlement or Wednesday 10:25 and held to expiry crosses the spread once | rule verified; strategy conjecture |
| Market data | NYMEX Real-Time L1, non-professional, USD 1.55 a month, waived above USD 20 of commissions; NYMEX delayed 10 minutes without it | verified by lane N20 |
| Commission | CL FOP all-in about USD 2.36 per contract (IB 0.85 + exchange 1.50 + 0.01); MCL options USD 1.01; exercise or assignment fee USD 0.85 at the exchange | verified (N20; CFTC filing for the exchange fees) |
| Margin | SPAN (energy on SPAN 2 per N20, recalled); CL futures margin USD 15,000 | verified by N20 |
| Paper account | Mirrors live permissions; futures-option permission needed | verified by N20 |

Commissions are small against a one-day straddle. On the discovery mean consumed variance for
a Wednesday (4.53e-4, a one-day volatility of 2.13%), an ATM one-day straddle is about
0.798 x 2.13% = 1.70% of the futures price, about USD 1,100 per straddle at USD 65 (conjecture,
derived). Two legs at USD 2.36 is 0.43% of premium per crossing. The binding cost is the spread,
which no free source quotes for CL weeklies. USO's 5 and 7-day ATM straddles pay 2.4 to 2.6%
of mid one way and its 0-day straddle 11.1% (lane N17, one delayed snapshot). A CL weekly at 2
to 5 ticks wide per leg would pay 1.8 to 4.5% of a USD 1.10 straddle one way (conjecture).

## 5. Data

| Source | Coverage | Granularity | Cost | Use here |
|---|---|---|---|---|
| Cboe OVX history CSV | 2009-09-18 to 2026-11-12 | daily close, mid-based index | free | implied side |
| EIA RCLC1, RCLC2 | 1983 to 2024-04-05 | daily settlement | free | realised side (C1) |
| EIA RWTC Cushing spot | 1986 to 2026-11-11 | daily | free | realised side, secondary |
| Yahoo (USO) | 2009-2026 | daily | free but robots-disallowed | used, then deleted (see 7.6) |
| CME DataMine, cmegroup.com | full | settlements and quotes | paid; site blocks scripts | not used |
| Databento GLBX.MDP3 | 2010 onward | tick and top of book | metered | priced, not pulled |

Settlement and daily index data cannot measure what a taker pays. The pull that would answer
the open question is a Databento GLBX.MDP3 top-of-book (cbbo-1m or mbp-1) snapshot of the CL
Wednesday weeklies (and Friday weeklies before July 2023), ATM plus or minus 10 strikes, at
Tuesday 14:25, Wednesday 10:25, 10:45 and 14:25 ET, for every WPSR week, plus the same times on
Tuesday-expiry and Thursday-expiry contracts in non-event weeks as controls. Lane N19 sizes the
crude pull (540 events, 250 contracts, 4 snapshots) at about 43 MB and USD 0.02 to USD 12.10
under its price assumptions (`../N19-data-access/data/pull_costs.csv`). A project cap of USD 25
would cover it with room. It must go through the project's metered-pull rules (free cost call,
hard cap, team lead's go-ahead).

## 6. Pilot

### 6.1 Design (diagnosis.log entries 1 to 5)

- Consumed implied variance on day t: dV_t = V_{t-1} - V_t + (OVX_t/100)^2 k/365, with
  V = (OVX/100)^2 x 30/365. The last term adds back the day the constant 30-day window gains at
  its far end (entry 2). Realised: squared log return of the WTI contract-1 settlement.
- Event: the Wednesday of a week with no federal holiday Monday to Wednesday. Control: the same
  week's Tuesday. Monday spans a weekend, and its window adds a Wednesday at the far end.
  Thursday's window adds a Saturday, and Thursday carries the gas storage report. Weeks
  touching a CL roll (calendar rule, two-business-day buffer) are dropped.
- Statistics: d (event-day carry minus control-day carry, variance per event); rho (EIA-day
  excess realised variance in Tuesday units); g = I - B (implied one-day volatility ratio minus
  the realised straddle break-even ratio, seller); R_buy (one-day straddle bought at Tuesday's
  settlement, held to Wednesday's, priced on consumed variance, buyer). Intervals are
  week-clustered bootstraps; the project's `date_clustered_ci` is used for d and components.
- Split: discovery 2009-09-21 to 2019-12-31; 2020 excluded (negative WTI and USO's change of
  holdings); held-out 2021-01-01 onward, read once after `freeze_eia_heldout.md` (SHA-256 in
  its sidecar; the scorer checks both hashes).

### 6.2 Funnel and attrition

Discovery: 537 weeks, 78 holiday weeks, 155 roll weeks, 2 missing days; 302 kept. Held-out C1:
170 weeks, 26 holiday, 46 roll, 98 kept. Held-out spot: 306, 45, 83, 178 kept. Every drop is
set by the calendar before outcomes are seen, so none can depend on the outcome. One global row
is dropped for a non-positive price (2020-04-20), outside every block.

### 6.3 Results (gross, at the mid; variance per event unless stated)

| Trial | Block | Statistic | Point | 95% interval | N |
|---|---|---|---|---|---|
| 2174 | discovery | d | -1.64e-4 | [-3.93e-4, +0.65e-4] | 302 |
| 2174 | discovery | implied excess (Wed - Tue dV) | +3.8e-5 | [-1.39e-4, +2.19e-4] | 302 |
| 2174 | discovery | realised excess (Wed - Tue r^2) | +2.02e-4 | [+0.79e-4, +3.27e-4] | 302 |
| 2175 | discovery | rho (Tuesday units) | +0.52 | [+0.19, +0.92] | 302 |
| 2176 | discovery | g = I - B | -0.17 (I 1.04, B 1.21) | [-0.45, +0.15] | 302 |
| 2177 | discovery | R_buy, return on premium | +5.8% | [-10.7%, +29.0%] | 302 |
| 2176 | held-out C1 | g | -0.10 (I 0.93, B 1.04) | frozen run NaN; nan-dropped [-0.54, +0.81], exploratory | 98 |
| 2177 | held-out C1 | R_buy | +16.0% | [-12.6%, +77.8%] | 98 |
| 2176 | held-out spot | g | -0.15 (I 0.89, B 1.04) | frozen run NaN; nan-dropped [-0.70, +0.38], exploratory | 178 |
| 2177 | held-out spot | R_buy | +15.6% | [-15.2%, +210%] | 178 |

Pre-registered outcome: the seller fails discovery (kill rule: mean d at or below zero) and
fails held-out on the point estimate. The buyer fails discovery and held-out (lower bounds below
zero). Nothing passed. T2172 and T2173 are listed in `trials.csv`: the first carried a
measurement error, and both used withdrawn data.

### 6.4 What the numbers mean

- Discovery says the 30-day crude options price the WPSR Wednesday as an almost ordinary day
  (implied excess +3.8e-5, about 0.09 of a day), while the day delivered about half a day of
  extra variance. Taken at face value that is an under-pricing, which a buyer could only collect
  in a contract that prices the event the same way. The one-day Wednesday weekly is a different
  contract with its own buyers, so the point is not transferable without quotes.
- Out of sample the realised excess itself shrank to 0.11 to 0.18 of a day, with intervals
  spanning zero. A seller needs the implied event share to exceed the realised one by enough to
  pay the spread once. With rho = 0.15 and a 2.5% one-way half-spread, the one-day contract
  would have to price at least 0.21 extra days (1.052 x 1.15 - 1). With rho = 0.52, the
  requirement is 0.60. This assumes no ordinary daily variance premium, and the ordinary
  premium here is small and insignificant: Tuesday carry +2.6e-5 [-1.2e-4, +1.7e-4], discovery.
- Power is the main limit of this design. The daily standard deviation of OVX consumed variance
  (2.3e-3 to 2.5e-3) is about five times the mean implied day (4.8e-4 to 5.3e-4), so the
  implied side cannot resolve an event worth a few times 1e-5. The realised side is the robust
  part, and it says the event is small and getting smaller.

### 6.5 Agreement with the parallel lane

Lane N17 ran an independent version on USO (F1, trial 2562): the event-day mid P&L of the
30-day straddle equivalent is -0.39% [-1.02, +0.21] of premium, N=455, discovery to 2020
(`../N17-commodity-etf-options/diagnosis.log`). The sign and the null agree with T2173 and
T2174. N17 replaced its Yahoo prices with Cboe's public USO closes before freezing. It
reports by message (2026-11-13) a clean held-out read on report Wednesdays from 2021-01 to
2026-10, N=187, with Tuesday and Thursday controls. The 7-day surplus is -3.41% [-7.96, +0.60]
of premium (gross, at the mid). Net of touch and commission, the 7-day result is -8.21%
[-12.57, -4.24] and the 30-day result -8.16% [-9.18, -7.23]. Implied excess is -0.30 ordinary
days against realised +0.05. N17's USO round trip including USD 2.60 commission per straddle is
5.3 to 5.5% of mid at 5 to 7 days (`spread_table.csv`, snapshots 14:33 and 14:57 ET). These
figures are N17's; verify them in its folder before quoting.

### 6.6 Process failures, stated

- The first realised series (USO from Yahoo via yfinance) breached the brief's robots rule:
  Yahoo's query endpoints disallow all paths. The file was deleted, both trials that used it
  remain counted, and the per-week pair files derived from it were deleted (entry 3). N17 was
  told, because its ETF prices come from the same endpoint.
- The EIA WPSR archive page was fetched once before robots.txt was read; it is disallowed
  (`/*archive/`), so the file was deleted unread and the release calendar comes from the
  schedule page's rule instead.
- The frozen held-out scorer returned NaN intervals for g, because 0.85% (C1) and 0.08% (spot)
  of resamples had a non-positive mean Tuesday consumed variance and `np.quantile` propagated
  the NaN. The verdict does not change, since the point estimates are negative. The
  nan-dropped intervals are exploratory (`posthoc_nan_check.py`, `results_posthoc_nan.log`).
- The CL roll rule and the API release time are recalled, not read at source (cmegroup.com
  blocks scripted reads).

## 7. Events not tested, and why

- **OPEC and OPEC+ meetings.** No primary, scrapable list of meeting dates was reachable:
  opec.org returns 403 to scripts, the IMF paper does not list its dates, and Wikipedia gives
  months only. The lane's web-search budget ran out before a secondary list was found. Literature
  priors: IV falls after meetings (Horan et al. 2004, recalled), the average fall is small
  (OptionMetrics 2025, verified text), and realised volatility is elevated around meetings
  (IMF 2022, verified). The OVX machinery here would test it in an afternoon once dates exist.
  The weekend meetings are the most promising structure in this lane: an event while the market
  is closed, as with earnings. N would be small, about 10 to 15 weekend decisions since 2024
  (conjecture).
- **API (Tuesday after the settlement).** It sits inside the tested Tuesday-to-Wednesday
  window. It cannot be separated with daily data.
- **IEA and OPEC monthly reports.** These are minor scheduled releases with no free intraday or
  option history, and were not tested.
- **Brent options (ICE Europe, CME BZ).** IB's NYMEX BZ fee row reads "N/A" and ICE Europe data
  is not priced (N20). The vehicle question was not pursued further.

## 8. Kill criterion and what a forward paper test would look like

Kill criterion for crude WPSR: if a quote pull shows that the CL Wednesday weekly, sold at
Tuesday's settlement and held to expiry, has a mean return at the touch at or below that of
the Tuesday weekly over the same window, on at least 100 weeks, with a lower bound not above
zero, the WPSR is closed.

A forward paper test needs the pull first, because the free evidence gives no reason to trade
it. If the pull shows a priced event share well above the realised 0.1 to 0.5 days, the paper
version would be as follows. Each WPSR week (no holiday), quote the CL Wednesday weekly ATM
straddle at 14:25 ET Tuesday with a real-time NYMEX L1 subscription (USD 1.55 a month). Rest a
limit at the mid less one tick, log fills against the 14:25 touch, and hold to expiry with
exercise netted in CL. Use the same contract and rule on the Tuesday weekly the previous day as
the matched control. At about 45 weeks a year, a year of paper trading gives N of about 45, too
few for a per-trade Sharpe interval that excludes zero unless the effect is large. That is
another reason to settle it on history first.
