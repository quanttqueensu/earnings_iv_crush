# Data catalogue

One row per dataset held on disk: what it is, where it came from, what it cost to obtain, what
builds and reads it, and whether a teammate receives it through `sync pull`. `docs/DATA.md`
describes the sources and the licence rule; this file describes the holdings.

Measured on 2026-11-01 from the working tree by walking every file under `data/` and
`outputs/research/` and reading one parquet footer per dataset. Ticker counts and date spans come
from file names (`{TICKER}_{YYYY-MM-DD}.parquet`), so they describe coverage, not row content.

## Totals

| Scope | Files | Size |
|---|---:|---:|
| On disk (`data/` + `outputs/research/`) | 232,930 | 15.41 GB |
| Pinned manifest, shared through R2 (`data/MANIFEST.pin.json`, 2026-10-18) | 123,465 | 12.43 GB |
| Excluded from sharing by `sync.EXCLUDE` (closed or banned sources) | about 109,000 | about 3.0 GB |
| On disk, shareable, not yet in the manifest | 22 | small |

Manifest integrity against disk, by path and size: 0 files missing, 0 files changed size. The 22
unpinned files are the four studies of 2026-10-20 and 2026-10-21 under `outputs/research/` with
their `prereg_*.json` records, and three new slices under `data/processed/wrds/`.

Upload status, checked 2026-11-01: no team-data bucket is configured on the lead's machine
(`IVCRUSH_R2_*` unset), and the WRDS mirror bucket holds no `earnings_iv_crush/` prefix. The
manifest and pin exist locally, but there is no evidence that any file has been pushed, so a
teammate cannot yet pull.

## 1. Databento OPRA (metered, per-user licence)

About 10.3 GB, all shared. Logged spend to date is about USD 62 (see `docs/DATA.md` section 5;
the Databento portal is the authority).

| Dataset | Schema | Names | Span | Files | Size | Built by | Read by | Status |
|---|---|---:|---|---:|---:|---|---|---|
| `data/cache/backfill_chains` | `cbbo-1m`, 15:59 ET chain per entry and exit session | 460 | 2013-04 to 2026-10 | 27,353 | 0.75 GB | `scripts/build/pull_broad_history.py` | `research/chains.py`, `score_oos_2026.py`, `research_calendar_cost.py` | live, primary event chains |
| `data/processed/databento_quotes` | `cbbo-1m`, held contracts only | 61 | 2013-04 to 2024-12 | 4,426 | 0.04 GB | `data/databento_quotes.py` | megacap quote-marked book | live, the marking basis |
| `data/processed/databento` | `ohlcv-1d`, trade-based closes | 45 | 2019-01 to 2026-05 | 2,180 | 0.33 GB | `data/databento_options.py` | comparison only | superseded marking basis |
| `data/cache/flow` | `cmbp-1` and trades, tick level | 318 | 2023-04 to 2026-06 | 2,926 | 9.01 GB | `research/execution/research_flow_liquidity.py` | same | flow line; 58% of all shared bytes |
| `data/cache/fills_et` | `cmbp-1` quotes and prints | 27 | 2023-04 to 2024-12 | 162 | 0.07 GB | `research/execution/research_fills_study.py` | same | fills study, current window |
| `data/cache/fills` | `cmbp-1` quotes and prints | 27 | 2023-04 to 2024-12 | 162 | 0.08 GB | none in tree | none in tree | earlier window of the fills study; candidate to drop |
| `data/cache/postea_quotes` | `cbbo-1m` at 15:59 ET | n/a | 2019-02 to 2024-10 | 1,002 | 0.01 GB | **missing** (see Gaps) | post-announcement study | closed study, builder lost |
| `data/cache/postea_chain` | chain snapshots | 23 | 2019-10 to 2024-10 | 36 | <0.01 GB | **missing** | same | same |

## 2. WRDS mirror on R2 (Queen's licence, read-only)

| Dataset | Content | Files | Size | Built by | Status |
|---|---|---:|---:|---|---|
| `data/processed/wrds` | Projected slices of Compustat `rdq`, IBES, CRSP daily, surprise panel, Fama-French, 13F; to 2024-12 | 3,087 | 0.24 GB | `data/wrds_r2.py` (local cache of the mirror) | live; 3 slices unpinned |
| `data/cache/postea_spots_crsp` | As-traded CRSP spots per event | 2,411 | 0.04 GB | **missing** | closed study |
| `data/cache/postea_spots` | Split-adjusted spots per event | 2,406 | 0.11 GB | **missing** | closed study; superseded by the CRSP as-traded cache |

## 3. Free sources (shared)

