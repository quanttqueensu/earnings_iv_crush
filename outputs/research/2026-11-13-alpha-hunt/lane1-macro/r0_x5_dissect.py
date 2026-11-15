"""r0_x5_dissect.py: descriptive dissection of the X5 near miss on its own (already viewed) block 2016-18."""
import numpy as np, pandas as pd
import lib
pd.set_option("display.width", 220)
d = lib.load((2016, 2018))
print("N", len(d), d.src.value_counts().to_dict())
for src in ("broad", "all"):
    b = d if src == "all" else d[d.src == "broad"].reset_index(drop=True)
    for out in ("yH", "yB", "yBmid"):
        r = lib.score(b, b.cal_any_exit.to_numpy(), out, n_boot=1000)
        print(src, out, "any release on reaction day:", lib.fmt(r))
b = d
for k in ("fomc", "cpi", "nfp"):
    for out in ("yH", "yB"):
        r = lib.score(b, b[f"cal_{k}_exit"].to_numpy(), out, n_boot=1000)
        print(k, out, lib.fmt(r))
# decomposition: what differs on treated events
g = b.groupby("cal_any_exit")
cols = ["implied_move", "abs_move", "move_ratio", "yB", "yBmid", "yH", "front_iv", "vix_lag", "dte_exit", "is_amc", "beta"]
print(g[cols].mean().T.to_string())
print(g[cols].median().T.to_string())
b = b.assign(abs_spy=b.spy_ret.abs())
print("abs SPY ret on reaction day by treated:", b.groupby("cal_any_exit").abs_spy.mean().to_dict())
print(b.groupby(["cal_fomc_exit","cal_cpi_exit","cal_nfp_exit"])[["abs_spy","move_ratio","yB","yH","implied_move"]].agg(["mean","size"]).to_string())
# is it the AMC / BMO split? BMO announcers on a release day vs AMC
print(b.groupby(["cal_any_exit","is_amc"])[["yB","yH","move_ratio"]].agg(["mean","size"]).to_string())
# per-date table of treated dates
t = b[b.cal_any_exit].groupby("exit_date").agg(n=("yB","size"), yB=("yB","mean"), yH=("yH","mean"), ratio=("move_ratio","mean"), spy=("spy_ret","first"))
print(t.sort_values("yH").to_string())
print("share of treated-sum yH from top 5 dates:", (t.yH*t.n).sort_values().tail(5).sum()/ (t.yH*t.n).sum())
# trimmed / median comparison
for out in ("yH","yB"):
    print(out, "medians treated/untreated", b.groupby("cal_any_exit")[out].median().to_dict(), "p10", b.groupby("cal_any_exit")[out].quantile(0.1).to_dict())
