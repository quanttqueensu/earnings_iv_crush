"""
study.py
Non-price information selectors for the hedged event hold.

Scores the pre-registration in ``prereg.md`` exactly as frozen: five trials (V1 stable 10-K
language, V2 demand in line, V3 pre-announced releases, V4 concurrent filers, V5 any flag), each
on discovery first and on the later blocks only if the earlier one passes.

Usage
-----
    python research/selection/2026-11-10-nonprice-selectors-hedged-hold/study.py --dry
    python research/selection/2026-11-10-nonprice-selectors-hedged-hold/study.py

References
----------
Cohen, L., Malloy, C. and Nguyen, Q. (2020). Lazy prices. Journal of Finance 75(3), 1371-1415.
Rogers, J. L., Skinner, D. J. and Van Buskirk, A. (2009). Earnings guidance and market
uncertainty. Journal of Accounting and Economics 48(1), 90-109.
Arif, S., Marshall, N. T., Schroeder, J. H. and Yohn, T. L. (2019). A growing disparity in
earnings disclosure mechanisms. Journal of Accounting and Economics 68(1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    N_BOOT,
    SEED,
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
SIM = ROOT / "data" / "cache" / "lazy_prices" / "similarity_10k.parquet"
CIKMAP = ROOT / "data" / "cache" / "lazy_prices" / "cik_permno.parquet"
CA = ROOT / "data" / "cache" / "carbonarc" / "ca_demand.parquet"
EDGAR = ROOT / "data" / "cache" / "edgar"

# ── frozen specification (prereg.md) ─────────────────────────────────────────

MARGIN_SPOT_FRAC = 0.20
MIN_PRIOR = 200
NULL_PCT_PASS = 95.0
TENOR_EDGES = [-1, 1, 4, 9, 100_000]
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]
SIM_COL = "10K_1A__sim_cosine"
SIM_MAX_AGE = 400  # days from the 10-K's information date to entry
SIM_REF_WINDOW = 365
SIM_PCT = 0.80
CA_MAX_STALE = 62
PRE_WINDOW = (3, 44)  # days before the announcement for a preliminary Item 2.02 8-K
EDGAR_MIN_HISTORY = 120
CONC_BEFORE_H, CONC_AFTER_H = 0.5, 1.0
CONC_LOOKBACK_MIN_DAYS = 45
CONC_N, CONC_K = 4, 3
BLOCKS = {
    "V1": {"discovery": (2015, 2018), "validation": (2019, 2024), "confirmation": (2025, 2026)},
    "V2": {"discovery": (2017, 2020), "validation": (2021, 2024), "confirmation": (2025, 2026)},
    "V3": {"discovery": (2019, 2021), "validation": (2022, 2024), "confirmation": (2025, 2026)},
    "V4": {"discovery": (2019, 2021), "validation": (2022, 2024), "confirmation": (2025, 2026)},
    "V5": {"discovery": (2019, 2021), "validation": (2022, 2024), "confirmation": (2025, 2026)},
}


# ── data ─────────────────────────────────────────────────────────────────────


def load_events() -> pd.DataFrame:
    """Hedged-hold events with announcement date, permno, implied move, tenor and cell."""
    hh = pd.concat(
        [
            pd.read_parquet(HH / "events.parquet"),
            pd.read_parquet(HH / "events_confirm_2025_26.parquet"),
        ],
        ignore_index=True,
    )
    hh = hh[hh["status"] == "ok"].copy()
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "announce_date", "permno"])
    for x in (hh, f):
        x["entry_date"] = pd.to_datetime(x["entry_date"]).dt.normalize()
    d = hh.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    latest = (
        f.dropna(subset=["permno"]).sort_values("entry_date").groupby("ticker")["permno"].last()
    )
    d["permno"] = d["permno"].fillna(d["ticker"].map(latest))
    d["announce_date"] = pd.to_datetime(d["announce_date"]).dt.normalize()
    d["F0"] = (d["m0"] - d["s0"]) / MARGIN_SPOT_FRAC
    d["implied_move"] = d["mid0"] / d["F0"]
    dte = (pd.to_datetime(d["expiry"]) - pd.to_datetime(d["exit_date"])).dt.days
    d["tenor"] = pd.cut(dte, TENOR_EDGES, labels=TENOR_LABELS).astype(str)
    d["y"] = d["H"] * d["m0"] / d["mid0"]
    d = d.sort_values("announce_date").reset_index(drop=True)
    d["im_bin"] = causal_bins(d["implied_move"].to_numpy(float), d["announce_date"], 3, MIN_PRIOR)
    d["cell"] = d["im_bin"] * 10 + pd.Categorical(d["tenor"], TENOR_LABELS).codes
    print(
        f"funnel: {len(hh)} hedged-hold ok, {int(d['announce_date'].notna().sum())} dated, "
        f"{int(d['permno'].notna().sum())} with permno, tercile assigned {int((d['im_bin'] >= 0).sum())}"
    )
    return d


def attach_similarity(d: pd.DataFrame) -> pd.DataFrame:
    """V1: percentile of the latest 10-K's Item 1A similarity among the trailing year's filings."""
    s = pd.read_parquet(SIM, columns=["cik", "info_date", SIM_COL]).dropna()
    s["info_date"] = pd.to_datetime(s["info_date"]).dt.normalize()
    s = s.sort_values("info_date")
    all_dates = s["info_date"].to_numpy()
    all_sims = s[SIM_COL].to_numpy(float)
    by_cik = {
        int(k): (g["info_date"].to_numpy(), g[SIM_COL].to_numpy(float)) for k, g in s.groupby("cik")
    }
    m = pd.read_parquet(CIKMAP, columns=["cik", "permno", "valid_from", "valid_to"])
    by_permno = {int(k): g for k, g in m.groupby("permno")}
    pct = np.full(len(d), np.nan)
    n_link = 0
    for i, (pn, t_in) in enumerate(
        zip(d["permno"].to_numpy(float), d["entry_date"].to_numpy(), strict=True)
    ):
        if not np.isfinite(pn) or int(pn) not in by_permno:
            continue
        lk = by_permno[int(pn)]
        lk = lk[(lk["valid_from"] <= t_in) & (lk["valid_to"] >= t_in)]
        if lk.empty or int(lk["cik"].iloc[0]) not in by_cik:
            continue
        n_link += 1
        dates, sims = by_cik[int(lk["cik"].iloc[0])]
        j = int(np.searchsorted(dates, t_in, side="left")) - 1
        if j < 0 or t_in - dates[j] > np.timedelta64(SIM_MAX_AGE, "D"):
            continue
        lo = int(
            np.searchsorted(all_dates, t_in - np.timedelta64(SIM_REF_WINDOW, "D"), side="left")
        )
        hi = int(np.searchsorted(all_dates, t_in, side="left"))
        if hi - lo < MIN_PRIOR:
            continue
        pct[i] = float((all_sims[lo:hi] <= sims[j]).mean())
    d = d.assign(sim_pct=pct)
    d["V1_def"] = np.isfinite(pct)
    d["V1"] = d["V1_def"] & (d["sim_pct"] >= SIM_PCT)
    print(f"funnel V1: CIK linked {n_link}, similarity percentile defined {int(d['V1_def'].sum())}")
    return d


def attach_carbonarc(d: pd.DataFrame) -> pd.DataFrame:
    """V2: lowest causal quintile of the absolute demand score."""
    ca = pd.read_parquet(CA).sort_values("eom")
    by = {
        int(k): (g["eom"].to_numpy(), g["ca_demand"].to_numpy(float))
        for k, g in ca.groupby("permno")
    }
    a = np.full(len(d), np.nan)
    stale = np.timedelta64(CA_MAX_STALE, "D")
    for i, (pn, t_in) in enumerate(
        zip(d["permno"].to_numpy(float), d["entry_date"].to_numpy(), strict=True)
    ):
        if not np.isfinite(pn) or int(pn) not in by:
            continue
        eom, val = by[int(pn)]
        j = int(np.searchsorted(eom, t_in, side="left")) - 1
        if j >= 0 and t_in - eom[j] <= stale:
            a[i] = abs(val[j])
    b = causal_bins(a, d["announce_date"], 5, MIN_PRIOR)
    d = d.assign(ca_abs=a, V2_def=b >= 0, V2=b == 0)
    print(f"funnel V2: score found {int(np.isfinite(a).sum())}, binned {int(d['V2_def'].sum())}")
    return d


def _filings(cik: int) -> pd.DataFrame | None:
    path = EDGAR / "submissions" / f"CIK{cik:010d}.json"
    if not path.exists():
        return None
    r = json.loads(path.read_text(encoding="utf-8"))["filings"]["recent"]
    f = pd.DataFrame({"form": r["form"], "items": r["items"], "acc": r["acceptanceDateTime"]})
    f["ts"] = pd.to_datetime(f["acc"], utc=True, errors="coerce")
    f = f.dropna(subset=["ts"])
    f["day"] = f["ts"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    return f.sort_values("ts").reset_index(drop=True)


def attach_edgar(d: pd.DataFrame) -> pd.DataFrame:
    """V3 pre-announced releases and V4 concurrent-filer regime from the cached filing arrays."""
    tick = json.loads((EDGAR / "company_tickers.json").read_text(encoding="utf-8"))
    cik_of = {v["ticker"].upper(): int(v["cik_str"]) for v in tick.values()}
    v3 = np.zeros(len(d), bool)
    v3_def = np.zeros(len(d), bool)
    v4 = np.zeros(len(d), bool)
    v4_def = np.zeros(len(d), bool)
    funnel = {"no_cik": 0, "no_file": 0, "short_history": 0}
    cache: dict[int, tuple | None] = {}
    for i, (t, ann) in enumerate(zip(d["ticker"], d["announce_date"], strict=True)):
        cik = cik_of.get(str(t).upper().replace("-", "."), cik_of.get(str(t).upper()))
        if cik is None or pd.isna(ann):
            funnel["no_cik"] += 1
            continue
        if cik not in cache:
            f = _filings(cik)
            if f is None:
                cache[cik] = None
            else:
                e = f[(f["form"] == "8-K") & f["items"].str.contains("2.02", regex=False)]
                q = f[f["form"].isin(["10-Q", "10-K"])]["ts"].to_numpy()
                conc = np.array(
                    [
                        bool(
                            (
                                (q >= ts - pd.Timedelta(hours=CONC_BEFORE_H))
                                & (q <= ts + pd.Timedelta(hours=CONC_AFTER_H))
                            ).any()
                        )
                        for ts in e["ts"]
                    ],
                    dtype=bool,
                )
                cache[cik] = (f["day"].min(), e["day"].to_numpy(), conc)
        item = cache[cik]
        if item is None:
            funnel["no_file"] += 1
            continue
        start, days, conc = item
        if start > ann - pd.Timedelta(days=EDGAR_MIN_HISTORY):
            funnel["short_history"] += 1
            continue
        ann64 = np.datetime64(ann)
        gap = (ann64 - days).astype("timedelta64[D]").astype(int)
        v3_def[i] = True
        v3[i] = bool(((gap >= PRE_WINDOW[0]) & (gap <= PRE_WINDOW[1])).any())
        prior = conc[gap >= CONC_LOOKBACK_MIN_DAYS]
        if prior.size >= CONC_N:
            v4_def[i] = True
            v4[i] = int(prior[-CONC_N:].sum()) >= CONC_K
    d = d.assign(V3=v3, V3_def=v3_def, V4=v4, V4_def=v4_def)
    print(
        f"funnel V3/V4: drops {funnel}, V3 defined {int(v3_def.sum())} treated {int(v3.sum())}, "
        f"V4 defined {int(v4_def.sum())} treated {int(v4.sum())}"
    )
    d["V5_def"] = d["V1_def"] & d["V3_def"] & d["V4_def"]
    d["V5"] = d["V5_def"] & (d["V1"] | d["V3"] | d["V4"])
    print(f"funnel V5: defined {int(d['V5_def'].sum())}, treated {int(d['V5'].sum())}")
    return d


# ── statistics ───────────────────────────────────────────────────────────────


def _delta(block: np.ndarray) -> float:
    """Treated-count-weighted mean of within-cell differences; columns y, treated, cell."""
    y, f, c = block[:, 0], block[:, 1] == 1.0, block[:, 2]
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= 2 and int((~f & m).sum()) >= 2:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def cell_matched_null(h: np.ndarray, treated: np.ndarray, cells: np.ndarray) -> float:
    """Percentile of the treated per-trade Sharpe among draws matched on count within cell."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(cells == u) for u in np.unique(cells)]
    counts = [int(treated[g].sum()) for g in groups]
    obs = per_trade_sharpe(h[treated])
    draws = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = np.concatenate(
            [rng.choice(g, k, replace=False) for g, k in zip(groups, counts, strict=True) if k]
        )
        draws[b] = per_trade_sharpe(h[idx])
    return float(100.0 * (draws < obs).mean())


