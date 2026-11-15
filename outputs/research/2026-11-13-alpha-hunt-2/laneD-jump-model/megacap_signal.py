"""
megacap_signal.py
Trial 2,081, signal side only: the frozen M4 demeaned-richness rule computed on the megacap
events of the hedged-hold study. Reads entry-time columns only (no H, B or exit quote), so the
funnel, treated count and minimum detectable effect are fixed before any outcome is read.

Inputs as in the frozen rule, with the megacap quote source: the two-expiry split and the front
straddle come from the megacap book's 15:59 consolidated-BBO strips (the source the hedged-hold
megacap amendment used), through the same package functions as the broad features
(`hedged_hold.atm_quote`, `split_jump_variance`, 7-day gap). The model is M4 (hyper_m3.json,
`round4.recalibrate`) run over the union of broad and megacap announcement histories; the
91-day demeaning, the implied-move terciles and the top-tercile breakpoints use the union of
broad and megacap events, strictly earlier dates only.

Usage
-----
    python megacap_signal.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

import lib
from build import CRSP_END, PANEL_DAILY, PANEL_EVENTS, RV_LONG, RV_LONG_MIN, RV_MIN, RV_WINDOW, YAHOO
from round3 import trailing_median
from round4 import recalibrate
from selector import richness

from earnings_iv_crush.config import HEDGED
from earnings_iv_crush.research import hedged_hold as hh

MEGA = lib.ROOT / "outputs/research/2026-11-02-hedged-event-hold/events_megacap.parquet"
FEATS = lib.ROOT / "outputs/research/2026-10-20-hedged-hold/features.parquet"
STRIPS = lib.ROOT / "data/processed/databento_quotes"
ENTRY_COLS = ["ticker", "entry_date", "exit_date", "expiry", "status", "strike", "m0", "s0", "mid0"]
TENOR_EDGES = [-1, 1, 4, 9, 100_000]  # as the nonprice-selectors study that defined the cells
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]


def strip_split(ticker: str, entry: pd.Timestamp, exit_: pd.Timestamp) -> dict:
    out = {"front_fwd": np.nan, "front_strike": np.nan, "front_t": np.nan, "front_mid": np.nan,
           "front_bid": np.nan, "jsplit_sd2": np.nan, "jsplit_jump_var": np.nan,
           "jsplit_valid": False, "split_status": "no_strip"}
    p = STRIPS / ticker / f"{entry.date()}_chain.parquet"
    if not p.exists():
        return out
    d = pd.read_parquet(p, columns=["expiry", "strike", "right", "bid", "ask"])
    d["expiry"] = pd.to_datetime(d["expiry"])
    x = d[(d["bid"] > 0) & (d["ask"] > 0)].rename(columns={"bid": "bid_px_00", "ask": "ask_px_00"})
    x = x.assign(mid=(x["bid_px_00"] + x["ask_px_00"]) / 2)
    exps = sorted(pd.Timestamp(e) for e in d["expiry"].unique())
    e1 = next((e for e in exps if e.normalize() >= exit_.normalize()), None)
    front = hh.atm_quote(x, e1, entry) if e1 is not None else None
    if front is None:
        out["split_status"] = "no_front"
        return out
    out.update({"front_fwd": front.fwd, "front_strike": front.strike, "front_t": front.t,
                "front_mid": front.mid, "front_bid": front.bid})
    e2 = next((e for e in exps if (e - e1).days >= HEDGED.jump_split_min_gap_days), None)
    back = hh.atm_quote(x, e2, entry) if e2 is not None else None
    if back is None or not (np.isfinite(front.iv) and np.isfinite(back.iv)) or back.t <= front.t:
        out["split_status"] = "no_second_expiry"
        return out
    s = hh.split_jump_variance(front.iv, front.t, back.iv, back.t)
    out.update({"jsplit_sd2": s.diffusive_var, "jsplit_jump_var": s.jump_var,
                "jsplit_valid": s.valid, "split_status": "ok" if s.valid else "invalid_split"})
    return out


def union_history(opt: pd.DataFrame) -> pd.DataFrame:
    """build.py's history logic, run for every permno in ``opt`` (permno, ticker, day0)."""
    permnos = sorted(int(p) for p in opt["permno"].unique())
    t = ds.dataset(PANEL_DAILY).to_table(
        columns=["permno", "date", "ret"], filter=ds.field("permno").isin(permnos)).to_pandas()
    t["date"] = pd.to_datetime(t["date"])
    t["ret"] = pd.to_numeric(t["ret"], errors="coerce").astype(float)
    t = t[t["date"] <= CRSP_END]
    y = pd.read_parquet(YAHOO)
    y.index = pd.to_datetime(y.index).normalize()
    yr = y.pct_change(fill_method=None)
    yr = yr[yr.index > CRSP_END]
    tick_of = opt.sort_values("day0").groupby("permno")["ticker"].last()
    parts = [pd.DataFrame({"permno": int(p), "date": yr[tk].dropna().index,
                           "ret": yr[tk].dropna().to_numpy()})
             for p, tk in tick_of.items() if tk in yr.columns]
    rets = pd.concat([t, *parts], ignore_index=True).sort_values(["permno", "date"])
    rets = rets.drop_duplicates(["permno", "date"])
    rets["lr"] = np.log1p(rets["ret"])
    pe = pd.read_parquet(PANEL_EVENTS, columns=["permno", "day0", "siccd"])
    pe = pe[pe["permno"].isin(permnos)].copy()
    pe["day0"] = pd.to_datetime(pe["day0"])
    pe["src"] = "panel"
    o = opt[["permno", "day0"]].drop_duplicates().assign(src="option")
    o["permno"] = o["permno"].astype(int)
    od = {int(k): np.sort(g["day0"].to_numpy()) for k, g in o.groupby("permno")}
    near = np.zeros(len(pe), bool)
    for i, (p, d0) in enumerate(zip(pe["permno"].astype(int), pe["day0"].to_numpy(), strict=True)):
        a = od.get(p)
        if a is not None:
            j = np.searchsorted(a, d0)
            for k in (j - 1, j):
                if 0 <= k < a.size and abs((a[k] - d0) / np.timedelta64(1, "D")) <= 3:
                    near[i] = True
    ann = pd.concat([pe.loc[~near, ["permno", "day0", "src"]], o], ignore_index=True)
    ann["permno"] = ann["permno"].astype(int)
    ann = ann.sort_values(["permno", "day0", "src"]).drop_duplicates(["permno", "day0"])
    ann["gap"] = ann.groupby("permno")["day0"].diff().dt.days
    ann = ann[~(ann["gap"] <= 3)].drop(columns="gap")
    sic = pe.dropna(subset=["siccd"]).sort_values("day0").groupby("permno")["siccd"].last()
    sic2 = (pd.to_numeric(sic, errors="coerce") // 100).astype("Int64")
    out = []
    by = {int(k): g.set_index("date")["lr"] for k, g in rets.groupby("permno")}
    for p, g in ann.groupby("permno"):
        r = by.get(int(p))
        if r is None or r.empty:
            continue
        idx, lr = r.index, r.to_numpy(float)
        excl = np.zeros(len(idx), bool)
        pos0 = idx.searchsorted(g["day0"].to_numpy())
        for q, d0 in zip(pos0, g["day0"], strict=True):
            if q < len(idx) and idx[q] == d0:
                excl[q] = True
                if q + 1 < len(idx):
                    excl[q + 1] = True
        for q, d0, src in zip(pos0, g["day0"], g["src"], strict=True):
            rec = {"permno": p, "day0": d0, "src": src, "r": np.nan, "s": np.nan,
                   "s_long": np.nan, "n_rv": 0}
            if q < len(idx) and idx[q] == d0 and q >= 2:
                rec["r"] = lr[q]
                lo = max(0, q - 1 - RV_WINDOW)
                w = lr[lo : q - 1]
                w = w[~excl[lo : q - 1] & np.isfinite(w)]
                rec["n_rv"] = int(w.size)
                if w.size >= RV_MIN:
                    rec["s"] = float(np.sqrt(np.mean(w * w)))
                lo2 = max(0, q - 1 - RV_LONG)
                w2 = lr[lo2 : q - 1]
                w2 = w2[~excl[lo2 : q - 1] & np.isfinite(w2)]
                if w2.size >= RV_LONG_MIN:
                    rec["s_long"] = float(np.sqrt(np.mean(w2 * w2)))
            out.append(rec)
    hist = pd.DataFrame(out)
    hist["sic2"] = hist["permno"].map(sic2)
    return hist


def main() -> None:
    m = pd.read_parquet(MEGA, columns=ENTRY_COLS)
    f = pd.read_parquet(FEATS, columns=["ticker", "entry_date", "exit_date", "permno", "announce_date"])
    f = f.rename(columns={"exit_date": "exit_f"})
    m = m.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"],
                how="left", validate="1:1")
    m["exit_date"] = m["exit_date"].fillna(m["exit_f"])
    print(f"megacap events {len(m)}; status {m['status'].value_counts().to_dict()};"
          f" permno {int(m['permno'].notna().sum())}")
    sp = pd.DataFrame([strip_split(t, e, x) for t, e, x in
                       zip(m["ticker"], m["entry_date"], m["exit_date"], strict=True)])
    m = pd.concat([m.reset_index(drop=True), sp], axis=1)
    print(f"strip split status: {m['split_status'].value_counts().to_dict()}")
    ok = m["status"] == "ok"
    rec = ok & np.isfinite(m["front_mid"])
    print(f"reconcile on ok events: strike match {np.isclose(m.loc[rec, 'front_strike'], m.loc[rec, 'strike']).mean():.4f},"
          f" mid match {np.isclose(m.loc[rec, 'front_mid'], m.loc[rec, 'mid0']).mean():.4f} (N {int(rec.sum())})")

    broad = pd.read_parquet(lib.HERE / "events.parquet")
    opt = pd.concat([
        broad.dropna(subset=["permno"])[["permno", "ticker", "exit_date"]],
        m.dropna(subset=["permno"])[["permno", "ticker", "exit_date"]],
    ]).rename(columns={"exit_date": "day0"})
    opt["permno"] = opt["permno"].astype(int)
    hist = union_history(opt)
    print(f"union history {len(hist)} announcements, {hist['permno'].nunique()} permnos")
    hp = lib.HyperLog(**json.loads((lib.HERE / "hyper_m3.json").read_text()))
    print(f"frozen hyperparameters: {hp}")
    h4 = recalibrate(lib.run_model_log(hist, hp))
    h4.to_parquet(lib.HERE / "megacap_model4_history.parquet", index=False)

    m["universe"] = "megacap"
    broad = broad.assign(universe="broad")
    keep = ["ticker", "entry_date", "exit_date", "expiry", "announce_date", "permno", "universe", "status",
            "m0", "s0", "mid0", "front_fwd", "front_strike", "front_t", "front_mid",
            "jsplit_sd2", "jsplit_jump_var", "jsplit_valid"]
    u = pd.concat([broad[keep], m[keep + ["split_status"]]], ignore_index=True)
    u["permno"] = pd.to_numeric(u["permno"], errors="coerce")
    u = u.merge(h4[["permno", "day0", "lsig2"]], left_on=["permno", "exit_date"],
                right_on=["permno", "day0"], how="left")
    u["year"] = u["announce_date"].dt.year
    u["B"] = np.nan  # outcomes are not loaded here; richness() derives yb from B
    u = richness(u, h4).drop(columns=["B", "yb"])
    u["R_dm"] = u["R_ratio"] - trailing_median(u["R_ratio"], u["announce_date"])
    u["bin"] = lib.causal_bins(u["R_dm"].to_numpy(float), u["announce_date"], 3)
    u["implied_move"] = u["mid0"] / ((u["m0"] - u["s0"]) / 0.20)
    u["im_bin"] = lib.causal_bins(u["implied_move"].to_numpy(float), u["announce_date"], 3)
    dte = (pd.to_datetime(u["expiry"]) - pd.to_datetime(u["exit_date"])).dt.days
    u["tenor"] = pd.cut(dte, TENOR_EDGES, labels=TENOR_LABELS).astype(str)
    u["cell"] = u["im_bin"] * 10 + pd.Categorical(u["tenor"], TENOR_LABELS).codes
    u.to_parquet(lib.HERE / "megacap_signal_union.parquet", index=False)

    g = u[u["universe"] == "megacap"]
    print("\nmegacap funnel (signal side):")
    steps = [("events", np.ones(len(g), bool)), ("hold status ok", g["status"] == "ok"),
             ("+ permno", (g["status"] == "ok") & g["permno"].notna()),
             ("+ model forecast", (g["status"] == "ok") & np.isfinite(g["lsig2"])),
             ("+ valid split", (g["status"] == "ok") & np.isfinite(g["lsig2"]) & g["jsplit_valid"].astype(bool)),
             ("+ R_dm defined", (g["status"] == "ok") & np.isfinite(g["R_dm"])),
             ("+ binned", (g["status"] == "ok") & (g["bin"] >= 0)),
             ("+ implied-move tercile", (g["status"] == "ok") & (g["bin"] >= 0) & (g["im_bin"] >= 0))]
    for k, v in steps:
        print(f"  {k:24s} {int(np.asarray(v).sum())}")
    s = g[(g["status"] == "ok") & (g["bin"] >= 0) & (g["im_bin"] >= 0)]
    print(f"  treated (top tercile) {int((s['bin'] == 2).sum())}, control {int((s['bin'] < 2).sum())};"
          f" by bin {s['bin'].value_counts().sort_index().to_dict()}")
    print(f"  non-ok events with a signal: {int(((g['status'] != 'ok') & (g['bin'] >= 0)).sum())};"
          f" top-tercile share ok {np.mean(s['bin'] == 2):.3f} vs non-ok"
          f" {np.mean(g.loc[(g['status'] != 'ok') & (g['bin'] >= 0), 'bin'] == 2):.3f}")


if __name__ == "__main__":
    main()

