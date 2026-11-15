# N07 fx-central-banks: evidence dossier

Lane question: is there a scheduled central-bank event premium in FX options that survives the
touch and can be paper traded at Interactive Brokers, with history obtainable at zero cost?

Status of this dossier: evidence gathered and computed by the lane; the verdict is the analyst's.
Every number below traces to a file in this folder or a URL in `sources.csv`. No trial numbers
from the reserved block (2,262 to 2,291) were used, because no option-price history could be
obtained within the brief's rules; `trials.csv` is empty by design.

## 1. Hypothesis, scope and success criteria

Hypothesis: the overnight option spanning an ECB, BoJ, BoE, RBA, BoC or FOMC decision is priced
above the variance the decision delivers, by more than the cost of selling it at the touch on a
CME weekly FX option. Scope: CME FX futures options (EUR, JPY, GBP, AUD, CAD) with daily weekly
expiries, which IB can route; OTC quotes only as a price reference. Success: a zero-cost history
that measures the touch (not available), or a sourced case for or against a metered pull, priced.

## 2. Prior work

| Paper | Sample | Finding | Costs measured |
|---|---|---|---|
| Wright (2020), NBER w28306 | CME Wednesday and Friday weeklies on Treasury and E-mini S&P futures, settlements | Event-day variance premia large and positive, largest on FOMC days; about half the FOMC-day rise in implied variance is premium | No |
| Ederington and Lee (1996), JFQA | T-bond, Eurodollar and Deutschemark futures options | Implied vol falls after scheduled releases, rises after unscheduled news | No |
| Marshall, Musayev, Pinto and Tang (2012), JIFMIM | Four major FX rates, 1998-2009 | FX implied vol falls on US announcement days; only BoJ interventions move it otherwise | No (abstract) |
| Kostakis, McBride, Sarno and Wang (2025), SSRN 5781462 | CME FX options and spot, six pairs, 2006-2024 | Inverted short-over-long implied vol term structure precedes large moves; long strangles on strong inversion profit after realistic costs | Yes, by the summary's claim; figures not seen (SSRN returned 403) |
| Mueller, Tahbaz-Salehi and Vedolin (2017), JF | FX spot, FOMC days | Short-dollar excess returns concentrated on FOMC days | Not an options study |

Closest paper: Wright (2020) for the design (an option expiring the morning after the event,
against same-weekday non-event controls), but it covers Treasury and equity futures, not
currencies. For FX, Marshall et al. (2012) document the crush in implied vol but do not price a
trade. I found no paper that sells FX central-bank event vol net of costs. The web-search budget
was exhausted part-way through the lane, so this negative is not exhaustive (section 9).

The strongest counter-evidence is Kostakis et al. (2025): on the same CME options, the profitable
side around large moves is long, not short, short-dated vol. It is not a test of scheduled events,
but it says the short-dated FX vol a seller would sell is not obviously rich when the term
structure inverts, which is exactly what an event week does.

The idea is not crowded in print; in practice it is the core business of every FX options dealer,
who prices each event day explicitly (section 3). That is the reason to expect a thin premium.

## 3. Mechanism and timing

OTC FX dealers quote an explicit overnight event vol and its break-even in pips (verified: the
Reuters wraps in `sources.csv` quote, for example, EURUSD overnight 19.0 vol or 83 pips for the
12 December 2024 ECB, and USDJPY about 12.0 vol or 80 pips for the BoJ decision of 30 October
2026). The quoted break-even is the at-the-money straddle premium, 0.798 x vol x spot x
sqrt(1/365); this reproduces six of the seven quoted pip figures to within one pip
(`data/anecdotes_on_vol.csv`). Dealers price event days through event weights in a
variance-time model (recalled, practitioner texts), so the event is priced by professionals on
both sides, unlike single-name earnings where retail demand concentrates in the event expiry.

Who might pay: corporate and real-money hedgers who buy protection through a known risk, and
leveraged funds positioning for a surprise (conjecture). Why it might persist: dealers' short
gamma inventory into a jump they cannot hedge (conjecture, consistent with Wright's FOMC result in
Treasuries).

When the information arrives (recalled unless stated; CME times verified from the filing):

| Event | Release (New York time) | CME weekly that spans it | Notes |
|---|---|---|---|
| ECB | 08:15, press conference 08:45 (verified, EA-MPD notes) | Thursday EUR weekly, expires 09:00 CT = 10:00 New York | Press conference ends close to the expiry; US 08:30 data often the same morning |
| BoJ | about 21:30-23:00 the evening before the Tokyo date | JPY weekly expiring the next morning | Lands in thin Asian Globex hours |
| BoE | 07:00 Thursday | Thursday GBP weekly | |
| RBA | 23:30 or 00:30 Monday night | Tuesday AUD weekly | |
| BoC | 09:45 Wednesday | Wednesday CAD weekly, 15 minutes later | Press conference after the expiry |
| FOMC | 14:00 Wednesday | Thursday weekly in any of the five | |

