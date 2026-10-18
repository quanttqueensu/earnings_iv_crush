"""
research_post_event_vrp.py
Pre-registered test: post-announcement short straddle sold at the exit-day 15:59, held to expiry.

``research/timing/preregs/post_event_vrp_prereg.md``. One entry half-spread (sold at the bid), settled at intrinsic
against the expiry-day close, so the large exit spread that sank the event book is never paid.

Usage:
    python research/timing/research_post_event_vrp.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.greeks import implied_vol  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from research.selection.research_p1_skew_reaction import (
    edgar_exclusion,
    parity_forward,
    usable,
)  # noqa: E402

PREREG = Path("research/timing/preregs/post_event_vrp_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_post_event_vrp.json")
EVENTS = Path("outputs/research/events_broad_oos_2025.parquet")
CHAINS = Path("data/cache/backfill_chains")
OUT = Path("outputs/research/post_event_vrp")
RAW = OUT / "raw_close.parquet"  # yfinance, split-adjusted (RV only)
RAW_SIP = OUT / "raw_sip_close.parquet"  # Alpaca SIP, unadjusted (settlement)
DTE_MIN, DTE_MAX = 14, 45
COMMISSION = 0.65  # USD per contract per leg
STOCK_COST = 0.0005  # disposing of delivered stock
REGT_SPOT = 0.20
N_BOOT = 5000
SEED = 0
N_TRIALS = 1504
STRESS = (pd.Timestamp("2025-03-15"), pd.Timestamp("2025-04-30"))


def _check_prereg() -> None:
    want = json.loads(PREREG_JSON.read_text())["prereg_sha256"]
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != want:
        raise SystemExit("pre-registration hash mismatch")


def build() -> pd.DataFrame:
    from earnings_iv_crush.research.chains import _parse_chain

    ev = pd.read_parquet(EVENTS, columns=["ticker", "announce_date", "entry_date", "exit_date"])
    for c in ("announce_date", "entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c]).dt.normalize()
    n0 = len(ev)
    ev = ev.drop_duplicates(["ticker", "announce_date"]).reset_index(drop=True)
    ev, _ = edgar_exclusion(ev)
    f: dict[str, int] = {"events": n0, "after_dedup_and_edgar": len(ev)}
    rows = []
    for _, e in ev.iterrows():
        p = CHAINS / f"{e['ticker']}_{e['exit_date'].date()}.parquet"
        ch = _parse_chain(pd.read_parquet(p)) if p.exists() else None
        if ch is None:
            f["no_exit_chain"] = f.get("no_exit_chain", 0) + 1
            continue
        dte = (pd.to_datetime(ch["expiry"]) - e["exit_date"]).dt.days
        exps = sorted(ch.loc[(dte >= DTE_MIN) & (dte <= DTE_MAX), "expiry"].unique())
        if not exps:
            f["no_expiry"] = f.get("no_expiry", 0) + 1
            continue
        expiry = pd.Timestamp(exps[0])
        leg = usable(ch[ch["expiry"] == expiry])
        calls = leg[leg["right"] == "C"].groupby("strike")[["bid_px_00", "mid"]].last()
        puts = leg[leg["right"] == "P"].groupby("strike")[["bid_px_00", "mid"]].last()
        fwd = parity_forward(calls["mid"], puts["mid"])
        both = calls.index.intersection(puts.index)
        if not np.isfinite(fwd) or len(both) == 0:
            f["no_forward"] = f.get("no_forward", 0) + 1
            continue
        k = float(min(both, key=lambda x: abs(float(x) - fwd)))
        t = (expiry - e["exit_date"]).days / 365.0
        cm, pm = float(calls.loc[k, "mid"]), float(puts.loc[k, "mid"])
        ivc = implied_vol(cm, fwd, k, t, 0.0, "C", hi=10.0)
        ivp = implied_vol(pm, fwd, k, t, 0.0, "P", hi=10.0)
        rows.append(
            {
                **e.to_dict(),
                "expiry": expiry,
                "dte": (expiry - e["exit_date"]).days,
                "strike": k,
                "fwd": fwd,
                "call_bid": float(calls.loc[k, "bid_px_00"]),
                "put_bid": float(puts.loc[k, "bid_px_00"]),
                "call_mid": cm,
                "put_mid": pm,
                "iv_entry": float(np.nanmean([ivc, ivp])),
            }
        )
    d = pd.DataFrame(rows)
    f["priced_entries"] = len(d)
    print("  funnel: " + ", ".join(f"{a}={b}" for a, b in f.items()), flush=True)
    if d.empty:
        raise SystemExit("no entries priced")
    return d


def closes(tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if RAW.exists():
        px = pd.read_parquet(RAW)
        if set(tickers) <= set(px.columns) and px.index.max() >= end:
            return px
    import yfinance as yf

    raw = yf.download(
        [t.replace(".", "-") for t in tickers],
        start=str((start - pd.Timedelta(days=5)).date()),
        end=str((end + pd.Timedelta(days=5)).date()),
        auto_adjust=False,
        progress=False,
        threads=True,
    )["Close"]
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    raw = raw.rename(columns=lambda c: c.replace("-", "."))
    OUT.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(RAW)
    return raw


def raw_sip(tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Unadjusted consolidated daily closes from Alpaca (free historical SIP), cached."""
    from earnings_iv_crush.data.alpaca_options import _DATA_HOST, _get

    if RAW_SIP.exists():
        px = pd.read_parquet(RAW_SIP)
        if set(tickers) <= set(px.columns) and px.index.max() >= end - pd.Timedelta(days=4):
            return px
    series: dict[str, dict[pd.Timestamp, float]] = {}
    for i in range(0, len(tickers), 50):
        token = None
        while True:
            params = {
                "symbols": ",".join(tickers[i : i + 50]),
                "timeframe": "1Day",
                "start": str((start - pd.Timedelta(days=5)).date()),
                "end": str((end + pd.Timedelta(days=5)).date()),
                "feed": "sip",
                "adjustment": "raw",
                "limit": 10000,
            }
            if token:
                params["page_token"] = token
            body = _get(_DATA_HOST, "/v2/stocks/bars", params)
            for sym, bars in (body.get("bars") or {}).items():
                dct = series.setdefault(sym, {})
                for bar in bars:
                    dct[pd.Timestamp(bar["t"][:10])] = float(bar["c"])
            token = body.get("next_page_token")
            if not token:
                break
    px = pd.DataFrame(series).sort_index()
    px.to_parquet(RAW_SIP)
    return px


