"""event_scorer.py: N17 ceiling test of scheduled-report variance premia in commodity ETF options.

Scores, per family (ETF, Cboe volatility index, report), the one-day short-straddle-equivalent
P&L at the mid across report days against matched non-report controls, and against the
round-trip touch cost measured on 2026-11-13 snapshots. The pre-registration is the
2026-11-13 14:50 entry of ``diagnosis.log``; the held-out block runs only when
``freeze_n17.md`` exists and records this file's SHA-256.

Basis of every output: per trade (one report day), gross at the mid from index closes
(model-based, not a tradeable level) for S1; S2 subtracts a measured round-trip touch share.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N17-commodity-etf-options/event_scorer.py \
        --block discovery
    python .../event_scorer.py --block heldout   # once, after the freeze note
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
MACRO = REPO / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"
FREEZE = HERE / "freeze_n17.md"

# ── constants fixed in the pre-registration ──────────────────────────────────
INDEX_TENOR_DAYS = 30
DISCOVERY_END = pd.Timestamp("2020-12-31")
HELDOUT_START, HELDOUT_END = pd.Timestamp("2021-01-01"), pd.Timestamp("2026-10-30")
MACRO_START = pd.Timestamp("2016-01-01")
CTRL_WINDOW_MACRO = 28
CTRL_WINDOW_WPSR = 21
MIN_CONTROLS = 2
COST_DTE = (21, 35)
SHORT_TENOR = 7  # calendar days: a one-week straddle, the front weekly spanning the report
COST_DTE_SHORT = (5, 10)
COMMISSION = 0.65  # USD per contract, IBKR Pro fixed (earnings_iv_crush/config.py uses the same)
MULTIPLIER = 100
COST_FILE = HERE / "cost_basis_frozen.csv"  # copy of spread_table.csv taken at the freeze
COST_SNAPS = {"20261113_1435"}  # the cost basis: the 14:33 ET snapshot (see diagnosis.log)

FAMILIES = {
    "USO_WPSR": ("USO", "OVX", "wpsr"),
    "GLD_MACRO": ("GLD", "GVZ", "macro"),
    "SLV_MACRO": ("SLV", "VXSLV", "macro"),
    "TLT_MACRO": ("TLT", "VXTLT", "macro"),
}
TRIALS = {
    "USO_WPSR": 2562, "GLD_MACRO": 2563, "SLV_MACRO": 2564, "TLT_MACRO": 2565,
    "GLD_cpi": 2566, "GLD_nfp": 2567, "GLD_fomc": 2568,
    "SLV_cpi": 2569, "SLV_nfp": 2570, "SLV_fomc": 2571,
    "TLT_cpi": 2572, "TLT_nfp": 2573, "TLT_fomc": 2574,
}
TRIALS_SHORT = {
    "USO_WPSR": 2575, "GLD_MACRO": 2576, "SLV_MACRO": 2577, "TLT_MACRO": 2578,
    "GLD_cpi": 2579, "GLD_nfp": 2580, "GLD_fomc": 2581,
    "SLV_cpi": 2582, "SLV_nfp": 2583, "SLV_fomc": 2584,
    "TLT_cpi": 2585, "TLT_nfp": 2586, "TLT_fomc": 2587,
}


# ── inputs ───────────────────────────────────────────────────────────────────


def load_index(sym: str) -> pd.Series:
    df = pd.read_csv(RAW / f"cboe_{sym}.csv")
    col = "CLOSE" if "CLOSE" in df.columns else sym
    s = pd.Series(pd.to_numeric(df[col], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df["DATE"], format="%m/%d/%Y"), name=sym)
    s = s[s > 0].dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_etf(sym: str) -> pd.Series:
    """Split-adjusted, dividend-unadjusted daily closes from Cboe's public historical endpoint."""
    df = pd.read_csv(RAW / f"cboehist_{sym}.csv", parse_dates=["date"])
    s = df.set_index("date")["close"].astype(float)
    s = s[s > 0].dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def excluded_days(etf: str, days: pd.DatetimeIndex) -> np.ndarray:
    """Days removed from events and controls alike, decided before any outcome.

    TLT pays a monthly dividend and the closes are not dividend-adjusted; its ex-date is the first
    trading day of the month (recalled iShares practice), so those days are dropped for TLT. GLD,
    SLV and USO pay no dividends.
    """
    if etf != "TLT":
        return np.zeros(len(days), dtype=bool)
    month = days.to_period("M")
    first = pd.Series(days, index=days).groupby(month).transform("min").to_numpy()
    return days.to_numpy() == first


