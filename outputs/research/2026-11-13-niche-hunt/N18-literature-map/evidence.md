# N18 evidence map: scheduled-event volatility premia across asset classes

## Question, scope and standard

Question: where outside US single-name earnings does published evidence show a scheduled-event
volatility premium (options or variance priced above what the event delivers), and how much of
that evidence survives transaction costs? Scope: equity index and VIX on macro days, Treasury and
rates options, FX options, grains, livestock, energy (EIA, OPEC), metals, elections and political
events, crypto, prediction markets, plus the strongest counter-evidence. Success criterion for the
lane: a ranked map that tells the other nineteen lanes which market-and-event pairs carry
net-of-cost evidence, which carry only gross or settlement-based evidence, and which carry none.

Labels used on every claim: **V** verified at the source in this lane (abstract or full text
read; the location is in `sources.csv`), **V2** verified only at a secondary summary of the
source (the paper itself not read), **R** recalled and not checked here, **C** conjecture or
arithmetic done in this lane.

Process note: the session's shared web-search budget ran out part way through the lane; later
rows rely on direct fetches of URLs already found. The gaps this left are listed in the last
section. No pilot was run, so no trial IDs were used.

## 1. Headline reading

1. **Only two published results measure a scheduled-event volatility premium net of the touch,
   and neither is in options.** Fernandez-Perez, Frijns and Tourani-Rad (2017) short the front
   VIX future from 09:35 to 15:30 ET on FOMC days at the prevailing bid and ask plus 0.10% a
   trade: +125 bp a trade, per-trade Sharpe 0.37, 67% of days positive, March 2004 to December
   2013 (V). Krieger, Mauck and Chen (2012) report that short-VIX derivative positions on
   scheduled FOMC days earn significant returns after bid-ask spreads (V2, abstract summary).
   Every option-based event premium in the literature is measured at settlement, at the mid or
   against trailing realised variance.
2. **The option-side evidence for macro days is strong at the mid and comes from the Federal
   Reserve's own researchers.** Daily SPX expirations spanning CPI, FOMC, payrolls and GDP are
   priced above neighbouring expirations (ATM implied volatility up to 134 bp higher for FOMC,
   7.5%; FOMC variance risk premium 44% above control; Londono and Samadi 2023, 2017-2023, V).
   One-day ES and Treasury futures options on FOMC and payroll eves carry positive and mostly
   significant variance risk premia measured against five-minute realised variance (Wright 2020,
   published 2025, V). These are the closest analogues to the project's own trade, with one
   difference that matters: the event jump in an index is small relative to the diffusive day,
   so the premium share of the straddle is smaller, but the half-spread on SPX or ES is far
   smaller still.
3. **Commodity report days are the best-documented premium outside equities and macro, and no
   study measures costs.** WASDE and other USDA reports cut grain implied volatility (0.7 points
   corn, 0.8 points soybeans, 1985-2002, V); weekly grain options over report weeks overprice
   realised volatility by 880 bp (corn) and 450 bp (soybeans), 2017-2021 end-of-day data (V); a
   long straddle loses 3% to 7% on report days only (He and Bian 2025, V2 abstract; sample and
   pricing basis unverified because the publisher page refused the fetch).
4. **The cross-cutting regularity the project already found on earnings appears in the earnings
   literature itself.** Gao, Xing and Zhang (2018) compute straddle returns at the closing
   bid-ask midpoint and find the pre-earnings straddle return rises from 1.14% to 4.93% across
   option bid-ask spread groups (V): the premium lives where it is most expensive to trade. Any
   market proposed by another lane should be checked for the same gradient.
5. **Counter-evidence is real and specific.** Treasury sector index options show predictable
   implied volatility around announcements but no profit after trading costs (Heuson and Su
   2003, V). An OptionMetrics study of index straddles finds the straddle premium negative around
   most announcements but positive (that is, buyers win) around FOMC meetings (DeSimone and Laux,
   V2), which conflicts with Wright's positive FOMC variance premium on a different sample. OPEC
   meetings move WTI implied volatility only slightly on average (OptionMetrics 2025, 57 meetings
   since 2005, V).

## 2. The map

Columns: market and event; closest work; sample and N; effect size with basis; costs measured;
event-time structure; replications or failures; label. "Not on closed list" is checked against
`docs/RESEARCH_STATE.md` section 2.

### 2.1 Equity index and VIX on macro days

