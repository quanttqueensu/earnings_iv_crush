# Pre-registration: large-gap continuation in the most liquid names

Frozen before any size-conditional outcome is computed. Record:
`outputs/research/prereg_2026-11-02-gap-continuation-size.json`. Scorer:
`research/timing/2026-11-02-gap-continuation-size/study.py`.

## Where the hypothesis comes from (disclosed)

The implied-move gap fade (prereg 17823c9b) failed with the opposite sign on its unseen set, which is
94% megacaps: fading gaps larger than the implied move lost -0.53% net per trade [-0.81%, -0.26%],
N=364, negative in both 2013-18 and 2019-24. On the broad events (seen by stream 3, in aggregate) the
same fade was +0.23% [-0.00%, +0.47%], N=1,150. The pattern suggests size or liquidity decides the
sign: large, liquid names keep moving in the direction of an outsized gap through the session
(institutional order splitting after a surprise; intraday momentum, Gao, Han, Li and Zhou, JFE 2018),
while small names reverse attention-driven opening demand (Berkman et al. 2012). The megacap set is
now spent; this study tests the size mechanism on the broad events, where the reaction path was
observed only pooled across sizes, never split by size.

## Hypothesis

Among broad events with `|gap| > implied move`, those in the top causal quintile of prior dollar
volume earn a positive mean net when following the gap from the reaction open to the reaction close.

## Data

- Events: broad events of `outputs/research/ml_zoo/events_full.parquet` in the hedged event hold's
  `ok` sets (2013-26), as used in the gap-fade study's in-sample comparison.
- Prices and volume: Yahoo daily bars (`auto_adjust=False`); `gap = O1 / C0 - 1`; open-to-close
  `C1 / O1 - 1`. Missing name or session drops the event, counted.
- Liquidity: mean of `Close x Volume` over the 60 sessions ending the session before entry (at least
  50), in USD.
- Quintiles: `hedged_hold.causal_bins` with 5 bins and 200 prior events on the liquidity of all
  broad events with a valid value, breakpoints from strictly earlier reaction dates.

## Trade

Selected: `|gap| > implied_move` and top liquidity quintile. Position `+sign(gap)` at the open,
closed at the close; net `sign(gap) x (C1/O1 - 1) - 10 bp` round trip, as frozen in the gap fade.

## Statistics and criterion

Date-clustered intervals (5,000 draws, seed 0). PASS if the pooled mean net is > 0 with its interval
excluding zero, the per-trade Sharpe is > 0, and the point mean is > 0 in at least two of 2013-18,
2019-24 and 2025-26. Otherwise FAIL. Secondary: every quintile's follow-the-gap mean (the mechanism
predicts it rises with liquidity), the SPY-adjusted version, gap-up against gap-down.

## Trial accounting

One trial: 1,562 + 1 = 1,563.
