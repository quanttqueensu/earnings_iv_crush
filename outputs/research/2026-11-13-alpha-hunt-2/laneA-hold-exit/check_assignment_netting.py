"""
check_assignment_netting.py
Descriptive check of lane C's accounting point (its trial 1856): the stored hedged hold unwinds the
whole stock hedge at the settlement close and also pays 5 bp disposal on the assigned share. Under
physical assignment the in-the-money leg delivers (short call) or takes (short put) one share, which
nets against the hedge, so only the residual ``h_prev - sign(settle - K)`` trades, at the floored
half-spread, with no disposal. This recomputes H on that basis and the perfect-foresight
hold-or-buy-back ceiling with it. Not a trial: no rule is scored.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneA-hold-exit/check_assignment_netting.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402
from earnings_iv_crush.research.hedged_hold import straddle_delta, year_frac  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402
from simulate import DISP, FLOOR, load_crsp  # noqa: E402

HOLD = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
FEAT = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"


def netting_gain(r: pd.Series, g: pd.DataFrame) -> float:
    """(old unwind cost + disposal - netted residual cost) / m0 for one event; 0 if no hedge."""
    t1, exp, k = pd.Timestamp(r["exit_date"]), pd.Timestamp(r["expiry"]), float(r["strike"])
    sess = nyse_sessions(t1, exp)
    p = g.reindex(sess)
    closes = p["prc"].to_numpy(float)
    n = len(closes) - 1
    if n == 0:
        return 0.0  # no hedge to net against: the assigned share is still disposed of
    settle = float(closes[-1])
    hs_last = max(float(((p["ask"] - p["bid"]) / 2 / p["prc"]).iloc[n - 1]), FLOOR)
    h_prev = straddle_delta(closes[n - 1], k, year_frac(sess[n - 1], exp), float(r["sigma"]))
    intr = abs(settle - k)
    old = abs(h_prev) * settle * hs_last + (DISP * settle if intr > 0 else 0.0)
    resid = h_prev - np.sign(settle - k) if intr > 0 else h_prev
    new = abs(resid) * settle * hs_last
    return (old - new) / float(r["m0"])


def main() -> None:
    crsp = load_crsp()
    ev = pd.read_parquet(HOLD)[["ticker", "entry_date", "strike"]]
    f = pd.read_parquet(FEAT)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    for y0, y1 in ((2013, 2018), (2019, 2024)):
        d = pd.read_parquet(HERE / f"sim_{y0}_{y1}.parquet")
        d = d.merge(ev.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"],
                    how="left", validate="1:1")
        d = d.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"],
                    how="left", validate="1:1")
        d["gain"] = [netting_gain(r, crsp[int(r["permno"])]) for _, r in d.iterrows()]
        d["H_net"] = d["H"] + d["gain"]
        dates = pd.to_datetime(d["exit_date"])
        mean = lambda a: float(np.mean(a))  # noqa: E731
        lev = date_clustered_ci(d["H_net"].to_numpy(float), dates, mean)
        gain = date_clustered_ci(d["gain"].to_numpy(float), dates, mean)
        orc = date_clustered_ci(np.maximum(d["H_net"], d["B"]).to_numpy(float), dates, mean)
        orc0 = float(np.maximum(d["H"], d["B"]).mean())
        print(f"{y0}-{y1} N {len(d)} | netting gain {gain.point:+.4%} [{gain.low:+.4%}, "
              f"{gain.high:+.4%}] | H stored {d['H'].mean():+.4%} -> netted {lev.point:+.4%} "
              f"[{lev.low:+.4%}, {lev.high:+.4%}] | oracle max(H,B) {orc0:+.4%} -> "
              f"{orc.point:+.4%} [{orc.low:+.4%}, {orc.high:+.4%}]")


if __name__ == "__main__":
    main()