def score_block(d: pd.DataFrame, trial: str, name: str) -> dict:
    lo, hi = BLOCKS[trial][name]
    b = d[d[f"{trial}_def"] & (d["im_bin"] >= 0) & d["announce_date"].dt.year.between(lo, hi)]
    tr = b[trial].to_numpy(bool)
    res: dict = {"block": name, "n_scored": len(b), "n_treated": int(tr.sum())}
    if tr.sum() < 10 or (~tr).sum() < 10:
        res["pass"] = False
        print(f"  {name} {lo}-{hi}: scored {len(b)}, treated {int(tr.sum())}: too few to score")
        return res
    cells = b["cell"].to_numpy(float)
    trio = np.column_stack([b["y"].to_numpy(float), tr.astype(float), cells])
    keys = b["announce_date"].to_numpy()
    res["delta"] = _delta(trio)
    res["delta_ci"] = cluster_bootstrap_ci(trio, keys, _delta, n_boot=N_BOOT, seed=SEED)
    res["null_pct"] = cell_matched_null(b["H"].to_numpy(float), tr, cells)
    th = date_clustered_ci(b.loc[tr, "H"], b.loc[tr, "announce_date"], np.mean)
    ts = date_clustered_ci(b.loc[tr, "H"], b.loc[tr, "announce_date"])
    res["treated_H"] = [th.point, th.low, th.high]
    res["treated_sharpe"] = [ts.point, ts.low, ts.high]
    res["all_H_mean"] = float(b["H"].mean())
    if name == "confirmation":
        res["pass"] = bool(res["delta"] > 0 and th.point > 0)
    else:
        res["pass"] = bool(res["delta_ci"][0] > 0 and res["null_pct"] >= NULL_PCT_PASS)
    print(
        f"  {name} {lo}-{hi}: scored {len(b)}, treated {int(tr.sum())}\n"
        f"      Delta (residual value per unit premium, within cell) {res['delta']:+.4f} "
        f"[{res['delta_ci'][0]:+.4f}, {res['delta_ci'][1]:+.4f}]; null percentile {res['null_pct']:.1f}\n"
        f"      treated H on m0: mean {th}; per-trade Sharpe {ts}; all scored mean {res['all_H_mean']:+.4f}"
    )
    return res


