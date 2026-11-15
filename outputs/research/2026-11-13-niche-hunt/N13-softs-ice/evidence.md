# N13 softs-ice: evidence dossier

Lane question: is there a scheduled-event volatility premium in ICE US coffee, cocoa, sugar or
cotton options that survives costs at the touch and can be paper traded at Interactive Brokers?
Every claim carries a label (verified at the source, recalled, or conjecture) and a source in
`sources.csv`. Numbers from this lane's own computation cite the log that produced them.

## Hypothesis, scope and success criteria

Scope: options on ICE Futures U.S. Cotton No. 2 (CT), Coffee C (KC), Cocoa (CC) and Sugar No. 11
(SB) around their scheduled reports. Success, per the brief: a tested candidate with real-data
evidence net at the touch, or a sourced case for or against a metered data pull, priced.
The zero-cost pilot tested the necessary condition (a report-day variance excess) for the one
event family whose historical dates are free and complete, WASDE. Pass rule, frozen before the
read: held-out cotton variance ratio R of at least 1.5 with the excess interval above zero and
no placebo excess (`freeze_2026-11-13_wasde-event-variance.md`).

## 1. Prior work

No paper studies option-implied volatility around scheduled reports in ICE softs. The searches
covered cotton implied volatility around WASDE and Crop Production, cocoa grind data, CONAB
coffee and UNICA sugar releases; the closest work is below. The idea is not crowded in the
literature; that is weak evidence, because the desks that make these markets do not publish.

| Work | Market, sample | Finding | Costs | Status |
|---|---|---|---|---|
| Prokopczuk, Symeonidis and Wese Simen (2017), J. Banking & Finance 81 | 21 commodities incl. cocoa, coffee, cotton, sugar, FCOJ; CRB settlement prices 1984-2011; 60-day synthetic variance swaps | RV minus MFIV (annualised variance): cotton +2.775% (t 8.69), sugar -2.311% (t -3.97), cocoa -2.626% (t -6.51), coffee +0.974% (t 0.27; post-2001 -6.618%, t -4.50), FCOJ -1.566% (t -2.73) | assumed haircuts only (10% proportional or 2 vol points); not measured | verified (Tables 1 and 2 of the accepted manuscript) |
| Adjemian (2012), AJAE 94(1) | cotton, soybean, wheat futures, 1981-2010 | WASDE moves prices; about $190 per contract on an average report | none (futures) | recalled (ERS summary snippet) |
| Isengildina-Massa, Irwin, Good and Gomez (2008), Agribusiness 24(4) | corn, soybean options 1985-2002 | implied volatility falls 1.1 (corn) and 1.5 (soy) points on WASDE plus Crop Production sessions, 0.3 on WASDE-only sessions | none | verified (author summary page) |
| Cao and Robe (2022), JFM 42(2) | corn, soybeans, wheat, 2009-2019 | implied volatility drops after USDA reports, more so with prior disagreement and surprise | none | verified (abstract); not cotton |
| Diersen and Wang (2023, NCCC-134) | new-crop grain options | pre-report IV elevated; no sharp post-report drop in new-crop December options | none | recalled (snippet) |

Reading: the variance premium in cocoa, sugar and FCOJ options is documented at settlement
prices and is ordinary (unconditional), not event-specific. Cotton is the exception with
realised above implied over 1984-2011, so a short-volatility seller in cotton had no ordinary
premium to start from. None of these measured a taker's cost.

## 2. Mechanism and event timing

| Event | Market | Release time | Session (ET, verified at ice.com) | Inside or outside the session |
|---|---|---|---|---|
| WASDE (with NASS Crop Production Aug-Jan; also Prospective Plantings, Acreage) | CT mainly; SB marginal (US sugar only); none for KC, CC | 12:00 ET (recalled) | CT 21:00-14:20, KC 04:15-13:30, CC 04:45-13:30, SB 03:30-13:00 | inside every session, before settlement |
| ECA European cocoa grind, quarterly | CC | 08:00 CET, 02:00 NY (verified, eurococoa.com); dates 16 Apr, 16 Jul, 15 Oct 2026; 21 Jan 2027 tentative | CC opens 04:45 | outside: released while ICE US cocoa is closed |
| North American (NCA) and Asian (CAA) grind | CC | not verified | | unknown |
| CONAB coffee crop surveys (about four a year) | KC | not verified | | unknown |
| UNICA fortnightly cane crush | SB | not verified | | unknown |

Who would pay an event premium: commercial hedgers (merchants, roasters, grinders, mills) buying
protection into supply-side reports, the same hedging-demand story as Garleanu, Pedersen and
Poteshman (2009) for equity options (recalled). Why it could persist: market makers in thin
softs option books carry inventory across a jump they cannot hedge in a closed or fast market.
The pilot below says the WASDE jump itself is small in softs, which removes the event leg of
this story for WASDE. The European cocoa grind is the one release here with the structure of an
after-close earnings report (information arrives while the market is closed, so the opening
gap is unhedgeable), and it is untested.

