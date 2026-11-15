"""fr_parse.py: retry missing notice texts, then extract meeting date(s) and agenda per notice.

Output: adcomm_agendas.csv (one row per notice: publication date, meeting date, committee, agenda).
"""
from __future__ import annotations

import re
import time

import pandas as pd
import requests

df = pd.read_parquet("fr_adcomm_text.parquet")
for i in df.index[df["text"] == ""]:
    for attempt in range(4):
        time.sleep(3 * (attempt + 1))
        try:
            r = requests.get(df.at[i, "raw_text_url"], timeout=90,
                             headers={"User-Agent": "research-client"})
            r.raise_for_status()
            df.at[i, "text"] = r.text
            break
        except Exception as exc:
            print("retry", exc)
print("still empty", (df["text"] == "").sum())
df.to_parquet("fr_adcomm_text.parquet")

MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|"
          "December")
DATE_RE = re.compile(rf"({MONTHS})\s+(\d{{1,2}}),?\s+(?:and\s+\d{{1,2}},?\s+)?(\d{{4}})")


def clean(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", t)


recs = []
for _, r in df.iterrows():
    t = clean(r["text"])
    m = re.search(r"DATES?:(.{0,400})", t)
    dates_txt = m.group(1) if m else ""
    dd = DATE_RE.findall(dates_txt)
    mdates = [pd.Timestamp(f"{a} {b} {c}") for a, b, c in dd]
    # agenda paragraphs: everything between 'Agenda:' and 'FDA intends'/'Procedure:'
    ag = re.findall(r"Agenda:(.*?)(?:FDA intends|Procedure:)", t)
    recs.append({
        "doc": r["document_number"], "pub_date": r["publication_date"],
        "committee": r["title"].split(";")[0],
        "meeting_dates": ";".join(d.strftime("%Y-%m-%d") for d in mdates),
        "dates_txt": dates_txt[:200], "agenda": " || ".join(a.strip() for a in ag)[:3000],
    })
out = pd.DataFrame(recs)
out.to_csv("adcomm_agendas.csv", index=False)
print(len(out), "notices;", (out["meeting_dates"] == "").sum(), "without a parsed date;",
      out["agenda"].str.contains("sponsor|submitted by", case=False).sum(), "with a sponsor")
