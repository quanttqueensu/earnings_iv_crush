"""event_variance.py: report-day variance against matched control days, ICE US softs futures.

Implements the construction pre-registered in diagnosis.log (2026-11-13): settle-to-settle log
returns of the Yahoo continuous front month, event-independent stale-day and roll-window filters,
same-weekday controls at plus and minus seven calendar days, per-event excess squared return with
a date-clustered interval, and the event/control variance ratio with an event bootstrap.

Usage:
    python scripts/event_variance.py --block discovery --roots CT KC CC SB --trial-base 2442
The held-out block is refused here; it runs only through heldout_scorer.py after the freeze.

References
----------
Adjemian, M. K. (2012). Quantifying the WASDE announcement effect. AJAE 94(1), 238-256.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

# ── configuration (every number named, rationale in diagnosis.log) ──
BLOCKS = {
    "discovery": ("2000-01-01", "2013-12-31"),
    "heldout": ("2014-01-01", "2026-11-13"),
}
CONTROL_OFFSETS_DAYS = (-7, 7)  # same weekday, one week either side
ROLL_PAD_BEFORE = 5  # weekdays before min(FND, LTD)
ROLL_PAD_AFTER = 2  # weekdays after max(FND, LTD)
N_BOOT_RATIO = 2000
SEED = 7
PASS_RATIO = 1.5
DEDUPE_TARGET_DAY = 10  # WASDE scheduled around the 8th to 12th of the month
CYCLES = {"CT": "HKNVZ", "KC": "HKNUZ", "CC": "HKNUZ", "SB": "HKNV"}
MONTH = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10,
         "X": 11, "Z": 12}


# ── roll windows from ICE contract rules (weekday calendar approximation) ──
def _bdays(year: int, month: int) -> pd.DatetimeIndex:
    start = pd.Timestamp(year, month, 1)
    return pd.bdate_range(start, start + pd.offsets.MonthEnd(0))


def _shift(d: pd.Timestamp, n: int) -> pd.Timestamp:
    return d + pd.offsets.BDay(n)


def fnd_ltd(root: str, year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Approximate first notice day and last trading day for one delivery month."""
    b = _bdays(year, month)
    first, last = b[0], b[-1]
    if root == "CT":
        return _shift(first, -5), _shift(last, -17)
    if root == "KC":
        lnd = _shift(last, -7)
        return _shift(first, -7), _shift(lnd, -1)
    if root == "CC":
        lnd = _shift(last, -10)
        return _shift(b[5], -10), _shift(lnd, -1)
    if root == "SB":
        prev_last = _bdays(*(year, month - 1) if month > 1 else (year - 1, 12))[-1]
        return _shift(prev_last, 1), prev_last
    raise ValueError(root)


def roll_mask(root: str, dates: pd.DatetimeIndex) -> np.ndarray:
    """True where a date sits inside any delivery month's roll window."""
    bad = np.zeros(len(dates), dtype=bool)
    for y in range(dates.min().year - 1, dates.max().year + 2):
        for code in CYCLES[root]:
            fnd, ltd = fnd_ltd(root, y, MONTH[code])
            lo = _shift(min(fnd, ltd), -ROLL_PAD_BEFORE)
            hi = _shift(max(fnd, ltd), ROLL_PAD_AFTER)
            bad |= (dates >= lo) & (dates <= hi)
    return bad


# ── series and events ──
def returns(root: str) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "raw" / "softs_daily.csv", parse_dates=["date"])
    g = d[d.root == root].sort_values("date").set_index("date")
    if g.empty:
        raise ValueError(f"{root}: no rows")
    g["r"] = np.log(g.close / g.close.shift(1))
    g["stale"] = (g.volume == 0) | (g.close == g.close.shift(1)) | g.r.isna()
    g["roll"] = roll_mask(root, g.index)
    g["ok"] = ~g.stale & ~g.roll
    return g