## 3. Tradability at Interactive Brokers

All verified at the cited IB and ICE pages on 2026-11-13 unless marked.

- Products: ICE US Cotton No. 2 options (regular H K N V Z, serials F U X; 1-cent strikes; tick
  0.01 c/lb, $5); weekly cotton options CTW (three listed at all times, Friday expiries,
  American, exercise into the first eligible future, October excluded); weekly coffee KCW (tick
  0.01 c/lb, $3.75) and weekly sugar SBW, listed since 6 February 2012. No weekly cocoa option is
  named in ICE's weekly-option documents (verified absence in the 2014 FAQ; current listing not
  rechecked).
- Market data: ICE Futures U.S. (NYBOT) L1/L2 USD 142.00 per month, non-professional and
  professional, footnoted "Includes options". Without it IB's ICE US quotes are 10 minutes late,
  and fills against them are not evidence.
- Commissions: IBKR fixed USD 0.85 per futures-option contract (up to 1,000 a month) plus ICE
  exchange and clearing USD 2.10 per side for softs futures and options (September 2026
  schedule), plus USD 0.10 per exercise or assignment. About USD 2.95 per leg per side.
- Paper account: IB paper accounts trade futures options when the live account holds futures
  permissions and share the live account's market-data subscriptions (recalled; lane N20 owns
  this check).
- Margin: SPAN at ICE Clear U.S. for a short straddle (recalled; not priced here).
- Cost against premium (this lane's computation from the free futures series, conjecture on
  spread width): a five-session ATM cotton straddle at the 2014-26 median realised volatility of
  22.8% is about 2.03 c/lb (USD 1,015). One half-spread is 0.49%, 1.48% or 2.46% of premium if
  each leg is quoted one, three or five ticks wide; fees add 0.58% per side. The equivalent
  shares are about 0.1-0.5% for coffee (tiny tick on a USD 3,900 straddle), 0.6-3.0% for cocoa
  and 1.7-8.7% for sugar. Actual quoted widths in softs options are not observable at zero cost;
  ticks are a floor, and coffee widths in particular are likely many ticks (conjecture).

## 4. Data

- Option history: no free source. ICE's Report Center report partials are disallowed by
  robots.txt; USDA AMS publishes cotton futures settlements from January 2023 only; Barchart
  history sits behind paid tiers; NYU V-Lab is GARCH, not implied; `data/cache/` holds no ICE
  data. Settlement-only option data (CRB, as in Prokopczuk et al.) could not measure the touch
  anyway.
- Paid route: Databento IFUS.IMPACT covers every ICE US future and option, outrights, spreads and
  options, from 2018-12-23, in MBO, MBP-1, MBP-10, TBBO, trades, BBO-1s, BBO-1m, OHLCV,
  definition and statistics schemas (verified, catalog page). Usage pricing "starts at USD 10.00
  per GB" (verified, Databento blog); the public pricing page shows no per-schema rate, so the
  exact quote needs the vendor's cost call, which this lane did not make.
- Pull estimate for the one candidate worth testing, the European cocoa grind (conjecture on
  sizes): about 28 releases 2019-2026, each needing the 13:29 ET close before and the first
  half-hour after the 04:45 open, plus two same-weekday control nights per release, so about 84
  sessions of BBO-1m on CC options with the definition schema for strike mapping. At roughly
  0.5 to 5 GB that is about USD 5 to 50 at USD 10 per GB; a hard cap of USD 60 is appropriate.
  Restricting to near-the-money instruments by symbol cuts it further. Dates for the grind
  releases 2019-2025 must be assembled first (ECA lists only the current year; news archives
  carry the rest).
- Free data used: Yahoo continuous front-month daily closes for CT, KC, CC, SB, 2000-2026
  (`raw/softs_daily.csv`, 0.9 MB, rebuild with `scripts/fetch_futures.py`); WASDE dates from
  USDA ESMIS (`raw/wasde_dates.csv`, rebuild with `scripts/fetch_wasde_dates.py`, crawl delay
  respected).

## 5. Pilot: WASDE report-day variance in softs futures (real data)

Design, pre-registered in `diagnosis.log` before any outcome: settle-to-settle squared log
returns on WASDE dates against same-weekday sessions one week either side, with event-independent
stale-day and roll-window filters fixed from ICE contract rules. Coffee and cocoa are placebos;
sugar is a near-placebo. Discovery 2000-2013, held-out 2014-2026, read once after the freeze.
Basis: gross, futures, daily variance units, not a tradeable P&L. Intervals: date-clustered 95%
on the per-event excess (`protocol.date_clustered_ci`); event bootstrap for the ratio R.

