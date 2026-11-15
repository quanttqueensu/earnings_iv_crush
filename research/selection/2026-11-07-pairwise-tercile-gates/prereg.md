# Pre-registration: pairwise tercile gates on residual value, three blocks

Frozen before any residual value for these events is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-07-pairwise-tercile-gates.json`. Scorer:
`research/selection/2026-11-07-pairwise-tercile-gates/study.py`.

## Hypothesis

For some pair of entry features, events in the seller-favourable tercile of both carry more residual
value (option value given back by the reaction-session close, net of intrinsic) than a random
selection of the same size, in every block. Mechanism: each feature below has a published or
project-internal reason to mark overpricing on its own; no single one survived, and an
intersection can isolate events where two independent symptoms of overpricing coincide.

## Data and blocks

- Events: the broad universe in `outputs/research/ml_zoo/events_full.parquet` (blocks `broad_hist`,
  `broad`, `broad_2026h2`; megacap excluded because it has no front quote in the hedged-hold
  build), joined on ticker and entry date to the hedged-hold builds
  `outputs/research/2026-11-02-hedged-event-hold/events.parquet` (2013-24) and
  `events_confirm_2025_26.parquet` (2025-26), status `ok`, for strike, front expiry, entry bid
  `s0`, entry mid `mid0` and margin `m0 = 0.20 x forward + s0`.
- Exit marks: the 15:59 reaction-session chains in `data/cache/backfill_chains`, read with the
  hedged-hold study's `exit_quotes` and `exit_fwd`.
- Blocks by announcement year: discovery 2013-2018, validation 2019-2024, confirmation 2025-2026.
  Disclosure: all three blocks have been scored by earlier studies, including the model zoo, which
  used these features in multivariate models; no earlier study scored these pairwise intersections
  on residual value.

## Specification

Features, all computed from 15:59 quotes or from strictly earlier data, with the favourable side
fixed here from the cited reason, not from any outcome:

| Feature | Favourable tercile | Reason |
|---|---|---|
| `implied_over_hist` | top | implied move rich to the name's history (Goyal and Saretto, JFE 2009) |
| `iv_term_spread` | top | event variance concentrated in the front (Dubinsky et al., RFS 2019) |
| `variance_risk_premium` | top | implied over realised variance (Bakshi and Kapadia, RFS 2003) |
| `entry_half_spread` | bottom | `(mid0 - s0) / mid0`; cheap to sell, spread gate in this project |
| `name_prior_ratio` | bottom | the name's own prior realised over implied: persistent overpricing |
| `bkm_kurt` | top | risk-neutral kurtosis priced high (Bakshi, Kapadia and Madan, RFS 2003) |
| `hist_move_dispersion` | bottom | a stable move history anchors the realised distribution |

- Terciles: `earnings_iv_crush.research.hedged_hold.causal_bins` with 3 bins and 200 prior
  events, breakpoints from strictly earlier announcement dates over the full 2013-26 broad
  sequence. An event without a bin for both features of a pair is unscored for that pair.
- Gates: every unordered pair of the seven features, 21 in all. Selected = favourable tercile of
  both.
- Exit mark per leg: `(bid + ask) / 2` when both are positive; `ask / 2` when the bid is zero and
  the ask positive (the project's amendment-01 convention for one-sided legs); undefined when the
  ask is zero or the leg is absent. Exit forward: `exit_fwd`; where it is undefined, put-call
  parity at the position's own strike from the exit marks.
- Residual value, fraction of `m0`: `-(mark_C + mark_P - |F_exit - K|) / m0`. Gross of execution,
  at the mid.
- Attrition: events whose residual value is undefined are counted per block, and their
  `realised_move / implied_move` is compared with the kept events' (date-clustered difference in
  means), so outcome-dependent drops are visible.

## Primary statistic and inference

Per pair and block: mean residual value of the selected events against the participation-matched
random null over the block's scored events (`protocol.matched_random_null`, statistic the mean,
5,000 draws, seed 0), and the selected-minus-unselected difference in mean residual value with a
date-clustered bootstrap interval (5,000 draws, seed 0). Every bin of the three-by-three grid is
written to disk (P5). Secondary, for any pair that passes: the selected events' net return per
trade on `m0` for the buy-back (`B`) and the hedged hold (`H`), mean and per-trade Sharpe with
date-clustered intervals.

## Success criterion

SELECTION SKILL for a pair: matched-null percentile at least 95 in all three blocks, and the
lower bound of the selected-minus-unselected interval above zero in validation and in
confirmation. TRADABLE: SELECTION SKILL and, in confirmation, the selected mean of `H` above zero
with its date-clustered lower bound above zero. Under independence a null pair passes the
selection condition with probability about 0.05 cubed, about 0.0001, so about 0.003 across 21.

## Kill criterion

Any pair short of SELECTION SKILL fails and is closed. If no pair passes, two-feature gates on these
seven 15:59 features are closed as a family. A pass in fewer than three blocks is reported as
FAIL with its block pattern, never as partial support.

## Trial accounting

Twenty-one trials, one per pair. The largest count in the hash records is 1,569
(`prereg_2026-11-07-forward-combined-gates.json`), so these are trials 1,570 to 1,590.
