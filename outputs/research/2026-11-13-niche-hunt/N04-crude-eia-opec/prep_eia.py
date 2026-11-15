"""prep_eia.py: parse EIA daily WTI series (HTML history tables) into one daily CSV.

Inputs, free from eia.gov (robots.txt allows /dnav/), fetched 2026-11-13:
    raw/RCLC1_leaf.html  NYMEX WTI futures contract 1 settlement (https://www.eia.gov/dnav/pet/hist/RCLC1D.htm)
    raw/RCLC2_leaf.html  contract 2 (RCLC2D.htm)
    raw/RWTC_leaf.html   Cushing WTI spot (RWTCD.htm)
Output: data/wti_daily.csv with columns date, c1, c2, spot.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N04-crude-eia-opec/prep_eia.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROW = re.compile(r"<td class='B6'>(.*?)</td>(.*?)</tr>", re.S)
CELL = re.compile(r"<td class='B3'>(.*?)</td>", re.S)


def parse(path: Path) -> pd.Series:
    """Weekly-row EIA table to a daily series; blank cells are non-trading days."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    out: dict[pd.Timestamp, float] = {}
    for label, cells in ROW.findall(text):
        label = html.unescape(label).replace("\xa0", " ").strip()
        m = re.match(r"(\d{4}) (\w{3})-\s*(\d+)", label)
        if not m:
            continue
        monday = pd.Timestamp(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        vals = CELL.findall(cells)
        if len(vals) != 5:
            raise ValueError(f"{path.name}: row {label!r} has {len(vals)} cells")
        for k, v in enumerate(vals):
            v = v.strip()
            if v:
                out[monday + pd.Timedelta(days=k)] = float(v)
    if not out:
        raise ValueError(f"{path.name}: no rows parsed")
    return pd.Series(out).sort_index()


def main() -> None:
    cols = {}
    for name, f in (("c1", "RCLC1"), ("c2", "RCLC2"), ("spot", "RWTC")):
        s = parse(HERE / "raw" / f"{f}_leaf.html")
        print(f"{name}: {len(s)} days {s.index.min().date()} to {s.index.max().date()}")
        cols[name] = s
    df = pd.DataFrame(cols)
    df.index.name = "date"
    (HERE / "data").mkdir(exist_ok=True)
    df.to_csv(HERE / "data" / "wti_daily.csv")


if __name__ == "__main__":
    main()
