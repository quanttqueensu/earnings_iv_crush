# N03 natgas-storage: evidence dossier

Lane question: is there a scheduled-event volatility premium in NYMEX Henry Hub natural gas
options around the EIA Weekly Natural Gas Storage Report (Thursday 10:30 ET) that survives the
touch, can be paper traded at Interactive Brokers, and can be tested on zero-cost data?

Status of every claim is in `sources.csv` (verified, recalled, conjecture). Trial numbers 2142 to
2145 are used; all four fail. Every number below gives N, interval, basis and file.

## 1. Hypothesis, scope and success criteria

Hypothesis: options expiring just after the storage report carry implied variance for the report
in excess of what the report delivers, so selling them into the report earns a premium net of
one half-spread. Scope: NYMEX NG options, the Thursday-expiry weekly (KN1 to KN5, listed since
2025-01-27) and the Friday weekly (LN1 to LN5), with the futures as a related vehicle. Success:
a premium net at the touch against a matched non-event control with a 95% interval above zero,
or a priced case for the data pull that could show it.

## 2. Prior work

- **Linn and Zhu (2004), J. Futures Markets 24(3)** (verified). Five-minute NYMEX NG futures,
  1999 to October 2002. In the EIA regime (May to October 2002, about 26 reports) the 10:30-10:35
  return standard deviation on Thursdays is about four times that of other weekdays (Figure 2;
  Table I panel D, Brown-Forsythe F 17.02, significant at 1%), and elevated volatility lasts about
  30 minutes. Realised volatility only; no options, no costs.
- **Prokopczuk, Wese Simen and Wichmann (2021), Energy Journal 42(2)** (verified, accepted
  version). 699 report days, March 2003 to December 2018. NG futures earn more than half their
  annual return on report days, with a negative sign the surprise does not explain. A short from
  90 minutes before to 30 minutes after the release earns 12.0% a year after bid-ask costs and
  funding; their Sharpe of 1.76 is annualised with the square root of 252 on a weekly book
  (inflated; on a square root of 52 basis it is about 0.80). The effect was 25% a year early and
  3% a year (Sharpe 0.5 on their basis) in 2014 to 2018, where it does not survive costs. This is
  the closest paper with costs measured; it is a directional premium, not a volatility premium.
- **Sharma (2017), University of Georgia MS thesis** (verified). Nearby NG option implied
  volatility (CRB, average of the two nearest-the-money calls and puts), July 1998 to June 2013:
  mean 100 ln(IV_t/IV_{t-1}) is -0.905 on 748 storage days against +0.481 on 2,103 days with no
  scheduled announcement (t -7.33). This is the only measurement found of the implied side, and
  the closest paper on the option crush. No trading test, no costs.
- A 2021 Energy Economics paper on a one-month NG volatility index reports the index falls from
  Wednesday to Thursday (recalled from a search snippet; page refused access; authors not
  confirmed). EIA 2017 conference slides by Linn and co-authors report the NG price response to
  the surprise intensified over time (verified).
- Energy variance risk premia are negative (implied above realised) in natural gas (Trolle and
  Schwartz 2010; Prokopczuk, Symeonidis and Wese Simen 2017) (recalled, not re-read).

Crowding: the realised storage-day jump and the announcement-day futures return are documented
and, per Prokopczuk et al., decayed. No paper found tests selling the storage event through
short-dated options at the touch, and the vehicle that makes it sharp (the Thursday weekly) is
22 months old. The idea is not crowded in the literature; whether dealers already price it is
the open question, and the evidence below makes a surplus unlikely to be large.

## 3. Mechanism and event time

The report lands at 10:30 ET mid-session (CME Globex runs Sunday 17:00 to Friday 16:00 CT with a
daily 16:00-17:00 CT break, verified in the CFTC filing), so unlike after-close earnings there is
no overnight gap: a market maker can widen quotes for the minutes around the print, and a
volatility seller is exposed only to the intraday jump. The Thursday weekly expires at the close
of Thursday trading and settles financially on the NG futures settlement price (verified), so an
option sold before the print can be held to cash settlement without paying an exit spread.

Who would pay: hedgers buying protection through the print, and dealers marking a fixed event
add-on. Why it would not persist: the number is increasingly forecastable. Consensus surveys,
ICE's weekly storage index futures that price the number directly (recalled), and daily pipeline
flow data let the market nowcast the build, and weather-model updates (twice daily) now carry
most NG news. The pilot below measures that erosion at daily resolution.