def _split_factor(f: float) -> float | None:
    """1 for no corporate action, the split ratio for a clean split, None otherwise."""
    if abs(f - 1) < 0.05:
        return 1.0
    for n in range(2, 51):
        for r in (float(n), 1.0 / n):
            if abs(f / r - 1) < 0.03:
                return r
    return None


def settle(d: pd.DataFrame) -> pd.DataFrame:
    tickers = sorted(d["ticker"].unique())
    adj = closes(tickers, d["exit_date"].min(), d["expiry"].max())
    raw = raw_sip([t.replace("-", ".") for t in tickers], d["exit_date"].min(), d["expiry"].max())
    out = []
    for _, e in d.iterrows():
        t = e["ticker"].replace("-", ".")
        rec: dict[str, Any] = {"s_t": np.nan, "split_factor": np.nan, "rv": np.nan, "drop": ""}
        if t not in raw.columns or t not in adj.columns:
            rec["drop"] = "no_prices"
            out.append(rec)
            continue
        r = raw[t].dropna()
        a = adj[t].dropna()
        r = r[(r.index >= e["exit_date"]) & (r.index <= e["expiry"])]
        a = a[(a.index >= e["exit_date"]) & (a.index <= e["expiry"])]
        if len(r) < 3 or r.index.max() < e["expiry"] - pd.Timedelta(days=4) or len(a) < 3:
            rec["drop"] = "no_settlement"
            out.append(rec)
            continue
        f = (r.iloc[0] / a.iloc[0]) / (r.iloc[-1] / a.loc[: r.index[-1]].iloc[-1])
        sf = _split_factor(float(f))
        if sf is None:
            rec["drop"] = "corporate_action_in_hold"
            out.append(rec)
            continue
        lr = np.diff(np.log(a.to_numpy()))
        rec.update(
            s_t=float(r.iloc[-1]) * sf,
            split_factor=sf,
            rv=float(np.sqrt(252 * np.mean(lr**2))),
        )
        out.append(rec)
    d = pd.concat([d.reset_index(drop=True), pd.DataFrame(out)], axis=1)
    n = len(d)
    print(f"  settlement drops: {d['drop'].value_counts().to_dict()}", flush=True)
    d = d[d["s_t"].notna()].reset_index(drop=True)
    print(f"  settled {len(d)}/{n}", flush=True)
    credit = (d["call_bid"] + d["put_bid"]) * 100
    credit_mid = (d["call_mid"] + d["put_mid"]) * 100
    intrinsic = (d["s_t"] - d["strike"]).abs() * 100
    disposal = STOCK_COST * d["s_t"] * 100 * (d["s_t"] != d["strike"])
    d["margin"] = REGT_SPOT * d["fwd"] * 100 + credit
    d["pnl"] = credit - intrinsic - 2 * COMMISSION - disposal
    d["rom"] = d["pnl"] / d["margin"]
    d["rom_mid"] = (credit_mid - intrinsic) / (REGT_SPOT * d["fwd"] * 100 + credit_mid)
    d["rop"] = d["pnl"] / credit
    d["vol_gap"] = d["iv_entry"] - d["rv"]
    return d


