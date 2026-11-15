"""
lib.py
Shared loaders and scorers for the lane-3 (surface and flow) alpha hunt, 2026-11-13.

Outcome basis used throughout: the short ATM straddle sold at the 15:59 mid less the measured
entry cost, bought back the next session at the exit mid plus the measured exit cost (the ask
when no two-sided exit mid exists), less fees. ``r_meas`` is that P&L on margin ``m0``;
``y`` is the same P&L per unit of premium collected (size neutral). Cells are the causal
implied-move tercile crossed with the tenor bucket, so every comparison is tenor matched.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.hedged_hold import causal_bins  # noqa: E402
from earnings_iv_crush.research.protocol import per_trade_sharpe  # noqa: E402

HERE = Path(__file__).resolve().parent
HH = ROOT / "outputs/research/2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs/research/2026-10-20-hedged-hold/features.parquet"
TRIALS = HERE / "trials.csv"

COST_IN, COST_OUT = 0.012714, 0.030182  # measured 15:59 cost per side, fraction of the mark
FEE = 0.0065  # USD per share per leg
MIN_PRIOR = 200
N_BOOT = 5000
SEED = 0
TENOR_EDGES = [-1, 1, 4, 9, 100_000]
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]
TRIAL_COLS = [
    "trial_id",
    "hypothesis",
    "mechanism",
    "block",
    "n_scored",
    "n_treated",
    "effect",
    "ci_low",
    "ci_high",
    "t",
    "null_pct",
    "treated_rom",
    "pool_rom",
    "verdict",
]


def load_events() -> pd.DataFrame:
    """The scorable hedged-event rows with buy-back returns, tenor and causal cells."""
    hh = pd.concat(
        [
            pd.read_parquet(HH / "events.parquet"),
            pd.read_parquet(HH / "events_confirm_2025_26.parquet"),
        ],
        ignore_index=True,
    )
    n0 = len(hh)
    hh = hh[hh["status"] == "ok"].copy()
    f = pd.read_parquet(FEATURES).drop(columns=["exit_date"])
    for x in (hh, f):
        x["entry_date"] = pd.to_datetime(x["entry_date"]).dt.normalize()
    d = hh.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    d["announce_date"] = pd.to_datetime(d["announce_date"]).dt.normalize()
    d["exit_date"] = pd.to_datetime(d["exit_date"]).dt.normalize()
    d["expiry"] = pd.to_datetime(d["expiry"]).dt.normalize()
    d["im"] = d["mid0"] / d["front_fwd"]
    ok = np.isfinite(d["im"]) & (d["im"] > 0) & np.isfinite(d["abs_move"])
    x = d["exit_mid"].where(np.isfinite(d["exit_mid"]), d["exit_ask"])
    d["exit_px"] = x
    pnl = d["mid0"] * (1 - COST_IN) - x * (1 + COST_OUT) - 4 * FEE
    d["r_meas"] = pnl / d["m0"]
    d["y"] = pnl / d["mid0"]
    d["y_gross"] = 1 - x / d["mid0"]
    ok &= np.isfinite(d["r_meas"])
    print(
        f"funnel events: {n0} rows, {len(hh)} status ok, {int(ok.sum())} with implied move, "
        "move and return"
    )
    d = d[ok].copy()
    d["dte"] = (d["expiry"] - d["exit_date"]).dt.days
    d["tenor"] = pd.cut(d["dte"], TENOR_EDGES, labels=TENOR_LABELS).astype(str)
    tot = d["front_iv"] ** 2 * d["front_t"]
    d["jump_share"] = np.where(
        d["jsplit_valid"].astype(bool) & (tot > 0), d["jsplit_jump_var"] / tot, np.nan
    )
    d["iv_term_spread"] = d["front_iv"] - d["s1_iv"]
    d["entry_spread"] = (d["front_ask"] - d["front_bid"]) / d["front_mid"]
    d["log_im"] = np.log(d["im"])
    d["ylog"] = np.log(np.maximum(d["abs_move"], 0.001))
    d["mv_ratio"] = d["abs_move"] / d["im"]
    d["year"] = d["announce_date"].dt.year
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    d["im_bin"] = causal_bins(d["im"].to_numpy(float), d["announce_date"], 3, MIN_PRIOR)
    d["tenor_code"] = pd.Categorical(d["tenor"], TENOR_LABELS).codes
    d["cell"] = d["im_bin"] * 10 + d["tenor_code"]
    return d


# ── statistics ──


def _delta(y: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    """Treated-count-weighted mean of within-cell treated minus untreated differences."""
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= 2 and int((~f & m).sum()) >= 2:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def _boot(
    y: np.ndarray, f: np.ndarray, c: np.ndarray, keys: np.ndarray, n_boot: int = N_BOOT
) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    uk, inv = np.unique(keys, return_inverse=True)
    groups = [np.flatnonzero(inv == i) for i in range(len(uk))]
    out = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.concatenate([groups[i] for i in rng.integers(0, len(uk), len(uk))])
        out[b] = _delta(y[idx], f[idx], c[idx])
    return out


def cell_null(r: np.ndarray, treated: np.ndarray, cells: np.ndarray, n: int = N_BOOT) -> float:
    """Percentile of the treated per-trade Sharpe among random draws matched on count per cell."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(cells == u) for u in np.unique(cells)]
    counts = [int(treated[g].sum()) for g in groups]
    obs = per_trade_sharpe(r[treated])
    draws = np.empty(n)
    for b in range(n):
        idx = np.concatenate(
            [rng.choice(g, k, replace=False) for g, k in zip(groups, counts, strict=True) if k]
        )
        draws[b] = per_trade_sharpe(r[idx])
    return float(100.0 * (draws < obs).mean())


