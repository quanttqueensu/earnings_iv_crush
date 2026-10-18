"""
audit_oos_2026_attrition.py
Audit of outcome-dependent attrition in the 2025-2026 straddle ledger.

The ledger's chain parser keeps a contract only when both its bid and its ask are positive. After a
large announcement move the far out-of-the-money leg of the sold straddle often shows a zero bid
with a live ask, so the event is dropped as "exit leg unquoted". Those are the events where a short
straddle loses most, so the attrition flatters the book. This script re-marks every event with the
ledger's own rules except that a leg with a zero bid and a positive ask is kept at mid = ask / 2
(the ledger marks at mid and charges its cost model on top). It writes to its own output directory
and never touches the canonical ledger.

Usage:
    python research/frozen_selector/audit_oos_2026_attrition.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import research.frozen_selector.score_oos_2026 as led_mod  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402

OUT = Path("outputs/research/oos_2026_attrition_audit")
N_BOOT = 5000
SEED = 0


def _parse_lenient(df: pd.DataFrame) -> pd.DataFrame | None:
    """The ledger's parser, but a zero bid is allowed when the ask is positive."""
    if df is None or df.empty or "symbol" not in df.columns:
        return None
    d = df.copy()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d.dropna(subset=["strike", "expiry"])
    bid = pd.to_numeric(d.get("bid_px_00"), errors="coerce").fillna(0.0)
    ask = pd.to_numeric(d.get("ask_px_00"), errors="coerce")
    d["mid"] = (bid.clip(lower=0) + ask) / 2.0
    d["zero_bid"] = bid <= 0
    d = d[(ask > 0) & d["mid"].notna()]
    if d.empty:
        return None
    return d.sort_values("ts_recv").groupby(["strike", "expiry", "right"], as_index=False).last()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ev = led_mod._load_events()
    spots = led_mod._spot_table(
        sorted(ev["ticker"].unique()),
        ev["entry_date"].min().strftime("%Y-%m-%d"),
        ev["exit_date"].max().strftime("%Y-%m-%d"),
    )
    rows, reasons = [], {}
    for _, e in ev.iterrows():
        t = str(e["ticker"])
        s_in = led_mod._spot_at(spots, t, e["entry_date"])
        s_out = led_mod._spot_at(spots, t, e["exit_date"])
        ch_in = led_mod._cached(t, e["entry_date"])
        if s_in is None or s_out is None or ch_in is None:
            reasons["no spot or entry chain"] = reasons.get("no spot or entry chain", 0) + 1
            continue
        built = led_mod._straddle(ch_in, s_in)
        if built is None:
            reasons["entry unquoted"] = reasons.get("entry unquoted", 0) + 1
            continue
        straddle_in, implied_move, strike, expiry = built
        ch_out = led_mod._cached(t, e["exit_date"])
        strict = led_mod._mark(ch_out, strike, expiry) if ch_out is not None else None
        lenient_d = _parse_lenient(ch_out) if ch_out is not None else None
        lenient, zero_bid = None, False
        if lenient_d is not None:
            leg = lenient_d[(lenient_d["strike"] == strike) & (lenient_d["expiry"] == expiry)]
            c, p = leg[leg["right"] == "C"], leg[leg["right"] == "P"]
            if len(c) and len(p):
                lenient = float(c["mid"].iloc[0] + p["mid"].iloc[0])
                zero_bid = bool(c["zero_bid"].iloc[0] or p["zero_bid"].iloc[0])
        if lenient is None:
            reasons["exit leg absent even with zero bids allowed"] = (
                reasons.get("exit leg absent even with zero bids allowed", 0) + 1
            )
            continue
        credit = straddle_in * led_mod.CONTRACT_MULTIPLIER
        margin = led_mod.regt_straddle_margin(s_in, strike, straddle_in, 1)
        cost = led_mod.COST * credit
        exit_value = lenient * led_mod.CONTRACT_MULTIPLIER
        rows.append(
            {
                "ticker": t,
                "entry_date": e["entry_date"],
                "in_strict_ledger": strict is not None,
                "zero_bid_leg": zero_bid,
                "realised_over_implied": abs(s_out / s_in - 1.0) / implied_move,
                "net_rom": (credit - exit_value - cost) / margin,
            }
        )
    d = pd.DataFrame(rows)
    print("  drops: " + ", ".join(f"{k}={v}" for k, v in reasons.items()))
    out: dict[str, object] = {"drops": reasons}
    for label, sub in (
        ("strict (ledger rule)", d[d["in_strict_ledger"]]),
        ("recovered by allowing zero bids", d[~d["in_strict_ledger"]]),
        ("all marked", d),
    ):
        x = sub["net_rom"]
        sh = x.mean() / x.std(ddof=1)
        lo, hi = cluster_bootstrap_ci(
            x.to_numpy(),
            sub["entry_date"].astype(str).to_numpy(),
            lambda v: float(np.mean(v) / np.std(v, ddof=1)),
            n_boot=N_BOOT,
            seed=SEED,
        )
        out[label] = {
            "n": len(sub),
            "mean_net_rom": float(x.mean()),
            "per_trade_sharpe": float(sh),
            "sharpe_ci": [float(lo), float(hi)],
            "mean_realised_over_implied": float(sub["realised_over_implied"].mean()),
            "share_zero_bid_leg": float(sub["zero_bid_leg"].mean()),
        }
    d.to_csv(OUT / "events.csv", index=False)
    print(json.dumps(out, indent=1, default=str))
    json.dump(out, open(OUT / "summary.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