def _ci(x: pd.Series, keys: pd.Series) -> list[float]:
    lo, hi = cluster_bootstrap_ci(
        x.to_numpy(), keys.astype(str).to_numpy(), np.mean, n_boot=N_BOOT, seed=SEED
    )
    return [float(lo), float(hi)]


def score() -> None:
    _check_prereg()
    d = settle(build())
    d.to_csv(OUT / "trades.csv", index=False)
    keys = d["expiry"]
    res: dict[str, Any] = {
        "n": len(d),
        "n_expiries": int(d["expiry"].nunique()),
        "mean_rom": float(d["rom"].mean()),
        "ci_rom": _ci(d["rom"], keys),
        "median_rom": float(d["rom"].median()),
        "mean_rom_mid": float(d["rom_mid"].mean()),
        "ci_rom_mid": _ci(d["rom_mid"], keys),
        "mean_rop": float(d["rop"].mean()),
        "sharpe_per_trade": float(d["rom"].mean() / d["rom"].std(ddof=1)),
        "dsr": float(deflated_sharpe_ratio(d["rom"], n_trials=N_TRIALS)),
        "mean_vol_gap": float(d["vol_gap"].mean()),
        "ci_vol_gap": _ci(d["vol_gap"].dropna(), d.loc[d["vol_gap"].notna(), "expiry"]),
        "spearman_pnl_volgap": float(spearmanr(d["vol_gap"], d["rom"], nan_policy="omit")[0]),
        "mean_dte": float(d["dte"].mean()),
        "mean_entry_half_spread_share": float(
            1 - (d["call_bid"] + d["put_bid"]).sum() / (d["call_mid"] + d["put_mid"]).sum()
        ),
        "n_split_rescaled": int((d["split_factor"] != 1).sum()),
        "worst10": d.nsmallest(10, "rom")[["ticker", "exit_date", "rom"]]
        .astype(str)
        .values.tolist(),
    }
    res["pass_pnl"] = res["ci_rom"][0] > 0
    res["pass_mechanism"] = res["ci_vol_gap"][0] > 0 and res["spearman_pnl_volgap"] > 0
    res["verdict"] = (
        "PASS"
        if res["pass_pnl"] and res["pass_mechanism"]
        else ("unexplained" if res["pass_pnl"] else "FAIL")
    )
    d["month"] = d["exit_date"].dt.to_period("M").astype(str)
    res["by_month"] = d.groupby("month")["rom"].agg(["mean", "count"]).round(4).to_dict()
    ex = d[(d["exit_date"] < STRESS[0]) | (d["exit_date"] > STRESS[1])]
    res["ex_stress_window"] = {"n": len(ex), "mean_rom": float(ex["rom"].mean())}
    days = pd.date_range(d["exit_date"].min(), d["expiry"].max())
    conc = [int(((d["exit_date"] <= x) & (d["expiry"] >= x)).sum()) for x in days]
    res["max_concurrent"] = max(conc)
    print(json.dumps(res, indent=1, default=str))
    json.dump(res, open(OUT / "summary.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    score()