## 4. Pilot on free data (trials 2142 to 2145)

Data: EIA NYMEX NG settlement series, contracts 1 to 4, 1993-12-20 to 2024-04-05 (EIA stopped
the series then; no later free source is reachable within the rules). Settle to settle
(14:28-14:30 ET), same-contract returns spliced at the roll, which `logs/check_roll.log`
confirms falls on the second-last trading day. No option price is used anywhere: these trials
measure the event's size and one related futures premium, not an option premium.

Design (pre-registered in `diagnosis.log` entry 1 before any outcome): event = the Thursday return
(Wednesday settle to Thursday settle); matched control = the Tuesday and Wednesday returns of the
same week. Discovery 2002-05 to 2018-12, held-out 2019-01 to 2024-04, frozen in
`freeze_heldout.md` (SHA-256 049f9f60...3331 in the sidecar; scorer 70224fbb...97c8; library
4e6a5d0b...6cff) and read once.

Funnel (`logs/score_discovery_run1.log`): 1,144 report Thursdays; 223 dropped for a federal
holiday in the week (EIA may move the release); 68 for a missing settlement; 173 because Tuesday,
Wednesday or Thursday is a front-month last-trade or roll day; 680 kept (506 discovery, 174
held-out). Every drop is calendar-determined, so attrition cannot depend on the outcome.

rho is the Thursday's excess variance in units of one ordinary day; B is the ratio of mean
absolute returns, the implied-volatility multiple a one-day Thursday-expiry straddle needs over a
Tuesday or Wednesday one to break even at settlement. Intervals are week-clustered percentile
bootstraps (10,000 resamples).

| Trial | Block | N weeks | Statistic | Point [95% CI] | Rule | Result |
|---|---|---|---|---|---|---|
| 2142 rho, C1 | 2002-18 | 506 | rho | +0.713 [+0.438, +1.038]; B 1.33 [1.22, 1.44] | lower > 0.25 | discovery pass |
| 2142 rho, C1 | 2019-24 | 174 | rho | -0.128 [-0.360, +0.163]; B 0.93 [0.79, 1.09] | lower > 0.25 | **fail** |
| 2143 rho, C2 | 2002-18 | 506 | rho | +0.839 [+0.536, +1.196] | lower > 0.25 | discovery pass |
| 2143 rho, C2 | 2019-24 | 174 | rho | -0.200 [-0.424, +0.096] | lower > 0.25 | **fail** |
| 2144 short C1 | 2002-18 | 506 | net per trade | +0.206% [-0.082%, +0.497%] | net and vs-control lower > 0 | fail |
| 2144 short C1 | 2019-24 | 174 | net per trade | +0.246% [-0.299%, +0.807%]; vs control +0.319% [-0.364%, +1.022%] | same | **fail** |
| 2145 short C2 | 2002-18 | 506 | net per trade | +0.177% [-0.092%, +0.451%] | same | fail |
| 2145 short C2 | 2019-24 | 174 | net per trade | +0.176% [-0.297%, +0.647%] | same | **fail** |

Short returns are per trade on futures notional, net of one tick plus USD 2.50 per side (mean
round trip 0.063% discovery, 0.090% held-out), executed at settlement (Trade-at-Settlement,
recalled). Per-trade Sharpe on held-out 2144 is 0.067 (33.5 kept trades a year; square root of
33.5 annualised 0.39). Files: `logs/discovery_results.json`, `logs/discovery_diagnostics.log`,
`logs/heldout_results.json`.

Reading. The storage day's excess variance shrank from +0.94 ordinary days in 2002-10
([+0.56, +1.42], 243 weeks) to +0.42 in 2011-18 ([+0.07, +0.89], 263 weeks) and is not
distinguishable from zero in 2019-24, with a negative point estimate. In discovery it was broad,
not a few outliers (top five Thursdays carry 11.6% of Thursday variance; median-based ratio 1.89).
On held-out, Thursday's daily standard deviation (3.70%) sits below the control's (3.96%). The
futures premium of Prokopczuk et al. does not reappear out of their sample. The freeze note's
expectation for rho (positive, 0.3 to 0.8) was wrong in sign.

Implied side, indirect (conjecture-grade, `logs/implied_event_from_sharma.log`). Backing the
event out of Sharma's mean IV changes with a variance-additive model gives an implied event worth
0.26 to 0.61 ordinary days (for 10 to 21 trading days to expiry), against a realised +0.71
[+0.44, +1.04] in 2002-18. In that era options did not over-price the event; if anything they
under-priced it. Mixed sources and the ordinary-day drift make this a direction, not a number.

