# N15: options on ADRs and foreign issuers reporting outside US hours

Evidence dossier for the analyst. Labels: [V] verified at the source, [R] recalled, [C]
conjecture. Pilot figures are real OPRA `cbbo-1m` 15:59 ET quotes from the project cache; every
one is per event, net at the touch unless stated, on m0 = 0.20 x forward + straddle bid, with
date-clustered 95% intervals (`protocol.date_clustered_ci`). The decision trail is
`diagnosis.log`; scored configurations are in `trials.csv` (trials 2,502 to 2,504).

## 0. Result in one paragraph

On the only US-listed foreign issuers the project holds quotes for (34 names, 2025-01 to
2026-05: Canadian cross-listings, foreign issuers listed only in the US, and five with a European
home venue), the short event straddle loses at the touch as US reporters do, and the touch is
wider. Frozen configuration, held-out 2026: foreign mean -7.26% of m0 [-10.68, -3.71], N=38 on
24 dates, against week- and tenor-matched US reporters -5.97% [-9.23, -3.56]; difference -1.29
points [-5.79, +3.18]. The matched entry half-spread is 3.6 points of premium wider [+0.6, +6.4].
The lane's core case, liquid ADRs whose home market prices the news before the US open (TSM,
ASML, SAP, NVO, BABA, TM and peers), is not in any free or cached source; a Databento pull for it
is cheap (section 5), but the evidence above gives no reason to expect it to pass.

## 1. Prior work

- **Closest paper on the event itself:** Bailey, Karolyi and Salva (2006), JFE 81(1) 175-213.
  387 non-US firms, 1989-2001: absolute return and volume reactions to earnings rise after a US
  cross-listing, most for developed-market firms and OTC or private-placement listings, and the
  authors attribute it to disclosure rather than liquidity or venue [V, abstract]. It studies
  stock reactions, not options, and measures no trading costs.
- **Option-market event premium (US names):** Dubinsky, Johannes, Kaeck and Seeger (RFS 2019)
  find implied earnings-day jump volatility above realised [V, conference slides; paper R]. The
  project's own work reproduces the premium at the mid and its loss at the touch.
- **ADR timing:** Leung and Kang (2016, arXiv 1611.03110) model the Asian ADR minus SPY spread
  as mean-reverting and backtest pairs trades; the abstract gives no costs [V]. A working paper
  argues that pre-open home-market trading improves the ADR's US opening price [R, search
  summary]. Overnight jumps carry about a quarter of jump risk in option prices (JFQA 2007) [R].
