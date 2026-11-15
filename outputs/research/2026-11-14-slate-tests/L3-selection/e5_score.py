"""e5_score.py: trials 2,954 (FES against SPY) and 2,955 (FNQ against QQQ).

For each daily ForecastEx index contract dated d, the last pair in [14:59, 15:59] ET on the
session before d is set against the digital implied by the cached 15:59 ETF chain for the expiry
dated d, aligned on the contract ladder's own median (diagnosis.log section 6). The rule buys the
side whose model value exceeds its cost by more than the margin; P&L is the USD 1 payout minus the
cost. Blocks follow amendment E5-A2: discovery is contracts dated 2025-04-21 to 2026-03-31,
held-out 2026-04-01 to 2026-10-30. The held-out block is read only if ``freeze_e5.md`` exists and records
this file's hash.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/e5_score.py --block disc
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    log_block_view,
    matched_random_null,
    sha256_file,
)

CHAINS = lib.ROOT / "data" / "cache" / "index_chains"
DATA = HERE / "e5_data"
PRODUCTS = {"FES": ("SPY", 2954), "FNQ": ("QQQ", 2955)}
FEE = 0.01  # USD per contract, ForecastEx exchange fee (IB commission zero)
MARGIN = 0.02  # model value must exceed cost by this much (interpolation error of the digital)
WINDOW = ("12:00", "15:59")  # ET window on d-1; amendment E5-A1 widened it from 14:59 (thin book)
MIN_DAYS = 30  # contract dates with a priced ladder needed before a block is scored (E5-A1)
HELDOUT_LAST = pd.Timestamp("2026-10-30")  # last cached chain
# E5-A2: split moved on liquidity counts alone (2025 had too few priced ladders)
SPLIT = pd.Timestamp("2026-04-01")
ET = "America/New_York"


# ── ForecastEx ───────────────────────────────────────────────────────────────


def load_pairs() -> pd.DataFrame:
    p = pd.concat([pd.read_parquet(f) for f in sorted((DATA / "pairs").glob("*.parquet"))])
    parts = p["event_contract"].str.split("_", expand=True)
    p["prod"], p["k"] = parts[0], pd.to_numeric(parts[2], errors="coerce")
    p["d"] = pd.to_datetime(parts[1], format="%m%d%y", errors="coerce")
    # fractions of a second come in varying lengths; seconds are precise enough here
    ts = p["pair_time"].str.replace(r"\.\d+", "", regex=True)
    p["t"] = pd.to_datetime(ts, utc=True, format="%Y-%m-%dT%H:%M:%S%z").dt.tz_convert(ET)
    for c in ("yes_price", "no_price"):
        p[c] = pd.to_numeric(p[c], errors="coerce")
    return p.dropna(subset=["k", "d", "yes_price", "no_price"])


def load_outcomes() -> pd.Series:
    r = pd.concat([pd.read_parquet(f) for f in sorted((DATA / "prices").glob("*.parquet"))])
    r["settlement_price"] = pd.to_numeric(r["settlement_price"], errors="coerce")
    # the YES row on the expiration date carries the resolved value; earlier rows are daily marks
    exp_day = pd.to_datetime(r["expiration_date"].str[:10])
    r = r[(r["subtype"] == "YES") & (pd.to_datetime(r["date"]) == exp_day)]
    r = r.dropna(subset=["settlement_price"])
    bad = ~r["settlement_price"].isin([0.0, 1.0])
    if bad.any():
        print(f"warning: {int(bad.sum())} expiration-day YES rows not 0 or 1; dropped")
    r = r[~bad]
    return r.groupby("event_contract")["settlement_price"].last()


# ── option-implied digital ──────────────────────────────────────────────────


def digital_curve(etf: str, day: pd.Timestamp, expiry: pd.Timestamp) -> tuple[np.ndarray, ...]:
    """(x = ln(K/F), D(x)) at 15:59 on ``day`` for ``expiry``; empty arrays if unavailable."""
    f = CHAINS / f"{etf}_{day:%Y-%m-%d}_1559.parquet"
    if not f.exists():
        return np.array([]), np.array([])
    c = pd.read_parquet(f, columns=["symbol", "bid_px_00", "ask_px_00"])
    s = c["symbol"].str[-15:]
    c = c.assign(
        exp=pd.to_datetime("20" + s.str[:6], format="%Y%m%d"),
        cp=s.str[6],
        k=s.str[7:].astype(float) / 1000.0,
    )
    c = c[(c["exp"] == expiry) & (c["bid_px_00"] > 0) & (c["ask_px_00"] >= c["bid_px_00"])]
    c = c.assign(mid=(c["bid_px_00"] + c["ask_px_00"]) / 2.0)
    w = c.pivot_table(index="k", columns="cp", values="mid", aggfunc="first").sort_index()
    if not {"C", "P"} <= set(w.columns):
        return np.array([]), np.array([])
    both = w.dropna()
    if len(both) < 3:
        return np.array([]), np.array([])
    fk = both.index.to_numpy() + both["C"].to_numpy() - both["P"].to_numpy()
    near = np.argsort(np.abs(both.index.to_numpy() - np.median(fk)))[:3]
    fwd = float(np.median(fk[near]))
    xs, ds = [], []
    for side in ("C", "P"):
        leg = w[side].dropna()
        k, v = leg.index.to_numpy(), leg.to_numpy()
        for i in range(len(k) - 1):
            km = 0.5 * (k[i] + k[i + 1])
            slope = (v[i] - v[i + 1]) / (k[i + 1] - k[i])
            if side == "C" and km > fwd:
                xs.append(np.log(km / fwd))
                ds.append(slope)
            elif side == "P" and km <= fwd:
                xs.append(np.log(km / fwd))
                ds.append(1.0 + slope)
    if len(xs) < 4:
        return np.array([]), np.array([])
    o = np.argsort(xs)
    x, d = np.asarray(xs)[o], np.clip(np.asarray(ds)[o], 0.0, 1.0)
    d = np.minimum.accumulate(d)  # a digital cannot rise with the strike
    return x, d


def _cross(x: np.ndarray, y: np.ndarray, level: float = 0.5) -> float:
    """First x where decreasing y crosses ``level`` by linear interpolation; nan if none."""
    for i in range(len(x) - 1):
        if y[i] >= level >= y[i + 1] and y[i] != y[i + 1]:
            return float(x[i] + (y[i] - level) * (x[i + 1] - x[i]) / (y[i] - y[i + 1]))
    return float("nan")


# ── build ────────────────────────────────────────────────────────────────────


def build(prod: str) -> tuple[pd.DataFrame, dict[str, int]]:
    etf = PRODUCTS[prod][0]
    p = load_pairs()
    p = p[p["prod"] == prod]
    out = load_outcomes()
    sessions = sorted(
        {pd.Timestamp(f.name.split("_")[1]) for f in CHAINS.glob(f"{etf}_*_1559.parquet")}
    )
    sess = pd.DatetimeIndex(sessions)
    funnel: dict[str, int] = {
        "contract_days": 0,
        "no_prior_session": 0,
        "no_ladder_cross": 0,
        "no_digital": 0,
        "contracts_priced": 0,
        "contracts_outside_curve": 0,
        "contracts_no_outcome": 0,
        "contracts_scored": 0,
    }
    rows = []
    for d, g in p.groupby("d"):
        funnel["contract_days"] += 1
        prev = sess[sess < d]
        if prev.empty or (d - prev[-1]).days > 4:
            funnel["no_prior_session"] += 1
            continue
        day = prev[-1]
        lo = pd.Timestamp(f"{day:%Y-%m-%d} {WINDOW[0]}").tz_localize(ET)
        hi = pd.Timestamp(f"{day:%Y-%m-%d} {WINDOW[1]}").tz_localize(ET)
        w = g[(g["t"] >= lo) & (g["t"] <= hi)].sort_values("t")
        last = w.groupby("k").tail(1).set_index("k").sort_index()
        if len(last) < 2:
            funnel["no_ladder_cross"] += 1
            continue
        px = 0.5 * (last["yes_price"] + 1.0 - last["no_price"])
        m = _cross(np.log(last.index.to_numpy(float)), px.to_numpy(float))
        if not np.isfinite(m):
            funnel["no_ladder_cross"] += 1
            continue
        x, dd = digital_curve(etf, day, d)
        if x.size == 0:
            funnel["no_digital"] += 1
            continue
        x0 = _cross(x, dd)
        if not np.isfinite(x0):
            funnel["no_digital"] += 1
            continue
        for k, r in last.iterrows():
            funnel["contracts_priced"] += 1
            xk = np.log(float(k)) - m + x0
            if not (x[0] <= xk <= x[-1]):
                funnel["contracts_outside_curve"] += 1
                continue
            ec = r["event_contract"]
            if ec not in out.index:
                funnel["contracts_no_outcome"] += 1
                continue
            funnel["contracts_scored"] += 1
            rows.append(
                {
                    "prod": prod,
                    "d": d,
                    "obs_day": day,
                    "k": float(k),
                    "event_contract": ec,
                    "yes": float(r["yes_price"]),
                    "no": float(r["no_price"]),
                    "q": float(np.interp(xk, x, dd)),
                    "y": float(out[ec]),
                    "dist": float(xk - x0),
                }
            )
    return pd.DataFrame(rows), funnel


def rule(e: pd.DataFrame) -> pd.DataFrame:
    e = e.copy()
    e["cost_yes"] = np.maximum(e["yes"], 1.0 - e["no"]) + FEE
    e["cost_no"] = np.maximum(e["no"], 1.0 - e["yes"]) + FEE
    e["edge_yes"], e["edge_no"] = e["q"] - e["cost_yes"], (1.0 - e["q"]) - e["cost_no"]
    e["side"] = np.where(e["edge_yes"] > MARGIN, "yes", np.where(e["edge_no"] > MARGIN, "no", ""))
    e["pnl"] = np.where(
        e["side"] == "yes",
        e["y"] - e["cost_yes"],
        np.where(e["side"] == "no", (1.0 - e["y"]) - e["cost_no"], np.nan),
    )
    rng = np.random.default_rng(0)
    coin = rng.random(len(e)) < 0.5
    e["pnl_random_side"] = np.where(coin, e["y"] - e["cost_yes"], (1.0 - e["y"]) - e["cost_no"])
    return e


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True, choices=["disc", "held"])
    a = ap.parse_args(argv)
    if a.block == "held":
        note = HERE / "freeze_e5.md"
        if not (note.exists() and sha256_file(Path(__file__)) in note.read_text(encoding="utf-8")):
            raise SystemExit("held-out read refused: no freeze note recording this scorer's hash")
    if not (DATA / "DONE").exists():
        raise SystemExit("e5_fetch.py has not completed")
    res: dict = {}
    for prod, (etf, trial) in PRODUCTS.items():
        e, funnel = build(prod)
        inb = e["d"] < SPLIT if a.block == "disc" else e["d"] >= SPLIT
        e = e[inb & (e["d"] <= HELDOUT_LAST)]
        n_days = int(e["d"].nunique())
        if n_days < MIN_DAYS:
            res[prod] = {
                "trial": trial,
                "etf": etf,
                "funnel_all_years": funnel,
                "days_in_block": n_days,
                "verdict": "underpowered: fewer than "
                f"{MIN_DAYS} contract dates with a priced ladder; no P&L computed",
            }
            print(prod, json.dumps(res[prod], indent=1, default=float))
            continue
        e = rule(e)
        t = e[e["side"] != ""]
        r: dict = {
            "trial": trial,
            "etf": etf,
            "funnel_all_years": funnel,
            "contracts_in_block": int(len(e)),
            "days_in_block": int(e["d"].nunique()),
            "trades": int(len(t)),
            "trade_days": int(t["d"].nunique()),
            "yes_trades": int((t["side"] == "yes").sum()),
        }
        # calibration descriptive: ForecastEx price and model value against the outcome
        px = 0.5 * (e["yes"] + 1 - e["no"])
        r["brier_forecastex"] = float(((px - e["y"]) ** 2).mean()) if len(e) else None
        r["brier_model"] = float(((e["q"] - e["y"]) ** 2).mean()) if len(e) else None
        r["mean_price_minus_model"] = float((px - e["q"]).mean()) if len(e) else None
        if len(t) >= 2:
            ci = date_clustered_ci(t["pnl"], t["d"], np.mean)
            r["pnl_mean"], r["pnl_lo"], r["pnl_hi"] = ci.point, ci.low, ci.high
            r["clusters"] = ci.clusters
            # null: the same number of contracts from the block, each with a random side; the
            # observed statistic is the rule's own P&L (matched_random_null would score the
            # random-side P&L of the selected contracts instead)
            nul = matched_random_null(
                e["pnl_random_side"].to_numpy(float), (e["side"] != "").to_numpy(), stat=np.mean
            )
            r["null_pct_vs_random_contracts_random_side"] = float(
                100.0 * (nul.null[np.isfinite(nul.null)] < r["pnl_mean"]).mean()
            )
            r["null_median"] = float(np.nanmedian(nul.null))
            r["passes"] = bool(ci.low > 0 and nul.percentile >= 95)
            by = []
            for lab, g in t.groupby(pd.cut(t["dist"].abs(), [0, 0.0025, 0.005, 0.01, 1.0])):
                if len(g):
                    by.append(
                        {
                            "abs_dist": str(lab),
                            "n": int(len(g)),
                            "pnl_mean": float(g["pnl"].mean()),
                            "yes_share": float((g["side"] == "yes").mean()),
                        }
                    )
            r["pnl_by_distance"] = by
        res[prod] = r
        print(prod, json.dumps(r, indent=1, default=float))
        e.to_parquet(HERE / f"e5_events_{prod}_{a.block}.parquet")
    (HERE / f"e5_results_{a.block}.json").write_text(
        json.dumps(res, indent=2, default=float), encoding="utf-8"
    )
    log_block_view(
        lib.LANE_VIEWS,
        panel="forecastex_index_contracts",
        period=a.block,
        outcome_family="event_contract_vs_option_digital",
        feature_family="ladder_shape",
        viewed_by="L3 e5_score.py trials 2,954-2,955",
    )


if __name__ == "__main__":
    main()
