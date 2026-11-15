"""s02_discovery.py: N08 discovery scorer (entry sessions 2016-01-04 to 2024-12-31 only).

Scores the families pre-registered in diagnosis.log entry 0 on block D. Block H rows are removed
before any statistic is computed; nothing here reads them.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s02_discovery.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.research.protocol import date_clustered_ci, per_trade_sharpe

HERE = Path(__file__).resolve().parent
MATCH_WINDOW = 60  # sessions either side, as frozen in the index study's B2
MIN_CONTROLS = 5  # as frozen in the index study's B2
KINDS = ("cpi", "nfp", "fomc", "pce")


# ── matching ─────────────────────────────────────────────────────────────────
def is_clean(df: pd.DataFrame) -> pd.Series:
    flag = np.zeros(len(df), dtype=bool)
    for k in KINDS:
        flag |= df[f"ev_{k}"].to_numpy() | df[f"en_{k}"].to_numpy()
    return pd.Series(~flag, index=df.index)


def matched(ev: pd.DataFrame, pool: pd.DataFrame, col: str, use_dte: bool = True) -> pd.DataFrame:
    """Attach the mean of matched controls (same weekday, same dte, +-60 sessions) to each event."""
    out = []
    for r in ev.itertuples():
        c = pool[(pool["weekday"] == r.weekday)
                 & ((pool["entry_pos"] - r.entry_pos).abs() <= MATCH_WINDOW)]
        if use_dte:
            c = c[c["dte"] == r.dte]
        c = c[np.isfinite(c[col])]
        out.append((len(c), float(c[col].mean()) if len(c) else np.nan))
    e = ev.copy()
    e["n_ctl"] = [o[0] for o in out]
    e["ctl"] = [o[1] for o in out]
    return e


def mean_ci(v: pd.Series, d: pd.Series) -> str:
    iv = date_clustered_ci(v.to_numpy(), d.to_numpy(), stat=np.mean)
    return f"{iv.point:+.4f} [{iv.low:+.4f}, {iv.high:+.4f}] N={iv.n}"


def score(df: pd.DataFrame, fam: str, tk: str, ev_mask: pd.Series, label: str, trial: int,
          col: str = "short_net", rows: list[dict[str, object]] | None = None) -> None:
    d = df[(df["family"] == fam) & (df["ticker"] == tk) & (df["status"] == "ok")]
    ev = d[ev_mask.reindex(d.index).fillna(False).to_numpy()]
    pool = d[is_clean(d)]
    e = matched(ev, pool, col, use_dte=(fam != "T3"))
    n_all = len(e)
    e = e[e["n_ctl"] >= MIN_CONTROLS]
    e = e[np.isfinite(e[col])]
    e["diff"] = e[col] - e["ctl"]
    ivb = date_clustered_ci(e[col].to_numpy(), e["event_date"].to_numpy(), stat=np.mean)
    ivp = date_clustered_ci(e["diff"].to_numpy(), e["event_date"].to_numpy(), stat=np.mean)
    t_p = ivp.point / (e["diff"].std(ddof=1) / np.sqrt(len(e)))
    passed = ivb.low > 0 and ivp.low > 0
    print(f"\n[{trial}] {fam} {tk} {label} ({col}): events {n_all}, with >= {MIN_CONTROLS} controls "
          f"{len(e)}; control pool {len(pool)}")
    print(f"  event book mean   {ivb}   Sharpe/trade {per_trade_sharpe(e[col]):+.3f}")
    print(f"  matched control   {e['ctl'].mean():+.4f}   pool mean {pool[col].mean():+.4f}")
    print(f"  paired diff       {ivp}   t {t_p:+.2f}")
    if "short_mid" in e:
        mm = e["short_mid"].dropna()
        print(f"  event mid (short, gross) {mm.mean():+.4f} N={len(mm)};  pool mid "
              f"{pool['short_mid'].mean():+.4f}")
    if "short_net_rom" in e and col == "short_net":
        print(f"  event on margin {e['short_net_rom'].mean():+.5f}")
    hs = e["half_spread_entry"].median()
    hx = e["half_spread_exit"].median() if "half_spread_exit" in e else np.nan
    print(f"  median half-spread / P0: entry {hs:.4f}, exit {hx:.4f}")
    for k in ("cpi", "nfp", "fomc", "pce"):
        sub = e[e[f"ev_{k}"]]
        if len(sub) >= 5 and k in label.lower():
            print(f"    {k}: book {sub[col].mean():+.4f} diff {sub['diff'].mean():+.4f} N={len(sub)}"
                  " (descriptive)")
    worst = e.nsmallest(3, col)[["event_date", col]]
    print("  worst 3:", [(str(a.date()), round(b, 3)) for a, b in worst.to_numpy()])
    if rows is not None:
        rows.append({"trial": trial, "family": fam, "ticker": tk, "events": label, "arm": col,
                     "block": "D 2016-2024", "n": ivb.n, "book_mean": ivb.point,
                     "book_lo": ivb.low, "book_hi": ivb.high,
                     "sharpe_pt": per_trade_sharpe(e[col]), "diff_mean": ivp.point,
                     "diff_lo": ivp.low, "diff_hi": ivp.high,
                     "verdict": "PASS" if passed else "FAIL"})


def mechanism(df: pd.DataFrame, tk: str, ev_mask: pd.Series, trial: int) -> None:
    """Implied extra night variance (J) against realised extra night variance, T1 rows."""
    d = df[(df["family"] == "T1") & (df["ticker"] == tk) & (df["status"] == "ok")].copy()
    d["rv"] = np.log(d["fwd1"] / d["fwd0"]) ** 2
    ev = d[ev_mask.reindex(d.index).fillna(False).to_numpy()]
    pool = d[is_clean(d)]
    rows = []
    for r in ev.itertuples():
        c = pool[(pool["weekday"] == r.weekday) & (pool["dte"] == r.dte)
                 & ((pool["entry_pos"] - r.entry_pos).abs() <= MATCH_WINDOW)]
        cj = c["J"].dropna()
        if len(c) >= MIN_CONTROLS and np.isfinite(r.J) and len(cj) >= MIN_CONTROLS:
            rows.append((r.event_date, r.J - cj.mean(), r.rv - c["rv"].mean()))
    m = pd.DataFrame(rows, columns=["d", "dJ", "dRV"])
    a = date_clustered_ci(m["dJ"].to_numpy(), m["d"].to_numpy(), stat=np.mean)
    b = date_clustered_ci(m["dRV"].to_numpy(), m["d"].to_numpy(), stat=np.mean)
    print(f"\n[{trial}] M1 {tk} implied extra variance on release nights (J, 15:59 term split): "
          f"{a.point:.2e} [{a.low:.2e}, {a.high:.2e}] N={a.n}")
    print(f"      realised extra variance 15:59 to 10:00, (log fwd move)^2: "
          f"{b.point:.2e} [{b.low:.2e}, {b.high:.2e}]")


def main() -> None:
    df = pd.read_parquet(HERE / "trades_all.parquet")
    n0 = len(df)
    df = df[df["block"] == "D"].copy()
    if df["entry"].max() >= pd.Timestamp("2025-01-01"):
        sys.exit("held-out rows leaked into discovery")
    print(f"discovery rows {len(df)} of {n0}; entry {df['entry'].min().date()} to "
          f"{df['entry'].max().date()}")
    r_mask = df["ev_cpi"] | df["ev_nfp"]
    rplus = r_mask | df["ev_pce"]
    f_mask = df["ev_fomc"]
    rows: list[dict[str, object]] = []
    score(df, "T1", "SPY", r_mask, "R=cpi|nfp overnight", 2292, rows=rows)
    score(df, "T2", "SPY", f_mask, "fomc intraday", 2293, rows=rows)
    score(df, "T3", "SPY", r_mask, "R=cpi|nfp settle", 2294, rows=rows)
    mechanism(df, "SPY", r_mask, 2295)
    score(df, "T1", "QQQ", r_mask, "R=cpi|nfp overnight", 2296, rows=rows)
    score(df, "T1", "IWM", r_mask, "R=cpi|nfp overnight", 2297, rows=rows)
    score(df, "T2", "QQQ", f_mask, "fomc intraday", 2298, rows=rows)
    score(df, "T2", "IWM", f_mask, "fomc intraday", 2299, rows=rows)
    score(df, "T3", "QQQ", r_mask, "R=cpi|nfp settle", 2300, rows=rows)
    score(df, "T3", "IWM", r_mask, "R=cpi|nfp settle", 2301, rows=rows)
    score(df, "T1", "SPY", rplus, "R+=cpi|nfp|pce overnight", 2302, rows=rows)
    score(df, "T2", "SPY", f_mask, "fomc intraday", 2303, col="long_net", rows=rows)
    pd.DataFrame(rows).to_csv(HERE / "discovery_round1.csv", index=False)


if __name__ == "__main__":
    main()
