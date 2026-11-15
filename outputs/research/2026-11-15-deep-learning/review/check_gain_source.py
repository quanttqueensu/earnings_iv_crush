"""
check_gain_source.py
Reviewer scratch check, EXPLORATORY (2019-24 was viewed before; chosen after the lanes' reads).
1. Gain over L4 by year x tenor tercile for D1 primary, D1 no-surface twin and D2 primary, from
   the stored per-event files.
2. L4 burn-in and scale: settled count, predictive df and scale dispersion by year.
3. A causal recalibration of L4 itself: at each quarter start Q, one scale factor per tenor
   tercile (cut points and factors fitted by maximum log score on events expiring before Q,
   using L4's own stored prior predictives), applied to L4's predictive on events entered in
   that quarter. Same quarterly batch schedule as the networks. Log score in H_net space with
   the Jacobian, via online_bayes.mixture_predictive; reproduces m_log_score at factor 1.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
import pandas as pd

from earnings_iv_crush.config import ONLINE_BAYES_L4_MODEL as CFG
from earnings_iv_crush.research import online_bayes as ob
from earnings_iv_crush.research.protocol import date_clustered_ci

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
K = ["ticker", "entry_date"]


def rd(p):
    d = pd.read_parquet(p)
    d["entry_date"] = pd.to_datetime(d["entry_date"]).dt.normalize()
    return d


t = rd(BASE / "D0-surface/targets.parquet")
t["expiry"] = pd.to_datetime(t["expiry"]).dt.normalize()
li = rd(BASE / "D0-surface/l4_inputs.parquet")
ls = rd(BASE / "D0-surface/l4_scores.parquet")
ev = t.merge(li.drop(columns=["expiry", "announce_date", "block"]), on=K, suffixes=("", "_li")).merge(
    ls[K + ["m_log_score", "b_log_score"]], on=K)
ev["dte"] = (ev["expiry"] - ev["entry_date"]).dt.days
ev["ltenor"] = np.log1p(ev["dte"])
ev["y"] = 100 * ev["H_net"]
ev["year"] = ev["entry_date"].dt.year
ok = ev["target_ok"].astype(bool) & ev["m_scored"].astype(bool) & np.isfinite(ev["m_log_score"])
x = np.where(np.isfinite(ev["y"]), -ev["y"] / ev["U_pct"], 0.0)
ev["z"] = np.where(ok, ob.yj(x, 0.0), np.nan)
ev["jac"] = np.where(ok, ob.yj_logderiv(x, 0.0) - np.log(ev["U_pct"]), np.nan)


def l4_ls(rows, c):
    r = ev.loc[rows]
    mp = ob.mixture_predictive(r["z"].to_numpy(), r["m_pred_loc"].to_numpy(), r["m_pred_q"].to_numpy(),
                               r["v"].to_numpy(), r["m_pred_s2"].to_numpy() * c ** 2,
                               r["m_pred_df"].to_numpy(), CFG)
    return mp["log_score"] + r["jac"].to_numpy()


out: dict = {"label": "EXPLORATORY reviewer check, after the lanes' held-out reads"}
chk = l4_ls(ev.index[ok], np.ones(ok.sum()))
out["recompute_L4_logscore_maxabs"] = float(np.nanmax(np.abs(chk - ev.loc[ok, "m_log_score"])))

held = ev[(ev["block"] == "2019-24") & ok].assign(evi=lambda d: d.index)
out["L4_by_year"] = {
    int(y): {"n_settled_min": int(g["m_n_settled_at_entry"].min()), "pred_df_median": round(float(g["m_pred_df"].median()), 1),
             "scale_median": round(float(g["m_pred_scale"].median()), 4),
             "scale_sd_over_mean": round(float(g["m_pred_scale"].std() / g["m_pred_scale"].mean()), 4)}
    for y, g in held.groupby("year")}

# ── 1. gain by year x tenor tercile ──
cut = np.quantile(held["ltenor"], [1 / 3, 2 / 3])
held = held.assign(terc=np.digitize(held["ltenor"], cut))
out["tenor_tercile_dte_cuts_days"] = [round(float(np.expm1(c)), 1) for c in cut]
files = {"D1_primary": (BASE / "D1-surface-net/heldout/cards_primary_2019-24.parquet", "log_score"),
         "D1_twin": (BASE / "D1-surface-net/heldout/cards_control_primary_2019-24.parquet", "log_score"),
         "D2_primary": (BASE / "D2-tabular/heldout_2019-24_events.parquet", "d2_log_score")}
gains = {}
for nm, (p, col) in files.items():
    d = rd(p)[K + [col]].rename(columns={col: nm})
    held = held.merge(d, on=K, how="left")
    gains[nm] = held[nm] - held["m_log_score"]


def tab(g):
    return {f"{int(y)}": [round(float(g[(held.year == y) & (held.terc == k)].mean()), 3) for k in range(3)]
            for y in sorted(held.year.unique())}


# ── 3. causal recalibration of L4 by tenor tercile, quarterly ──
grid = np.exp(np.linspace(-0.8, 0.8, 161))
recal = pd.Series(np.nan, index=held.index)
fac_log = {}
for q in pd.date_range("2019-01-01", "2025-01-01", freq="QS")[:-1]:
    tr = ev.index[ok & (ev["expiry"] < q)]
    sc = held.index[(held["entry_date"] >= q) & (held["entry_date"] < q + pd.offsets.QuarterBegin(startingMonth=1))]
    cq = np.quantile(ev.loc[tr, "ltenor"], [1 / 3, 2 / 3])
    ttr = np.digitize(ev.loc[tr, "ltenor"], cq)
    tsc = np.digitize(held.loc[sc, "ltenor"], cq)
    facs = []
    for k in range(3):
        rows = tr[ttr == k]
        res = minimize_scalar(lambda lc: -np.mean(l4_ls(rows, np.full(rows.size, np.exp(lc)))),
                              bounds=(-0.8, 0.8), method="bounded", options={"xatol": 1e-3})
        best = float(np.exp(res.x))
        facs.append(round(float(best), 3))
        srows = sc[tsc == k]
        recal.loc[srows] = l4_ls(held.loc[srows, "evi"].to_numpy(), np.full(srows.size, best))
    fac_log[str(q.date())] = facs
gains["L4_recalibrated_by_tenor"] = recal - held["m_log_score"]
out["recal_factors_by_quarter_short_mid_long"] = {k: fac_log[k] for k in list(fac_log)[::4]}

cl = held["announce_date"].to_numpy()
for nm, g in gains.items():
    c = date_clustered_ci(g.to_numpy(), cl, np.mean)
    out[nm] = {"gain_vs_L4": [round(c.point, 4), round(c.low, 4), round(c.high, 4), c.n],
               "by_tercile": [round(float(g[held.terc == k].mean()), 4) for k in range(3)],
               "year_x_tercile": tab(g)}
for nm in files:
    d = (held[nm] - recal).to_numpy()
    c = date_clustered_ci(d, cl, np.mean)
    out[f"{nm}_minus_L4_recalibrated"] = [round(c.point, 4), round(c.low, 4), round(c.high, 4)]
    out[f"{nm}_minus_L4_recalibrated_by_year"] = {int(y): round(float(d[held.year.to_numpy() == y].mean()), 4) for y in sorted(held.year.unique())}
print(json.dumps(out, indent=1))
(HERE / "check_gain_source.json").write_text(json.dumps(out, indent=1) + "\n")
