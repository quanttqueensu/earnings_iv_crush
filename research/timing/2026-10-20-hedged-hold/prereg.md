# Pre-registration: delta-hedged short straddles held to expiry, with a HAR selector

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record: `outputs/research/prereg_2026-10-20-hedged-hold.json`.
Scorer: `research/timing/2026-10-20-hedged-hold/study.py`.

## Hypothesis

H1 (S1, pre-event). A short at-the-money straddle on an expiry 20 to 45 calendar days out, sold at
the bid at 15:59 ET on the session before the announcement reaction, delta-hedged daily in the
stock and held to expiry, earns a positive mean net return on margin per trade. Mechanism: the
position collects the announcement jump premium and the diffusive variance premium over the
option's life, and pays one option half-spread (no exit cross, settlement at intrinsic) instead
of the two that sink the next-session book. The daily hedge removes most of the terminal-move
exposure that sank the unhedged post-event hold.

H2 (S2, post-event). The same position entered at 15:59 on the reaction session, on an expiry
14 to 45 days out, earns a positive mean net return on margin per trade. Mechanism: the
single-stock variance risk premium after the event (implied exceeded realised by 2.27 vol points
on the unhedged 2025-26 study), collected hedged and for one half-spread.

H3 (S3a on the S1 book, S3b on the S2 book). Events whose entry implied diffusive variance is
high relative to a HAR-RV forecast of variance over the option's life earn more volatility
points per unit of vega than events where it is low.

Nearest closed work: post-announcement straddle held to expiry (unhedged, DoltHub/Alpaca
2025-26, net RoM -1.41% [-3.23%, +0.20%]); conditional hold to expiry (front weekly, unhedged);
calendars (front short, back long, closed next session). This study differs in the hedge, the
tenor, the single spread and the data (full OPRA 15:59 chains, 2013-2024). Closest published
work: Goyal and Saretto (JFE 2009) and Cao and Han (JFE 2013) on delta-hedged single-stock
option returns; Corsi (JFEc 2009) for HAR-RV; Dubinsky, Johannes, Kaeck and Seeger (RFS 2019)
for the two-expiry jump split.

## Data and blocks

Events: `outputs/research/ml_zoo/events_full.parquet` (ticker, announce, entry and exit dates).
Chains: `data/cache/backfill_chains/{ticker}_{date}.parquet`, OPRA cbbo-1m at 15:59 ET, all listed
expiries. Stock path: CRSP daily stock file (`dsf`) from the R2 mirror (`prc`, `ret`, `cfacpr`,
`bid`, `ask`), linked by ticker to the permno live on the entry date (`dsenames`).

- Discovery: entry dates 2013-01-01 to 2018-12-31.
- Validation: entry dates 2019-01-01 to 2024-12-31.
- Confirmation: entry dates 2025-01-01 onward, run only if a free unadjusted daily close source
  covers the names (Alpaca raw consolidated closes); otherwise reported as not run. Equity hedge
  cost on this block is the name's median CRSP half-spread over 2024. The 2025-26 events have had
  unhedged straddle outcomes viewed in earlier studies; no hedged hold-to-expiry outcome has
  been viewed on any block.

## Specification

- Parse: `earnings_iv_crush.research.chains._parse_chain` (both sides quoted, last quote per
  contract). Times to expiry are calendar days divided by 365 (ACT/365); rate zero
  (`GlobalConfig.risk_free_rate`).
- Sold expiry: S1, the shortest expiry with 20 to 45 days from the entry date that expires on or
  after the exit date; S2, the shortest expiry with 14 to 45 days from the exit date.
- Forward and strike: at the strike minimising |call mid - put mid|, F = K + C - P. Sold strike:
  the listed strike nearest F at which both legs have a positive bid.
- Sale price: call bid plus put bid (the touch). Fee USD 0.65 per contract per leg on entry.
- Implied vol of the sold straddle: Black-Scholes inversion of the straddle mid at forward F.
- Jump split (S1 only): E1 = shortest expiry on or after the exit date, E2 = the sold expiry, or if
  the sold expiry is E1, the next expiry at least 14 days after E1. Total variance V = sigma^2 T.
  Diffusive variance sd2 = (V2 - V1) / (T2 - T1); jump variance J = V1 - sd2 T1. Valid if sd2 > 0
  and J >= 0.
