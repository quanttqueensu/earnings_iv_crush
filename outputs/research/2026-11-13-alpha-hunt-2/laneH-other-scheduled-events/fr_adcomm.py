"""fr_adcomm.py: pull FDA advisory committee meeting notices from the Federal Register API.

The Federal Register publishes each FDA advisory committee meeting notice at least 15 days
before the meeting (21 CFR 14.20), so the publication date proves the meeting date was public
in advance. Output: fr_adcomm_raw.parquet (one row per notice).
"""
from __future__ import annotations

import time

import pandas as pd
import requests

URL = "https://www.federalregister.gov/api/v1/documents.json"
FIELDS = ["document_number", "title", "abstract", "publication_date", "html_url",
          "raw_text_url", "type"]


def pull(year: int) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        params = [("conditions[agencies][]", "food-and-drug-administration"),
                  ("conditions[type][]", "NOTICE"),
                  ("conditions[term]", '"Notice of Meeting" advisory committee'),
                  ("conditions[publication_date][gte]", f"{year}-01-01"),
                  ("conditions[publication_date][lte]", f"{year}-12-31"),
                  ("per_page", "200"), ("page", str(page))]
        params += [("fields[]", f) for f in FIELDS]
        r = requests.get(URL, params=params, timeout=60, headers={"User-Agent": "research-client"})
        r.raise_for_status()
        b = r.json()
        rows += b.get("results", [])
        if page >= b.get("total_pages", 1):
            break
        page += 1
        time.sleep(0.5)
    return rows


allrows = []
for y in range(2018, 2025):
    rr = pull(y)
    print(y, len(rr))
    allrows += rr
df = pd.DataFrame(allrows)
df = df[df["title"].str.contains("Advisory Committee", case=False, na=False)]
print("advisory committee notices", len(df))
df.to_parquet("fr_adcomm_raw.parquet")
print(df["title"].value_counts().head(30))
