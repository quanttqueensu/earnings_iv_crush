"""
build_broad_history_events.py
Build features and outcomes for the 2013-2024 broad-universe earnings events from the 15:59 chains.

Features come from ``build_execution_events`` fed the cached 15:59 chain (IV inverted from quote
mids, ``research_ml_zoo_1559.fetch_chain_1559``), the same path as the rebuilt 2025-2026 features.
Outcomes are the short at-the-money straddle marked from the same cached chains exactly as
``audit_oos_2026_attrition.py`` does (ledger strike and expiry rules, zero-bid exit legs at ask / 2,
11.6%-of-premium round-trip cost, Reg-T margin). Events missing either chain are dropped and counted.

Usage:
    python scripts/build/build_broad_history_events.py [--limit N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import research.frozen_selector.score_oos_2026 as led_mod  # noqa: E402
from earnings_iv_crush.data.real_events import build_execution_events  # noqa: E402
from research.frozen_selector.audit_oos_2026_attrition import _parse_lenient  # noqa: E402
from research.selection.research_ml_zoo_1559 import fetch_chain_1559  # noqa: E402
from scripts.build.build_broad_oos_2025 import _fetch_prices  # noqa: E402

CALENDAR = Path("outputs/research/calendar_broad_2013_2024.parquet")
OUT = Path("outputs/research/ml_zoo/broad_history_events.parquet")


def outcome(e: pd.Series) -> dict | str:
    t = str(e["ticker"])
    ch_in, ch_out = led_mod._cached(t, e["entry_date"]), led_mod._cached(t, e["exit_date"])
    if ch_in is None or ch_out is None or ch_in.empty or ch_out.empty:
        return "no_chain"
    s_in, s_out = float(e["spot_entry"]), float(e["spot_exit"])
    built = led_mod._straddle(ch_in, s_in)
    if built is None:
        return "entry_unquoted"
    straddle_in, implied_move, strike, expiry = built
    d = _parse_lenient(ch_out)
    leg = None if d is None else d[(d["strike"] == strike) & (d["expiry"] == expiry)]
    if leg is None or not {"C", "P"} <= set(leg["right"]):
        return "exit_leg_absent"
    exit_v = float(
        leg.loc[leg["right"] == "C", "mid"].iloc[0] + leg.loc[leg["right"] == "P", "mid"].iloc[0]
    )
    credit = straddle_in * led_mod.CONTRACT_MULTIPLIER
    margin = led_mod.regt_straddle_margin(s_in, strike, straddle_in, 1)
    cost = led_mod.COST * credit
    return {
        "rom": (credit - exit_v * led_mod.CONTRACT_MULTIPLIER - cost) / margin,
        "implied_move_mark": implied_move,
        "realised_over_implied_mark": abs(s_out / s_in - 1.0) / implied_move,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--limit", type=int, default=0, help="first N names only (smoke test)")
    ap.add_argument("--shard", type=str, default="", help="i/n: process every n-th name from i")
    a = ap.parse_args()
    cal = pd.read_parquet(CALENDAR)
    cal = cal[(cal["session_source"] == "ibes_time") & cal["session"].isin(["amc", "bmo"])]
    cal["announce_date"] = pd.to_datetime(cal["announce_date"])
    names = sorted(cal["ticker"].unique())
    if a.limit:
        names = names[: a.limit]
    out_path = OUT
    if a.shard:
        i, n = (int(v) for v in a.shard.split("/"))
        names = names[i::n]
        out_path = OUT.with_name(f"{OUT.stem}_shard{i}of{n}.parquet")
    parts, funnel = [], {"events": int(cal["ticker"].isin(names).sum())}
    for i, t in enumerate(names, start=1):
        sub = cal[cal["ticker"] == t][["ticker", "announce_date", "session"]]
        try:
            ev = build_execution_events(
                sub, fetch_chain=fetch_chain_1559, fetch_prices=_fetch_prices
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {t}: feature build failed ({type(exc).__name__})", flush=True)
            continue
        if ev.empty:
            continue
        rows = []
        for _, e in ev.iterrows():
            o = outcome(e)
            if isinstance(o, str):
                funnel[o] = funnel.get(o, 0) + 1
                continue
            rows.append({**e.to_dict(), **o})
        if rows:
            parts.append(pd.DataFrame(rows))
        if i % 25 == 0:
            print(f"  {i}/{len(names)} names, {sum(len(p) for p in parts)} events", flush=True)
    out = pd.concat(parts, ignore_index=True)
    funnel["with_features_and_outcome"] = len(out)
    print("  funnel: " + ", ".join(f"{k}={v}" for k, v in funnel.items()), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    print(f"  wrote {len(out)} events -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
