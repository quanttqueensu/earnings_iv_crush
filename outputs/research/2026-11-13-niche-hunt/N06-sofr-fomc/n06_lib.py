"""n06_lib.py: FOMC short-rate variance premium from the Atlanta Fed Market Probability Tracker.

Builds, for each FOMC decision date and each matched control Wednesday, the two-row payoff of
selling an at-the-money Bachelier straddle on every quarterly SOFR reference window, marked from
the tracker's risk-neutral quartiles and mean. The design is pre-registered in diagnosis.log
(entry 1); this module only implements it. Every filter prints a funnel.

References
----------
Bauer, M., Lakdawala, A. and Mueller, P. (2022). Market-based monetary policy uncertainty.
    Economic Journal 132(644), 1290-1308.
Wright, J. H. (2025). Event-day options. Journal of Time Series Analysis 46(6), 1085-1097.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import N_BOOT, SEED, date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
MPT_XLSX = HERE / "data" / "mpt_histdata.xlsx"
RELEASES = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"


# ── configuration (every number is pre-registered in diagnosis.log entry 1) ──


@dataclass(frozen=True)
class N06Config:
    """Single source of truth for the lane's constants."""

    iqr_to_sd: float = 1.349  # normal IQR in standard deviations
    atm_straddle: float = float(2 * norm.pdf(0.0))  # Bachelier ATM straddle per unit SD
    h_min: int = 30  # shortest horizon (days, row t-1 to window start) in the primary band
    h_max: int = 730  # longest horizon: the liquid first two years of quarterly options
    half_spread_low_bp: float = 0.125  # quarter-tick-wide market, 0.0025 IMM points
    half_spread_pass_bp: float = 0.25  # half-tick-wide market, 0.005 IMM points: pass level
    legs_paid: int = 4  # straddle sold (2 legs) and bought back (2 legs)
    discovery_end: str = "2024-12-31"
    min_bin_mass: float = 90.0  # bin-based robustness keeps rows with this much mass (%)
    sheppard_bp2: float = 25.0**2 / 12.0  # Sheppard correction for 25 bp bins


CFG = N06Config()

# Minutes release dates (federalreserve.gov/monetarypolicy/fomccalendars.htm, read 2026-11-13).
MINUTES = pd.to_datetime(
    [
        "2023-04-12", "2023-05-24", "2023-07-05", "2023-08-16", "2023-10-11", "2023-11-21",
        "2024-01-03", "2024-02-21", "2024-04-10", "2024-05-22", "2024-07-03", "2024-08-21",
        "2024-10-09", "2024-11-26", "2025-01-08", "2025-02-19", "2025-04-09", "2025-05-28",
        "2025-07-09", "2025-08-20", "2025-10-08", "2025-11-19", "2025-12-30", "2026-02-18",
        "2026-04-08", "2026-05-20", "2026-07-08", "2026-08-19", "2026-10-07",
    ]
)
# Meetings with a Summary of Economic Projections (same source).
SEP = pd.to_datetime(
    [
        "2023-06-14", "2023-09-20", "2023-12-13", "2024-03-20", "2024-06-12", "2024-09-18",
        "2024-12-18", "2025-03-19", "2025-06-18", "2025-09-17", "2025-12-10", "2026-03-18",
        "2026-06-17", "2026-09-16",
    ]
)


# ── loading ──


