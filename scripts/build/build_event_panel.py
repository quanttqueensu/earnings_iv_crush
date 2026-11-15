"""
build_event_panel.py
Build the point-in-time earnings-event panel from the WRDS R2 mirror.

Orchestrates ``earnings_iv_crush.data.wrds_panel.build_event_panel`` over the
full 1996-2024 sample (fit 1996-2011, holdout 2012-2024), writes the two
artifacts downstream research pieces consume, and runs the independent
reference check: a 5,000-row random sample of the panel is joined against
I/B/E/S's own ``tr_ibes.surpsum`` surprise file on ``(ticker, anndats)``,
restricted to the same ``EPS``/``QTR``/``usfirm=1`` slice the panel is built
from, and the panel's ``actual - meanest`` is reconciled against I/B/E/S's own
``actual - surpmean`` on level, sign and correlation. ``surpmean`` is the
consensus *level* I/B/E/S struck the surprise against, not the surprise, so it
is the difference that is the reference quantity, see
:func:`_surpsum_reference_check`.

The first CRSP ``dsf`` pull reads ~29 years of the candidate permno universe
year-by-year (see ``wrds_panel.load_crsp_daily``); at roughly 60s/year this
is a 40-60 minute run on a cold cache. Reruns skip the pull when both output
parquet files already exist and cover the requested window, unless
``--refresh`` is passed.

Run: ``python scripts/build/build_event_panel.py``
     ``python scripts/build/build_event_panel.py --refresh``
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import (
    wrds_panel,  # noqa: E402
    wrds_r2,  # noqa: E402
)

OUT_DIR = Path("outputs") / "research"
EVENTS_PATH = OUT_DIR / "panel_events.parquet"
DAILY_PATH = OUT_DIR / "panel_daily.parquet"
START, END = "1996-01-01", "2024-12-31"
REFERENCE_SAMPLE_N = 5000
REFERENCE_SEED = 0
REFERENCE_MIN_LEVEL_MATCH = 0.95  # `actual` must reconcile against I/B/E/S's own surprise file


def _cache_covers_window(start: str, end: str) -> bool:
    """True when both artifacts exist and panel_events spans [start, end].

    The bounds are checked against what a *built* panel can actually contain,
    not against the request literally. The first announcement in the window
    lands days after ``start`` (1996-01-03 for a 1996-01-01 request: the 1st is
    a holiday and nobody reports on the 2nd), so requiring ``min(anndats) <=
    start`` is a condition no correct build can ever satisfy, it made the
    cache miss unconditionally and re-ran the 40-60 minute CRSP pull on every
    invocation. The panel covers the window when its first event is not later
    than one reporting quarter into it and its last is not earlier than one
    quarter short of the end.
    """
    if not (EVENTS_PATH.exists() and DAILY_PATH.exists()):
        return False
    try:
        ev = pd.read_parquet(EVENTS_PATH, columns=["anndats"])
    except Exception:
        return False
    if ev.empty:
        return False
    lo, hi = ev["anndats"].min(), ev["anndats"].max()
    quarter = pd.Timedelta(days=95)
    return lo <= pd.Timestamp(start) + quarter and hi >= pd.Timestamp(end) - quarter


def _surpsum_reference_check(events: pd.DataFrame) -> float:
    """Validate the panel's surprise against I/B/E/S's own independently-computed one.

    ``tr_ibes.surpsum`` is I/B/E/S's Surprise History file. It carries the
    realised ``actual`` and ``surpmean``, and ``surpmean`` is the **consensus
    estimate level** I/B/E/S used to strike the surprise, *not* the surprise
    itself. The reference surprise is therefore ``actual - surpmean``, and the
    panel's surprise is ``actual - meanest``; comparing the sign of the latter
    against the sign of ``surpmean`` compares a surprise against an EPS level,
    which agrees roughly whenever the firm both has positive EPS and beat
    consensus and is not a validity check at all.

    The join is also restricted to the same slice the panel is built from
    (``measure='EPS'``, ``fiscalp='QTR'``, ``usfirm=1``) before deduplication:
    without ``fiscalp``, an annual-period row can win the ``(ticker, anndats)``
    dedupe and be compared against a quarterly consensus.

    Reports three independent agreements, the ``actual`` level, the surprise
    sign, and the surprise correlation, and raises when the level agreement
    falls below :data:`REFERENCE_MIN_LEVEL_MATCH`, which is the failure that
    would mean the point-in-time join is picking the wrong row.

    Parameters
    ----------
    events : pd.DataFrame
        The built panel_events frame (post-filter).

    Returns
    -------
    float
        Fraction of matched rows whose surprise *sign* agrees with I/B/E/S's.
        NaN if no rows matched.
    """
    rng = np.random.default_rng(REFERENCE_SEED)
    n = min(REFERENCE_SAMPLE_N, len(events))
    sample = events.sample(n=n, random_state=int(rng.integers(0, 2**32 - 1)))

    tickers = sorted(sample["ibes_ticker"].unique())
    lo, hi = sample["anndats"].min().date(), sample["anndats"].max().date()
    surp = wrds_r2.read_table(
        "tr_ibes",
        "surpsum",
        columns=["ticker", "measure", "fiscalp", "usfirm", "anndats", "actual", "surpmean"],
        filters=[
            ("measure", "=", "EPS"),
            ("fiscalp", "=", "QTR"),
            ("usfirm", "=", 1),
            ("ticker", "in", tickers),
            ("anndats", ">=", lo),
            ("anndats", "<=", hi),
        ],
    )
    surp["anndats"] = pd.to_datetime(surp["anndats"])
    surp = surp.dropna(subset=["surpmean", "actual"]).drop_duplicates(["ticker", "anndats"])
    surp = surp.rename(columns={"actual": "actual_ibes"})[
        ["ticker", "anndats", "actual_ibes", "surpmean"]
    ]

    merged = sample.merge(
        surp, left_on=["ibes_ticker", "anndats"], right_on=["ticker", "anndats"], how="inner"
    )
    if merged.empty:
        print("surpsum reference check: no rows matched; cannot validate the panel's surprise.")
        return float("nan")

    ours = merged["actual"] - merged["meanest"]
    theirs = merged["actual_ibes"] - merged["surpmean"]

    level_match = float(np.isclose(merged["actual"], merged["actual_ibes"], atol=1e-6).mean())
    sign_agree = np.sign(ours) == np.sign(theirs)
    sign_agree = sign_agree | (np.sign(ours) == 0) | (np.sign(theirs) == 0)
    sign_match = float(sign_agree.mean())
    corr = float(pd.Series(ours).corr(pd.Series(theirs)))

    print(
        f"surpsum reference check: {len(merged):,}/{n:,} sampled events matched on "
        f"(ticker, anndats), EPS/QTR/usfirm=1.\n"
        f"  actual level agrees        : {level_match:.1%}\n"
        f"  surprise sign agrees       : {sign_match:.1%}\n"
        f"  surprise correlation       : {corr:.4f}"
    )
    if level_match < REFERENCE_MIN_LEVEL_MATCH:
        raise RuntimeError(
            f"surpsum reference check FAILED: the panel's `actual` matches I/B/E/S's own on only "
            f"{level_match:.1%} of sampled events (floor {REFERENCE_MIN_LEVEL_MATCH:.0%}). The "
            "point-in-time consensus selection is picking the wrong row, or the split basis "
            "differs. Stop and diagnose; do not build research on this panel."
        )
    return sign_match


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--refresh", action="store_true", help="ignore cached artifacts, rebuild")
    ap.add_argument("--no-progress", action="store_true", help="disable the CRSP-pull progress bar")
    args = ap.parse_args()

    if not args.refresh and _cache_covers_window(args.start, args.end):
        print(
            f"cached artifacts at {EVENTS_PATH} / {DAILY_PATH} already cover the window; "
            "skipping the pull (pass --refresh to force a rebuild)."
        )
        events = pd.read_parquet(EVENTS_PATH)
        _surpsum_reference_check(events)
        return

    print(
        "no cached build covering the requested window: pulling the WRDS R2 mirror. "
        "CRSP dsf is read year-by-year (~60s/year on a cold cache) -> ETA ~40-60 minutes "
        f"for the full {args.start}..{args.end} window."
    )
    t0 = time.time()
    events, daily = wrds_panel.build_event_panel(
        args.start, args.end, progress=not args.no_progress
    )
    elapsed = time.time() - t0
    print(f"build finished in {elapsed / 60:.1f} min")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events.to_parquet(EVENTS_PATH, index=False)
    daily.to_parquet(DAILY_PATH, index=False)
    print(f"wrote {EVENTS_PATH} ({len(events):,} rows)")
    print(f"wrote {DAILY_PATH} ({len(daily):,} rows)")

    assert (
        events["statpers"] < events["anndats"]
    ).all(), "look-ahead assertion failed: statpers must strictly precede anndats for every event"
    print("look-ahead assertion OK: statpers < anndats for every event.")

    _surpsum_reference_check(events)


if __name__ == "__main__":
    main()
