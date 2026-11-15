# N19 data access: evidence dossier

Lane question: which of the hunt's tests can be run on data the team can obtain, at what
granularity, and what the paid alternatives cost for the pulls lanes N01 to N13 need.
Compiled 2026-11-13. Labels: **verified** (read at the source or measured on disk today),
**recalled** (prior knowledge, not re-read today), **conjecture** (my estimate). Every claim is
also a row in `sources.csv`. No vendor API was called; no login-walled page was opened.

Note on method: the session's shared web-search budget ran out part way through this lane, so
later checks used direct fetches of known URLs only. Claims that a search would normally have
confirmed are labelled recalled.

## 1. Headline for other lanes

1. **No free source anywhere gives historical bid/ask on futures options** (CME, CBOT, NYMEX,
   COMEX, ICE). Free futures-option history is at best settlement prices, and the CME's own site
   forbids and actively blocks automated access (verified: HTTP 403 on 2026-11-13 with a message
   citing CME's Data Terms of Use). Lanes N01 to N07, N12 (futures leg) and N13 cannot measure
   the touch historically at zero cost. Settlement-to-settlement results are not tradeable
   levels (BRIEF standard).
2. **US-listed ETF and index options (OPRA) are cheap, not free.** The project already runs a
   capped Databento OPRA `cbbo-1m` pipeline (`scripts/build/pull_index_chains.py`). Its own
   ledger gives an empirical cost of $0.000698 per one-minute snapshot of a +/-5%, up-to-10-day
   strip (mean over N=15,848 billed requests; SPY's mean $0.000978). A full 2016-2026 daily
   panel at two snapshots a day costs about $4 to $5 per underlying (section 5). That unlocks the
   touch for N09 (VIX options), N12 (GLD, SLV), N16 (country ETFs), N17 (USO, UNG, GLD, SLV,
   TLT) and N10 (IBIT), but it is a spend and needs the team lead's go-ahead.
3. **The cheapest adequate route for every CME lane is one month of Databento's Standard plan,
   $199** (verified, databento.com/pricing): 16+ years of L0 data (OHLCV bars, instrument
   definitions, statistics including the settlement price) and the last 12 months of L1 quotes
   (BBO, CBBO, MBP-1, trades) for CME, CBOT, NYMEX and COMEX. Twelve months of quotes give N of
   about 50 for the weekly reports (EIA storage, EIA petroleum) but only 8 to 16 for monthly or
   FOMC events; older quotes are pay-as-you-go at a per-GB rate no public page prints. The
   volume needed is tiny (10 to 60 MB per lane for ten years of event snapshots), so the bill is
   the plan, not the bytes.
4. **Zero-cost, in hand today:** N08 (SPY/QQQ/IWM 15:59 and 10:00 quote snapshots, 2016-2026),
   the macro release calendar, Deribit trades around macro events, Kalshi markets, ForecastEx
   daily summaries (N11's pull), free Cboe implied-volatility index histories, Cboe VX futures
   settlements, and EIA futures settlements.

## 2. What is already on disk (`data/cache`, `data/processed`)

Inventory taken by listing files and reading Parquet schemas only; no vendor rows printed.

| Path | What it is (verified from file names and schemas) | Coverage | Granularity | Lanes served |
|---|---|---|---|---|
| `cache/index_chains` | Databento OPRA `cbbo-1m` snapshots, SPY, QQQ, IWM; columns `ts_recv, symbol, bid_px_00, ask_px_00, bid_sz_00, ask_sz_00` | 2016-01-04 to 2026-10-30, 2,724 sessions per ticker, 15:59 and 10:00 ET; strikes within +/-5%, expiries within 10 calendar days; 5,173,116 rows in 16,344 files | two-sided NBBO with size, one minute | N08 directly; equity-index reaction leg for N05, N06, N11, N12 |
| `cache/index_chains/_cost_ledger.csv` | one row per billed request | N=15,848, total $11.07 | cost per request | empirical OPRA rate for all OPRA pricing below |
| `cache/index_events` | `macro_releases_2016_2026.csv` (344 dates: NFP 129, CPI 129, FOMC 86), FRED release dates, megacap earnings calendars | 2016-2026 | dates | N05 to N09, N11, N12 |
| `cache/spy_macro` | DoltHub SPY end-of-day chains (expiry, strike, bid, ask, iv, OI) | 2019 onward, sparse, rotating expiries | EOD | closed test (N=5); not a route |
| `cache/deribit` | `history.deribit.com` option trades in windows around macro releases (234 files; fields include `iv, mark_price, index_price, direction, amount`), BTC delivery prices, release list | 2023-01 to 2026-10 | trade-level, no quotes | N10 (macro windows only; closed for macro, so N10 needs new crypto-native windows, free from the same API) |
| `cache/kalshi`, `cache/kalshi_rep` | Kalshi market JSONs (CPI, core CPI, claims and others), 6,503 files | 2022 onward | market snapshots | N11 comparator |
| `cache/dolthub_*`, `processed/dolthub_*` | DoltHub `option_chain` for US single names and SPY; N17's probe found no USO, UNG, GLD, SLV or TLT | 2019 onward, sparse | EOD | not a route for N01 to N13 |
| `processed/databento`, `databento_quotes`, `cache/flow`, `fills*`, `entry_1545_chains`, `backfill_chains`, `postea_*` | OPRA single-name chains, quotes and MBP-1 flow around earnings | 2013 onward | daily bars, one-minute quotes, tick | N14, N15 only |
| `processed/lse_raw`, `lse_1m` | one-minute option OHLC for 48 US single names | various | trade bars | N14, N15 only |
| `processed/nse_fo`, `b3_cotahist` | NSE F&O bhavcopy (474 zips), B3 COTAHIST (360 zips) | 2024 onward | EOD settlement | closed (India, Brazil) |
| `processed/wrds` | R2 mirror of WRDS calendar and CRSP spot | | | holds no options (CLAUDE.local.md) |

**Gap, verified:** no file, module or document in the repository references a CME (`GLBX`) or
ICE (`IFUS`, `IFEU`) dataset; the only hit for those strings is a sentence in
`research/off_earnings/findings/spy_macro.md`. Nothing on disk covers futures options at any
granularity.

How the project loads data today (read only): `earnings_iv_crush/data/providers.py` routes chain
sources; `databento_options.py` pulls OPRA `ohlcv-1d` with explicit symbols and inverts IV
locally (its docstring records that `cbbo-1m` covers 2013-04-01 onward and cost $0.0124 per
event against $0.0590 for daily bars); `databento_quotes.py` marks off `cbbo-1m`; every builder
prices with the free `metadata.get_cost`, reserves against `--cap`, and logs to a ledger. A CME
pull would reuse that pattern with `dataset="GLBX.MDP3"` and CME raw symbols; nothing in the
package handles futures-option symbology, multipliers or the futures underlying yet.

## 3. Free and public sources

| Source | Covers | Granularity | History | Terms | How to get it | Label |
|---|---|---|---|---|---|---|
| Cboe index histories (`cdn.cboe.com/api/global/us_indices/daily_prices/{SYM}_History.csv`) | VIX, VIX9D, VIX1D, OVX (USO), GVZ (GLD), VXSLV, VXTLT and others | daily OHLC of the index, a 30-day (9-day, 1-day) constant-maturity implied vol at the mid | VIX9D from 2011-01-04, VIX1D from 2022-05-13, OVX and GVZ from 2009-09-18 (fetched today) | cboe.com/terms s.2: one copy for personal non-commercial use | plain GET | verified |
| Cboe CFE VX futures per-contract CSV (`cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{expiry}.csv`) | VIX futures | daily open, high, low, close, settle, volume, EFP, OI; no bid/ask | each contract from listing | as above | plain GET (fetched VX 2026-12-16) | verified |
| Cboe delayed quotes JSON (`cdn-api.cboe.com/api/global/delayed_quotes/options/_{SYM}.json`) | any Cboe-quoted OPRA root: VIX, SPX, ETFs | current chain: bid, ask, sizes, IV, greeks, OI, about 15 minutes late | snapshot only, no history | s.2 allows one personal copy; storing in an electronic retrieval system needs Cboe's written consent, so a standing collector is a grey area | plain GET; today 1,540 VIX series, 1,443 two-sided, median absolute spread $0.13 (about 14:20 ET) | verified |
| Deribit public API (`history.deribit.com/api/v2/public/...`) | BTC and ETH options trades including expired | trade-level with `iv, mark_price, index_price, direction`; current book only, no historical quotes | 2016 onward for trades (recalled) | public, no key | plain GET; project cache already uses it | verified (fields), recalled (start) |
| Tardis.dev free CSV (`datasets.tardis.dev/v1/deribit/options_chain/YYYY/MM/01/OPTIONS.csv.gz`) | full Deribit option chain quotes on the first day of each month | every quote update, bid/ask/IV | Deribit from 2019-03-30, quote channel from 2019-10-01 | research use allowed, no redistribution | free without key, but metered: today's request returned 429 "This account has reached its data transfer limit", retry after 86,257 s | verified (docs and the 429) |
| ForecastEx public daily summaries (`forecastex-public-data` S3 bucket, linked from forecastex.com/data) | all ForecastEx contracts | daily summary rows | 2025-01-01 onward, 681 files (N11's fetch log) | public bucket | N11's `fetch_forecastex.py` | verified (via N11 log) |
| EIA daily futures prices (`RNGC1d.xls` to `RNGC4d.xls`, `RCLC1d.xls`) | NYMEX natural gas and WTI futures, first to fourth contract | daily settlement | decades | US government, public | plain download (N03, N04 hold copies) | verified (via N03, N04 files) |
| Kalshi public API | Kalshi event markets | market and trade history | 2021 onward | public | project cache | verified (cache) |
| CME settlements web pages | all CME products incl. options | settlement only | recent days only (recalled), free to view after midnight CT (CME FAQ, search snippet) | automated access prohibited by CME's Data Terms of Use; this lane's plain GET was refused with 403 citing those terms | none for research automation | verified (403 and message) |
| CME QuikStrike (settlement-vol tools) | CME options settlement vols | settlement | some history | free account login | login-walled, outside this hunt's limits; a person can view | recalled |
| MRCI and similar settlement mirrors | CME settlements | EOD | long | MRCI moved prices behind subscription because CME now licenses delayed and EOD redistribution | none free | verified (search snippet of MRCI page) |
| ICE Report Center | ICE futures and options EOD reports | settlement, volume, OI | historical packages | EOD CSV packages are a paid annual subscription; historical packages are a one-off purchase; fee PDF not reachable (404) | purchase | verified (pages), price unknown |
| Barchart futures-option pages | current chains | delayed quotes | current only; history is a paid product | terms not retrieved (empty fetch); recalled to prohibit scraping | not a route | recalled |
| Nasdaq Data Link | OptionWorks futures-option vol surfaces (OWF) are premium | settlement-derived surfaces | 2000s onward | robots.txt disallows crawler access to API data paths | paid | recalled (OWF), verified (robots) |
| Yahoo Finance chains | US-listed options | current snapshot | none | unofficial endpoint | other lanes use it for daily ETF OHLC | recalled |
| Interactive Brokers API | all IB products | quotes and bars | **no historical data for expired options or futures options**; expired futures only up to two years after expiry | account and real-time subscription | forward collection only (N20's lane) | verified (TWS API docs) |

Conclusion for free sources: the free world gives (a) mid-level implied vol through vol indices
and settlements, (b) the touch for Cboe-quoted options going forward from today, and (c)
Deribit trades with Deribit's own mark. It gives no historical touch for any futures option.

## 4. Paid sources and their public prices

| Vendor and product | Coverage | Granularity | Public price | Label |
|---|---|---|---|---|
| Databento GLBX.MDP3 | CME, CBOT, NYMEX, COMEX futures and options from June 2010; before 2017 sourced from MDP 2 with no MBO, CMBP-1 or CBBO schemas; statistics include settlement | L0: OHLCV, definitions, statistics; L1: BBO-1s/1m, MBP-1, TBBO, trades; L2/L3 | Usage-based: per-GB rate not printed on any page fetched ("from $0.50/GB" headline). **Standard $199/month**, monthly billing, no licence fees: 16+ years L0, last 12 months L1, last month L2/L3, older history pay-as-you-go. Plus $1,750/month, annual (16+ years L1). Unlimited $4,500/month, annual (all schemas, 16+ years). $125 free credit for new teams, one set per team, expires after 6 months | verified (pricing page, dataset docs) |
| Databento IFUS.IMPACT (ICE Futures US: coffee, cocoa, sugar, cotton, canola, OJ, MSCI, USDX) | from 2018-12-23 | options normalised as MBP-10 only (no BBO-1m); statistics with settlement | $10.00/GB usage-based; included with any subscription (wording of the launch post) | verified (blog 2025-06-18, docs) |
| Databento IFEU.IMPACT (ICE Futures Europe incl. Brent) | from 2018-12-23 | options MBP-10 only | exchange licence fees from $875/month per feed (live); historical usage rate not printed | verified (blog 2024-01-18) |
| Databento OPRA.PILLAR | all US equity, ETF and index options (VIX and SPX inclusion recalled, not re-verified today) | `cbbo-1m` from 2013-04-01; CMBP-1, TCBBO from 2023-03-28 | empirical $2.14 per million `cbbo-1m` rows from the project ledger, which implies about $27 to $33 per GB at 64 to 80 bytes a record | verified (ledger, project docstring), conjecture (record size) |
| Cboe DataShop Option EOD Summary | OPRA options only (stocks, ETFs, indices); no futures options | NBBO at 15:45 ET and EOD, OHLC, volume, OI | price shown only in a basket builder; academic discount 50% with a $500 minimum | verified (product and academic pages) |
| CME DataMine | all CME venues; BBO top-of-book files 1999 to 2025 in ASCII, CSV from 2025; EOD summaries | top-of-book, EOD | not printed on reachable pages; cmegroup.com blocks automated fetches. A CME FAQ (date uncertain) listed End of Market Summary from $105/month per DCM to $2,100/month. A 12-month prepaid subscription gets two months free | partly verified (search snippets), price recalled/stale |
| iVolatility Data Download | US, Canadian, European, Asian equity, index and futures options (exchanges not named) | EOD NBBO close prices, raw IV; 15:45 snapshots by quote only | $0.40 per ticker per day (option prices), $0.60 (raw IV and surfaces); no minimum; from 2005 | verified (pricing page) |
| historicaloptiondata.com | US equity, ETF, index options only | EOD bid/ask; 15-minute intraday | $230 (1 year) to $2,035 (24 years); intraday $1,815/year | verified |
| OptionMetrics IvyDB Futures (through WRDS) | futures options, settlement-based | EOD | institutional licence; WRDS logins are outside this hunt | recalled |

## 5. Pricing the pulls lanes N01 to N13 need

Script: `scripts/cost_model.py`; output `data/pull_costs.csv`; log `logs/cost_model.log`.

**Design assumed (conjecture, adjustable):** for each event, one-minute quote snapshots at entry
and exit, doubled for a matched non-event control (4 snapshots), on the front two or three
expiries within about +/-10% of the money (80 to 300 series per snapshot by product). Event
counts per year: monthly releases 12, USDA grain report days about 16, EIA weekly about 50, FOMC
8, central-bank meetings 8 per bank. CME `bbo-1m` records taken as 80 bytes (recalled DBN
layout).

**Arithmetic, worked for N01 (grains):** 16 report days a year x 10 years x 3 products = 480
event-products; x 150 series x 4 snapshots = 288,000 records; x 80 bytes = 23.0 MB. At $0.50/GB
that is $0.01; at $10/GB $0.23; at $280/GB (the highest per-GB figure in Databento's own docs,
an example value) $6.45.

| Lane | Venue | Products | Event-products, 10 y | MB | Cost at $0.50 / $10 / $280 per GB |
|---|---|---|---|---|---|
| N01 grains | GLBX | ZC ZS ZW | 480 | 23.0 | $0.01 / $0.23 / $6.45 |
| N02 livestock | GLBX | HE LE GF | 480 | 12.3 | $0.01 / $0.12 / $3.44 |
| N03 natgas | GLBX | NG, LNE weeklies | 500 | 32.0 | $0.02 / $0.32 / $8.96 |
| N04 crude | GLBX | CL, LO weeklies | 540 | 43.2 | $0.02 / $0.43 / $12.10 |
| N05 treasuries | GLBX | ZN ZB ZF ZT | 1,280 | 61.4 | $0.03 / $0.61 / $17.20 |
| N06 SOFR | GLBX | SR3 and mid-curves | 320 | 30.7 | $0.02 / $0.31 / $8.60 |
| N07 FX | GLBX | 6E 6J 6B 6A 6C | 800 | 25.6 | $0.01 / $0.26 / $7.17 |
| N10 crypto (CME) | GLBX | BTC, ETH, 6 years | 240 | 9.2 | $0.00 / $0.09 / $2.58 |
| N12 metals (futures) | GLBX | GC SI HG | 960 | 46.1 | $0.02 / $0.46 / $12.90 |
| N13 softs | IFUS | KC CC SB CT, 7 years | 336 | up to 7,419 | $14.84 to $74.19 at $10/GB (MBP-10, 30-minute windows, 1 to 5 book updates per series per minute, conjecture) |

Instrument definitions (needed to map CME option symbols) are L0, included in the Standard
plan; on pure usage-based billing they could exceed the quote bytes if pulled daily for a whole
product (conjecture: a few thousand series at about 520 bytes each per day), so pull them once
per month per product.

**OPRA lanes (empirical ledger rate, full daily panel 2016-2026 at 15:59 and 10:00):**

| Lane | Underlyings | Snapshots | Cost (ledger mean / SPY-sized worst) |
|---|---|---|---|
| N09 | VIX | 5,448 | $3.81 / $5.33 |
| N12 | GLD SLV | 10,896 | $7.61 / $10.66 |
| N17 | USO UNG GLD SLV TLT | 27,240 | $19.03 / $26.64 |
| N16 | EWZ EWW FXI EWJ EWG INDA EWT | 38,136 | $26.64 / $37.30 |
| N10 | IBIT, from listing (about 490 sessions) | 980 | $0.68 / $0.96 |

An event-only design (entry, exit and a matched control per event) costs a quarter to a tenth
of these. The SPY-sized bound is conservative: smaller ETFs list fewer whole-dollar strikes in a
+/-5% band.

**Reading the table.** Bytes are not the constraint. For CME the cost is the plan ($199 for one
month buys the last 12 months of quotes for every CME lane at once, plus 16 years of
settlements and one-minute trade bars) and an unverified per-GB rate for quotes older than 12
months, which on these designs stays under about $17 per lane even at the highest per-GB figure
found. For OPRA the cost is under $40 per lane. Every one of these is still a spend: under the
BRIEF it makes the lane "viable pending a priced pull", and the binding number is the free
`metadata.get_cost` on the actual symbol list, run by the team lead.

**Alternatives priced for comparison.** iVolatility EOD NBBO for one futures underlying over 10
years is 2,520 ticker-days x $0.40 = $1,008, or 320 event days x $0.40 = $128, and gives only
a close-of-day quote. Databento Unlimited is $4,500 a month on an annual contract
($54,000), unjustified for a pilot. CME DataMine and Cboe DataShop prices could not be read from
a public page.

## 6. Feasibility by lane

| Lane | Zero-cost route | What it can and cannot measure | Cheapest adequate paid route |
|---|---|---|---|
| N01 grains | none for options; settlements not scrapable | premium at the touch: no | Databento Standard, 1 month ($199): 12 months of quotes (about 16 report days) plus 16 years of settlements; older quotes pay-as-you-go ($0.01 to $6.45) |
| N02 livestock | none | no | as N01 (about 16 reports a year across Hogs and Pigs, Cattle on Feed); thin books, so the 12-month window also measures the touch |
| N03 natgas | EIA futures settlements (in N03) | realised report-day move only; no implied leg | Standard $199 (about 50 storage reports in 12 months: adequate N for a pilot) |
| N04 crude | EIA futures settlements, OVX (free) | OVX is a USO-option 30-day vol at the mid: a ceiling test only | Standard $199 for CL/LO weeklies (about 50 WPSR in 12 months); USO via OPRA under $6 |
| N05 treasuries | VXTLT (free), SPY/QQQ/IWM touch in hand | ceiling only on Treasuries | Standard $199 (12 months: 12 CPI, 12 NFP, 8 FOMC) plus older L1 pay-as-you-go up to $17; TLT via OPRA under $6 |
| N06 SOFR | macro calendar in hand | no | Standard $199 plus older L1 for FOMC N (8 a year) |
| N07 FX | none; OTC event vols are terminal-only (recalled) | no | Standard $199 plus older L1 |
| N08 index macro | **in hand**: SPY, QQQ, IWM two-sided quotes at 15:59 and 10:00, 2016-2026 | net at the touch, overnight and intraday FOMC hold | none needed |
| N09 VIX | VIX, VIX9D, VIX1D histories; VX settlements (free) | mid-level and settlement only | VIX options via OPRA, $3.81 to $5.33 for a daily 2016-2026 panel |
| N10 crypto | Deribit API trades with mark and IV (free); Tardis first-of-month quotes (free but metered, exhausted today) | Deribit premium at trade prices; touch only on first-of-month days | IBIT via OPRA about $1; CME BTC options in the Standard plan |
| N11 ForecastEx | ForecastEx daily CSVs (N11 has them); Kalshi cache; SPY touch in hand | yes for ForecastEx against SPY options; SOFR comparator needs GLBX | Standard $199 for the SOFR leg |
| N12 metals | GVZ, VXSLV (free) | ceiling only | GLD and SLV via OPRA $7.61 to $10.66; COMEX in the Standard plan |
| N13 softs | none | no | Databento IFUS at $10/GB, about $15 to $74 for 7 years of windowed MBP-10 (conjecture on book activity) |

## 7. What I could not verify

- Databento's per-GB rates for GLBX.MDP3 and OPRA by schema (not on any public page fetched;
  the catalog loads them dynamically). The free `metadata.get_cost` call is the authority.
- Whether the Standard plan also covers IFUS (the IFUS launch post says "included with any
  subscription"; the pricing page lists only CME venues under Standard).
- Whether GLBX `bbo-1m` exists for pre-2017 (MDP 2) dates; the docs exclude MBO, CMBP-1 and
  CBBO, and say nothing explicit about BBO-1m.
- CME DataMine and Cboe DataShop list prices (basket builders; cmegroup.com refuses automated
  fetches).
- That OPRA.PILLAR includes VIX options (recalled; VIX options are Cboe-listed and OPRA
  disseminated).
- The Tardis free sample's contents (the free tier's transfer limit was already exhausted).
- Barchart's terms of use text (fetch returned empty).