def daily_panel(etf: str, idx: str) -> pd.DataFrame:
    """Per-day share30 on sessions where both the index and the ETF have consecutive closes."""
    px, iv = load_etf(etf), load_index(idx)
    common = px.index.intersection(iv.index)
    df = pd.DataFrame({"px": px.reindex(common), "iv": iv.reindex(common)})
    df["d_prev"] = df.index.to_series().shift(1)
    df["n"] = (df.index.to_series() - df["d_prev"]).dt.days
    s0, s1 = df["iv"].shift(1) / 100.0, df["iv"] / 100.0
    r = np.log(df["px"] / df["px"].shift(1))
    n = df["n"]
    df["r2"] = r**2
    df["dv30"] = (s1**2 - s0**2) * INDEX_TENOR_DAYS / 365.0
    df["var_pnl"] = s0**2 * n / 365.0 - r**2 - ((INDEX_TENOR_DAYS - n) / 365.0) * (s1**2 - s0**2)
    df["v30"] = s0**2 * INDEX_TENOR_DAYS / 365.0
    df["share30"] = df["var_pnl"] / (2.0 * df["v30"])
    df = df.dropna(subset=["share30"])
    # A gap longer than a long weekend means a missing close in one source; such pairs are not
    # one-day trades and are dropped loudly.
    long_gap = df["n"] > 4
    if long_gap.any():
        print(f"  {etf}/{idx}: dropped {int(long_gap.sum())} pairs with gap > 4 calendar days")
    df = df[~long_gap]
    excl = excluded_days(etf, df.index)
    if excl.any():
        print(f"  {etf}: dropped {int(excl.sum())} first-of-month sessions (ex-dividend proxy)")
    return df[~excl]


def macro_calendar() -> pd.DataFrame:
    m = pd.read_csv(MACRO, parse_dates=["date"])
    return m


def holiday_weeks(start: str, end: str) -> set[pd.Timestamp]:
    """Monday-dated weeks with a federal or NYSE-closure weekday on Monday to Wednesday."""
    fed = USFederalHolidayCalendar().holidays(start=start, end=end)
    weeks = set()
    for h in fed:
        if h.weekday() <= 2:
            weeks.add((h - pd.Timedelta(days=h.weekday())).normalize())
    return weeks


# ── event and control construction ───────────────────────────────────────────