| Pair | Work | Sample, N | Effect, basis | Costs | Event timing | Replication / failure | Label |
|---|---|---|---|---|---|---|---|
| SPX daily expirations over CPI, FOMC, NFP, GDP | Londono and Samadi (2023), FRB IFDP 1376 | Jan 2017 to May 2023; 75 CPI, 51 FOMC, 26 GDP, 74 NFP; OptionMetrics | ATM IV of spanning expiries +44 bp (GDP) to +134 bp (FOMC) over neighbours, +2.5% to +7.5%; VRP up to +63 bp (FOMC), +44%; release fixed effects, SE clustered by release | None. VRP is implied minus trailing realised, not a P&L | CPI, NFP, GDP 08:30 ET (pre-open for SPY, inside SPX global trading hours, R); FOMC 14:00 in session | Extended by Knox, Londono, Samadi and Vissing-Jorgensen (2024) and a 2025 FEDS Note | V |
| SPX daily expirations, data-driven "equity premium events" | Knox et al. (2024) | Oct 2016 to Dec 2023 trade dates | 38 most significant forward days include 9 CPI, 7 NFP, 13 FOMC and the 2016 and 2020 presidential elections; option-implied equity premium (forward SVIX, IEP), not variance | None | as above | Same team | V |
| SPX and STOXX 50 daily expirations, US and euro-area events | Londono and Samadi, FEDS Note (3 Oct 2025) | Sep 2023 to Jul 2025; 1,716 US and 1,747 euro-area observations | LVIX event premia, annualised bp: US CPI 45 (t 10.4), US policy rate 49 (t 4.7), US employment 53 (t 8.8); euro-area policy rate 28 (t 6.2) in STOXX 50; French election of July 2024 2.75 (% annualised) in STOXX 50, 99th percentile | None | ECB 14:15 CET decision in session (R) | The note's text and table disagree on the FOMC figure (53 vs 49) | V |
| ES (E-mini S&P) and Treasury futures 1-day weekly options, FOMC and payroll eves | Wright (2020 NBER w28306; J. Time Series Analysis 2025) | NFP Jan 2011 to Aug 2020; FOMC Jun 2017 to Aug 2020 (Wednesday meetings only; about 25, C); CME settlement prices | Event-induced implied daily variance (S&P): FOMC 0.241 (SE 0.115), NFP 0.423 (0.223). Variance risk premium on event day, S&P: FOMC 0.248 (0.076), NFP 0.204 (0.100). Units: daily variance in squared percent of price, Newey-West SE | None; settlement-based IV | Options valued at the close of the eve; release next day | DeSimone and Laux disagree on FOMC sign for straddles (below) | V |
| SPX straddles around many macro announcements | DeSimone and Laux, "The timing of variance risk premia around macroeconomic news events" (OptionMetrics, 2018) | Not read (PDF 404) | Straddle premium negative around announcements (sellers earn), positive around FOMC (buyers earn); CPI, NFP, ISM and industrial production days show sharply negative straddle returns | Not stated | n/a | Conflicts with Wright on FOMC | V2 |
| S&P 500 FOMC jump premium from pre-FOMC options | Liu, Tang and Zhou (2022), JFE 145(1) | 192 meetings, 1996-2019 | Recovered FOMC risk premium 1 to 326 bp, mean 45 bp (equity return premium, not variance); out-of-sample R2 7.51% for announcement returns | None | 14:00 in session | | V2 |
| SPX tail risk around FOMC | Beckmeyer, Branger and Grünthaler, "Fed Tails" (working paper) | Not read | Hedging premium "approx. 9% per meeting"; uncertainty builds days ahead and resolves at the decision; unique to FOMC among macro releases | None | | | V2 |
| VIX and VIX futures on FOMC days | Fernandez-Perez, Frijns and Tourani-Rad (2017), J. Empirical Finance 41 | VIX 1996-2013, 143 scheduled meetings; VIX futures Mar 2004 to Dec 2013 (about 78 meetings, C); TRTH intraday quotes | VIX and front future fall immediately after the statement for about 45 minutes. Short front future 09:35 to 15:30 at bid/ask plus 0.10% a trade: **+125 bp a trade, per-trade Sharpe 0.37** (annualised by √8 to 1.04), 67% positive; second future +56 bp, Sharpe 0.22. 2008-2013: +114 bp, Sharpe 0.40. Non-announcement days lose after costs | **Yes, at the touch** | Intraday, in session | Krieger, Mauck and Chen (2012) find the same sign net of spreads; Huang, Tsai and Yang (2024, IRFA) find predictable order imbalance in VIX derivatives during the FOMC blackout. No post-2013 out-of-sample test found | V |
| VIX derivatives on FOMC days | Krieger, Mauck and Chen (2012), Fin. Markets and Portfolio Mgmt 26(3) | Not read | VIX declines significantly on scheduled meeting days; short-VIX derivative positions earn significant returns after bid-ask spreads; not a mechanical effect | Yes (per abstract) | | | V2 |
| NDX 1-day ATM straddles over FOMC | Nasdaq practitioner note (not fetched; page timed out) | 12 meetings | Overpriced in 10 of 12; one December 2024 loss (straddle 187.40 against a 790.69 settlement) | Not modelled | | | V2 (search summary) |
| US elections, VIX | Goodell and Vähämaa (2013) JBF 37(3); St Louis Fed note (Dec 2024) | 5 elections (IEM data); 10 presidential elections since 1988 | VIX rises with the eventual winner's probability; VIX falls -15% on average (median -11%) from two days before to three days after presidential elections, -7.3% after midterms; fell the day after in 7 of the last 10 | None | Results overnight, options closed | Exceptions 2000, 2008, 2012 | V (Fed note), V2 (JBF) |
| Country equity index options, national elections and G20 summits | Kelly, Pástor and Veronesi (2016), JF 71(5) | 20 countries, 1990-2012, monthly expiries, OptionMetrics | Spanning ATM options +1.43 vol points a year, about 5.1% more expensive; 5% OTM puts +9.6%, 10% OTM +16.0%; VRP +0.0107 a year; about 8% more expensive in weak economies, 1% in strong | None (BS IV from closing bid-offer) | Elections mostly at weekends | Knox et al. find the 2016 and 2020 US elections among the most priced days | V |

