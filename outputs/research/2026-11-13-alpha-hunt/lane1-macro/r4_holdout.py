"""r4_holdout.py: single held-out read of the two frozen candidates (freeze_2026-11-13.md) on 2019-24."""
import numpy as np, pandas as pd
import lib
d = lib.load(lib.HOLDOUT)
print("held-out N", len(d), "dates", d.entry_date.nunique(), "months", d.entry_date.dt.to_period("M").nunique(), "| mean yB %.4f" % d.yB.mean())
assert d.vix_pct_lag.notna().all() and d.dd_lag.notna().all()
def go(tid, hyp, mech, tr):
    r = lib.score(d, np.asarray(tr, bool), "yB", None, True, n_boot=5000, label=hyp)
    ok = r["ci_low"] > 0 and r["ci_month_low"] > 0 and r["t"] >= 3 and r["null_pct_cell"] >= 95 and r["null_pct_shift"] >= 95
    lib.log_trial(tid, hyp, mech, "held-out 2019-24", r, "PASS held-out" if ok else "FAIL held-out")
    for o in ("yH", "yBmid", "move_ratio"):
        m = d[o].notna().to_numpy()
        print("     secondary Delta %s %+.4f" % (o, lib.delta(d[o].to_numpy(float)[m], np.asarray(tr, bool)[m], d.cell.to_numpy(float)[m])))
    print(d.assign(t=np.asarray(tr, bool)).groupby([d.entry_date.dt.year, "t"]).yB.agg(["mean", "size"]).unstack().round(4).to_string())
    return ok
a = go(1656, "C1 avoid high index vol: prior-close VIX below expanding top tercile", "reverse of H1; mechanism not accepted (see freeze note)", ~(d.vix_pct_lag >= 2/3))
b = go(1657, "C2 no drawdown: SPY within 2% of 250d high at prior close", "lower market variance and vol-of-vol in the overnight move", d.dd_lag >= -0.02)
print("passes:", a, b)
