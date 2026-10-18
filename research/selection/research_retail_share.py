"""
research_retail_share.py
T3 of the final earnings test set: retail ownership as the selector.

Mechanism. Retail investors buy options in a concentrated way before earnings and overpay
(de Silva, So and Smith 2026); market makers charge for absorbing that one-sided demand
(Muravyev 2016). Retail demand should be larger where retail owns more of the stock, so at a
given priced move, high-retail-share names should carry richer options.

Signal. One minus 13F institutional ownership: the sum of 13F holdings over shares
outstanding, from the latest report date at least 45 days before entry (the 13F filing lag),
matched on 8-digit CUSIP from CRSP names valid at that date.

Stages, each run only if the previous passed (``research/selection/preregs/final_earnings_set_prereg.md``):
discovery 2019-2024 megacap, validation 2013-2018 megacap, confirmation 2025-2026 broad.

Usage:
    python research/selection/research_final_earnings_set.py --test t3

References
----------
de Silva, T., So, E. C. and Smith, K. (2026). Losing is Optional: Retail Option Trading and
Expected Announcement Volatility. *Review of Finance* 30(2), 489-.
Muravyev, D. (2016). Order Flow and Expected Option Returns. *Journal of Finance* 71(2),
673-708.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import wrds_r2  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from research.execution.research_spread_gate import sharpe  # noqa: E402
from research.selection.research_clean_iv import decompose  # noqa: E402
from research.selection.research_final_earnings_set import (  # noqa: E402
    LEDGER,
    N_BOOT,
    SEED,
    megacap_blocks,
    sharpe_ci,
)

FILING_LAG_DAYS = 45
Q = 0.80
MIN_HIST = 25
N_NULL = 1000


# ── ownership ────────────────────────────────────────────────────────────────


def _names(tickers: list[str]) -> pd.DataFrame:
    nm = wrds_r2.read_table(
        "crsp_a_stock",
        "dsenames",
        columns=["permno", "ticker", "ncusip", "namedt", "nameendt"],
        filters=[("ticker", "in", sorted(set(tickers)))],
    )
    nm["namedt"] = pd.to_datetime(nm["namedt"])
    nm["nameendt"] = pd.to_datetime(nm["nameendt"])
    return nm.dropna(subset=["ncusip"])


def institutional_ownership(cusips: list[str]) -> pd.DataFrame:
    """Quarterly IO per 8-digit CUSIP: summed 13F shares over shares outstanding, capped at 1."""
    s = wrds_r2.read_table(
        "tr_13f",
        "s34",
        columns=["fdate", "cusip", "shares", "shrout1", "shrout2"],
        filters=[
            ("cusip", "in", sorted(set(cusips))),
            ("fdate", ">=", pd.Timestamp("2012-01-01").date()),
        ],
    )
    if s.empty:
        raise SystemExit("13F returned no holdings for the universe - refusing to proceed")
    s["fdate"] = pd.to_datetime(s["fdate"])
    for c in ("shares", "shrout1", "shrout2"):
        s[c] = pd.to_numeric(s[c], errors="coerce").astype(float)
    g = s.groupby(["cusip", "fdate"]).agg(
        held=("shares", "sum"), shrout1=("shrout1", "max"), shrout2=("shrout2", "max")
    )
    out = np.where(g["shrout2"] > 0, g["shrout2"] * 1e3, g["shrout1"] * 1e6)
    g["io"] = np.minimum(g["held"] / out, 1.0)
    return g.reset_index()[["cusip", "fdate", "io"]].dropna()


def attach_retail_share(ev: pd.DataFrame) -> pd.DataFrame:
    """Retail share at entry for every event, causal in the 13F filing lag."""
    ev = ev.copy()
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    nm = _names(ev["ticker"].unique().tolist())
    io = institutional_ownership(nm["ncusip"].unique().tolist())
    io_by = {c: g.sort_values("fdate") for c, g in io.groupby("cusip")}
    out = np.full(len(ev), np.nan)
    reasons: dict[str, int] = {}
    for i, (t, d) in enumerate(zip(ev["ticker"], ev["entry_date"], strict=True)):
        live = nm[(nm["ticker"] == t) & (nm["namedt"] <= d) & (d <= nm["nameendt"])]
        if live.empty:
            reasons["no CRSP name at entry"] = reasons.get("no CRSP name at entry", 0) + 1
            continue
        g = io_by.get(live.iloc[-1]["ncusip"])
        if g is None:
            reasons["no 13F holdings"] = reasons.get("no 13F holdings", 0) + 1
            continue
        avail = g[g["fdate"] <= d - pd.Timedelta(days=FILING_LAG_DAYS)]
        if avail.empty:
            reasons["no report before lag"] = reasons.get("no report before lag", 0) + 1
            continue
        out[i] = 1.0 - float(avail["io"].iloc[-1])
    ev["retail_share"] = out
    print(f"  retail share attached to {int(np.isfinite(out).sum())}/{len(ev)}; missing {reasons}")
    return ev


# ── stages ───────────────────────────────────────────────────────────────────


def discovery(d: pd.DataFrame) -> tuple[bool, dict]:
    d = d[np.isfinite(d["retail_share"]) & np.isfinite(d["net_rom"])].copy()
    d["decile"] = pd.qcut(d["retail_share"].rank(method="first"), 10, labels=False)
    dec = d.groupby("decile")["net_rom"].mean()
    rho = float(stats.spearmanr(dec.index, dec.values)[0])
    d["quint"] = pd.qcut(d["retail_share"].rank(method="first"), 5, labels=False)
    top, bot = d[d["quint"] == 4], d[d["quint"] == 0]
    keys = d["entry_date"].dt.strftime("%Y-%m-%d").to_numpy()
    is_top = (d["quint"] == 4).to_numpy()
    is_bot = (d["quint"] == 0).to_numpy()
    r = d["net_rom"].to_numpy()

    def gap(i: np.ndarray) -> float:
        i = i.astype(int)
        t, b = r[i][is_top[i]], r[i][is_bot[i]]
        return float(t.mean() - b.mean()) if len(t) and len(b) else float("nan")

    lo, hi = cluster_bootstrap_ci(
        np.arange(len(d), dtype=float), keys, gap, n_boot=N_BOOT, seed=SEED
    )
    comp = decompose(d.assign(return_on_margin=d["return_on_margin"]))
    prem_gap = float(comp.loc[top.index, "premium"].mean() - comp.loc[bot.index, "premium"].mean())
    tot_gap = float(top["return_on_margin"].mean() - bot["return_on_margin"].mean())
    prem_share = prem_gap / tot_gap if tot_gap != 0 else float("nan")
    res = {
        "stage": "discovery_2019_2024",
        "n": len(d),
        "decile_spearman": rho,
        "top_minus_bottom": float(top["net_rom"].mean() - bot["net_rom"].mean()),
        "tmb_ci_low": lo,
        "tmb_ci_high": hi,
        "premium_share_of_gap": prem_share,
        "retail_share_top_quintile_median": float(top["retail_share"].median()),
        "retail_share_bottom_quintile_median": float(bot["retail_share"].median()),
        "sharpe_top_quintile": sharpe(top["net_rom"].to_numpy()),
    }
    # The mechanism check is meaningful only for a positive gap: a negative gap mostly
    # "carried by premium" is not a selector that sells bigger options, it is no selector.
    mech = tot_gap > 0 and prem_share < 0.5
    passed = rho >= 0.60 and lo > 0 and mech
    print("  decile means:", [f"{v:+.4f}" for v in dec.values])
    return passed, res


def causal_book(d: pd.DataFrame) -> np.ndarray:
    d = d.sort_values("announce_date")
    sig = d["retail_share"].to_numpy(dtype=float)
    ad = pd.to_datetime(d["announce_date"]).to_numpy()
    take = np.zeros(len(d), dtype=bool)
    for i in range(len(d)):
        prior = sig[(ad < ad[i]) & np.isfinite(sig)]
        if np.isfinite(sig[i]) and prior.size >= MIN_HIST and sig[i] >= np.quantile(prior, Q):
            take[i] = True
    return pd.Series(take, index=d.index).reindex(d.index).to_numpy()


def against_null(d: pd.DataFrame, label: str) -> tuple[bool, dict]:
    d = d[np.isfinite(d["retail_share"]) & np.isfinite(d["net_rom"])].sort_values("announce_date")
    take = causal_book(d)
    book = d[take]
    rng = np.random.default_rng(SEED)
    pool = d["net_rom"].to_numpy()
    null = np.array([sharpe(rng.choice(pool, len(book), replace=False)) for _ in range(N_NULL)])
    x = book["net_rom"].to_numpy()
    lo, hi = sharpe_ci(x, book["entry_date"])
    diff_lo, diff_hi = float(np.quantile(sharpe(x) - null, 0.025)), float(
        np.quantile(sharpe(x) - null, 0.975)
    )
    res = {
        "stage": label,
        "n": len(book),
        "sharpe_book": sharpe(x),
        "book_ci_low": lo,
        "book_ci_high": hi,
        "null_median": float(np.median(null)),
        "diff_ci_low": diff_lo,
        "diff_ci_high": diff_hi,
    }
    return diff_lo > 0, res


def test_t3() -> pd.DataFrame:
    blocks = megacap_blocks()
    rows = []
    disc = attach_retail_share(blocks["discovery_2019_2024"])
    ok, r = discovery(disc)
    rows.append(r)
    print(f"  T3 discovery: {'PASS' if ok else 'FAIL'}  {r}")
    if ok:
        hold = attach_retail_share(blocks["holdout_2013_2018"])
        ok, r = against_null(hold, "validation_2013_2018")
        rows.append(r)
        print(f"  T3 validation: {'PASS' if ok else 'FAIL'}  {r}")
        if ok:
            led = pd.read_csv(LEDGER, parse_dates=["entry_date", "announce_date"])
            ok, r = against_null(attach_retail_share(led), "confirmation_2025_2026")
            rows.append(r)
            print(f"  T3 confirmation: {'PASS' if ok else 'FAIL'}  {r}")
    print(f"\n  T3 PRIMARY: {'PASS' if ok else 'FAIL'}")
    return pd.DataFrame(rows)
