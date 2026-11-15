"""
study.py
Three tests on the hackathon filing and characteristics panels: pre-announced releases with
extended history (P1), a fundamentals composite on the hedged hold (P2) and the direction of the
mispricing score across the announcement (P3). Scores ``prereg.md`` exactly as frozen.

Usage
-----
    python research/selection/2026-11-10-hackathon-panels/study.py [--dry]

References
----------
Zhan, X., Han, B., Cao, J. and Tong, Q. (2022). Option return predictability. Review of Financial
Studies 35(3), 1394-1442.
Engelberg, J., McLean, R. D. and Pontiff, J. (2018). Anomalies and news. Journal of Finance 73(5).
Rogers, J. L., Skinner, D. J. and Van Buskirk, A. (2009). Earnings guidance and market
uncertainty. Journal of Accounting and Economics 48(1), 90-109.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import verify_prereg  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
PANELS = Path.home() / "FIAM_Hackathon_2026" / "temp"
FILINGS = PANELS / "8k_20150101_20260831_identified.parquet"
CHARS = PANELS / "chars_final_with_names.parquet"
DIR_EVENTS = ROOT / "outputs" / "research" / "2026-11-10-pre-event-direction" / "events.parquet"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vol = _load("nonprice", HERE.parent / "2026-11-10-nonprice-selectors-hedged-hold" / "study.py")
dirn = _load(
    "direction", ROOT / "research" / "timing" / "2026-11-10-pre-event-direction" / "study.py"
)

# ── frozen specification (prereg.md) ─────────────────────────────────────────

PRE_WINDOW = (3, 44)
MIN_HISTORY = 120
P1_RANGES = (("2015-04-01", "2018-12-31"), ("2022-01-01", "2026-08-31"))
CHAR_MAX_STALE = 45
P2_POS = ("cash_at", "ocfq_saleq_std", "chcsho_12m", "netis_at", "o_score")
P2_NEG = ("prc", "ebit_sale", "ope_be")
P2_MIN = 6
P3_COLS = ("mispricing_mgmt", "mispricing_perf")
STD = {"discovery": (2015, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)}
MIN_PRIOR = 200


# ── features ─────────────────────────────────────────────────────────────────


def attach_preannounced(d: pd.DataFrame) -> pd.DataFrame:
    """P1 flag from the filing panel, with the history-coverage rule."""
    f = pd.read_parquet(
        FILINGS, columns=["permno", "form_type", "items", "filing_date", "is_amendment"]
    )
    f["filing_date"] = pd.to_datetime(f["filing_date"]).dt.normalize()
    f = f[(f["form_type"] == "8-K") & ~f["is_amendment"].astype(bool)]
    first = f.groupby("permno")["filing_date"].min().to_dict()
    e = f[f["items"].map(lambda x: x is not None and "2.02" in [str(v) for v in x])]
    by = {int(k): np.sort(g["filing_date"].to_numpy()) for k, g in e.groupby("permno")}
    flag = np.zeros(len(d), bool)
    ok = np.zeros(len(d), bool)
    for i, (pn, ann) in enumerate(
        zip(d["permno"].to_numpy(float), d["announce_date"], strict=True)
    ):
        if not np.isfinite(pn) or int(pn) not in first or pd.isna(ann):
            continue
        if first[int(pn)] > ann - pd.Timedelta(days=MIN_HISTORY):
            continue
        ok[i] = True
        days = by.get(int(pn))
        if days is not None:
            gap = (np.datetime64(ann) - days).astype("timedelta64[D]").astype(int)
            flag[i] = bool(((gap >= PRE_WINDOW[0]) & (gap <= PRE_WINDOW[1])).any())
    in_block = np.zeros(len(d), bool)
    for lo, hi in P1_RANGES:
        in_block |= d["announce_date"].between(pd.Timestamp(lo), pd.Timestamp(hi)).to_numpy()
    print(
        f"funnel P1: history covered {int(ok.sum())}, flagged {int((flag & ok).sum())}, "
        f"in block {int((ok & in_block).sum())}"
    )
    return d.assign(P1=flag, P1_cov=ok, P1_def=ok & in_block)


def attach_chars(d: pd.DataFrame) -> pd.DataFrame:
    """Composite S (P2) and M (P3) from monthly cross-sectional percentiles, causal timing."""
    cols = [*P2_POS, *P2_NEG, *P3_COLS]
    c = pd.read_parquet(CHARS, columns=["permno", "eom", *cols])
    c["eom"] = pd.to_datetime(c["eom"]).dt.normalize()
    c[cols] = c.groupby("eom")[cols].rank(pct=True)
    c = c.sort_values("eom")
    by = {int(k): (g["eom"].to_numpy(), g[cols].to_numpy(float)) for k, g in c.groupby("permno")}
    vals = np.full((len(d), len(cols)), np.nan)
    found = 0
    stale = np.timedelta64(CHAR_MAX_STALE, "D")
    for i, (pn, t_in) in enumerate(
        zip(d["permno"].to_numpy(float), d["entry_date"].to_numpy(), strict=True)
    ):
        if not np.isfinite(pn) or int(pn) not in by:
            continue
        eom, v = by[int(pn)]
        j = int(np.searchsorted(eom, t_in, side="left")) - 1
        if j >= 0 and t_in - eom[j] <= stale:
            vals[i] = v[j]
            found += 1
    n_pos, n_neg = len(P2_POS), len(P2_NEG)
    s_parts = np.column_stack([vals[:, :n_pos], 1.0 - vals[:, n_pos : n_pos + n_neg]])
    n_ok = np.isfinite(s_parts).sum(axis=1)
    s = np.where(n_ok >= P2_MIN, np.nansum(s_parts, axis=1) / np.maximum(n_ok, 1), np.nan)
    m_parts = vals[:, n_pos + n_neg :]
    m = np.where(np.isfinite(m_parts).all(axis=1), m_parts.mean(axis=1), np.nan)
    print(
        f"funnel chars: row found {found}, S defined {int(np.isfinite(s).sum())}, "
        f"M defined {int(np.isfinite(m).sum())}"
    )
    return d.assign(S=s, M=m)


# ── scoring ──────────────────────────────────────────────────────────────────


def score_p1(d: pd.DataFrame) -> dict:
    """One pooled test, then sub-blocks as secondary output."""
    print("\nP1 (pooled 2015-18 and 2022-26):")
    vol.BLOCKS["P1"] = {"discovery": (2015, 2026)}
    r = vol.score_block(d, "P1", "discovery")
    print(f"  VERDICT P1: {'PASS' if r['pass'] else 'FAIL'}")
    print("  secondary, unable to rescue:")
    for name, rng in (
        ("2015-18", (2015, 2018)),
        ("2022-24", (2022, 2024)),
        ("2025-26", (2025, 2026)),
    ):
        vol.BLOCKS["P1"] = {name: rng}
        vol.score_block(d, "P1", name)
    d2 = d.assign(P1x=d["P1"], P1x_def=d["P1_cov"] & (d["announce_date"] >= "2015-04-01"))
    vol.BLOCKS["P1x"] = {"all years incl. 2019-21": (2015, 2026)}
    vol.score_block(d2, "P1x", "all years incl. 2019-21")
    return r


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="print funnels and counts, no outcomes")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = attach_chars(attach_preannounced(vol.load_events()))
    b = causal_bins(d["S"].to_numpy(float), d["announce_date"], 5, MIN_PRIOR)
    d = d.assign(P2=b == 4, P2_def=b >= 0)
    vol.BLOCKS["P2"] = STD
    ev = attach_chars(pd.read_parquet(DIR_EVENTS))
    ev["bin_M"] = causal_bins(ev["M"].to_numpy(float), ev["entry_date"], 5, MIN_PRIOR)
    dirn.TRIALS["P3"] = ("M", +1, "R", STD)
    if args.dry:
        yr = d["announce_date"].dt.year
        ok1 = d["P1_def"] & (d["im_bin"] >= 0)
        print(f"P1: scored {int(ok1.sum())} treated {int((ok1 & d['P1']).sum())}")
        e = vol.attach_edgar(vol.attach_carbonarc(vol.attach_similarity(d)))
        both = (e["V3_def"] & e["P1_cov"]).to_numpy()
        agree = float((e.loc[both, "V3"] == e.loc[both, "P1"]).mean())
        print(f"P1 flag agreement with the EDGAR-cache flag: {agree:.3f} on {int(both.sum())}")
        for n, r in STD.items():
            ok = d["P2_def"] & (d["im_bin"] >= 0) & yr.between(*r)
            y3 = ev["exit_date"].dt.year.between(*r)
            print(
                f"{n}: P2 scored {int(ok.sum())} treated {int((ok & d['P2']).sum())}; "
                f"P3 top {int(((ev['bin_M'] == 4) & y3).sum())} "
                f"bottom {int(((ev['bin_M'] == 0) & y3).sum())}"
            )
        return
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"P1": score_p1(d), "P2": vol.score_trial(d, "P2"), "P3": dirn.score_trial(ev, "P3")}
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