### 2.2 Treasury, rates and FX options

| Pair | Work | Sample, N | Effect, basis | Costs | Event timing | Replication / failure | Label |
|---|---|---|---|---|---|---|---|
| ZF, ZN, ZB weekly options, FOMC and NFP | Wright (2020/2025) | as above | Event-induced implied daily variance, FOMC: 5y 0.042, 10y 0.066, 30y 0.144; NFP: 0.055, 0.233, 0.631 (all significant). VRP, FOMC: 5y 0.019 (ns), 10y 0.031 (SE 0.015), 30y 0.116 (0.034); NFP: 0.028, 0.077, 0.177 (all significant). Roughly half the FOMC event variance in 5y and 10y is premium, most of it in 30y; only a small share for NFP in 10y and 30y | None; settlement | NFP 08:30, in the CME overnight session (R) | 2-year weeklies too illiquid (2019 Friday volume 142, settlements at minimum tick) | V |
| Treasury bond and Eurodollar options, employment report and PPI | Ederington and Lee (1996), JFQA 31(4) | 1980s-1990s (not read) | ISD falls after scheduled releases; Friday drop and Monday rise in ISD is explained by the release calendar | None | | Foundational; replicated by Beber and Brandt | V2 |
| Treasury futures options, implied densities | Beber and Brandt (2006), JME 53(8) | not read | Releases reduce the second moment of the implied density regardless of the news; higher moments respond to news direction | None | | Beber and Brandt (2009) extend to stocks | V2 |
| CBOE Treasury sector index options | Heuson and Su (2003), Financial Review 38(1) | intraday | IV rises the afternoon before market-moving releases and normalises as fast as cash prices; **no arbitrage profit after trading costs** | **Yes; result is null** | | Counter-evidence | V |
| Swaptions, macro releases | Fornari (2004, BIS Quarterly Review) | | Implied volatility falls after releases | | | | R |
| USD FX on FOMC days | Mueller, Tahbaz-Salehi and Vedolin (2017), JF | | Short-dollar spot carry earns more on FOMC days, rising with monetary-policy uncertainty measured from Treasury futures options | Spot only; no option premium measured | | Karnaukh: pre-FOMC dollar return higher when FX implied volatility is high | V2 |
| FX options, central-bank meetings (ECB, BoE, BoJ) | none found | | Dealer commentary only: overnight implied volatility over an ECB decision described as the year's highest outside the US election (Reuters columns, Tickmill) | | | **No peer-reviewed event-volatility premium for FX options found** (search budget exhausted before a second pass) | V (commentary) |

### 2.3 Grains, livestock, energy and metals

