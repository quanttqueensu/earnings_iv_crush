"""
study.py
Lottery-like stocks before and after the earnings announcement, traded in the stock against SPY.
Scores ``prereg.md`` exactly as frozen.

Usage
-----
    python research/timing/2026-11-10-lottery-around-earnings/study.py [--dry]

References
----------
Liu, B., Wang, H., Yu, J. and Zhao, S. (2018). Time-varying demand for lottery: speculation ahead
of earnings announcements. Working paper.
Kumar, A. (2009). Who gambles in the stock market? Journal of Finance 64(4), 1889-1933.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import verify_prereg  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
CHARS = Path.home() / "FIAM_Hackathon_2026" / "temp" / "chars_final_with_names.parquet"
_spec = importlib.util.spec_from_file_location(
    "direction", HERE.parent / "2026-11-10-pre-event-direction" / "study.py"
)
assert _spec and _spec.loader
dirn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dirn)

# ── frozen specification (prereg.md) ─────────────────────────────────────────

POS = ("ivol_ff3_21d", "iskew_ff3_21d", "rmax1_21d")
NEG = ("prc",)
MIN_PARTS = 3
LEAD_DAYS = 8
MAX_STALE = 53
PRE, POST = 5, 4
STD = {"discovery": (2015, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}


def attach_windows(ev: pd.DataFrame) -> pd.DataFrame:
    """Market-adjusted returns over the run-up and reversal windows."""
    px = pd.read_parquet(dirn.PRICES)
    spy = px["SPY"].dropna()
    series = {t: px[t].dropna() for t in px.columns}
    pre = np.full(len(ev), np.nan)
    post = np.full(len(ev), np.nan)
    for i, (t, d0, d1) in enumerate(
        zip(ev["ticker"], ev["entry_date"], ev["exit_date"], strict=True)
    ):
        g = series.get(t)
        if g is None or d0 not in g.index or d1 not in g.index or d0 not in spy.index:
            continue
        e, x = g.index.get_loc(d0), g.index.get_loc(d1)
        if e >= PRE and g.index[e - PRE] in spy.index:
            da = g.index[e - PRE]
            pre[i] = g.iloc[e] / g.iloc[e - PRE] - 1 - (spy.loc[d0] / spy.loc[da] - 1)
        if x + POST < len(g) and g.index[x + POST] in spy.index:
            db = g.index[x + POST]
            post[i] = g.iloc[x + POST] / g.iloc[e] - 1 - (spy.loc[db] / spy.loc[d0] - 1)
    print(
        f"funnel: events {len(ev)}, R_pre finite {int(np.isfinite(pre).sum())}, "
        f"R_post finite {int(np.isfinite(post).sum())}"
    )
    return ev.assign(R_pre=pre, R_post=post)


def attach_lottery(ev: pd.DataFrame) -> pd.DataFrame:
    """Composite lottery score from monthly cross-sectional percentiles, predating the window."""
    cols = [*POS, *NEG]
    c = pd.read_parquet(CHARS, columns=["permno", "eom", *cols])
    c["eom"] = pd.to_datetime(c["eom"]).dt.normalize()
    c[cols] = c.groupby("eom")[cols].rank(pct=True)
    c = c.sort_values("eom")
    by = {int(k): (g["eom"].to_numpy(), g[cols].to_numpy(float)) for k, g in c.groupby("permno")}
    score = np.full(len(ev), np.nan)
    lead, stale = np.timedelta64(LEAD_DAYS, "D"), np.timedelta64(MAX_STALE, "D")
    for i, (pn, t_in) in enumerate(
        zip(ev["permno"].to_numpy(float), ev["entry_date"].to_numpy(), strict=True)
    ):
        if not np.isfinite(pn) or int(pn) not in by:
            continue
        eom, v = by[int(pn)]
        j = int(np.searchsorted(eom, t_in - lead, side="right")) - 1
        if j < 0 or t_in - eom[j] > stale:
            continue
        parts = np.concatenate([v[j, : len(POS)], 1.0 - v[j, len(POS) :]])
        if np.isfinite(parts).sum() >= MIN_PARTS:
            score[i] = float(np.nanmean(parts))
    bins = causal_bins(score, ev["entry_date"], 5, 200)
    print(
        f"funnel: lottery score defined {int(np.isfinite(score).sum())}, "
        f"binned {int((bins >= 0).sum())}"
    )
    return ev.assign(lot=score, bin_lot=bins)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="counts only, no outcomes")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    ev = pd.read_parquet(dirn.OUT / "events.parquet")
    ev = attach_lottery(attach_windows(ev))
    if args.dry:
        yr = ev["exit_date"].dt.year
        for n, r in STD.items():
            m = yr.between(*r)
            top = int(((ev["bin_lot"] == 4) & m).sum())
            bottom = int(((ev["bin_lot"] == 0) & m).sum())
            print(f"{n}: top {top} bottom {bottom}")
        return
    dirn.TRIALS["LP"] = ("lot", +1, "R_pre", STD)
    dirn.TRIALS["LR"] = ("lot", -1, "R_post", STD)
    res = {t: dirn.score_trial(ev, t) for t in ("LP", "LR")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
