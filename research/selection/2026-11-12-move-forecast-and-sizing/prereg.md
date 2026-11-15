# Pre-registration: forecasting the size of the earnings move, and sizing the book on it

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-12-move-forecast-and-sizing.json`.
Scorer: `research/selection/2026-11-12-move-forecast-and-sizing/study.py`.

## Hypothesis

Two questions, kept separate because they have different answers in the literature and in this
project.

**Part A, forecasting.** Does information outside the option price forecast the size of the
earnings reaction better than the implied move alone? The option-implied announcement jump is
known to be an informative forecast (Dubinsky, Johannes, Kaeck and Seeger, RFS 2019), and every
selector that needed the move relative to the implied move has failed here (move, skew and
kurtosis gates; the ML ratio predictor; the 375-model zoo; trials 1,616 to 1,622). A model that
adds non-price information to the implied move is equivalent to a forecast of the move relative
to the implied move, so Part A is the direct test of whether such information exists.

**Part B, sizing.** Sizing does not need to beat the market's forecast: a short straddle's loss
scales with the move, and the implied move already forecasts the move, so sizing inversely to it
should equalise risk across events and reduce the weight of the few events that decide the book.
The live book trades a fixed 5 contracts, which puts more risk on high-priced and high-volatility
names. The hypothesis is that risk-equalised sizing raises the per-date Sharpe ratio and lowers
the drawdown relative to fixed contracts, without selecting events.

Trials: Part A is trial 1,623; Part B compares five schemes against fixed contracts, trials 1,624
to 1,628.

## Data and blocks

- Events: `outputs/research/2026-11-02-hedged-event-hold/events.parquet` (status `ok`) and
  `events_confirm_2025_26.parquet` (status `ok`), forward `front_fwd` and permno from
  `outputs/research/2026-10-20-hedged-hold/features.parquet` on ticker and entry date. The
  2025-26 events carry no permno; each takes its ticker's latest permno from earlier events, and
  the funnel reports how many are mapped.
- Characteristics: `~/FIAM_Hackathon_2026/temp/chars_final_with_names.parquet`, latest month-end
  strictly before entry and at most 62 days old, cross-sectional percentiles within month where
  stated.
- Implied move `im = mid0 / F0`. Realised `abs_move` = |reaction-day close / F0 - 1|.
- **Return per event, measured basis (primary):** `r = (mid0 (1 - 0.012714) - X (1 + 0.030182) -
  4 fee) / m0`, `X` the exit mid where two-sided and the exit ask otherwise (never dropped: the
  events without an exit bid follow large moves), fee 0.0065 per share per leg (0.65 per contract),
  `m0` the margin per share. The 1.2714% entry and 3.0182% exit costs are the measured 15:59 basis
  in the state of record. **Touch basis (robustness):** `B`, sell at bid, buy back at ask.
- Part A evaluation: walk-forward out of sample, 2016-2024 pooled (primary) and 2025-26
  (confirmation). Part B blocks: 2016-2020, 2021-2024, 2025-26, and 2016-2024 pooled.
- Outcomes viewed before: tail rates and money gaps under trials 1,616 to 1,622 today, the
  megacap option-feature AUCs today, and the hedged-hold aggregates of earlier studies. No sizing
  scheme and no move-size regression has been run on this panel.

## Part A specification

- Target `y = log(max(abs_move, 0.001))`.
- **M0:** OLS of `y` on a constant and `log(im)`.
- **M1:** M0 plus, all causal at the entry date:
  - `hist_move`: mean of `y` over the name's last eight panel events with exit before entry (at
    least four);
  - `hist_ratio`: mean of `y - log(im)` over the same events;
  - `jump_share`: `jsplit_jump_var / (front_iv^2 * front_t)`, the share of front variance the
    term structure attributes to the event (where `jsplit_valid`);
  - `log_me` (`log(me)`), `rvol_21d`, `ivol_capm_21d`, `turnover_126d`, `ret_1_0`, `age`, and the
    within-month percentiles of `earnings_variability` and `prc_highprc_252d`.
- Walk-forward by calendar year: for year `Y` from 2016, fit on events with exit date before
  1 January `Y`, predict year `Y`. Both models are fit and scored on the same events (all M1
  inputs defined); the funnel reports the drop.
- **Primary statistic:** mean over events of `(y - yhat_M0)^2 - (y - yhat_M1)^2`, date-clustered
  95% interval (`protocol.date_clustered_ci`, 5,000 draws, seed 0). **Success:** interval wholly
  above zero on 2016-2024 and a positive point estimate on 2025-26.
- Secondary: out-of-sample R^2 of both models; the M0 slope on `log(im)` from the last fit; QLIKE
  loss on squared moves (`m^2/h - log(m^2/h) - 1`, `h = exp(2 yhat)`, moves floored at 0.001),
  which ranks variance forecasts robustly to a noisy proxy (Patton, J. Econometrics 2011).

## Part B specification

Contracts per event `n`, dollar P&L `n * 100 * m0 * r`. Schemes, each defined up to a constant
(every statistic below is scale-free):

- **S1, fixed contracts:** `n = 1`. The live rule.
- **S2, equal margin:** `n proportional to 1 / m0`.
- **S3, equal premium:** `n proportional to 1 / mid0`, risk parity on the implied move.
- **S4, forecast risk parity:** `n proportional to 1 / (F0 * exp(yhat))`, `yhat` from M1 where
  all inputs are defined, else from M0; the funnel reports the share on each.
- **S5, equal margin, fixed daily budget:** S2 weights divided by the number of events entering
  that date.
- **S6, equal premium, fixed daily budget:** S3 weights divided by the number of events entering
  that date.

Weights use only entry-time quantities. The P&L series is the sum over events by entry date.

- **Primary statistic:** per-date Sharpe ratio (mean over sd of per-date P&L, not annualised),
  each scheme minus S1, paired date-clustered bootstrap (dates resampled jointly for both series,
  5,000 draws, seed 0). **Success for a scheme:** pooled 2016-2024 interval wholly above zero and a
  positive point estimate in each of 2016-2020, 2021-2024 and 2025-26.
- Secondary, scale-free: maximum drawdown of cumulative P&L in units of the per-date sd; worst
  date in sd units; expected shortfall of the worst 1% of dates in sd units; the share of total
  absolute loss carried by the worst 1% of events. Annualised Sharpe reported only beside the
  per-date figure, scaled by the square root of the block's own event dates per year.
- All of Part B on the measured basis, repeated on the touch basis.

## Trial accounting

Six trials, numbers 1,623 to 1,628. Next free number after this record: 1,629.
