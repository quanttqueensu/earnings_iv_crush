"""sponsor_map.py: map FDA advisory committee agenda text to listed tickers.

Ticker mapping is the analyst's (recalled company-to-ticker identities, not fetched). The
economically exposed listed party is used: a partnered drug maps to the listed partner too
(Eisai lecanemab -> BIIB; Sanofi sotagliflozin -> LXRX; Akcea volanesorsen -> AKCA and IONS).
Output: adcomm_events.csv, one row per (meeting date, ticker), and a feasibility funnel.
"""
from __future__ import annotations

import json
import re

import pandas as pd

MAP: dict[str, list[str]] = {
    r"Biogen": ["BIIB"], r"Eisai": ["BIIB"], r"Amgen": ["AMGN"], r"Gilead": ["GILD"],
    r"Regeneron": ["REGN"], r"Eli Lilly|Avid Radiopharm": ["LLY"],
    r"Merck Sharpe?\b|Merck & Co": ["MRK"], r"Pfizer": ["PFE"], r"BioNTech": ["BNTX"],
    r"Bristol[- ]Myers": ["BMY"], r"Celgene": ["CELG", "BMY"], r"Incyte": ["INCY"],
    r"Nektar": ["NKTR"], r"Amarin": ["AMRN"], r"Cytokinetics": ["CYTK"], r"Ardelyx": ["ARDX"],
    r"Janssen|Johnson & Johnson": ["JNJ"], r"AstraZeneca": ["AZN"],
    r"GlaxoSmithKline": ["GSK"], r"Novartis": ["NVS"], r"Novo Nordisk": ["NVO"],
    r"Sanofi": ["SNY", "LXRX"], r"Takeda": ["TAK"], r"Alkermes": ["ALKS"],
    r"Pacira": ["PCRX"], r"Emergent BioSolutions": ["EBS"], r"Mallinckrodt|SpecGx": ["MNK"],
    r"Viatris": ["VTRS"], r"SIGA": ["SIGA"], r"Intercept": ["ICPT"], r"Sage Therapeutics": ["SAGE"],
    r"Insmed": ["INSM"], r"Paratek": ["PRTK"], r"Karyopharm": ["KPTI"], r"Epizyme": ["EPZM"],
    r"Reata": ["RETA"], r"FibroGen": ["FGEN"], r"Provention": ["PRVB"], r"Acadia": ["ACAD"],
    r"Cidara": ["CDTX"], r"TG Therapeutics": ["TGTX"], r"Spectrum Pharm": ["SPPI"],
    r"Veru": ["VERU"], r"Avenue Therapeutics": ["ATXI"], r"Amylyx": ["AMLX"],
    r"Alnylam": ["ALNY"], r"Geron": ["GERN"], r"Lexicon": ["LXRX"], r"Iterum": ["ITRM"],
    r"Stealth BioTher": ["MITO"], r"Trevena": ["TRVN"], r"AcelRx": ["ACRX"],
    r"Akcea": ["AKCA", "IONS"], r"Intra-Cellular": ["ITCI"], r"ChemoCentryx": ["CCXI"],
    r"Mesoblast": ["MESO"], r"Y- ?mAbs": ["YMAB"], r"DURECT": ["DRRX"], r"Agile Thera": ["AGRX"],
    r"GW Pharma": ["GWPH"], r"Horizon Pharma": ["HZNP"], r"Shire": ["SHPG"],
    r"Achaogen": ["AKAO"], r"INSYS": ["INSY"], r"22nd Century": ["XXII"], r"Altria": ["MO"],
    r"R\.\s?J\.\s?Reynolds": ["BTI"], r"BeiGene": ["BGNE"], r"Neovasc": ["NVCN"],
    r"Zevra": ["ZVRA"], r"ARS Pharma": ["SPRY"], r"IceCure": ["ICCM"], r"Correvio": ["CORV"],
    r"ModernaTX|Moderna": ["MRNA"], r"Novavax": ["NVAX"], r"Abbott": ["ABT"],
    r"Medtronic": ["MDT"], r"Boston Scientific": ["BSX"], r"Edwards Lifesciences": ["EW"],
    r"Intuitive Surgical": ["ISRG"], r"Dexcom": ["DXCM"], r"Insulet": ["PODD"],
    r"Teva": ["TEVA"], r"Endo ": ["ENDP"], r"Purdue": [], r"Ionis": ["IONS"],
    r"Vertex": ["VRTX"], r"Jazz": ["JAZZ"], r"Neurocrine": ["NBIX"], r"Exelixis": ["EXEL"],
    r"United Therapeutics": ["UTHR"], r"Corcept": ["CORT"], r"Vanda": ["VNDA"],
    r"Arrowhead": ["ARWR"], r"Vir Bio": ["VIR"], r"AbbVie|Allergan": ["ABBV"],
    r"BioMarin": ["BMRN"], r"Sarepta": ["SRPT"], r"Axsome": ["AXSM"], r"Supernus": ["SUPN"],
    r"Halozyme": ["HALO"], r"Ligand": ["LGND"], r"Catalyst Pharm": ["CPRX"],
    r"Coherus": ["CHRS"], r"Eagle Pharm": ["EGRX"], r"Amphastar": ["AMPH"],
    r"Heron": ["HRTX"], r"Omeros": ["OMER"], r"Rigel": ["RIGL"], r"Clovis": ["CLVS"],
}

ag = pd.read_csv("adcomm_agendas.csv").fillna("")
u = json.load(open("dolt_universe.json"))
univ = set(u["2020-06-17"]) | set(u["2023-05-10"])

rows = []
for _, r in ag.iterrows():
    if not r["meeting_dates"]:
        continue
    text = r["agenda"]
    tick: set[str] = set()
    for pat, tt in MAP.items():
        if re.search(pat, text):
            tick |= set(tt)
    for t in sorted(tick):
        for md in r["meeting_dates"].split(";"):
            rows.append({"meeting_date": md, "pub_date": r["pub_date"], "ticker": t,
                         "committee": r["committee"], "doc": r["doc"],
                         "in_dolt_universe": t in univ, "agenda": text[:400]})
ev = pd.DataFrame(rows).drop_duplicates(["meeting_date", "ticker"])
ev["lead_days"] = (pd.to_datetime(ev["meeting_date"]) - pd.to_datetime(ev["pub_date"])).dt.days
ev = ev[(ev["meeting_date"] >= "2019-01-01") & (ev["meeting_date"] <= "2024-11-08")]
ev.to_csv("adcomm_events.csv", index=False)
print("notices", len(ag), "| with parsed date", (ag["meeting_dates"] != "").sum())
print("ticker-meeting events 2019-01..2024-11:", len(ev), "| distinct tickers", ev.ticker.nunique())
print("in DoltHub universe:", int(ev.in_dolt_universe.sum()))
print("lead days (pub to meeting) min/median:", ev.lead_days.min(), ev.lead_days.median())
print(ev[ev.in_dolt_universe][["meeting_date", "ticker", "committee"]].to_string())
print("outside universe:", sorted(ev[~ev.in_dolt_universe].ticker.unique()))
