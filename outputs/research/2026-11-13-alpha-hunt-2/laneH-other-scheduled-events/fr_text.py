"""fr_text.py: fetch full text of each FDA advisory committee notice and extract date and agenda."""
from __future__ import annotations

import re
import time

import pandas as pd
import requests

df = pd.read_parquet("fr_adcomm_raw.parquet")
texts = []
for i, u in enumerate(df["raw_text_url"]):
    for attempt in range(3):
        try:
            r = requests.get(u, timeout=60, headers={"User-Agent": "research-client"})
            r.raise_for_status()
            texts.append(r.text)
            break
        except Exception as exc:
            print("retry", exc)
            time.sleep(2)
    else:
        texts.append("")
    time.sleep(0.2)
df["text"] = texts
print("empty texts", (df["text"] == "").sum())
df.to_parquet("fr_adcomm_text.parquet")
