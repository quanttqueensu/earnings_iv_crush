"""
study.py
Stacked execution levers (hedged exit, parity leg choice) under the G1 gate on the event straddle.

Scores the pre-registration in ``prereg.md`` exactly as frozen.

Usage
-----
    python research/selection/2026-11-09-combined-levers-hedged-hold/study.py

References
----------
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option pricing of earnings
announcement risks. Review of Financial Studies 32(2), 646-687.
Goyal, A. and Saretto, A. (2009). Cross-section of option returns and volatility. Journal of
Financial Economics 94(2), 310-326.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    N_BOOT,
    SEED,
    date_clustered_ci,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
RES = ROOT / "outputs" / "research"
HH = RES / "2026-11-02-hedged-event-hold"
PARITY = RES / "2026-11-02-parity-leg-choice" / "events_amend01.parquet"
ZOO = RES / "ml_zoo" / "events_full.parquet"

# ── frozen specification (prereg.md) ─────────────────────────────────────────

TERM_Q = 2 / 3
SPREAD_Q = 0.5
MIN_PRIOR = 200
NULL_PCT_PASS = 95.0
TENOR_EDGES = [-1, 1, 4, 9, 100_000]
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]
BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}
KEYS = ["ticker", "entry_date"]


# ── data ─────────────────────────────────────────────────────────────────────


def load_events() -> pd.DataFrame:
    """Arm H events joined to zoo features and the parity add-on; funnel printed."""
    hh = pd.concat(
        [
            pd.read_parquet(HH / "events.parquet"),
            pd.read_parquet(HH / "events_confirm_2025_26.parquet"),
        ],
        ignore_index=True,
    )
    n_hh = len(hh)
    hh = hh[hh["status"] == "ok"].copy()
    z = pd.read_parquet(
        ZOO, columns=["ticker", "entry_date", "announce_date", "block", "iv_term_spread"]
    )
    z = z[z["block"] != "megacap"]
    p = pd.read_parquet(PARITY, columns=["ticker", "entry_date", "status_p", "adv_pos"])
    for f in (hh, z, p):
        f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    d = hh.merge(z, on=KEYS, how="inner", validate="one_to_one")
    d = d.merge(p, on=KEYS, how="left", validate="one_to_one")
    used = (d["status_p"] == "ok") & d["adv_pos"].notna()
    d["parity_add"] = np.where(used, d["adv_pos"], 0.0)
    d["C"] = d["H"] + d["parity_add"]
    d["half_spread"] = (d["mid0"] - d["s0"]) / d["mid0"]
    d["announce_date"] = pd.to_datetime(d["announce_date"]).dt.normalize()
    d["year"] = d["announce_date"].dt.year
    dte = (pd.to_datetime(d["expiry"]) - pd.to_datetime(d["exit_date"])).dt.days
    d["tenor"] = pd.cut(dte, TENOR_EDGES, labels=TENOR_LABELS).astype(str)
    print(
        f"funnel: {n_hh} hedged-hold rows, {len(hh)} ok, {len(d)} joined to broad zoo, "
        f"parity used on {int(used.sum())}, H finite {int(d['H'].notna().sum())}"
    )
    if d["C"].isna().any():
        raise ValueError(f"{int(d['C'].isna().sum())} events have no outcome C")
    return d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)


def causal_quantile(v: np.ndarray, t: np.ndarray, q: float) -> np.ndarray:
    """Quantile of finite values with strictly earlier dates; NaN under MIN_PRIOR of them."""
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        prior = v[(t < t[i]) & np.isfinite(v)]
        if len(prior) >= MIN_PRIOR:
            out[i] = np.quantile(prior, q)
    return out


def assign(d: pd.DataFrame) -> pd.DataFrame:
    t = d["announce_date"].to_numpy()
    term, hs = d["iv_term_spread"].to_numpy(float), d["half_spread"].to_numpy(float)
    q_term = causal_quantile(term, t, TERM_Q)
    q_hs = causal_quantile(hs, t, SPREAD_Q)
    scored = np.isfinite(q_term) & np.isfinite(q_hs) & np.isfinite(term) & np.isfinite(hs)
    d = d.assign(scored=scored, g1=scored & (term >= q_term) & (hs <= q_hs))
    print(f"funnel: scored {int(scored.sum())}, G1 selected {int(d['g1'].sum())}")
    return d


# ── statistics ───────────────────────────────────────────────────────────────


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _within_tenor(block: np.ndarray) -> float:
    """Selected-count-weighted mean of within-bucket differences; columns y, selected, bucket."""
    y, f, c = block[:, 0], block[:, 1] == 1.0, block[:, 2]
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= 2 and int((~f & m).sum()) >= 2:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def tenor_matched_null(y: np.ndarray, sel: np.ndarray, bucket: np.ndarray) -> float:
    """Percentile of the selected mean among same-count draws within each tenor bucket."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(bucket == u) for u in np.unique(bucket)]
    counts = [int(sel[g].sum()) for g in groups]
    obs = float(y[sel].mean())
    draws = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = np.concatenate(
            [rng.choice(g, k, replace=False) for g, k in zip(groups, counts, strict=True) if k]
        )
        draws[b] = y[idx].mean()
    return float(100.0 * (draws < obs).mean())