Globex runs Sunday 17:00 to Friday 16:00 CT with a one-hour daily break (verified), so unlike
after-close earnings there is no closed-market gap: every decision lands while the option and its
future trade, though at thin hours for BoJ and RBA.

## 4. Tradability at IB

- Product: CME FX futures options, Tuesday and Thursday weeklies listed since trade date
  5 December 2022 alongside the Monday, Wednesday and Friday series (verified, CFTC copy of CME
  submission 22-440). Two of each weekday listed at a time; trading ends 09:00 CT on expiry day;
  European, auto-exercised against the CME FX fixing into the quarterly future (an in-the-money
  leg becomes a futures position that must be closed).
- Ticks: EUR 0.0001 (USD 12.50 on EUR 125,000), JPY 0.000001 per yen (USD 12.50 on JPY 12.5m),
  GBP 0.0001 (USD 6.25), AUD and CAD 0.0001 (USD 10); half-ticks below a small premium (verified).
- Commission: USD 0.85 per contract at IBKR Pro up to 1,000 a month, plus exchange and regulatory
  fees (verified, IB page as captured by lane N05). CME non-member Globex fee USD 1.60 and
  exercise fee USD 0.65 in the 2022 filing (verified then; may have changed).
- Market data: CME Real-Time (L1) at USD 1.55 a month in IB's non-professional column; CME
  delayed data on IB is 10 minutes, not 15 (verified, same capture). Without it, fills are not
  evidence.
- Margin: SPAN on futures options (recalled; not priced here). Paper-account access to FX futures
  options and shared subscriptions: recalled, not verified.

Cost floor (`scripts/cost_floor.py`, `data/cost_floor.csv`; a scenario, not a measurement): a
13.5-vol ECB straddle on one EUR contract is worth USD 818. One tick per leg of half-spread is
1.5% of that premium; with commissions, exchange fees and closing the exercised future, the
round trip held to expiry costs 2.9%, 4.4% and 7.5% of premium at quoted widths of 1, 2 and 4
ticks per leg. On JPY the tick is coarser relative to premium: a 12-vol BoJ straddle is worth
USD 412 and the same widths cost 5.7%, 8.8% and 14.8%. For comparison, the project's equity
hedged hold loses on a half-spread of 4-6% of premium (`docs/RESEARCH_STATE.md` section 2). The
EUR contract is cheaper at the touch only if quotes really sit one or two ticks wide on the
event-spanning weekly, which nothing free can show.

## 5. Data

- Option prices, zero cost: none found. Cboe FX vol indices (EVZ, EUVIX, JYVIX, BPVIX) return
  Access Denied on Cboe's CDN while VIX on the same path returns 200; DoltHub's options database
  carries no currency-ETF options; cmegroup.com blocks this client (403, not retried); FRED and
  Dukascopy hang on the project User-Agent (not retried with another); Yahoo option chains need a
  crumb (not used). CME settlement-only history would not measure the touch even if obtained.
- Metered route: Databento GLBX.MDP3 (CME Globex), `definition` to map the weekly series, then
  top of book (`bbo-1m`, or `mbp-1` restricted to 14:00-16:00 New York on the eve and 07:00-10:00
  on the expiry morning) for the event-spanning weekly and the matched same-weekday control, EUR
  and JPY first, December 2022 to date. Databento's static price list shows no per-GB rates (only
  the USD 125 one-time credit, already used by the team under its terms, and plans from USD 199 a
  month); my estimate is tens of US dollars (conjecture). Price it with the free cost call and a
  hard cap before any go-ahead.
- Free physical-measure data used here: ECB EA-MPD (meeting dates and intraday EURUSD moves),
  BoJ past-meeting page, the project's cached FOMC dates, Yahoo daily and hourly FX bars
  (`raw/`, about 14 MB).

## 6. What the free data show (physical measure only, gross, at the mid)

Design and the two data defects fixed before reading results are in `diagnosis.log`. M_P is the
event-day variance over the same-weekday non-event variance; v_fair is the overnight vol at which
a short at-the-money straddle over the window breaks even at the mid. Intervals are 95% event-level
bootstrap (each event its own date). Source: `data/realised_event_variance.csv`.

