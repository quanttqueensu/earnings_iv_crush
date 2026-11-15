# Freeze note: trial 2,805, report session as an entry selector on the hedged hold

Written 2026-11-14, after the discovery read (2013-18) and before any held-out (2019-24) outcome.

Discovery (session_discovery.json, after amendment 01 to the driver check only):
- Primary fails: amc mean residual value +0.0209 of entry premium [-0.0196, +0.0610], N=712
  amc of 2,059 labelled, 291 date clusters; matched random null percentile 89.4 (pass needs 95
  and a lower bound above zero).
- Within-cell amc minus bmo +0.0270 [-0.0317, +0.0842]; night +0.0075, continuation +0.0195
  [-0.010, +0.051]; post-event realised variance relative to entry front variance -0.016
  [-0.061, +0.030]; amc events carry a higher implied move and premium per m0 within cell.

No rule, label treatment, cell, cost or pass threshold changes. The direction was set by the
paper, not by discovery, and the discovery block had been viewed before this trial (lane5
diag1.log), so the held-out 2019-24 block is the only clean read of this feature. It is read
once with the declared rule. Because discovery failed, the trial cannot pass overall; a held-out
pass would justify only a forward paper test, and the result is labelled exploratory either way.

Search count: one configuration (trial 2,805); amendment 01 changed only the driver check.

Held-out block check: block_is_clean(panel hedged_event_hold, period 2019-24, outcome
residual_value, feature report_session) is True with no clashes. Prior view of a related split on
this panel and block: research/timing/2026-11-02-open-hedge, by_amc on the open-hedge 'add'
metric (a different outcome; its numbers not read by this lane).

selector_session.py sha256: 65017aa160239b4bf4ffab5f1dcb4d6fe92bb72b7a7690c7d482430a0205c262
note sha256: 6f9a72361a2c4f0098218b4085ae1c262867e690124d3254b6c1db6dd8c88384
