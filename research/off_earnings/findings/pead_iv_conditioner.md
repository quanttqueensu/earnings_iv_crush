# Can option-implied earnings measures sharpen PEAD?

Answer: **no, and not for the reason the idea would fail on its merits.** The option data
and the drift live in disjoint parts of the universe, so the test can never be run on the
sample that matters.

Three constructions were pre-declared in `scripts/research_pead_iv_conditioners.py` before
any was scored. All three were run. All three are negative.

## Setup

Merged the full PEAD firm-quarter panel (198,774 rows, IBES surprise plus CRSP) against the
three validated option event tables via a date-aware CRSP `dsenames` permno-to-ticker
crosswalk. Result: **1,791 firm-quarters, 311 names, 2019-2024**, of which 1,738 have a
usable 60-day forward CAR.

Causality holds. The option leg's `exit_date` equals PEAD `day0` for 1,770 of 1,791 events
and the position is entered at `day0+1`, so every conditioner is observable before entry.

## Result

Spread is the top-minus-bottom tercile mean 60-day market-adjusted return. Breakpoints are
set within the announcement quarter. CI is a quarter-clustered bootstrap over 24 clusters.

| Signal | N | Spread | t | 95% CI | Per-trade Sharpe |
|---|---|---|---|---|---|
| **Baseline** `sue_sigma` | 1,738 | -0.0015 | -0.23 | [-0.0178, +0.0125] | -0.007 |
| **C1** `sue_iv` | 1,738 | -0.0101 | -1.46 | [-0.0280, +0.0041] | -0.043 |
| **C2** `crush_resid` | 1,738 | +0.0099 | +1.38 | [+0.0001, +0.0205] | +0.040 |
| **C3** `move_ratio` | 1,738 | +0.0084 | +1.19 | [-0.0113, +0.0224] | +0.034 |

C2's interval technically excludes zero at +0.0001. That is not a result. Its t is 1.38,
and against the three trials run here a Bonferroni-corrected threshold needs p below
0.0167 where C2 gives roughly 0.17. Treat it as noise.

## The baseline failed, so the test was void

`sue_sigma` is the frozen PEAD primary, worth +0.545 net calendar Sharpe on the full
holdout. In this subsample it returns -0.0015 with t = -0.23. **There is no drift here to
condition.**

That has two possible causes with opposite conclusions, so it was checked rather than
assumed (`scripts/validate_pead_car_harness.py`). The same harness, same window, run over
the full CRSP universe:

| Sample | N | Spread | t | p |
|---|---|---|---|---|
| Full universe | 11,944 | +0.0143 | +2.98 | 0.0029 |
| Option-covered names | 1,861 | -0.0014 | -0.20 | 0.84 |
| Non-option-covered | 10,083 | +0.0157 | +2.84 | 0.0045 |

The harness reproduces PEAD where PEAD lives. The null in the option names is the finding,
not a bug.

## It is size, not option attention

The tempting story is that option-market attention arbitrages the drift away, which
Govindaraj, Liu and Livnat report. That story is **not identifiable here**
(`scripts/research_pead_size_vs_options.py`, 23,889 events):

| Size quintile | With options | Without options |
|---|---|---|
| 1 (smallest) | n=1 | n=4,786, +2.00%, t=+1.86 |
| 2 | n=2 | n=4,768, +2.49%, t=+2.89 |
| 3 | n=4 | n=4,769, -0.76%, t=-1.02 |
| 4 | n=362, +3.47%, t=+1.55 | n=4,396, +1.52%, t=+2.38 |
| 5 (largest) | n=3,282, -0.36%, t=-0.70 | n=1,500, +0.64%, t=+0.70 |

Option coverage is effectively absent below the fourth quintile. In the one quintile where
both groups have samples, neither spread is significant and neither is their difference.
There is no variation with which to separate option attention from market cap, and size is
both the simpler explanation and the documented one.

## What is actually tradeable

PEAD in this window is a small and mid-cap effect, and costs do not eat it:

| Size quintile | Median quoted spread | Gross 60-day spread | Net |
|---|---|---|---|
| 1 | 18 bps | +200 bps | **+182 bps** |
| 2 | 10 bps | +249 bps | **+239 bps** |
| 3 | 6 bps | -76 bps | -82 bps |
| 4 | 4 bps | +152 bps | **+148 bps** |
| 5 | 3 bps | -36 bps | -39 bps |

Not monotonic across quintiles, and quintile 3 is negative, so this is noisy rather than
clean. But the two smallest quintiles clear their costs by an order of magnitude.

## Consequence for the book

The PEAD sleeve must trade small and mid caps. The short-straddle sleeve can only trade
large, liquid, heavily-optioned names. **The two sleeves are structurally disjoint.** That
is genuine diversification, and it also means option-implied measures can never inform the
PEAD sleeve, because the option data does not exist for the names PEAD needs.

That closes the question rather than leaving it open. No amount of additional option data
fixes it; the constraint is that listed options concentrate in exactly the names where the
drift has been arbitraged away or never existed.

## Trial accounting

This run adds **three trials** to the PEAD programme's existing 16, taking it to 19. None
produced a result, so nothing is claimed and no deflated Sharpe is quoted. The cost is that
any future positive on this programme is deflated against 19 trials rather than 16.

## Caveats

- The merged sample is 57% concentrated in 2024, because the broad option tables are
  2024-weighted while the megacap table spans 2019-2024.
- 24 quarterly clusters is thin for cluster-robust inference.
- Full-universe tests are on random samples of 12,000 and 24,000 events for tractability,
  not the full 45,211 firm-quarters in the window.
- The 2019-2024 window is a subsample of the PEAD holdout, which runs 2012-2024. The
  earlier full-holdout result remains the stronger evidence on PEAD itself.
