"""
build_ledger.py
Per-event forensic ledger for the short earnings straddle (lane2-forensics, alpha hunt 2026-11-13).

Joins the stored hedged-event-hold panel (no re-pricing) to every pre-entry feature that can be
built from files already on disk: the option features table, CRSP daily paths, the announcement
calendar, the monthly characteristics panel and the cached EDGAR filing index. Every feature uses
information dated strictly before the entry session's 15:59 decision unless stated.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt/lane2-forensics/build_ledger.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402

PANEL = ROOT / "outputs/research/2026-11-10-nonprice-selectors-hedged-hold/events.parquet"
FEATURES = ROOT / "outputs/research/2026-10-20-hedged-hold/features.parquet"
ZOO = ROOT / "outputs/research/ml_zoo/events_full.parquet"
CRSP = ROOT / "outputs/research/2026-10-20-hedged-hold/crsp_paths.parquet"
CAL = ROOT / "outputs/research/calendar_broad_2013_2024.parquet"
CHARS = Path.home() / "FIAM_Hackathon_2026/temp/chars_final_with_names.parquet"
EDGAR = ROOT / "data/cache/edgar"

# ── parameters ──
LAST_YEAR = 2024  # 2025-26 has no calendar or CRSP rows and is viewed for every family
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]
MIN_PRIOR_BINS = 200  # burn-in for the causal implied-move tercile (as the 2026-11-10 study)
HIST_N, HIST_MIN = 8, 4  # own-history window and minimum
CHARS_MAX_AGE_D = 62
PEER_WINDOW_D = 7  # calendar days, about five sessions
EDGAR_LOOKBACK_D = 100  # 8-K item window before entry, about one quarter
EDGAR_MIN_HISTORY_D = 120
ENTRY_HOUR_ET = 15.98  # 15:59 New York


def funnel(label: str, n: int, of: int | None = None) -> None:
    print(f"funnel {label}: {n}" + (f" of {of}" if of is not None else ""))


# ── panel ──


def load_panel() -> pd.DataFrame:
    d = pd.read_parquet(PANEL)
    funnel("panel rows status ok (2013-26)", len(d))
    d = d[d["announce_date"].dt.year <= LAST_YEAR].copy()
    funnel(f"announce year <= {LAST_YEAR}", len(d))
    drop = [c for c in d.columns if c.startswith("V") or c in ("sim_pct", "ca_abs", "y")]
    d = d.drop(columns=drop)
    for c in ("entry_date", "exit_date", "expiry", "announce_date"):
        d[c] = pd.to_datetime(d[c]).astype("datetime64[ns]")
    if d.duplicated(["ticker", "entry_date"]).any():
        raise ValueError("panel not unique on ticker, entry_date")
    f = pd.read_parquet(FEATURES)
    f["entry_date"] = pd.to_datetime(f["entry_date"]).astype("datetime64[ns]")
    keep = [
        "ticker", "entry_date", "front_t", "front_bid", "front_ask", "front_mid", "front_iv",
        "s1_t", "s1_iv", "s1_bid", "s1_ask", "s1_mid", "jsplit_jump_var", "jsplit_valid",
    ]  # fmt: skip
    d = d.merge(f[keep], on=["ticker", "entry_date"], how="left", validate="one_to_one")
    z = pd.read_parquet(ZOO)
    z["entry_date"] = pd.to_datetime(z["entry_date"]).astype("datetime64[ns]")
    zk = [
        "ticker", "entry_date", "trailing_rv", "skew_25d", "variance_risk_premium", "bkm_skew",
        "bkm_kurt", "vix", "vix_chg_20d", "is_amc", "season_pos", "sic1", "shift",
    ]  # fmt: skip
    z = z[zk].drop_duplicates(["ticker", "entry_date"])
    d = d.merge(z, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    funnel("with model-zoo surface row", int(d["skew_25d"].notna().sum()), len(d))

    # outcomes
    d["pnl_margin"] = d["B"]  # net, touch, next-day buy-back, fraction of margin
    d["pnl_prem"] = d["B"] * d["m0"] / d["mid0"]  # same, per unit of entry mid premium
    d["ratio"] = d["abs_move"] / d["implied_move"]
    d["dte"] = (d["expiry"] - d["exit_date"]).dt.days
    d["spread_pct"] = (d["front_ask"] - d["front_bid"]) / d["front_mid"]
    d["term_slope"] = d["front_iv"] - d["s1_iv"]
    tot = d["front_iv"] ** 2 * d["front_t"]
    d["jump_share"] = np.where(
        d["jsplit_valid"].fillna(False).astype(bool) & (tot > 0), d["jsplit_jump_var"] / tot, np.nan
    )
    d["session"] = np.where(d["announce_date"] == d["exit_date"], "bmo", "amc")
    d["dow_entry"] = d["entry_date"].dt.dayofweek
    d["year"] = d["announce_date"].dt.year
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    d["im_bin"] = causal_bins(
        d["implied_move"].to_numpy(float), d["announce_date"], 3, MIN_PRIOR_BINS
    )
    d["cell"] = d["im_bin"] * 10 + pd.Categorical(d["tenor"], TENOR_LABELS).codes
    funnel("finite pnl_prem", int(np.isfinite(d["pnl_prem"]).sum()), len(d))
    return d


# ── CRSP price path ──


def crsp_features(d: pd.DataFrame) -> pd.DataFrame:
    c = pd.read_parquet(CRSP)
    c["date"] = pd.to_datetime(c["date"]).astype("datetime64[ns]")
    c = c.sort_values(["permno", "date"])
    for k in ("prc", "ret", "cfacpr", "bid", "ask"):
        c[k] = pd.to_numeric(c[k], errors="coerce")
    c["prc"] = c["prc"].abs()
    c["adj"] = c["prc"] / c["cfacpr"]
    by = {int(k): g.reset_index(drop=True) for k, g in c.groupby("permno")}
    cols: dict[str, list[float]] = {
        k: []
        for k in [
            "px_prev", "ret_5d", "ret_20d", "ret_60d", "ret_250d", "pos_52w", "dist_52w_high",
            "dist_52w_low", "rv_5d", "rv_20d", "rv_60d", "max_abs_ret_60d", "stock_spread_bps",
            "listed_days", "signed_react", "ret_entry_day",
        ]
    }  # fmt: skip
    miss = 0
    for pn, t0, t1 in zip(d["permno"], d["entry_date"], d["exit_date"], strict=True):
        g = by.get(int(pn)) if np.isfinite(pn) else None
        row = dict.fromkeys(cols, np.nan)
        if g is not None:
            dates = g["date"].to_numpy()
            j = int(np.searchsorted(dates, np.datetime64(t0), side="left"))  # first row >= entry
            if j >= 2:
                a = g["adj"].to_numpy(float)
                r = g["ret"].to_numpy(float)
                p = j - 1  # last close strictly before the entry session
                row["px_prev"] = float(g["prc"].iloc[p])
                for name, k in (("ret_5d", 5), ("ret_20d", 20), ("ret_60d", 60), ("ret_250d", 250)):
                    if p - k >= 0:
                        row[name] = a[p] / a[p - k] - 1.0
                w = a[max(0, p - 251) : p + 1]
                if len(w) >= 120:
                    hi, lo = np.nanmax(w), np.nanmin(w)
                    row["pos_52w"] = (a[p] - lo) / (hi - lo) if hi > lo else np.nan
                    row["dist_52w_high"] = a[p] / hi - 1.0
                    row["dist_52w_low"] = a[p] / lo - 1.0
                for name, k in (("rv_5d", 5), ("rv_20d", 20), ("rv_60d", 60)):
                    if p - k + 1 >= 1:
                        row[name] = float(np.nanstd(r[p - k + 1 : p + 1]) * np.sqrt(252))
                if p - 59 >= 1:
                    row["max_abs_ret_60d"] = float(np.nanmax(np.abs(r[p - 59 : p + 1])))
                bid, ask = g["bid"].to_numpy(float), g["ask"].to_numpy(float)
                sp = (ask[max(0, p - 19) : p + 1] - bid[max(0, p - 19) : p + 1]) / g["prc"].to_numpy(
                    float
                )[max(0, p - 19) : p + 1]
                row["stock_spread_bps"] = float(np.nanmedian(sp) * 1e4)
                row["listed_days"] = float((np.datetime64(t0) - dates[0]) / np.timedelta64(1, "D"))
                # outcome description for the case file, not a feature
                j1 = int(np.searchsorted(dates, np.datetime64(t1), side="left"))
                if j1 < len(dates) and dates[j1] == np.datetime64(t1) and j < len(dates):
                    if dates[j] == np.datetime64(t0):
                        row["signed_react"] = a[j1] / a[j] - 1.0
                        row["ret_entry_day"] = r[j]  # known at 16:00, one minute after entry
        else:
            miss += 1
        for k in cols:
            cols[k].append(row[k])
    funnel("no CRSP path for permno", miss, len(d))
    out = d.assign(**cols)
    funnel("price-path features defined (ret_250d)", int(out["ret_250d"].notna().sum()), len(d))
    return out


# ── calendar: own reaction history, timing habit, peers ──


def calendar_table(d: pd.DataFrame) -> pd.DataFrame:
    """Every calendar announcement with its CRSP reaction return, for history and peers."""
    cal = pd.read_parquet(CAL)
    cal["announce_date"] = pd.to_datetime(cal["announce_date"]).astype("datetime64[ns]")
    pmap = (
        d.dropna(subset=["permno"]).sort_values("entry_date").groupby("ticker")["permno"].last()
    )
    cal["permno"] = cal["ticker"].map(pmap)
    funnel("calendar rows", len(cal))
    cal = cal.dropna(subset=["permno"]).copy()
    funnel("calendar rows with permno", len(cal))
    c = pd.read_parquet(CRSP, columns=["permno", "date", "ret"])
    c["date"] = pd.to_datetime(c["date"]).astype("datetime64[ns]")
    c["ret"] = pd.to_numeric(c["ret"], errors="coerce")
    c = c.sort_values(["permno", "date"])
    by = {int(k): (g["date"].to_numpy(), g["ret"].to_numpy(float)) for k, g in c.groupby("permno")}
    react, rdate, sig = [], [], []
    for pn, a, s in zip(cal["permno"], cal["announce_date"], cal["session"], strict=True):
        dates, r = by.get(int(pn), (np.array([], "datetime64[ns]"), np.array([])))
        j = int(np.searchsorted(dates, np.datetime64(a), side="left"))
        if s == "amc":
            j = int(np.searchsorted(dates, np.datetime64(a), side="right"))
        if 61 <= j < len(dates):
            react.append(r[j])
            rdate.append(dates[j])
            sig.append(float(np.nanstd(r[j - 61 : j - 1])))
        else:
            react.append(np.nan)
            rdate.append(np.datetime64("NaT"))
            sig.append(np.nan)
    cal["react"] = react
    cal["react_date"] = pd.to_datetime(rdate)
    cal["sigma_pre"] = sig
    cal["z_react"] = cal["react"].abs() / cal["sigma_pre"]
    funnel("calendar reactions defined", int(cal["react"].notna().sum()), len(cal))
    return cal.sort_values(["ticker", "announce_date"]).reset_index(drop=True)


def history_features(d: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    by = {t: g.reset_index(drop=True) for t, g in cal.groupby("ticker")}
    pan = {t: g for t, g in d.groupby("ticker")}
    names = [
        "hist_n", "hist_abs_mean", "hist_abs_max", "hist_abs_med", "hist_z_mean", "hist_z_max",
        "gap_prev_d", "yoy_shift_d", "dow_same_share", "session_switch", "im_rel_own",
        "ratio_prev_mean", "prev_tail", "n_prior_panel", "im_prev",
    ]  # fmt: skip
    out: dict[str, list[float]] = {k: [] for k in names}
    for t, ann, t0, sess, im in zip(
        d["ticker"], d["announce_date"], d["entry_date"], d["session"], d["implied_move"],
        strict=True,
    ):  # fmt: skip
        row = dict.fromkeys(names, np.nan)
        g = by.get(t)
        if g is not None:
            prior = g[(g["react_date"] < t0) & g["react"].notna()].tail(HIST_N)
            row["hist_n"] = float(len(prior))
            if len(prior) >= HIST_MIN:
                a = prior["react"].abs().to_numpy()
                row["hist_abs_mean"], row["hist_abs_max"] = float(a.mean()), float(a.max())
                row["hist_abs_med"] = float(np.median(a))
                z = prior["z_react"].to_numpy()
                row["hist_z_mean"], row["hist_z_max"] = float(np.nanmean(z)), float(np.nanmax(z))
            pa = g[g["announce_date"] < ann]
            if len(pa) >= 1:
                row["gap_prev_d"] = float((ann - pa["announce_date"].iloc[-1]).days)
            if len(pa) >= 4:
                # same fiscal quarter one year earlier: the announcement four back, if 300-430 days
                ref = pa["announce_date"].iloc[-4]
                gap = (ann - ref).days
                if 300 <= gap <= 430:
                    row["yoy_shift_d"] = float(gap - 364)
                last = pa.tail(HIST_N)
                row["dow_same_share"] = float((last["announce_date"].dt.dayofweek == ann.dayofweek).mean())
                mode = last["session"].replace({"dmh": "bmo"}).mode()
                row["session_switch"] = float(sess != mode.iloc[0])
        p = pan[t]
        pp = p[p["exit_date"] < t0].tail(HIST_N)
        row["n_prior_panel"] = float(len(pp))
        if len(pp) >= 3:
            row["im_rel_own"] = float(im / pp["implied_move"].median())
            row["ratio_prev_mean"] = float(pp["ratio"].mean())
            row["prev_tail"] = float((pp["ratio"] > 2).any())
        if len(pp) >= 1:
            row["im_prev"] = float(im / pp["implied_move"].iloc[-1])
        for k in names:
            out[k].append(row[k])
    res = d.assign(**out)
    res["im_over_hist"] = res["implied_move"] / res["hist_abs_mean"]
    res["im_over_histmax"] = res["implied_move"] / res["hist_abs_max"]
    for k in ("hist_abs_mean", "yoy_shift_d", "dow_same_share", "im_rel_own"):
        funnel(f"history feature {k} defined", int(res[k].notna().sum()), len(res))
    return res


def chars_features(d: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "permno", "eom", "gics", "market_equity", "age", "bidaskhl_21d", "turnover_126d",
        "rvol_21d", "ivol_capm_252d", "beta_60m", "o_score", "z_score", "be_me", "ni_me",
        "saleq_gr1", "niq_su", "saleq_su", "earnings_variability", "rmax5_21d", "iskew_capm_21d",
        "dolvol_126d", "debt_me", "f_score", "ret_12_1", "eqnpo_12m",
    ]  # fmt: skip
    ch = pd.read_parquet(CHARS, columns=cols).dropna(subset=["permno"])
    ch["eom"] = pd.to_datetime(ch["eom"]).astype("datetime64[ns]")
    ch["permno"] = ch["permno"].astype("int64")
    ch["me_pct"] = ch.groupby("eom")["market_equity"].rank(pct=True)
    ch = ch.sort_values("eom").rename(columns={"eom": "chars_eom"})
    left = d[d["permno"].notna()].copy()
    left["permno"] = left["permno"].astype("int64")
    m = pd.merge_asof(
        left.sort_values("entry_date")[["ticker", "entry_date", "permno"]],
        ch,
        left_on="entry_date",
        right_on="chars_eom",
        by="permno",
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=CHARS_MAX_AGE_D),
    )
    out = d.merge(m.drop(columns=["permno"]), on=["ticker", "entry_date"], how="left")
    funnel("characteristics row matched", int(out["chars_eom"].notna().sum()), len(out))
    # sector: latest known code, else the name's first code (static classification fallback)
    first = ch.dropna(subset=["gics"]).groupby("permno")["gics"].first()
    g = out["gics"].fillna(out["permno"].map(first))
    out["gics2"] = g.map(lambda x: str(int(x))[:2] if pd.notna(x) else None)
    out["gics6"] = g.map(lambda x: str(int(x))[:6] if pd.notna(x) else None)
    funnel("sector code present", int(out["gics6"].notna().sum()), len(out))
    return out


def peer_features(d: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Sector peers that reacted in the prior five sessions: count, standardised size, ratio."""
    g6 = d.dropna(subset=["gics6"]).groupby("ticker")["gics6"].last()
    cal = cal.assign(gics6=cal["ticker"].map(g6)).dropna(subset=["gics6", "react_date"])
    cal_by = {k: g for k, g in cal.groupby("gics6")}
    pan_by = {k: g for k, g in d.dropna(subset=["gics6"]).groupby("gics6")}
    names = [
        "peer_n_5s", "peer_z_mean_5s", "peer_z_max_5s", "peer_ratio_mean_5s", "peer_ratio_max_5s",
        "peer_n_30d", "peer_ratio_mean_30d", "peer_panel_n_5s",
    ]  # fmt: skip
    out: dict[str, list[float]] = {k: [] for k in names}
    for t, g, t0 in zip(d["ticker"], d["gics6"], d["entry_date"], strict=True):
        row = dict.fromkeys(names, np.nan)
        if g is not None and g in cal_by:
            c = cal_by[g]
            c = c[(c["ticker"] != t) & (c["react_date"] < t0)]
            w = c[c["react_date"] >= t0 - pd.Timedelta(days=PEER_WINDOW_D)]
            row["peer_n_5s"] = float(len(w))
            row["peer_n_30d"] = float((c["react_date"] >= t0 - pd.Timedelta(days=30)).sum())
            if len(w):
                row["peer_z_mean_5s"] = float(w["z_react"].mean())
                row["peer_z_max_5s"] = float(w["z_react"].max())
            p = pan_by[g]
            p = p[(p["ticker"] != t) & (p["exit_date"] < t0)]
            pw = p[p["exit_date"] >= t0 - pd.Timedelta(days=PEER_WINDOW_D)]
            row["peer_panel_n_5s"] = float(len(pw))
            if len(pw):
                row["peer_ratio_mean_5s"] = float(pw["ratio"].mean())
                row["peer_ratio_max_5s"] = float(pw["ratio"].max())
            p30 = p[p["exit_date"] >= t0 - pd.Timedelta(days=30)]
            if len(p30):
                row["peer_ratio_mean_30d"] = float(p30["ratio"].mean())
        for k in names:
            out[k].append(row[k])
    res = d.assign(**out)
    funnel("peer reacted in prior 5 sessions (calendar)", int((res["peer_n_5s"] > 0).sum()), len(d))
    funnel("peer ratio in prior 5 sessions (panel)", int(res["peer_ratio_mean_5s"].notna().sum()), len(d))
    return res


