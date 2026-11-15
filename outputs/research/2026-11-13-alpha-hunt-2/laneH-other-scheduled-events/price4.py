"""price4.py: round-4 pricing (smile-interpolated exit marks) and the model-mark reconciliation.

Runs price3 twice from the cached chains: once model-marking every exit (to reconcile the model
mark against quoted exit mids where the strike is quoted), once in the round-4 mode. Output:
windows4_priced.parquet, reconcile4.log lines on stdout.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import price3

price3.EXIT_MODE = "smile"
price3.FORCE_MODEL = True
price3.OUT = "windows4_forcemodel.parquet"
price3.main()
price3.FORCE_MODEL = False
price3.OUT = "windows4_priced.parquet"
price3.main()
a = pd.read_parquet("windows4_priced.parquet")
b = pd.read_parquet("windows4_forcemodel.parquet")
key = ["event_id", "shift"]
m = a[(a["price_status"] == "ok") & (~a["bounded_exit"].astype(bool))][key + ["mid1", "m0"]].merge(
    b[key + ["mid1"]], on=key, suffixes=("_quote", "_model"))
err = (m["mid1_model"] - m["mid1_quote"]) / m["m0"]
print(f"\nRECONCILE model exit mark vs quoted exit mid, N={len(m)}: mean error "
      f"{err.mean():+.4f} m0, mean abs {err.abs().mean():.4f} m0, p95 abs "
      f"{np.nanpercentile(err.abs(), 95):.4f} m0")
