"""lib.py: shared loading and scoring for lane L3 (selection and other markets).

Every selector in this lane is scored the same way, on the corrected panel
``L1-corrections/base_corrected.parquet``:

- the outcome pair is ``residual_value`` (option value left at the reaction-session 15:59 marks,
  net of intrinsic, seller-signed, fraction of m0) and ``H_corr`` (the declared headline hedged
  hold, fraction of m0), side by side;
- the statistic is selected minus unselected mean, with a 95% percentile interval resampling whole
  reaction-session dates (``exit_date``);
- the participation-matched random null (``protocol.matched_random_null``, statistic the mean) is
  run on both outcomes;
- features enter only through ``hedged_hold.causal_bins`` (breakpoints from strictly earlier
  dates).

Nothing here reads a held-out block by itself; callers pass the block.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    N_BOOT,
    SEED,
    block_is_clean,
    date_clustered_ci,
    log_block_view,
    matched_random_null,
)

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "L1-corrections" / "base_corrected.parquet"
PANEL = (
    ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt-2" / "laneE-walk-forward-model"
    / "panel.parquet"
)
LEDGER = ROOT / "research" / "ledger" / "blocks.csv"
LANE_VIEWS = HERE / "blocks_viewed.csv"


# ── lane configuration ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class L3Config:
    """Lane-local constants (the package config is not edited by this lane).

    Attributes
    ----------
    blocks : dict
        Entry-year blocks. ``2013-18`` discovery and ``2019-24`` held-out, as the programme brief
        fixes; ``2025-26`` exploratory only.
    min_prior : int
        Events with an earlier date needed before a causal breakpoint is formed. ``200``: the
        pairwise-tercile study's value, so bins are comparable across the record.
    null_pct_pass : float
        Matched-null percentile a selector must reach. ``95``: one-sided 5%, the project's bar.
    """

    blocks: tuple[tuple[str, int, int], ...] = (
        ("2013-18", 2013, 2018),
        ("2019-24", 2019, 2024),
        ("2025-26", 2025, 2026),
    )
    min_prior: int = 200
    null_pct_pass: float = 95.0


CFG = L3Config()


# ── loading ──────────────────────────────────────────────────────────────────


def load_base(panel_cols: list[str] | None = None) -> pd.DataFrame:
    """The corrected panel, optionally joined one-to-one to 15:59 features of the lane E panel.

    Raises
    ------
    ValueError
        If the feature join is not one-to-one.
    """
    b = pd.read_parquet(BASE)
    if panel_cols:
        p = pd.read_parquet(PANEL, columns=["ticker", "entry_date", *panel_cols])
        n0 = len(b)
        b = b.merge(p, on=["ticker", "entry_date"], how="left", validate="one_to_one")
        if len(b) != n0:
            raise ValueError("feature join changed the row count")
    return b


def block_of(year: pd.Series) -> pd.Series:
    """Block label for each entry year."""
    out = pd.Series("", index=year.index, dtype=object)
    for name, y0, y1 in CFG.blocks:
        out[year.between(y0, y1)] = name
    return out


# ── scoring ──────────────────────────────────────────────────────────────────


def _diff_of_means(block: np.ndarray) -> float:
    v, f = block[:, 0], block[:, 1] == 1.0
    if f.all() or not f.any():
        return float("nan")
    return float(v[f].mean() - v[~f].mean())


def score_mask(
    d: pd.DataFrame,
    selected: np.ndarray,
    *,
    outcomes: tuple[str, ...] = ("residual_value", "H_corr"),
    date_col: str = "exit_date",
) -> dict[str, Any]:
    """Selected minus unselected on each outcome, its date-clustered interval and matched null.

    ``d`` is the scored population of one block (every row eligible); ``selected`` its boolean
    mask. Outcomes are fractions of m0; the returned figures are in % of m0 per trade.
    Rows with a NaN outcome are dropped for that outcome only, and the count is returned.
    """
    sel = np.asarray(selected, dtype=bool)
    if sel.shape[0] != len(d):
        raise ValueError("mask length differs from the population")
    out: dict[str, Any] = {"N": int(len(d)), "n_sel": int(sel.sum())}
    keys_all = pd.to_datetime(d[date_col]).dt.normalize().to_numpy()
    for o in outcomes:
        v = d[o].to_numpy(float)
        ok = np.isfinite(v)
        out[f"{o}_n_dropped_nan"] = int((~ok).sum())
        vv, ss, kk = v[ok], sel[ok], keys_all[ok]
        if ss.sum() < 2 or (~ss).sum() < 2:
            out[f"{o}_diff"] = out[f"{o}_lo"] = out[f"{o}_hi"] = out[f"{o}_null_pct"] = np.nan
            continue
        pair = np.column_stack([vv, ss.astype(float)])
        lo, hi = cluster_bootstrap_ci(pair, kk, _diff_of_means, n_boot=N_BOOT, seed=SEED)
        out[f"{o}_diff"] = 100 * _diff_of_means(pair)
        out[f"{o}_lo"], out[f"{o}_hi"] = 100 * lo, 100 * hi
        out[f"{o}_null_pct"] = matched_random_null(vv, ss, stat=np.mean).percentile
        ci = date_clustered_ci(vv[ss], kk[ss], np.mean)
        out[f"{o}_sel_mean"], out[f"{o}_sel_lo"], out[f"{o}_sel_hi"] = (
            100 * ci.point,
            100 * ci.low,
            100 * ci.high,
        )
        out[f"{o}_clusters"] = int(len(np.unique(kk)))
    return out


def fmt(r: dict[str, Any], o: str) -> str:
    """One-line summary of an outcome's selected-minus-unselected figures."""
    return (
        f"{o}: sel-unsel {r[f'{o}_diff']:+.3f} [{r[f'{o}_lo']:+.3f}, {r[f'{o}_hi']:+.3f}] % m0, "
        f"null pct {r[f'{o}_null_pct']:.1f}; selected book {r.get(f'{o}_sel_mean', np.nan):+.3f} "
        f"[{r.get(f'{o}_sel_lo', np.nan):+.3f}, {r.get(f'{o}_sel_hi', np.nan):+.3f}]"
    )


def passes(r: dict[str, Any]) -> bool:
    """The lane's declared pass rule: residual value lifts, with the null and the interval."""
    return bool(
        r["residual_value_lo"] > 0
        and r["residual_value_null_pct"] >= CFG.null_pct_pass
        and r["H_corr_diff"] > 0
    )


# ── block ledger ─────────────────────────────────────────────────────────────


def check_clean(period: str, outcome_family: str, feature_family: str) -> str:
    """Clean status on the project ledger under both panel names this panel's events carry."""
    msgs = []
    for panel in ("hedged_event_hold", "base_corrected"):
        clean, hits = block_is_clean(
            LEDGER,
            panel=panel,
            period=period,
            outcome_family=outcome_family,
            feature_family=feature_family,
        )
        msgs.append(f"{panel} {period} {outcome_family}/{feature_family}: clean={clean}"
                    f" ({len(hits)} clashes)")
    return "; ".join(msgs)


def log_view(period: str, outcome_family: str, feature_family: str, who: str, kind: str) -> None:
    """Record one view of a block in the lane's ``blocks_viewed.csv``."""
    log_block_view(
        LANE_VIEWS,
        panel="base_corrected",
        period=period,
        outcome_family=outcome_family,
        feature_family=feature_family,
        viewed_by=who,
        kind=kind,
    )