def score_block(d: pd.DataFrame, name: str) -> dict:
    y0, y1 = BLOCKS[name]
    b = d[d["scored"] & d["year"].between(y0, y1)]
    sel = b["g1"].to_numpy(bool)
    bucket = pd.Categorical(b["tenor"], TENOR_LABELS).codes.astype(float)
    y = b["C"].to_numpy(float)
    dates = b["announce_date"]
    trio = np.column_stack([y, sel.astype(float), bucket])
    return {
        "block": name,
        "n_scored": len(b),
        "n_selected": int(sel.sum()),
        "P1_sharpe": date_clustered_ci(y[sel], dates[sel]),
        "P1_mean": date_clustered_ci(y[sel], dates[sel], _mean),
        "P2_null_pct": tenor_matched_null(y, sel, bucket),
        "P2_within_tenor": _within_tenor(trio),
        "P2_within_tenor_ci": cluster_bootstrap_ci(
            trio, dates.to_numpy(), _within_tenor, n_boot=N_BOOT, seed=SEED
        ),
        "sec_C_all": date_clustered_ci(y, dates, _mean),
        "sec_H_selected": date_clustered_ci(b["H"].to_numpy(float)[sel], dates[sel], _mean),
        "sec_parity_selected": float(b["parity_add"].to_numpy(float)[sel].mean()),
        "selected_by_tenor": b.loc[sel, "tenor"].value_counts().to_dict(),
    }


def show(r: dict) -> None:
    lo, hi = r["P2_within_tenor_ci"]
    print(f"\n{r['block']}: scored {r['n_scored']}, G1 selected {r['n_selected']}")
    print(f"  P1 per-trade Sharpe of C (net, on m0): {r['P1_sharpe']}")
    print(f"  P1 mean C per trade (net, fraction of m0): {r['P1_mean']}")
    print(f"  P2 tenor-matched null percentile (mean C): {r['P2_null_pct']:.1f}")
    print(
        f"  P2 within-tenor selected minus unselected: {r['P2_within_tenor']:+.4f} [{lo:+.4f}, {hi:+.4f}]"
    )
    print(f"  sec: C all scored {r['sec_C_all']}")
    print(
        f"  sec: H under G1 {r['sec_H_selected']}; parity add under G1 {r['sec_parity_selected']:+.5f}"
    )
    print(f"  sec: selected by tenor {r['selected_by_tenor']}")


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = assign(load_events())
    OUT.mkdir(parents=True, exist_ok=True)
    d[KEYS + ["announce_date", "tenor", "scored", "g1", "H", "parity_add", "C"]].to_parquet(
        OUT / "events.parquet", index=False
    )
    res = {k: score_block(d, k) for k in BLOCKS}
    for r in res.values():
        show(r)
    dsc, val, con = res["discovery"], res["validation"], res["confirmation"]
    book = val["P1_sharpe"].low > 0 and con["P1_sharpe"].low > 0 and dsc["P1_sharpe"].point > 0
    gate = dsc["P2_null_pct"] >= NULL_PCT_PASS and val["P2_null_pct"] >= NULL_PCT_PASS
    if book and gate:
        verdict = "PASS, conditional on blocks partly seen"
    elif gate and not book:
        verdict = "FAIL: selection without a book"
    else:
        verdict = "FAIL"
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    main()
