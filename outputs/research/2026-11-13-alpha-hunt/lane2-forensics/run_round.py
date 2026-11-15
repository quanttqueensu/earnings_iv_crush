"""
run_round.py
Score one round of rules on a block and append to trials.csv.

Usage
-----
    python run_round.py --round 1
    python run_round.py --ids 1659 --block heldout    # needs freeze_note.md
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from lib import LEDGER, load, score
from rules import RULES, add_pcts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--round", type=int, default=0)
    ap.add_argument("--ids", type=int, nargs="*", default=[])
    ap.add_argument("--block", default="discovery")
    ap.add_argument("--nboot", type=int, default=2000)
    a = ap.parse_args()
    full = add_pcts(pd.read_parquet(LEDGER))  # features only; causal percentiles need all dates
    keys = load(a.block)[["ticker", "entry_date"]]
    d = keys.merge(full, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    ids = a.ids or [k for k, v in RULES.items() if v[3] == a.round]
    for tid in ids:
        name, mech, sign, rnd, fn = RULES[tid]
        flag, defined = fn(d)
        score(d, np.asarray(flag, bool), np.asarray(defined, bool), trial_id=tid, name=name,
              mechanism=mech, sign=sign, rnd=rnd, block=a.block, n_boot=a.nboot)  # fmt: skip


if __name__ == "__main__":
    main()