| Pair | Work | Sample, N | Effect, basis | Costs | Event timing | Replication / failure | Label |
|---|---|---|---|---|---|---|---|
| Corn and soybean options, WASDE | Isengildina-Massa, Irwin, Good and Gomez (2008), Agribusiness 24(4) | 1985-2002 | IV falls 0.7 points (corn) and 0.8 points (soybeans) on average; 1.1 and nearly 1.5 points for reports with domestic and international outlook; strongest 1996-2002 | None | WASDE 12:00 ET, inside the day session (R) | Irwin, Good and Gomez (2001); McNew and Espinosa (1994) found the same for Crop Production | V |
| Corn, soybeans: WASDE, Grain Stocks, Prospective Plantings, Acreage | Cao and Robe (2022), JFM 42(2) | 90-day constant-maturity IV | IV falls after release and stays low up to five days; smaller drop when the report surprises; depends on pre-report analyst dispersion | None | | | V2 |
| Corn and soybean weekly options, major USDA reports | Diersen and Wang (2025), JAAE 57(1) | 1 Jan 2017 to 31 Dec 2021; 1,261 days, 74 report dates (59 WASDE); CME end-of-day data | Weeklies overprice realised volatility by 420 bp (corn), 280 bp (soybeans); reports add 650 bp and 240 bp; report-week VRP 880 bp and 450 bp; report-week IV 25.6% vs RV 16.8% (corn) | None; no option returns or spreads analysed | | | V |
| Corn, soybeans, wheat options, WASDE: announcement VRP | He and Bian (2025), J. Agricultural Economics 76(3) | Not verified (publisher returned 403) | Announcement jump model; options overpriced chiefly against report-day realised volatility; **long straddle loses 3% to 7% only on release days**; larger when forecast dispersion is high | Not verified | | Closest published analogue of the project's trade outside equities | V2 |
| Corn options after August crop reports | Yang and McKenzie (2025), JFM 45(10) | | Options adjust partially and gradually to the updated volatility expectations; short-term misalignment over the first two days | None | | | V2 |
| Wheat, USDA reports | Bunek and Janzen (NCCC-134, 2015) | | Realised volatility rises rather than falls after wheat reports | | | Counter-evidence for wheat | V2 (search snippet) |
| Live cattle, lean hogs: Hogs and Pigs, Cattle on Feed | Isengildina, Irwin and Good (2006), JARE; McKenzie, Thomsen and Adjemian (NCCC 2015) | 1985-2004 | Hogs and Pigs raises conditional SD of lean hog returns by 96%; cattle reports 26% to 37.5%. Skew studies find persistent put skew; no premium test | None | Livestock reports at 15:00 ET after the close (R): an overnight gap like earnings | No option-premium study found | V2 |
| WTI options, OPEC meetings | Horan, Peterson and Mahar (2004), Energy Journal 25(3) | not read | IV drifts up before meetings and falls after | None | Variable timing | OptionMetrics (Friedman, Oct 2025), 57 meetings 2005-2025: IV declines on average "albeit minorly"; largest IV moves not near meetings | V2 / V |
| WTI options and futures, weekly EIA crude inventory | Miao, Ramchander, Wang and Yang (2018), JFM 38(1) | | Near-the-money options most sensitive; response declines with maturity | Not stated | Wednesday 10:30 ET in session (R) | Sharma (UGA thesis, 1998-2013): IV falls on report days | V2 |
| Natural gas options, weekly EIA storage | none found | | Only practitioner commentary | | Thursday 10:30 ET in session (R) | **Gap** | V |
| Gold and silver options, FOMC or CPI | none found | | CME commentary only | | | **Gap** | V |

### 2.4 Crypto and prediction markets

| Pair | Work | Sample, N | Effect, basis | Costs | Replication / failure | Label |
|---|---|---|---|---|---|---|
| BTC options (Deribit), FOMC and CPI | Project's own test | `other_markets/findings/deribit_macro.md` | Ordinary variance premium, no event surplus: paired +0.079% [-0.275, +0.440], N=116 | | **Closed** | V (repo) |
| BTC options, FOMC | Practitioner notes (BIT, Deribit Insights, Amberdata) | | IV marked up before known dates; no systematic event-window statistic | | No academic study found | V (commentary) |
| Kalshi event contracts | Bürgi, Deng and Whelan (Jan 2026), "Makers and Takers" | over 300,000 contracts | Favourite-longshot bias; makers earn more than takers; both show the pattern. VoxEU summary: takers about -32%, makers about -10% on average (V2) | Fees modelled | Project's Kalshi tail and maker tests **closed** | V |

### 2.5 Single-name earnings (for calibration; the project's home market)

