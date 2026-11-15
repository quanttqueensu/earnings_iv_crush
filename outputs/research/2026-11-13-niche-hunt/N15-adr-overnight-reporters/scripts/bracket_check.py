"""
bracket_check.py
Entry-only check that the cached (D1, D2) pair brackets a pending announcement: the event
variance an upcoming announcement adds to the front expiry shows as front ATM vol above the next
expiry's. Uses the D1 chain only, so it is available before the trade and carries no outcome.

Writes ``cache/bracket_<year>.parquet`` with ``iv_front``, ``iv_next``, ``term_ratio`` and the
implied jump variance from the two-expiry split.

Usage
-----
    python .../scripts/bracket_check.py --year 2025
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402

LANE = Path(__file__).resolve().parents[1]
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
MIN_GAP = 7  # days between front and next expiry: the weekly after the front, as the config's jump split


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, required=True)
    a = ap.parse_args()
    ev = pd.read_parquet(LANE / "cache" / f"events_{a.year}.parquet")
    ev = ev[ev["status"].isin(["ok", "no_exit_leg"])]
    rows = []
    for r in ev.itertuples(index=False):
        c = _parse_chain(pd.read_parquet(CHAINS / f"{r.ticker}_{pd.Timestamp(r.d1).date()}.parquet"))
        c = c.reset_index(drop=True)
        e1 = pd.Timestamp(r.expiry)
        exps = sorted(pd.Timestamp(x) for x in c["expiry"].unique())
        e2 = next((e for e in exps if (e - e1).days >= MIN_GAP), None)
        q2 = hh.atm_quote(c, e2, pd.Timestamp(r.d1)) if e2 is not None else None
        iv2 = q2.iv if q2 is not None else np.nan
        js = (
            hh.split_jump_variance(r.iv1, hh.year_frac(r.d1, e1), iv2, q2.t)
            if q2 is not None and np.isfinite(iv2) and np.isfinite(r.iv1)
            else None
        )
        rows.append(
            {
                "ticker": r.ticker,
                "d1": r.d1,
                "iv_front": r.iv1,
                "iv_next": iv2,
                "term_ratio": r.iv1 / iv2 if iv2 and np.isfinite(iv2) else np.nan,
                "jump_var": js.jump_var if js is not None else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    out.to_parquet(LANE / "cache" / f"bracket_{a.year}.parquet")
    print(f"bracket check {a.year}: {len(out)} events, term ratio defined on "
          f"{int(out['term_ratio'].notna().sum())}")


if __name__ == "__main__":
    main()
