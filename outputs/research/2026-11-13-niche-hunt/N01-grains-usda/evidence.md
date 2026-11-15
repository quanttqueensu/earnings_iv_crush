# N01 grains-usda: evidence dossier

CBOT corn, soybean and wheat options around USDA reports (WASDE, Crop Production, Grain Stocks,
Prospective Plantings, Acreage). Claims carry a label (verified, recalled, conjecture) and a
source row in `sources.csv`. No option outcome was computed and no trial number was used
(`trials.csv` is empty; `diagnosis.log` says why).

## Verdict

Viable pending a priced data pull, with a modest prior. Grains are the most thoroughly documented
scheduled-event volatility premium outside equity earnings: five peer-reviewed papers over
three decades find implied volatility falls on report days and that options are dear relative to
report-day realised volatility, and one measures a straddle loss of 3 to 7% on release days. None
measures costs. On published spread levels, the front-month quoted spread is about 1.0 to 1.7%
of an at-the-money straddle premium per side, three to five times cheaper relative to premium
than the project's equity events (4 to 6% per half-spread, `docs/RESEARCH_STATE.md`). The net
edge implied by combining the two is small (about 0 to +4% of premium per trade on a one-day
hold) and needs about 175 independent report dates to resolve at +2%, against about 15 dates a
year. History, not a forward test, has to carry the evidence.

## 1. Prior work

| Paper | Sample | Effect | Costs measured | Label |
|---|---|---|---|---|
| He and Bian, J. Agric. Econ. 76(3) 2025 | WASDE, corn, soybeans, wheat; period not verified | announcement jump model; options overpriced relative to realised volatility on release days only; long straddle loses 3 to 7% on release days; larger when forecast dispersion is high | not stated in abstract | verified (abstract only; paywalled) |
| Diersen and Wang, JAAE 2024 | CME end-of-day, corn and soybean weeklies, 2017-2021, 74 report dates | report-week IV minus RV 880 bps corn (25.6 vs 16.8), 230 bps otherwise; soybeans 450 vs 210 bps | no; no straddle returns | verified |
| Diersen and Wang, NCCC-134 2023 | corn, 2017-2021, settlement IV | weekly IV 35.1 the day before vs 22.5 at the report-day settle; nearby 23.8 vs 21.0; daily range 14.19 c on report dates vs 8.08 c; notes settlement IV is smoothed | no | verified |
| Isengildina-Massa, Irwin, Good, Gomez, Agribusiness 2008 | corn and soybeans, 1985-2002 | WASDE lowers IV 0.7 and 0.8 vol points; 1.1 and almost 1.5 with Crop Production | no | verified (abstract) |
| Cao and Robe, JFM 2022 | corn and soybeans (90-day constant-maturity IV) | IV lower for several days after reports; larger drop with expert disagreement | no | verified (abstract) |
| Yang and McKenzie, NCCC-134 2024 (JFM 2025) | corn new-crop IV, 1995-2022 | pre-report IV biased and inefficient; options slow to absorb report news | no | verified (abstract) |
| Adjemian, Johansson, McKenzie, Thomsen, AEPP 2018 | October 2013 WASDE cancelled | without the report, IV did not resolve and options stayed dear: a natural experiment that the drop is caused by the report | no | verified at secondary source |
| Ma and Serra, working paper 2024 | CME Market Depth, corn and soybean options, Jan 2019 to Jun 2020 | quoted spread day session mean 0.38 c, median 0.23 c (corn); 3 to 17 trades per option per session | the only option-spread measurement found | verified |

