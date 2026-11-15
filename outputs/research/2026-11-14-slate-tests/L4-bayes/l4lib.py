"""
l4lib.py
Lane L4 data assembly and run helpers for the sequential Bayesian model: joins L1's corrected
panel (outcomes, components, flags) to the lane E panel's 15:59 features, builds the declared
design causally, and runs the model and its no-feature baseline on identical event sets.

Basis: ``y`` is ``H_corr`` (or ``residual_value``) per trade in % of m0 (the stored fractions
times ``pct_per_unit``), net at the touch. Rows with ``h_status`` other than ``ok`` carry no
outcome: they are predicted but never absorbed or scored.

Usage
-----
    import l4lib; d = l4lib.load(); X, usable = l4lib.design(d)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.config import OnlineBayesConfig  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402

BASE = HERE.parent / "L1-corrections" / "base_corrected.parquet"
BASE_SHA256 = "7d8022f84214afa1c05b8a17d9d7f5abf6a208e57044574a2d591b50288fdd93"
PANEL = ROOT / "outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/panel.parquet"
LEDGER = ROOT / "research" / "ledger" / "blocks.csv"
BLOCKS_VIEWED = HERE / "blocks_viewed.csv"
KEYS = ["ticker", "entry_date"]
TARGETS = {"H_corr": "H_corr", "residual_value": "residual_value"}
COMPONENTS = [
    "c_premium",
    "c_settlement",
    "c_hedge",
    "c_equity_cost",
    "c_fees",
    "c_disposal",
    "c_financing",
]
FLAGS = ["exdiv_in_hold", "special_div", "spot_src", "lnFK", "h_status", "call_assigned"]
BLOCK_ORDER = ["2013-18", "2019-24", "2025-26"]
COEFS = ["intercept", *ob.FEATURES]


def load() -> pd.DataFrame:
    """The 9,350 base events with outcomes, components, flags, features and timestamps."""
    got = ob_sha(BASE)
    if got != BASE_SHA256:
        raise ValueError(f"base_corrected.parquet changed: {got[:12]} vs {BASE_SHA256[:12]}")
    b = pd.read_parquet(BASE)
    p = pd.read_parquet(PANEL, columns=KEYS + ["announce_date"] + list(ob.RAW_COLUMNS[1:]))
    d = b.merge(p, on=KEYS, how="left", validate="one_to_one", indicator=True, suffixes=("", "_p"))
    lost = int((d["_merge"] != "both").sum())
    if lost:
        raise ValueError(f"{lost} corrected events have no feature row")
    if not np.allclose(d["m0"], d["m0_p"]):
        raise ValueError("m0 disagrees between the corrected panel and the feature panel")
    d = d.drop(columns=["_merge", "m0_p"])
    for c in ("entry_date", "exit_date", "expiry", "announce_date"):
        d[c] = pd.to_datetime(d[c]).dt.normalize()
    d = d.sort_values(KEYS, kind="stable").reset_index(drop=True)
    ok = d["h_status"] == "ok"
    print(
        f"[load] {len(d)} events; h_status ok {int(ok.sum())}, other "
        f"{dict(d.loc[~ok, 'h_status'].value_counts())} (src "
        f"{dict(d.loc[~ok, 'src'].value_counts())}); of those, H_corr NaN "
        f"{int(d.loc[~ok, 'H_corr'].isna().sum())}; H_corr NaN on ok rows "
        f"{int(d.loc[ok, 'H_corr'].isna().sum())}; residual_value NaN "
        f"{int(d['residual_value'].isna().sum())}"
    )
    print(f"[load] blocks {dict(d['block'].value_counts().reindex(BLOCK_ORDER))}")
    return d


def ob_sha(path: Path) -> str:
    from earnings_iv_crush.research.protocol import sha256_file

    return sha256_file(path)


def target(d: pd.DataFrame, name: str, cfg: OnlineBayesConfig) -> np.ndarray:
    """The outcome in % of m0, NaN where the row is not ``h_status == ok``."""
    y = d[TARGETS[name]].to_numpy(float) * cfg.pct_per_unit
    return np.where(d["h_status"].to_numpy() == "ok", y, np.nan)


def design(d: pd.DataFrame, cfg: OnlineBayesConfig) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Standardised design (intercept first), the shared usable mask, and the raw features.

    A row is usable when every standardised feature and the premium-share weight are defined,
    so every configuration, with or without features, predicts and absorbs the same events.
    """
    raw = ob.build_features(d, cfg)
    z, _ = ob.causal_standardise(raw[list(ob.FEATURES)], d["entry_date"], cfg.min_prior_events)
    X = np.column_stack([np.ones(len(d)), z.to_numpy(float)])
    v_ps = ob.causal_variance_weight(
        raw["premium_share"].to_numpy(), d["entry_date"], "premium_share", cfg.min_prior_events
    )
    usable = np.isfinite(X).all(axis=1) & np.isfinite(v_ps)
    print(f"[design] usable (features and weight defined) {int(usable.sum())} of {len(d)}")
    return X, usable, raw


def frame(
    d: pd.DataFrame, y: np.ndarray, raw: pd.DataFrame, usable: np.ndarray, cfg: OnlineBayesConfig
) -> pd.DataFrame:
    """The run frame for one configuration (its variance weight), NaN weight where unusable."""
    v = ob.causal_variance_weight(
        raw["premium_share"].to_numpy(), d["entry_date"], cfg.variance_weight, cfg.min_prior_events
    )
    return pd.DataFrame(
        {
            "entry_date": d["entry_date"],
            "settle_date": d["expiry"],
            "name": d["ticker"],
            "cluster": d["announce_date"],
            "y": y,
            "v": np.where(usable, v, np.nan),
        },
        index=d.index,
    )


def run_pair(
    d: pd.DataFrame,
    y: np.ndarray,
    X: np.ndarray,
    raw: pd.DataFrame,
    usable: np.ndarray,
    model_cfg: OnlineBayesConfig,
    base_cfg: OnlineBayesConfig,
    quiet: bool = True,
) -> tuple[ob.OnlineRun, ob.OnlineRun]:
    """The feature model and the intercept-and-name baseline on the same events."""
    m = ob.run_online(
        frame(d, y, raw, usable, model_cfg), X, model_cfg, coef_names=COEFS, quiet=quiet
    )
    b = ob.run_online(
        frame(d, y, raw, usable, base_cfg), X[:, :1], base_cfg, coef_names=COEFS[:1], quiet=quiet
    )
    return m, b