def wasde_dates() -> pd.DatetimeIndex:
    w = pd.read_csv(ROOT / "raw" / "wasde_dates.csv", parse_dates=["date"])
    if w.empty:
        raise ValueError("no WASDE dates")
    # ESMIS lists corrections and re-issues as extra dates; keep one per month, the date closest
    # to the 10th (WASDE is scheduled around the 8th to 12th). Rule fixed before any outcome.
    w["month"] = w.date.dt.to_period("M")
    w["dist"] = (w.date.dt.day - DEDUPE_TARGET_DAY).abs()
    kept = w.sort_values(["month", "dist", "date"]).groupby("month").head(1)
    dropped = len(w) - len(kept)
    if dropped:
        print(f"WASDE dates: {len(w)} listed, {dropped} same-month duplicates dropped")
    return pd.DatetimeIndex(kept.date.sort_values())


@dataclass(frozen=True)
class Result:
    root: str
    block: str
    n_events: int
    mean_excess: float
    excess_lo: float
    excess_hi: float
    ratio: float
    ratio_lo: float
    ratio_hi: float
    robust_ratio: float
    event_share_weekly: float
    funnel: str


def build_events(root: str, block: str, events: pd.DatetimeIndex,
                 months: tuple[int, ...] | None = None) -> tuple[pd.DataFrame, str]:
    g = returns(root)
    lo, hi = (pd.Timestamp(x) for x in BLOCKS[block])
    ev = events[(events >= lo) & (events <= hi)]
    if months is not None:
        ev = ev[ev.month.isin(months)]
    evset = set(events)
    n0 = len(ev)
    in_series = [e for e in ev if e in g.index]
    not_stale = [e for e in in_series if not g.at[e, "stale"]]
    not_roll = [e for e in not_stale if not g.at[e, "roll"]]
    rows = []
    for e in not_roll:
        cs = []
        for k in CONTROL_OFFSETS_DAYS:
            c = e + pd.Timedelta(days=k)
            if c in g.index and g.at[c, "ok"] and c not in evset:
                cs.append(g.at[c, "r"] ** 2)
        if cs:
            rows.append({"date": e, "re2": g.at[e, "r"] ** 2, "rc2": float(np.mean(cs)),
                         "abs_re": abs(g.at[e, "r"]), "abs_rc": float(np.mean(np.sqrt(cs)))})
    funnel = (f"{root} {block}: releases {n0} -> trading day {len(in_series)} -> not stale "
              f"{len(not_stale)} -> outside roll window {len(not_roll)} -> with control {len(rows)}")
    if not rows:
        raise ValueError(f"empty event set: {funnel}")
    return pd.DataFrame(rows), funnel


def score(root: str, block: str, months: tuple[int, ...] | None = None) -> Result:
    df, funnel = build_events(root, block, wasde_dates(), months)
    x = (df.re2 - df.rc2).to_numpy()
    ci = date_clustered_ci(x, df.date, stat=np.mean)
    rng = np.random.default_rng(SEED)
    n = len(df)
    re2, rc2 = df.re2.to_numpy(), df.rc2.to_numpy()
    boots = []
    for _ in range(N_BOOT_RATIO):
        i = rng.integers(0, n, n)
        boots.append(re2[i].mean() / rc2[i].mean())
    ratio = re2.mean() / rc2.mean()
    rlo, rhi = np.percentile(boots, [2.5, 97.5])
    rm = float(np.median(df.abs_re) / np.median(df.abs_rc))
    return Result(root, block, n, float(ci.point), float(ci.low), float(ci.high), float(ratio),
                  float(rlo), float(rhi), rm, float(ratio / (4 + ratio)), funnel)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True, choices=["discovery"])
    ap.add_argument("--roots", nargs="+", default=["CT", "KC", "CC", "SB"])
    ap.add_argument("--trial-base", type=int, required=True)
    ap.add_argument("--months", type=int, nargs="+", default=None)
    a = ap.parse_args()
    for k, root in enumerate(a.roots):
        r = score(root, a.block, tuple(a.months) if a.months else None)
        print(r.funnel)
        print(f"  trial {a.trial_base + k}: N={r.n_events} mean excess r^2 {r.mean_excess:.3e} "
              f"[{r.excess_lo:.3e}, {r.excess_hi:.3e}]  R {r.ratio:.3f} [{r.ratio_lo:.3f}, "
              f"{r.ratio_hi:.3f}]  robust |r| ratio {r.robust_ratio:.3f}  weekly event share "
              f"{r.event_share_weekly:.3f}")


if __name__ == "__main__":
    main()