The closest paper is He and Bian (2025). Its effect, a 3 to 7% release-day loss to the straddle
buyer, is the gross premium this lane would harvest, but its data, maturities and cost treatment
could not be read. The idea is crowded in knowledge: the IV drop has been published since 1994,
CME markets weekday options explicitly for trading around reports (recalled, CME press release
snippet), and its own commentary quotes report "event volatility" (corn above 35% against a
typical 20% in September 2024; recalled, snippet). No net-of-cost test was found. The nearest
closed project directions are Deribit BTC macro events (ordinary variance premium, no event
surplus) and index options on mega-cap earnings nights (priced fairly); grains differ by venue,
by the release falling inside the session, and by a peer-reviewed event-specific premium.

## 2. Mechanism and timing

Who pays: hedgers and position-takers buying options ahead of a report. Report-day option
volume in corn rises 56% in calls and 72% in puts (Diersen and Wang 2024, verified), and the
premium grows with pre-report forecast dispersion (He and Bian; Cao and Robe, verified). Why it
can persist: the jump is hard to hedge (futures can trade limit on large reports, recalled), and
option liquidity provision is thin, 3 to 17 trades per option per session (Ma and Serra, verified).

Timing: WASDE and the NASS reports have been released at 12:00 ET, 11:00 CT, since January
2013, inside the CBOT day session (08:30 to 13:20 CT; Ma and Serra, verified; the 2013 change is
recalled from trade-press snippets). Before 2013 they came out at 08:30 ET with the market closed,
the equity-earnings analogue. Prices absorb the release within about 5 to 15 minutes (recalled).
This is the main structural difference from earnings: a seller can sell minutes before the release
and buy back within the hour, holding almost no diffusive risk, so the trade is close to a pure
bet on the event. Whether quotes stay tight at 10:55 CT, when market makers face the jump, is the
critical unknown and no free source measures it.

Calendar (verified, `data/usda_report_dates.csv`, from ESMIS): 213 distinct report dates from
2013 to 2026-11-10, about 15 a year; 65 on Fridays, 50 Tuesdays, 48 Thursdays, 31 Wednesdays,
19 Mondays. WASDE was not issued in October 2013, January 2019 and October 2025. Since
Monday-to-Thursday options were added in February 2025, every report date has a same-day expiry.

## 3. Tradability at Interactive Brokers

- Product: CBOT options on corn (ZC), soybeans (ZS), Chicago wheat (ZW), 5,000 bushels, option
  tick 0.125 c/bu (USD 6.25), futures tick 0.25 c (verified, Ma and Serra). Standard, serial,
  Friday weekly, short-dated new-crop, and Monday-to-Thursday weekday expiries (weekday launch
  recalled). American style, exercising into futures. IB trading-class codes for weeklies were not
  verified.
- Hours against the event: report at 11:00 CT inside the 08:30 to 13:20 CT session (verified).
- Market data: CBOT Real-Time (L1) USD 1.55 a month for non-professionals; delayed CBOT data lags
  10 minutes on IB, not 15 (verified, IB market-data page, 2026-11-13).
- Commissions: USD 0.85 per contract per side plus exchange and regulatory fees (verified, IB
  page). The CBOT fee was not verified; USD 1.50 is assumed in the arithmetic below.
- Margin: SPAN; the requirement for a short straddle was not verified. Paper-account support for
  futures options is lane N20's question.

## 4. Data

- On disk: nothing. `data/cache/` holds no grain futures or options.
- Free: none found within the rules. CME's site returns HTTP 403 to automated clients and its
  terms prohibit scraping (verified); the Internet Archive holds one capture of the settlement
  file, a 404; Yahoo and Stooq disallow all agents in robots.txt. Free futures settlements were
  therefore not obtained either, and the realised side below comes from published ranges.
- Paid, priced from the public list (verified, databento.com/pricing): a Databento Standard plan
  is USD 199 for one month and includes 12 months of CME L1 history (BBO, MBP-1, TBBO, trades)
  and 16+ years of L0 (OHLCV, definitions, statistics). One month buys: top-of-book quotes on CBOT
  grain options from about 2025-11 to 2026-11 (about 14 report dates, the whole weekday-option
  era, intraday at 10:55 and 11:30 CT), plus a settlement and bar history back to 2010 if the
  statistics schema carries option settlements (recalled; verify on the schema page first).
  Older L1 is pay-as-you-go and the per-GB price is only in the catalogue, so it needs the
  project's free cost call with a hard cap and the team lead's go-ahead. Licence terms for CME
  data through Databento were not checked.
