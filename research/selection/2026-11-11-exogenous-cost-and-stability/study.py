"""
study.py
Exogenous cost instruments, stability and macro overlap as selectors for the hedged event hold.

Scores ``prereg.md`` exactly as frozen, importing the loader and statistics of the non-price
selectors study. Five trials: X1 monthly expiry, X2 penny tick, X3 low idiosyncratic volatility,
X4 stable earnings surprises, X5 macro release on the reaction session.

Usage
-----
    python research/selection/2026-11-11-exogenous-cost-and-stability/study.py [--dry]

References
----------
Cao, J. and Han, B. (2013). Cross section of option returns and idiosyncratic stock volatility.
Journal of Financial Economics.
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
IVOL = ROOT / "outputs" / "research" / "2026-11-02-ivol-max-hedged-hold" / "events.parquet"
WRDS = ROOT / "data" / "processed" / "wrds" / "raw"
MACRO = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"
_spec = importlib.util.spec_from_file_location(
    "nonprice", HERE.parent / "2026-11-10-nonprice-selectors-hedged-hold" / "study.py"
)
assert _spec and _spec.loader
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

# ── frozen specification (prereg.md) ─────────────────────────────────────────

LEG_BAND = (2.0, 4.0)  # one dollar either side of the tick threshold
LEG_THRESHOLD = 3.0  # Penny Interval Program: USD 0.01 below, USD 0.05 at or above
SURPRISE_FLOOR = 0.10  # USD of consensus EPS; stops a near-zero consensus inflating the ratio
SURPRISE_WINDOW = 8
SURPRISE_MIN = 6
N_QUINTILES = 5
_FULL = {"discovery": (2013, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}
base.BLOCKS.clear()
base.BLOCKS.update(
    {
        "X1": _FULL,
        "X2": _FULL,
        "X3": _FULL,
        "X4": {"discovery": (2013, 2018), "validation": (2019, 2024)},
        "X5": {"discovery": (2016, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)},
    }
)


# ── features ─────────────────────────────────────────────────────────────────


def attach_calendar_and_tick(d: pd.DataFrame) -> pd.DataFrame:
    """X1 monthly expiry and X2 leg price against the tick threshold, from the ledger alone."""
    ex = pd.to_datetime(d["expiry"])
    monthly = ((ex.dt.weekday == 4) & ex.dt.day.between(15, 21)) | (
        (ex.dt.weekday == 5) & ex.dt.day.between(16, 22)
    )
    leg = d["mid0"] / 2.0
    return d.assign(
        X1=monthly.to_numpy(),
        X1_def=True,
        X2=(leg < LEG_THRESHOLD).to_numpy(),
        X2_def=leg.between(*LEG_BAND).to_numpy(),
    )


def attach_ivol(d: pd.DataFrame) -> pd.DataFrame:
    """X3: bottom causal quintile of the stored pre-entry idiosyncratic volatility."""
    iv = pd.read_parquet(IVOL, columns=["ticker", "entry_date", "ivol"])
    iv["entry_date"] = pd.to_datetime(iv["entry_date"]).dt.normalize()
    d = d.merge(
        iv.drop_duplicates(["ticker", "entry_date"]),
        on=["ticker", "entry_date"],
        how="left",
        validate="one_to_one",
    )
    bins = causal_bins(d["ivol"].to_numpy(float), d["announce_date"], N_QUINTILES, base.MIN_PRIOR)
    print(
        f"X3 funnel: ivol present {int(d['ivol'].notna().sum())} of {len(d)}, "
        f"binned {int((bins >= 0).sum())}"
    )
    return d.assign(X3_def=bins >= 0, X3=bins == 0)


def attach_surprise_stability(d: pd.DataFrame) -> pd.DataFrame:
    """X4: bottom causal quintile of the median scaled surprise over the prior eight quarters."""
    files = sorted(WRDS.glob("tr_ibes.surpsum.*.parquet"))
    s = next((pd.read_parquet(f) for f in files if "actual" in pd.read_parquet(f).columns), None)
    if s is None:
        raise FileNotFoundError("no IBES surpsum slice with an `actual` column")
    s = s[(s["measure"] == "EPS") & (s["fiscalp"] == "QTR")].dropna(subset=["actual", "surpmean"])
    s["anndats"] = pd.to_datetime(s["anndats"])
    s["u"] = (s["actual"] - s["surpmean"]).abs() / s["surpmean"].abs().clip(lower=SURPRISE_FLOOR)
    link = pd.read_parquet(next(WRDS.glob("wrdsapps_link_crsp_ibes.ibcrsphist.*.parquet")))
    link["sdate"], link["edate"] = pd.to_datetime(link["sdate"]), pd.to_datetime(link["edate"])
    by_ibes = {k: g.sort_values("anndats") for k, g in s.groupby("ticker")}
    by_permno = {int(k): g for k, g in link.dropna(subset=["permno"]).groupby("permno")}
    stab = np.full(len(d), np.nan)
    funnel = {"no_permno": 0, "no_link": 0, "no_series": 0, "thin": 0, "ok": 0}
    for i, (p, t_in) in enumerate(zip(d["permno"], d["entry_date"], strict=True)):
        if pd.isna(p):
            funnel["no_permno"] += 1
            continue
        lk = by_permno.get(int(p))
        if lk is not None:
            lk = lk[(lk["sdate"] <= t_in) & (lk["edate"] >= t_in)]
        if lk is None or lk.empty:
            funnel["no_link"] += 1
            continue
        g = by_ibes.get(lk.sort_values("score")["ticker"].iloc[0])
        if g is None:
            funnel["no_series"] += 1
            continue
        past = g.loc[g["anndats"] < t_in, "u"].tail(SURPRISE_WINDOW)
        if len(past) < SURPRISE_MIN:
            funnel["thin"] += 1
            continue
        stab[i] = float(past.median())
        funnel["ok"] += 1
    bins = causal_bins(stab, d["announce_date"], N_QUINTILES, base.MIN_PRIOR)
    print(f"X4 funnel: {funnel}, binned {int((bins >= 0).sum())}")
    return d.assign(stab=stab, X4_def=bins >= 0, X4=bins == 0)


def attach_macro(d: pd.DataFrame) -> pd.DataFrame:
    """X5: a scheduled CPI, payrolls or FOMC release on the reaction session."""
    m = pd.read_csv(MACRO, parse_dates=["date"])
    days = set(m["date"].dt.normalize())
    lo, hi = m["date"].min(), m["date"].max()
    ex = pd.to_datetime(d["exit_date"]).dt.normalize()
    covered = ex.between(lo, hi)
    print(
        f"X5 funnel: macro calendar {lo.date()} to {hi.date()}, {len(days)} dates; "
        f"events inside the calendar {int(covered.sum())} of {len(d)}"
    )
    return d.assign(X5_def=covered.to_numpy(), X5=(ex.isin(days) & covered).to_numpy())


# ── entry point ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="print funnels and counts, no outcomes")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = base.load_events()
    d = attach_macro(attach_surprise_stability(attach_ivol(attach_calendar_and_tick(d))))
    if args.dry:
        base.dry(d)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    res = [base.score_trial(d, t) for t in base.BLOCKS]
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
