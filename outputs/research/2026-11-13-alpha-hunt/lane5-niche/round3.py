"""
round3.py
Round 3 of the lane5-niche hunt: robustness of the early-reporter lead on discovery (2013-18),
two calendar selectors, the capped pre-announced rescue and a small-lot retail proxy (both on
blocks already viewed, exploratory only).

Usage
-----
    python round3.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

import lib

ROOT = Path(__file__).resolve().parents[4]
FILINGS = Path.home() / "FIAM_Hackathon_2026" / "temp" / "8k_20150101_20260831_identified.parquet"
FLOW = ROOT / "data" / "cache" / "flow" / "broad_2025_2026"
PRE_WINDOW = (3, 44)  # as frozen in trial 1,604
MIN_HISTORY = 120
SMALL_LOT = 2  # contracts


def preannounced(d: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Trial 1,604's flag, rebuilt from the filing panel read in place."""
    f = pd.read_parquet(
        FILINGS, columns=["permno", "form_type", "items", "filing_date", "is_amendment"]
    )
    f["filing_date"] = pd.to_datetime(f["filing_date"]).dt.normalize()
    f = f[(f["form_type"] == "8-K") & ~f["is_amendment"].astype(bool)]
    first = f.groupby("permno")["filing_date"].min().to_dict()
    e = f[f["items"].map(lambda x: x is not None and "2.02" in [str(v) for v in x])]
    by = {int(k): np.sort(g["filing_date"].to_numpy()) for k, g in e.groupby("permno")}
    flag, ok = np.zeros(len(d), bool), np.zeros(len(d), bool)
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
    print(f"pre-announced funnel: history covered {int(ok.sum())}, flagged {int((flag & ok).sum())}")
    return pd.Series(flag & ok, index=d.index), pd.Series(ok, index=d.index)


def small_lot_share(d: pd.DataFrame) -> pd.Series:
    """Share of trade prints of at most SMALL_LOT contracts in the traded straddle before 15:59."""
    out = pd.Series(np.nan, index=d.index)
    funnel = {"no_file": 0, "few_trades": 0, "ok": 0}
    sub = d[d["year"] >= 2025]
    for ix, t, ent in zip(sub.index, sub["ticker"], sub["entry_date"], strict=True):
        p = FLOW / f"{t}_{ent:%Y-%m-%d}_pre.parquet"
        if not p.exists():
            funnel["no_file"] += 1
            continue
        x = pq.read_table(
            p, columns=["ts_event", "action", "size"], filters=[("action", "=", "T")]
        ).to_pandas()
        ts = x["ts_event"].dt.tz_convert("America/New_York")
        cut = pd.Timestamp(ent.date(), tz="America/New_York") + pd.Timedelta(hours=15, minutes=59)
        x = x[ts < cut]
        if len(x) < 20:
            funnel["few_trades"] += 1
            continue
        out[ix] = float((x["size"] <= SMALL_LOT).mean())
        funnel["ok"] += 1
    print(f"small-lot funnel (2025-26 events {len(sub)}): {funnel}")
    return out


def one_vote_per_name(d: pd.DataFrame, flag: pd.Series, ok: pd.Series, trial_id: int) -> None:
    """Treated effect with every name weighted equally, bootstrap over names (exploratory)."""
    b = d[ok & (d["im_bin"] >= 0) & d["year"].between(2015, 2026)].copy()
    f = flag[b.index].to_numpy(bool)
    ctrl = b[~f].groupby("cell")["y"].mean()
    tr = b[f].assign(r=lambda x: x["y"] - x["cell"].map(ctrl)).dropna(subset=["r"])
    per = tr.groupby("ticker")["r"].mean().to_numpy()
    rng = np.random.default_rng(lib.SEED)
    draws = np.array([rng.choice(per, per.size).mean() for _ in range(lib.N_BOOT)])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    t = per.mean() / draws.std(ddof=1)
    counts = tr["ticker"].value_counts()
    ex = tr[tr["ticker"] != counts.index[0]]
    print(
        f"preannounced_one_vote_per_name [2015-26, all viewed] treated events {len(tr)}, names "
        f"{per.size}: equal-name-weight effect on y {per.mean():+.4f} [{lo:+.4f}, {hi:+.4f}] "
        f"t {t:+.2f}; event-weighted {tr['r'].mean():+.4f}; dropping the top name "
        f"({counts.iloc[0]} events) {ex['r'].mean():+.4f}; share of names positive "
        f"{np.mean(per > 0):.3f}"
    )
    with lib.TRIALS.open("a", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=lib.FIELDS).writerow(
            {
                "trial_id": trial_id,
                "hypothesis": "preannounced_one_vote_per_name",
                "mechanism": "trial 1,604's pre-announced flag with each name weighted equally, "
                "so habitual pre-releasers cannot carry it; a post hoc rescue on viewed blocks",
                "block": "viewed 2015-2026",
                "n_scored": len(b),
                "n_treated": len(tr),
                "effect": round(per.mean(), 5),
                "ci_low": round(lo, 5),
                "ci_high": round(hi, 5),
                "t": round(t, 3),
                "null_pct": "",
                "verdict": "fail" if lo <= 0 else "pass",
                "label": "exploratory rescue, no clean block",
            }
        )