- Hedge: hold +delta_straddle shares per straddle share, Black-Scholes delta at the CRSP close of
  each trading day from the entry date to the last trading day before expiry. Hedge volatility:
  S1 uses the sold expiry's total implied vol for closes before the exit date and sqrt(sd2) from
  the exit-date close on (the total implied vol throughout when the split is invalid, counted);
  S2 uses the sold expiry's implied vol. Daily hedge P&L h_t * P_t * ret_{t+1} (CRSP total return).
- Settlement: |S_E - K| at the CRSP close on the expiry date, or the last trading day before it.
  The final hedge is unwound at that close. Delivered stock disposal cost 5 bp of S_E on one share.
- Equity cost: half the CRSP closing quoted spread, (ask - bid) / 2 / prc, floored at 1 bp, per
  share traded, on every hedge change and the unwind.
- Margin per share: 0.20 F + sale price + 0.5 max_t |h_t| P_t.
- Net P&L per share: sale price - settlement value + hedge P&L - equity costs - fees - disposal.
  Net return on margin (RoM) = net P&L / margin.
- Exclusions, each counted in a funnel: no chain file, no expiry in the window, no two-sided
  strike near F, implied vol not invertible, permno not linked, CRSP path incomplete to expiry,
  any change in `cfacpr` from entry to expiry (split or other distribution). Outcome dependence
  of drops is tested by comparing the absolute reaction-day return of dropped and kept events
  (Mann-Whitney).
- HAR (S3): daily log returns ln(1 + ret); RV_t = r_t^2. The return on each of the name's exit
  (reaction) dates is excluded. OLS of RV_{t+1} on a constant, RV_t, the 5-day mean and the 22-day
  mean, fitted on all complete rows strictly before the decision date (S3a: before the entry date;
  S3b: before the exit date), minimum 500 rows. Forecast iterated h steps, h = weekdays from the
  decision date to expiry (an approximation of the exchange calendar for the horizon only),
  annualised by 252 / h. Signal S3a = sd2 / HAR variance (valid split required); S3b = sold
  implied variance / HAR variance.
- Terciles: breakpoints from the signal values of all events with strictly earlier entry dates
  (S3a) or exit dates (S3b), pooled across names, minimum 200 prior events.
- Selector outcome: net volatility points per unit vega = net P&L per share / (straddle vega per
  share for one vol point at entry). This is the residual-value analogue for a hedged hold: it
  does not reward selling a larger option.

## Primary statistic and inference

S1, S2: mean net RoM per trade (net, at the touch, on margin, per trade, not annualised), with
per-trade Sharpe. 95% percentile cluster bootstrap, 5,000 draws, seed 0, clusters are expiry
dates (overlapping holds share a path). DSR against 1,539 trials with the recorded trial-Sharpe
dispersion 0.127475.

S3a, S3b: top-minus-bottom tercile mean of net vol points per vega, same bootstrap; the top
tercile's mean net RoM against `protocol.matched_random_null` (5,000 draws) over all
tercile-assigned events in the block.

Reported, not trials: the next-session front straddle on the same events and machinery (the
control), results at the mid, and by year.

## Success criterion

S1, S2: mean net RoM with the interval's lower bound above zero in discovery, and again in
validation. S3a, S3b: top-minus-bottom lower bound above zero in discovery and in validation, and
the top tercile at or above the 95th percentile of the matched null in both. Confirmation is
reported and must not reverse sign for a candidate to be called promising.

## Kill criterion

Any candidate whose discovery lower bound is at or below zero is closed and not run on
validation. A candidate passing discovery and failing validation is closed. No specification
change follows a failure.

## Trial accounting

Four trials (S1, S2, S3a, S3b). Count before: 1,532 (conservative input in
`docs/RESEARCH_STATE.md`). The sibling pre-registrations of the same date declare three more
(jump richness, two post-event equity signals); the count after all seven is 1,539. A second wave
(S1 at 46 to 120 days; S2 selected by the post-event term slope; a GARCH(1,1) with an
announcement dummy in place of HAR for the stronger S3 arm) is declared here and runs only if
fewer than three candidates pass, each under its own amendment, adding three.
