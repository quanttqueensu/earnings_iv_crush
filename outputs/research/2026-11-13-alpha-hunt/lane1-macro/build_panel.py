"""
build_panel.py
Point-in-time macro panel joined to every hedged-hold event on disk (broad 2013-26, megacap
2013-24). Writes panel.parquet in this folder. No outcome is analysed here.

Feature timestamps
------------------
*_lag  : close of the session BEFORE the entry session (strictly before the 15:59 entry).
cal_*  : release calendars (FOMC, CPI, payrolls) as scheduled in advance.
seas_* : from events whose reaction session closed strictly before the entry date.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt/lane1-macro/build_panel.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402

DL = HERE / "dl"
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
ZOO = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
YADJ = ROOT / "data" / "cache" / "yahoo_adj" / "adj_close.parquet"
MACRO = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"

MARGIN_SPOT_FRAC = 0.20
MIN_PRIOR = 200
TENOR_EDGES = [-1, 1, 4, 9, 100_000]
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]

FOMC_2013_15 = [
    "2013-01-30", "2013-03-20", "2013-05-01", "2013-06-19", "2013-07-31", "2013-09-18",
    "2013-10-30", "2013-12-18", "2014-01-29", "2014-03-19", "2014-04-30", "2014-06-18",
    "2014-07-30", "2014-09-17", "2014-10-29", "2014-12-17", "2015-01-28", "2015-03-18",
    "2015-04-29", "2015-06-17", "2015-07-29", "2015-09-17", "2015-10-28", "2015-12-16",
]


# ── events ───────────────────────────────────────────────────────────────────


def load_events() -> pd.DataFrame:
    parts = []
    for f, src in [
        ("events.parquet", "broad"),
        ("events_confirm_2025_26.parquet", "broad"),
        ("events_megacap.parquet", "megacap"),
    ]:
        x = pd.read_parquet(HH / f)
        n0 = len(x)
        x = x[x["status"] == "ok"].copy()
        x["src"] = src
        x["expiry"] = pd.to_datetime(x["expiry"]).astype("datetime64[ns]")
        print(f"funnel {f}: {n0} rows, {len(x)} ok")
        parts.append(x)
    d = pd.concat(parts, ignore_index=True)
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c]).dt.normalize().astype("datetime64[ns]")
    dup = d.duplicated(["ticker", "entry_date"]).sum()
    if dup:
        raise ValueError(f"{dup} duplicate ticker/entry rows across sources")
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "announce_date", "permno",
                                           "front_iv", "s2_iv", "front_t"])
    f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize().astype("datetime64[ns]")
    d = d.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    z = pd.read_parquet(ZOO, columns=["ticker", "entry_date", "is_amc", "front_atm_iv",
                                      "back_atm_iv", "iv_term_spread", "log_mcap", "trailing_rv"])
    z["entry_date"] = pd.to_datetime(z["entry_date"]).dt.normalize().astype("datetime64[ns]")
    d = d.merge(z.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"],
                how="left", validate="one_to_one")
    latest = f.dropna(subset=["permno"]).sort_values("entry_date").groupby("ticker")["permno"].last()
    d["permno"] = d["permno"].fillna(d["ticker"].map(latest))
    d["announce_date"] = pd.to_datetime(d["announce_date"]).dt.normalize()
    d["F0"] = (d["m0"] - d["s0"]) / MARGIN_SPOT_FRAC
    d["implied_move"] = d["mid0"] / d["F0"]
    dte = (d["expiry"] - d["exit_date"]).dt.days
    d["dte_exit"] = dte
    d["tenor"] = pd.cut(dte, TENOR_EDGES, labels=TENOR_LABELS).astype(str)
    # outcomes per unit of entry premium (mid): P&L share of premium kept
    d["yH"] = d["H"] * d["m0"] / d["mid0"]  # hedged hold, net at touch
    d["yB"] = d["B"] * d["m0"] / d["mid0"]  # next-session buy-back, net at touch
    d["yBmid"] = (d["mid0"] - d["exit_mid"]) / d["mid0"]  # buy-back, gross at mid
    d["move_ratio"] = d["abs_move"] / d["implied_move"]
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    d["im_bin"] = causal_bins(d["implied_move"].to_numpy(float), d["announce_date"], 3, MIN_PRIOR)
    d["cell"] = d["im_bin"] * 10 + pd.Categorical(d["tenor"], TENOR_LABELS).codes
    print(f"funnel events: {len(d)} ok; announce dated {int(d['announce_date'].notna().sum())}; "
          f"im tercile assigned {int((d['im_bin'] >= 0).sum())}; yB defined "
          f"{int(d['yB'].notna().sum())}; yH defined {int(d['yH'].notna().sum())}")
    return d


def attach_stock_return(d: pd.DataFrame) -> pd.DataFrame:
    """Signed close-to-close stock return over the reaction session (outcome side, for hedges)."""
    c = pd.read_parquet(CRSP, columns=["permno", "date", "ret"])
    c["ret"] = pd.to_numeric(c["ret"], errors="coerce")
    c["date"] = pd.to_datetime(c["date"]).astype("datetime64[ns]")
    c = c.rename(columns={"date": "exit_date", "ret": "stk_ret"})
    d = d.merge(c, on=["permno", "exit_date"], how="left")
    y = pd.read_parquet(YADJ)
    y.index = pd.to_datetime(y.index).astype("datetime64[ns]")
    yr = y.pct_change(fill_method=None)
    lk = yr.stack().rename("yret").reset_index()
    lk.columns = ["exit_date", "ticker", "yret"]
    d = d.merge(lk, on=["exit_date", "ticker"], how="left")
    d["stk_ret"] = d["stk_ret"].fillna(d["yret"])
    spy = yr["SPY"].rename("spy_ret")
    d = d.merge(spy, left_on="exit_date", right_index=True, how="left")
    # trailing 250-session beta to SPY from yahoo adjusted closes, ending the session before entry
    yv = yr.to_numpy(float)
    cols = {t: i for i, t in enumerate(yr.columns)}
    dates = yr.index.to_numpy()
    sp = yr["SPY"].to_numpy(float)
    beta = np.full(len(d), np.nan)
    for i, (t, e) in enumerate(zip(d["ticker"], d["entry_date"].to_numpy(), strict=True)):
        j = cols.get(t)
        if j is None:
            continue
        hi = int(np.searchsorted(dates, e, side="left"))  # strictly before entry
        lo = max(hi - 250, 0)
        a, b = yv[lo:hi, j], sp[lo:hi]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() >= 120:
            beta[i] = np.cov(a[ok], b[ok])[0, 1] / np.var(b[ok], ddof=1)
    d["beta"] = beta
    chk = (d["stk_ret"].abs() - d["abs_move"]).abs()
    print(f"funnel stock return: present {int(d['stk_ret'].notna().sum())} of {len(d)}; beta "
          f"{int(np.isfinite(beta).sum())}; |ret| matches abs_move within 1pt on "
          f"{int((chk < 0.01).sum())} of {int(chk.notna().sum())}")
    return d.drop(columns=["yret"])


# ── macro daily panel ────────────────────────────────────────────────────────


def _cboe(name: str) -> pd.Series:
    x = pd.read_csv(DL / f"cboe_{name}.csv")
    x.columns = [c.upper() for c in x.columns]
    col = "CLOSE" if "CLOSE" in x.columns else name
    s = pd.Series(pd.to_numeric(x[col], errors="coerce").to_numpy(),
                  index=pd.to_datetime(x["DATE"], format="%m/%d/%Y"), name=name.lower())
    return s[~s.index.duplicated()].sort_index()


def _fred(name: str) -> pd.Series:
    x = pd.read_csv(DL / f"fred_{name}.csv")
    s = pd.Series(pd.to_numeric(x.iloc[:, 1], errors="coerce").to_numpy(),
                  index=pd.to_datetime(x.iloc[:, 0]), name=name.lower())
    return s.sort_index()


def _exp_pct(s: pd.Series, min_n: int = 500) -> pd.Series:
    """Expanding percentile rank of each value among strictly earlier values."""
    v = s.to_numpy(float)
    out = np.full(len(v), np.nan)
    hist: list[float] = []
    import bisect
    for i, x in enumerate(v):
        if np.isfinite(x):
            if len(hist) >= min_n:
                out[i] = bisect.bisect_left(hist, x) / len(hist)
            bisect.insort(hist, x)
    return pd.Series(out, index=s.index)


def macro_daily() -> pd.DataFrame:
    y = pd.read_parquet(YADJ, columns=["SPY"])
    y.index = pd.to_datetime(y.index).astype("datetime64[ns]")
    spy = y["SPY"].dropna()
    m = pd.DataFrame(index=spy.index)
    m["spy"] = spy
    for n in ("VIX", "VIX9D", "VIX3M", "VVIX", "SKEW"):
        m[n.lower()] = _cboe(n).reindex(m.index)
    for n in ("BAA10Y", "T10Y2Y", "DGS2", "DGS10", "DTWEXBGS"):
        m[n.lower()] = _fred(n).reindex(m.index).ffill(limit=3)
    r = np.log(m["spy"]).diff()
    m["spy_ret1"] = r
    m["spy_ret5"] = r.rolling(5).sum()
    m["spy_ret20"] = r.rolling(20).sum()
    m["rv5"] = r.rolling(5).std() * np.sqrt(252) * 100
    m["rv20"] = r.rolling(20).std() * np.sqrt(252) * 100
    m["vix_minus_rv20"] = m["vix"] - m["rv20"]
    m["vix_rv_ratio"] = m["vix"] / m["rv20"]
    for k in (1, 5, 20):
        m[f"vix_chg{k}"] = np.log(m["vix"]).diff(k)
    m["ts_9d"] = m["vix9d"] / m["vix"]
    m["ts_3m"] = m["vix"] / m["vix3m"]
    m["dd"] = m["spy"] / m["spy"].rolling(250, min_periods=120).max() - 1
    m["baa_chg20"] = m["baa10y"].diff(20)
    m["abs_dgs10_1"] = m["dgs10"].diff().abs()
    m["abs_dgs10_5"] = m["dgs10"].diff(5).abs()
    m["abs_dgs2_5"] = m["dgs2"].diff(5).abs()
    m["usd_chg20"] = np.log(m["dtwexbgs"]).diff(20)
    m["abs_spy_ret1"] = r.abs()
    feats = [c for c in m.columns if c != "spy"]
    for c in feats:
        m[c + "_pct"] = _exp_pct(m[c])
    print(f"macro daily: {len(m)} sessions {m.index.min().date()} to {m.index.max().date()}; "
          "non-null counts: " + ", ".join(f"{c} {int(m[c].notna().sum())}" for c in
                                          ("vix", "vix9d", "vix3m", "vvix", "baa10y", "dtwexbgs")))
    return m


# ── calendars ────────────────────────────────────────────────────────────────


def release_calendar() -> pd.DataFrame:
    cal = pd.read_csv(MACRO, parse_dates=["date"])
    extra = []
    for sid, kind in (("PAYEMS", "nfp"), ("CPIAUCSL", "cpi")):
        txt = (DL / f"alfred_{sid}.html").read_text(encoding="utf-8", errors="ignore")
        ds = pd.to_datetime(sorted(set(re.findall(r"20\d\d-\d\d-\d\d", txt))))
        ds = ds[(ds >= "2012-01-01") & (ds <= "2026-12-31")]
        # one release per month: the first vintage of each calendar month
        first = pd.Series(ds, index=ds).groupby([ds.year, ds.month]).min()
        ref = set(cal.loc[cal["kind"] == kind, "date"])
        ov = first[(first >= "2016-01-01") & (first <= "2026-10-28")]
        hit = sum(x in ref for x in ov)
        print(f"calendar check {kind}: ALFRED first-vintage dates match the cached calendar on "
              f"{hit} of {len(ov)} months 2016-26 ({len(ref)} cached)")
        extra.append(pd.DataFrame({"date": first[first < "2016-01-01"].to_numpy(), "kind": kind}))
    extra.append(pd.DataFrame({"date": pd.to_datetime(FOMC_2013_15), "kind": "fomc"}))
    out = pd.concat([cal] + extra, ignore_index=True).drop_duplicates().sort_values("date")
    out = out[out["date"] >= "2013-01-01"]
    print("calendar counts by kind:", out["kind"].value_counts().to_dict())
    return out


def attach_calendar(d: pd.DataFrame, cal: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    pos = pd.Series(np.arange(len(sessions)), index=sessions)
    ent = pos.reindex(d["entry_date"]).to_numpy(float)
    ext = pos.reindex(d["exit_date"]).to_numpy(float)
    print(f"funnel calendar: entry on a session {int(np.isfinite(ent).sum())} of {len(d)}")
    for kind in ("fomc", "cpi", "nfp"):
        ks = cal.loc[cal["kind"] == kind, "date"]
        kp = np.sort(pos.reindex(ks).dropna().to_numpy(float))
        nxt = np.searchsorted(kp, ext, side="left")  # first release on or after the reaction day
        d[f"cal_{kind}_to_next"] = np.where(nxt < len(kp), kp[np.minimum(nxt, len(kp) - 1)] - ext, np.nan)
        prv = np.searchsorted(kp, ent, side="right") - 1  # last release on or before entry day
        d[f"cal_{kind}_since"] = np.where(prv >= 0, ent - kp[np.maximum(prv, 0)], np.nan)
        d[f"cal_{kind}_exit"] = d[f"cal_{kind}_to_next"] == 0
        d[f"cal_{kind}_entry"] = d[f"cal_{kind}_since"] == 0
    d["cal_any_exit"] = d[["cal_fomc_exit", "cal_cpi_exit", "cal_nfp_exit"]].any(axis=1)
    d["cal_any_entry"] = d[["cal_fomc_entry", "cal_cpi_entry", "cal_nfp_entry"]].any(axis=1)
    d["cal_min_to_next"] = d[[f"cal_{k}_to_next" for k in ("fomc", "cpi", "nfp")]].min(axis=1)
    return d


# ── earnings season state ────────────────────────────────────────────────────


def attach_season(d: pd.DataFrame) -> pd.DataFrame:
    """Season position and season-so-far realised/implied, from strictly earlier reaction days."""
    q = d["announce_date"].dt.to_period("Q")
    # season = announcements in a calendar quarter; week index from the quarter's first Monday
    qstart = q.dt.start_time
    d["seas_week"] = ((d["announce_date"] - qstart).dt.days // 7).astype(float)
    d = d.sort_values(["entry_date", "ticker"]).reset_index(drop=True)
    ratio = d["move_ratio"].to_numpy(float)
    ent = d["entry_date"].to_numpy()
    ext = d["exit_date"].to_numpy()
    qq = q.reindex(d.index) if False else d["announce_date"].dt.to_period("Q").astype(str).to_numpy()
    order = np.argsort(ext, kind="stable")
    sofar_mean = np.full(len(d), np.nan)
    sofar_n = np.zeros(len(d))
    last10 = np.full(len(d), np.nan)
    last5d = np.full(len(d), np.nan)
    ext_sorted = ext[order]
    for i in range(len(d)):
        hi = int(np.searchsorted(ext_sorted, ent[i], side="left"))  # reaction closed before entry day
        idx = order[:hi]
        same = idx[qq[idx] == qq[i]]
        r = ratio[same]
        r = r[np.isfinite(r)]
        sofar_n[i] = len(r)
        if len(r) >= 20:
            sofar_mean[i] = r.mean()
        # last 10 calendar days regardless of quarter
        lo = int(np.searchsorted(ext_sorted, ent[i] - np.timedelta64(10, "D"), side="left"))
        r2 = ratio[order[lo:hi]]
        r2 = r2[np.isfinite(r2)]
        if len(r2) >= 15:
            last10[i] = r2.mean()
            last5d[i] = np.median(r2)
    d["seas_sofar_ratio"] = sofar_mean
    d["seas_sofar_n"] = sofar_n
    d["seas_last10_ratio"] = last10
    d["seas_last10_med"] = last5d
    tot = d.groupby(d["announce_date"].dt.to_period("Q"))["ticker"].transform("size")
    # share reported uses the prior-year same-quarter total as the denominator proxy is not
    # available cleanly; use the count so far and the count on the entry day (both known ex ante
    # from the scheduled calendar)
    d["seas_same_day_n"] = d.groupby("exit_date")["ticker"].transform("size").astype(float)
    d["seas_share_sofar_expost"] = sofar_n / tot  # denominator is ex post: descriptive only
    print(f"funnel season: so-far ratio defined {int(np.isfinite(sofar_mean).sum())}, "
          f"last-10-day ratio defined {int(np.isfinite(last10).sum())} of {len(d)}")
    return d


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    d = attach_stock_return(load_events())
    m = macro_daily()
    lag = m.shift(1)  # value at the close of the session before the entry session
    lag.columns = [c + "_lag" for c in lag.columns]
    n0 = len(d)
    d = d.merge(lag, left_on="entry_date", right_index=True, how="left")
    same = m[["vix", "spy_ret1", "abs_spy_ret1"]].rename(columns=lambda c: c + "_same")
    d = d.merge(same, left_on="entry_date", right_index=True, how="left")
    assert len(d) == n0
    print(f"funnel macro join: vix_lag present {int(d['vix_lag'].notna().sum())} of {n0}")
    d = attach_calendar(d, release_calendar(), m.index)
    d = attach_season(d)
    # dispersion proxy: single-name front ATM IV relative to index IV (VIX, lagged)
    d["disp_iv_ratio"] = d["front_iv"] * 100 / d["vix_lag"]
    d["disp_back_ratio"] = d["back_atm_iv"] * 100 / d["vix_lag"]
    d.to_parquet(HERE / "panel.parquet", index=False)
    m.to_parquet(HERE / "macro_daily.parquet")
    print(f"wrote panel {d.shape}; distinct entry dates {d['entry_date'].nunique()}; by year:")
    print(d.groupby([d["entry_date"].dt.year, "src"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
