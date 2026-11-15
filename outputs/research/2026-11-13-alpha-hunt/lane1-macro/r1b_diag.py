"""r1b_diag.py: per-event diagnostics after round 1 (discovery 2013-18 only, descriptive)."""
import numpy as np, pandas as pd
import lib
pd.set_option("display.width", 220)
d = lib.load(lib.DISCOVERY)
d["hi_vix"] = d.vix_pct_lag >= 2/3
d["fri"] = d.exit_date.dt.weekday == 4
d["idio"] = (d.stk_ret - d.beta * d.spy_ret).abs() / d.implied_move
d["mkt"] = (d.beta * d.spy_ret).abs() / d.implied_move
d["yr"] = d.entry_date.dt.year
print("VIX level threshold check: vix_lag range in treated", d[d.hi_vix].vix_lag.describe()[["min","50%","max"]].to_dict(), "untreated", d[~d.hi_vix].vix_lag.describe()[["min","50%","max"]].to_dict())
print("\nhi_vix by year: n, yB mean")
print(d.groupby(["yr","hi_vix"]).agg(n=("yB","size"), yB=("yB","mean"), yBmid=("yBmid","mean"), ratio=("move_ratio","mean"), idio=("idio","mean"), mkt=("mkt","mean"), im=("implied_move","mean"), dates=("entry_date","nunique")).to_string())
print("\nVIX expanding-percentile quintile bins (all bins):")
d["vq"] = pd.cut(d.vix_pct_lag, [0,.2,.4,.6,.8,1.0001], labels=False, include_lowest=True)
print(d.groupby("vq").agg(n=("yB","size"), dates=("entry_date","nunique"), vix=("vix_lag","mean"), yB=("yB","mean"), yBmid=("yBmid","mean"), yH=("yH","mean"), ratio=("move_ratio","mean"), idio=("idio","mean"), mkt=("mkt","mean"), im=("implied_move","mean"), fiv=("front_iv","mean")).to_string())
# episodes: contiguous runs of hi_vix dates
dates = d.groupby("entry_date").hi_vix.first()
ep = (dates != dates.shift()).cumsum()[dates]
g = d[d.hi_vix].assign(ep=d[d.hi_vix].entry_date.map(ep))
e = g.groupby("ep").agg(start=("entry_date","min"), end=("entry_date","max"), n=("yB","size"), yB=("yB","mean"))
print("\nhigh-VIX episodes with >=20 events:\n", e[e.n>=20].to_string(), "\n episodes total", len(e))
# quarter-level: within-quarter contrast
d["q"] = d.entry_date.dt.to_period("Q").astype(str)
w = d.groupby(["q","hi_vix"]).yB.agg(["mean","size"]).unstack()
w = w[(w[("size",True)]>=15)&(w[("size",False)]>=15)]
print("\nquarters holding both states (>=15 each): diff hi-lo yB\n", (w[("mean",True)]-w[("mean",False)]).round(3).to_string())
print("\nFriday: by tenor cell and year")
print(d.groupby(["tenor","fri"]).agg(n=("yB","size"), yB=("yB","mean"), yBmid=("yBmid","mean"), yH=("yH","mean"), ratio=("move_ratio","mean"), im=("implied_move","mean"), amc=("is_amc","mean"), mcap=("log_mcap","mean")).to_string())
print(d.groupby(["yr","fri"]).agg(n=("yB","size"), yB=("yB","mean"), ratio=("move_ratio","mean")).unstack().to_string())
print(d.groupby(d.exit_date.dt.weekday).agg(n=("yB","size"), yB=("yB","mean"), yBmid=("yBmid","mean"), yH=("yH","mean"), ratio=("move_ratio","mean"), absmove=("abs_move","mean"), im=("implied_move","mean"), dte=("dte_exit","mean")).to_string())
print(d.groupby([d.exit_date.dt.weekday, "dte_exit"]).agg(n=("yB","size"), yB=("yB","mean"), ratio=("move_ratio","mean")).query("n>=40").to_string())