# ── EDGAR ──

ITEM_FLAGS = {
    "exec_change": ["5.02"],
    "restatement": ["4.02"],
    "auditor_change": ["4.01"],
    "material_agreement": ["1.01"],
    "acquisition_done": ["2.01"],
    "restructuring": ["2.05"],
    "impairment": ["2.06"],
    "prelim_results": ["2.02"],
    "reg_fd": ["7.01"],
    "debt": ["2.03"],
}
MERGER_FORMS = {"425", "DEFM14A", "PREM14A", "S-4", "S-4/A", "SC TO-T", "SC 14D9", "SC TO-T/A"}
LATE_FORMS = {"NT 10-K", "NT 10-Q"}
AMEND_FORMS = {"10-K/A", "10-Q/A"}


def _load_filings(cik: int) -> tuple[pd.DataFrame, str | None] | None:
    main = EDGAR / "submissions" / f"CIK{cik:010d}.json"
    if not main.exists():
        return None
    j = json.loads(main.read_text(encoding="utf-8"))
    parts = [j["filings"]["recent"]]
    for extra in sorted((EDGAR / "submissions").glob(f"CIK{cik:010d}-submissions-*.json")):
        parts.append(json.loads(extra.read_text(encoding="utf-8")))
    f = pd.concat(
        [pd.DataFrame({"form": p["form"], "items": p["items"], "acc": p["acceptanceDateTime"]}) for p in parts],
        ignore_index=True,
    )
    f["ts"] = pd.to_datetime(f["acc"], utc=True, errors="coerce")
    f = f.dropna(subset=["ts"])
    f["et"] = f["ts"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    return f.sort_values("et").reset_index(drop=True), j.get("fiscalYearEnd")


def edgar_features(d: pd.DataFrame) -> pd.DataFrame:
    tick = json.loads((EDGAR / "company_tickers.json").read_text(encoding="utf-8"))
    cik_of = {v["ticker"].upper(): int(v["cik_str"]) for v in tick.values()}
    names = [f"e_{k}" for k in ITEM_FLAGS] + [
        "e_merger_form_180d", "e_late_form_365d", "e_amend_form_365d", "e_n8k_100d",
        "e_n8k_nonearn_30d", "e_def", "fiscal_q4", "fye_known",
    ]  # fmt: skip
    out: dict[str, list[float]] = {k: [] for k in names}
    cache: dict[int, tuple[pd.DataFrame, str | None] | None] = {}
    drops = {"no_cik": 0, "no_file": 0, "short_history": 0}
    for t, ann, t0 in zip(d["ticker"], d["announce_date"], d["entry_date"], strict=True):
        row = dict.fromkeys(names, np.nan)
        row["e_def"] = 0.0
        row["fye_known"] = 0.0
        cik = cik_of.get(str(t).upper().replace("-", "."), cik_of.get(str(t).upper()))
        if cik is None:
            drops["no_cik"] += 1
        else:
            if cik not in cache:
                cache[cik] = _load_filings(cik)
            item = cache[cik]
            if item is None:
                drops["no_file"] += 1
            else:
                f, fye = item
                if fye and len(fye) == 4:
                    # fiscal Q4 report: the latest fiscal quarter-end before the announcement is
                    # the fiscal year-end month (current FYE applied to all years; changes are rare)
                    fm = int(fye[:2])
                    qend = (ann - pd.Timedelta(days=12)).to_period("M") - 1
                    k = 0
                    while (qend.month - fm) % 3 != 0 and k < 3:
                        qend -= 1
                        k += 1
                    row["fiscal_q4"] = float(qend.month == fm)
                    row["fye_known"] = 1.0
                cutoff = t0 + pd.Timedelta(hours=ENTRY_HOUR_ET)
                if f["et"].min() > t0 - pd.Timedelta(days=EDGAR_MIN_HISTORY_D):
                    drops["short_history"] += 1
                else:
                    row["e_def"] = 1.0
                    w = f[(f["et"] < cutoff) & (f["et"] >= t0 - pd.Timedelta(days=EDGAR_LOOKBACK_D))]
                    k8 = w[w["form"] == "8-K"]
                    for name, codes in ITEM_FLAGS.items():
                        hit = k8["items"].map(lambda s: any(c in s.split(",") for c in codes))
                        row[f"e_{name}"] = float(hit.any()) if len(k8) else 0.0
                    row["e_n8k_100d"] = float(len(k8))
                    k30 = k8[k8["et"] >= t0 - pd.Timedelta(days=30)]
                    row["e_n8k_nonearn_30d"] = float(
                        (~k30["items"].str.contains("2.02", regex=False)).sum()
                    )
                    w180 = f[(f["et"] < cutoff) & (f["et"] >= t0 - pd.Timedelta(days=180))]
                    row["e_merger_form_180d"] = float(w180["form"].isin(MERGER_FORMS).any())
                    w365 = f[(f["et"] < cutoff) & (f["et"] >= t0 - pd.Timedelta(days=365))]
                    row["e_late_form_365d"] = float(w365["form"].isin(LATE_FORMS).any())
                    row["e_amend_form_365d"] = float(w365["form"].isin(AMEND_FORMS).any())
        for k in names:
            out[k].append(row[k])
    res = d.assign(**out)
    print(f"funnel EDGAR drops: {drops}")
    funnel("EDGAR window defined", int(res["e_def"].sum()), len(res))
    print("funnel EDGAR defined by year:", res.groupby("year")["e_def"].sum().astype(int).to_dict())
    funnel("fiscal year-end known", int(res["fye_known"].sum()), len(res))
    return res


def main() -> None:
    d = load_panel()
    d = crsp_features(d)
    cal = calendar_table(d)
    d = chars_features(d)
    d = history_features(d, cal)
    d = peer_features(d, cal)
    d = edgar_features(d)
    d["log_me"] = np.log(d["market_equity"])
    d["me_bucket"] = pd.cut(d["me_pct"], [0, 0.9, 0.97, 1.0], labels=["below p90", "p90-97", "top 3%"]).astype(str)
    d["im_over_rv"] = d["implied_move"] / (d["rv_60d"] / np.sqrt(252))
    d["quiet_ratio"] = d["rv_5d"] / d["rv_60d"]
    d["run_abs_5d_over_im"] = d["ret_5d"].abs() / d["implied_move"]
    d["block"] = np.where(d["year"] <= 2021, "discovery", "heldout")
    d["subperiod"] = np.where(d["year"] <= 2017, "2013-17", np.where(d["year"] <= 2021, "2018-21", "2022-24"))
    funnel("ledger rows", len(d))
    print("funnel by block:", d["block"].value_counts().to_dict())
    print("funnel scorable (causal tercile assigned) by block:", d[d["im_bin"] >= 0]["block"].value_counts().to_dict())
    d.to_parquet(HERE / "ledger_all.parquet", index=False)
    cal.to_parquet(HERE / "calendar_reactions.parquet", index=False)
    print(f"written {HERE / 'ledger_all.parquet'} with {d.shape[1]} columns")


if __name__ == "__main__":
    main()
