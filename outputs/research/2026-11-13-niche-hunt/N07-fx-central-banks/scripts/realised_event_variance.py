"""
realised_event_variance.py
Physical-measure event variance for FX pairs around central-bank decisions (lane N07).

Descriptive only: no option prices enter. Computes, per (bank, pair), the realised variance
multiple of announcement windows over matched control windows, and the overnight at-the-money
implied vol at which a short straddle over the same window breaks even at the mid. See
`../diagnosis.log` (pre-statement D1, D2) for the design, fixed before this ran.

Usage
-----
    python -I scripts/realised_event_variance.py      # from the lane folder

Inputs are the raw files under `raw/` (Yahoo chart JSON, ECB EA-MPD workbook, BoJ past-meeting
page) and the project's cached US release calendar. Outputs go to `data/`.

References
----------
Altavilla, Brugnolini, Gurkaynak, Motto and Ragusa (2019), Measuring euro area monetary policy,
    Journal of Monetary Economics 108, 162-179 (EA-MPD dates and windows).
Wright (2020), Event-day options, NBER working paper 28306 (event versus same-weekday controls).
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# ── configuration ─────────────────────────────────────────────────────────────

LANE = Path(__file__).resolve().parents[1]
RAW = LANE / "raw"
OUT = LANE / "data"
PROJECT = LANE.parents[3]
US_CAL = PROJECT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"


@dataclass(frozen=True)
class Config:
    # E|Z| for a standard normal: the ATM straddle is worth this many standard deviations.
    straddle_k: float = float(np.sqrt(2.0 / np.pi))
    # OTC overnight vol is quoted ACT/365 over one calendar day; this reproduces the quoted
    # break-evens in the verified wraps to the pip (13.5 vol at 1.15 gives 65 pips).
    day_frac: float = 1.0 / 365.0
    bootstrap_draws: int = 10_000
    seed: int = 20261113
    # Daily FX bars with |r| above this are treated as data errors and dropped, with a count.
    max_abs_daily: float = 0.08
    # Exclusion buffer around any event when choosing controls, in business days.
    buffer_bdays: int = 1
    ny_cut_hour: int = 10


CFG = Config()

# ── loaders ───────────────────────────────────────────────────────────────────


def load_yahoo(pair: str, freq: str) -> pd.Series:
    """Close series from a Yahoo chart JSON, UTC index, NaN closes dropped with a count."""
    body = json.loads((RAW / f"{pair}_{freq}.json").read_text())
    res = body["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    q = res["indicators"]["quote"][0]
    s = pd.Series(q["close"], index=ts, dtype=float)
    n0 = len(s)
    s = s.dropna()
    s = s[~s.index.duplicated(keep="last")]
    print(f"[load] {pair} {freq}: {n0} bars, {n0 - len(s)} NaN or duplicate dropped")
    return s


def ecb_dates() -> pd.DatetimeIndex:
    d = pd.read_excel(RAW / "eampd.xlsx", sheet_name="Monetary Event Window")
    # The column mixes Excel datetimes (to 2023) with dd/mm/yyyy strings (2024 on); parsing
    # both as strings with dayfirst swaps day and month on the datetimes, so split them.
    out = [
        pd.Timestamp(v) if not isinstance(v, str) else pd.to_datetime(v, format="%d/%m/%Y")
        for v in d["date"]
    ]
    dates = pd.DatetimeIndex(out).normalize()
    weekend = int((dates.dayofweek >= 5).sum())
    if weekend:
        raise RuntimeError(f"EA-MPD parse produced {weekend} weekend dates")
    return pd.DatetimeIndex(sorted(dates.unique()))


def boj_dates() -> pd.DatetimeIndex:
    t = (RAW / "boj.html").read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))
    parts = re.split(r"(\d{4}) Table : \d{4}", s)
    mon = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "June": 6, "July": 7, "Aug": 8,
           "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    mname = "|".join(mon)
    day = r"\((?:Mon|Tues|Wed|Thurs|Fri|Sat|Sun)\.\)"
    pat = re.compile(rf"({mname})\.? (\d+) {day}, (?:({mname})\.? )?(\d+) {day}")
    out = []
    for k in range(1, len(parts), 2):
        year = int(parts[k])
        for m in pat.finditer(parts[k + 1]):
            month = mon[m.group(3) or m.group(1)]
            out.append(pd.Timestamp(year=year, month=month, day=int(m.group(4))))
    if not out:
        raise RuntimeError("BoJ parser found no meetings")
    return pd.DatetimeIndex(sorted(set(out)))


def us_dates() -> pd.DataFrame:
    cal = pd.read_csv(US_CAL, parse_dates=["date"])
    return cal


# ── statistics ────────────────────────────────────────────────────────────────


def boot_ci(x: np.ndarray, fn, rng: np.random.Generator) -> tuple[float, float]:
    idx = rng.integers(0, len(x), size=(CFG.bootstrap_draws, len(x)))
    stats = np.array([fn(x[i]) for i in idx])
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def ratio_ci(ev: np.ndarray, ct: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    ie = rng.integers(0, len(ev), size=(CFG.bootstrap_draws, len(ev)))
    ic = rng.integers(0, len(ct), size=(CFG.bootstrap_draws, len(ct)))
    r = (ev[ie] ** 2).mean(axis=1) / (ct[ic] ** 2).mean(axis=1)
    return float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


def summarise(label: str, ev: np.ndarray, ct: np.ndarray, rng: np.random.Generator) -> dict:
    to_vol = 1.0 / (CFG.straddle_k * np.sqrt(CFG.day_frac))
    m_p = float((ev**2).mean() / (ct**2).mean())
    lo, hi = ratio_ci(ev, ct, rng)
    vf = float(np.abs(ev).mean() * to_vol * 100)
    vf_lo, vf_hi = (v * to_vol * 100 for v in boot_ci(np.abs(ev), np.mean, rng))
    vc = float(np.abs(ct).mean() * to_vol * 100)
    vc_lo, vc_hi = (v * to_vol * 100 for v in boot_ci(np.abs(ct), np.mean, rng))
    row = {
        "label": label, "n_event": len(ev), "n_control": len(ct),
        "M_P": round(m_p, 3), "M_P_lo": round(lo, 3), "M_P_hi": round(hi, 3),
        "v_fair_event": round(vf, 2), "v_fair_event_lo": round(vf_lo, 2),
        "v_fair_event_hi": round(vf_hi, 2),
        "v_fair_control": round(vc, 2), "v_fair_control_lo": round(vc_lo, 2),
        "v_fair_control_hi": round(vc_hi, 2),
        "abs_ratio": round(float(np.abs(ev).mean() / np.abs(ct).mean()), 3),
        "event_share_top5_r2": round(float(np.sort(ev**2)[-5:].sum() / (ev**2).sum()), 3),
    }
    print(f"[{label}] N={len(ev)} vs {len(ct)}: M_P {m_p:.2f} [{lo:.2f}, {hi:.2f}]; "
          f"v_fair event {vf:.2f} [{vf_lo:.2f}, {vf_hi:.2f}] vs control {vc:.2f}")
    return row


# ── daily design (D1) ─────────────────────────────────────────────────────────


def daily_returns(pair: str) -> pd.Series:
    s = load_yahoo(pair, "d")
    # Yahoo FX daily bars are stamped at London midnight, but the close stamped D is the price
    # near the START of London day D (checked against hourly bars 2024-26, correlation 0.87 with
    # the next label against 0.21 with the same label, and against the ECB EA-MPD intraday
    # event moves). So the move over London day D is close(D+1) / close(D).
    lon = s.index.tz_convert("Europe/London")
    s.index = pd.DatetimeIndex(lon.date)
    idx = s.index.to_series()
    gap = (idx.shift(-1) - idx).dt.days
    ok = (gap == 1) | ((idx.dt.weekday == 4) & (gap == 3))
    r = (np.log(s).shift(-1) - np.log(s))[ok.to_numpy()]
    print(f"[clean] {pair} daily: {int((~ok).sum())} bars without a next-day bar dropped")
    bad = r.abs() > CFG.max_abs_daily
    zero = r == 0.0
    print(f"[clean] {pair} daily: {len(r)} returns, {int(bad.sum())} above "
          f"{CFG.max_abs_daily:.0%} dropped, {int(zero.sum())} exact zeros dropped (stale)")
    return r[~bad & ~zero]


def buffer_set(dates: pd.DatetimeIndex) -> set[pd.Timestamp]:
    out: set[pd.Timestamp] = set()
    for d in dates:
        for k in range(-CFG.buffer_bdays, CFG.buffer_bdays + 1):
            out.add((d + pd.offsets.BDay(k)).normalize() if k else d.normalize())
    return out


def d1(rng: np.random.Generator) -> pd.DataFrame:
    ecb, boj = ecb_dates(), boj_dates()
    us = us_dates()
    fomc = pd.DatetimeIndex(us.loc[us["kind"] == "fomc", "date"])
    nfp_cpi = pd.DatetimeIndex(us.loc[us["kind"].isin(["nfp", "cpi"]), "date"])
    all_cb = ecb.append(boj).append(fomc)
    excl = buffer_set(all_cb) | set(nfp_cpi.normalize())
    # Yahoo's daily stamping convention changed around 2011 (ECB event moves correlate with the
    # same label to 2010 and with the next label from 2011), so D1 starts in 2012.
    specs = [
        ("ECB", "EURUSD", ecb, "2012-01-01", "2025-12-31"),
        ("ECB", "EURUSD", ecb, "2012-01-01", "2018-12-31"),
        ("ECB", "EURUSD", ecb, "2019-01-01", "2025-12-31"),
        ("BoJ", "USDJPY", boj, "2012-01-01", "2025-12-31"),
        ("FOMC", "EURUSD", fomc, "2016-01-01", "2026-11-12"),
        ("FOMC", "USDJPY", fomc, "2016-01-01", "2026-11-12"),
        ("FOMC", "AUDUSD", fomc, "2016-01-01", "2026-11-12"),
    ]
    rows = []
    cache: dict[str, pd.Series] = {}
    # Alignment check: the London-day return must carry the ECB's own intraday event move.
    ea = pd.read_excel(RAW / "eampd.xlsx", sheet_name="Monetary Event Window")
    if len(ecb_dates()) != len(ea):
        raise RuntimeError("EA-MPD has duplicate or unsorted dates; alignment check unsafe")
    ea.index = ecb_dates()
    r_eur = cache.setdefault("EURUSD", daily_returns("EURUSD"))
    j = pd.concat([ea["EURUSD"], r_eur * 100], axis=1, join="inner").dropna()
    j = j[j.index >= "2012-01-01"]
    print(f"[align] corr(EA-MPD EURUSD event-window move, London-day return) 2012-2025 = "
          f"{j.corr().iloc[0, 1]:.2f}, N={len(j)}")
    for bank, pair, dates, a, b in specs:
        r = cache.setdefault(pair, daily_returns(pair))
        r = r[(r.index >= a) & (r.index <= b)]
        ev_dates = [d for d in dates if a <= str(d.date()) <= b]
        ev = r.reindex(ev_dates)
        missing = int(ev.isna().sum())
        ev = ev.dropna()
        wd = sorted({d.weekday() for d in ev.index})
        ct = r[[d.weekday() in wd and d not in excl for d in r.index]]
        print(f"[funnel] {bank}/{pair} {a[:4]}-{b[:4]}: {len(ev_dates)} events, "
              f"{missing} without a clean daily return, controls on weekdays {wd}")
        row = summarise(f"D1 {bank} {pair} {a[:4]}-{b[:4]}", ev.to_numpy(), ct.to_numpy(), rng)
        row.update({"design": "D1 daily London day", "missing_events": missing})
        rows.append(row)
    return pd.DataFrame(rows)


# ── hourly design (D2) ────────────────────────────────────────────────────────


def ny_cut_price(h: pd.Series, day: pd.Timestamp) -> float:
    """Price at 10:00 New York on `day`: close of the last bar starting before 10:00 NY."""
    t = pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta(
        hours=CFG.ny_cut_hour)
    t_utc = t.tz_convert("UTC")
    win = h[(h.index < t_utc) & (h.index >= t_utc - pd.Timedelta(hours=1))]
    return float(win.iloc[-1]) if len(win) else np.nan


def window_return(h: pd.Series, expiry_day: pd.Timestamp) -> float:
    start = expiry_day - pd.offsets.BDay(1)
    p0, p1 = ny_cut_price(h, start), ny_cut_price(h, expiry_day)
    return float(np.log(p1 / p0)) if p0 > 0 and p1 > 0 else np.nan


def d2(rng: np.random.Generator) -> pd.DataFrame:
    ecb, boj = ecb_dates(), boj_dates()
    us = us_dates()
    fomc = pd.DatetimeIndex(us.loc[us["kind"] == "fomc", "date"])
    nfp_cpi = pd.DatetimeIndex(us.loc[us["kind"].isin(["nfp", "cpi"]), "date"])
    # Expiry session whose 10:00 NY cut first follows the announcement.
    # ECB 08:15 NY (14:15 CET): same day. FOMC 14:00 NY: next business day.
    # BoJ about 22:00-23:30 NY on the evening before the Tokyo date: the Tokyo date itself.
    expiry = {
        "ECB": ecb,
        "FOMC": pd.DatetimeIndex([d + pd.offsets.BDay(1) for d in fomc]),
        "BoJ": boj,
    }
    excl = buffer_set(expiry["ECB"].append(expiry["FOMC"]).append(expiry["BoJ"]))
    excl |= {d.normalize() for d in nfp_cpi}
    excl |= {(d + pd.offsets.BDay(1)).normalize() for d in nfp_cpi}
    specs = [("ECB", "EURUSD"), ("BoJ", "USDJPY"), ("FOMC", "EURUSD"), ("FOMC", "USDJPY"),
             ("FOMC", "AUDUSD")]
    rows = []
    hcache: dict[str, pd.Series] = {}
    for bank, pair in specs:
        h = hcache.setdefault(pair, load_yahoo(pair, "h"))
        first = h.index.min().tz_convert("America/New_York").normalize().tz_localize(None)
        last = h.index.max().tz_convert("America/New_York").normalize().tz_localize(None)
        days = pd.bdate_range(first + pd.offsets.BDay(2), last - pd.offsets.BDay(1))
        ev_days = [d for d in expiry[bank] if days[0] <= d <= days[-1]]
        ev = np.array([window_return(h, d) for d in ev_days])
        wd = sorted({d.weekday() for d in ev_days})
        ct_days = [d for d in days if d.weekday() in wd and d.normalize() not in excl]
        ct = np.array([window_return(h, d) for d in ct_days])
        print(f"[funnel] D2 {bank}/{pair}: {len(ev_days)} events, {int(np.isnan(ev).sum())} "
              f"without both cut prices; {len(ct_days)} controls, {int(np.isnan(ct).sum())} "
              f"without both cut prices")
        ev, ct = ev[~np.isnan(ev)], ct[~np.isnan(ct)]
        if len(ev) < 5 or len(ct) < 20:
            raise RuntimeError(f"D2 {bank}/{pair}: too few windows ({len(ev)}, {len(ct)})")
        row = summarise(f"D2 {bank} {pair} NY cut", ev, ct, rng)
        row.update({"design": "D2 hourly 10:00 NY to 10:00 NY", "missing_events": 0})
        rows.append(row)
    return pd.DataFrame(rows)


# ── anecdotes (D3) ────────────────────────────────────────────────────────────

# Verified by fetch on 2026-11-13; see sources.csv. Expiry is the session whose 10:00 NY cut
# ends the overnight option that the wrap describes.
ANECDOTES = [
    ("FOMC 2025-06-18", "EURUSD", "2025-06-19", 13.5, 65, 11.0),
    ("FOMC 2025-06-18", "USDJPY", "2025-06-19", 13.5, 81, 10.5),
    ("FOMC 2025-06-18", "AUDUSD", "2025-06-19", 15.0, 59, 11.0),
    ("BoC 2024-12-11", "USDCAD", "2024-12-11", 13.5, 80, np.nan),
    ("ECB 2024-12-12 (US PPI same morning)", "EURUSD", "2024-12-12", 19.0, 83, np.nan),
    ("SNB 2024-12-12", "USDCHF", "2024-12-12", 17.5, 64, 12.0),
    ("BoJ 2026-10-30", "USDJPY", "2026-10-30", 12.0, 80, 8.0),
]


def d3() -> pd.DataFrame:
    rows = []
    for event, pair, exp, vol, be_pips, base in ANECDOTES:
        h = load_yahoo(pair, "h")
        d = pd.Timestamp(exp)
        p0 = ny_cut_price(h, d - pd.offsets.BDay(1))
        p1 = ny_cut_price(h, d)
        pip = 0.01 if "JPY" in pair else 0.0001
        move = abs(p1 - p0) / pip
        implied_be = CFG.straddle_k * vol / 100 * np.sqrt(CFG.day_frac) * p0 / pip
        rows.append({
            "event": event, "pair": pair, "expiry_ny_cut": exp, "quoted_on_vol": vol,
            "quoted_breakeven_pips": be_pips, "recomputed_breakeven_pips": round(implied_be, 1),
            "realised_move_pips": round(move, 1),
            # Scored on the break-even recomputed from the quoted vol, because one wrap's pip
            # figure (AUDUSD) is inconsistent with its own vol.
            "short_straddle_mid_pnl_share_of_premium": round(1 - move / implied_be, 3),
            "quoted_base_on_vol": base,
            "M_Q_vs_base": round((vol / base) ** 2, 2) if base == base else np.nan,
        })
    df = pd.DataFrame(rows)
    print(df.to_string())
    return df


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(CFG.seed)
    res = pd.concat([d1(rng), d2(rng)], ignore_index=True)
    res.to_csv(OUT / "realised_event_variance.csv", index=False)
    d3().to_csv(OUT / "anecdotes_on_vol.csv", index=False)
    print(f"[done] wrote {OUT / 'realised_event_variance.csv'} and anecdotes_on_vol.csv")


if __name__ == "__main__":
    main()
