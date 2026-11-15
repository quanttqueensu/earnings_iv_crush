"""eia_event_variance.py: implied versus realised variance on EIA release days, OVX and WTI.

Gross, at-the-mid pricing test of the weekly EIA Petroleum Status Report (lane N04). The
measurement is fixed in ``diagnosis.log`` entry 1; this file implements it and nothing else.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N04-crude-eia-opec/eia_event_variance.py \
        --block discovery --trial 2174 [--realised c1|spot]

T2172 and T2173 used USO prices from Yahoo, withdrawn for robots non-compliance (diagnosis.log
entry 3); from T2174 the realised leg is EIA's WTI contract-1 settlement or Cushing spot.

The held-out block refuses to run unless a ``freeze_*.md`` note exists in this folder.

References
----------
Cboe (2009-), OVX methodology: 30-day variance from USO option midpoints (VIX method).
Sharma, M. (2017), Do scheduled announcements affect market uncertainty in energy derivative
markets?, MSc thesis, University of Georgia (supervisor B. Karali).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

# ── constants (rationale in diagnosis.log entry 1) ──
HERE = Path(__file__).resolve().parent
TAU = 30.0 / 365.0  # OVX is a 30-calendar-day variance
FAR_END_FIX = True  # False reproduces T2172 (diagnosis entry 2)
BLOCKS = {
    "discovery": ("2009-09-21", "2019-12-31"),
    "heldout": ("2021-01-01", "2026-11-12"),
}
ROLL_BUFFER = 2  # business days either side of the computed CL expiry (entry 3)


def _mean(x: np.ndarray) -> float:
    return float(np.mean(x))


def cl_expiry(year: int, month: int) -> pd.Timestamp:
    """CL contract-1 last trade in calendar month (year, month), weekday arithmetic only.

    Three business days before the 25th; if the 25th is a weekend, three business days before
    the last business day preceding it (NYMEX rule 200.05, holidays ignored, hence a buffer).
    """
    d25 = pd.Timestamp(year=year, month=month, day=25)
    if d25.weekday() >= 5:
        d25 = d25 - pd.offsets.BDay(1)
    return (d25 - pd.offsets.BDay(3)).normalize()


def roll_zone(start: str, end: str) -> set[pd.Timestamp]:
    """Dates within ROLL_BUFFER business days of any computed CL expiry."""
    out: set[pd.Timestamp] = set()
    for m in pd.period_range(start, end, freq="M"):
        e = cl_expiry(m.year, m.month)
        for k in range(-ROLL_BUFFER, ROLL_BUFFER + 2):  # +1 covers the first day after expiry
            out.add((e + pd.offsets.BDay(k)).normalize())
    return out


def load_daily(realised: str) -> pd.DataFrame:
    """Join OVX and an EIA WTI series on trading dates; consumed implied and realised variance."""
    ovx = pd.read_csv(HERE / "raw" / "OVX_History.csv")
    ovx["date"] = pd.to_datetime(ovx["DATE"], format="%m/%d/%Y")
    ovx = ovx.set_index("date")["OVX"].astype(float)
    wti = pd.read_csv(HERE / "data" / "wti_daily.csv", index_col=0, parse_dates=True)
    px = wti[realised].astype(float)
    df = pd.concat({"ovx": ovx, "px": px}, axis=1, join="inner").dropna()
    n0 = len(df)
    df = df[(df["ovx"] > 0) & (df["px"] > 0)]
    if len(df) < n0:
        print(f"funnel: dropped {n0 - len(df)} rows with non-positive OVX or price")
    df["V"] = (df["ovx"] / 100.0) ** 2 * TAU
    df["prev"] = pd.Series(df.index, index=df.index).shift(1)
    k = (pd.Series(df.index, index=df.index) - df["prev"]).dt.days
    # constant 30-day maturity: add back the far-end day the window gains (diagnosis entry 2)
    far_end = (df["ovx"] / 100.0) ** 2 * k / 365.0 if FAR_END_FIX else 0.0
    df["dV"] = df["V"].shift(1) - df["V"] + far_end
    df["r"] = np.log(df["px"] / df["px"].shift(1))
    df["r2"] = df["r"] ** 2
    df["carry"] = df["dV"] - df["r2"]
    return df.dropna()


def build_pairs(df: pd.DataFrame, control: str, event: str) -> pd.DataFrame:
    """One row per week: event-day and control-day carry, with the funnel printed."""
    hol = set(USFederalHolidayCalendar().holidays("2009-01-01", "2027-12-31"))
    days = pd.Series(df.index, index=df.index)
    week = days.dt.to_period("W-SUN")
    rows = []
    funnel = {"weeks": 0, "holiday_mon_wed": 0, "roll": 0, "missing_day": 0, "gap": 0, "kept": 0}
    rolls = roll_zone(str(df.index.min().date()), str(df.index.max().date()))
    for wk, _idx in days.groupby(week):
        funnel["weeks"] += 1
        mon = wk.start_time.normalize()
        mon_wed = {mon + pd.Timedelta(days=k) for k in range(3)}
        shifted = bool(mon_wed & hol)
        if event == "wed" and shifted:
            funnel["holiday_mon_wed"] += 1
            continue
        if event == "thu_shift" and not shifted:
            continue
        if mon_wed & rolls:
            funnel["roll"] += 1
            continue
        ev_day = mon + pd.Timedelta(days=2 if event == "wed" else 3)
        ct_day = mon + pd.Timedelta(days=1 if control == "tue" else 3)
        if event == "thu_shift":
            ct_day = mon + pd.Timedelta(days=4)  # Friday after a Thursday release
        if ev_day not in df.index or ct_day not in df.index:
            funnel["missing_day"] += 1
            continue
        ok = True
        for d in (ev_day, ct_day):
            gap = np.busday_count(df.loc[d, "prev"].date(), d.date())
            if gap != 1:
                ok = False
        if not ok:
            funnel["gap"] += 1
            continue
        e, c = df.loc[ev_day], df.loc[ct_day]
        rows.append(
            {
                "week": wk.start_time.date(),
                "event_day": ev_day.date(),
                "dV_e": e["dV"],
                "dV_c": c["dV"],
                "r2_e": e["r2"],
                "r2_c": c["r2"],
                "d": e["carry"] - c["carry"],
            }
        )
        funnel["kept"] += 1
    print("funnel:", json.dumps(funnel))
    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("no event weeks survived the filters")
    return out


def score(pairs: pd.DataFrame) -> dict:
    """Primary statistic, components and the break-even half-spread share."""
    weeks = pd.to_datetime(pairs["week"])
    months = weeks.dt.to_period("M").dt.to_timestamp()
    res: dict = {"n_weeks": int(len(pairs))}
    for name, col in (
        ("d", pairs["d"]),
        ("implied_excess", pairs["dV_e"] - pairs["dV_c"]),
        ("realised_excess", pairs["r2_e"] - pairs["r2_c"]),
        ("carry_event", pairs["dV_e"] - pairs["r2_e"]),
        ("carry_control", pairs["dV_c"] - pairs["r2_c"]),
    ):
        iv = date_clustered_ci(col.to_numpy(), weeks, stat=_mean)
        ivm = date_clustered_ci(col.to_numpy(), months, stat=_mean)
        res[name] = {
            "mean": iv.point,
            "ci_week": [iv.low, iv.high],
            "ci_month": [ivm.low, ivm.high],
        }
    mean_dv_e = float(pairs["dV_e"].mean())
    mean_dv_c = float(pairs["dV_c"].mean())
    res["mean_dV_event"] = mean_dv_e
    res["mean_dV_control"] = mean_dv_c
    res["mean_r2_event"] = float(pairs["r2_e"].mean())
    res["mean_r2_control"] = float(pairs["r2_c"].mean())
    res["breakeven_halfspread_share"] = 0.5 * res["d"]["mean"] / mean_dv_e
    res["breakeven_halfspread_share_ci_week"] = [0.5 * x / mean_dv_e for x in res["d"]["ci_week"]]

    # winsorised robustness: top 1% of |r2| events drive variance tests
    # T2175: EIA-day excess realised variance in units of an ordinary Tuesday
    def _rho(idx: np.ndarray) -> float:
        return float(pairs["r2_e"].to_numpy()[idx].sum() / pairs["r2_c"].to_numpy()[idx].sum() - 1)

    rng = np.random.default_rng(20261113)
    n = len(pairs)
    boots = [_rho(rng.integers(0, n, n)) for _ in range(10_000)]
    res["rho"] = {
        "point": _rho(np.arange(n)),
        "ci_week": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
    }
    # T2176: straddle break-even ratio against the implied ratio (diagnosis entry 4)
    ae = np.sqrt(pairs["r2_e"].to_numpy())
    ac = np.sqrt(pairs["r2_c"].to_numpy())
    ve = pairs["dV_e"].to_numpy()
    vc = pairs["dV_c"].to_numpy()

    def _g(idx: np.ndarray) -> tuple[float, float, float]:
        b = ae[idx].mean() / ac[idx].mean()
        i = float(np.sqrt(max(ve[idx].mean(), 0.0) / vc[idx].mean()))
        return i - b, b, i

    gb = np.array([_g(rng.integers(0, n, n)) for _ in range(10_000)])
    g0 = _g(np.arange(n))
    res["straddle_ratio"] = {
        "g": g0[0],
        "B": g0[1],
        "I": g0[2],
        "g_over_I": g0[0] / g0[2],
        "g_ci_week": [float(np.quantile(gb[:, 0], 0.025)), float(np.quantile(gb[:, 0], 0.975))],
        "B_ci_week": [float(np.quantile(gb[:, 1], 0.025)), float(np.quantile(gb[:, 1], 0.975))],
        "I_ci_week": [float(np.quantile(gb[:, 2], 0.025)), float(np.quantile(gb[:, 2], 0.975))],
    }

    # T2177: buyer of the one-day straddle, gross at the mid (diagnosis entry 5)
    def _rb(idx: np.ndarray) -> tuple[float, float, float]:
        rb = ae[idx].mean() / (np.sqrt(2 / np.pi) * np.sqrt(max(ve[idx].mean(), 1e-12))) - 1
        rc = ac[idx].mean() / (np.sqrt(2 / np.pi) * np.sqrt(vc[idx].mean())) - 1
        return rb, rc, rb - rc

    rbb = np.array([_rb(rng.integers(0, n, n)) for _ in range(10_000)])
    r0 = _rb(np.arange(n))
    res["buyer"] = {
        "R_buy": r0[0],
        "R_ctl": r0[1],
        "diff": r0[2],
        "R_buy_ci_week": [
            float(np.quantile(rbb[:, 0], 0.025)),
            float(np.quantile(rbb[:, 0], 0.975)),
        ],
        "R_ctl_ci_week": [
            float(np.quantile(rbb[:, 1], 0.025)),
            float(np.quantile(rbb[:, 1], 0.975)),
        ],
        "diff_ci_week": [
            float(np.quantile(rbb[:, 2], 0.025)),
            float(np.quantile(rbb[:, 2], 0.975)),
        ],
    }
    res["median_ratio_r2"] = float(pairs["r2_e"].median() / pairs["r2_c"].median())
    q = pairs["r2_e"].quantile(0.99)
    trimmed = pairs[pairs["r2_e"] <= q]
    res["d_mean_excl_top1pct_event_moves"] = float(trimmed["d"].mean())
    return res


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_freeze() -> None:
    """Held-out runs only against an unmodified freeze note that names this scorer's hash."""
    notes = sorted(glob.glob(str(HERE / "freeze_*.md")))
    if len(notes) != 1:
        raise SystemExit(f"expected exactly one freeze note, found {len(notes)}")
    note = Path(notes[0])
    side = Path(str(note) + ".sha256")
    if not side.exists() or side.read_text().split()[0] != _sha(note):
        raise SystemExit("freeze note hash does not match its sidecar")
    if _sha(Path(__file__)) not in note.read_text(encoding="utf-8"):
        raise SystemExit("scorer hash not recorded in the freeze note; scorer changed after freeze")
    print(f"freeze verified: {note.name}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--block", choices=list(BLOCKS), required=True)
    p.add_argument("--trial", type=int, required=True)
    p.add_argument("--realised", choices=["c1", "spot"], default="c1")
    p.add_argument("--control", choices=["tue", "thu"], default="tue")
    p.add_argument("--event", choices=["wed", "thu_shift"], default="wed")
    a = p.parse_args()
    if not 2172 <= a.trial <= 2201:
        raise SystemExit("trial number outside the N04 block")
    if a.block == "heldout":
        _verify_freeze()
    lo, hi = BLOCKS[a.block]
    df = load_daily(a.realised)
    df = df[(df.index >= lo) & (df.index <= hi)]
    pairs = build_pairs(df, a.control, a.event)
    res = score(pairs)
    res.update(
        {
            "trial": a.trial,
            "block": a.block,
            "control": a.control,
            "event": a.event,
            "realised": a.realised,
        }
    )
    tag = f"T{a.trial}_{a.block}_{a.realised}_{a.event}_{a.control}"
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    pairs.to_csv(out / f"{tag}_pairs.csv", index=False)
    (out / f"{tag}.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
