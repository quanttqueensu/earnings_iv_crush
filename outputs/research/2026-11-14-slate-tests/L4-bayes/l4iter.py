"""
l4iter.py
Lane L4 iteration-round helpers: the point-in-time industry level, the design for any feature
set, one run of a configuration, and its rolling-origin discovery score.

Rolling origin. The model runs sequentially from the first 2013 event; each discovery year
2015 to 2018 is scored on the predictions made for its events by the posterior holding every
outcome that settled before each entry date. One pass therefore gives four rolling origins.
2013-14 is burn-in (standardisation needs 200 earlier events, scoring 200 settled trades).

Industry. Two-digit SIC from the CRSP name history cached in ``data/processed/wrds/raw`` (the
shard carrying ``siccd``; nothing is fetched): the record whose ``[namedt, nameendt]`` holds the
entry date, else the last record before it. 2025-26 rows carry no permno, so the ticker's
latest 2013-24 permno is used, else the latest CRSP record of that ticker; its SIC is then as of
2024-12-31 at the latest, which is strictly before every 2025-26 entry. SIC code 0 (unassigned)
and an unmapped name are no industry: the level adds its prior variance and nothing else.

Usage
-----
    import l4iter; d = l4iter.load_all(); D = l4iter.Design(d)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import l4lib  # noqa: E402

from earnings_iv_crush.config import OnlineBayesConfig  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402

RAW = ROOT / "data" / "processed" / "wrds" / "raw"
SIC_SHARDS = ("crsp_a_stock.dsenames.a5818c8cd21b.parquet",)
DISCOVERY_YEARS = (2015, 2016, 2017, 2018)
GROUP_LEVELS = ("none", "sic2", "sic_div")
# SIC divisions (US OSHA SIC manual): lower bound of each two-digit range.
SIC_DIVISIONS = ((1, "A"), (10, "B"), (15, "C"), (20, "D"), (40, "E"), (50, "F"), (52, "G"),
                 (60, "H"), (70, "I"), (91, "J"), (100, "Z"))  # fmt: skip


def load_all() -> pd.DataFrame:
    """``l4lib.load`` plus the wide feature set's lane E columns, joined one to one."""
    d = l4lib.load()
    cols = [c for c in ob.RAW_COLUMNS_WIDE if c not in d.columns]
    p = pd.read_parquet(l4lib.PANEL, columns=l4lib.KEYS + cols)
    p["entry_date"] = pd.to_datetime(p["entry_date"]).dt.normalize()
    out = d.merge(p, on=l4lib.KEYS, how="left", validate="one_to_one", indicator=True)
    if (out["_merge"] != "both").any():
        raise ValueError("wide feature join lost rows")
    return out.drop(columns="_merge")


# ── industry ─────────────────────────────────────────────────────────────────


def _sic_table() -> pd.DataFrame:
    parts = [
        pd.read_parquet(RAW / f, columns=["permno", "ticker", "namedt", "nameendt", "siccd"])
        for f in SIC_SHARDS
    ]
    nm = pd.concat(parts).drop_duplicates()
    nm["namedt"] = pd.to_datetime(nm["namedt"])
    nm["nameendt"] = pd.to_datetime(nm["nameendt"])
    nm["permno"] = nm["permno"].astype("int64")
    return nm.sort_values(["permno", "namedt"]).reset_index(drop=True)


def _division(sic2: int) -> str:
    lab = "Z"
    for lo, name in SIC_DIVISIONS:
        if sic2 >= lo:
            lab = name
    return lab