def score_trial(d: pd.DataFrame, trial: str) -> dict:
    print(f"\n{trial}:")
    out: dict = {"trial": trial, "blocks": [], "verdict": "PASS"}
    for name in BLOCKS[trial]:
        r = score_block(d, trial, name)
        out["blocks"].append(r)
        if not r["pass"]:
            out["verdict"] = f"FAIL at {name}"
            break
    print(f"  VERDICT {trial}: {out['verdict']}")
    return out


def dry(d: pd.DataFrame) -> None:
    """Counts only: no outcome is read."""
    yr = d["announce_date"].dt.year
    for trial, blocks in BLOCKS.items():
        ok = d[f"{trial}_def"] & (d["im_bin"] >= 0)
        line = ", ".join(
            f"{n} scored {int((ok & yr.between(*r)).sum())} treated {int((ok & d[trial] & yr.between(*r)).sum())}"
            for n, r in blocks.items()
        )
        print(f"{trial}: {line}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="print funnels and counts, no outcomes")
    args = ap.parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    d = attach_edgar(attach_carbonarc(attach_similarity(load_events())))
    OUT.mkdir(parents=True, exist_ok=True)
    if args.dry:
        dry(d)
        return
    keep = [c for c in d.columns if d[c].dtype != object or c in ("ticker", "tenor")]
    d[keep].to_parquet(OUT / "events.parquet", index=False)
    res = [score_trial(d, t) for t in BLOCKS]
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