| Work | Effect | Costs | Label |
|---|---|---|---|
| Gao, Xing and Zhang (2018), JFQA 53(6) | ATM straddle from three days before to the announcement +3.34% (closing bid-ask midpoints); +1.14% in the lowest option-spread group, +4.93% in the highest | **Mid only**; the premium is largest where spreads are widest | V |
| Govindaraj, Jin, Livnat and Zhao (SSRN 2501750, 2014) | Net straddle returns (after transaction costs) around earnings and annual meetings are significantly negatively related to predicted volatility; option traders price the event correctly | Yes, for long straddles | V |
| Dubinsky, Johannes, Kaeck and Seeger (2019); Alexiou et al. (2025); Barth and So (2014) | Earnings as a priced jump; variance premium concentrated on announcement days | No tradeable P&L | R (project references) |
| Project: the crush is real and vega-carried, positive at the mid, eaten at the touch | `docs/RESEARCH_STATE.md` section 2; `outputs/research/2026-11-13-alpha-hunt-2/SUMMARY.md` | Measured | V (repo) |

## 3. Cross-cutting regularities

1. **Implied volatility falls after scheduled releases in every market studied**: Treasury and
   Eurodollar (Ederington and Lee 1996), Treasury densities (Beber and Brandt 2006), VIX after
   FOMC (Fernandez-Perez et al. 2017), grains after WASDE (Isengildina-Massa et al. 2008; Cao and
   Robe 2022), crude after OPEC and EIA (Horan et al. 2004; Sharma), equity indices after
   elections (St Louis Fed 2024). The fall is the mechanical removal of event variance. It is
   not, on its own, a premium; the literature that separates the two (Wright; Diersen and Wang;
   He and Bian; Londono and Samadi) finds a premium on top of it in index, Treasury and grain
   options. Label V for each cited row.
2. **No published option study measures the event premium at the touch.** The two touch-level
   results are in VIX futures. This is the gap the project's own evidence warns about.
3. **The premium concentrates where trading is costly** (Gao, Xing and Zhang 2018; Goyal and
   Saretto 2009 on illiquid names, R). The markets where the half-spread is a small share of a
   one-day straddle (SPX, ES, front-month Treasury options, R and C) are the ones where the
   event premium is smallest relative to diffusive variance.
4. **Event timing differs by market, and it matters for the trade.** CPI, NFP and GDP land at
   08:30 ET, before SPY and single-stock options open (an overnight gap like earnings) but inside
   SPX global trading hours and the CME overnight session (R). FOMC (14:00), WASDE (12:00), EIA
   crude (Wednesday 10:30) and gas storage (Thursday 10:30) land in session, so a seller can exit
   minutes before and after, and the premium can be measured intraday. Livestock reports land at
   15:00 ET after the close (R).

## 4. Power arithmetic for a one-day index straddle (C)

This is arithmetic, not evidence. Take Wright's S&P FOMC figures at face value: a VRP of 0.248
squared-percent of daily variance. If the eve-of-FOMC one-day implied variance were about 1.0
(1% daily, about 16% annualised, C), the premium would be about a quarter of implied variance,
and a short straddle priced in volatility terms would keep roughly 1 - sqrt(0.75), about 13% of
premium, before costs. The realised payout is the absolute move, with expected value 0.87 of
premium on these numbers; the ratio of its standard deviation to its mean is 0.76 for a normal
move and nearer 1.0 under fat tails. The per-trade Sharpe of the short one-day straddle is then
0.13 / (0.87 x 0.76 to 1.0), about 0.15 to 0.20 before costs. Detecting that at t = 2 needs
roughly 100 to 180 events: twelve to twenty years of FOMC meetings alone, or three to six years
of CPI, NFP and FOMC pooled (about 32 events a year). Costs: a round trip pays two half-spreads
(one if held to expiry). At 0.5% to 1% of premium per half-spread (plausible for SPX or ES, C)
the round trip takes 1% to 2% of a 13% edge; at the project's equity figure of 4% to 6% per
half-spread it would take 8% to 12%, most of the edge. The point: index macro days are limited by
power before cost, the reverse of single-name earnings.

## 5. Strongest counter-evidence, ranked

1. **The touch eats mid-measured premia** (project, V). Every option row in section 2 is at the
   mid, settlement, or against trailing realised variance.
2. **Heuson and Su (2003)**: predictable implied volatility around releases, no profit after
   costs, in Treasury sector index options (V).
