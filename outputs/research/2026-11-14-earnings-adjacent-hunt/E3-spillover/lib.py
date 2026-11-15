"""
lib.py
Shared loaders for the E3 spillover lane: the event calendar, CRSP closes with closing quotes,
point-in-time SIC codes, and the peer-night table (a reporter's event night joined to every
same-industry name in the universe that is not itself reporting near that night).

Every function prints a funnel; nothing here computes an outcome.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WRDS = ROOT / "data" / "processed" / "wrds" / "raw"
CRSP_SLICE = WRDS / "crsp_a_stock.dsf.a336cb25197b.parquet"  # 332 event-universe permnos
DSENAMES = WRDS / "crsp_a_stock.dsenames.a5818c8cd21b.parquet"  # full name history with SIC
DSI_GLOB = "crsp_a_stock.dsi.*.parquet"
FEATURES = ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt" / "lane5-niche" / "features.parquet"
EVENTS_ALL = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
CALENDAR_BROAD = ROOT / "outputs" / "research" / "calendar_broad_2013_2024.parquet"
CAL_CLEAR_DAYS = 1  # calendar days either side of a broad-calendar announce date

# ── constants (each with its reason) ─────────────────────────────────────────
SIC_DIGITS = 3  # SIC industry group: narrow enough to share demand shocks, wide enough for peers
PEER_CLEAR_BEFORE = 2  # sessions: the peer may not report in the two sessions before B's entry
PEER_CLEAR_SHORT = 2  # sessions after B's reaction kept clear for the one-session horizon
PEER_CLEAR_AFTER = 6  # sessions after B's reaction kept clear for the five-session horizon
RDQ_CLEAR_DAYS = 3  # calendar days either side of a Compustat rdq (no session-timing field)
STOCK_FEE_BP = 1.0  # brief rule 5: stock legs pay the half-spread plus 1 bp per side
HEDGE_HALF_SPREAD_BP = 0.3  # SPY close half-spread, about one cent on a USD 300-600 price
MIN_ABS_SIGNAL = 0.01  # |abnormal reaction| floor so the sign seen at 15:45 matches the close


def sessions() -> pd.DatetimeIndex:
    """Trading sessions present in the CRSP slice."""
    d = pd.read_parquet(CRSP_SLICE, columns=["date"])
    return pd.DatetimeIndex(sorted(pd.to_datetime(d["date"]).unique()))


def crsp() -> pd.DataFrame:
    """CRSP daily rows: total return, absolute close, closing half-spread as a fraction."""
    d = pd.read_parquet(CRSP_SLICE)
    d["date"] = pd.to_datetime(d["date"])
    for c in ("prc", "ret", "bid", "ask", "cfacpr"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["prc"] = d["prc"].abs()
    ok = (d["bid"] > 0) & (d["ask"] >= d["bid"])
    mid = (d["bid"] + d["ask"]) / 2
    d["half_spread"] = np.where(ok, (d["ask"] - d["bid"]) / 2 / mid, np.nan)
    print(
        f"crsp: {len(d)} rows, {d['permno'].nunique()} permnos, {d['date'].min().date()} to "
        f"{d['date'].max().date()}; ret finite {d['ret'].notna().mean():.4f}; closing quote "
        f"usable {np.isfinite(d['half_spread']).mean():.4f}"
    )
    return d


def market() -> pd.Series:
    """S&P 500 price return by date (CRSP dsi sprtrn), the SPY hedge leg's return.

    Price return omits SPY's dividend, about 0.6 bp a day, which is negligible against the
    peer's daily noise and enters both signs of the trade equally.
    """
    f = glob.glob(str(WRDS / DSI_GLOB))
    if len(f) != 1:
        raise FileNotFoundError(f"expected one cached dsi slice, found {len(f)}")
    m = pd.read_parquet(f[0])
    m["date"] = pd.to_datetime(m["date"])
    if "sprtrn" not in m.columns:
        raise KeyError(f"dsi slice has no sprtrn: {list(m.columns)}")
    s = m.set_index("date")["sprtrn"].astype(float)
    print(f"market: sprtrn {s.index.min().date()} to {s.index.max().date()}, {s.notna().sum()} days")
    return s


def sic_history() -> pd.DataFrame:
    """Point-in-time SIC rows for the universe permnos."""
    n = pd.read_parquet(DSENAMES, columns=["permno", "namedt", "nameendt", "siccd", "ticker"])
    n["namedt"] = pd.to_datetime(n["namedt"])
    n["nameendt"] = pd.to_datetime(n["nameendt"]).fillna(pd.Timestamp("2099-12-31"))
    n["siccd"] = pd.to_numeric(n["siccd"], errors="coerce")
    return n


def sic_at(names: pd.DataFrame, permno: np.ndarray, dates: np.ndarray) -> np.ndarray:
    """SIC code in force for each (permno, date); NaN where no name row covers the date."""
    out = np.full(len(permno), np.nan)
    by = {k: g for k, g in names.groupby("permno")}
    for i, (p, t) in enumerate(zip(permno, dates, strict=True)):
        g = by.get(p)
        if g is None:
            continue
        hit = g[(g["namedt"] <= t) & (g["nameendt"] >= t)]
        if len(hit):
            out[i] = hit["siccd"].iloc[-1]
    return out


def events() -> pd.DataFrame:
    """Reporter events in the universe with reaction session; one row per event."""
    f = pd.read_parquet(FEATURES, columns=["ticker", "permno", "entry_date", "exit_date",
                                           "announce_date", "amc", "gics", "gvkey"])
    for c in ("entry_date", "exit_date", "announce_date"):
        f[c] = pd.to_datetime(f[c]).dt.normalize()
    f = f.dropna(subset=["permno"]).copy()
    f["permno"] = f["permno"].astype(int)
    print(f"events: {len(f)} rows, {f['permno'].nunique()} permnos, "
          f"{f['entry_date'].min().date()} to {f['entry_date'].max().date()}")
    return f


def all_report_dates() -> pd.DataFrame:
    """Every known report date per permno: panel events (any status) plus Compustat rdq.

    Used only to exclude peers that are themselves reporting near a bellwether's night.
    """
    f = events()
    tick2perm = f.dropna(subset=["permno"]).groupby("ticker")["permno"].first()
    e = pd.read_parquet(EVENTS_ALL, columns=["ticker", "entry_date", "exit_date"])
    e["permno"] = e["ticker"].map(tick2perm)
    miss = int(e["permno"].isna().sum())
    e = e.dropna(subset=["permno"])
    rows = [
        pd.DataFrame({"permno": f["permno"], "d0": f["entry_date"], "d1": f["exit_date"]}),
        pd.DataFrame({"permno": e["permno"].astype(int), "d0": pd.to_datetime(e["entry_date"]),
                      "d1": pd.to_datetime(e["exit_date"])}),
    ]
    # Compustat rdq through gvkey (no session timing, so it is widened by RDQ_CLEAR_DAYS)
    parts = []
    for p in sorted(glob.glob(str(WRDS / "comp_na_daily_all.fundq.*.parquet"))):
        x = pd.read_parquet(p)
        if {"gvkey", "rdq"} <= set(x.columns):
            parts.append(x[["gvkey", "rdq"]])
    q = pd.concat(parts, ignore_index=True).dropna()
    q["gvkey"] = q["gvkey"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    q["rdq"] = pd.to_datetime(q["rdq"], errors="coerce")
    g2p = f.dropna(subset=["gvkey"]).groupby("gvkey")["permno"].first()
    q["permno"] = q["gvkey"].map(g2p)
    q = q.dropna(subset=["permno", "rdq"]).drop_duplicates()
    tol = pd.Timedelta(days=RDQ_CLEAR_DAYS)
    rows.append(pd.DataFrame({"permno": q["permno"].astype(int), "d0": q["rdq"] - tol,
                              "d1": q["rdq"] + tol}))
    # the broad calendar the 15:59 history was pulled from (IBES-timed and untimed rows), which
    # covers names whose gvkey does not link and whose events failed the panel's filters
    cal = pd.read_parquet(CALENDAR_BROAD, columns=["ticker", "announce_date", "gvkey"])
    cal["announce_date"] = pd.to_datetime(cal["announce_date"])
    cal["permno"] = cal["ticker"].map(tick2perm)
    gk = cal["gvkey"].astype(str).str.replace(".0", "", regex=False).str.zfill(6).map(g2p)
    cal["permno"] = cal["permno"].fillna(gk)
    cal = cal.dropna(subset=["permno"])
    one = pd.Timedelta(days=CAL_CLEAR_DAYS)
    rows.append(pd.DataFrame({"permno": cal["permno"].astype(int),
                              "d0": cal["announce_date"] - one, "d1": cal["announce_date"] + one}))
    # any Databento event chain on disk marks an event session for that ticker
    bf = pd.DataFrame(sorted(file_index(str(ROOT / "data" / "cache" / "backfill_chains" / "*.parquet"))),
                      columns=["ticker", "d"])
    bf["permno"] = bf["ticker"].map(tick2perm)
    bf = bf.dropna(subset=["permno"])
    bf["d"] = pd.to_datetime(bf["d"])
    rows.append(pd.DataFrame({"permno": bf["permno"].astype(int), "d0": bf["d"], "d1": bf["d"]}))
    r = pd.concat(rows, ignore_index=True).drop_duplicates()
    print(f"report dates: {len(r)} windows over {r['permno'].nunique()} permnos "
          f"(events file tickers unmapped: {miss}; rdq-linked permnos {q['permno'].nunique()}; "
          f"broad-calendar rows mapped {len(cal)}; backfill chain days mapped {len(bf)})")
    return r


def file_index(pattern: str) -> set[tuple[str, str]]:
    """(TICKER, YYYY-MM-DD) pairs present in a cache glob, by filename only."""
    out = set()
    for p in glob.glob(pattern):
        b = os.path.basename(p)
        stem = b.rsplit(".", 1)[0]
        for suf in ("_pre", "_exit", "_entry"):
            if stem.endswith(suf):
                stem = stem[: -len(suf)]
        if "_" not in stem:
            continue
        t, d = stem.rsplit("_", 1)
        out.add((t, d))
    return out
