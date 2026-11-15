"""
build_features.py
Point-in-time cross-sectional and calendar features for the hedged event hold (lane5-niche).

Every feature is stamped: it uses only data dated strictly before the entry session, or
schedule facts (expiry, weekday, fiscal period, the reporting calendar) fixed before entry.
Outcomes are carried through untouched from the frozen loader.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt/lane5-niche/build_features.py
"""

from __future__ import annotations

import glob
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
WRDS = ROOT / "data" / "processed" / "wrds" / "raw"
CHARS = Path.home() / "FIAM_Hackathon_2026" / "temp" / "chars_final_with_names.parquet"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
YAHOO = ROOT / "data" / "cache" / "yahoo_adj" / "adj_close.parquet"

_spec = importlib.util.spec_from_file_location(
    "nonprice",
    ROOT / "research" / "selection" / "2026-11-10-nonprice-selectors-hedged-hold" / "study.py",
)
assert _spec and _spec.loader
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

PEER_DATADATE_TOL = 31  # days: same fiscal quarter end, allowing 52/53-week calendars
PEER_MIN = 5
RDQ_MATCH_TOL = 7  # days between the panel announcement date and Compustat rdq


def _clean_code(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(".0", "", regex=False)


def load_fundq() -> pd.DataFrame:
    """All Compustat quarterly report dates on disk: gvkey, rdq, datadate, fqtr."""
    parts = []
    for f in sorted(glob.glob(str(WRDS / "comp_na_daily_all.fundq.*.parquet"))):
        x = pd.read_parquet(f)
        if {"gvkey", "rdq", "datadate"} <= set(x.columns):
            if "fqtr" not in x.columns:
                x["fqtr"] = np.nan
            parts.append(x[["gvkey", "rdq", "datadate", "fqtr"]])
    q = pd.concat(parts, ignore_index=True)
    q["rdq"] = pd.to_datetime(q["rdq"], errors="coerce")
    q["datadate"] = pd.to_datetime(q["datadate"], errors="coerce")
    q = q.dropna(subset=["rdq", "datadate"]).sort_values("fqtr")
    q["gvkey"] = _clean_code(q["gvkey"]).str.zfill(6)
    q = q.drop_duplicates(["gvkey", "datadate"], keep="first")
    print(
        f"fundq: {len(q)} firm-quarters, rdq {q['rdq'].min().date()} to {q['rdq'].max().date()}, "
        f"{q['gvkey'].nunique()} firms, fqtr present {q['fqtr'].notna().mean():.3f}"
    )
    return q.sort_values("rdq").reset_index(drop=True)


def main() -> None:
    d = base.load_events()
    f = pd.read_parquet(
        FEATURES,
        columns=["ticker", "entry_date", "front_bid", "front_ask", "front_mid", "front_iv",
                 "front_t"],
    )
    f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    d = d.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    for c in ("entry_date", "exit_date", "expiry"):
        d[c] = pd.to_datetime(d[c]).dt.normalize()

    # ── outcomes and controls (outcomes are not features) ────────────────────
    d["ri"] = d["abs_move"] / d["implied_move"]
    d["yb"] = d["B"] * d["m0"] / d["mid0"]
    d["half_spread"] = (d["mid0"] - d["s0"]) / d["mid0"]  # entry quote, 15:59 entry session
    d["amc"] = d["announce_date"] == d["entry_date"]
    d["dte"] = (d["expiry"] - d["exit_date"]).dt.days

    # ── calendar (schedule facts, fixed before entry) ────────────────────────
    sessions = pd.DatetimeIndex(pd.read_parquet(YAHOO, columns=["SPY"]).dropna().index).normalize()
    sess = sessions.to_numpy().astype("datetime64[ns]")
    pos_exit = np.searchsorted(sess, d["exit_date"].to_numpy().astype("datetime64[ns]"))
    pos_exp = np.searchsorted(
        sess, d["expiry"].to_numpy().astype("datetime64[ns]"), side="right"
    )  # side=right so a Saturday expiry counts the Friday session
    covered = d["exit_date"].between(sessions.min(), sessions.max()).to_numpy()
    d["sess_to_expiry"] = np.where(covered, pos_exp - pos_exit - 1, np.nan)
    d["gap_days"] = (d["exit_date"] - d["entry_date"]).dt.days
    d["exit_wd"] = d["exit_date"].dt.weekday
    wd_between = np.array(
        [
            np.busday_count(a.date(), b.date()) if b >= a else 0
            for a, b in zip(d["exit_date"], d["expiry"], strict=True)
        ]
    )
    d["holiday_to_expiry"] = covered & (wd_between - d["sess_to_expiry"].fillna(0) > 0)
    entry_wd = d["entry_date"].dt.weekday
    d["holiday_in_gap"] = ((entry_wd == 4) & (d["gap_days"] > 3)) | (
        (entry_wd != 4) & (d["gap_days"] > 1)
    )
    qe = d["exit_date"] + pd.offsets.QuarterEnd(0)
    d["days_to_qend"] = (qe - d["exit_date"]).dt.days
    d["month"] = d["announce_date"].dt.month
    print(
        f"calendar funnel: sessions {sessions.min().date()} to {sessions.max().date()}, "
        f"covered {int(covered.sum())} of {len(d)}; gap over one day {int((d['gap_days'] > 1).sum())}; "
        f"holiday in gap {int(d['holiday_in_gap'].sum())}; holiday before expiry "
        f"{int(d['holiday_to_expiry'].sum())}"
    )

    # ── characteristics: last month end strictly before the entry month ──────
    ch = pd.read_parquet(
        CHARS, columns=["permno", "gvkey", "eom", "me", "gics", "prc", "turnover_126d",
                        "dolvol_126d"]
    )
    ch["eom"] = pd.to_datetime(ch["eom"])
    ch["gvkey"] = _clean_code(ch["gvkey"]).str.zfill(6)
    ch["gics"] = _clean_code(ch["gics"])
    ch.loc[~ch["gics"].str.fullmatch("[0-9]{8}"), "gics"] = np.nan
    ch = ch.sort_values("eom")
    static = (
        ch.dropna(subset=["gics"]).groupby("permno").agg(gvkey=("gvkey", "last"), gics=("gics", "last"))
    )
    d["permno_i"] = d["permno"].astype("Int64")
    d = d.merge(static, left_on="permno_i", right_index=True, how="left")
    d["sector"] = d["gics"].str[:2]
    d["igroup"] = d["gics"].str[:4]
    d["industry"] = d["gics"].str[:6]
    left = d[["permno_i", "entry_date"]].dropna().copy()
    left["key"] = left["entry_date"].dt.to_period("M").dt.start_time
    left["permno_i"] = left["permno_i"].astype("int64")
    left = left.reset_index().sort_values("key")
    right = ch[["permno", "eom", "me", "prc", "turnover_126d", "dolvol_126d"]].sort_values("eom")
    left["key"] = left["key"].astype(right["eom"].dtype)
    m = pd.merge_asof(
        left, right, left_on="key", right_on="eom", left_by="permno_i", right_by="permno",
        allow_exact_matches=False, tolerance=pd.Timedelta(days=70),
    ).set_index("index")
    for c in ("me", "prc", "turnover_126d", "dolvol_126d"):
        d[c] = m[c].reindex(d.index)
    print(
        f"chars funnel: gics {int(d['gics'].notna().sum())} of {len(d)}, lagged me "
        f"{int(d['me'].notna().sum())} (panel starts 2015), turnover "
        f"{int(d['turnover_126d'].notna().sum())}"
    )

    # ── Compustat reporting calendar: fiscal quarter, crowding, peers ────────
    q = load_fundq()
    gmap = ch.dropna(subset=["gics"]).groupby("gvkey")["gics"].last()
    q["gics"] = q["gvkey"].map(gmap)
    per_day = q.groupby("rdq").size()
    d["crowd_all"] = d["announce_date"].map(per_day)
    in_cal = d["announce_date"].between(q["rdq"].min(), q["rdq"].max())
    d.loc[in_cal & d["crowd_all"].isna(), "crowd_all"] = 0
    d.loc[~in_cal, "crowd_all"] = np.nan
    by_g = {k: g for k, g in q.groupby("gvkey")}
    qg = q.dropna(subset=["gics"]).copy()
    qg["igroup"], qg["industry"] = qg["gics"].str[:4], qg["gics"].str[:6]
    by_ig = {k: g for k, g in qg.groupby("igroup")}
    by_ind = {k: g for k, g in qg.groupby("industry")}
    n = len(d)
    fq, share, npeer = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    week, prior6 = np.full(n, np.nan), np.full(n, np.nan)
    funnel = {"no_gvkey": 0, "no_rdq_match": 0, "few_peers": 0, "ok": 0}
    tol = pd.Timedelta(days=PEER_DATADATE_TOL)
    for i, (g, ann, ent, ig, ind) in enumerate(
        zip(d["gvkey"], d["announce_date"], d["entry_date"], d["igroup"], d["industry"],
            strict=True)
    ):
        own = by_g.get(g) if isinstance(g, str) else None
        if own is None or not isinstance(ig, str):
            funnel["no_gvkey"] += 1
            continue
        gap = (own["rdq"] - ann).abs()
        j = gap.idxmin()
        if gap[j] > pd.Timedelta(days=RDQ_MATCH_TOL):
            funnel["no_rdq_match"] += 1
            continue
        fq[i] = own.at[j, "fqtr"]
        dd = own.at[j, "datadate"]
        p = by_ig.get(ig)
        p6 = by_ind.get(ind)
        if p is None or p6 is None:
            funnel["few_peers"] += 1
            continue
        p = p[((p["datadate"] - dd).abs() <= tol) & (p["gvkey"] != g)]
        p6 = p6[((p6["datadate"] - dd).abs() <= tol) & (p6["gvkey"] != g)]
        week[i] = int(((p6["rdq"] < ent) & (p6["rdq"] >= ent - pd.Timedelta(days=7))).sum())
        prior6[i] = int((p6["rdq"] < ent).sum())
        if len(p) < PEER_MIN:
            funnel["few_peers"] += 1
            continue
        npeer[i] = len(p)
        share[i] = float((p["rdq"] < ent).mean())  # strictly before the entry session
        funnel["ok"] += 1
    d = d.assign(fqtr=fq, peer_share=share, n_peers=npeer, peer_week=week, ind_prior=prior6)
    print(
        f"reporting-calendar funnel: {funnel}; fqtr present {int(np.isfinite(fq).sum())}; "
        f"crowd defined {int(d['crowd_all'].notna().sum())}"
    )
    panel_all = pd.read_parquet(FEATURES, columns=["announce_date"])
    d["crowd_panel"] = d["announce_date"].map(
        pd.to_datetime(panel_all["announce_date"]).dt.normalize().value_counts()
    )
    keep = [c for c in d.columns if c != "permno_i"]
    d[keep].to_parquet(HERE / "features.parquet", index=False)
    print(f"wrote {HERE / 'features.parquet'}: {d.shape}")


if __name__ == "__main__":
    main()
