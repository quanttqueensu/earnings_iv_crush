# Freeze note: lane C held-out reads (2026-11-13)

Written before any lane C outcome on the held-out block (entry dates 2019-2024) was computed. The
scripts named below are frozen as they stand; the held-out read runs once, with no change to code,
features, thresholds or statistics.

## Candidate 1: trial 1,855, predictability of the post-reaction diffusive part

- Hypothesis: the causal top tercile of a walk-forward forecast of D_net earns a larger realised
  diffusive part than the bottom tercile.
- Mechanism, stated in advance: the premium left after the reaction is set by the held option's
  own state at the reaction close (implied volatility level, distance from the strike, sessions
  left). Round 2 (trial 1,847) showed a HAR forecast adds nothing once implied volatility is fixed,
  so the claim is about where the premium sits, not about forecasting realised volatility.
- Provenance: discovery-derived. The model's feature list was fixed in round 3 (trial 1,851) after
  rounds 1 and 2 had been read on discovery.
- Model: OLS of D_net on a constant, post-event IV (vol points), HAR ex-event forecast (vol
  points), gap over entry implied move, log sessions left and absolute log moneyness, refitted each
  January on events whose expiry precedes that January (`round3.walk_forward_pred`). Terciles are
  causal over the chronological panel, 200 prior events minimum.
- Statistic: top minus bottom tercile mean D_net, per trade, fraction of m0, at the reaction-close
  mid net of equity costs; date-clustered 95% interval on the reaction session; matched random
  null on the top tercile's mean D_net. Script: `r5_predictability.py --block heldout`.
- Pass: t >= 3, interval above zero, null percentile >= 95. Discovery read: +1.02% [+0.39, +1.60],
  N=1,823, t 3.32, null percentile 100.
- What a pass would and would not mean: it says the diffusive premium is predictable per event. It
  is not a trade: in discovery every tercile has a positive hold gain, so the hold is kept in every
  tercile and no book changes.

## Candidate 2: trial 1,851, forecast hold-or-close against always holding

- Hypothesis: closing at the reaction close where forecast D_net plus the exit half-spread plus the
  saved fees is below zero beats always holding.
- Mechanism: as above, with the closing cost known at the decision used as the threshold.
- Provenance: discovery-derived (round 3).
- Statistic: mean paired difference rule book minus always-hold, per trade, fraction of m0, net at
  the touch; matched random null on the closed events' B - H. Script: `r6_holdout_1851.py`.
- Pass: interval above zero, t >= 3, null percentile >= 95. Discovery read: -0.018% [-0.050,
  +0.016], N=2,029, null percentile 100 (selection of low-gain events is real but the closed
  events still have a positive hold gain, +0.19%). Expected outcome: fail. It is taken to the
  held-out block because it is the strongest honest version of the lane's monetisation question.

## Universe and attrition, both candidates

Lane-ok events: front contract status ok in the 2026-11-02 hedged event hold (broad and megacap),
one or more hedging sessions left, a two-sided reaction-close quote, and a bracketed straddle IV
at the reaction close. Events with a one-sided reaction quote are held under every rule (no IV
exists to decide on). The build funnel is printed by `build_panel.py`.
