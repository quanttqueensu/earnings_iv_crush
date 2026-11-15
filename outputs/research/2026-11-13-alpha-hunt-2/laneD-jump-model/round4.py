"""
round4.py
Round 4 on the discovery block. (a) Demeaned M3 richness inside jump-share cells. (b) Economic
threshold: sell only where the 15:59 bid exceeds the model-fair value (R_touch > 0). (c) M4: a
causal Mincer-Zarnowitz recalibration of M3's log scale (OLS of log r^2 on the forecast over
strictly earlier announcements, 5-year half-life), its calibration, encompassing and selection.

Usage
-----
    python round4.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib
from fit_calib import clustered, ratio, slope
from round3 import trailing_median
from selector import richness, score

H_RECAL = 5.0  # years, half-life of the recalibration regression's evidence
MIN_RECAL = 2000  # announcements before the recalibration is used


def recalibrate(h: pd.DataFrame) -> pd.DataFrame:
    h = h.sort_values("day0", kind="stable").reset_index(drop=True)
    y = np.log(h["r"].to_numpy(float) ** 2 + lib.FLOOR)
    x = h["lsig2"].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y)
    day = (h["day0"] - pd.Timestamp("1990-01-01")).dt.days.to_numpy()
    lam = np.log(2) / (H_RECAL * 365.0)
    acc = np.zeros(5)  # w, x, y, xx, xy
    last = float(day[0])
    a_out, b_out = np.full(len(h), np.nan), np.full(len(h), np.nan)
    cnt = 0
    i = 0
    while i < len(h):
        j = i
        while j < len(h) and day[j] == day[i]:
            j += 1
        acc *= np.exp(-lam * (day[i] - last))
        last = float(day[i])
        if cnt >= MIN_RECAL:
            w, sx, sy, sxx, sxy = acc
            b = (sxy - sx * sy / w) / (sxx - sx * sx / w)
            a_out[i:j], b_out[i:j] = sy / w - b * sx / w, b
        for k in range(i, j):
            if ok[k]:
                acc += np.array([1.0, x[k], y[k], x[k] * x[k], x[k] * y[k]])
                cnt += 1
        i = j
    h["recal_a"], h["recal_b"] = a_out, b_out
    # the intercept absorbs E[log z^2]; the level is restored by the z pool at pricing time
    h["lsig2_raw"] = h["lsig2"]
    h["lsig2"] = a_out + b_out * x
    h["z"] = h["r"] / np.exp(h["lsig2"] / 2)
    return h


def main() -> None:
    e = pd.read_parquet(lib.HERE / "rich_m3_r3.parquet")
    e3 = e[e["js_bin"] >= 0].copy()
    e3["cell"] = e3["cell"] * 10 + e3["js_bin"]
    score(e3, "R_dm", "yb", "discovery", 1887,
          hyp="m3 top-tercile demeaned R_ratio -> yb, cells implied move x tenor x jump share",
          mech="demeaned richness pays beyond the term-structure jump share")
    mech_t = ("selling only where the bid exceeds the model-fair straddle (an economic threshold, not"
              " a quantile): the seller is paid more than the model's expected payoff")
    score(e, "R_touch", "yb", "discovery", 1888, fixed=0.0, mech=mech_t,
          hyp="m3 bid above model-fair value (R_touch > 0) -> yb")
    score(e, "R_touch", "y", "discovery", 1889, fixed=0.0, mech=mech_t,
          hyp="m3 bid above model-fair value (R_touch > 0) -> y")

    # ── M4 ────────────────────────────────────────────────────────────────────
    h3 = pd.read_parquet(lib.HERE / "model3_history.parquet")
    h4 = recalibrate(h3)
    print(f"\nM4 recalibration slope at 2019-01-01: "
          f"{h4.loc[h4['day0'] >= '2019-01-01', 'recal_b'].iloc[0]:.3f}; at 2024-12-31: "
          f"{h4.loc[h4['day0'] <= '2024-12-31', 'recal_b'].iloc[-1]:.3f}")
    h4.to_parquet(lib.HERE / "model4_history.parquet", index=False)
    ev = pd.read_parquet(lib.HERE / "events_model3.parquet").drop(columns=["lsig2"])
    ev = ev.merge(h4[["permno", "day0", "lsig2"]], on=["permno", "day0"], how="left")
    # model's own predicted variance: sig^2 E[z^2] over the pool before the event's year
    ez2 = {yr: float(np.mean(lib.shape_pool(h4, yr) ** 2)) for yr in range(2013, 2027)}
    ev["pred_var4"] = np.exp(ev["lsig2"]) * ev["entry_date"].dt.year.map(ez2)
    ev.to_parquet(lib.HERE / "events_model4.parquet", index=False)
    lo, hi = lib.BLOCKS["discovery"]
    d = ev[ev["year"].between(lo, hi)]
    d = d[np.isfinite(d["r"]) & np.isfinite(d["pred_var4"]) & np.isfinite(d["mkt_var"])].copy()
    keys = d["announce_date"].dt.normalize().to_numpy()
    r2, pv, mv = (d["r"] ** 2).to_numpy(), d["pred_var4"].to_numpy(), d["mkt_var"].to_numpy()
    p, l_, u_, _ = clustered(ratio, keys, r2, pv)
    d["dec"] = pd.qcut(d["pred_var4"], 10, labels=False)
    rows = []
    for k, g in d.groupby("dec"):
        kk = g["announce_date"].dt.normalize().to_numpy()
        a, b, c, _ = clustered(ratio, kk, (g["r"] ** 2).to_numpy(), g["pred_var4"].to_numpy())
        rows.append({"decile": int(k), "n": len(g), "pred_sd": np.sqrt(g["pred_var4"].mean()),
                     "real_sd": np.sqrt((g["r"] ** 2).mean()), "ratio": a, "lo": b, "hi": c})
    cal = pd.DataFrame(rows)
    mz, mzl, mzh, _ = clustered(slope, keys, r2, pv)
    print(f"M4 calibration, discovery N {len(d)}: realised/predicted variance {p:.3f} [{l_:.3f}, {u_:.3f}];"
          f" MZ slope {mz:.3f} [{mzl:.3f}, {mzh:.3f}]")
    print(cal.round(4).to_string(index=False))
    calibrated = (l_ <= 1 <= u_) and (cal.iloc[0]["lo"] <= 1 <= cal.iloc[0]["hi"]) and (
        cal.iloc[-1]["lo"] <= 1 <= cal.iloc[-1]["hi"])
    lib.log_trial({"trial_id": 1890, "hypothesis": "M4 (causally recalibrated M3) predicted variance unbiased",
                   "mechanism": "a causal MZ slope on the log forecast removes M3's residual fan",
                   "block": f"discovery {lo}-{hi}", "n": len(d), "effect": round(p, 4),
                   "ci_low": round(l_, 4), "ci_high": round(u_, 4), "t": "", "null_pct": "",
                   "basis": f"ratio mean r^2 / model variance; MZ slope {mz:.3f} [{mzl:.3f}, {mzh:.3f}]",
                   "verdict": "calibrated" if calibrated else "not calibrated", "label": "diagnostic"})
    b, bl, bh, bb = clustered(slope, keys, r2 - mv, pv - mv)
    tt = b / np.std(bb, ddof=1)
    print(f"M4 encompassing slope {b:.3f} [{bl:.3f}, {bh:.3f}] t {tt:.2f}")
    lib.log_trial({"trial_id": 1891, "hypothesis": "M4 minus market variance predicts realised minus market",
                   "mechanism": "model information absent from the price", "block": f"discovery {lo}-{hi}",
                   "n": len(d), "effect": round(b, 4), "ci_low": round(bl, 4), "ci_high": round(bh, 4),
                   "t": round(tt, 2), "null_pct": "", "basis": "OLS slope, variance units",
                   "verdict": "pass" if bl > 0 else "fail", "label": "diagnostic"})
    cal.to_csv(lib.HERE / "calibration_m4_discovery.csv", index=False)

    e4 = richness(ev, h4)
    e4["R_dm"] = e4["R_ratio"] - trailing_median(e4["R_ratio"], e4["announce_date"])
    e4.to_parquet(lib.HERE / "rich_m4.parquet", index=False)
    mech4 = "M4 demeaned richness: recalibrated fair value, mispricing relative to its own period"
    score(e4, "R_dm", "yb", "discovery", 1892, mech=mech4, hyp="m4 top-tercile demeaned R_ratio -> yb")
    score(e4, "R_dm", "y", "discovery", 1893, mech=mech4, hyp="m4 top-tercile demeaned R_ratio -> y")


if __name__ == "__main__":
    main()