- **Options on ADRs around earnings:** four targeted searches found no peer-reviewed study [C:
  absence of evidence; the session's search budget ran out before SSRN-specific queries]. The
  idea is not crowded in print. Desks quote TSM and BABA event straddles routinely [R], so the
  liquid end is not neglected in practice.

## 2. Mechanism and timing

- Who releases when. European issuers publish before their home open (Deutsche Bank released
  Q1 2025 on 2025-04-29 with an 11:00 CEST call, so before 05:00 ET [V]; Xetra opens 03:00 ET
  [R]). Their home venue prices the news for hours before US options open. Asian issuers mostly
  publish after their home close and before the US open [R], so the US ADR is the first venue to
  trade it, like a US pre-market reporter. Canadian issuers publish in the same time zone, around
  06:00 to 07:00 ET for the banks [R], with the TSX on NYSE hours.
- For the US option seller every case reduces to the same bracket as a US pre-market report:
  sell at the prior US close, the news arrives while US options are shut, buy back on the
  reaction session. The home-venue variant only changes how digested the price is at 09:30 ET.
  That could matter for an early exit (the stock reopens on a settled price), but the cache holds
  only 15:59 marks, so this lane cannot test it.
- Why a premium might differ: thinner US option supply on foreign names could raise both the
  premium and the spread [C]. The pilot finds the spread effect and no premium effect.

## 3. Tradability at IB

US-listed options on ADRs and foreign issuers are ordinary OPRA equity options: same exchanges,
09:30 to 16:00 ET, 100-share multiplier, Reg-T margin, weeklies on the liquid names and monthlies
only on many others (in the cache, CAN and several FUS names list monthlies only, so the front
contract sits 14 to 24 days past the event). IB route, as verified by lane N20 from IB's pages
(IB's commission page returned HTTP 403 to this lane): USD 0.65 per contract at or below 10,000
a month; OPRA L1 USD 1.50 a month, waived above USD 20 of commissions; delayed OPRA quotes are 15
minutes late. This is the existing harness path; only the universe and the calendar change. ADRs
carry a depositary fee of a few cents per share charged to holders [R], which matters only if a
short straddle is assigned into stock.

## 4. Data, and how the project's calendar treats these names

| Source | ADRs? | Foreign issuers? | Notes |
|---|---|---|---|
| WRDS-built calendars and events, 2013-2024 | no | no | `wrds_panel.py:63` keeps CRSP share codes 10 and 11 only [V] |
| `outputs/research/2026-11-02-hedged-event-hold/` event files | no | only US-schedule redomiciled names (ACN, MDT, ETN, LIN, ...) | built on the WRDS universe |
| `data/cache/backfill_chains`, 2025-01 to 2026-05 | no | 34 names, about 10 sessions each | pulled by the 2025-26 broad backfill, used by no event file until now [V] |
| `data/cache/flow`, `entry_1545_chains` | no | NXPI only | |
| `postea_quotes` (closed study) | BILI, TME, YUMC and a few | about 30 foreign names | 42-day straddle after the event, not an event bracket |
| DoltHub `dolthub/options` (free) | none of 25 ADRs tested | none of TD, RY, SHOP | AAPL present on the same dates; samples Monday, Wednesday, Friday only [V] |
| `api.nasdaq.com` calendar | | | robots.txt disallows all agents; historical rows say `time-not-supplied` [V] |

The calendar defect. The 2025-26 chains were pulled through Finnhub's `hour` field
(`chains.py:94-128` [V]). On the entry chain, 13 of 61 Canadian events in 2025 (21%) and 3 of 32
in 2026 (9%) carry no event variance at all (two-expiry split jump variance at or below zero),
against 1.2% and 2.4% of US events; no overseas or US-only foreign event shows it. The flat
events are the large Canadian banks, BCE, CVE and similar (BMO 2025-05-28, BNS 2025-05-27, CM
2025-12-04, BNS 2026-02-24, ...). The pattern fits pre-market Canadian releases stamped as
after-close, so the pair enters on the announcement day's close, after the news [diagnostic V,
cause C]. Any forward book that adds foreign names needs the two-of-three calendar vote plus this
entry-only check.

## 5. The pilot

Design (pre-registered in `diagnosis.log` [2] before any outcome): every pair of consecutive NYSE
sessions with a cached chain on both; front ATM straddle (first expiry on or after the reaction
session, strike nearest the parity forward) sold at the D1 15:59 bid and bought back at the D2
15:59 ask, USD 0.65 a leg. Groups fixed from domicile and listing: OVS (DB, ALC, FER, CCEP, FLUT),
FUS (CHKP, CYBR, GRAB, CPNG, ICLR, AER, NXPI, FERG, CRH), CAN (20 names), F = all three. Control:
US events in the same ISO week and tenor bucket. Discovery 2025, held-out 2026, read once after
`freeze_N15.md` (self-hash and scorer hashes verified by `score_heldout.py`).

| Trial | Block | Foreign mean B | Minus matched US | N (dates) | Null pct |
|---|---|---|---|---|---|
| 2,502 no bracket filter | 2025 | -3.76% [-5.96, -1.73] | -1.07 [-3.41, +1.17] | 87 (60) | 19 |
| 2,503 entry-only bracket filter | 2025 | -2.82% [-5.06, -0.74] | -0.16 [-2.75, +2.16] | 73 (51) | 46 |
| 2,504 as 2,503, unquoted exit legs restored | 2025 | -3.60% [-5.62, -1.65] | +0.62 [-1.76, +3.03] | 92 (59) | 67 |
| 2,503 frozen | 2026 | -7.26% [-10.68, -3.71] | -1.29 [-5.79, +3.18] | 38 (24) | 27 |
| 2,504 robustness | 2026 | -9.31% [-13.19, -4.86] | -3.06 [-7.65, +2.23] | 48 (27) | 7 |

Per-trade Sharpe of the frozen foreign book: -0.31 (2025), -0.56 (2026), per event, not
annualised. Both pass rules fail in every row.

Where the money goes (trial 2,503 configuration, medians unless stated):

| | Half-spread share of premium | Crush, vol points (mid, not tradeable) | Mean B at the mid, of m0 (not tradeable) |
|---|---|---|---|
| F 2025 | 9.4% [7.4, 10.8] | 7.1 [4.7, 9.6] | +3.31% [+1.70, +4.93] |
| US 2025 | 5.3% [4.8, 5.7] | 14.8 [13.4, 16.9] | +3.86% [+3.12, +4.54] |
| F 2026 | 11.0% | 6.3 | -0.18% [-4.24, +3.94] |
| US 2026 | 7.7% | 13.1 | +2.40% [+1.59, +3.23] |

The mid premium on foreign names is no larger than on US names, and the round trip costs about
6.1 points of m0 against 5.8 for US names (2025, mean at the mid minus mean at the touch). The crush is
smaller because the front contract is often a monthly far past the event and because Canadian
names carry little event variance (CAN median 2.5 vol points in 2025). Subgroups are exploratory:
FUS mean B -1.33% [-4.97, +1.78] (N=30, 2025) and -7.46% [-16.53, +0.94] (N=12, 2026); OVS
-2.97% [-8.43, +2.40] (N=12) and +1.0% [-7.9, +8.7] (N=4), too few to read.

Attrition. A missing 15:59 record on an exit leg drops 18% of foreign and 15% of US events in
2025. Dropped events have lower entry implied moves (F 5.45% against 6.44%), so the drop does
not select on rich premium, but the missing legs are far out-of-the-money legs on expiry day after
a move. Restoring them at intrinsic plus a tick (trial 2,504) lowers the US book from -1.93% to
-3.42% of m0: the drop rule flatters both books by about 1.5 points, and the comparison is
unchanged.

## 6. The metered pull for true ADRs, priced

The open question this lane cannot close for free is the liquid ADR set with weeklies, where the
spread may be as tight as US megacaps. Pull: Databento OPRA `cbbo-1m`, the 15:59 minute on the
entry and exit sessions, parent symbol, about 40 ADRs (TSM, ASML, SAP, NVO, BABA, PDD, JD, BIDU,
TM, SONY, AZN, NVS, SHEL, BP, HSBC, UBS, ARM, SHOP, TD, RY and peers), 2013-04 to 2026, about 3.5
reports a year (several Europeans report half-yearly): about 1,900 events and 3,850 chains.
Price: the project's history pull cost USD 20.87 for the chains of 7,773 events, about USD 0.0013
a chain [V, `ml_zoo.md`]; ADR chains are larger, and at the ledger rate of USD 2.14 per million
rows (lane N19 [V]) with 1,000 to 4,000 rows a chain the pull is USD 8 to 33. Estimate USD 5 to
35; hard cap USD 40; price it first with the free `metadata.get_cost` call. The binding cost is
not money but the calendar: ADR announcement dates with release times are not in the WRDS mirror
(a new IBES slice needs a WRDS login), and the free routes are company IR pages or the two-of-three
vote with the entry-only bracket check above.

## 7. Verdict, kill criterion and forward test

Not viable on the evidence in hand: the foreign book has no net premium at the touch in either
block and its touch is wider, not cheaper. A priced pull for liquid ADRs is possible at under USD
40 but is not recommended on its own merits; it would earn its place only bundled with a wider
universe pull for another purpose. Kill criterion for that pull, if run: the ADR group's
discovery mean B at the touch has its 95% upper bound below zero, or its matched half-spread
share is not below the US control's. A forward paper test would add the liquid weekly ADRs to the
existing harness under the two-of-three calendar vote and the entry-only bracket check, score the
same B per event against same-week US reporters. With the 2025 dispersion (standard deviation
about 9% of m0 per event) an interval of plus or minus three points needs about 35 events before
clustering and about 50 after, which 40 ADRs supply in roughly one reporting season.

## Rebuilding the caches

`cache/events_<year>.parquet` and `cache/bracket_<year>.parquet` hold per-event figures derived
from licensed OPRA quotes; keep them inside the team. Rebuild with
`scripts/build_events.py --year Y` then `scripts/bracket_check.py --year Y` (no network, reads
`data/cache/backfill_chains`).

## Not verified

Release times other than Deutsche Bank's; the Canadian banks' release dates behind the flagged
events; IB's commission page (403); whether CRH and FERG retain a non-US listing; the OVS group's
behaviour beyond 16 events; any figure for true ADRs.

C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N15-adr-overnight-reporters\evidence.md
