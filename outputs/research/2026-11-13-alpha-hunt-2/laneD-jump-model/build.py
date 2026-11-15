"""
build.py
Lane D data build: (1) every announcement of every name in the option event set since 1996 with
its reaction-session log return and the trailing pre-event daily volatility, (2) the option event
table (entry-time quotes, two-expiry jump split, hedged-hold and buy-back outcomes) joined to it.

Point in time. For an announcement whose reaction session is day0, the trailing volatility uses
the 60 sessions ending two sessions before day0 (the session before the 15:59 entry), excluding
day0 and day0+1 of every known announcement of the name. Returns are CRSP holding-period returns
to 2024-12-31 and Yahoo adjusted-close returns from 2025-01-01 (ratios only; never joined to raw
strikes). Option quotes are the 15:59 entry-session chain.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneD-jump-model/build.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

LANE5 = ROOT / "outputs/research/2026-11-13-alpha-hunt/lane5-niche/features.parquet"
FEATS = ROOT / "outputs/research/2026-10-20-hedged-hold/features.parquet"
PANEL_EVENTS = ROOT / "outputs/research/panel_events.parquet"
PANEL_DAILY = ROOT / "outputs/research/panel_daily.parquet"
YAHOO = ROOT / "data/cache/yahoo_adj/adj_close.parquet"
CRSP_END = pd.Timestamp("2024-12-31")
RV_WINDOW = 60  # sessions of pre-event daily returns behind the volatility normaliser
RV_MIN = 40  # fewer valid returns than this leaves the normaliser undefined
RV_LONG = 250  # long-run normaliser (M3): jump size tracks the name's year of vol, not a spike
RV_LONG_MIN = 150


def main() -> None:
    # ── option events with outcomes ─────────────────────────────────────────
    ev = pd.read_parquet(LANE5)
    f = pd.read_parquet(FEATS)
    keep = ["ticker", "entry_date", "front_fwd", "front_strike", "jsplit_sd2", "jsplit_jump_var",
            "jsplit_valid", "s1_iv", "s2_iv"]
    n0 = len(ev)
    ev = ev.merge(f[keep], on=["ticker", "entry_date"], how="left", validate="1:1")
    assert len(ev) == n0
    latest = ev.dropna(subset=["permno"]).sort_values("entry_date").groupby("ticker")["permno"].last()
    ev["permno"] = ev["permno"].fillna(ev["ticker"].map(latest))
    print(f"option events {len(ev)}; permno missing {int(ev['permno'].isna().sum())}")
    permnos = sorted(int(p) for p in ev["permno"].dropna().unique())
    tick_of = ev.dropna(subset=["permno"]).groupby("permno")["ticker"].agg(lambda s: s.iloc[-1])

    # ── daily returns: CRSP to 2024, Yahoo from 2025 ────────────────────────
    t = ds.dataset(PANEL_DAILY).to_table(
        columns=["permno", "date", "ret"], filter=ds.field("permno").isin(permnos)
    ).to_pandas()
    t["date"] = pd.to_datetime(t["date"])
    t["ret"] = pd.to_numeric(t["ret"], errors="coerce").astype(float)
    t = t[t["date"] <= CRSP_END]
    print(f"CRSP daily rows {len(t)} for {t['permno'].nunique()} of {len(permnos)} permnos")
    y = pd.read_parquet(YAHOO)
    y.index = pd.to_datetime(y.index).normalize()
    yr = y.pct_change(fill_method=None)
    yr = yr[yr.index > CRSP_END]
    parts = []
    miss_y = 0
    for p, tk in tick_of.items():
        if tk in yr.columns:
            s = yr[tk].dropna()
            parts.append(pd.DataFrame({"permno": int(p), "date": s.index, "ret": s.to_numpy()}))
        else:
            miss_y += 1
    rets = pd.concat([t, *parts], ignore_index=True).sort_values(["permno", "date"])
    rets = rets.drop_duplicates(["permno", "date"])
    rets["lr"] = np.log1p(rets["ret"])
    print(f"Yahoo 2025-26 returns for {len(parts)} permnos ({miss_y} tickers absent)")

    # ── announcement history ────────────────────────────────────────────────
    pe = pd.read_parquet(PANEL_EVENTS, columns=["permno", "day0", "siccd"])
    pe = pe[pe["permno"].isin(permnos)].copy()
    pe["day0"] = pd.to_datetime(pe["day0"])
    pe["src"] = "panel"
    opt = ev.dropna(subset=["permno"])[["permno", "exit_date"]].rename(columns={"exit_date": "day0"})
    opt["permno"] = opt["permno"].astype(int)
    opt["src"] = "option"
    # match rate of option reaction sessions to panel day0 (a check on the session convention)
    pk = set(zip(pe["permno"].astype(int), pe["day0"]))
    m = np.array([(int(a), b) in pk for a, b in zip(opt["permno"], opt["day0"], strict=True)])
    in_crsp = opt["day0"] <= CRSP_END
    print(f"option reaction sessions found as panel day0: {m[in_crsp].mean():.3f} (to 2024)")
    # an option event's own reaction session wins over a panel date within 3 days of it, so every
    # option event carries its own realised return in the history table
    near = np.zeros(len(pe), bool)
    od = {int(k): np.sort(g["day0"].to_numpy()) for k, g in opt.groupby("permno")}
    for i, (p, d0) in enumerate(zip(pe["permno"].astype(int), pe["day0"].to_numpy(), strict=True)):
        a = od.get(p)
        if a is not None:
            j = np.searchsorted(a, d0)
            for k in (j - 1, j):
                if 0 <= k < a.size and abs((a[k] - d0) / np.timedelta64(1, "D")) <= 3:
                    near[i] = True
    print(f"panel announcements replaced by an option reaction session within 3 days: {near.sum()}")
    pe = pe[~near]
    ann = pd.concat([pe[["permno", "day0", "src"]], opt], ignore_index=True)
    ann["permno"] = ann["permno"].astype(int)
    ann = ann.sort_values(["permno", "day0", "src"]).drop_duplicates(["permno", "day0"])
    # collapse announcements on adjacent sessions (calendar sources disagree by a day)
    ann["gap"] = ann.groupby("permno")["day0"].diff().dt.days
    n_adj = int((ann["gap"] <= 3).sum())
    ann = ann[~(ann["gap"] <= 3)].drop(columns="gap")
    print(f"announcements {len(ann)} (dropped {n_adj} within 3 days of the previous one)")

    sic = pe.dropna(subset=["siccd"]).sort_values("day0").groupby("permno")["siccd"].last()
    sic2 = (pd.to_numeric(sic, errors="coerce") // 100).astype("Int64")

    out = []
    for p, g in ann.groupby("permno"):
        r = rets[rets["permno"] == p].set_index("date")["lr"]
        if r.empty:
            continue
        idx = r.index
        lr = r.to_numpy(float)
        excl = np.zeros(len(idx), bool)
        pos0 = idx.searchsorted(g["day0"].to_numpy())
        for q, d0 in zip(pos0, g["day0"], strict=True):
            if q < len(idx) and idx[q] == d0:
                excl[q] = True
                if q + 1 < len(idx):
                    excl[q + 1] = True
        for q, d0, src in zip(pos0, g["day0"], g["src"], strict=True):
            rec = {"permno": p, "day0": d0, "src": src, "r": np.nan, "s": np.nan, "s_long": np.nan,
                   "n_rv": 0}
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
                rec["s_long"] = float(np.sqrt(np.mean(w2 * w2))) if w2.size >= RV_LONG_MIN else np.nan
            out.append(rec)
    hist = pd.DataFrame(out)
    hist["sic2"] = hist["permno"].map(sic2)
    ok = np.isfinite(hist["r"]) & np.isfinite(hist["s"]) & (hist["s"] > 0)
    print(
        f"history: {len(hist)} announcements, {int(ok.sum())} with return and normaliser; "
        f"sic2 missing {int(hist['sic2'].isna().sum())}; years "
        f"{hist['day0'].dt.year.min()}-{hist['day0'].dt.year.max()}"
    )
    hist.to_parquet(HERE / "history.parquet", index=False)
    ev["permno"] = ev["permno"].astype("Int64")
    ev.to_parquet(HERE / "events.parquet", index=False)
    print(f"wrote {HERE / 'history.parquet'} and {HERE / 'events.parquet'}")


if __name__ == "__main__":
    main()