| Dataset | Source | Names | Span | Files | Size | Built by | Status |
|---|---|---:|---|---:|---:|---|---|
| `data/cache/edgar` | SEC EDGAR 8-K Item 2.02 acceptance times, XBRL | n/a | filings from 2004 | 2,516 | 0.09 GB | `data/edgar_sessions.py` | live, session check |
| `data/cache/dolthub_runup` | DoltHub dated chains | 64 | 2019-02 to 2024-12 | 11,789 | 0.06 GB | `research/timing/research_vega_runup.py` | closed study |
| `data/cache/dolthub_p2` | DoltHub dated chains | 70 | 2021-01 to 2026-08 | 6,083 | 0.03 GB | `research/off_earnings/research_p2_term_slope.py` | closed study |
| `data/cache/dolthub_spread` | DoltHub dated chains | 64 | 2019-02 to 2024-11 | 2,842 | 0.02 GB | `research/execution/research_entry_spread_dolthub.py` | closed study |
| `data/cache/spy_macro` | DoltHub, one SPY chain per business day | 1 | 2019-01 to 2024-12 | 1,566 | 0.01 GB | `research/off_earnings/research_spy_macro.py` | closed study |
| `data/cache/deribit` | Deribit BTC options | n/a | 2023-01 to 2026-10 | 237 | 0.03 GB | `research/other_markets/research_deribit_macro.py` | closed line |
| `data/cache/kalshi`, `kalshi_rep` | Kalshi event contracts (JSON) | n/a | n/a | 6,503 | 0.04 GB | `research/other_markets/research_kalshi_*.py` | closed line |
| `data/processed/dolthub_chain_*` | DoltHub per-event chains | 18 | 2019-01 to 2024-06 | 1,834 | 0.01 GB | `data/dolthub_options.py` | early work |
| `data/processed/calendar_*` | Per-name earnings calendars | 50 | 2024-02 to 2026-06 | 350 | <0.01 GB | `data/calendar_build.py` | superseded by `outputs/research/calendar_*` |

## 4. Not shared (`sync.EXCLUDE`), local only

| Dataset | Source | Files | Size | Reason |
|---|---|---:|---:|---|
| `data/processed/alpaca_chain_panel_*`, `alpaca_chain_entry_*` | Alpaca daily option bars, 346 names, 2023-12 to 2026-06 | 107,425 | 0.74 GB | end-of-day last trades leak against a 15:59 decision; never used for selection |
| `data/cache/alpaca_legacy` | Alpaca | 60 | 0.68 GB | same |
| `data/processed/lse`, `lse_1m`, `lse_raw` | London Strategic Edge | 1,087 | 0.79 GB | evaluated, not adopted |
| `data/processed/nse_*`, `nse_fo` | NSE India F&O bhavcopy | 19,337 | 0.68 GB | closed geography |
| `data/processed/b3_*`, `b3_cotahist` | B3 Brazil COTAHIST | about 24,300 | 0.30 GB | closed geography |

## 5. Built research datasets (`outputs/research/`, shared, 1.20 GB)

The files most studies read are listed in `docs/DATA.md` section 3. Of the 1.20 GB, 1.14 GB is
loose files at the top level (38 parquet, 144 CSV, 31 logs, 30 JSON). Each subfolder holds one
study's outputs and its findings note; the dated folders (`2026-10-20-hedged-hold` and the four
after it) are not yet pinned.

## Gaps and defects found by this inventory

1. **Lost builders.** `postea_quotes`, `postea_chain`, `postea_spots` and `postea_spots_crsp`
   were built by `scripts/build_postea_calendar.py`, `build_postea_spot_cache.py`,
   `research_postea_pull.py` and `research_postea.py` (named in
   `research/timing/findings/post_announcement_overpricing.md`). None exists in the tree or in
   any git commit, so the caches cannot be regenerated and the metered pull cannot be repriced.
   The cached files on the lead's disk are the only known copy.
2. **Orphan cache.** `data/cache/fills` has no reader in the tree; `fills_et` replaced it. It
   costs 76 MB in every full pull.
3. **Stale pin.** 22 shareable files postdate the 2026-10-18 manifest; re-pin after the current
   studies settle.
4. **Pull size is dominated by one study.** `flow` is 9.0 of the 12.4 GB; a teammate who does not
   work on tick-level execution should not fetch it (see below).

## Handoff

A teammate with the read keys in `.env` takes only what their work needs:

```bash
python -m earnings_iv_crush.data.sync pull --only outputs/research   # 1.2 GB: built events, ledgers
python -m earnings_iv_crush.data.sync pull --only data/cache/backfill_chains   # 0.75 GB: event chains
python -m earnings_iv_crush.data.sync pull                          # 12.4 GB: everything shared
python scripts/validate_screen.py                                   # must reproduce N=391, +0.055992
```

Every file is checked against its SHA-256 on arrival, and the manifest itself against the hash
pinned in git, so what a teammate receives is byte-identical to what the results were built on.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\docs\DATA_CATALOGUE.md
