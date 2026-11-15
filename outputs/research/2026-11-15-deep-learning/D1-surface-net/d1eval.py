"""
d1eval.py
Lane D1 fold construction and scoring: rolling-origin development folds, quarterly
walk-forward refit windows, the log-score comparison against L4 with date-clustered
intervals and years positive, and the economic comparison of the selected book against the
unconditional book, the tight-spread-per-date screen at matched participation and the
participation-matched random null.

The tight-spread-per-date screen reproduces review correction 1 of the slate tests
(``2026-11-14-slate-tests/SUMMARY.md``): on each entry date it takes the same number of events
as the model selects that date, those with the smallest 15:59 straddle half-spread (laneE panel
``half_spread``), ties broken by the stable event order. ``decompose_selection.py`` does not
contain it (it holds the causal-median spread gate), so it is reproduced here from that text.

Basis: every book figure is a mean per trade in % of m0, net at the touch, not annualised;
per-trade Sharpe is reported beside it. Intervals are date-clustered 95% (5,000 draws over
announcement dates, seed 0, the protocol defaults).

Usage
-----
    import d1eval; rows = d1eval.dev_folds(D)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import d1lib  # noqa: F401  (imports pyarrow before torch)
import numpy as np
import pandas as pd

from earnings_iv_crush.research.protocol import (
    N_BOOT,
    SEED,
    date_clustered_ci,
    matched_random_null,
    per_trade_sharpe,
)

DEV_YEARS = (2016, 2017, 2018)


@dataclass
class Fold:
    origin: pd.Timestamp
    end: pd.Timestamp
    train: np.ndarray
    val: np.ndarray
    score: np.ndarray


def _base_ok(D: Any) -> np.ndarray:
    inp = D.inp
    return (
        np.isfinite(inp.l4_loc)
        & np.isfinite(inp.l4_scale)
        & (inp.l4_scale > 0)
        & np.isfinite(inp.feats).all(axis=1)
        & np.isfinite(D.ev["U_pct"].to_numpy(float))
        & (D.ev["U_pct"].to_numpy(float) > 0)
    )


def make_fold(D: Any, origin: pd.Timestamp, end: pd.Timestamp, val_days: int) -> Fold:
    """Train on events with expiry before ``origin``; early-stop on those entered in the last
    ``val_days`` before it; predict events entered in ``[origin, end)``."""
    ev = D.ev
    ok = _base_ok(D)
    entry = ev["entry_date"].to_numpy("datetime64[ns]")
    expiry = ev["expiry"].to_numpy("datetime64[ns]")
    o, e = np.datetime64(origin, "ns"), np.datetime64(end, "ns")
    train = ok & np.isfinite(D.inp.z) & (expiry < o)
    val = train & (entry >= np.datetime64(origin - pd.Timedelta(days=val_days), "ns"))
    score = ok & (entry >= o) & (entry < e)
    if (expiry[train] >= o).any():
        raise AssertionError("a training row expires on or after the refit date")
    return Fold(origin, end, np.flatnonzero(train), np.flatnonzero(val), np.flatnonzero(score))


def dev_folds(D: Any, val_days: int) -> list[Fold]:
    return [
        make_fold(D, pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01"), val_days)
        for y in DEV_YEARS
    ]


def quarter_folds(D: Any, start: str, end: str, val_days: int) -> list[Fold]:
    qs = pd.date_range(start, end, freq="QS")
    return [make_fold(D, qs[i], qs[i + 1], val_days) for i in range(len(qs) - 1)]


# ── log score ────────────────────────────────────────────────────────────────


def _iv(c: Any, nd: int = 4) -> dict[str, Any]:
    return {
        "point": round(c.point, nd),
        "low": round(c.low, nd),
        "high": round(c.high, nd),
        "N": c.n,
        "clusters": c.clusters,
    }


def log_score_gain(
    ls: np.ndarray, ref: np.ndarray, clusters: np.ndarray, years: np.ndarray
) -> dict[str, Any]:
    """Mean per-event gain ``ls - ref`` (nats per event, H_net space) with its date-clustered
    interval, and the gain by year."""
    ok = np.isfinite(ls) & np.isfinite(ref)
    g = (ls - ref)[ok]
    out: dict[str, Any] = {"gain": _iv(date_clustered_ci(g, clusters[ok], np.mean))}
    by = {}
    for y in np.unique(years[ok]):
        m = years[ok] == y
        by[int(y)] = {"gain": round(float(g[m].mean()), 4), "N": int(m.sum())}
    out["by_year"] = by
    out["years_positive"] = int(sum(v["gain"] > 0 for v in by.values()))
    out["n_years"] = len(by)
    out["dropped_no_score"] = int((~ok).sum())
    return out


# ── books ────────────────────────────────────────────────────────────────────


def tight_screen(
    selected: np.ndarray, half_spread: np.ndarray, dates: np.ndarray
) -> np.ndarray:
    """Per entry date, the same number of events as ``selected`` with the smallest
    half-spread (stable order on ties)."""
    out = np.zeros(selected.size, bool)
    d = pd.to_datetime(pd.Series(dates)).to_numpy()
    for t in np.unique(d):
        idx = np.flatnonzero(d == t)
        k = int(selected[idx].sum())
        if k == 0:
            continue
        hs = half_spread[idx]
        if not np.isfinite(hs).all():
            raise ValueError(f"non-finite half-spread on {t}")
        out[idx[np.argsort(hs, kind="stable")[:k]]] = True
    return out


def _paired_diff_ci(
    v: np.ndarray, a: np.ndarray, b: np.ndarray, clusters: np.ndarray
) -> dict[str, Any]:
    """``mean(v[a]) - mean(v[b])`` with a date-clustered percentile interval (the two books
    resampled together, by announcement date)."""
    keys = pd.to_datetime(pd.Series(clusters)).dt.normalize().to_numpy()
    uniq, inv = np.unique(keys, return_inverse=True)
    G = uniq.size
    sa = np.bincount(inv, weights=np.where(a, v, 0.0), minlength=G)
    na = np.bincount(inv, weights=a.astype(float), minlength=G)
    sb = np.bincount(inv, weights=np.where(b, v, 0.0), minlength=G)
    nb = np.bincount(inv, weights=b.astype(float), minlength=G)
    point = sa.sum() / na.sum() - sb.sum() / nb.sum()
    rng = np.random.default_rng(SEED)
    draws = np.empty(N_BOOT)
    for i in range(N_BOOT):
        w = np.bincount(rng.integers(0, G, G), minlength=G)
        draws[i] = (w @ sa) / (w @ na) - (w @ sb) / (w @ nb)
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    return {"point": round(float(point), 4), "low": round(float(lo), 4),
            "high": round(float(hi), 4), "N_a": int(a.sum()), "N_b": int(b.sum()),
            "clusters": int(G)}


def book_comparison(
    v: np.ndarray, selected: np.ndarray, half_spread: np.ndarray, dates: np.ndarray,
    clusters: np.ndarray,
) -> dict[str, Any]:
    """The selected book against the unconditional pool, the tight screen and the null.

    ``v`` is the outcome (% of m0) on the eligible pool; every array is over the pool.
    """
    if not np.isfinite(v).all():
        raise ValueError("the pool must hold outcomes only")
    sel = selected.astype(bool)
    out: dict[str, Any] = {"N_pool": int(v.size), "N_selected": int(sel.sum())}
    if sel.sum() < 2 or sel.all():
        out["note"] = "degenerate selection; no comparison"
        return out
    tight = tight_screen(sel, half_spread, dates)
    out["unconditional_mean"] = _iv(date_clustered_ci(v, clusters, np.mean), 3)
    out["selected_mean"] = _iv(date_clustered_ci(v[sel], clusters[sel], np.mean), 3)
    out["selected_sharpe_per_trade"] = _iv(
        date_clustered_ci(v[sel], clusters[sel], per_trade_sharpe), 4
    )
    out["tight_mean"] = _iv(date_clustered_ci(v[tight], clusters[tight], np.mean), 3)
    out["tight_sharpe_per_trade"] = _iv(
        date_clustered_ci(v[tight], clusters[tight], per_trade_sharpe), 4
    )
    out["overlap_with_tight"] = round(float((sel & tight).sum() / sel.sum()), 3)
    out["selected_minus_tight"] = _paired_diff_ci(v, sel, tight, clusters)
    out["selected_minus_pool"] = _paired_diff_ci(v, sel, np.ones_like(sel), clusters)
    nc = matched_random_null(v, sel, np.mean)
    out["null_mean"] = {
        "observed": round(nc.observed, 4),
        "null_median": round(float(np.nanmedian(nc.null)), 4),
        "percentile": round(nc.percentile, 2),
    }
    ns = matched_random_null(v, sel, per_trade_sharpe)
    out["null_sharpe"] = {
        "observed": round(ns.observed, 4),
        "null_median": round(float(np.nanmedian(ns.null)), 4),
        "percentile": round(ns.percentile, 2),
    }
    out["pass"] = bool(
        out["selected_minus_tight"]["low"] > 0
        and out["selected_minus_pool"]["low"] > 0
        and out["null_mean"]["percentile"] > 95.0
    )
    return out