def score(
    d: pd.DataFrame,
    treated: pd.Series,
    defined: pd.Series,
    years: tuple[int, int],
    *,
    ycol: str = "y",
    rcol: str = "r_meas",
    cellcol: str = "cell",
    n_boot: int = N_BOOT,
    quiet: bool = False,
) -> dict:
    """Within-cell treated minus untreated on ``ycol``, date-clustered, with the matched null."""
    b = d[defined & (d["im_bin"] >= 0) & d["year"].between(*years) & np.isfinite(d[ycol])]
    tr = treated.loc[b.index].to_numpy(bool)
    res: dict = {"block": f"{years[0]}-{years[1]}", "n_scored": len(b), "n_treated": int(tr.sum())}
    if tr.sum() < 30 or (~tr).sum() < 30:
        if not quiet:
            print(f"  {res['block']}: scored {len(b)}, treated {int(tr.sum())}: too thin to score")
        return res
    y, c = b[ycol].to_numpy(float), b[cellcol].to_numpy(float)
    keys = b["announce_date"].to_numpy()
    eff = _delta(y, tr, c)
    draws = _boot(y, tr, c, keys, n_boot)
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    se = np.nanstd(draws, ddof=1)
    r = b[rcol].to_numpy(float)
    res.update(
        effect=eff,
        ci_low=lo,
        ci_high=hi,
        t=eff / se if se > 0 else np.nan,
        null_pct=cell_null(r, tr, c, n_boot),
        treated_rom=float(r[tr].mean()),
        pool_rom=float(r.mean()),
        treated_sharpe=per_trade_sharpe(r[tr]),
        pool_sharpe=per_trade_sharpe(r),
    )
    if not quiet:
        print(
            f"  {res['block']}: N {len(b)}, treated {int(tr.sum())}; Delta {ycol} within cell "
            f"{eff:+.4f} [{lo:+.4f}, {hi:+.4f}] t {res['t']:+.2f}; null pct {res['null_pct']:.1f}; "
            f"treated RoM {res['treated_rom']:+.4f} (Sharpe {res['treated_sharpe']:+.3f}) vs pool "
            f"{res['pool_rom']:+.4f} (Sharpe {res['pool_sharpe']:+.3f})"
        )
    return res


def top_bin(
    d: pd.DataFrame, col: str, n_bins: int = 3, sign: int = 1
) -> tuple[pd.Series, pd.Series]:
    """Causal top bin of ``sign * col`` (strictly earlier events set the cuts)."""
    b = causal_bins((sign * d[col]).to_numpy(float), d["announce_date"], n_bins, MIN_PRIOR)
    return pd.Series(b == n_bins - 1, index=d.index), pd.Series(b >= 0, index=d.index)


def bins_table(
    d: pd.DataFrame, col: str, years: tuple[int, int], n_bins: int = 3, by: str | None = None
) -> pd.DataFrame:
    """Disjoint causal bins of ``col``: y demeaned within cell, RoM, premium, tenor, move ratio."""
    b = causal_bins(d[col].to_numpy(float), d["announce_date"], n_bins, MIN_PRIOR)
    x = d.assign(fbin=b)
    x = x[(x["fbin"] >= 0) & (x["im_bin"] >= 0) & x["year"].between(*years)].copy()
    x["y_dm"] = x["y"] - x.groupby("cell")["y"].transform("mean")
    keys = ["fbin"] if by is None else [by, "fbin"]
    return (
        x.groupby(keys)
        .agg(
            n=("y", "size"),
            y_dm=("y_dm", "mean"),
            y=("y", "mean"),
            rom=("r_meas", "mean"),
            im=("im", "median"),
            dte=("dte", "median"),
            mv_ratio=("mv_ratio", "median"),
        )
        .round(4)
    )


def log_trial(trial_id: int, hypothesis: str, mechanism: str, res: dict, verdict: str) -> None:
    """Append one scored variant to trials.csv."""
    new = not TRIALS.exists()
    nan = float("nan")
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(TRIAL_COLS)
        w.writerow(
            [
                trial_id,
                hypothesis,
                mechanism,
                res.get("block"),
                res.get("n_scored"),
                res.get("n_treated"),
                f"{res.get('effect', nan):+.5f}",
                f"{res.get('ci_low', nan):+.5f}",
                f"{res.get('ci_high', nan):+.5f}",
                f"{res.get('t', nan):+.2f}",
                f"{res.get('null_pct', nan):.1f}",
                f"{res.get('treated_rom', nan):+.5f}",
                f"{res.get('pool_rom', nan):+.5f}",
                verdict,
            ]
        )