def load_mpt() -> pd.DataFrame:
    """Wide table: one row per (date, reference_start) with mean, q25, q75 and bin moments."""
    raw = pd.read_excel(MPT_XLSX, sheet_name="DATA")
    raw["date"] = pd.to_datetime(raw["date"])
    raw["reference_start"] = pd.to_datetime(raw["reference_start"])
    key = ["date", "reference_start"]
    stats = raw[raw["field"].isin(["Rate: mean", "Rate: 25th percentile", "Rate: 75th percentile"])]
    wide = stats.pivot_table(index=key, columns="field", values="value", aggfunc="first")
    wide = wide.rename(
        columns={"Rate: mean": "F", "Rate: 25th percentile": "q25", "Rate: 75th percentile": "q75"}
    )
    bins = raw[raw["field"].str.match(r"Prob: \d")].copy()
    lo_hi = bins["field"].str.extract(r"Prob: (\d+)bps - (\d+)bps").astype(float)
    bins["mid"] = lo_hi.mean(axis=1)
    bins["p"] = bins["value"] / 100.0
    g = bins.groupby(key)
    mass = g["p"].sum()
    m1 = g.apply(lambda x: float((x["p"] * x["mid"]).sum() / x["p"].sum()), include_groups=False)
    m2 = g.apply(
        lambda x: float((x["p"] * x["mid"] ** 2).sum() / x["p"].sum()), include_groups=False
    )
    wide["bin_mass_pct"] = mass * 100.0
    wide["V_bin"] = (m2 - m1**2) - CFG.sheppard_bp2
    wide = wide.reset_index()
    wide["V_iqr"] = ((wide["q75"] - wide["q25"]) / CFG.iqr_to_sd) ** 2
    bad = wide[["F", "q25", "q75"]].isna().any(axis=1).sum()
    if bad:
        print(f"[load] WARNING {bad} rows missing mean or quartiles; dropped")
        wide = wide.dropna(subset=["F", "q25", "q75"])
    print(f"[load] {len(wide)} date-window rows, {wide['date'].nunique()} dates")
    return wide


def load_releases() -> pd.DataFrame:
    rel = pd.read_csv(RELEASES, parse_dates=["date"])
    return rel


# ── event and control windows ──


