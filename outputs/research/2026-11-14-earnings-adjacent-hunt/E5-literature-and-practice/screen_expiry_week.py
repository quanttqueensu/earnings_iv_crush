"""
screen_expiry_week.py
Exploratory screen of the option-expiration-week stock effect (lane E5, trial 2,804).

Long an equal-weight basket of the project's optioned names and short the S&P 500 over each
monthly expiration week (Monday to the third Friday), net of a fixed weekly round trip, against
the same basket in other weeks. Declarations are in ``diagnosis.log``; the held-out block runs
only after ``freeze_expiry_week.md`` exists and its recorded hashes match.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/screen_expiry_week.py --block discovery
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/screen_expiry_week.py --block heldout

References
----------
Stivers, C. and Sun, L. (2013). Returns and option activity over the option-expiration week for
S&P 100 stocks. Journal of Banking and Finance 37(11), 4226-4240.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

from screens import CFG, ROOT, SPOTS, _is_split, _market  # noqa: E402

from earnings_iv_crush.research.protocol import block_is_clean, date_clustered_ci  # noqa: E402

FREEZE = HERE / "freeze_expiry_week.md"


# ── data ──


def _third_friday(year: int, month: int) -> pd.Timestamp:
    first = pd.Timestamp(year=year, month=month, day=1)
    off = (4 - first.weekday()) % 7
    return first + pd.Timedelta(days=off + 14)


def weekly_panel() -> tuple[pd.DataFrame, dict[str, int]]:
    """Equal-weight basket minus S&P 500, one row per calendar week, with the expiry flag."""
    mkt = _market()
    mkt = mkt[(mkt.index >= "2018-12-01") & (mkt.index <= CFG.last_date)]
    wk = mkt.index.to_period("W-SUN")
    m_week = (1 + mkt).groupby(wk).prod() - 1
    last_day = pd.Series(mkt.index, index=mkt.index).groupby(wk).max()
    rets: list[pd.Series] = []
    funnel = {"names": 0, "name_weeks_split_dropped": 0}
    for f in sorted(SPOTS.glob("*.parquet")):
        px = pd.read_parquet(f).dropna()
        px["date"] = pd.to_datetime(px["date"])
        px = px.drop_duplicates("date").set_index("date")["close"].astype(float).abs().sort_index()
        px = px[px.index.isin(last_day.to_numpy())]
        if len(px) < 2:
            continue
        ratio = px / px.shift(1)
        # A weekly ratio is only valid between consecutive week-ends.
        pos = pd.Series(np.searchsorted(last_day.to_numpy(), px.index.to_numpy()), index=px.index)
        ok = (pos - pos.shift(1)) == 1
        bad = pd.Series(_is_split(ratio.to_numpy()), index=ratio.index)
        funnel["name_weeks_split_dropped"] += int((bad & ok).sum())
        r = (ratio - 1)[ok & ~bad]
        r.index = r.index.to_period("W-SUN")
        rets.append(r.rename(f.stem))
        funnel["names"] += 1
    panel = pd.concat(rets, axis=1)
    ew = panel.mean(axis=1, skipna=True)
    cnt = panel.notna().sum(axis=1)
    df = pd.DataFrame({"ew": ew, "n_names": cnt, "mkt": m_week.reindex(ew.index)})
    df["adj"] = df.ew - df.mkt
    third = {
        _third_friday(y, m).to_period("W-SUN") for y in range(2018, 2026) for m in range(1, 13)
    }
    df["expiry_week"] = [p in third for p in df.index]
    df["week_end"] = [p.end_time.normalize() for p in df.index]
    df = df[(df.week_end >= pd.Timestamp(CFG.first_date)) & (df.n_names >= 100)]
    if df.mkt.isna().any():
        raise ValueError("market return missing for some weeks")
    funnel["weeks"] = len(df)
    funnel["expiry_weeks"] = int(df.expiry_week.sum())
    funnel["min_names_per_week"] = int(df.n_names.min())
    return df, funnel


# ── scoring ──


def score(df: pd.DataFrame, block: str) -> dict[str, object]:
    cut = pd.Timestamp(CFG.disc_end)
    d = df[df.week_end <= cut] if block == "discovery" else df[df.week_end > cut]
    ex, ot = d[d.expiry_week], d[~d.expiry_week]

    def ci(s: pd.Series, dates: pd.Series) -> dict[str, float]:
        iv = date_clustered_ci(s.to_numpy(), dates.to_numpy(), stat=np.mean)
        return {"point": iv.point, "low": iv.low, "high": iv.high, "n": iv.n}

    res: dict[str, object] = {"block": block, "round_trip_cost": CFG.round_trip}
    res["t2804_net_mean_expiry_weeks"] = ci(ex.adj - CFG.round_trip, ex.week_end)
    res["t2804_gross_expiry_weeks"] = ci(ex.adj, ex.week_end)
    res["t2804_gross_other_weeks"] = ci(ot.adj, ot.week_end)
    diff = ex.adj.mean() - ot.adj.mean()
    rng = np.random.default_rng(20261114)
    boots = [
        rng.choice(ex.adj.to_numpy(), len(ex)).mean() - rng.choice(ot.adj.to_numpy(), len(ot)).mean()
        for _ in range(10_000)
    ]
    res["t2804_expiry_minus_other"] = {
        "point": float(diff),
        "low": float(np.quantile(boots, 0.025)),
        "high": float(np.quantile(boots, 0.975)),
    }
    res["t2804_pass"] = bool(res["t2804_net_mean_expiry_weeks"]["low"] > 0 and diff > 0)
    return res


def _verify_freeze() -> None:
    if not FREEZE.exists():
        raise SystemExit("held-out refused: freeze note missing")
    text = FREEZE.read_text(encoding="utf-8")
    m = re.search(r"screen_expiry_week\.py sha256: ([0-9a-f]{64})", text)
    if not m or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != m.group(1):
        raise SystemExit("held-out refused: scorer hash does not match the freeze note")
    body, _, tail = text.rpartition("note sha256: ")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != tail.strip()[:64]:
        raise SystemExit("held-out refused: freeze note hash does not match")


def main() -> None:
    ap = argparse.ArgumentParser(description="Option-expiration-week screen (trial 2,804)")
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    if a.block == "heldout":
        _verify_freeze()
        clean, clash = block_is_clean(
            ROOT / "research" / "ledger" / "blocks.csv",
            panel="crsp_weekly_basket",
            period="2022-24",
            outcome_family="stock_return_direction",
            feature_family="option_expiry_calendar",
        )
        print(f"block_is_clean: {clean}; clashes: {len(clash)}")
    df, funnel = weekly_panel()
    print("funnel:", json.dumps(funnel))
    res = score(df, a.block)
    res["funnel"] = funnel
    (HERE / f"expiry_week_{a.block}.json").write_text(
        json.dumps(res, indent=2, default=float), encoding="utf-8"
    )
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
