"""s04_rebuild_compliant.py: provenance rebuild of the T4 hedged hold from the cache alone.

Replaces the Yahoo closes behind trials 2,307 and 2,312 with each session's 15:59 put-call-parity
forward from `data/cache/index_chains` (shortest expiry strictly after the session with a
two-sided pair, strike minimising |C mid - P mid|, F = K + C mid - P mid). Hedge prices are those
forwards from the entry session to the last session before expiry, hedge returns are ratios of
consecutive forwards, and the settlement price is the forward on the expiry session (or the last
session on or before it). No network access. A session with no usable forward drops every trade
whose path needs it (counted); there is no fallback.

Then re-scores exactly the frozen rule (SPY, CPI or payrolls, expiry at most 3 calendar days after
entry, HEDGED_NET, matched clean controls, date-clustered mean intervals) on block D (trial 2,313)
and block H (trial 2,314), beside the Yahoo-based rows of trades_round2.parquet.

Known approximation: the forward is one minute before the close and is a forward to the next
expiry, so it sits below spot by the carry and by any dividend going ex before that expiry.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s04_rebuild_compliant.py
"""

from __future__ import annotations

import importlib.util
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.config import HEDGED_NET
from earnings_iv_crush.engine.stats import nyse_sessions
from earnings_iv_crush.research.hedged_hold import hedged_short_straddle, straddle_iv, year_frac

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CHAINS = ROOT / "data" / "cache" / "index_chains"
PRICED = ROOT / "outputs" / "research" / "2026-11-01-index-event-crush" / "priced_trades.parquet"
TICKERS = ("SPY", "QQQ", "IWM")
START, END = pd.Timestamp("2016-01-04"), pd.Timestamp("2026-10-30")
MAX_DTE = 3.0
MARGIN_SPOT_FRAC = 0.15


def _load(name: str, path: Path):  # noqa: ANN202
    s = importlib.util.spec_from_file_location(name, path)
    assert s is not None and s.loader is not None
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


disc = _load("disc", HERE / "s02_discovery.py")
r2 = _load("r2", HERE / "s02b_round2.py")  # for attach() only; its Yahoo loader is never called
ho = _load("ho", HERE / "s03_heldout.py")  # for run() only; its main() is never called


def parity_forward(job: tuple[str, pd.Timestamp]) -> tuple[str, pd.Timestamp, float]:
    tk, d = job
    p = CHAINS / f"{tk}_{d.date()}_1559.parquet"
    if not p.exists():
        return tk, d, np.nan
    df = pd.read_parquet(p)
    if df.empty:
        return tk, d, np.nan
    df = df.sort_values("ts_recv").groupby("symbol", as_index=False).last()
    sym = df["symbol"].astype(str)
    q = pd.DataFrame({"expiry": pd.to_datetime(sym.str[6:12], format="%y%m%d"),
                      "cp": sym.str[12], "strike": sym.str[13:21].astype(int) / 1000.0,
                      "bid": df["bid_px_00"].astype(float), "ask": df["ask_px_00"].astype(float)})
    q = q[(q["bid"] > 0) & (q["ask"] >= q["bid"]) & np.isfinite(q["ask"]) & (q["expiry"] > d)]
    for exp in sorted(q["expiry"].unique()):
        piv = q[q["expiry"] == exp].pivot_table(index="strike", columns="cp",
                                                values=["bid", "ask"]).dropna()
        if piv.empty or ("bid", "C") not in piv.columns or ("bid", "P") not in piv.columns:
            continue
        cm = (piv[("bid", "C")] + piv[("ask", "C")]) / 2
        pm = (piv[("bid", "P")] + piv[("ask", "P")]) / 2
        k = float((cm - pm).abs().idxmin())
        return tk, d, k + float(cm.loc[k] - pm.loc[k])
    return tk, d, np.nan


def forwards() -> pd.DataFrame:
    path = HERE / "parity_forwards_1559.parquet"
    if path.exists():
        return pd.read_parquet(path)
    sess = [d for d in nyse_sessions(START, END) if START <= d <= END]
    jobs = [(tk, d) for tk in TICKERS for d in sess]
    with ProcessPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(parity_forward, jobs, chunksize=64))
    f = pd.DataFrame(rows, columns=["ticker", "date", "fwd"])
    f.to_parquet(path)
    return f


