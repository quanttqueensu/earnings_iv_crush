# Pre-registration: idiosyncratic volatility and lottery demand as selectors for the hedged event hold

Frozen before any signal is joined to an outcome. Record:
`outputs/research/prereg_2026-11-02-ivol-max-hedged-hold.json`. Scorer:
`research/selection/2026-11-02-ivol-max-hedged-hold/study.py`.

## Hypotheses (two trials)

- S1, idiosyncratic volatility. Cao and Han (JFE 2013) find delta-hedged equity option returns fall
  with the underlying's idiosyncratic volatility: market makers charge more to hold options they
  cannot hedge cheaply. A seller of hedged options should earn more on high-IVOL names.
- S2, lottery demand. Byun and Kim (JFE 2016) find options on lottery-like stocks (high maximum
  daily return over the prior month, Bali, Cakici and Whitelaw JFE 2011) are overpriced, calls
  most. A seller should earn more on high-MAX names.

Base trade: the hedged event hold, arm H (prereg 3e80d470 and amendment 91293d96), unchanged.
Neither signal is on the closed list. The nearest closed rows are the VRP and trailing-RV overlays
(total realised volatility on the one-night buy-back, no lift) and own-history richness. IVOL here is
residual to the market, MAX is a skewness proxy, and the base trade is the hedged hold.

## Data

- Outcomes: arm H, `ok` events, `outputs/research/2026-11-02-hedged-event-hold/events.parquet`
  (2013-24) and `events_confirm_2025_26.parquet` (2025-26). Unit per trade, fraction of m0.
- Stock returns: CRSP daily total returns (`outputs/research/2026-10-20-hedged-hold/crsp_paths.parquet`,
  2011-24) for 2013-24 events, by permno from the features file; Yahoo Finance Adj Close returns
  for 2025-26 events. Market: SPY Adj Close returns from Yahoo.
- Blocks: discovery 2013-18, validation 2019-24, confirmation 2025-26 (by reaction date).

## Signals (strictly before the entry session)

- IVOL: standard deviation of residuals of OLS of the stock's daily total return on SPY's over the
  60 sessions ending the session before the entry date; at least 50 valid days, else missing.
- MAX: the largest daily total return over the 21 sessions ending the session before the entry
  date; at least 18 valid days, else missing.
- Deciles: `hedged_hold.causal_bins` with 10 bins and 200 prior events, breakpoints from strictly
  earlier reaction dates across the full 2013-26 sequence. Selected = top decile.

## Statistics

- Per block: per-trade Sharpe of H in every decile (all reported); top-decile Sharpe with a
  date-clustered 95% interval; `matched_random_null` percentile of the top decile's Sharpe against
  random draws of the same size from that block's assigned events.
- Residual value (P4): H per unit of entry premium (`H x m0 / s0`), so a selector that only picks
  larger options gains nothing; top minus bottom decile difference with a date-clustered interval.

## Criterion, per signal

PASS only if all of:
1. discovery: top-decile null percentile >= 95;
2. validation: null percentile >= 95 and top-decile Sharpe interval excludes zero above;
3. confirmation: top-decile Sharpe point > 0 and null percentile >= 95.

Anything else is FAIL, with the failed step named. Attrition: events with a missing signal are
counted per block, and mean H of missing against assigned events is reported; a gap above 0.5% of
m0 flags the block.

## Trial accounting

Two trials: 1,557 + 2 = 1,559.
