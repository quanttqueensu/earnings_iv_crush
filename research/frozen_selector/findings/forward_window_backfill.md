# Backfill: short earnings straddle, 2026-07-21 to 2026-08-11

**This is a backtest.** Entry decisions were made after the outcomes were knowable. It
carries none of the inferential weight of a forward book and must never be presented
alongside `outputs/paper/radar_ledger.csv` as one record. The two overlap on the same
events (see below) and summing them would double-count.

Run: `python scripts/backfill_forward_window.py --start 2026-07-21 --end 2026-08-11 --cap 5`
Marks: last OPRA consolidated quote at or before 15:59 ET on the entry session, parent
symbology, `cbbo-1m`. Realised move close to close on split-adjusted bars. Return on
premium `ret = 1 - |realised| / implied`, net of the 11.6%-of-premium round trip.

## Result

| Book | N | Dates | Net mean | Hit | Per-trade Sharpe | Date-clustered 95% CI |
|---|---|---|---|---|---|---|
| Unconditional | 241 | 13 | +0.1795 | 0.714 | +0.2985 | [+0.0908, +0.2759] |
| Rich overlay | 81 | 12 | +0.1998 | 0.741 | +0.3512 | [+0.0875, +0.3195] |

Treating each earnings date as one observation, which is what the common short-volatility
factor makes them: unconditional t = +3.39 (p = 0.0054), rich t = +2.51 (p = 0.0289).
Intra-date correlation gives a design effect that puts the effective N near 107, not 241.

Spend: estimated $0.3322, actual $0.3322. Both below the $1.37 pre-run estimate because
that figure assumed entry and exit chains; only the entry chain is pulled, and 38 were
already cached. Cap $5.00, never approached.

## Why this does not revive the strategy

**Thirteen clusters is too few to trust.** Cluster-robust inference needs roughly 30 to 50
clusters before its asymptotics hold. Below that, cluster bootstrap intervals are too narrow
and over-reject. Both intervals above are therefore optimistic, and the date-level t-tests
rest on 13 and 12 observations respectively.

**The settled verdict rests on 391 events across two disjoint six-year blocks and should
win.** It gives per-trade Sharpe +0.055992 with a clustered CI of [-0.042, +0.180] containing
zero, and DSR 0.0001. Three weeks is under 1% of that evidence base. A favourable window is
exactly what a null of no edge produces some of the time; 11 of these 13 dates were positive,
which is what a calm three weeks looks like, not what a rediscovered edge looks like.

**No tail event occurred.** Hit rate 0.714 against roughly 0.65 historically, dispersion
0.601, worst trade -2.70. The broad historical book's worst single trade is -4.22 and its
monthly drawdown reaches -88%. Short-volatility books read well until the tail arrives, and
the entire risk of this structure sits in a tail these three weeks did not contain.

**Concentration.** The top three dates carry 62.1% of total P&L on 72 of 241 trades.

**Selection.** 20 of 261 events were dropped (12 with no markable ATM straddle, 5 with no
spot, 3 with no chain). If those skew toward wider, less liquid names, the survivors are
mildly favourable. Not quantified here.

**Cost is assumed, not measured, for this universe.** The flat 11.6% of premium comes from
the megacap fills study, where median price improvement was zero and 54% of prints paid the
full touch. Whether it holds for the smaller names in this window is untested. If it is
optimistic here, the edge shrinks proportionally.

**One basis inconsistency, stated rather than hidden.** The entry straddle is marked from a
15:59 ET consolidated quote; the realised move is close to close on daily bars. The two are
about one minute apart and the effect is small, but they are not the same instant.

## A useful by-product: the free marking path is sound

Seven events appear in both this backfill and the live yfinance-marked recorder. On those:

| Measure | Agreement |
|---|---|
| Implied move, correlation | 0.9993 |
| Implied move, mean absolute difference | 0.0008 |
| Net return, difference in means | +0.0043 |

Free yfinance chains reproduce paid OPRA consolidated quotes closely enough to mark this
book. The live recorder does not need metered data, which removes the running cost from the
forward test entirely.

## Disposition

Treat as a favourable window, well measured, that does not change the verdict. Its legitimate
use is as a prior for the live forward test and as validation that the pipeline marks
correctly. It is not evidence that the strategy works, and it must not be presented as a
three-week track record.
