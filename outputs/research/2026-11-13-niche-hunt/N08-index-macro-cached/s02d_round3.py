"""s02d_round3.py: N08 discovery round 3. Concentrate the event: short tenors only (block D).

Diagnosis (s02c_diag.log): the release-night surplus falls with tenor, as it should if the
premium is a fixed amount of event variance diluted by ordinary days (Dubinsky et al. 2019). The
rule keeps release nights whose traded contract has at most 3 calendar days to expiry at entry,
a quantity known at 15:59. Trials 2,307 (T4 hedged hold, R), 2,308 (T4, R plus PCE),
2,309 (T1 buy-back at 10:00, R), 2,310 (T4 QQQ, R plus PCE), 2,311 (T4 IWM, R plus PCE).

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s02d_round3.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("disc", HERE / "s02_discovery.py")
disc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(disc)
MAX_DTE = 3.0  # calendar days to expiry at entry; the release plus at most one ordinary session

a = pd.read_parquet(HERE / "trades_all.parquet")
b = pd.read_parquet(HERE / "trades_round2.parquet")
df = pd.concat([a, b], ignore_index=True)
df = df[(df["block"] == "D") & (df["dte"] <= MAX_DTE)].copy()
assert df["entry"].max() < pd.Timestamp("2025-01-01")
print(f"rows with dte <= {MAX_DTE}: {len(df)}")
r = df["ev_cpi"] | df["ev_nfp"]
rp = r | df["ev_pce"]
rows: list[dict[str, object]] = []
disc.score(df, "T4", "SPY", r, "R=cpi|nfp hedged hold dte<=3", 2307, rows=rows)
disc.score(df, "T4", "SPY", rp, "R+=cpi|nfp|pce hedged hold dte<=3", 2308, rows=rows)
disc.score(df, "T1", "SPY", r, "R=cpi|nfp overnight dte<=3", 2309, rows=rows)
disc.score(df, "T4", "QQQ", rp, "R+=cpi|nfp|pce hedged hold dte<=3", 2310, rows=rows)
disc.score(df, "T4", "IWM", rp, "R+=cpi|nfp|pce hedged hold dte<=3", 2311, rows=rows)
pd.DataFrame(rows).to_csv(HERE / "discovery_round3.csv", index=False)