def industry(d: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time ``sic2`` and ``sic_div`` labels per event (None where unknown)."""
    nm = _sic_table()
    perm = d["permno"].copy()
    latest = d.loc[d["permno"].notna()].sort_values("entry_date").groupby("ticker")["permno"].last()
    fill = perm.isna()
    perm[fill] = d.loc[fill, "ticker"].map(latest)
    by_tk = nm.sort_values("nameendt").groupby("ticker")["permno"].last()
    fill2 = perm.isna()
    perm[fill2] = d.loc[fill2, "ticker"].map(by_tk)
    sic = np.full(len(d), np.nan)
    groups = {k: g for k, g in nm.groupby("permno")}
    for i, (p, t) in enumerate(zip(perm.to_numpy(), d["entry_date"].to_numpy(), strict=True)):
        if not np.isfinite(p) or int(p) not in groups:
            continue
        g = groups[int(p)]
        prior = g[g["namedt"] <= t]
        if prior.empty:
            continue
        sic[i] = float(prior.iloc[-1]["siccd"])
    s2 = np.where(np.isfinite(sic) & (sic > 0), np.floor(sic / 100), np.nan)
    out = pd.DataFrame(
        {
            "sic2": [None if not np.isfinite(x) else f"s{int(x):02d}" for x in s2],
            "sic_div": [None if not np.isfinite(x) else _division(int(x)) for x in s2],
        },
        index=d.index,
    )
    print(
        f"[industry] permno direct {int(d['permno'].notna().sum())}, via ticker's earlier "
        f"permno {int((fill & ~fill2).sum())}, via CRSP ticker {int((fill2 & perm.notna()).sum())}"
        f", unmapped {int(perm.isna().sum())}; SIC assigned {int(np.isfinite(s2).sum())} of "
        f"{len(d)}; sic2 groups {out['sic2'].nunique()}, divisions {out['sic_div'].nunique()}"
    )
    return out


# ── design ───────────────────────────────────────────────────────────────────


@dataclass
class Design:
    """Standardised designs for both feature sets and the shared usable mask.

    A row is usable when it has ``min_prior_events`` earlier events (so every feature is
    standardised) and a defined premium-share weight. The mask is the same for every
    configuration, with or without features, so every comparison is on identical events.
    """

    d: pd.DataFrame
    cfg: OnlineBayesConfig = OnlineBayesConfig()

    def __post_init__(self) -> None:
        self.raw: dict[str, pd.DataFrame] = {}
        self.Z: dict[str, np.ndarray] = {}
        for fs in ("declared", "wide"):
            c = replace(self.cfg, feature_set=fs)
            raw = ob.build_feature_set(self.d, c)
            z, _ = ob.causal_standardise(
                raw[list(ob.FEATURE_SETS[fs])], self.d["entry_date"], c.min_prior_events
            )
            self.raw[fs] = raw
            self.Z[fs] = z.to_numpy(float)
        ps = self.raw["declared"]["premium_share"].to_numpy()
        v2 = ob.causal_variance_weight(
            ps, self.d["entry_date"], "premium_share", self.cfg.min_prior_events
        )
        self.usable = np.isfinite(self.Z["wide"]).all(axis=1) & np.isfinite(v2)
        if not np.array_equal(self.usable, self.usable & np.isfinite(self.Z["declared"]).all(1)):
            raise AssertionError("declared and wide designs disagree on usable rows")
        self.ind = industry(self.d)
        print(f"[design] usable {int(self.usable.sum())} of {len(self.d)}")

    def X(self, cfg: OnlineBayesConfig, with_features: bool = True) -> np.ndarray:
        if not with_features:
            return np.ones((len(self.d), 1))
        z = np.clip(self.Z[cfg.feature_set], -cfg.z_clip, cfg.z_clip)
        return np.column_stack([np.ones(len(self.d)), z])

    def coef_names(self, cfg: OnlineBayesConfig, with_features: bool = True) -> list[str]:
        return ["intercept", *ob.FEATURE_SETS[cfg.feature_set]] if with_features else ["intercept"]

    def v(self, cfg: OnlineBayesConfig) -> np.ndarray:
        ps = self.raw["declared"]["premium_share"].to_numpy()
        w = ob.causal_variance_weight(
            ps,
            self.d["entry_date"],
            cfg.variance_weight,
            cfg.min_prior_events,
            power=cfg.variance_power,
        )
        return np.where(self.usable, w, np.nan)

    def frame(self, cfg: OnlineBayesConfig, y: np.ndarray, group_level: str) -> pd.DataFrame:
        g: Any = None if group_level == "none" else self.ind[group_level].to_numpy(object)
        return pd.DataFrame(
            {
                "entry_date": self.d["entry_date"],
                "settle_date": self.d["expiry"],
                "name": self.d["ticker"],
                "cluster": self.d["announce_date"],
                "y": y,
                "v": self.v(cfg),
                "group": g,
                # The 15:59 premium in % of m0 (100 s0 / m0), the transform's unit; known at entry.
                "unit": self.raw["declared"]["premium_share"].to_numpy() * cfg.pct_per_unit,
            },
            index=self.d.index,
        )

    def run(
        self,
        cfg: OnlineBayesConfig,
        y: np.ndarray,
        *,
        with_features: bool,
        group_level: str = "none",
        quiet: bool = True,
    ) -> ob.OnlineRun:
        if group_level == "none" and cfg.group_prior_scale > 0:
            raise ValueError("group_prior_scale > 0 needs a group level")
        return ob.run_online(
            self.frame(cfg, y, group_level),
            self.X(cfg, with_features),
            cfg,
            coef_names=self.coef_names(cfg, with_features),
            quiet=quiet,
        )


def discovery_mask(d: pd.DataFrame, usable: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Events scored in the rolling-origin discovery evaluation (entry years 2015 to 2018)."""
    yr = d["entry_date"].dt.year.to_numpy()
    return usable & np.isfinite(y) & np.isin(yr, DISCOVERY_YEARS)


def score(run: ob.OnlineRun, d: pd.DataFrame, mask: np.ndarray) -> dict[str, float]:
    """Mean log score over ``mask`` and by discovery year, coverage, PIT tails, selection."""
    ev = run.events
    ls = ev["log_score"].to_numpy()
    if not np.isfinite(ls[mask]).all() or not ev["scored"].to_numpy()[mask].all():
        raise AssertionError("a discovery event lacks a scored prediction")
    yr = d["entry_date"].dt.year.to_numpy()
    out: dict[str, float] = {"mean_log_score": float(ls[mask].mean()), "n": int(mask.sum())}
    for y in DISCOVERY_YEARS:
        out[f"ls_{y}"] = float(ls[mask & (yr == y)].mean())
    pit = ev["pit"].to_numpy()[mask]
    out["coverage90"] = float(ev["covered"].to_numpy()[mask].mean())
    out["pit_lo5"] = float((pit < 0.05).mean())
    out["pit_hi5"] = float((pit > 0.95).mean())
    out["n_decide"] = int(ev["decide"].to_numpy()[mask].sum())
    return out
