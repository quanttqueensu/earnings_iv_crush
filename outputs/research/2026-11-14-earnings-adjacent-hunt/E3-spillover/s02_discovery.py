"""
s02_discovery.py
Score the declared trials 2742 to 2747 on the discovery block (reaction sessions 2013-2018).

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E3-spillover/s02_discovery.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spill  # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> None:
    res = spill.run((2013, 2018), [2742, 2743, 2744, 2745, 2746, 2747], print)
    (HERE / "discovery_results.json").write_text(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
