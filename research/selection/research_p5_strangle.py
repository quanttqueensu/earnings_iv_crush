"""
research_p5_strangle.py
Pre-registered test P5: short strangle at plus or minus one implied move against the straddle.

``research/selection/preregs/p5_strangle_prereg.md`` with amendment 01. Both structures are sold at the 15:59 ET
entry bids and bought back at the 15:59 exit asks on the same chains, so the comparison carries no
cost-convention asymmetry.

Usage:
    python research/selection/research_p5_strangle.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from research.selection.research_p1_skew_reaction import parity_forward, usable  # noqa: E402

PREREG = Path("research/selection/preregs/p5_strangle_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_p5_strangle.json")
LEDGER = Path("outputs/research/oos_2026_ledger.csv")
CHAINS = Path("data/cache/backfill_chains")
OUT = Path("outputs/research/p5_strangle")
COMMISSION = 0.65
N_BOOT = 5000
SEED = 0
N_TRIALS = 1505


def _check_prereg() -> None:
    want = json.loads(PREREG_JSON.read_text())["prereg_sha256"]
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != want:
        raise SystemExit("pre-registration hash mismatch")


def _book(ch: pd.DataFrame, expiry: pd.Timestamp) -> pd.DataFrame:
    """Usable quotes for one expiry, indexed by (right, strike)."""
    u = usable(ch[ch["expiry"] == expiry])
    return u.groupby(["right", "strike"])[["bid_px_00", "ask_px_00", "mid"]].last()


def _naked(prem: float, otm: float, s: float) -> float:
    return prem + max(0.20 * s - otm, 0.10 * s)


def build() -> pd.DataFrame:
    from earnings_iv_crush.research.chains import _parse_chain

    led = pd.read_csv(LEDGER, parse_dates=["entry_date", "exit_date", "expiry"])
    f: dict[str, int] = {"ledger": len(led)}
    rows = []
    for _, e in led.iterrows():
        pe = CHAINS / f"{e['ticker']}_{e['entry_date'].date()}.parquet"
        px = CHAINS / f"{e['ticker']}_{e['exit_date'].date()}.parquet"
        if not (pe.exists() and px.exists()):
            f["no_chain"] = f.get("no_chain", 0) + 1
            continue
        ce, cx = _parse_chain(pd.read_parquet(pe)), _parse_chain(pd.read_parquet(px))
        if ce is None or cx is None:
            f["empty_chain"] = f.get("empty_chain", 0) + 1
            continue
        a, b = _book(ce, e["expiry"]), _book(cx, e["expiry"])
        if "C" not in a.index.get_level_values(0) or "P" not in a.index.get_level_values(0):
            f["no_book"] = f.get("no_book", 0) + 1
            continue
        fwd = parity_forward(a.loc["C", "mid"], a.loc["P", "mid"])
        m = float(e["implied_move"])
        calls = [k for k in a.loc["C"].index if k >= fwd * (1 + m)]
        puts = [k for k in a.loc["P"].index if k <= fwd * (1 - m)]
        if not np.isfinite(fwd) or not calls or not puts:
            f["no_wing_strike"] = f.get("no_wing_strike", 0) + 1
            continue
        kc, kp = min(calls), max(puts)
        k0 = float(e["strike"])
        need = [("C", kc), ("P", kp), ("C", k0), ("P", k0)]
        if any(x not in a.index or x not in b.index for x in need):
            f["leg_missing"] = f.get("leg_missing", 0) + 1
            continue

        def trade(
            legs: list[tuple[str, float]], a: pd.DataFrame = a, b: pd.DataFrame = b
        ) -> dict[str, float]:
            credit = sum(float(a.loc[x, "bid_px_00"]) for x in legs) * 100
            cost = sum(float(b.loc[x, "ask_px_00"]) for x in legs) * 100
            mid0 = sum(float(a.loc[x, "mid"]) for x in legs) * 100
            mid1 = sum(float(b.loc[x, "mid"]) for x in legs) * 100
            return {"credit": credit, "cost": cost, "mid0": mid0, "mid1": mid1}

        st, sd = trade([("C", kc), ("P", kp)]), trade([("C", k0), ("P", k0)])
        cprem, pprem = float(a.loc[("C", kc), "bid_px_00"]), float(a.loc[("P", kp), "bid_px_00"])
        req_c = _naked(cprem, max(kc - fwd, 0.0), fwd)
        req_p = _naked(pprem, max(fwd - kp, 0.0), fwd)
        margin_st = (max(req_c + pprem, req_p + cprem)) * 100
        margin_sd = (0.20 * fwd) * 100 + sd["credit"]
        fees = 4 * COMMISSION
        rows.append(
            {
                "ticker": e["ticker"],
                "entry_date": e["entry_date"],
                "implied_move": m,
                "kc": kc,
                "kp": kp,
                "k0": k0,
                "rom_st": (st["credit"] - st["cost"] - fees) / margin_st,
                "rom_sd": (sd["credit"] - sd["cost"] - fees) / margin_sd,
                "rom_st_mid": (st["mid0"] - st["mid1"]) / margin_st,
                "rom_sd_mid": (sd["mid0"] - sd["mid1"]) / margin_sd,
                "hs_st": 1 - st["credit"] / st["mid0"],
                "hs_sd": 1 - sd["credit"] / sd["mid0"],
                "ledger_net_rom": float(e["net_rom"]),
            }
        )
    d = pd.DataFrame(rows)
    f["scored"] = len(d)
    print("  funnel: " + ", ".join(f"{k}={v}" for k, v in f.items()), flush=True)
    if d.empty:
        raise SystemExit("no strangle priced")
    return d


def _ci(x: pd.Series, keys: pd.Series) -> list[float]:
    lo, hi = cluster_bootstrap_ci(
        x.to_numpy(), keys.astype(str).to_numpy(), np.mean, n_boot=N_BOOT, seed=SEED
    )
    return [float(lo), float(hi)]


def score() -> None:
    _check_prereg()
    OUT.mkdir(parents=True, exist_ok=True)
    d = build()
    d.to_csv(OUT / "trades.csv", index=False)
    k = d["entry_date"]
    diff = d["rom_st"] - d["rom_sd"]
    res: dict[str, Any] = {
        "n": len(d),
        "n_dates": int(k.nunique()),
        "strangle_mean": float(d["rom_st"].mean()),
        "strangle_ci": _ci(d["rom_st"], k),
        "straddle_touch_mean": float(d["rom_sd"].mean()),
        "straddle_touch_ci": _ci(d["rom_sd"], k),
        "paired_mean": float(diff.mean()),
        "paired_ci": _ci(diff, k),
        "strangle_sharpe": float(d["rom_st"].mean() / d["rom_st"].std(ddof=1)),
        "dsr": float(deflated_sharpe_ratio(d["rom_st"], n_trials=N_TRIALS)),
        "strangle_mid_mean": float(d["rom_st_mid"].mean()),
        "straddle_mid_mean": float(d["rom_sd_mid"].mean()),
        "half_spread_share_strangle": float(d["hs_st"].mean()),
        "half_spread_share_straddle": float(d["hs_sd"].mean()),
        "paired_vs_ledger_mean": float((d["rom_st"] - d["ledger_net_rom"]).mean()),
        "paired_vs_ledger_ci": _ci(d["rom_st"] - d["ledger_net_rom"], k),
    }
    res["pass_i"] = res["strangle_ci"][0] > 0
    res["pass_ii"] = res["paired_ci"][0] > 0
    res["verdict"] = "PASS" if res["pass_i"] and res["pass_ii"] else "FAIL"
    d["im_tercile"] = pd.qcut(d["implied_move"], 3, labels=["low", "mid", "high"])
    res["by_im_tercile"] = (
        d.groupby("im_tercile", observed=True)[["rom_st", "rom_sd"]].mean().round(4).to_dict()
    )
    res["worst10"] = d.nsmallest(10, "rom_st")[["ticker", "entry_date", "rom_st"]].astype(str)
    res["worst10"] = res["worst10"].values.tolist()
    print(json.dumps(res, indent=1, default=str))
    json.dump(res, open(OUT / "summary.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    score()