def main() -> None:
    d = lib.load()
    T = pd.Series(True, index=d.index)
    b = lib.causal_quantile_bins(d["peer_share"].to_numpy(float), d["announce_date"], 3)
    early, early_def = pd.Series(b == 0, index=d.index), pd.Series(b >= 0, index=d.index)

    d["cell_sector"] = d["cell"] * 100 + pd.to_numeric(d["sector"], errors="coerce").fillna(-1)
    lib.score(
        d, early, early_def & d["sector"].notna(), "discovery", hyp="early_sector_neutral",
        trial_id=1764, cell_col="cell_sector",
        mechanism="as 1759 with the contrast taken inside sector as well as implied-move "
        "tercile and tenor, so the financials and industrials tilt cannot carry it",
    )
    print()
    qstart = d["announce_date"].dt.to_period("Q").dt.start_time
    d["season_pos"] = (d["announce_date"] - qstart).dt.days
    sb = lib.causal_quantile_bins(d["season_pos"].to_numpy(float), d["announce_date"], 3)
    lib.score(
        d, pd.Series(sb == 0, index=d.index), pd.Series(sb >= 0, index=d.index), "discovery",
        hyp="early_calendar_position", trial_id=1765,
        mechanism="bottom causal tercile of days since the calendar quarter began: tests "
        "whether the early-reporter effect is season timing rather than order in industry",
    )
    print()
    both = early_def & (sb >= 0)
    blk = d[both & d.year.between(2013, 2018) & (d.im_bin >= 0)]
    r = blk["y"] - blk.groupby("cell")["y"].transform("mean")
    for name, m in (
        ("early in industry and early in calendar", early & (sb == 0)),
        ("early in industry, not early in calendar", early & (sb != 0)),
        ("early in calendar, not early in industry", ~early & (sb == 0)),
        ("neither", ~early & (sb != 0)),
    ):
        mm = m[blk.index]
        print(f"descriptive, discovery: {name}: n {int(mm.sum())}, mean cell-residual y "
              f"{r[mm].mean():+.4f}")
    print()
    lib.score(
        d, ~d["month"].isin([3, 6, 9, 12]), T, "discovery", hyp="on_cycle_month", trial_id=1766,
        mechanism="prints outside March, June, September and December: off-cycle fiscal years "
        "report alone, with no peer read-through, and moved more than priced in diag1; the "
        "seller keeps more on-cycle",
    )
    print()
    try:
        lib.score(
            d, d["days_to_qend"] <= 5, T, "discovery", hyp="quarter_end_window", trial_id=1767,
            mechanism="reaction within five days of a calendar quarter end: rebalancing and "
            "balance-sheet constraints make dealers charge more for event vol",
        )
    except ValueError as e:
        print(f"quarter_end_window NOT SCORED: {e}")
    print()
    flag, ok = preannounced(d)
    one_vote_per_name(d, flag, ok, 1768)
    print("pre-announced treated events by sector (share):",
          d.loc[flag, "sector"].value_counts(normalize=True).round(3).head(5).to_dict())
    print()
    sl = small_lot_share(d)
    sbins = lib.causal_quantile_bins(sl.to_numpy(float), d["announce_date"], 3, min_prior=150)
    lib.score(
        d, pd.Series(sbins == 2, index=d.index), pd.Series(sbins >= 0, index=d.index),
        "viewed_2025_26", hyp="small_lot_share_top_tercile", trial_id=1769,
        label="exploratory, block already viewed",
        mechanism="top causal tercile of the share of prints of at most two contracts in the "
        "traded straddle over the three sessions to 15:59 on the entry day: retail demand "
        "enriches the event premium",
    )
    sub = d[sl.notna()]
    print(
        "small-lot share Spearman with half-spread",
        round(sub["half_spread"].corr(sl[sub.index], method="spearman"), 3),
        "with implied move",
        round(sub["implied_move"].corr(sl[sub.index], method="spearman"), 3),
    )


if __name__ == "__main__":
    main()
