"""r2_slate.py: round 2, discovery 2013-18 (X5b on 2013-15, which the original X5 never read)."""
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
# H14 expected market share of the overnight move
d["mkt_share"] = d.beta.abs() * d.vix_lag / 100 / np.sqrt(252) / d.implied_move
x, ok = causal_event(d.mkt_share, 1/3, top=False)
run(1642, "H14 expected market share of the move (beta x VIX daily / implied move) bottom causal tercile",
    "the event straddle is priced off the idiosyncratic jump; overnight market variance in the realised move is uncompensated, so low-share events keep more", x, ok, False)
# H15 hedge upper bound: variance of yB removable by an ex-post optimal position in |SPY move| (long index straddle proxy, zero cost)
m = d.yB.notna() & d.spy_ret.notna() & d.beta.notna()
y = d.yB[m].to_numpy(); h = (d.beta.abs() * d.spy_ret.abs() / d.implied_move)[m].to_numpy()
rho = np.corrcoef(y, h)[0, 1]
rng = np.random.default_rng(0); keys = d.entry_date[m].to_numpy(); ud, inv = np.unique(keys, return_inverse=True)
g = [np.flatnonzero(inv == k) for k in range(len(ud))]; bs = []
for _ in range(2000):
    idx = np.concatenate([g[i] for i in rng.integers(0, len(g), len(g))]); bs.append(np.corrcoef(y[idx], h[idx])[0, 1])
lo, hi = np.percentile(bs, [2.5, 97.5])
r = dict(outcome="corr(yB, beta|SPY ret|/implied)", n_scored=int(m.sum()), n_treated=int(m.sum()), n_dates_treated=len(ud),
         n_months_treated=int(d.entry_date[m].dt.to_period("M").nunique()), effect=float(rho), ci_low=float(lo), ci_high=float(hi),
         ci_month_low=float("nan"), ci_month_high=float("nan"), t=float(rho/np.std(bs, ddof=1)), null_pct_cell=float("nan"), null_pct_shift=float("nan"),
         treated_mean=float(y.mean()), untreated_mean=float("nan"))
print("H15 variance removable at most rho^2 = %.4f (zero-cost, in-sample optimal hedge ratio: upper bound)" % rho**2)
hv = (d.vix_pct_lag >= T)[m].to_numpy()
print("   same correlation inside high-VIX tercile: %.4f (N=%d), rho^2 %.4f" % (np.corrcoef(y[hv], h[hv])[0, 1], hv.sum(), np.corrcoef(y[hv], h[hv])[0, 1]**2))
lib.log_trial(1643, "H15 index-straddle hedge: correlation of yB with beta-scaled absolute SPY move on the reaction day (upper bound on variance removed = rho squared)",
              "market beta in the realised move could be hedged with long index gamma", "discovery 2013-18", r,
              "fail discovery (hedge removes under 1% of variance)" if rho**2 < 0.01 else "descriptive: worth pricing")
# H16 X5b on 2013-15
e = d[d.entry_date.dt.year.between(2013, 2015)].reset_index(drop=True)
run(1644, "H16 X5b: CPI or payrolls at 08:30 on the reaction session (FOMC dropped), outcome yH, fresh block 2013-15",
    "X5 on 2016-18 was carried by the 08:30 releases and by the hedged hold, not the overnight leg; replicate on years X5 never read",
    (e.cal_cpi_exit | e.cal_nfp_exit).to_numpy(), None, True, "yH", "discovery 2013-15 (fresh for X5 family)", e)
run("1644b", "H16 same treatment, original X5 definition (any of FOMC, CPI, payrolls), yH, 2013-15", "replication of X5 as frozen, descriptive companion row",
    e.cal_any_exit.to_numpy(), None, True, "yH", "discovery 2013-15 (fresh for X5 family)", e)
# H17 busy reporting day
x, ok = causal_event(d.seas_same_day_n, T)
run(1645, "H17 busy reaction day (same-day reporter count top causal tercile)", "limited attention mutes the immediate reaction on crowded days (Hirshleifer, Lim and Teoh 2009)", x, ok, False)
run(1646, "H18 prior-session absolute SPY return bottom tercile (quiet tape)", "after a large index move dealers mark single-name vol defensively and the overnight tape is volatile", d.abs_spy_ret1_pct_lag <= 1-T)
run(1647, "H19 dollar 20d log change, absolute, bottom tercile", "large dollar moves add translation uncertainty to guidance for multinationals", (d.usd_chg20_lag.abs() <= d.usd_chg20_lag.abs().expanding(200).quantile(1/3).shift(1)).fillna(False))
run(1648, "H20 2s10s slope top tercile (steep curve)", "flat or inverted curve marks late-cycle earnings risk", d.t10y2y_pct_lag >= T)
pre = (d.cal_fomc_to_next >= 1) & (d.cal_fomc_to_next <= 3)
run(1649, "H21 reaction session 1 to 3 sessions before an FOMC decision", "index realised vol is compressed ahead of FOMC; less market variance in the overnight move", pre)
run(1650, "H22 Cboe SKEW top tercile", "index tail-hedging demand spills into single-name event premia", d.skew_pct_lag >= T)
calm = (d.vix_pct_lag < T) & (d.dd_lag >= -0.02)
run(1651, "H23 calm composite: VIX below top tercile and SPY within 2% of 250d high (descended from H1 and H11 on this block)", "market variance in the overnight move is low and unpriced-for in the name", calm)
