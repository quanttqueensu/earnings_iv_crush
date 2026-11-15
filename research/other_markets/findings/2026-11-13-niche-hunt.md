# Niche hunt: scheduled-event volatility beyond US single-name earnings (2026-11-13)

Artefacts (lane folders, scripts, logs and per-event files) are in `outputs/research/2026-11-13-niche-hunt/`, which is shared through the R2 bucket, not git: `python -m earnings_iv_crush.data.sync pull --only outputs/research`. Paths below are relative to that folder unless they start at the repository root.

Twenty lanes, run in parallel under `BRIEF.md` and `LANES.md`, looked for a scheduled-event
premium that survives costs at the touch, in a market Interactive Brokers can paper trade, on data
obtainable at zero cost. An independent quant review (`niche-hunt-reviewer`) checked every lane
on disk except N11, which finished after it; its corrections are applied below. Everything here
is exploratory: 158 trial numbers
were used (2,082 to 2,681 reserved), no lane ran under a hashed pre-registration in
`outputs/research/prereg_*`, and several held-out blocks had already been viewed by an earlier
study or another lane.

## Result

No lane produced a tradeable candidate. Fourteen lanes scored a held-out read on real data and
none passed. The pattern is the same in every market with a measurable event: options price the
release, the premium at the mid is small or absent after 2019, and where the touch could be
measured it exceeds whatever premium remains. Grains, Treasury weeklies and SOFR options remain
untested at the touch because no free intraday option quotes exist; each needs a metered pull,
and none has evidence strong enough to set direction.

## Verdict by lane

Per trade unless stated; intervals are date-clustered 95% (97.5% where the lane pre-registered it).
"Settle" and "index" results are gross ceilings at settlement or the mid, not tradeable levels.

| Lane | Market and event | Best held-out evidence | Basis | Verdict |
|---|---|---|---|---|
| N08 | SPY/QQQ/IWM, CPI and payrolls (cached Databento quotes) | Frozen rule 2,312: book +0.76% of premium [-16.3, +17.1], paired +5.1% [-13.2, +23.2], N=20 | net at the touch | not viable |
| N08 | Same, sell 15:59, buy 10:00 (discovery only) | -1.86% [-4.52, +0.69], N=204; round trip about 2.7% of premium | net at the touch | not viable |
| N15 | ADRs and foreign reporters, earnings | 2,503: -7.26% of m0 [-10.68, -3.71], N=38; foreign minus US -1.29 points [-5.79, +3.18] | net at the touch | not viable |
| N11 | ForecastEx versus Kalshi, macro contracts | Gap 2,386: -$0.039 per contract [-0.154, +0.077], N=58; favourites 2,385: -$0.007 [-0.061, +0.029], N=91 | net of fee plus 2c allowance | not viable |
| N09 | VIX futures, FOMC (published trade) | 2,330: -0.028 SD [-0.339, +0.244], N=78 (2017-26) | net, assumed one tick | not viable |
| N03 | NYMEX natural gas, EIA storage | 2,142: extra variance -0.13 days [-0.36, +0.16], N=174 weeks (2019-24) | settle | not viable |
| N04 | WTI, EIA petroleum report | 2,177 buyer +16.0% [-12.6, +77.8], N=98; seller test 2,176 uninformative (ill-posed ratio) | index | not viable |
| N17 | USO/GLD/SLV/TLT options, EIA and macro | USO 2,562: -8.16% [-9.18, -7.23], N=187 | index plus today's touch | not viable |
| N05 | Treasuries (TLT via VXTLT), CPI/NFP/FOMC | Pooled +0.60% of 30-day premium [-0.69, +1.79], N=181; FOMC +0.19% [-2.48, +2.55], N=47 | index | fails; pull candidate |
| N06 | SOFR options, FOMC | 2,238: -3.60% [-11.51, +3.01], N=15; underpowered by construction | synthetic settle marks | uninformative; pull candidate |
| N12 | Gold and silver, macro | GLD 2,412: +0.02 days [-0.61, +0.61], N=147 | index | not viable |
| N13 | ICE softs, WASDE | Cotton 2,446: variance ratio 1.27 [0.84, 1.90], N=113 | settle | not viable |
| N16 | Country ETFs, Copom and elections | Copom 2,532: +0.6% of weekly premium [-19.8, +23.3], N=23 | index | not viable |
| N14 | Bank stress tests | 2,472: +0.51 sessions [-0.03, +1.16], N=150 bank-nights on 15 nights | close to close | not viable |
| N10 | Crypto events, Deribit expiry Friday | +0.154 of premium [-0.186, +0.469], N=46 | net, estimated touch | not viable |
| N02 | Livestock, Cattle on Feed | no free data; both trials abandoned unscored | n/a | pull, low priority |
| N07 | CME FX options, central banks | realised only; dealer quotes at or below delivered event variance | spot | no sell-side surplus |
| N01 | CBOT grains, USDA reports | literature only; no free option data | n/a | pull candidate |
| N18, N19, N20 | Literature, data access, IB execution | infrastructure | n/a | see below |

