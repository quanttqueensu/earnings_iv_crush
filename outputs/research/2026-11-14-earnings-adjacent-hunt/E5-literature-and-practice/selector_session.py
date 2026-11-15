"""
selector_session.py
Report session (after the close against before the open) as an entry selector on the hedged
hold, scored on residual value under HEDGED_NET (lane E5, trial 2,805).

Treated events are those with a timed calendar label of amc; untreated are bmo. The primary is
the mean causal residual value of the amc events against a matched random null over all
labelled events in the block, with a date-clustered interval. A driver check splits the
within-cell amc minus bmo contrast into the event night (buy-back), the continuation to expiry,
post-event realised variance and entry balance. Declarations are in ``diagnosis.log``; the
held-out block runs only after ``freeze_session.md`` exists and its recorded hashes match.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/selector_session.py --block discovery
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/selector_session.py --block heldout

References
----------
Lyle, M. R., Rigsby, C., Stephan, A. and Yohn, T. L. (2018). The speed of the market reaction
to pre-open versus post-close earnings announcements. Working paper, Kellogg School of
Management.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import (  # noqa: E402
    block_is_clean,
    date_clustered_ci,
    matched_random_null,
)

_spec = importlib.util.spec_from_file_location(
    "laneJ_lib", ROOT / "outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/lib.py"
)
lj = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(lj)

FREEZE = HERE / "freeze_session.md"
NETTING = ROOT / "outputs/research/2026-11-13-alpha-hunt-2/netting_reconciliation/netting_by_event.parquet"
EVENTS_FULL = ROOT / "outputs/research/ml_zoo/events_full.parquet"
CALENDARS = (
    "calendar_broad_2013_2024",
    "calendar_wrds_2013_2018",
    "calendar_wrds",
    "calendar_postea",
)
DSF = ROOT / "data/processed/wrds/raw/crsp_a_stock.dsf.a336cb25197b.parquet"


# ── configuration ──


@dataclass(frozen=True)
class SessionConfig:
    """Every number the scorer uses, with its reason."""

    blocks: tuple[tuple[str, int, int], ...] = (("discovery", 2013, 2018), ("heldout", 2019, 2024))
    min_known: int = 200  # resolved events before any causal cell mean is used
    min_cell_known: int = 20  # resolved events in a cell before its mean is used
    winsor_q: tuple[float, float] = (0.01, 0.99)  # causal residual tails (y reaches -13 premiums)
    null_pct_pass: float = 95.0
    trading_days: int = 252  # converts annualised front IV to a per-session variance


CFG = SessionConfig()


# ── data ──


def session_labels(d: pd.DataFrame) -> tuple[pd.Series, dict[str, int]]:
    """'amc', 'bmo' or NaN per event: timed calendars only, agreeing with is_amc."""
    ef = pd.read_parquet(EVENTS_FULL, columns=["ticker", "entry_date", "announce_date", "is_amc"])
    for c in ("entry_date", "announce_date"):
        ef[c] = pd.to_datetime(ef[c]).dt.normalize()
    key = d[["ticker", "entry_date"]].merge(ef, on=["ticker", "entry_date"], how="left")
    if key["is_amc"].isna().any():
        raise ValueError(f"{int(key['is_amc'].isna().sum())} events have no is_amc")
    rows = []
    for name in CALENDARS:
        c = pd.read_parquet(ROOT / "outputs" / "research" / f"{name}.parquet")
        c = c[c["session_source"] == "ibes_time"][["ticker", "announce_date", "session"]]
        c["announce_date"] = pd.to_datetime(c["announce_date"]).dt.normalize()
        rows.append(c)
    cal = pd.concat(rows).drop_duplicates()
    agg = cal.groupby(["ticker", "announce_date"])["session"].agg(lambda s: "|".join(sorted(set(s))))
    lab = key.set_index(["ticker", "announce_date"]).index.map(agg.to_dict().get)
    lab = pd.Series(lab, index=d.index, dtype=object)
    is_amc = key["is_amc"].astype(int).to_numpy()
    out = pd.Series(np.nan, index=d.index, dtype=object)
    ok_amc = (lab == "amc").to_numpy() & (is_amc == 1)
    ok_bmo = (lab == "bmo").to_numpy() & (is_amc == 0)
    out[ok_amc] = "amc"
    out[ok_bmo] = "bmo"
    funnel = {
        "unmatched": int(lab.isna().sum()),
        "dmh": int(lab.fillna("").str.contains("dmh").sum()),
        "contradicted_or_mixed": int(lab.fillna("").str.contains(r"\|").sum()),
        "disagrees_with_is_amc": int(
            (((lab == "amc").to_numpy() & (is_amc == 0)) | ((lab == "bmo").to_numpy() & (is_amc == 1))).sum()
        ),
        "labelled_amc": int(ok_amc.sum()),
        "labelled_bmo": int(ok_bmo.sum()),
    }
    return out, funnel


def load() -> tuple[pd.DataFrame, dict[str, int]]:
    d = lj.load()
    funnel: dict[str, int] = {"lane5_events": len(d)}
    net = pd.read_parquet(NETTING, columns=["ticker", "entry_date", "H_net"])
    net["entry_date"] = pd.to_datetime(net["entry_date"]).dt.normalize()
    d = d.merge(net, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    d["y_net"] = d["H_net"] * d["m0"] / d["mid0"]
    funnel["with_H_net"] = int(d["y_net"].notna().sum())
    d["session"], f2 = session_labels(d)
    funnel.update(f2)
    d["y_post"] = np.where(d["b_defined"].astype(bool), d["y_net"] - d["yb"], np.nan)
    d["prem_over_m0"] = d["mid0"] / d["m0"]
    return d, funnel


def causal_residual(d: pd.DataFrame, col: str) -> pd.Series:
    """``col`` less its causal cell mean, winsorised at causal cut-offs; NaN where undefined."""
    out = pd.Series(np.nan, index=d.index)
    y = d[col].to_numpy(float)
    cell = d["cell"].to_numpy(float)
    exp_t = d["expiry"].to_numpy("datetime64[ns]")
    for t, idx in d.groupby("entry_date").indices.items():
        known = (exp_t < np.datetime64(t)) & np.isfinite(y) & (cell >= 0)
        if known.sum() < CFG.min_known:
            continue
        k = np.flatnonzero(known)
        s = pd.Series(y[k]).groupby(cell[k])
        mean, cnt = s.mean(), s.size()
        cm = pd.Series(cell[k]).map(mean).to_numpy()
        lo, hi = np.quantile(y[k] - cm, CFG.winsor_q)
        for i in idx:
            c = cell[i]
            if c >= 0 and np.isfinite(y[i]) and c in cnt.index and cnt[c] >= CFG.min_cell_known:
                out.iloc[i] = float(np.clip(y[i] - mean[c], lo, hi))
    return out


def post_event_rv(d: pd.DataFrame) -> pd.DataFrame:
    """Mean squared daily CRSP log total return per session after the exit session to expiry.

    Amendment 01 (before any freeze): the close cache starts 2018-11, so the driver check uses
    the cached CRSP daily file with ``ret`` (split and dividend adjusted), which covers every
    event of both blocks by permno.
    """
    dsf = pd.read_parquet(DSF, columns=["permno", "date", "ret"]).dropna()
    dsf["date"] = pd.to_datetime(dsf["date"]).dt.normalize()
    res = pd.DataFrame(np.nan, index=d.index, columns=["n_post", "rv_post"])
    by = {p: g.set_index("date")["ret"].sort_index() for p, g in dsf.groupby("permno")}
    for i, r in d.iterrows():
        s = by.get(r["permno"])
        if s is None:
            continue
        seg = s[(s.index > r["exit_date"]) & (s.index <= r["expiry"])]
        res.loc[i, "n_post"] = len(seg)
        if len(seg):
            res.loc[i, "rv_post"] = float(np.mean(np.log1p(seg.to_numpy(float)) ** 2))
    return res


# ── scoring ──


def _contrast(b: pd.DataFrame, col: str, f: np.ndarray) -> dict[str, float]:
    ok = np.isfinite(b[col].to_numpy(float))
    y, ff, c = b[col].to_numpy(float)[ok], f[ok], b["cell"].to_numpy(float)[ok]
    keys = b["announce_date"].to_numpy()[ok]
    eff = lj._delta(y, ff, c)
    draws = lj._boot_delta(y, ff, c, keys)
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    return {"amc_minus_bmo": eff, "low": float(lo), "high": float(hi), "n": int(ok.sum()),
            "n_amc": int(ff.sum())}


def score(d: pd.DataFrame, block: str) -> dict[str, object]:
    name, y0, y1 = next(b for b in CFG.blocks if b[0] == block)
    sel = d["year"].between(y0, y1) & d["session"].notna() & d["r"].notna()
    b = d[sel].copy()
    f = (b["session"] == "amc").to_numpy()
    res: dict[str, object] = {"block": f"{name} {y0}-{y1}", "N": int(len(b)), "n_amc": int(f.sum()),
                              "n_bmo": int((~f).sum()), "n_names_amc": int(b.loc[f, "ticker"].nunique())}
    iv = date_clustered_ci(b.loc[f, "r"], b.loc[f, "announce_date"], np.mean)
    nul = matched_random_null(b["r"].to_numpy(float), f, np.mean)
    res["primary_amc_mean_residual"] = {"point": iv.point, "low": iv.low, "high": iv.high,
                                        "n": iv.n, "clusters": iv.clusters}
    res["pool_mean_residual"] = float(b["r"].mean())
    res["matched_null_pct"] = nul.percentile
    res["matched_null_median"] = float(np.nanmedian(nul.null))
    res["pass"] = bool(iv.low > 0 and nul.percentile >= CFG.null_pct_pass)
    bmo = date_clustered_ci(b.loc[~f, "r"], b.loc[~f, "announce_date"], np.mean)
    res["bmo_mean_residual"] = {"point": bmo.point, "low": bmo.low, "high": bmo.high, "n": bmo.n}
    lvl = date_clustered_ci(b.loc[f, "H_net"], b.loc[f, "announce_date"], np.mean)
    res["amc_level_H_net_m0"] = {"point": lvl.point, "low": lvl.low, "high": lvl.high}
    res["pool_level_H_net_m0"] = float(b["H_net"].mean())
    y = b["y_net"].to_numpy(float)
    res["secondary_within_cell_y_net"] = _contrast(b, "y_net", f)
    res["secondary_cell_null_pct"] = lj._cell_null(y, f, b["cell"].to_numpy(float))
    # driver check
    b["rv_ratio"] = b["rv_post"] / (b["front_iv"] ** 2 / CFG.trading_days)
    lo_r, hi_r = b["rv_ratio"].quantile(list(CFG.winsor_q)).to_numpy()
    b["rv_ratio_w"] = b["rv_ratio"].clip(lo_r, hi_r)
    drv = {}
    for col in ("yb", "y_post", "rv_ratio_w", "n_post", "implied_move", "half_spread",
                "prem_over_m0"):
        drv[col] = _contrast(b, col, f)
    drv["mean_n_post_amc"] = float(b.loc[f, "n_post"].mean())
    drv["mean_n_post_bmo"] = float(b.loc[~f, "n_post"].mean())
    drv["rv_defined"] = int(b["rv_post"].notna().sum())
    res["driver"] = drv
    return res


def _verify_freeze() -> None:
    if not FREEZE.exists():
        raise SystemExit("held-out refused: freeze note missing")
    text = FREEZE.read_text(encoding="utf-8")
    m = re.search(r"selector_session\.py sha256: ([0-9a-f]{64})", text)
    if not m or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != m.group(1):
        raise SystemExit("held-out refused: scorer hash does not match the freeze note")
    body, _, tail = text.rpartition("note sha256: ")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != tail.strip()[:64]:
        raise SystemExit("held-out refused: freeze note hash does not match")


def main() -> None:
    ap = argparse.ArgumentParser(description="Report-session selector on the hedged hold (2,805)")
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    period = "2013-18" if a.block == "discovery" else "2019-24"
    if a.block == "heldout":
        _verify_freeze()
    clean, clash = block_is_clean(
        ROOT / "research" / "ledger" / "blocks.csv", panel="hedged_event_hold", period=period,
        outcome_family="residual_value", feature_family="report_session",
    )
    print(f"block_is_clean {period}: {clean}; clashes {len(clash)}")
    d, funnel = load()
    d["r"] = causal_residual(d, "y_net")
    funnel["residual_defined"] = int(d["r"].notna().sum())
    rv = post_event_rv(d)
    d = d.join(rv)
    print("funnel:", json.dumps(funnel))
    res = score(d, a.block)
    res["funnel"] = funnel
    res["block_is_clean"] = clean
    (HERE / f"session_{a.block}.json").write_text(json.dumps(res, indent=2, default=float),
                                                  encoding="utf-8")
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