def t4_compliant(fw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_parquet(PRICED)
    d = d[(d["exit_snap"].astype(str) == "1000") & (d["status"] == "ok")].copy()
    for c in ("entry", "exit", "expiry"):
        d[c] = pd.to_datetime(d[c])
    series = {tk: g.set_index("date")["fwd"].sort_index() for tk, g in fw.groupby("ticker")}
    rows, drops, funnel = [], [], Counter()
    for r in d.itertuples():
        g = series[r.ticker]
        w = g.loc[r.entry:r.expiry]
        if len(w) < 2 or w.index[0] != r.entry:
            funnel["path_outside_cache"] += 1
            drops.append({"ticker": r.ticker, "entry": r.entry, "why": "path_outside_cache"})
            continue
        if not np.isfinite(w.to_numpy()).all():
            funnel["missing_forward"] += 1
            drops.append({"ticker": r.ticker, "entry": r.entry, "why": "missing_forward"})
            continue
        sig = straddle_iv(r.p0, r.fwd0, r.strike, year_frac(r.entry, r.expiry))
        if not np.isfinite(sig):
            funnel["no_iv"] += 1
            drops.append({"ticker": r.ticker, "entry": r.entry, "why": "no_iv"})
            continue
        cl = w.to_numpy(float)
        n = len(cl) - 1
        res = hedged_short_straddle(
            sale_price=r.c0b + r.p0b, sale_mid=r.p0, strike=r.strike, fwd=r.fwd0,
            closes=cl[:-1], rets=cl[1:] / cl[:-1] - 1.0,
            taus=np.array([year_frac(x, r.expiry) for x in w.index[:-1]]),
            sigmas=np.full(n, sig), half_spreads=np.zeros(n), settle_close=float(cl[-1]),
            cfg=HEDGED_NET,
        )
        funnel["ok"] += 1
        rows.append({"status": "ok", "ticker": r.ticker, "entry": r.entry, "event_date": r.exit,
                     "dte": r.dte, "short_net": res.net_pnl / r.p0,
                     "short_mid": res.gross_pnl_mid / r.p0,
                     "short_net_rom": res.net_pnl / (r.p0 + MARGIN_SPOT_FRAC * r.fwd0),
                     "half_spread_entry": (r.c0a - r.c0b + r.p0a - r.p0b) / 2 / r.p0})
    print("T4 compliant funnel", dict(funnel))
    return pd.DataFrame(rows), pd.DataFrame(drops)


def main() -> None:
    fw = forwards()
    miss = fw[~np.isfinite(fw["fwd"])]
    print(f"sessions x tickers {len(fw)}; without a usable 15:59 parity forward {len(miss)}")
    print(miss.groupby("ticker").size().to_dict())
    base = pd.read_parquet(HERE / "trades_all.parquet")
    t4, drops = t4_compliant(fw)
    out = r2.attach(t4, "T4", base)
    out.to_parquet(HERE / "trades_round2_compliant.parquet")
    print("wrote trades_round2_compliant.parquet", out.shape)

    yahoo = pd.read_parquet(HERE / "trades_round2.parquet")
    yahoo = yahoo[yahoo["family"] == "T4"]
    res_rows = []
    for blk, trial in (("D", 2313), ("H", 2314)):
        for tag, src in (("compliant", out), ("yahoo", yahoo)):
            df = src[(src["block"] == blk) & (src["dte"] <= MAX_DTE)].copy()
            r = df["ev_cpi"] | df["ev_nfp"]
            res, e = ho.run(df, "SPY", r)
            res_rows.append({"trial": trial, "block": blk, "source": tag, **res})
            print(f"[{trial}] {blk} {tag}: N={res['n']} of {res['events']} events; book "
                  f"{np.round(res['book'], 4).tolist()} paired {np.round(res['diff'], 4).tolist()}"
                  f" rom {res['rom_mean']:+.5f} pass {res['pass']}")
            if tag == "compliant":
                ec = e.set_index("event_date")
            else:
                ey = e.set_index("event_date")
        j = ec[["short_net", "diff"]].join(ey[["short_net", "diff"]], lsuffix="_c", rsuffix="_y",
                                           how="outer")
        both = j.dropna()
        print(f"  {blk}: events in both {len(both)}, only Yahoo {j['short_net_c'].isna().sum()}, "
              f"only compliant {j['short_net_y'].isna().sum()}; per-event corr "
              f"{both['short_net_c'].corr(both['short_net_y']):.4f}; mean |diff| "
              f"{(both['short_net_c'] - both['short_net_y']).abs().mean():.4f} of P0")
        dropped = j[j["short_net_c"].isna()]
        if len(dropped):
            kept = both["short_net_y"]
            print(f"  dropped events' Yahoo outcome mean {dropped['short_net_y'].mean():+.4f} "
                  f"(N={len(dropped)}) vs kept {kept.mean():+.4f}: "
                  f"{dropped.index.date.tolist()}")
    # drop counts on the SPY release events of the rule, by block
    if len(drops):
        dd = drops.merge(base[base["family"] == "T1"][["ticker", "entry", "event_date", "ev_cpi",
                                                       "ev_nfp", "dte", "block"]],
                         on=["ticker", "entry"], how="left")
        ev = dd[(dd["ticker"] == "SPY") & (dd["ev_cpi"] | dd["ev_nfp"]) & (dd["dte"] <= MAX_DTE)]
        print("rule-event drops (SPY, R, dte<=3):", ev.groupby(["block", "why"]).size().to_dict())
        print("all drops by ticker and reason:", drops.groupby(["ticker", "why"]).size().to_dict())
    pd.DataFrame(res_rows).to_json(HERE / "rebuild_compliant_results.json", orient="records",
                                   indent=2)


if __name__ == "__main__":
    main()