Trustworthy as stated (reviewer): the negative verdicts of N03, N08, N09 and N15. N12, N13 and
N16 hold as negatives except for provenance (below).

## Corrections made in review

- **N08 provenance rebuild (2,313, 2,314) is not firmer evidence.** It replaced Yahoo hedge and
  settlement prices with 15:59 put-call-parity forwards. Each day's forward refers to a different
  expiry, so a SPY ex-dividend inside the window enters as a false price move: per-event gap 16.0%
  of premium on the 18 events near an ex-date against 5.3% on the other 72, with a systematic
  +1.98-point shift that accounts for the whole change from 2,307. A correlation of 0.978 between
  the two versions hid it. The frozen 2,307 and 2,312 stand, flagged for Yahoo provenance.
- **N08's best discovery rule** (expiry within three days, delta-hedged hold; +10.9% paired
  [-0.7, +22.0], N=90) was picked from a tenor split after 20 trials; its t of about 2 does not
  survive that search, and shared controls make the event bootstrap too narrow.
- **N10 did not pass discovery.** The pre-registered primary (2,352, on notional) failed at +0.95%
  [-0.14, +2.07]; the pass came from switching to return on premium afterwards. The IBIT-versus-
  Deribit ratio (1.22 to 1.38, one snapshot) is like-for-like but is not a seller's edge: the
  lane's own figure puts IBIT implied at 0.97 of realised weekend variance.
- **N04 2,176** is uninformative, not negative (denominator noise about five times its mean).
- **N14 stage B** intervals rest on 2 to 4 release clusters, too few for a cluster bootstrap;
  stage A printed held-out without a freeze (disclosed).
- **N09** held-out (2017-26) overlaps macro outcomes the 2026-11-01 index study had printed; not
  flagged by the lane.
- **N05** freeze note hashes a Yahoo file since deleted; its Cboe rebuild (2,218 to 2,221) moved
  every figure by 0.12 points or less.

## Process breaches

- **Robots.txt.** Yahoo's chart and query endpoints and Stooq disallow automated clients. Results
  still resting on them: N13 (2,442 to 2,451, via `yfinance`), N16 (2,532 to 2,535), N07
  (section 6, no trials), N08 (2,304 to 2,312). N04, N05, N12 and N17 withdrew or rebuilt; N12's
  rebuild on Cboe's public GLD and SLV history (2,418 to 2,422, exploratory) reproduces the
  held-out figures exactly, and its one Stooq request returned only a challenge page, so no Stooq
  price was used. N14 reads the pre-existing project cache `data/cache/yahoo_adj`
  (written 2026-11-10, before the hunt). N01 sent three test requests to Yahoo before reading its
  robots.txt; N04 fetched one disallowed EIA archive page; N08 fetched one ALFRED page without
  checking. Every affected scored result is a fail, so no verdict depends on the breach.
- **Search budget.** The shared web-search allowance ran out partway through; several lanes list
  unverified items as a result.

## Candidates that need a metered pull (team lead's decision)

The project's Databento account may not cover CME data; nothing in the repository shows it does.
That is the first thing to check. None of these has real-data evidence at the touch.

