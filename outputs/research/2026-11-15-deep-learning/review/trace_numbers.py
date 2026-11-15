"""
trace_numbers.py
Reviewer scratch check: every decimal number in each lane's evidence.md is searched for in that
lane's (and D0's) json, log, csv and txt files, allowing rounding to the printed precision. Prints
the numbers with no match, with their line, for manual tracing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
NUM = re.compile(r"(?<![\w.])[+-]?\d[\d,]*\.\d+|(?<![\w.])[+-]?\d{1,3}(?:,\d{3})+(?![\d.])")


def corpus_numbers(dirs):
    vals = []
    for d in dirs:
        for p in d.rglob("*"):
            if p.suffix in {".json", ".log", ".csv", ".txt"} and p.is_file() and p.name not in {"diagnosis.log", "STATE.md", "blocks_viewed.csv", "trials.csv"} and "review" not in p.parts:
                for m in NUM.finditer(p.read_text(encoding="utf-8", errors="ignore")):
                    try:
                        vals.append(float(m.group().replace(",", "")))
                    except ValueError:
                        pass
                for m in re.finditer(r"-?\d+\.\d+e-?\d+|-?\d+(?:\.\d+)?", p.read_text(encoding="utf-8", errors="ignore")):
                    try:
                        vals.append(float(m.group()))
                    except ValueError:
                        pass
    return vals


for lane in sys.argv[1:]:
    ld = BASE / lane
    vals = corpus_numbers([ld, BASE / "D0-surface"])
    import numpy as np
    arr = np.array(vals)
    print(f"== {lane}")
    for i, line in enumerate((ld / "evidence.md").read_text(encoding="utf-8").splitlines(), 1):
        for m in NUM.finditer(line):
            s = m.group().replace(",", "")
            x = float(s)
            dec = len(s.split(".")[1]) if "." in s else 0
            tol = 0.5 * 10 ** (-dec) + 1e-12
            hit = np.any(np.abs(arr - x) <= tol) or np.any(np.abs(100 * arr - x) <= tol) or np.any(np.abs(arr - x / 100) <= tol / 100)
            if not hit:
                print(f"  L{i}: {m.group()}  | {line.strip()[:110]}")
