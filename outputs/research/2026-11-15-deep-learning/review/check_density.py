"""
check_density.py
Reviewer scratch check (development rows only, entry year 2016): for one event, rebuild each
lane's predictive density of H_net (% of m0), integrate it numerically in H space, compare its
value at the realised outcome with the lane's stored log score, and recompute the quadrature
mean by independent integration. Writes nothing into lane folders (block views go to
review/blocks_viewed.csv; run with PYTHONDONTWRITEBYTECODE=1).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pyarrow  # noqa: F401
import pyarrow.parquet  # noqa: F401
import numpy as np
import pandas as pd
from scipy import integrate, stats

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
LOGF = HERE / "blocks_viewed.csv"


def log_view(*a, **k):
    new = not LOGF.exists()
    with LOGF.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["utc", "period", "viewed_by", "kind"])
        w.writerow([pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"), k.get("period", "2013-18"),
                    "review check_density (development rows)", "descriptive"])


# independent Yeo-Johnson, power 0
def z_of_h(h, U):
    x = -np.asarray(h, float) / U
    return np.where(x >= 0, np.log1p(np.abs(x)), -((1 - x) ** 2 - 1) / 2)


def dz_dh(h, U, eps=1e-6):
    return (z_of_h(h + eps, U) - z_of_h(h - eps, U)) / (2 * eps)


def h_density(pz, U):
    return lambda h: pz(z_of_h(h, U)) * np.abs(dz_dh(h, U))


def integrate_h(f, U, lo=-np.inf, hi=np.inf):
    # split at h = 0 (the branch point) and integrate each side
    pts = [(-np.inf, -50 * U), (-50 * U, 0.0), (0.0, U), (U, np.inf)]
    tot = 0.0
    for a, b in pts:
        tot += integrate.quad(f, a, b, limit=400, epsabs=1e-12, epsrel=1e-10)[0]
    return tot


out = {}
EVENT = None

# ── D1 primary r2_02 on the 2016 development fold ───────────────────────────
sys.path.insert(0, str(BASE / "D1-surface-net"))
import d1data, d1eval, d1lib  # noqa: E402

d1data.log_block_view = log_view
D = d1data.load("dev", viewer="review")
fz = json.loads((BASE / "D1-surface-net/frozen_config.json").read_text())
spec = d1lib.ModelSpec(**fz["primary"]["spec"])
f16 = d1eval.dev_folds(D, d1lib.CFG.val_days)[0]
dev = "cuda"
import torch  # noqa: E402

if not torch.cuda.is_available():
    dev = "cpu"
fr = d1lib.fit_two_stage(spec, D.inp, f16.train, f16.val, [0, 1], dev)
pred = d1lib.predict_ensemble(fr, D.inp, f16.score, dev)
y = D.ev["y"].to_numpy()[f16.score]
U = D.ev["U_pct"].to_numpy()[f16.score]
sc = d1lib.score_rows(pred, y, U)
stored = pd.read_parquet(BASE / "D1-surface-net/dev_preds/r2_02.parquet")
stored = stored[stored["fold"] == 2016].reset_index(drop=True)
ev16 = D.ev.iloc[f16.score][["ticker", "entry_date"]].reset_index(drop=True)
mm = ev16.assign(ls=sc["log_score"], mean=sc["mean"]).merge(stored, on=["ticker", "entry_date"], suffixes=("", "_st"))
out["D1_refit_vs_stored_dev_logscore_maxabs"] = float(np.nanmax(np.abs(mm["ls"] - mm["log_score"])))
out["D1_refit_vs_stored_dev_mean_maxabs"] = float(np.nanmax(np.abs(mm["mean"] - mm["mean_st"])))
i = int(np.nanargmin(np.abs(y - np.nanmedian(y))))  # a typical event
EVENT = (str(ev16.ticker[i]), str(ev16.entry_date[i].date()))
w, mu, sg = pred.w[i], pred.mu[i], pred.sig[i]
pz = lambda z: np.sum(w * stats.norm.pdf(np.asarray(z)[..., None], mu, sg), axis=-1)
fh = h_density(pz, U[i])
out["D1"] = {
    "event": EVENT, "U_pct": float(U[i]), "y": float(y[i]),
    "integral_H": integrate_h(fh, U[i]),
    "logdens_at_y_independent": float(np.log(fh(y[i]))),
    "lane_log_score": float(sc["log_score"][i]),
    "mean_independent": integrate_h(lambda h: h * fh(h), U[i]),
    "mean_lane_quadrature": float(sc["mean"][i]),
}

# ── D2 primary c17 on the same fold and event ──────────────────────────────
sys.path.insert(0, str(BASE / "D2-tabular"))
import d2lib, d2net  # noqa: E402

d2lib.log_view = lambda *a, **k: log_view(period=a[0] if a else "2013-18")
ev = d2lib.load_real(heldout=False, note="review")
c = json.loads((BASE / "D2-tabular/frozen_config.json").read_text())["primary"]
cfg = d2net.Config(head=c["head"], K=c["K"], hidden=tuple(c["hidden"]), weight_decay=c["weight_decay"],
                   dropout=c["dropout"], lr=c["lr"], scale_net=c["scale_net"], drop_inputs=tuple(c["drop_inputs"]), name=c["name"])
fold = d2lib.dev_folds()[0]
fits = [d2net.fit_fold(ev, fold, cfg, s) for s in (0, 1)]
idx = fits[0]["index"]
row = ev.iloc[idx].reset_index(drop=True)
j = int(np.flatnonzero((row.ticker == EVENT[0]) & (row.entry_date == pd.Timestamp(EVENT[1])))[0])
h, U2 = float(row.h[j]), float(row.U[j])
W = np.concatenate([np.exp(f["logw"][j]) / 2 for f in fits])
MU = np.concatenate([f["mu"][j] for f in fits])
SG = np.concatenate([f["sig"][j] for f in fits])
pz2 = lambda z: np.sum(W * stats.norm.pdf(np.asarray(z)[..., None], MU, SG), axis=-1)
fh2 = h_density(pz2, U2)
st2 = pd.read_parquet(BASE / "D2-tabular/search/c17.parquet")
st2 = st2[(st2.ticker == EVENT[0]) & (pd.to_datetime(st2.entry_date) == pd.Timestamp(EVENT[1]))].iloc[0]
lane_lp = d2net.ensemble_logpz(fits, d2lib.to_z(row.h.to_numpy(), row.U.to_numpy()), "gm")
lane_ls = d2lib.log_score_h(lane_lp, row.h.to_numpy(), row.U.to_numpy())
out["D2"] = {
    "event": EVENT, "U_pct": U2, "y": h,
    "integral_H": integrate_h(fh2, U2),
    "logdens_at_y_independent": float(np.log(fh2(h))),
    "lane_log_score_refit": float(lane_ls[j]),
    "lane_log_score_stored_search": float(st2.d2_log_score),
    "mean_independent": integrate_h(lambda x: x * fh2(x), U2),
    "mean_stored_search_quadrature": float(st2.pred_mean),
}

# ── L4 champion (D0 l4_inputs), same event ─────────────────────────────────
li = pd.read_parquet(BASE / "D0-surface/l4_inputs.parquet")
ls = pd.read_parquet(BASE / "D0-surface/l4_scores.parquet")
r = li[(li.ticker == EVENT[0]) & (pd.to_datetime(li.entry_date) == pd.Timestamp(EVENT[1]))].iloc[0]
s = ls[(ls.ticker == EVENT[0]) & (pd.to_datetime(ls.entry_date) == pd.Timestamp(EVENT[1]))].iloc[0]
nu = 30.0


def pz_l4(z):
    z = np.atleast_1d(np.asarray(z, float))
    def one(zz):
        g = lambda lam: stats.gamma.pdf(lam, nu / 2, scale=2 / nu) * stats.t.pdf(
            zz, r.m_pred_df, r.m_pred_loc, np.sqrt(r.m_pred_s2 * (r.m_pred_q + r.v / lam)))
        return integrate.quad(g, 0, np.inf, limit=200)[0]
    return np.array([one(zz) for zz in z]) if z.size > 1 else one(z[0])


U4 = float(r.U_pct)
fh4 = h_density(pz_l4, U4)
trunc = {}
for B in (1e2, 1e3, 1e4):
    trunc[str(B)] = integrate.quad(lambda x: x * fh4(x), -B * U4, 50 * U4, limit=400)[0]
out["L4"] = {
    "event": EVENT, "U_pct": U4,
    "integral_H": integrate_h(fh4, U4),
    "logdens_at_y_independent": float(np.log(fh4(h))),
    "stored_m_log_score": float(s.m_log_score),
    "truncated_mean_lower_bound_multiples_of_U": trunc,
}
print(json.dumps(out, indent=1, default=str))
(HERE / "check_density.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