def _adjacent_rows(dates: pd.DatetimeIndex, d: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Rows immediately before and after d, or None if d is not a row."""
    pos = dates.searchsorted(d)
    if pos >= len(dates) or dates[pos] != d or pos == 0 or pos + 1 >= len(dates):
        return None
    return dates[pos - 1], dates[pos + 1]


def build_windows(mpt: pd.DataFrame, rel: pd.DataFrame) -> pd.DataFrame:
    """One row per (anchor date, arm) with its t-1 and t+1 rows, with a printed funnel."""
    dates = pd.DatetimeIndex(sorted(mpt["date"].unique()))
    fomc = pd.DatetimeIndex(sorted(rel.loc[rel["kind"] == "fomc", "date"]))
    fomc = fomc[(fomc > dates[0]) & (fomc < dates[-1])]
    macro = pd.DatetimeIndex(rel.loc[rel["kind"].isin(["cpi", "nfp"]), "date"])
    blocked = set(fomc) | set(MINUTES) | set(macro)
    rows = []
    for t in fomc:
        adj = _adjacent_rows(dates, t)
        if adj is None:
            print(f"[funnel] FOMC {t.date()} has no adjacent rows; dropped")
            continue
        coincident = any((t + pd.Timedelta(days=k)) in set(macro) for k in (0, 1))
        rows.append(dict(anchor=t, arm="fomc", t0=adj[0], t1=adj[1], coincident=coincident))
    n_fomc = len(rows)
    wed = dates[dates.dayofweek == 2]
    n_w, n_adj, n_clean = len(wed), 0, 0
    for d in wed:
        adj = _adjacent_rows(dates, d)
        if adj is None or (adj[0] != d - pd.Timedelta(days=1)) or (adj[1] != d + pd.Timedelta(days=1)):
            continue
        n_adj += 1
        if any((d + pd.Timedelta(days=k)) in blocked for k in (-2, -1, 0, 1)):
            continue
        n_clean += 1
        rows.append(dict(anchor=d, arm="control", t0=adj[0], t1=adj[1], coincident=False))
    print(
        f"[funnel] FOMC events {len(fomc)} in range -> {n_fomc} with adjacent rows; "
        f"Wednesdays {n_w} -> {n_adj} with consecutive rows -> {n_clean} clean controls"
    )
    return pd.DataFrame(rows)


# ── payoffs ──


def bachelier_straddle(sd: np.ndarray, moneyness: np.ndarray) -> np.ndarray:
    """Straddle value for SD sd and forward minus strike moneyness, both in bp."""
    x = moneyness / sd
    return sd * (2 * norm.pdf(x) + x * (2 * norm.cdf(x) - 1))


def window_payoffs(mpt: pd.DataFrame, win: pd.DataFrame, vcol: str = "V_iqr") -> pd.DataFrame:
    """Per (anchor, window): pi in bp^2, straddle return, premium and hurdles."""
    a = mpt.set_index(["date", "reference_start"])
    out = []
    for w in win.itertuples(index=False):
        try:
            s0 = a.xs(w.t0, level="date")
            s1 = a.xs(w.t1, level="date")
        except KeyError:
            print(f"[funnel] {w.anchor.date()} missing a row; dropped")
            continue
        j = s0.join(s1, lsuffix="0", rsuffix="1", how="inner")
        j = j.reset_index()
        j["h"] = (j["reference_start"] - w.t0).dt.days
        j = j[(j["h"] >= CFG.h_min) & (j["h"] <= CFG.h_max)]
        if vcol == "V_bin":
            j = j[(j["bin_mass_pct0"] >= CFG.min_bin_mass) & (j["bin_mass_pct1"] >= CFG.min_bin_mass)]
        j = j[(j[f"{vcol}0"] > 0) & (j[f"{vcol}1"] > 0)]
        if j.empty:
            print(f"[funnel] {w.anchor.date()} {w.arm}: no windows in band; dropped")
            continue
        v0, v1 = j[f"{vcol}0"].to_numpy(), j[f"{vcol}1"].to_numpy()
        dF = (j["F1"] - j["F0"]).to_numpy()
        p0 = CFG.atm_straddle * np.sqrt(v0)
        p1 = bachelier_straddle(np.sqrt(v1), dF)
        o = pd.DataFrame(
            dict(
                anchor=w.anchor, arm=w.arm, coincident=w.coincident,
                reference_start=j["reference_start"].to_numpy(), h=j["h"].to_numpy(),
                V0=v0, V1=v1, dF=dF, dV=v0 - v1, pi=v0 - v1 - dF**2,
                P0=p0, r=1 - p1 / p0,
                hurdle_low=CFG.legs_paid * CFG.half_spread_low_bp / p0,
                hurdle_pass=CFG.legs_paid * CFG.half_spread_pass_bp / p0,
            )
        )
        out.append(o)
    return pd.concat(out, ignore_index=True)


def per_date(pay: pd.DataFrame) -> pd.DataFrame:
    """Average windows within each anchor date: one observation per date."""
    g = pay.groupby(["anchor", "arm"], as_index=False).agg(
        R=("r", "mean"), hurdle_low=("hurdle_low", "mean"), hurdle_pass=("hurdle_pass", "mean"),
        pi=("pi", "mean"), dV=("dV", "mean"), dF2=("dF", lambda x: float(np.mean(x**2))),
        P0=("P0", "mean"), n_windows=("r", "size"), coincident=("coincident", "first"),
    )
    return g


# ── statistics ──


def diff_ci(a: np.ndarray, b: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float]:
    """Mean(a) - mean(b), with a 95% interval from independent bootstraps over dates."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.size < 2 or b.size < 2:
        raise ValueError("each arm needs at least two dates")
    da = rng.choice(a, size=(n_boot, a.size)).mean(1)
    db = rng.choice(b, size=(n_boot, b.size)).mean(1)
    d = da - db
    return float(a.mean() - b.mean()), float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))


def mean_ci(values: np.ndarray, dates: np.ndarray):
    return date_clustered_ci(values, dates, stat=np.mean)


def block(df: pd.DataFrame, name: str) -> pd.DataFrame:
    end = pd.Timestamp(CFG.discovery_end)
    if name == "discovery":
        return df[df["anchor"] <= end]
    if name == "heldout":
        return df[df["anchor"] > end]
    raise ValueError(name)