3. **DeSimone and Laux (2018)**: index straddle buyers, not sellers, earn around FOMC (V2),
   against Wright's positive FOMC VRP (V). Samples differ (Wright: June 2017 to August 2020,
   one-day ES options).
4. **OptionMetrics on OPEC (2025)**: average IV change around 57 meetings small (V).
5. **Govindaraj et al. (2014)**: net straddle returns around earnings and shareholder meetings
   say options price the event correctly (V).
6. **Decay after publication**: pre-FOMC equity drift reported as disappearing (Kurov, Wolfe and
   Gilbert, R); McLean and Pontiff (2016) on post-publication decay (R). The Fernandez-Perez VIX
   result ends in 2013 and has no published out-of-sample test (V for the absence in what was
   read).
7. **Wheat**: realised volatility rises after reports (Bunek and Janzen 2015, V2), so the grain
   result does not transfer across grains without its own test.

## 6. Ranked five market-and-event pairs not on the closed list

Ranking weighs net-of-cost evidence first, then mid-level evidence with a plausibly small
half-spread share, then whether the team can test it at zero cost.

1. **SPY and SPX one-day options over 08:30 CPI and payroll releases (FOMC second).** Evidence:
   Londono and Samadi (2023), Wright (2025), Knox et al. (2024), FEDS Note (2025), DeSimone and
   Laux for CPI and NFP sellers (V, V2). Differs from the closed "SPY macro-release straddles"
   row because that test used DoltHub (N=5); `data/cache/index_chains` holds SPY 15:59 and
   10:00 snapshots for 2016-2026, which allows sell-at-15:59, buy-back-at-10:00 over the release
   with SPY daily expiries since late 2022 (R for the listing date). Main risk: power (section 4).
2. **Front VIX futures (CFE VX) short on FOMC days, intraday.** The only peer-reviewed
   net-at-the-touch event result found: +125 bp a trade, per-trade Sharpe 0.37, 2004-2013 (V).
   Needs an out-of-sample test on 2014-2026 and a check that it is not the unconditional short
   VIX roll yield (the paper's non-announcement days lose after costs, which argues against).
3. **Corn and soybean weekly and short-dated new-crop options over WASDE, Acreage and Grain
   Stocks.** Diersen and Wang (V), He and Bian (V2), Isengildina-Massa et al. (V), Cao and Robe
   (V2). Releases fall at 12:00 ET inside the session (R), so entry and exit can bracket the
   release tightly. No cost evidence at all; the half-spread on a weekly corn straddle is the
   open number (lanes N01 and N19).
4. **ZN and ZB weekly options over FOMC and NFP.** Wright (V): significant event VRP in 10-year
   and 30-year, settlement-based. Counter-evidence: Heuson and Su (V). The 1/64 tick against a
   one-day straddle is the cost question (C), and 30-year carries the larger premium share.
5. **Euro Stoxx 50 daily and weekly options (Eurex OESX) over ECB decisions, euro-area HICP and
   national elections.** FEDS Note (2025): euro-area policy-rate premium 28 bp annualised, t 6.2,
   and the French election of July 2024 at the 99th percentile (V); Kelly, Pástor and Veronesi
   (2016) on elections across 20 countries (V). Measured as an equity premium (LVIX), not a
   variance premium, so it is one step further from the trade; data is not free (R).

Pairs left out and why: FX options over central-bank meetings (no academic premium evidence
found); natural gas storage and gold (no study found); crude over OPEC (premium small on the most
recent evidence); livestock (only skew studies, though the 15:00 ET release makes it the closest
in timing to earnings); crypto and Kalshi (closed).

## 7. What this lane could not verify

- He and Bian (2025): sample period, pricing basis (settlement or quotes) and whether costs were
  measured. Publisher page returned 403, and the search budget ran out before an SSRN copy was
  found.
- DeSimone and Laux (2018): the PDF link is dead (404); only OptionMetrics summaries were read.
- Kurov, Wolfe and Gilbert on the disappearing pre-FOMC drift; Horan, Peterson and Mahar full
  text; Fornari (2004); Muravyev and Pearson (2020) exact effective-to-quoted ratios (secondary
  summaries disagree on them).
- Any academic study of FX option event premia around ECB, BoE or BoJ meetings: one search found
  only commentary, and the budget ran out before a second pass.
- Release times and product trading hours marked R (08:30, 12:00, 15:00 ET; SPX global trading
  hours; CME Globex sessions) need confirming against BLS, USDA, Cboe and CME pages by lanes N01,
  N02, N05, N08 and N20.
