"""r1_slate.py: round 1, discovery 2013-18. One pre-stated treatment per hypothesis; primary outcome
yB (next-session buy-back, net at the touch, per unit of entry premium); yH and move_ratio read as
secondary columns of the same trial. Treatment = the set the mechanism predicts the seller keeps MORE."""
import numpy as np, pandas as pd
import lib
d = lib.load(lib.DISCOVERY)
print("discovery N", len(d), "dates", d.entry_date.nunique(), "| mean yB %.4f yH %.4f yBmid %.4f" % (d.yB.mean(), d.yH.mean(), d.yBmid.mean()))
T = 2/3
def causal_event_top(x, q=T):
    """event-level feature: top tercile against strictly earlier entry dates (expanding)."""
    x = np.asarray(x, float); dates = d.entry_date.to_numpy(); out = np.zeros(len(x), bool); ok = np.zeros(len(x), bool)
    order = np.argsort(dates, kind="stable"); xs = x[order]; ds = dates[order]
    for k, i in enumerate(order):
        hi = np.searchsorted(ds, dates[i], side="left"); h = xs[:hi]; h = h[np.isfinite(h)]
        if len(h) >= 200 and np.isfinite(x[i]):
            ok[i] = True; out[i] = x[i] >= np.quantile(h, q)
    return out, ok
SL = [
 (1629, "H1 VIX level top tercile (expanding pct, prior close)", "hedging demand lifts single-name event vol with index vol; seller keeps more", d.vix_pct_lag >= T, None, True),
 (1630, "H2 VIX 5-session log change top tercile", "fear spike overprices event vol", d.vix_chg5_pct_lag >= T, None, True),
 (1631, "H3 VIX9D/VIX bottom tercile (steep near-term contango)", "calm near-term index vol means low overnight market variance in the realised move", d.ts_9d_pct_lag <= 1-T, None, True),
 (1632, "H4 VIX minus SPX 20d realised top tercile", "index vol rich relative to realised carries over to single names", d.vix_minus_rv20_pct_lag >= T, None, True),
 (1634, "H6 Baa-10y spread 20d change bottom tercile (credit tightening)", "credit stress raises jump sizes; calm credit favours the seller", d.baa_chg20_pct_lag <= 1-T, None, True),
 (1635, "H7 abs 5d change in 10y yield bottom tercile (quiet rates)", "rate shocks add market variance to the overnight move", d.abs_dgs10_5_pct_lag <= 1-T, None, True),
 (1636, "H8 no FOMC/CPI/NFP on entry or reaction day and none within 2 sessions after", "macro-heavy windows add uncompensated variance", (d.cal_min_to_next > 2) & ~d.cal_any_entry, None, True),
 (1639, "H11 SPY within 2% of 250d high", "no drawdown: lower market beta variance and vol-of-vol", d.dd_lag >= -0.02, None, True),
 (1640, "H12 VVIX top tercile", "vol-of-vol premium embedded in event options", d.vvix_pct_lag >= T, None, True),
 (1641, "H13 reaction session is a Friday (X5 confound check)", "NFP is always a Friday; weekly expiry that day removes residual time value", d.exit_date.dt.weekday == 4, None, True),
 (1638, "H10 late season (season week >= 6)", "late reporters are smaller and less followed; option market has learned the season", d.seas_week >= 6, None, True),
]
x, ok = causal_event_top(d.disp_iv_ratio)
SL.append((1633, "H5 single-name front IV / VIX top causal tercile", "idiosyncratic richness relative to index vol", x, ok, False))
x, ok = causal_event_top(-d.seas_last10_ratio)
SL.append((1637, "H9 last-10-day realised/implied of reported names bottom causal tercile", "calm season persists; near-duplicate of the closed season-state test, different window and universe", x, ok, False))
rows = []
for tid, hyp, mech, tr, ok, dl in sorted(SL):
    tr = np.asarray(tr, bool)
    r = lib.score(d, tr, "yB", ok, dl, label=hyp)
    sec = {}
    for o in ("yH", "yBmid", "move_ratio"):
        m = d[o].notna().to_numpy() & (ok if ok is not None else True)
        sec[o] = lib.delta(d[o].to_numpy(float)[m], tr[m], d.cell.to_numpy(float)[m])
    passed = r["ci_low"] > 0 and r["null_pct_cell"] >= 95 and (not dl or r["null_pct_shift"] >= 95)
    lib.log_trial(tid, hyp, mech, "discovery 2013-18", r, "pass discovery" if passed else "fail discovery")
    print("     secondary Delta: yH %+.4f  yBmid %+.4f  move_ratio %+.4f" % (sec["yH"], sec["yBmid"], sec["move_ratio"]))
