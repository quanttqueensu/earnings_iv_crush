"""vx_lib.py: event surplus in Treasury implied variance from VXTLT, shared by both scorers.

Builds the daily panel (VXTLT close, TLT dividend-adjusted close), the event calendar and
matched controls, and the per-event statistic defined in ``diagnosis.log`` entry 1.

The statistic is the one-day implied-minus-realised variance of a short 30-day variance
position, in units of one ordinary day's implied variance, event day minus same-weekday
non-event controls. It is an index-level, gross measure: nothing here is at the touch.

References
----------
Wright, J. H. (2020). Event-day options. NBER Working Paper 28306.
Carr, P. and Wu, L. (2009). Variance risk premiums. Review of Financial Studies 22(3), 1311-1341.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

LANE = Path(__file__).resolve().parents[1]
ROOT = LANE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

# ── configuration ──


@dataclass(frozen=True)
class VxConfig:
    """Every number the scorer uses, with its reason."""

    tau_days: float = 30.0  # VXTLT is a constant 30-calendar-day variance (VIX method)
    year_days: float = 365.0  # VIX method annualises in calendar time
    control_window_days: int = 35  # about five same-weekday neighbours each side
    min_controls: int = 2  # a single control is too noisy to difference against
    disc_start: str = "2016-01-01"  # first date of the project's event calendar
    disc_end: str = "2020-12-31"  # Wright (2020) sample ends August 2020
    held_start: str = "2021-01-01"
    held_end: str = "2026-11-12"  # last VXTLT close on disk
    n_boot: int = 5000  # project convention
    seed: int = 0


CFG = VxConfig()
KINDS = ("nfp", "cpi", "fomc")
VX_PATH = LANE / "raw" / "cboe" / "VXTLT_History.csv"
TLT_PATH = LANE / "raw" / "yahoo" / "chart_TLT.json"
CAL_PATH = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"

# ── data ──


def load_panel() -> pd.DataFrame:
    """Daily VXTLT and TLT adjusted close on dates where both exist, with one-day fields."""
    vx = pd.read_csv(VX_PATH)
    vx["date"] = pd.to_datetime(vx["DATE"], format="%m/%d/%Y")
    vx = vx.set_index("date")["VXTLT"].astype(float)
    j = json.loads(TLT_PATH.read_text())["chart"]["result"][0]
    ts = pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    tlt = pd.Series(j["indicators"]["adjclose"][0]["adjclose"], index=ts.normalize().tz_localize(None))
    tlt = tlt[~tlt.index.duplicated(keep="last")].astype(float)
    p = pd.concat({"vx": vx, "tlt": tlt}, axis=1, join="inner").dropna()
    bad = (p["vx"] <= 0) | (p["tlt"] <= 0)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} non-positive rows in panel")
    p["sig2"] = (p["vx"] / 100.0) ** 2
    p["prev_date"] = p.index.to_series().shift(1)
    p["delta"] = (p.index.to_series() - p["prev_date"]).dt.days / CFG.year_days
    p["r"] = np.log(p["tlt"] / p["tlt"].shift(1))
    tau = CFG.tau_days / CFG.year_days
    s2_prev = p["sig2"].shift(1)
    p["e"] = s2_prev * tau - p["sig2"] * (tau - p["delta"])
    p["y"] = (p["e"] - p["r"] ** 2) / (s2_prev * p["delta"])
    p["y_raw"] = p["e"] - p["r"] ** 2
    with np.errstate(invalid="ignore"):
        p["s"] = np.where(p["e"] > 0, 1.0 - p["r"].abs() / (np.sqrt(2 / np.pi) * np.sqrt(p["e"].clip(lower=0))), np.nan)
    sig_prev = np.sqrt(s2_prev)
    f_prev = p["tlt"].shift(1)
    v0 = black_straddle(f_prev, f_prev, sig_prev, tau)
    v1 = black_straddle(p["tlt"], f_prev, np.sqrt(p["sig2"]), tau - p["delta"])
    p["straddle"] = (v0 - v1) / v0  # short 30-day ATM straddle, one-day return on premium
    gap = p["delta"] > 5 / CFG.year_days
    if gap.any():
        print(f"[panel] {int(gap.sum())} rows follow a gap of more than 5 calendar days; dropped")
        p.loc[gap, ["y", "y_raw", "s", "e", "straddle"]] = np.nan
    return p.iloc[1:]


def black_straddle(f: pd.Series, k: pd.Series, sig: pd.Series, t: pd.Series | float) -> np.ndarray:
    """Black (1976) call plus put with zero rates; positional over aligned series."""
    from scipy.stats import norm

    f, k, sig = np.asarray(f, float), np.asarray(k, float), np.asarray(sig, float)
    t = np.asarray(t, float) if not np.isscalar(t) else np.full_like(f, t)
    sd = sig * np.sqrt(t)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(f / k) + 0.5 * sd**2) / sd
    d2 = d1 - sd
    call = f * norm.cdf(d1) - k * norm.cdf(d2)
    put = k * norm.cdf(-d2) - f * norm.cdf(-d1)
    return call + put


def load_events() -> pd.DataFrame:
    """One row per event date with the set of kinds released that day."""
    c = pd.read_csv(CAL_PATH, parse_dates=["date"])
    c = c[c["kind"].isin(KINDS)]
    g = c.groupby("date")["kind"].apply(lambda k: "+".join(sorted(set(k))))
    return g.rename("kinds").to_frame()


# ── statistic ──


def build_events(panel: pd.DataFrame, start: str, end: str, col: str = "y") -> pd.DataFrame:
    """Per-event value, mean of matched controls and the difference, with a printed funnel."""
    ev = load_events()
    ev_dates = set(ev.index)
    days = panel.index
    after_event = {days[i + 1] for i, d in enumerate(days[:-1]) if d in ev_dates}
    blk = ev.loc[(ev.index >= start) & (ev.index <= end)]
    n0 = len(blk)
    rows = []
    miss_data = few_ctrl = 0
    for d, kinds in blk["kinds"].items():
        if d not in panel.index or not np.isfinite(panel.at[d, col]):
            miss_data += 1
            continue
        lo, hi = d - pd.Timedelta(days=CFG.control_window_days), d + pd.Timedelta(days=CFG.control_window_days)
        win = panel.loc[lo:hi]
        ctrl = win[
            (win.index.weekday == d.weekday())
            & (~win.index.isin(ev_dates))
            & (~win.index.isin(after_event))
            & np.isfinite(win[col])
        ]
        if len(ctrl) < CFG.min_controls:
            few_ctrl += 1
            continue
        rows.append(
            {
                "date": d,
                "kinds": kinds,
                "event": float(panel.at[d, col]),
                "control": float(ctrl[col].mean()),
                "n_controls": len(ctrl),
            }
        )
    out = pd.DataFrame(rows)
    print(
        f"[funnel {start}..{end} {col}] calendar dates {n0}; no VXTLT/TLT close or gap {miss_data}; "
        f"fewer than {CFG.min_controls} controls {few_ctrl}; scored {len(out)}"
    )
    if out.empty:
        raise ValueError("no events scored")
    out["d"] = out["event"] - out["control"]
    out["month"] = out["date"].dt.to_period("M").dt.to_timestamp()
    return out


def summarise(df: pd.DataFrame, label: str, col: str = "d") -> dict:
    """Mean with month-clustered interval, per-event Sharpe, and the event and control means."""
    iv = date_clustered_ci(df[col], df["month"], stat=np.mean, n_boot=CFG.n_boot, seed=CFG.seed)
    sd = float(df[col].std(ddof=1))
    res = {
        "label": label,
        "n": iv.n,
        "clusters": iv.clusters,
        "mean": iv.point,
        "lo": iv.low,
        "hi": iv.high,
        "sharpe": float(df[col].mean() / sd) if sd > 0 else float("nan"),
        "event_mean": float(df["event"].mean()),
        "control_mean": float(df["control"].mean()),
        "median_d": float(df[col].median()),
    }
    print(
        f"{label}: mean {res['mean']:+.4f} [{res['lo']:+.4f}, {res['hi']:+.4f}] N={res['n']} "
        f"({res['clusters']} month clusters); per-event Sharpe {res['sharpe']:+.3f}; "
        f"event {res['event_mean']:+.4f} vs control {res['control_mean']:+.4f}; median d {res['median_d']:+.4f}"
    )
    return res