| Event, pair, window | N events / controls | M_P [95% CI] | v_fair [95% CI] |
|---|---|---|---|
| ECB, EURUSD, London day 2012-25 | 122 / 937 | 2.63 [1.81, 3.66] | 14.6 [12.6, 16.8] |
| ECB, EURUSD, London day 2019-25 | 54 / 462 | 1.59 [1.04, 2.27] | 11.0 [9.1, 13.1] |
| ECB, EURUSD, 10:00 to 10:00 NY 2024-25 | 14 / 84 | 0.80 [0.30, 2.09] | 7.3 [4.8, 10.1] |
| BoJ, USDJPY, London day 2012-25 | 120 / 1,971 | 3.39 [2.18, 4.88] | 17.0 [14.0, 20.3] |
| BoJ, USDJPY, 10:00 to 10:00 NY 2024-25 | 15 / 379 | 5.40 [1.94, 10.56] | 21.9 [13.0, 32.5] |
| FOMC, EURUSD, London day 2016-26 | 86 / 733 | 1.91 [1.40, 2.55] | 12.1 [10.4, 13.7] |
| FOMC, USDJPY, 10:00 to 10:00 NY 2024-26 | 23 / 160 | 5.62 [2.66, 10.98] | 22.1 [15.8, 29.0] |
| FOMC, AUDUSD, 10:00 to 10:00 NY 2024-26 | 23 / 166 | 2.36 [1.49, 3.50] | 15.0 [12.1, 18.1] |

Against these, the verified quotes (N=7, OTC mid, selection-biased toward notable events) imply
event-to-base variance multiples of 1.5 to 2.3 where a base is quoted. That is at or below the
realised multiple for BoJ and for FOMC on the yen, and inside the interval for FOMC on EURUSD and
AUDUSD. Only the December 2024 ECB quote (19.0 vol) sits well above v_fair, and its window also
held US PPI. All seven short straddles made money at the mid (+4% to +81% of premium), which a
fairly priced straddle also does most of the time because the median move is below the mean; it
is not evidence of a premium.

Three readings, conservative first. First, there is no visible systematic surplus on the sell
side: the quotes seen price these events roughly at, or below, what they deliver. Second, event
variance in FX is regime-dependent and fat-tailed (BoJ and FOMC on the yen in 2024-25 delivered
five times a normal day), which is the risk a seller is paid for and the reason a short book
would need many events to tell premium from luck. Third, the anecdotes hint at the opposite
trade, buying BoJ and FOMC yen event variance, in line with Kostakis et al.; with seven quotes
this is conjecture, not a finding.

## 7. Verdict for the analyst

Not viable as a zero-cost pilot: there is no free history of FX option prices, let alone quotes.
On the free physical-measure evidence and seven verified quotes, the short side shows no event
surplus large enough to beat a cost floor of about 3% to 7.5% of premium on EUR and 6% to 15% on
JPY. A metered pull is cheap and would settle it; on present evidence it ranks below lanes that
already show a gross premium.

Kill criterion for any pull: if the mean mid-to-expiry P&L of the short event straddle on the EUR
Thursday weekly over ECB meetings since December 2022, minus the same statistic on matched
non-event Thursdays, is not above the measured half-spread plus fees with its date-clustered 95%
interval excluding zero, the short side is closed; the same test with the sign reversed covers the
long BoJ and FOMC-yen variant.

Forward paper test, if wanted: subscribe to CME L1 at IB (USD 1.55 a month), and at 15:00 New York
on the eve of every ECB, BoJ, BoE, RBA, BoC and FOMC decision log bid and ask on the event-spanning
weekly straddle in the matching currency and on a same-weekday control, with the 10:00 fixing
outcome; about 45 events a year across five currencies.

## 8. Files

- `diagnosis.log`: pre-statement, defects, results.
- `scripts/realised_event_variance.py`, `logs/realised_event_variance.log`,
  `data/realised_event_variance.csv`, `data/anecdotes_on_vol.csv`.
- `scripts/cost_floor.py`, `logs/cost_floor.log`, `data/cost_floor.csv`.
- `raw/`: Yahoo chart JSON, EA-MPD workbook, BoJ page, CFTC filing copy. Rebuild with the URLs in
  `sources.csv`.
- `sources.csv`, `trials.csv` (empty: no trial run).

## 9. Not verified

- The web-search budget for the session ran out mid-lane, so the literature search is not
  exhaustive; a paper selling FX event vol net of costs may exist.
- Actual bid-ask widths and volume on CME event-spanning FX weeklies (the binding number).
- Current CME exchange fees (2022 filing used), SPAN margin for a short weekly straddle, and IB
  paper-account access to FX futures options.
- Kostakis et al. (2025) figures and cost assumptions (SSRN returned 403).
- Exact release times for BoJ, RBA, BoE and BoC (recalled); BoE, RBA and BoC calendars were not
  built (BoE page lists only rate changes, RBA returned 403, BoC page is script-rendered).
- Whether the OTC overnight quote and the CME weekly trade at the same vol on event days.
