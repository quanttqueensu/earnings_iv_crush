# Lane 2: per-trade forensics (unfinished)

Compiled by the team lead from this folder's logs after the lane hit the usage limit. The lane
did not reach a held-out read, so every result here is a discovery screen and exploratory. All
numbers are copied from `trials.csv`, `round1.log` to `round3.log` and `levels.log`.

## Data and basis

Ledger `ledger_all.parquet`: 7,753 events 2013-24 (funnel in `build_ledger.log`); discovery
loads 4,969. Case files for individual events are in `case_files.csv`. Effect (`delta_prem`) is
flagged minus unflagged net buy-back P&L at the touch, per unit of premium, per trade, within
matched cells, with date-clustered 95% intervals. The `delta_margin` column gives the same on
margin. A rule "passes discovery" here when its interval excludes zero in either direction, so a
negative pass is a rule for avoiding trades.

## What the levels say (descriptive, discovery)

The whole discovery book loses 16.1% of premium per trade net at the touch (N=4,759) while
earning +10.8% gross at the mid where the exit is two-sided (N=3,531). Every group earns at the
mid; what separates them is the spread paid.

| Group | N | Net at touch, per premium | Gross at mid | Quoted spread |
|---|---|---|---|---|
| Tightest quote quintile | 799 | -0.022 | +0.135 | 0.033 |
| Liquid top quintile | 822 | -0.091 | +0.125 | 0.057 |
| All | 4,759 | -0.161 | +0.108 | 0.099 |
| Small cap | 697 | -0.225 | +0.091 | 0.114 |
| Wide quote quintile | 1,145 | -0.346 | +0.096 | 0.240 |

## Discovery screens that cleared

| Trial | Rule | Flagged | Effect | 95% CI | t | Null pct |
|---|---|---|---|---|---|---|
| 1,661 | Wide entry quote, top quintile (the closed spread gate, reference) | 1,145 | -0.240 | [-0.276, -0.201] | -12.78 | 0.0 |
| 1,660 | Small cap, below the 90th percentile of market equity | 697 | -0.114 | [-0.165, -0.065] | -4.39 | 0.0 |
| 1,674 | Liquid name, dollar volume top quintile | 822 | +0.113 | [+0.052, +0.174] | 3.62 | 100.0 |
| 1,679 | Small cap outside the wide-quote quintile | 502 | -0.107 | [-0.168, -0.045] | -3.44 | 0.0 |
| 1,677 | Cheap premium: implied move at most 0.90x its own last-8 median | 1,374 | -0.066 | [-0.112, -0.016] | -2.66 | 0.5 |
| 1,663 | Late report, 5 or more days after the same quarter last year | 1,084 | -0.050 | [-0.091, -0.010] | -2.43 | 0.5 |
| 1,659 | Cheap premium at 0.85x | 1,009 | -0.062 | [-0.111, -0.008] | -2.34 | 1.1 |
| 1,680 | Health-care sector | 400 | -0.068 | [-0.134, -0.003] | -1.99 | 2.1 |

Only the liquidity and size rules reach |t| >= 3, and they measure the same thing as the closed
spread gate: within each group the gross-at-mid result is similar, the cost is not. Cheap
premium and late reporting both lose their significance once the wide-quote quintile is removed
(trials 1,670 and 1,678: t -1.25 and -1.53), so they are also largely spread effects.

## Failed rules

Continuous peer shock (+0.009); fiscal Q4 (+0.013); amended 10-K or 10-Q in the prior year
(-0.067, t -1.27); 52-week extreme (+0.025); session switched against habit (-0.076, t -1.74,
211 flagged); merger filing in the prior 180 days (-0.046); unusual weekday (+0.035); rich
premium at 1.20x own median (+0.034, t 1.68, null 98.0); cheap premium in a stressed tape
(-0.029); premium fell since the last report (-0.036); cheap premium with no peer reported
(+0.003); implied move at most 0.45x the largest of the last eight reactions (-0.002).

## Not done

No held-out read and no frozen candidate. The natural one is the liquidity rule (trial 1,674),
but it would first need to show it adds anything over the closed spread gate, judged at each
event's own touch.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt\lane2-forensics\report.md