1. **N05, CBOT weekly Treasury options** (ZN, ZB) into NFP, CPI and FOMC, held to the 14:00 CT
   expiry. The fixed 1/64 tick makes cost a smaller share of premium than in equities. Net edge is
   built from Wright (2020) settlement premia read partly by eye, with an assumed one-tick quote:
   10-year NFP about +6% at one tick and +3% at two; 10-year FOMC +0.9% and -3.1%; 30-year about
   +6% and +4%. The lane's own real-data held-out failed. Pull: one-minute top of book on
   near-the-money weeklies, events plus controls, about 3 GB (lane estimate, rate unverified).
2. **N01, CBOT grains** into USDA reports (11:00 CT, mid-session; weekday options since February
   2025). Gross premium from an abstract with unknown tenor; net range -1.2% to +5.0%. The $199
   Standard month buys about 14 report dates against the roughly 175 the lane's own power
   calculation needs, so it can measure the spread but cannot decide the premium.
3. **N06, SOFR options** into FOMC. Rests on Eurodollar-era Bauer, Lakdawala and Mueller (2022):
   +9.1% of premium gross on the front contract; the paper itself says 0.5 to 1 bp spreads would
   eat most of it. Nets positive only where quarter-tick quotes apply.

N03 (gas weeklies), N04 (CL Wednesday weekly), N02 (cattle weekly), N14 (bank weeklies) and N15
(liquid ADRs) each describe a pull; none is recommended on the evidence. N10's IBIT history pull
(about $0.70, $3 cap) would settle a lead the review has already weakened.

## Zero-cost follow-ups

- **ForecastEx index digitals against cached SPY/QQQ chains (N11).** Daily S&P 500 and Nasdaq-100
  contracts, 35 million traded since 2025, compared on CPI and FOMC days with digitals implied by
  `data/cache/index_chains`. Free data, adequate capacity, untested.
- **Pre-market SPY options session (N08).** Since 2026-10-19 Cboe trades SPY, QQQ and IWM options
  07:30 to 09:25 ET, so an 08:30 release falls inside a session. No history exists; recording
  quotes (no orders) on CPI mornings would show whether an 08:35 exit captures the reset at a
  tolerable touch. Needs real-time OPRA through IB.

## Findings that affect the current paper book

- **No penny fills on IB paper (N20, verified at IB's page; raw copy in
  `N20-ib-execution/raw/ib/aboutpaper.txt`).** "Penny trading for US Options is not supported.
  Orders can be submitted but will not receive a penny fill." The ladder rounds legs under $3.00 to
  $0.01 (`ib_orders.round_to_tick`, `ladder._tick`), so mid and partial rungs on those legs measure
  the simulator, not the market. Not yet checked against `outputs/live/order_events.csv`.
- **Calendar timing for Canadian names (N15).** Finnhub-sourced events show no pending event in
  the entry chain on 21% of Canadian events in 2025 (13 of 61), against 1.2% for US names, most
  likely pre-market releases stamped after-close. A front-over-next implied vol check on the entry
  chain catches it. Whether the paper book's universe includes these names is not yet checked.
- **Futures-option readiness (N20).** The harness's Reg-T straddle margin overstates SPAN 4 to 16
  times and must not be reused; `broker_option_positions` sees only secType OPT, so a futures-option
  leg or an assigned future would be invisible to the orphan check.

## Literature anchor (N18)

No published option study measures a scheduled-event premium net of the touch in any asset class.
The only peer-reviewed net-of-cost result (short VIX futures on FOMC days, Fernandez-Perez, Frijns
and Tourani-Rad 2017) does not survive 2017-26 (N09). Index macro days are limited by sample size
before cost: on Wright's figures a short one-day index straddle keeps about 13% of premium gross,
a per-trade Sharpe of 0.15 to 0.20, needing 100 to 180 events for t of 2 (lane arithmetic).

## Trial accounting

158 numbers used: N02 2, N03 4, N04 6, N05 20, N06 9, N08 23, N09 11, N10 14, N11 6, N12 11,
N13 10, N14 9, N15 3, N16 4, N17 26; N01, N07 and N18 to N20 used none. All fall inside their reserved
blocks. Unused reserved numbers are not trials.

## Files

Each lane's `evidence.md`, `sources.csv`, `trials.csv`, `diagnosis.log` and freeze notes are in its
folder under `C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\`.
