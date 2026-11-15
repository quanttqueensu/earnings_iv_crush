# Pre-registration: fade reaction-day gaps that exceed the option-implied move

Frozen before any outcome on the test set is computed. Record:
`outputs/research/prereg_2026-11-02-implied-move-gap-fade.json`. Scorer:
`research/timing/2026-11-02-implied-move-gap-fade/study.py`.

## Hypothesis

On the reaction session the overnight earnings gap partly reverses by the close (Berkman, Koch,
Tuttle and Zhang, JFQA 2012, attention-driven buying at the open; stream 3 of this session found the
same reversal in the short straddle's hedge on the broad events, larger in the top gap tercile and
about five times larger in 2025-26). The day before, the options price the expected size of the
reaction: the implied move. A gap larger than the implied move is a reaction beyond what the
marginal option seller expected, the candidate for overreaction. Hypothesis: fading only gaps with
`|gap| > implied move`, from the reaction open to the reaction close, earns a positive mean net of
costs. Fading every gap in stock alone netted about zero over 2013-24 on the broad events (stream 3,
descriptive), so the claim is specific to the implied-move condition.

Closest prior work: Berkman et al. 2012; Liu, Hope and Hu (JCF 2023) on earnings-day intraday
reversal; PEAD (Bernard and Thomas 1989) predicts continuation over days, the opposite sign over a
longer horizon. Closed rows: P1 put skew and the parity premium predict the reaction (no), PEAD on
SUE (not established). None conditions an intraday fade on the option-implied move.

## Test set (unseen)

Every event of `outputs/research/ml_zoo/events_full.parquet` not in the hedged event hold's `ok`
sets (2013-24 and 2025-26), because stream 3 observed the reaction-day path of those. That leaves
1,907 events (1,794 megacap, 113 other), 2013-26, 130 names.

## Data

- Prices: Yahoo Finance daily bars (`auto_adjust=False`): entry-session Close `C0`, reaction-session
  Open `O1` and Close `C1`, all on the same adjustment basis so ratios are as traded. Reaction
  session = `exit_date`. Missing name or session drops the event, counted. Market: SPY Open and Close.
- Implied move: `implied_move` in the events file (the 15:59 front ATM straddle over spot).

## Trade

- `gap = O1 / C0 - 1`. Selected if `|gap| > implied_move`.
- Position `-sign(gap)` at the reaction open, closed at the reaction close.
- Net return per trade (fraction of notional): `-sign(gap) x (C1 / O1 - 1) - 10 bp` (5 bp opening
  auction, 3 bp closing auction, 2 bp commission and fees, round trip).

## Statistics (date-clustered by reaction date, 5,000 draws, seed 0)

- Primary: mean net return per trade on the selected events, with its interval; per-trade Sharpe.
- Splits by reaction year 2013-18, 2019-24, 2025-26 (sign check).

## Criterion

PASS if the pooled mean net is > 0 with its interval excluding zero, the per-trade Sharpe is > 0,
and the point mean is > 0 in at least two of the three splits. Otherwise FAIL.

## Secondary (descriptive)

Unconditional fade on the test set; `|gap| > 2 x implied_move`; SPY-adjusted return
(`-sign(gap) x [(C1/O1 - 1) - (SPY C1/O1 - 1)]`); gap-up against gap-down; the same selected rule on
the stream-3 events labelled in-sample; selected count and funnel.

## Trial accounting

One trial: 1,561 + 1 = 1,562.
