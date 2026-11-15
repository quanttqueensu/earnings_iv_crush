"""r3_slate.py: round 3, discovery 2013-18."""
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

hv = (d.vix_pct_lag >= T).to_numpy()
sub = d[hv].reset_index(drop=True)
bt = sub.beta >= d.beta.quantile(T)  # descriptive cut inside the block, mechanism check only
run(1652, "H24 mechanism check of reversed H1: inside high-VIX dates, top-tercile beta names against the rest (expect NEGATIVE if market variance carries the high-VIX penalty)",
    "if overnight market variance drives the high-VIX shortfall it concentrates in high-beta names", bt.to_numpy(), sub.beta.notna().to_numpy(), False, "yB", "discovery 2013-18, high-VIX subset", sub)
run(1653, "H25 VIX 20-session log change bottom tercile (index vol compressing)", "single-name event IV is sticky while index vol normalises after stress; seller keeps more", d.vix_chg20_pct_lag <= 1-T)
# H26 implied-correlation proxy: trailing median of single-name back-month IV over VIX across events entered in the prior 20 sessions
g = d.groupby("entry_date").disp_back_ratio.median()
cnt = d.groupby("entry_date").disp_back_ratio.count()
roll = g.rolling(20, min_periods=8).median().shift(1)   # strictly earlier entry dates
pct = roll.expanding(120).rank(pct=True)               # includes current value; current value uses prior dates only
x = d.entry_date.map(pct)
print("H26 funnel: proxy defined on", int(x.notna().sum()), "of", len(d))
run(1654, "H26 implied-correlation proxy high (trailing 20-date median single-name back IV / VIX in bottom tercile)",
    "in a macro-dominated tape firm news moves prices less relative to what the name's options charge", (x <= 1-T).fillna(False).to_numpy(), x.notna().to_numpy(), True)
