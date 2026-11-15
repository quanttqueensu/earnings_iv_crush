"""
dev_economics.py
Lane D2, development only: the frozen rule's book on the 2016-18 rolling-origin folds for the
frozen configuration's 2-seed search fit (search/<id>.parquet), against the same comparators the
held-out scorer uses. Reads rows entered before 2019 only. Real data; not a trial.

Usage
-----
    PYTHONPATH=. python outputs/research/2026-11-15-deep-learning/D2-tabular/dev_economics.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import d2lib  # noqa: E402
import pandas as pd  # noqa: E402
import score_heldout as sh  # noqa: E402


def main() -> None:
    fz = json.loads((HERE / "frozen_config.json").read_text(encoding="utf-8"))
    ev = d2lib.load_real(heldout=False, note="dev_economics (2016-18 folds, frozen config)")
    gm = pd.read_parquet(HERE / "search" / f"{fz['primary_config_id']}.parquet")
    sc = gm["scored"].to_numpy(bool)
    res = sh.economics(ev, gm, sc)
    res["label"] = "DEVELOPMENT 2016-18, 2-seed search fit, real data, not a trial"
    (HERE / "dev_economics.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
