# Data

Which source feeds what, what each costs, what its licence allows, and how a teammate gets the
cached research inputs. Credentials live only in a git-ignored `.env`; `.env.example` lists the
variable names with no values.

## 1. What a clone has, and how to get the rest

A clone carries the code, the tests, the pre-registrations, the findings, the 346-name trading
universe (`data/universe_broad.csv`) and two of the project's own small artefacts
(`outputs/research/fills_rescore.csv` and the `prereg_*.json` hash records). It does not carry
the research caches: they are licensed or vendor-derived (Databento OPRA, WRDS), so they are
shared through the club's Cloudflare R2 bucket, never through git.

The bucket holds a manifest of every shared file with its size and SHA-256; the repository
tracks only `data/MANIFEST.pin.json`, which fixes the manifest's own hash and the file count and
size per folder, so a manifest that does not match the pin is refused. With the bucket keys in
`.env`:

```bash
python -m earnings_iv_crush.data.sync verify        # what you are missing
python -m earnings_iv_crush.data.sync pull          # fetch it, hash-checked
python scripts/validate_screen.py                   # then this must reproduce N=391, +0.055992
```

`pull` refuses to start if the bucket lacks any file in the manifest, and re-hashes every
download before it replaces a local file. The full set is about 12 GB, most of it the tick-level
flow pull (`data/cache/flow`); `pull --only outputs/research` fetches just the built event files
and ledgers most studies read. Caches of closed or banned sources (Alpaca, London Strategic Edge,
India, Brazil) are not shared; `EXCLUDE` in `earnings_iv_crush/data/sync.py` lists each with its
reason. The lead regenerates the manifest after building new
caches (`sync manifest`) and uploads with `sync push`, which needs write keys.

**Licence rule.** Raw rows from Databento, WRDS (CRSP, Compustat, IBES, 13F) or any other
licensed source never go into a commit, a findings note, a figure's data file or a chat with
someone outside the team. Aggregates the project computed (a Sharpe, a decile mean, a count) are
the project's own and are fine.

## 2. Sources

Module paths are relative to `earnings_iv_crush/`.

### Metered or licensed

| Source | Module | Supplies | Licence and cost | Env |
|---|---|---|---|---|
| Databento OPRA `cbbo-1m` | `data/databento_quotes.py` | The marking basis: consolidated best bid and offer each minute from 2013-04-01; the mark is the last two-sided quote at or before 15:59 ET | metered, per-user licence; narrow requests to the two held contracts and a short window (this cut one study's cost about 1,000 times) | `DATABENTO_API_KEY` |
| Databento OPRA `cmbp-1`, trades | `data/databento_quotes.py` | Tick quotes and prints for the fills and flow studies (from 2023-03-28) | metered | same |
| Databento OPRA daily bars | `data/databento_options.py` | Superseded marking basis, kept for comparison | metered | same |
| WRDS mirror on R2 | `data/wrds_r2.py`, `data/wrds_panel.py` | Compustat `rdq` and IBES announcement times (the calendar), CRSP daily (spot), a point-in-time surprise panel, Fama-French factors, 13F; to 2024-12 | Queen's licence, read-only; no OptionMetrics was ingested | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET` |
| Interactive Brokers | `live/ib_market.py`, `live/ib_orders.py` | Live chains, underlying quotes, paper orders | paper account; real-time option quotes need the OPRA top-of-book subscription on the linked live account (USD 1.50 a month), otherwise quotes are 15 minutes delayed | none (the gateway holds the login) |

### Free

| Source | Module | Supplies | Caveat | Env |
|---|---|---|---|---|
| Finnhub | `data/earnings.py` | Upcoming earnings with `bmo`/`amc` | one of the three calendar votes; dates can disagree with the others | `FINNHUB_API_KEY` |
| Nasdaq calendar | `data/earnings.py` | Upcoming earnings with session | second vote; no key | none |
| Yahoo (yfinance) | `data/earnings.py`, `data/equities.py`, `data/options.py` | Earnings dates with time (third vote), equity bars, current chains, ex-dividend dates | rate-limited from datacenter addresses | none |
| SEC EDGAR | `data/sec_edgar.py`, `data/edgar_sessions.py` | 8-K Item 2.02 acceptance times (session after the fact), CIK map, XBRL EPS | the calendar session matches EDGAR on 99.1% of 1,990 events | `SEC_USER_AGENT` |
| DoltHub | `data/dolthub_options.py` | Dated chains 2019 to 2024 with bid, ask and greeks | sampled about three sessions a week with rotating expiries; check the snapshot dates of any pair you build | none |
| Alpaca | `data/alpaca_options.py` | Daily option bars from about Feb 2024 | end-of-day last trades: never build selection features from them (they leak relative to a 15:59 decision) | `ALPACA_KEY`, `ALPACA_SECRET` |
| FRED | `data/vix.py` | VIX, VIX3M | | `FRED_API_KEY` (optional) |
| Deribit, Kalshi | research scripts under `research/other_markets/` | BTC options; event contracts | closed lines | none |

## 3. The main built datasets

All under `outputs/research/` and fetched by `sync pull`.

| File | What it is | Built by |
|---|---|---|
| `events_megacap_databento.parquet`, `events_megacap_v2.parquet` | Megacap 2019-24 events, quote-marked (the frozen book's input) | `scripts/build/build_quote_marked_chains.py` |
| `reverse_alpha/panel.parquet`, `quotes.parquet` | 1,794 megacap events 2013-24 with the P&L decomposition and two-sided quotes | `research/selection/reverse_alpha_panel.py`, `reverse_alpha_quotes.py` |
| `events_broad_oos_2025.parquet`, `oos_2026_ledger.csv` | Broad 2025-26 block, 2,037 events on 346 names; the ledger carries the attrition bias in `docs/SYSTEM.md` | `scripts/build/build_broad_oos_2025.py`, `research/frozen_selector/score_oos_2026.py` |
| `ml_zoo/` events | 11,257 events on the 15:59 basis, broad 2013-2026 | `scripts/build/build_broad_history_events.py` |
| `calendar_wrds*.parquet`, `calendar_broad_2013_2024.parquet` | Point-in-time calendars with session | `scripts/build/build_wrds_events.py` |
| `fills_rescore.csv` (tracked) | The three-row cost-basis summary the attainability test reads | `research/execution/run_fills_rescore.py` |

## 4. Gaps

- No OptionMetrics: no historical implied-volatility surface or open interest. Ask the mirror
  maintainer whether `optionm_all` is licensed and can be ingested.
- Tick data only from 2023-03-28; no trade-condition codes, no depth.
- Intraday quotes exist only for the two held contracts in a short window.
- The 2025-26 calendar has no IBES backstop; sessions are checked against EDGAR instead.

## 5. Metered pulls

Every metered entry point prices the request with the vendor's free cost call first, takes a hard
`--cap` in US dollars, and reserves against it atomically so parallel workers cannot overshoot.
State the estimate, get the lead's go-ahead, and reconcile actual spend against the estimate
afterwards in the findings note. Logged Databento spend is about USD 36 to 2026-09-14, plus
USD 5.15 (flow pull) and USD 20.87 (15:59 history) since, about USD 62 in all; the portal is the
authority.
