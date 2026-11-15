"""
study.py
Pre-event directional signals on the earnings night, traded in the stock against SPY.

Scores the pre-registration in ``prereg.md`` exactly as frozen: five trials (D1 pre-event
reversal, D2 consumer demand, D3 earnings seasonality, D4 revision breadth, D5 composite), each
on discovery first and on the later blocks only if the earlier one passes.

Usage
-----
    python research/timing/2026-11-10-pre-event-direction/study.py --dry   # funnels only
    python research/timing/2026-11-10-pre-event-direction/study.py

References
----------
So, E. C. and Wang, S. (2014). News-driven return reversals: liquidity provision ahead of
earnings announcements. Journal of Financial Economics 114(1), 20-35.
Chang, T. Y., Hartzmark, S. M., Solomon, D. H. and Soltes, E. F. (2017). Being surprised by the
unsurprising: earnings seasonality and stock returns. Review of Financial Studies 30(1), 281-323.
Froot, K., Kang, N., Ozik, G. and Sadka, R. (2017). What do measures of real-time corporate sales
say about earnings surprises and post-announcement returns? Journal of Financial Economics 125(1).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import rankdata  # noqa: E402

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
EVENTS = ROOT / "outputs" / "research" / "ml_zoo" / "events_full.parquet"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CA = ROOT / "data" / "cache" / "carbonarc" / "ca_demand.parquet"
PRICES = ROOT / "data" / "cache" / "yahoo_adj" / "adj_close.parquet"
WRDS = ROOT / "data" / "processed" / "wrds" / "raw"

# ── frozen specification (prereg.md) ─────────────────────────────────────────

COST = 12e-4  # round trip per position, stock and SPY hedge together
N_BINS = 5
MIN_PRIOR = 200
CA_MAX_STALE = 62  # days between the score's month end and entry
IBES_MAX_STALE = 40
MIN_NUMEST = 3
SEASON_QUARTERS = 20
SEASON_MAX_SPAN_DAYS = int(5.5 * 365.25)
SEASON_LAGS = (4, 8, 12, 16, 20)
STD_BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}
CA_BLOCKS = {"discovery": (2017, 2020), "validation": (2021, 2024), "confirmation": (2025, 2026)}
# orientation: +1 long the top quintile, -1 long the bottom quintile
TRIALS = {
    "D1": ("F", -1, "R1", STD_BLOCKS),
    "D2": ("ca", +1, "R", CA_BLOCKS),
    "D3": ("season", +1, "R", STD_BLOCKS),
    "D4": ("breadth", +1, "R", STD_BLOCKS),
    "D5": ("composite", +1, "R", STD_BLOCKS),
}


# ── data ─────────────────────────────────────────────────────────────────────


def load_prices(tickers: list[str]) -> pd.DataFrame:
    """Yahoo adjusted closes, one column per ticker, cached on first use."""
    if PRICES.exists():
        px = pd.read_parquet(PRICES)
        if set(tickers) <= set(px.attrs.get("requested", px.columns)):
            return px
    import yfinance as yf

    raw = yf.download(
        tickers,
        start="2012-06-01",
        end="2026-11-01",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    cols = {}
    for t in tickers:
        try:
            g = raw[t]["Adj Close"].dropna()
        except KeyError:
            continue
        if not g.empty:
            cols[t] = g
    px = pd.DataFrame(cols)
    px.index = pd.to_datetime(px.index).tz_localize(None).normalize()
    PRICES.parent.mkdir(parents=True, exist_ok=True)
    px.to_parquet(PRICES)
    return px


def load_events() -> pd.DataFrame:
    """De-duplicated events with permno and the stock outcomes of the frozen windows."""
    ev = pd.read_parquet(
        EVENTS, columns=["ticker", "announce_date", "entry_date", "exit_date", "block"]
    )
    for c in ("announce_date", "entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c]).dt.normalize()
    n0 = len(ev)
    ev = ev.drop_duplicates(["ticker", "entry_date"]).reset_index(drop=True)
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "permno"])
    f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    latest = (
        f.dropna(subset=["permno"]).sort_values("entry_date").groupby("ticker")["permno"].last()
    )
    ev = ev.merge(
        f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )
    ev["permno"] = ev["permno"].fillna(ev["ticker"].map(latest))
    px = load_prices(sorted(ev["ticker"].unique()) + ["SPY"])
    spy = px["SPY"].dropna()
    out = {k: np.full(len(ev), np.nan) for k in ("R", "R1", "F")}
    miss = {"no_name": 0, "no_session": 0, "short_history": 0}
    series = {t: px[t].dropna() for t in px.columns}
    for i, (t, d0, d1) in enumerate(
        zip(ev["ticker"], ev["entry_date"], ev["exit_date"], strict=True)
    ):
        g = series.get(t)
        if g is None:
            miss["no_name"] += 1
            continue
        if d0 not in g.index or d1 not in g.index or d0 not in spy.index or d1 not in spy.index:
            miss["no_session"] += 1
            continue
        e = g.index.get_loc(d0)
        out["R"][i] = g.loc[d1] / g.iloc[e] - 1 - (spy.loc[d1] / spy.loc[d0] - 1)
        if e < 4:
            miss["short_history"] += 1
            continue
        da, db = g.index[e - 4], g.index[e - 1]
        if da not in spy.index or db not in spy.index:
            miss["no_session"] += 1
            continue
        out["F"][i] = g.iloc[e - 1] / g.iloc[e - 4] - 1 - (spy.loc[db] / spy.loc[da] - 1)
        out["R1"][i] = g.loc[d1] / g.iloc[e - 1] - 1 - (spy.loc[d1] / spy.loc[db] - 1)
    ev = ev.assign(**out)
    print(
        f"funnel: {n0} zoo rows, {len(ev)} after de-duplication, R finite "
        f"{int(np.isfinite(ev['R']).sum())}, F finite {int(np.isfinite(ev['F']).sum())}, "
        f"permno {int(ev['permno'].notna().sum())}; drops {miss}"
    )
    return ev.sort_values("entry_date").reset_index(drop=True)


def attach_carbonarc(ev: pd.DataFrame) -> pd.DataFrame:
    """Latest demand score strictly before entry and within the staleness limit."""
    ca = pd.read_parquet(CA).sort_values("eom")
    by = {
        int(k): (g["eom"].to_numpy(), g["ca_demand"].to_numpy(float))
        for k, g in ca.groupby("permno")
    }
    out = np.full(len(ev), np.nan)
    stale = np.timedelta64(CA_MAX_STALE, "D")
    for i, (pn, t_in) in enumerate(
        zip(ev["permno"].to_numpy(float), ev["entry_date"].to_numpy(), strict=True)
    ):
        if not np.isfinite(pn) or int(pn) not in by:
            continue
        eom, val = by[int(pn)]
        j = int(np.searchsorted(eom, t_in, side="left")) - 1
        if j >= 0 and t_in - eom[j] <= stale:
            out[i] = val[j]
    print(f"funnel: Carbon Arc score found {int(np.isfinite(out).sum())}")
    return ev.assign(ca=out)


def attach_ibes(ev: pd.DataFrame) -> pd.DataFrame:
    """Revision breadth for the reported quarter and the seasonality rank of that quarter."""
    link = pd.read_parquet(glob.glob(str(WRDS / "wrdsapps_link_crsp_ibes.ibcrsphist.*.parquet"))[0])
    for c in ("sdate", "edate"):
        link[c] = pd.to_datetime(link[c])
    link = link.rename(columns={"ticker": "ibes"}).dropna(subset=["permno"])
    link = link[link["permno"].isin(ev["permno"].dropna().unique())]
    s = pd.read_parquet(
        glob.glob(str(WRDS / "tr_ibes.statsum_epsus.*.parquet"))[0],
        columns=[
            "ticker",
            "statpers",
            "fpedats",
            "numest",
            "numup",
            "numdown",
            "actual",
            "anndats_act",
        ],
    ).rename(columns={"ticker": "ibes"})
    s = s[s["ibes"].isin(link["ibes"].unique())]
    for c in ("statpers", "fpedats", "anndats_act"):
        s[c] = pd.to_datetime(s[c], errors="coerce")
    by_ibes = {k: g for k, g in s.groupby("ibes")}
    hist = {
        k: g.dropna(subset=["actual", "anndats_act"])
        .drop_duplicates("fpedats", keep="last")
        .sort_values("fpedats")[["fpedats", "actual", "anndats_act"]]
        for k, g in by_ibes.items()
    }
    by_permno = {int(float(str(k))): g for k, g in link.groupby("permno")}
    breadth = np.full(len(ev), np.nan)
    season = np.full(len(ev), np.nan)
    stale = pd.Timedelta(days=IBES_MAX_STALE)
    span = pd.Timedelta(days=SEASON_MAX_SPAN_DAYS)
    n_row = 0
    for i, (pn, t_in, t_ann) in enumerate(
        zip(
            ev["permno"].to_numpy(float),
            ev["entry_date"].tolist(),
            ev["announce_date"].tolist(),
            strict=True,
        )
    ):
        if not np.isfinite(pn) or int(pn) not in by_permno:
            continue
        lk = by_permno[int(pn)]
        lk = lk[(lk["sdate"] <= t_in) & (lk["edate"] >= t_in)]
        if lk.empty:
            continue
        key = lk.sort_values("score")["ibes"].iloc[0]
        g = by_ibes.get(key)
        if g is None:
            continue
        g = g[(g["statpers"] < t_in) & (g["statpers"] >= t_in - stale) & (g["fpedats"] < t_ann)]
        if g.empty:
            continue
        g = g[g["statpers"] == g["statpers"].max()]
        row = g.sort_values("fpedats").iloc[-1]
        n_row += 1
        if row["numest"] >= MIN_NUMEST:
            breadth[i] = (row["numup"] - row["numdown"]) / row["numest"]
        h = hist[key]
        h = h[(h["fpedats"] < row["fpedats"]) & (h["anndats_act"] < t_in)].tail(SEASON_QUARTERS)
        if len(h) == SEASON_QUARTERS and row["fpedats"] - h["fpedats"].iloc[0] <= span:
            ranks = rankdata(h["actual"].to_numpy(float))[::-1]  # index 0 is lag 1
            season[i] = float(np.mean([ranks[k - 1] for k in SEASON_LAGS]))
    print(
        f"funnel: IBES row found {n_row}, breadth finite {int(np.isfinite(breadth).sum())}, "
        f"seasonality finite {int(np.isfinite(season).sum())}"
    )
    return ev.assign(breadth=breadth, season=season)


def assign_bins(ev: pd.DataFrame) -> pd.DataFrame:
    """Causal quintiles per signal, then the composite and its own causal quintiles."""
    ev = ev.copy()
    for sig in ("F", "ca", "season", "breadth"):
        ev[f"bin_{sig}"] = causal_bins(ev[sig].to_numpy(float), ev["entry_date"], N_BINS, MIN_PRIOR)
    parts = []
    for sig, sign in (("F", -1), ("ca", 1), ("season", 1), ("breadth", 1)):
        b = ev[f"bin_{sig}"].to_numpy(float)
        parts.append(np.where(b >= 0, sign * (b - 2) / 2, np.nan))
    stack = np.vstack(parts)
    n_def = np.isfinite(stack).sum(axis=0)
    with np.errstate(invalid="ignore"):
        comp = np.nansum(stack, axis=0) / np.where(n_def > 0, n_def, np.nan)
    ev["composite"] = np.where(n_def >= 2, comp, np.nan)
    ev["bin_composite"] = causal_bins(
        ev["composite"].to_numpy(float), ev["entry_date"], N_BINS, MIN_PRIOR
    )
    return ev


# ── scoring ──────────────────────────────────────────────────────────────────


def positions(ev: pd.DataFrame, trial: str) -> pd.DataFrame:
    """Long and short positions of one trial with gross and net return per position."""
    sig, orient, outcome, _ = TRIALS[trial]
    b = ev[f"bin_{sig}"].to_numpy()
    side = np.where(b == N_BINS - 1, orient, np.where(b == 0, -orient, 0))
    p = ev.assign(side=side)
    p = p[(p["side"] != 0) & np.isfinite(p[outcome])].copy()
    p["gross"] = p["side"] * p[outcome]
    p["net"] = p["gross"] - COST
    p["year"] = p["exit_date"].dt.year
    return p


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def summ(p: pd.DataFrame, col: str = "net") -> dict:
    if len(p) < 5:
        return {"n": int(len(p))}
    ci = date_clustered_ci(p[col], p["exit_date"], _mean)
    return {
        "n": ci.n,
        "clusters": ci.clusters,
        "mean": ci.point,
        "ci": [ci.low, ci.high],
        "sharpe": per_trade_sharpe(p[col]),
    }


def fmt(s: dict) -> str:
    if "mean" not in s:
        return f"N={s['n']} (too few)"
    return (
        f"{100 * s['mean']:+.3f}% [{100 * s['ci'][0]:+.3f}, {100 * s['ci'][1]:+.3f}] "
        f"Sharpe {s['sharpe']:+.3f} (N={s['n']}, {s['clusters']} dates)"
    )


def score_trial(ev: pd.DataFrame, trial: str) -> dict:
    blocks = TRIALS[trial][3]
    p = positions(ev, trial)
    res: dict = {"trial": trial, "blocks": {}, "verdict": "PASS"}
    print(
        f"\n{trial}: {len(p)} positions ({int((p['side'] > 0).sum())} long, {int((p['side'] < 0).sum())} short)"
    )
    for name, (lo, hi) in blocks.items():
        b = p[p["year"].between(lo, hi)]
        s = summ(b)
        res["blocks"][name] = {
            "net": s,
            "gross": summ(b, "gross"),
            "long": summ(b[b["side"] > 0]),
            "short": summ(b[b["side"] < 0]),
            "megacap": summ(b[b["block"] == "megacap"]),
            "broad": summ(b[b["block"] != "megacap"]),
        }
        print(f"  {name} {lo}-{hi}: net per position {fmt(s)}")
        for k in ("gross", "long", "short", "megacap", "broad"):
            print(f"      sec {k}: {fmt(res['blocks'][name][k])}")
        if name == "confirmation":
            ok = s.get("mean", -1.0) > 0
        else:
            ok = s.get("ci", [-1.0])[0] > 0
        if not ok:
            res["verdict"] = f"FAIL at {name}"
            break
    print(f"  VERDICT {trial}: {res['verdict']}")
    return res


def dry(ev: pd.DataFrame) -> None:
    """Counts only: no outcome is read."""
    for trial, (sig, _, _, blocks) in TRIALS.items():
        b = ev[f"bin_{sig}"]
        yr = ev["exit_date"].dt.year
        line = ", ".join(
            f"{n} top {int(((b == 4) & yr.between(*r)).sum())} bottom {int(((b == 0) & yr.between(*r)).sum())}"
            for n, r in blocks.items()
        )
        print(f"{trial} ({sig}): binned {int((b >= 0).sum())}; {line}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="print funnels and counts, no outcomes")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    ev = assign_bins(attach_ibes(attach_carbonarc(load_events())))
    OUT.mkdir(parents=True, exist_ok=True)
    if args.dry:
        dry(ev)
        return
    ev.to_parquet(OUT / "events.parquet", index=False)
    res = {t: score_trial(ev, t) for t in TRIALS}
    p1 = positions(ev.assign(R1=ev["R"]), "D1")
    print("\nD1 secondary, one-night window (entry close to exit close):")
    for name, (lo, hi) in STD_BLOCKS.items():
        print(f"  {name}: {fmt(summ(p1[p1['year'].between(lo, hi)]))}")
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
