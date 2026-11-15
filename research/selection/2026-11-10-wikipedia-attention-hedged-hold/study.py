"""
study.py
Wikipedia attention in the week before the release as a selector for the hedged event hold.

Scores ``prereg.md`` exactly as frozen, importing the loader and statistics of the non-price
selectors study. ``--pull`` fetches and caches the free page-view series; it reads no outcome.

Usage
-----
    python research/selection/2026-11-10-wikipedia-attention-hedged-hold/study.py --pull
    python research/selection/2026-11-10-wikipedia-attention-hedged-hold/study.py [--dry]

References
----------
de Silva, T., So, E. C. and Smith, K. (2025). Losing is optional: retail option trading and
expected announcement volatility. Review of Finance.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import urllib.parse
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
WIKI = ROOT / "data" / "cache" / "wikipedia"
MAP = WIKI / "ticker_article.csv"
API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{article}/daily/20150701/20260831"
)
_spec = importlib.util.spec_from_file_location(
    "nonprice", HERE.parent / "2026-11-10-nonprice-selectors-hedged-hold" / "study.py"
)
assert _spec and _spec.loader
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

# ── frozen specification (prereg.md) ─────────────────────────────────────────

WINDOW_DAYS = 5
BASE_DAYS = 60
BASE_MIN_OBS = 40
TRIAL = "W1"
base.BLOCKS[TRIAL] = {
    "discovery": (2016, 2018),
    "validation": (2019, 2024),
    "confirmation": (2025, 2026),
}


def pull() -> None:
    """Fetch each mapped article's daily views once; a failed article is recorded, not retried."""
    import requests

    m = pd.read_csv(MAP)
    done = miss = 0
    for t, art in zip(m["ticker"], m["article"], strict=True):
        path = WIKI / "views" / f"{t}.json"
        if path.exists():
            continue
        url = API.format(article=urllib.parse.quote(art, safe=""))
        for attempt in range(6):
            r = requests.get(
                url, headers={"User-Agent": "research-script/0.1 (pageview study)"}, timeout=60
            )
            if r.status_code != 429:
                break
            time.sleep(20 * (attempt + 1))  # throttled: back off, never record as missing
        if r.status_code == 429:
            print(f"  {t} {art}: still throttled, left for a later run")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if r.status_code == 200:
            items = [(i["timestamp"][:8], i["views"]) for i in r.json()["items"]]
            path.write_text(json.dumps(items), encoding="utf-8")
            done += 1
        else:
            path.write_text("[]", encoding="utf-8")
            miss += 1
            print(f"  {t} {art}: HTTP {r.status_code}")
        time.sleep(2.0)
    print(f"pulled {done}, failed {miss}")


def attach_attention(d: pd.DataFrame) -> pd.DataFrame:
    """Log ratio of the pre-entry week's mean views to the prior sixty days' median."""
    series: dict[str, pd.Series] = {}
    for p in (WIKI / "views").glob("*.json"):
        items = json.loads(p.read_text(encoding="utf-8"))
        if items:
            s = pd.Series({pd.Timestamp(k): float(v) for k, v in items}).sort_index()
            series[p.stem] = s
    a = np.full(len(d), np.nan)
    funnel = {"no_series": 0, "thin_window": 0, "thin_base": 0, "ok": 0}
    for i, (t, t_in) in enumerate(zip(d["ticker"], d["entry_date"], strict=True)):
        s = series.get(t)
        if s is None:
            funnel["no_series"] += 1
            continue
        w_end = t_in - pd.Timedelta(days=1)
        w_start = w_end - pd.Timedelta(days=WINDOW_DAYS - 1)
        w = s[w_start:w_end]
        if len(w) < WINDOW_DAYS:
            funnel["thin_window"] += 1
            continue
        b = s[w_start - pd.Timedelta(days=BASE_DAYS) : w_start - pd.Timedelta(days=1)]
        if len(b) < BASE_MIN_OBS or b.median() <= 0:
            funnel["thin_base"] += 1
            continue
        a[i] = float(np.log(w.mean() / b.median()))
        funnel["ok"] += 1
    bins = causal_bins(a, d["announce_date"], 5, base.MIN_PRIOR)
    print(f"funnel: {funnel}, binned {int((bins >= 0).sum())}")
    return d.assign(attention=a, W1_def=bins >= 0, W1=bins == 4)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pull", action="store_true", help="fetch page views (no outcome read)")
    ap.add_argument("--dry", action="store_true", help="print funnels and counts, no outcomes")
    args = ap.parse_args(argv)
    if args.pull:
        pull()
        return
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = attach_attention(base.load_events())
    if args.dry:
        yr = d["announce_date"].dt.year
        for n, r in base.BLOCKS[TRIAL].items():
            ok = d["W1_def"] & (d["im_bin"] >= 0) & yr.between(*r)
            print(f"{n}: scored {int(ok.sum())} treated {int((ok & d['W1']).sum())}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    res = base.score_trial(d, TRIAL)
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