def build_pairs(panel: pd.DataFrame, kind: str) -> pd.DataFrame:
    days = panel.index
    macro = macro_calendar()
    macro_days = set(macro["date"].dt.normalize())
    if kind == "wpsr":
        hw = holiday_weeks(str(days.min().date()), str(days.max().date()))
        # NYSE closures on Mon-Wed also shift the release; a missing weekday session marks them.
        all_bd = pd.bdate_range(days.min(), days.max())
        missing = set(all_bd.difference(days))
        for d in missing:
            if d.weekday() <= 2:
                hw.add((d - pd.Timedelta(days=d.weekday())).normalize())
        week = (days - pd.to_timedelta(days.weekday, unit="D")).normalize()
        in_hw = pd.Series(week, index=days).isin(hw).to_numpy()
        is_macro = days.normalize().isin(macro_days)
        ev_mask = (days.weekday == 2) & ~in_hw & ~is_macro & (panel["n"].to_numpy() == 1)
        ctrl_mask = np.isin(days.weekday, [1, 3]) & ~in_hw & ~is_macro & (panel["n"].to_numpy() == 1)
        window = CTRL_WINDOW_WPSR
        labels = pd.Series("wpsr", index=days)
        n_cal_events = int((days.weekday == 2).sum())
        print(f"  WPSR funnel: Wednesdays {n_cal_events}, holiday-week drop "
              f"{int(((days.weekday == 2) & in_hw).sum())}, macro-coincident drop "
              f"{int(((days.weekday == 2) & ~in_hw & is_macro).sum())}, n!=1 drop "
              f"{int(((days.weekday == 2) & ~in_hw & ~is_macro & (panel['n'].to_numpy() != 1)).sum())}")
    else:
        mk = macro.groupby(macro["date"].dt.normalize())["kind"].apply(lambda s: "+".join(sorted(s)))
        ev_mask = days.normalize().isin(mk.index) & (days >= MACRO_START)
        ctrl_mask = ~days.normalize().isin(macro_days) & (days >= MACRO_START - pd.Timedelta(days=40))
        window = CTRL_WINDOW_MACRO
        labels = pd.Series(mk.reindex(days.normalize()).to_numpy(), index=days)
        n_cal = int(((mk.index >= days.min()) & (mk.index <= days.max())).sum())
        print(f"  macro funnel: calendar dates in span {n_cal}, matched to a session pair "
              f"{int(ev_mask.sum())}")
    ev_days = days[ev_mask]
    ctrl = panel[ctrl_mask]
    rows = []
    dropped = 0
    for d in ev_days:
        e = panel.loc[d]
        c = ctrl[(abs((ctrl.index - d).days) <= window)]
        if kind != "wpsr":
            c = c[(c.index.weekday == d.weekday()) & (c["n"] == e["n"])]
        if len(c) < MIN_CONTROLS:
            dropped += 1
            continue
        rows.append({
            "date": d, "kind": labels.loc[d], "n": int(e["n"]),
            "share30": e["share30"], "ctrl_share30": c["share30"].mean(), "n_ctrl": len(c),
            "r2": e["r2"], "ctrl_r2": c["r2"].mean(),
            "dv30": e["dv30"], "ctrl_dv30": c["dv30"].mean(), "iv_prev": panel["iv"].shift(1).loc[d],
            "var_pnl": e["var_pnl"],
            # normalised by the day's own 30-day implied variance, for the diagnostic ratio
            "imp_norm": -e["dv30"] / e["v30"], "ctrl_imp_norm": (-c["dv30"] / c["v30"]).mean(),
            "real_norm": e["r2"] / e["v30"], "ctrl_real_norm": (c["r2"] / c["v30"]).mean(),
            "v30": e["v30"],
        })
    print(f"  events kept {len(rows)}, dropped for < {MIN_CONTROLS} controls {dropped}")
    out = pd.DataFrame(rows)
    out["surplus"] = out["share30"] - out["ctrl_share30"]
    return out


# ── costs ────────────────────────────────────────────────────────────────────


def cost_shares(dte: tuple[int, int]) -> dict[str, float]:
    t = pd.read_csv(COST_FILE)
    t = t[(t.status == "ok") & t.dte_cal.between(*dte) & t.snap.astype(str).isin(COST_SNAPS)].copy()
    # Commission: two legs, opened and closed, per 100-share contract, as a share of the mid.
    t["total_share"] = t["rt_cost_share"] + COMMISSION * 4 / (MULTIPLIER * t["straddle_mid"])
    out = t.groupby("sym")["total_share"].median().to_dict()
    n = t.groupby("sym").size().to_dict()
    print(f"  round-trip touch plus commission, share of mid (median, {dte[0]}-{dte[1]} dte): "
          + ", ".join(f"{k} {v:.4f} (n={n[k]})" for k, v in out.items()))
    return out


# ── short-tenor equivalent ───────────────────────────────────────────────────

LUMP_FILE = HERE / "lump_fractions_discovery.json"


def lump_fractions(pairs: pd.DataFrame) -> float:
    """Event lump as a fraction of 30-day implied variance: event minus control, clipped at 0."""
    return max(0.0, float((pairs["imp_norm"] - pairs["ctrl_imp_norm"]).mean()))


def share_short(pairs: pd.DataFrame, tenor: int, lump_frac: float) -> pd.Series:
    """var_pnl over twice the short straddle's total variance: base over the tenor plus the lump."""
    base = pairs["v30"] * tenor / INDEX_TENOR_DAYS
    return pairs["var_pnl"] / (2.0 * (base + lump_frac * pairs["v30"]))


# ── scoring ──────────────────────────────────────────────────────────────────


def _mean(x: np.ndarray) -> float:
    return float(np.mean(x))


