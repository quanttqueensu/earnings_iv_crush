"""stage_a_moves.py: trials 2472-2475, excess variance of bank stocks on stress-test nights.

Pre-registered in diagnosis.log entry 1. Close-to-close returns from the cached adjusted closes
(data/cache/yahoo_adj/adj_close.parquet). For each bank and each event night t the reaction is
the return from close t to close t+1, scaled by the name's trailing ordinary-session standard
deviation; controls are the same weekday 1-4 weeks earlier on the same name.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N14-bank-stress-tests-and-regulatory/stage_a_moves.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, ROOT)
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PRIMARY = ["JPM", "BAC", "C", "WFC", "GS", "MS", "USB", "PNC", "COF", "STT"]
SECONDARY = ["TFC", "SCHW", "AXP", "NTRS", "FITB", "KEY", "RF", "HBAN", "MTB"]
SIG_WIN, SIG_GAP, EARN_EXCL = 60, 5, 3
CONTROL_LAGS = [5, 10, 15, 20]
EXCLUDED_NIGHTS = {pd.Timestamp("2016-06-23")}  # Brexit referendum night, pre-registered
FOMC_2015 = [pd.Timestamp("2015-01-28"), pd.Timestamp("2015-03-18")]  # recalled


def mean(x: np.ndarray) -> float:
    return float(np.mean(x))


def load() -> tuple[pd.DataFrame, dict[str, list[pd.Timestamp]], set[pd.Timestamp]]:
    px = pd.read_parquet(os.path.join(ROOT, "data/cache/yahoo_adj/adj_close.parquet"))
    px.index = pd.to_datetime(px.index)
    files = os.listdir(os.path.join(ROOT, "data/cache/backfill_chains"))
    earn: dict[str, list[pd.Timestamp]] = {}
    for f in files:
        t, d = f[:-8].rsplit("_", 1)
        earn.setdefault(t, []).append(pd.Timestamp(d))
    mac = pd.read_csv(os.path.join(ROOT, "data/cache/index_events/macro_releases_2016_2026.csv"))
    macro = set(pd.to_datetime(mac["date"])) | set(FOMC_2015)
    return px, earn, macro


def main() -> None:
    px, earn, macro = load()
    cal = pd.read_csv(os.path.join(HERE, "stress_calendar.csv"))
    cal["night"] = pd.to_datetime(cal["night"])
    cal = cal[cal["night"] >= "2015-01-01"].copy()
    sessions = px.index
    pos = {d: i for i, d in enumerate(sessions)}
    event_nights = set(cal["night"])
    first_night = cal.groupby("cycle")["night"].min().to_dict()
    funnel: dict[str, int] = {}
    rows = []
    for t in PRIMARY + SECONDARY + ["SPY"]:
        if t not in px.columns:
            funnel[f"missing_price_{t}"] = 1
            continue
        r = px[t].pct_change()
        e_idx = set()
        for d in earn.get(t, []):
            i = sessions.searchsorted(d)
            e_idx.update(range(i - EARN_EXCL, i + EARN_EXCL + 1))
        ev_idx = {sessions.searchsorted(n) for n in event_nights}
        for _, ev in cal.iterrows():
            n = ev["night"]
            if n not in pos:
                funnel["night_not_a_session"] = funnel.get("night_not_a_session", 0) + 1
                continue
            i = pos[n]
            fi = pos[first_night[ev["cycle"]]]
            win = [k for k in range(fi - SIG_GAP - SIG_WIN, fi - SIG_GAP) if k not in e_idx]
            s = r.iloc[win].std()
            z2e = (r.iloc[i + 1] / s) ** 2 if np.isfinite(s) and s > 0 else np.nan
            ctrl = []
            for lag in CONTROL_LAGS:
                k = i - lag
                if any(abs(k - j) <= 3 for j in ev_idx) or k in e_idx or (k + 1) in e_idx:
                    continue
                if sessions[k + 1] in macro:
                    continue
                ctrl.append((r.iloc[k + 1] / s) ** 2)
            rows.append({"ticker": t, "cycle": ev["cycle"], "night": n,
                         "night_type": ev["night_type"], "ret": r.iloc[i + 1], "sigma": s,
                         "z2": z2e, "n_ctrl": len(ctrl),
                         "z2_ctrl": np.mean(ctrl) if ctrl else np.nan,
                         "earn_in_reaction": (i + 1) in e_idx})
    d = pd.DataFrame(rows)
    d["excess"] = d["z2"] - d["z2_ctrl"]
    d["block"] = np.where(d["night"] < "2020-01-01", "discovery", "heldout")
    d["capital"] = d["night_type"].isin(["ccar_capital", "bank_disclosure", "results_and_capital"])
    d["results"] = d["night_type"].isin(["results_dfast", "results_scb", "results_and_capital"])
    d.to_csv(os.path.join(HERE, "stage_a_rows.csv"), index=False)
    print("funnel", funnel)
    base = d[d["ticker"].isin(PRIMARY)]
    print(f"primary bank-nights {len(base)}; excluded Brexit night "
          f"{int(base['night'].isin(EXCLUDED_NIGHTS).sum())}; earnings inside reaction "
          f"{int(base['earn_in_reaction'].sum())}; no controls {int(base['z2_ctrl'].isna().sum())}")
    keep = base[~base["night"].isin(EXCLUDED_NIGHTS) & ~base["earn_in_reaction"]
                & base["excess"].notna()]
    out = []
    for trial, name, mask in [(2472, "all nights", keep.index == keep.index),
                              (2473, "results nights", keep["results"]),
                              (2474, "capital-action nights", keep["capital"])]:
        for blk in ["discovery", "heldout"]:
            x = keep[mask & (keep["block"] == blk)]
            ci = date_clustered_ci(x["excess"], x["night"], stat=mean)
            ce = date_clustered_ci(x["z2"], x["night"], stat=mean)
            cc = date_clustered_ci(x["z2_ctrl"], x["night"], stat=mean)
            out.append({"trial": trial, "test": name, "block": blk, "n": ci.n,
                        "clusters": ci.clusters, "excess": ci.point, "lo": ci.low, "hi": ci.high,
                        "z2_event": ce.point, "z2_event_lo": ce.low, "z2_event_hi": ce.high,
                        "z2_ctrl": cc.point, "median_abs_ret_event": x["ret"].abs().median(),
                        "median_sigma": x["sigma"].median()})
    res = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    print(res.round(4).to_string(index=False))
    # sensitivity: Brexit night in; secondary names
    sens = base[base["excess"].notna() & ~base["earn_in_reaction"]]
    for blk in ["discovery", "heldout"]:
        x = sens[sens["block"] == blk]
        ci = date_clustered_ci(x["excess"], x["night"], stat=mean)
        print(f"sensitivity, Brexit night kept, {blk}: excess {ci.point:.3f} "
              f"[{ci.low:.3f}, {ci.high:.3f}] N={ci.n} clusters={ci.clusters}")
    sec = d[d["ticker"].isin(SECONDARY) & d["excess"].notna() & ~d["earn_in_reaction"]
            & ~d["night"].isin(EXCLUDED_NIGHTS)]
    for blk in ["discovery", "heldout"]:
        x = sec[sec["block"] == blk]
        ci = date_clustered_ci(x["excess"], x["night"], stat=mean)
        print(f"secondary names {blk}: excess {ci.point:.3f} [{ci.low:.3f}, {ci.high:.3f}] "
              f"N={ci.n} clusters={ci.clusters}")
    spy = d[(d["ticker"] == "SPY") & d["excess"].notna() & ~d["night"].isin(EXCLUDED_NIGHTS)]
    ci = date_clustered_ci(spy["excess"], spy["night"], stat=mean)
    print(f"SPY on the same nights (market confound check): excess {ci.point:.3f} "
          f"[{ci.low:.3f}, {ci.high:.3f}] N={ci.n}")
    per_night = keep.groupby(["night", "night_type"]).agg(
        n=("z2", "size"), z2=("z2", "mean"), z2_ctrl=("z2_ctrl", "mean"),
        mean_ret=("ret", "mean"), med_abs=("ret", lambda v: v.abs().median()))
    print(per_night.round(4).to_string())
    res.to_csv(os.path.join(HERE, "stage_a_results.csv"), index=False)

    # trial 2475 calibration: earnings reaction sessions on the primary names
    cal_rows = []
    for t in PRIMARY:
        r = px[t].pct_change()
        for dd in sorted(set(earn.get(t, []))):
            if dd < pd.Timestamp("2015-01-01"):
                continue
            # backfill files sit on the entry day and the reaction day; banks report before
            # the open, so the later file of each pair is the reaction session
            pair = [x for x in earn[t] if 0 <= (x - dd).days <= 4]
            if len(pair) > 1 and dd != min(pair):
                continue
            react = max(pair)
            i = sessions.searchsorted(react)
            if i >= len(sessions) or i < SIG_GAP + SIG_WIN:
                continue
            win = list(range(i - SIG_GAP - SIG_WIN, i - SIG_GAP))
            s = r.iloc[win].std()
            cal_rows.append({"ticker": t, "date": sessions[i], "z2": (r.iloc[i] / s) ** 2,
                             "ret": r.iloc[i]})
    c = pd.DataFrame(cal_rows).drop_duplicates(["ticker", "date"])
    ci = date_clustered_ci(c["z2"], c["date"], stat=mean)
    print(f"trial 2475 calibration, bank earnings reaction sessions 2015-2026: mean z2 "
          f"{ci.point:.2f} [{ci.low:.2f}, {ci.high:.2f}] N={ci.n} clusters={ci.clusters}; "
          f"median |ret| {c['ret'].abs().median():.4f}")
    c.to_csv(os.path.join(HERE, "stage_a_earnings_calibration.csv"), index=False)


if __name__ == "__main__":
    main()
