# Pre-registration: name-level richness persistence on executable marks

Frozen before the executable-mark run. Every parameter below is **inherited** from the
already-completed move-space study rather than chosen now, so none of them can have been
selected with knowledge of the executable-mark outcome. Nothing in this file may be
changed after the run; a change requires a separate dated amendment file, and both are
reported.

## Hypothesis

A firm carries a persistent firm-specific component in the gap between the risk-neutral
earnings uncertainty priced into its options and the event risk subsequently realised.
Operationally: a name's own prior event richness predicts its next event's richness.

The null is the efficient-markets one, that no pre-event variable observable at entry
predicts the short straddle's return, and in particular that a name's own history does
not.

This is distinct from the term gate, which selects events; this selects **names**.

## What is new relative to the completed study

The completed study measured the payoff in move space as

    ret = 1 - |realised move| / implied move

net of a flat 11.6%-of-premium round trip. That is a proxy, not a traded straddle. It
reported per-trade Sharpe +0.2009 unconditional and +0.3796 for the overlay on 2019-2024,
and +0.1388 / +0.3581 on 2022-2024 out of sample, with all four name-block intervals
excluding zero.

**The only change under test is the payoff measurement.** The signal, the universe, the
thresholds and the inference are all held fixed. The question is whether the result
survives an actual two-leg executable mark.

## Frozen specification

**Signal.** For event *t* of name *i*, `prior_mean` is the causal expanding mean of that
name's own past `ret`, strictly leave-current-out, using only events with an earlier
announce date.

**Inherited parameters, unchanged:**

| Parameter | Value |
|---|---|
| Minimum priors before a name's signal is used | 3 |
| Overlay threshold | top 30% of names by `prior_mean` (quantile 0.70) |
| Winsorisation of the payoff for mean and Sharpe | 1st and 99th percentile |
| Cost, flat arm | 11.6% of premium, round trip |
| Bootstrap draws | 5,000 |
| Seed | 0 |
| Inference | name-block bootstrap, resampling whole names |
| Windows | full 2019-2024, and out-of-sample 2022-2024 with priors from 2019+ |

**Payoff, changed.** The straddle is marked at the entry strike, held fixed, from the
two legs' consolidated quotes at 15:59 exchange-local time on the entry and exit
sessions, through the existing marking path. Return on margin is the reported unit,
alongside return on premium so the two bases are comparable to the completed study.

**Cost arms, both reported, neither preferred after the fact:**

1. Flat 11.6% of premium round trip, matching the completed study.
2. Measured, at 1.7871% per side, asymmetric between entry (1.2714%) and exit (3.0182%),
   from the 34,672-print fixed-time execution study.

## Decision rule, declared in advance

The result is called **positive** only if all four hold:

1. The overlay's per-trade Sharpe exceeds the unconditional book's on **both** windows.
2. The overlay's name-block 95% interval excludes zero on the **2022-2024** window, which
   is the out-of-sample one.
3. Both cost arms satisfy (1) and (2). If the flat arm passes and the measured arm fails,
   the result is **negative** and is reported as cost-bound.
4. The overlay retains its advantage after removing the single largest contributing name.

Anything short of all four is a negative or an inconclusive, reported as such with the
achieved N.

## Declared in advance as non-decisive

The following are reported and are **not** permitted to change the verdict: the
unconditional book's own level, any in-sample-only window, the full 2019-2024 interval on
its own, and the raw move-space figures.

## Known hazards this run inherits

The stale entry spot is unrepaired on 16.9% of priced events and 27.4% of gated ones, and
affects strike selection, marks and sizing. It is not corrected here. If the result is
positive, that correction becomes a precondition for believing it rather than a footnote.

The maximum monthly drawdown on the completed study's overlay is −88% with a worst single
trade of −4.22 in move space. Whatever the Sharpe, the tail is the reason this is not
directly allocable.

## Trial accounting

This is **one** trial on a new payoff basis, not a search. No threshold, window or filter
is varied. If it fails, the correct conclusion is that the completed study's result was a
property of the move-space proxy, and the DSR cost of this run is one trial.
