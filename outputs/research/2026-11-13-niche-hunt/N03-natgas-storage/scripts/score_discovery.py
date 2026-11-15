"""score_discovery.py: scores trials 2142-2144 on the discovery block (2002-05 to 2018-12) only.

Also prints a roll-detection check that uses no event outcome. The held-out block is never
touched here: the panel is cut to the discovery span before any statistic is computed.

Usage:
  python -I scripts/score_discovery.py <lane_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def main() -> None:
    lane = Path(sys.argv[1])
    sys.path.insert(0, str(lane / "scripts"))
    import lib

    f = lib.load_futures(lane)
    r = lib.same_contract_returns(f)
    roll = r[r["is_roll"]]
    prev = f.shift(1).loc[roll.index]
    naive = np.abs(np.log(f.loc[roll.index, "c1"] / prev["c1"]))
    spliced = np.abs(np.log(f.loc[roll.index, "c1"] / prev["c2"]))
    print(f"roll days {len(roll)}; spliced return smaller than naive on {(spliced < naive).mean():.1%}")
    print(f"median |naive| {naive.median():.4f}, median |spliced| {spliced.median():.4f}")
    big = r.loc[r.index >= lib.FIRST_EIA_RELEASE, "r_c1"].abs()
    print(f"same-contract C1 |r| > 0.25 on {(big > 0.25).sum()} days (check for splices)")

    p, funnel = lib.weekly_panel(r)
    print("funnel (all weeks 2002-05 to file end):")
    print(funnel)
    d = lib.block(p, lib.DISCOVERY)
    print(f"discovery weeks {len(d)}: {d['week'].min().date()} to {d['week'].max().date()}")
    out = {
        "2142_rho_c1": lib.rho_stats(d, "1"),
        "2143_rho_c2": lib.rho_stats(d, "2"),
        "2144_short_c1": lib.short_stats(d),
    }
    for k, v in out.items():
        print(k, json.dumps({a: round(b, 5) for a, b in v.items()}))
    (lane / "logs" / "discovery_results.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
