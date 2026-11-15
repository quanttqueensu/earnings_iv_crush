"""
s03_iterate.py
Discovery-block iteration declared in diagnosis.log entry 3: trials 2749 to 2752 (2013-2018).

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E3-spillover/s03_iterate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spill  # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> None:
    res = spill.run((2013, 2018), [2749, 2750, 2751, 2752], print)
    (HERE / "iterate_results.json").write_text(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
