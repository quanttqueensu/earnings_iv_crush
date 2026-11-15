# N14: bank stress tests, capital actions and PDUFA dates

Dossier for lane N14. Hypothesis, scope and pass rules were written to `diagnosis.log` before any
outcome was computed. Every number states its N, interval and basis; claims are labelled in
`sources.csv`.

## Scope and question

Does a scheduled, after-close regulatory event for large US banks (the Federal Reserve
stress-test results night, and the banks' capital-action disclosure night that follows) carry an
option premium a seller can harvest net of the spread at the touch, in the way earnings do? And
are large-cap PDUFA dates on liquid names a testable variant at zero cost?

Success criterion (lane level): either a tested candidate with real-data evidence, or a sourced
case for or against a metered pull.

## Event structure (verified at federalreserve.gov unless stated)

- Results are released after the cash close: 16:30 ET every year 2015-2025, 16:00 ET in 2026
  (exactly at the equity-option close, so still outside the session). 2013-2014 pages say "For
  immediate release" with no time (16:30 recalled). Full list with links: `stress_calendar.csv`.
- The date is pre-announced about two weeks ahead by press release (for example 13 June 2025 for
  27 June 2025; 6 June 2024 for 26 June 2024; 9 June 2026 for 24 June 2026).
- 2015-2019: two nights a week apart, DFAST results (no supervisory consequence) then CCAR
  (objections, capital plans; banks announced dividends and buybacks the same evening).
  2015 events were in March; 2016 onwards in late June.
- 2020-2026 (stress capital buffer era): one results night, then banks may disclose capital
  actions and their buffer after 16:30 on a date the results document names: Monday 28 June
  2021, Monday 27 June 2022, Friday 30 June 2023, 28 June 2024, 1 July 2025. 2020 (Monday 29
  June) is recalled; 2026 is inferred from "typically two business days" (Friday 26 June).
  2020 also had a second round on Friday 18 December, with buybacks announced that evening
  (recalled).
- Everything lands while the market is closed, the same timing as after-close earnings. The
  difference is the size of the news, measured below.

## Prior work

- Flannery, Hirtle and Kovner (JFI 2017; read as NY Fed Staff Report 744). Nine disclosure dates
  2009-2015, CRSP and OptionMetrics. Stress-tested BHCs show 3-day absolute CAR of 2.75% on
  average, with excess |CAR| of at least one percentage point on each date; abnormal volume is
  higher. Their one options measure, the change in one-month ATM implied vol over [t-1, t+1],
  "falls significantly around some event dates, though it rises significantly on others". No
  trading P&L, no costs. Verified. This is the closest paper and it already hints at the answer:
  there is no consistent crush.
- Guerrieri and Modugno (FEDS 2021-012). Overnight returns (close to next open) after DFAST and
  CCAR releases through 2019 sit in the tails of the prior six months; DFAST moves prices on
  resilience news, CCAR on capital distributions. Verified. Again no options, no costs.
- Fernandes, Igan and Pinheiro (JBF 2020): limited market learning from stress tests. Recalled
  from conference slides; journal text not read.
- I found no study of a tradeable volatility strategy around US stress tests, net of costs or
  otherwise. The web-search budget for the session ran out mid-lane, so this absence is labelled
  conjecture, not a finding. The idea is not crowded in print; the measurements below suggest why.

## Stage A: is there a jump to price? (trials 2472-2475, 2478)

Price data only: cached adjusted closes (`data/cache/yahoo_adj`), 2015-2026, ten banks tested
every year (JPM, BAC, C, WFC, GS, MS, USB, PNC, COF, STT). For each bank-night, z^2 is the
squared close-to-close reaction return over the session after the night, divided by the name's
trailing 60-session variance (earnings sessions removed). Controls: the same name, 5, 10, 15 and
20 sessions earlier, avoiding earnings, other event nights and FOMC, CPI and payroll reaction
sessions. Excess = event z^2 minus mean control z^2, in units of one ordinary session's
variance. Date-clustered 95% intervals, clusters = event nights. Discovery 2015-2019, held-out
2020-2026, rule fixed beforehand: held-out excess at least 1.0 with lower bound above zero.
Pre-registered and run once, with no discovery iteration; not hash-frozen (diagnosis.log entry 4).

| Trial | Nights | Block | N (nights) | Excess | 95% CI | Verdict |
|---|---|---|---|---|---|---|
| 2472 | all | 2015-19 | 90 (9) | +1.01 | [+0.23, +2.17] | discovery |
| 2472 | all | 2020-26 | 150 (15) | +0.51 | [-0.03, +1.16] | Fail |
| 2473 | results | 2015-19 | 40 (4) | -0.02 | [-0.14, +0.08] | discovery |
| 2473 | results | 2020-26 | 80 (8) | +0.96 | [+0.10, +2.02] | Fail (point below 1.0) |
| 2474 | capital actions | 2015-19 | 50 (5) | +1.83 | [+0.76, +3.58] | discovery |
| 2474 | capital actions | 2020-26 | 80 (8) | +0.25 | [-0.28, +0.85] | Fail |
| 2478 | all, market-adjusted | 2020-26 | 150 (15) | +0.86 | [+0.43, +1.44] | Fail (residual-variance units) |

Calibration (trial 2475): the same ten banks' earnings reaction sessions, 2015-2026, have mean
z^2 of 5.37 [4.03, 7.21], N=389 over 213 dates, against about 0.7 for ordinary control sessions,
so an earnings session adds about 4.6 ordinary sessions of variance. A stress-test night adds
about 0.5 (total-variance units, held-out), roughly a ninth of an earnings night. In
market-adjusted units the held-out excess is +0.86 and its interval excludes zero: there is real
bank-specific news, but it is small.

Two further facts from the per-night table (`stage_a_rows.csv`). The CCAR-era capital nights
(2015-2019) carried the discovery effect (2015-03-11: 3.2% median absolute move, z^2 5.7); in
the buffer era, where capital plans are no longer approved or objected to, that effect is gone
(+0.25). And the largest held-out nights coincide with market-wide moves: 25 June 2020 (banks
-6.2% mean against SPY -2.4% the same session; the Fed capped dividends) and 23 June 2022
(banks +4.5%, SPY +3.2%; both from the cached closes). SPY itself shows +0.42 [-0.09, +1.02] excess on the same nights.
Brexit night (23 June 2016) was excluded beforehand; kept, discovery jumps to +3.62
[+0.34, +9.05], which shows how one macro night can manufacture an event effect.

Secondary names (TFC, SCHW, AXP, NTRS, FITB, KEY, RF, HBAN, MTB): +0.71 [-0.07, +1.66]
discovery, +0.04 [-0.46, +0.65] held-out.

## What this implies for a seller (arithmetic, not a test)

A straddle's value scales with the square root of the variance to expiry. On a front contract
with N ordinary sessions left, an event adding e sessions of variance is worth about
e / (2N) of the premium. With e = 0.5 and the shortest contract DoltHub offers (N about 10 to
15), the whole event is worth 1.7% to 2.5% of premium. If the market charged twice the realised
event variance, the seller's edge would be that same 1.7% to 2.5%. On a weekly expiring two
days after the night (N about 2, not in the free data) it would be about 12%, which is the only
construction where the arithmetic leaves room, and it rests on the market overpricing a night it
has had twelve years to calibrate.

## Stage B: do bank options price and crush the night? (trials 2476, 2477, 2479, 2480)

DoltHub end-of-day chains, 2020-2026 (no bank coverage before 2020), the same ten banks. A check
against unadjusted closes shows the end-of-day snapshot is struck at the close, before the 16:30
release (95% of 40 snapshots sit nearer the same-day close; 12 of 12 where the next session moved
more than 2%; diagnosis.log entry 5), so entering on the results-day snapshot is not look-ahead.
Trade: short ATM straddle sold at the bid on the last snapshot on or before the results day,
bought at the ask on the first snapshot after the capital-action night (two to six sessions).
Controls: the same name and construction 28 and 35 days earlier. Discovery 2020-2022 (four
cycles including December 2020), held-out 2023-2026, frozen by `freeze_stage_b.md` (SHA-256 in
`freeze_stage_b.sha256`, scorer hash recorded) and read once.

Round 1 required the traded expiry to end before the bank's July earnings. DoltHub lists about
three expiries and the nearest in late June is usually July earnings week, so 28 of 40 discovery
windows dropped and 2021-2022 vanished entirely (N=9, two clusters; uninformative). Round 2 drops
the earnings rule on both legs; the event contracts then span earnings, which biases the event
leg against the seller if implied vol runs up into earnings, so a fail is partly mechanical and a
pass would have been conservative.

| Trial | Block | N (cycles) | Measure | Value | 95% CI |
|---|---|---|---|---|---|
| 2479 | discovery 2020-22 | 39 (4) | event minus control, net at touch, share of m0 | +0.021 | [-0.024, +0.101] |
| | | | event level, net at touch | -0.009 | [-0.041, +0.029] |
| 2480 | discovery | 39 (4) | IV change, event minus control, vol points | -0.92 | [-5.72, +1.59] |
| 2479 | held-out 2023-26 | 40 (4) | event minus control, net at touch, share of m0 | -0.000 | [-0.025, +0.024] |
| | | | event level, net at touch | -0.027 | [-0.043, -0.016] |
| | | | event level, gross at mid | -0.005 | [-0.024, +0.010] |
| 2480 | held-out | 40 (4) | IV change, event minus control, vol points | +0.56 | [-0.80, +1.92] |

Basis: per trade, m0 = 0.20 x forward + entry bid (project convention), end-of-day quotes. Entry
half-spread at the end of day: 5.1% of the mid premium (held-out), the same on events and
controls. Held-out attrition: none (40 of 40 priced). The discovery pair's positive point comes
from 2020 alone, a quiet event window set against controls in the volatile weeks of May 2020;
every later discovery cycle is negative. On held-out, even where DoltHub offered a contract about
17 days out (2024, 2026), the event IV did not fall relative to controls. The book loses about
the spread at the touch and nothing at the mid, which is what a night worth half an ordinary
session should produce. Four clusters make every interval wide; the conclusion rests on the
agreement of stage A's mechanism, the absent crush, and the cost arithmetic, not on any single
interval.

What the free data cannot show: a weekly expiring one or two sessions after the results night,
the only contract where a half-session event is a visible share of premium. If the market
overpriced the night by a factor of two, the edge there would be about 12% of premium by the
arithmetic above; nothing in stage A or B suggests it does (FHK's IV changes go both ways).

## Tradability at Interactive Brokers

The vehicle is the one the project already trades: US-listed equity options on large bank
holding companies (OPRA, American style, physically settled; weekly expiries on the large names, recalled and
not checked per name), plus the bank ETFs (KBE, KRE, XLF) if a sector-level version were wanted. The event lands
after the 16:00 option close, so the entry is the 15:59 cross on the results day and the exit is
the next session, the same timing as the project's after-close earnings book. Requirements are
those already documented for the paper book (project docs, not re-read at IB because IB's pricing
page returned 403 to this client): OPRA top-of-book on the linked live account at USD 1.50 a
month, without which paper quotes are about fifteen minutes late and fills are not evidence;
commission USD 0.65 per contract, four fills per straddle round trip; Reg-T margin for a short
straddle. Nothing in the live harness would need to change. Label: recalled from project docs.

## Data route and cost

- Free and used: DoltHub public SQL API (`dolthub/options` to late 2024, `post-no-preference/
  options` to 2026; identical rows where both exist, checked on JPM 2024-06-26). End-of-day bid
  and ask, about three snapshots a week before 2025, near daily after; three expiries within 75
  days, the nearest typically two to three weeks out; no bank coverage before 2020 (JPM probed on
  seven 2019 dates). End-of-day quotes are a tradeable level only approximately: they are not the
  15:59 consolidated quote the project marks on.
- Free and used: cached adjusted closes for the price-only stage, 2012-2026.
- Paid, not pulled: Databento OPRA `cbbo-1m` for the weekly expiring just after the event, at
  15:59 on the results day and at 15:59 (or 10:00) the next session. The project's logged cost
  for a narrowed request (two contracts, thirty minutes) is about USD 0.04 per event; ten banks,
  twelve cycles, two nights each, with two matched controls per event, is about 720 two-contract
  windows of two snapshots each, so roughly USD 30 to 60 by analogy. That is an estimate from the project's own spend
  log, not the vendor's cost call, which must be run before any pull. On the evidence below I do
  not recommend it.

## PDUFA dates on liquid names

Not piloted; the reasoning was recorded in `diagnosis.log` entry 4 before any PDUFA option price
was read.

- Calendar. The FDA does not publish goal dates; sponsors do, in press releases. The free
  structured sources found are realised decision dates, not scheduled ones: openFDA's complete
  response letters (458 letters, 2002-2026, 309 later approved and 149 not; verified at
  api.fda.gov/transparency/crl.json) and Drugs@FDA approvals. Entering on a realised decision date
  is look-ahead whenever the decision came early, and the published CRL set is a subset, so the
  outcome mix is not the population. BiopharmCatalyst's historical catalyst calendar, the obvious
  scheduled-date source, sits behind its premium tools (recalled; not accessed).
- Universe. Since 2020 the CRLs on sponsors DoltHub carries fall on diversified large caps (Eli
  Lilly 5, Regeneron 5, AbbVie 3, Gilead 2). For these, lane H found the traded contract's implied
  vol barely moves through FDA committee meetings and the realised-to-implied move ratio is the
  same as on control weeks (0.49 against 0.55). The jump lives in small and mid-cap sponsors that
  DoltHub does not carry: lane H's off-DoltHub committee events moved 28% on average against 3.1%
  on DoltHub names.
- Direction. Lane H's evidence is that the binary jump on material names is under-priced (term
  structure priced about 5.3%, realised 11.2%), which favours a buyer, not the project's seller.
- Prior work: event studies of stock reactions to FDA decisions exist (for example Sarkar and de
  Jong 2006; Rothenstein et al. 2011, recalled); I could not verify an options-premium study around
  PDUFA dates before the search budget ran out.
- What a real test needs: a scheduled-date calendar for 2016-2026 (a hand-built list from sponsor
  press releases, or a paid calendar) and intraday option quotes on small and mid-cap biotech
  (Databento OPRA, metered). It would test the buyer's side, which is a different book from the
  project's.

## Verdict

Stress-test results and capital-action nights: not viable. The news is real but small: about
half an ordinary session of extra variance for the largest banks in the 2020-2026 buffer era
(+0.51 [-0.03, +1.16], N=150 bank-nights, 15 nights), against about 4.6 for the same banks'
earnings. The CCAR-era capital-plan effect (+1.83 [+0.76, +3.58], 2015-2019) is gone now that
plans are no longer objected to. Bank options show no crush over the window and the short
straddle loses about the spread at the touch (held-out -0.027 of m0 [-0.043, -0.016], N=40). No
metered pull is recommended.

PDUFA dates on liquid names: not viable at zero cost and probably on the wrong side for this
project: no free scheduled-date calendar, the liquid (DoltHub) sponsors are diversified pharma
where lane H found no premium, and the material jumps sit in small caps where the evidence points
to under-pricing, a buyer's trade.

Kill criterion, if anyone reopens the stress-test idea with intraday data: on the weekly expiring
within two sessions of the results night, implied event variance (from the weekly and the next
expiry at the 15:59 cross) must exceed realised event variance by more than the round-trip
half-spread in variance terms on a pre-registered block; below that, stop.

Forward paper test, if wanted at no cost: on the 2027 results date (pre-announced by the Fed
about two weeks ahead), record at the 15:59 cross on the results day and the next session the
bid, ask and mid of the shortest-dated ATM straddle on the ten names with the OPRA subscription
active, without trading. One cycle gives ten correlated observations, so it informs the cost side
(half-spread on a two-day weekly) rather than the premium.

## Could not verify

- The 2020 bank disclosure night (29 June) and the 2026 one (26 June, inferred from "typically
  two business days").
- The 16:30 release time for 2013-2014 (pages carry no time); these years are excluded.
- Whether any study measures an option P&L around US stress tests or PDUFA dates: the session's
  web-search budget ran out mid-lane, so the absence is not established.
- IB's commission and market-data pages (403 to this client); figures are from project docs.
- Weekly listings per name, and the Databento cost, which must come from the vendor's cost call.
- Fernandes, Igan and Pinheiro (2020) beyond their conference slides.

## Files

Pre-registration and log: `diagnosis.log`. Trials: `trials.csv` (2472-2480; 2481-2501 unused).
Stage A: `stage_a_moves.py`, `stage_a_adjusted.py`, `stage_a_results.csv`, `stage_a_rows.csv`,
`stage_a_adjusted_rows.csv`, `stage_a_earnings_calibration.csv`. Stage B: `dolt.py`,
`stage_b_options.py`, `snapshot_timing.py`, `freeze_stage_b.md`, `score_discovery_r1.log`,
`score_discovery_r2.log`, `score_heldout.log`, `stage_b_scored_*.csv`. Calendar and participants:
`stress_calendar.csv`, `participants.py`, `participants.csv`. Raw Fed pages, results PDFs and
papers: `raw/` (about 40 MB; rebuild by re-downloading the URLs in `sources.csv`). Option chains:
`chains/` (DoltHub public data; rebuild with `stage_b_options.py --fetch`, about 40 minutes at
one request a second).

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N14-bank-stress-tests-and-regulatory\evidence.md