| Trial | Block | Root | N | Mean excess r^2 [95% CI] | R [95% CI] | Robust abs ratio |
|---|---|---|---|---|---|---|
| 2,442 | 2000-13 | CT | 125 | +2.01e-4 [+4.58e-5, +3.56e-4] | 1.633 [1.114, 2.436] | 1.433 |
| 2,443 | 2000-13 | KC (placebo) | 94 | +6.80e-5 [-7.37e-5, +2.09e-4] | 1.226 [0.814, 1.876] | 0.851 |
| 2,444 | 2000-13 | CC (placebo) | 89 | -7.13e-5 [-2.62e-4, +1.15e-4] | 0.836 [0.510, 1.333] | 0.702 |
| 2,445 | 2000-13 | SB | 160 | +5.60e-5 [-7.69e-5, +1.93e-4] | 1.130 [0.839, 1.494] | 0.978 |
| 2,450 | 2000-13 | CT Aug-Jan | 63 | +2.11e-4 [+9.07e-6, +4.19e-4] | 1.734 [1.031, 3.185] | 1.698 |
| 2,451 | 2000-13 | CT Feb-Jul | 62 | +1.91e-4 [-4.12e-5, +4.34e-4] | 1.549 [0.902, 2.683] | 1.302 |
| **2,446** | **2014-26** | **CT (primary)** | **113** | **+6.29e-5 [-4.02e-5, +1.73e-4]** | **1.268 [0.839, 1.900]** | **0.901** |
| 2,447 | 2014-26 | KC (placebo) | 87 | -1.57e-4 [-3.90e-4, +5.02e-5] | 0.700 [0.434, 1.128] | 0.800 |
| 2,448 | 2014-26 | CC (placebo) | 85 | +2.05e-4 [-1.47e-5, +4.52e-4] | 1.585 [0.982, 2.514] | 0.868 |
| 2,449 | 2014-26 | SB | 149 | -4.63e-5 [-1.16e-4, +2.93e-5] | 0.845 [0.634, 1.104] | 0.763 |

Sources: `logs/discovery_2442-2445.log`, `logs/discovery_2450.log`, `logs/discovery_2451.log`,
`logs/heldout.log`, `trials.csv`.

Result: H1 fails on held-out. Cotton's WASDE session carried about 1.6 ordinary sessions of
variance in 2000-2013 and about 1.3 in 2014-2026, with an interval that includes no excess; the
median WASDE session is now quieter than its controls (robust ratio 0.90). No placebo shows an
excess, so the method is not the problem. Funnel (held-out CT): 153 releases, 153 trading days,
149 not stale, 115 outside roll windows, 113 with a control; roll drops are the delivery-month
WASDEs, fixed by the calendar. At the held-out event share of 0.241 of a five-session weekly,
a short straddle held to expiry needs WASDE-day variance overpriced by 8.9%, 17.1% or 25.3%
(one-, three- or five-tick legs, fees included) just to pay the entry, and the realised event
excess itself is not distinguishable from zero.

Eleven numbers were registered for this design (2,442 to 2,452); ten were scored (2,442 to
2,451); 2,452 was conditional on a discovery gap that did not appear and was never scored.
Numbers 2,452 to 2,471 are unused.

## 6. Verdict

WASDE in ICE softs: not viable. The event is too small in held-out data to carry an event-
volatility trade, so the trade collapses into the ordinary variance premium, which in cotton
historically ran against the seller. Kill criterion, met: held-out report-day variance ratio
below 1.5 with an excess interval spanning zero.

The European cocoa grind: untested, and the only softs event with the after-close structure.
Viable pending a priced data pull (Databento IFUS.IMPACT, about USD 5 to 50, cap USD 60, team
lead's go-ahead required), conditional on first showing at zero cost that the grind opening gap
is large: the same pilot on cocoa futures with grind dates assembled from news archives, with
a pre-registered bar of an opening-session variance ratio of at least 3 (an event share above
40% of a five-session option) before any money is spent. Cocoa has no weekly options, so the
vehicle is the front monthly option, which dilutes the event share further; that is the
strongest argument against it.

A forward paper test, if the grind passes both steps: sell the front cocoa ATM straddle at the
13:29 ET close before each European grind release, buy it back after 05:00 ET, against
same-weekday control nights, with the NYBOT subscription live (USD 142 per month) so that marks
are real-time; about four events a year, so a year of paper trading gives N of about 4 and can
only check execution, not significance.

## 7. Not verified

- WASDE's 12:00 ET release time (recalled; consistent with every session being open).
- Release times of the North American and Asian cocoa grinds, CONAB coffee surveys and UNICA
  reports; historical grind dates before 2026.
- Quoted bid-ask widths in any ICE softs option (no free intraday source); the shares of premium
  above are tick floors.
- Databento's per-schema price for IFUS.IMPACT and the byte sizes behind the pull estimate.
- IB paper-account access to ICE US futures options and SPAN margin on a short softs straddle.
- Whether ICE now lists weekly cocoa options (absent from the 2014 weekly-option documents).
- Adjemian (2012) and Diersen and Wang (2023) figures, read from summaries, not the papers.
- The web-search budget for the session ran out before the coffee and sugar event searches
  completed; those event families rest on the absence of evidence, not on a search that found
  nothing.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N13-softs-ice\evidence.md
