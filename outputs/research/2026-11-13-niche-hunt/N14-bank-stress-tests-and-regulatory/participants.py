"""participants.py: which listed banks appear in each year's Fed stress-test results document.

Reads the pdftotext output of each results PDF under raw/fed/ and searches for the holding
company's name. Output: participants.csv (year, ticker, in_test).
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {
    "JPM": r"JPMorgan Chase", "BAC": r"Bank of America", "C": r"Citigroup",
    "WFC": r"Wells Fargo", "GS": r"Goldman Sachs", "MS": r"Morgan Stanley",
    "USB": r"U\.?\s?S\.? Bancorp", "PNC": r"PNC Financial", "TFC": r"Truist",
    "BBT": r"BB&T", "STI": r"SunTrust", "COF": r"Capital One", "SCHW": r"Charles Schwab",
    "BK": r"Bank of New York Mellon", "STT": r"State Street", "NTRS": r"Northern Trust",
    "AXP": r"American Express", "FITB": r"Fifth Third", "KEY": r"KeyCorp|Keycorp",
    "RF": r"Regions Financial", "HBAN": r"Huntington Bancshares", "MTB": r"M&T Bank",
    "CFG": r"Citizens Financial", "ALLY": r"Ally Financial", "DFS": r"Discover Financial",
    "CMA": r"Comerica", "ZION": r"Zions",
}
FILES = {
    2013: "dfast_dfast_2013_results_20130314.txt", 2014: "dfast_bcreg20140320a1.txt",
    2015: "dfast_bcreg20150305a1.txt", 2016: "dfast_bcreg20160623a1.txt",
    2017: "dfast_2017-dfast-methodology-results-20170622.txt",
    2018: "dfast_2018-dfast-methodology-results-20180621.txt",
    2019: "dfast_2019-dfast-results-20190621.txt", 2020: "2020.txt",
    2021: "2021-dfast-results-20210624.txt", 2022: "2022-dfast-results-20220623.txt",
    2023: "2023-dfast-results-20230628.txt", 2024: "2024-dfast-results-20240626.txt",
    2025: "2025-dfast-results-20250627.txt", 2026: "2026.txt",
}
rows = []
for y, f in FILES.items():
    txt = open(os.path.join(HERE, "raw", "fed", f), encoding="utf-8", errors="ignore").read()
    txt = re.sub(r"\s+", " ", txt)
    for t, pat in NAMES.items():
        # firm-level result tables name each firm repeatedly; one passing mention is not enough
        n = len(re.findall(pat, txt))
        rows.append({"year": y, "ticker": t, "mentions": n, "in_test": n >= 3})
out = pd.DataFrame(rows)
out.to_csv(os.path.join(HERE, "participants.csv"), index=False)
print(out.pivot(index="ticker", columns="year", values="mentions").to_string())
