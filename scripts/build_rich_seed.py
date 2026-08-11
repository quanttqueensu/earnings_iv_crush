"""
build_rich_seed.py
Build the name-richness seed the forward paper radar labels its book against.

For each name, the seed carries the mean short-ATM-straddle return on premium,
``ret = 1 - |realised_move| / implied_move``, over the validated event tables, and a
flag for whether the name sits in the top 30% by that mean. ``scripts/paper_radar.py``
reads the flag to label each forward trade rich or not; it does not filter on it, so a
revised seed can be applied to an existing book after the fact.

Sources are the three event tables the name-persistence study was validated on
(megacap Databento, broad 2024, broad 2025). The DoltHub S&P pull is deliberately NOT
used: ``research_dolthub_sp500_persistence.py`` is a resumable per-ticker build and the
checkpoint on disk stopped at ticker CHD, so a seed derived from it covers only names
beginning A to C.

Causality: every event in these tables predates the forward book, so a full-sample name
mean is a legitimate prior for trades booked from now on. It is NOT a valid signal for
scoring the historical tables themselves, which is why the research script builds an
expanding leave-current-out prior instead.

Usage:
    python -m scripts.build_rich_seed
    python scripts/build_rich_seed.py --top-q 0.70 --min-events 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

SOURCES = {
    "megacap": Path("outputs/research/events_megacap_databento.parquet"),
    "broad_2024": Path("outputs/research/events_broad_full.parquet"),
    "broad_2025": Path("outputs/research/events_broad_oos_2025.parquet"),
}
OUT = Path("data/rich_set.csv")

MIN_IM = 0.02  # discard events whose implied move is too small to be a real straddle
WINSOR = (0.01, 0.99)  # tame single blow-ups before taking a name mean


def build(top_q: float, min_events: int) -> pd.DataFrame:
    frames = []
    for label, path in SOURCES.items():
        if not path.exists():
            raise FileNotFoundError(f"event table missing: {path.resolve()}")
        d = pd.read_parquet(path)
        d["source"] = label
        frames.append(d)
        print(f"  {label:12s} {len(d):5d} events  {d['ticker'].nunique():4d} names")

    ev = pd.concat(frames, ignore_index=True)
    ev = ev[(ev["implied_move"] >= MIN_IM) & ev["realised_move"].notna()].copy()
    ev["ret"] = 1.0 - ev["realised_move"].abs() / ev["implied_move"]
    lo, hi = ev["ret"].quantile(list(WINSOR))
    ev["ret"] = ev["ret"].clip(lo, hi)

    name = ev.groupby("ticker")["ret"].agg(["mean", "size"])
    name = name[name["size"] >= min_events]
    if name.empty:
        raise RuntimeError(
            f"no name cleared min_events={min_events} across {len(ev)} events - "
            f"refusing to write an empty seed"
        )
    thr = name["mean"].quantile(top_q)
    name["is_rich"] = name["mean"] >= thr

    out = (
        name.reset_index()
        .rename(columns={"mean": "prior_mean_ret", "size": "n_events"})
        .sort_values("prior_mean_ret", ascending=False)
    )
    print(
        f"\n  pooled {len(ev)} events, {len(name)} names with >={min_events} events, "
        f"q{top_q:.2f} threshold {thr:+.4f}, {int(name['is_rich'].sum())} rich"
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-q", type=float, default=0.70, help="rich = top 1-q of names")
    ap.add_argument("--min-events", type=int, default=3, help="events a name needs to qualify")
    args = ap.parse_args()

    print("=== building name-richness seed ===")
    out = build(args.top_q, args.min_events)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"  wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