- Settlement data cannot measure a taker's cost and settlement IV is smoothed (Diersen and Wang
  2023 say so); the long history can only give a gross-at-settlement reading, to which a cost
  model calibrated on the 12-month L1 window would be applied and labelled as such.

## 5. Cost and power arithmetic (calculation from published aggregates, not a result)

`scripts/cost_and_power.py`, output in `logs/cost_and_power.log`. Inputs: Ma and Serra spreads,
pooled IV 0.22 and 32-day tenor; Diersen and Wang ranges converted to a standard deviation by the
Parkinson factor; corn at 430 c (assumption).

Quoted spread on both legs, per side, as a share of an at-the-money straddle premium:

| Straddle | Premium | One tick (0.125 c) | Median (0.23 c) | Mean (0.38 c) |
|---|---|---|---|---|
| Front, 32 days, one-day hold over the report | 22.4 c | 0.6% | 1.0% | 1.7% |
| Weekly, about 5 sessions including the report | 14.1 c | 0.9% | 1.6% | 2.7% |
| Same-day expiry sold before 11:00 CT | 6.2 c | 2.0% | 3.7% | 6.1% |

Round trip on the front straddle, spread plus commissions and the assumed fee: 2.0% (one tick),
2.9% (median), 4.2% (mean) of premium. Against He and Bian's 3 to 7% gross, the implied net is
+1.0 to +5.0%, +0.1 to +4.1% and -1.2 to +2.8% per trade. The pooled spreads cover all actively
quoted strikes in 2019-20, not at-the-money quotes at 10:55 CT on report days, which could be
tighter (at-the-money) or much wider (before the release). This is the number the pull must
replace.

Power: the one-day hold has a P&L standard deviation of about 9.5% of premium (gamma 6.5%, vega
6.8%, assuming a 1.5 vol-point standard deviation of the report-day IV change), so a +2% net mean
needs about 175 independent report dates and +3% about 78. A same-day straddle held to expiry
has a standard deviation near 76% of premium and needs about 450 dates to resolve +10%. At 15
dates a year with the three grains sharing each date, a forward paper test cannot establish the
edge in any useful horizon; it can only check fills against the modelled touch.

## 6. Verdict detail, kill criterion and forward test

Viable pending the USD 199 pull. Kill if, on the L1 window, the median at-the-money quoted
spread on the front straddle at the decision time on report dates is at least 4% of premium per
side, or if the held-out report-minus-control interval has an upper bound below +1% of premium.
The draft pre-registration (one-day hold at 13:14 CT, and an intraday 10:55 to 11:30 CT variant,
each against same-series same-weekday controls one week either side, date-clustered) is in
`diagnosis.log`; it is not frozen. A forward paper test would subscribe to CBOT L1 (USD 1.55 a
month), log the decision-time quotes and hypothetical fills on every report date, and be judged
on fill realism, not on P&L.

## 7. What could not be verified

He and Bian's sample, maturities and cost basis; the CBOT agricultural option exchange fee; the
weekday-option launch details, expiry time and IB trading classes (CME pages blocked); SPAN
margin for a short grain straddle; whether Databento's statistics schema carries CME option
settlements and the per-GB price of older L1; at-the-money spreads near the release time; the
2013 release-time change and the 5 to 15 minute absorption, both from search snippets only.

## Rebuild

`python -I scripts/fetch_usda_calendar.py --out data/usda_report_dates.csv` (about 40 requests
at one a second) and `python -I scripts/cost_and_power.py > logs/cost_and_power.log`, run from
this folder.