def score(pairs: pd.DataFrame, cost: float, label: str, trial: int, tenor: int,
          lump_frac: float) -> dict:
    if len(pairs) < 5:
        print(f"  {label}: N={len(pairs)} too small to score")
        return {"trial": trial, "family": label, "tenor": tenor, "n": len(pairs)}
    if tenor == INDEX_TENOR_DAYS:
        ev, ctrl = pairs["share30"], pairs["ctrl_share30"]
    else:
        ev = share_short(pairs, tenor, lump_frac)
        ctrl = pairs["ctrl_share30"] * INDEX_TENOR_DAYS / tenor
    s1 = date_clustered_ci(ev - ctrl, pairs["date"], stat=_mean)
    s2 = date_clustered_ci(ev - cost, pairs["date"], stat=_mean)
    tot = date_clustered_ci(ev, pairs["date"], stat=_mean)
    imp_ex = float((pairs["imp_norm"] - pairs["ctrl_imp_norm"]).mean())
    real_ex = float((pairs["real_norm"] - pairs["ctrl_real_norm"]).mean())
    ratio = imp_ex / real_ex if real_ex > 0 else float("nan")
    res = {
        "trial": trial, "family": label, "tenor": tenor, "lump_frac": lump_frac,
        "n": s1.n, "clusters": s1.clusters,
        "event_share30": tot.point, "event_lo": tot.low, "event_hi": tot.high,
        "surplus": s1.point, "surplus_lo": s1.low, "surplus_hi": s1.high,
        "cost_rt_share": cost,
        "net": s2.point, "net_lo": s2.low, "net_hi": s2.high,
        "implied_excess_var": imp_ex, "realised_excess_var": real_ex, "imp_over_real": ratio,
        "pass_S1": s1.low > 0, "pass_S2": s2.low > 0,
    }
    print(f"  {label} {tenor}d (trial {trial}): event {tot}; surplus {s1}; net {s2}; "
          f"implied/realised excess (share of 30d var) {imp_ex:+.4f}/{real_ex:+.4f} = {ratio:.2f}")
    return res


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_freeze() -> None:
    if not FREEZE.exists():
        raise SystemExit("held-out refused: freeze_n17.md does not exist")
    text = FREEZE.read_text(encoding="utf-8")
    m = re.search(r"event_scorer\.py SHA-256: ([0-9a-f]{64})", text)
    if m is None or m.group(1) != sha(Path(__file__)):
        raise SystemExit("held-out refused: scorer hash does not match the freeze note")
    print(f"  freeze verified: scorer {m.group(1)[:12]}..., note {sha(FREEZE)[:12]}...")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    args = ap.parse_args()
    if args.block == "heldout":
        check_freeze()
        lumps = json.loads(LUMP_FILE.read_text(encoding="utf-8"))
    else:
        lumps = {}
    costs = {30: cost_shares(COST_DTE), SHORT_TENOR: cost_shares(COST_DTE_SHORT)}
    results, all_pairs = [], []
    for fam, (etf, idx, kind) in FAMILIES.items():
        print(f"{fam}:")
        pairs = build_pairs(daily_panel(etf, idx), kind)
        if args.block == "discovery":
            pairs = pairs[pairs["date"] <= DISCOVERY_END]
        else:
            pairs = pairs[(pairs["date"] >= HELDOUT_START) & (pairs["date"] <= HELDOUT_END)]
        pairs = pairs.assign(family=fam)
        all_pairs.append(pairs)
        subsets = [(fam, pairs)]
        if kind == "macro":
            subsets += [(f"{etf}_{k}", pairs[pairs["kind"] == k]) for k in ["cpi", "nfp", "fomc"]]
        for label, sub in subsets:
            if args.block == "discovery":
                lumps[label] = lump_fractions(sub) if len(sub) else 0.0
            for tenor in (30, SHORT_TENOR):
                trials = TRIALS if tenor == 30 else TRIALS_SHORT
                results.append(score(sub, costs[tenor][etf], label, trials[label], tenor,
                                     lumps[label]))
    if args.block == "discovery":
        LUMP_FILE.write_text(json.dumps(lumps, indent=2), encoding="utf-8")
        print(f"wrote {LUMP_FILE.name}: {lumps}")
    tag = args.block
    pd.DataFrame(results).to_csv(HERE / f"results_{tag}.csv", index=False)
    pd.concat(all_pairs).to_csv(HERE / f"pairs_{tag}.csv", index=False)
    print(f"wrote results_{tag}.csv and pairs_{tag}.csv")


if __name__ == "__main__":
    main()
