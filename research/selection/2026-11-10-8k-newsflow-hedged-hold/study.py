"""
study.py
8-K news flow before the release as a selector for the hedged event hold.

Scores the pre-registration in ``prereg.md`` exactly as frozen, importing the loader and
statistics of the non-price selectors study.

Usage
-----
    python research/selection/2026-11-10-8k-newsflow-hedged-hold/study.py [--dry]

References
----------
Heitz, A. R., Narayanamoorthy, G. and Zekhnini, M. (2020). The disappearing earnings announcement
premium. Working paper.
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
_spec = importlib.util.spec_from_file_location(
    "nonprice", HERE.parent / "2026-11-10-nonprice-selectors-hedged-hold" / "study.py"
)
assert _spec and _spec.loader
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

# ── frozen specification (prereg.md) ─────────────────────────────────────────

WINDOW = (3, 60)
TRIAL = "K8"
base.BLOCKS[TRIAL] = {
    "discovery": (2019, 2021),
    "validation": (2022, 2024),
    "confirmation": (2025, 2026),
}


def attach_newsflow(d: pd.DataFrame) -> pd.DataFrame:
    """Count of non-earnings 8-Ks in the window before each announcement."""
    tick = json.loads((base.EDGAR / "company_tickers.json").read_text(encoding="utf-8"))
    cik_of = {v["ticker"].upper(): int(v["cik_str"]) for v in tick.values()}
    k = np.full(len(d), np.nan)
    cache: dict[int, tuple | None] = {}
    for i, (t, ann) in enumerate(zip(d["ticker"], d["announce_date"], strict=True)):
        cik = cik_of.get(str(t).upper().replace("-", "."), cik_of.get(str(t).upper()))
        if cik is None or pd.isna(ann):
            continue
        if cik not in cache:
            f = base._filings(cik)
            if f is None:
                cache[cik] = None
            else:
                e = f[(f["form"] == "8-K") & ~f["items"].str.contains("2.02", regex=False)]
                cache[cik] = (f["day"].min(), e["day"].to_numpy())
        item = cache[cik]
        if item is None or item[0] > ann - pd.Timedelta(days=base.EDGAR_MIN_HISTORY):
            continue
        gap = (np.datetime64(ann) - item[1]).astype("timedelta64[D]").astype(int)
        k[i] = float(((gap >= WINDOW[0]) & (gap <= WINDOW[1])).sum())
    b = causal_bins(k, d["announce_date"], 5, base.MIN_PRIOR)
    print(f"funnel: count defined {int(np.isfinite(k).sum())}, binned {int((b >= 0).sum())}")
    return d.assign(k8=k, K8_def=b >= 0, K8=b == 4)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="print funnels and counts, no outcomes")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = attach_newsflow(base.load_events())
    if args.dry:
        yr = d["announce_date"].dt.year
        for n, r in base.BLOCKS[TRIAL].items():
            ok = d["K8_def"] & (d["im_bin"] >= 0) & yr.between(*r)
            print(f"{n}: scored {int(ok.sum())} treated {int((ok & d['K8']).sum())}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    res = base.score_trial(d, TRIAL)
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
