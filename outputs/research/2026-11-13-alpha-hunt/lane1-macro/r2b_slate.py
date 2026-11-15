"""r2b_slate.py: round 2 continued after trial 1648 raised (2s10s top tercile empty on 2013-18: the curve only flattened, one monotone regime, not testable), discovery 2013-18 (X5b on 2013-15, which the original X5 never read)."""
import numpy as np, pandas as pd
import lib
d = lib.load(lib.DISCOVERY)
T = 2/3
def causal_event(x, q, top=True):
    x = np.asarray(x, float); dates = d.entry_date.to_numpy(); out = np.zeros(len(x), bool); ok = np.zeros(len(x), bool)
    order = np.argsort(dates, kind="stable"); xs = x[order]; ds = dates[order]
    for i in range(len(x)):
        hi = np.searchsorted(ds, dates[i], side="left"); h = xs[:hi]; h = h[np.isfinite(h)]
        if len(h) >= 200 and np.isfinite(x[i]):
            ok[i] = True; out[i] = (x[i] >= np.quantile(h, q)) if top else (x[i] <= np.quantile(h, q))
    return out, ok
def run(tid, hyp, mech, tr, ok=None, dl=True, outcome="yB", block="discovery 2013-18", dd=None):
    b = d if dd is None else dd
    tr = np.asarray(tr, bool)
    r = lib.score(b, tr, outcome, ok, dl, label=hyp)
    passed = r["ci_low"] > 0 and r["null_pct_cell"] >= 95 and (not dl or r["null_pct_shift"] >= 95)
    lib.log_trial(tid, hyp, mech, block, r, "pass discovery" if passed else "fail discovery")
    sec = {}
    for o in ("yB", "yH", "yBmid", "move_ratio"):
        m = b[o].notna().to_numpy() & (ok if ok is not None else True)
        sec[o] = lib.delta(b[o].to_numpy(float)[m], tr[m], b.cell.to_numpy(float)[m])
    print("     secondary Delta: " + "  ".join(f"{k} {v:+.4f}" for k, v in sec.items()))
    return r
pre = (d.cal_fomc_to_next >= 1) & (d.cal_fomc_to_next <= 3)
run(1649, "H21 reaction session 1 to 3 sessions before an FOMC decision", "index realised vol is compressed ahead of FOMC; less market variance in the overnight move", pre)
run(1650, "H22 Cboe SKEW top tercile", "index tail-hedging demand spills into single-name event premia", d.skew_pct_lag >= T)
calm = (d.vix_pct_lag < T) & (d.dd_lag >= -0.02)
run(1651, "H23 calm composite: VIX below top tercile and SPY within 2% of 250d high (descended from H1 and H11 on this block)", "market variance in the overnight move is low and unpriced-for in the name", calm)
