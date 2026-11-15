"""s01_build.py: N08 trade panel. SPY, QQQ, IWM straddles around scheduled US macro releases.

Builds one row per (family, ticker, session) for three trades, every NYSE session 2016-2026, so that
release days and matched non-release controls come from the same valuation path:

- T1 overnight: the frozen index study's B3 rows (15:59 on t to 10:00 on t+1, shortest expiry
  strictly after t+1), read from its priced_trades.parquet, not recomputed.
- T2 intraday: 10:00 on d to 15:59 on d, shortest expiry strictly after d with a two-sided pair at
  10:00, strike minimising |C mid - P mid|, sold at the 10:00 bids and bought at the 15:59 asks.
  Built here from data/cache/index_chains with the frozen study's quote rules.
- T3 settle: the frozen next-day-expiry rows (sell the t+1 expiry at 15:59 on t, settle at t+1).

Flags every session with the release kinds on it (CPI, payrolls, FOMC from the frozen calendar; PCE
from ALFRED release 54). No outcome is summarised here; the scorer does that.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s01_build.py

References
----------
Muravyev and Ni (2020), Why do option returns change sign from day to night?, JFE.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.engine.stats import nyse_sessions

# ── paths and constants ──────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CHAINS = ROOT / "data" / "cache" / "index_chains"
MACRO = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"
PCE = HERE / "pce_release_dates_alfred_rid54.csv"
PRICED = ROOT / "outputs" / "research" / "2026-11-01-index-event-crush" / "priced_trades.parquet"
NDE = ROOT / "outputs" / "research" / "2026-11-02-next-day-expiry-settle" / "trades.parquet"
LANEG = ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt-2" / "laneG-index-event-vol"
TICKERS = ("SPY", "QQQ", "IWM")
START, END = pd.Timestamp("2016-01-04"), pd.Timestamp("2026-10-30")
COMMISSION = 0.0065  # USD per share per leg per side, as frozen in the index study
MARGIN_SPOT_FRAC = 0.15  # broad-based ETF short straddle approximation, as frozen
SESSIONS = [d for d in nyse_sessions(START, END + pd.Timedelta(days=10)) if d <= END]


# ── quotes ───────────────────────────────────────────────────────────────────
def load_quotes(tk: str, d: pd.Timestamp, snap: str) -> pd.DataFrame | None:
    p = CHAINS / f"{tk}_{d.date()}_{snap}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if df.empty:
        return None
    df = df.sort_values("ts_recv").groupby("symbol", as_index=False).last()
    sym = df["symbol"].astype(str)
    return pd.DataFrame(
        {
            "expiry": pd.to_datetime(sym.str[6:12], format="%y%m%d"),
            "cp": sym.str[12],
            "strike": sym.str[13:21].astype(int) / 1000.0,
            "bid": df["bid_px_00"].astype(float),
            "ask": df["ask_px_00"].astype(float),
        }
    )


def intraday_trade(job: tuple[str, pd.Timestamp]) -> dict[str, object]:
    """T2: 10:00 entry, 15:59 exit on the same session."""
    tk, d = job
    rec: dict[str, object] = {"ticker": tk, "date": d}
    q0 = load_quotes(tk, d, "1000")
    if q0 is None:
        rec["status"] = "no_entry_snapshot"
        return rec
    two = q0[(q0["bid"] > 0) & (q0["ask"] >= q0["bid"]) & np.isfinite(q0["ask"])]
    two = two[two["expiry"] > d]
    chosen = None
    for exp in sorted(two["expiry"].unique()):
        g = two[two["expiry"] == exp]
        piv = g.pivot_table(index="strike", columns="cp", values=["bid", "ask"]).dropna()
        if ("bid", "C") in piv.columns and ("bid", "P") in piv.columns and not piv.empty:
            chosen = (pd.Timestamp(exp), piv)
            break
    if chosen is None:
        rec["status"] = "no_two_sided_pair"
        return rec
    exp, piv = chosen
    cm = (piv[("bid", "C")] + piv[("ask", "C")]) / 2
    pm = (piv[("bid", "P")] + piv[("ask", "P")]) / 2
    k = float((cm - pm).abs().idxmin())
    c0b, c0a = float(piv.loc[k, ("bid", "C")]), float(piv.loc[k, ("ask", "C")])
    p0b, p0a = float(piv.loc[k, ("bid", "P")]), float(piv.loc[k, ("ask", "P")])
    p0 = (c0b + c0a + p0b + p0a) / 2
    fwd0 = k + (c0b + c0a) / 2 - (p0b + p0a) / 2
    rec.update({"expiry": exp, "strike": k, "dte": float((exp - d).days), "p0": p0, "fwd0": fwd0,
                "c0b": c0b, "c0a": c0a, "p0b": p0b, "p0a": p0a})
    q1 = load_quotes(tk, d, "1559")
    if q1 is None:
        rec["status"] = "no_exit_snapshot"
        return rec
    leg = q1[(q1["expiry"] == exp) & (q1["strike"] == k)].set_index("cp")
    if "C" not in leg.index or "P" not in leg.index:
        rec["status"] = "no_exit_contract"
        return rec
    c1b, c1a = float(leg.loc["C", "bid"]), float(leg.loc["C", "ask"])
    p1b, p1a = float(leg.loc["P", "bid"]), float(leg.loc["P", "ask"])
    rec.update({"c1b": c1b, "c1a": c1a, "p1b": p1b, "p1a": p1a})
    if not (c1a > 0 and p1a > 0 and np.isfinite(c1a) and np.isfinite(p1a)):
        rec["status"] = "no_exit_ask"
        return rec
    rec["status"] = "ok"
    comm = 4 * COMMISSION
    rec["short_net"] = (c0b + p0b - c1a - p1a - comm) / p0
    rec["long_net"] = (c1b + p1b - c0a - p0a - comm) / p0 if (c1b > 0 and p1b > 0) else np.nan
    two_sided_exit = c1b > 0 and p1b > 0 and c1a >= c1b and p1a >= p1b
    rec["short_mid"] = (p0 - (c1b + c1a + p1b + p1a) / 2) / p0 if two_sided_exit else np.nan
    rec["fwd1"] = k + (c1b + c1a) / 2 - (p1b + p1a) / 2 if two_sided_exit else np.nan
    rec["half_spread_entry"] = (c0a - c0b + p0a - p0b) / 2 / p0
    rec["half_spread_exit"] = (c1a - c1b + p1a - p1b) / 2 / p0 if two_sided_exit else np.nan
    rec["short_net_rom"] = rec["short_net"] * p0 / (p0 + MARGIN_SPOT_FRAC * fwd0)
    return rec


# ── calendar ─────────────────────────────────────────────────────────────────
def calendar() -> pd.DataFrame:
    m = pd.read_csv(MACRO, parse_dates=["date"])[["date", "kind"]]
    p = pd.read_csv(PCE, parse_dates=["date"])[["date", "kind"]]
    cal = pd.concat([m, p], ignore_index=True)
    sess = set(SESSIONS)
    in_win = cal[(cal["date"] >= START) & (cal["date"] <= END)]
    off = in_win[~in_win["date"].isin(sess)]
    print(f"calendar rows in window {len(in_win)}; on non-sessions (dropped) {len(off)}:")
    print(off.groupby("kind")["date"].apply(lambda s: [str(x.date()) for x in s]).to_string())
    cal = in_win[in_win["date"].isin(sess)]
    flags = cal.assign(v=True).pivot_table(index="date", columns="kind", values="v",
                                           aggfunc="any").fillna(False)
    return flags.reindex(pd.Index(SESSIONS, name="date"), fill_value=False).astype(bool)


def main() -> None:
    flags = calendar()
    flags.to_parquet(HERE / "calendar_flags.parquet")
    print("release sessions by kind:", flags.sum().to_dict())

    # T2 intraday, built here
    jobs = [(tk, d) for tk in TICKERS for d in SESSIONS]
    with ProcessPoolExecutor(max_workers=8) as ex:
        t2 = pd.DataFrame(list(ex.map(intraday_trade, jobs, chunksize=64)))
    print("T2 funnel:\n", t2.groupby(["ticker", "status"]).size().unstack(fill_value=0).to_string())

    # attrition check on T2: drops with an entry quote, compared on |intraday forward move| later
    t2["family"] = "T2"
    t2["event_date"] = t2["date"]
    t2["entry"] = t2["date"]

    # T1 overnight, frozen B3 rows
    p = pd.read_parquet(PRICED)
    p = p[p["exit_snap"].astype(str) == "1000"].copy()
    if p.empty:
        raise ValueError("no 10:00-exit rows in the frozen priced trades")
    t1 = pd.DataFrame(
        {
            "family": "T1",
            "ticker": p["ticker"],
            "entry": pd.to_datetime(p["entry"]),
            "event_date": pd.to_datetime(p["exit"]),
            "dte": p["dte"],
            "p0": p["p0"],
            "fwd0": p["fwd0"],
            "fwd1": p["fwd1"],
            "status": p["status"],
            "short_net": p["short_touch_net"],
            "long_net": p["long_touch"] - 4 * COMMISSION / p["p0"],
            "short_mid": p["short_mid"],
            "short_net_rom": p["short_touch_net_rom"],
            "half_spread_entry": (p["c0a"] - p["c0b"] + p["p0a"] - p["p0b"]) / 2 / p["p0"],
            "half_spread_exit": (p["c1a"] - p["c1b"] + p["p1a"] - p["p1b"]) / 2 / p["p0"],
        }
    )
    print("T1 rows", len(t1), t1.groupby("ticker").size().to_dict())

    # T3 next-day-expiry settle, frozen rows
    n = pd.read_parquet(NDE)
    t3 = pd.DataFrame(
        {
            "family": "T3",
            "ticker": n["ticker"],
            "entry": pd.to_datetime(n["entry"]),
            "event_date": pd.to_datetime(n["exit"]),
            "dte": 1.0 * (pd.to_datetime(n["exit"]) - pd.to_datetime(n["entry"])).dt.days,
            "p0": n["p0"],
            "fwd0": n["fwd0"],
            "status": n["status"],
            "short_net": n["N"],
            "short_mid": n["N_mid"],
            "short_net_rom": n["N_rom"],
            "half_spread_entry": n["half_spread"],
        }
    )
    print("T3 rows", len(t3), t3.groupby("ticker").size().to_dict())

    allt = pd.concat([t1, t2.drop(columns=["date"]), t3], ignore_index=True)
    allt["entry"] = pd.to_datetime(allt["entry"])
    allt["event_date"] = pd.to_datetime(allt["event_date"])
    fl = flags.copy()
    for col in ("cpi", "nfp", "fomc", "pce"):
        if col not in fl.columns:
            raise ValueError(f"calendar kind {col} missing")
    allt = allt.join(fl.add_prefix("ev_"), on="event_date")
    allt = allt.join(fl.add_prefix("en_"), on="entry")
    for c in [c for c in allt.columns if c.startswith(("ev_", "en_"))]:
        miss = allt[c].isna().sum()
        if miss:
            print(f"  {c}: {miss} rows outside the session calendar, set False")
        allt[c] = allt[c].astype("boolean").fillna(False).astype(bool)
    allt["weekday"] = allt["entry"].dt.weekday
    allt["block"] = np.where(allt["entry"] < "2025-01-01", "D", "H")
    sess_pos = {d: i for i, d in enumerate(SESSIONS)}
    allt["entry_pos"] = allt["entry"].map(sess_pos)

    # lane G term-structure split and VIX, joined on the 15:59 entry session
    g = pd.read_parquet(LANEG / "panel.parquet")[["ticker", "entry", "J", "a", "n1", "n2",
                                                    "w_front", "vix_prev"]]
    g["entry"] = pd.to_datetime(g["entry"])
    allt = allt.merge(g, on=["ticker", "entry"], how="left")
    allt.to_parquet(HERE / "trades_all.parquet")
    print("wrote trades_all.parquet", allt.shape)
    print(allt.groupby(["family", "ticker", "status"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