## 5. Half-spread against premium

Illustrative, conjecture until quotes are pulled: a one-day ATM Thursday-expiry straddle sold at
Wednesday settlement, futures at $3.50, daily s.d. 3.5%, is worth about 0.798 x 0.035 x 3.50 =
$0.098 per MMBtu, 98 ticks or $978. At 2 to 4 ticks wide per leg the straddle's half-spread is 2
to 4 ticks, 2.0% to 4.1% of premium, paid once because the option cash-settles. Fees per leg:
IB USD 0.85 (verified) + NYMEX non-member USD 1.50 + cash-settlement USD 1.15 (verified), about
0.7% of premium per straddle. The equity book pays 1.79% per side and pays it twice. So the cost
bar is similar or lower; what is missing is the premium. With held-out rho near zero, the fair
Thursday straddle equals an ordinary day's, and an edge exists only if dealers still mark a
storage add-on. If they priced the event at the Sharma-era 0.4 days while it delivers zero, the
straddle would be rich by sqrt(1.4) - 1 = 18%; if they have updated, the edge is the ordinary
variance premium, which the matched Wednesday expiry (JN) also carries.

## 6. Tradability at IB

- Product: NYMEX Henry Hub natural gas weekly options on NG futures (codes HN, IN, JN, KN, LN 1
  to 5 for Monday to Friday), 10,000 MMBtu, tick $0.001 = $10, European, cash-settled on the NG
  settlement (verified, CFTC filing 25-008). The symbol IB uses for them is not verified.
- Session: the 10:30 ET release is inside Globex hours. Entry options: Wednesday settlement
  (1 day to expiry) or Thursday 10:00-10:25 (about four hours, report inside).
- IB: futures-options commission USD 0.85 per contract up to 1,000 a month (verified). Market
  data: NYMEX Real-Time L1 non-professional USD 1.55 a month, or the US Securities Snapshot and
  Futures Value Bundle (USD 10 base, waived for activity) which includes NYMEX top of book
  (verified). Without it IB's NYMEX data is 10 minutes delayed (verified), not 15; fills on it are
  not evidence. Paper accounts inherit the live account's subscriptions; margin on a short
  straddle is SPAN (recalled). US futures trading permission is required (verified).
- Open item: whether IB's paper account offers the KN/JN weeklies by symbol; not checked (no IB
  connection allowed).

## 7. Data route and cost

Free: none for option prices (CME blocks automated reads; Barchart, Options Analysis Suite and
Argus are paid or bot-walled; Yahoo and Stooq disallow robots). EIA futures settlements stop at
2024-04-05.

Priced: Databento CME Globex MDP 3.0 Standard plan, USD 199 a month (verified on the public price
page; one search summary says Standard needs an annual contract, which would make it USD 2,388;
unresolved). Included history: statistics and definitions 16+ years (settlement prices and open
interest for every NG option, recalled that statistics carries option settlements), and L1 quotes
(BBO, MBP-1, TBBO) for the last 12 months. One month covers the whole test below. New accounts
also get USD 125 of usage credit. Usage-based per-GB prices are in a PDF not read; no vendor API
was called. Check first whether the project's existing Databento account already holds the CME
dataset.

The test the pull enables: implied event variance from settlements, KN (or LN) against JN on the
same Wednesday, every week since KN listing (about 85 Thursdays to date) and LN back to its
listing, then the touch from 12 months of L1 at Wednesday 14:25 and Thursday 10:20. Statistic:
paired net P&L, KN straddle sold at the Wednesday bid and cash-settled, minus JN straddle sold at
the Tuesday bid and cash-settled, per trade on premium, date-clustered interval.

## 8. Verdict

Not viable on present evidence; one narrow hypothesis is left that a USD 199 pull can settle.
The storage report no longer adds measurable daily variance (held-out rho -0.13 [-0.36, +0.16],
N=174 weeks, 2019-24), so there is no event for options to over-price unless dealers still mark
one. Kill criterion for the pull: if the KN-minus-JN implied variance at Wednesday settlement is
under 0.25 ordinary days, or the paired net P&L interval includes zero on the 12-month L1 block,
close the lane. Forward paper test if it passes: sell one KN ATM straddle at Wednesday 14:25 ET
with a limit at the mid, cash-settle, record the JN control each Tuesday, for 26 weeks, with the
NYMEX L1 subscription live.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N03-natgas-storage\evidence.md
