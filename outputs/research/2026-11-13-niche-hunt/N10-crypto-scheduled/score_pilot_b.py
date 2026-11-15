"""
score_pilot_b.py
Pilot B of lane N10: the 23-hour BTC short ATM straddle into a Deribit monthly expiry (last
Friday of the month) against the same trade into the ordinary Fridays 1, 2 and 3 weeks earlier.
Pre-registered in diagnosis.log before any outcome.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/score_pilot_b.py \
        --block discovery --trial 2352
    options: --quarterly  --exclude-macro  --max-stale 60  --entry-hour 9
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from n10lib import HERE, ROOT, delivery_prices, mean_ci, straddle

BLOCKS = {
    "discovery": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2022-12-31", tz="UTC")),
    "heldout": (pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2026-10-31", tz="UTC")),
}
CONTROL_WEEKS = (1, 2, 3)
EXPIRY_HOUR = 8
MACRO = ROOT / "data" / "cache" / "deribit" / "releases.csv"


def last_fridays(lo: pd.Timestamp, hi: pd.Timestamp) -> list[pd.Timestamp]:
    fr = pd.date_range(lo, hi, freq="W-FRI")
    s = pd.Series(fr, index=fr)
    return list(s.groupby([s.index.year, s.index.month]).max())


def build(block: str, quarterly: bool, max_stale: float | None, entry_hour: int) -> pd.DataFrame:
    lo, hi = BLOCKS[block]
    deliv = delivery_prices("btc_usd")
    macro = pd.read_csv(MACRO, parse_dates=["close_time"])["close_time"] if MACRO.exists() else None
    fridays = last_fridays(lo, hi)
    if quarterly:
        fridays = [f for f in fridays if f.month in (3, 6, 9, 12)]
    funnel = {"events": len(fridays), "event ok": 0, "paired": 0}
    reasons: dict[str, int] = {}
    rows = []
    for f in fridays:
        exp = f + pd.Timedelta(hours=EXPIRY_HOUR)

        def leg(fri_exp: pd.Timestamp) -> dict | None:
            entry = fri_exp - pd.Timedelta(days=1) + pd.Timedelta(hours=entry_hour - EXPIRY_HOUR)
            r, why = straddle("BTC", entry, deliv, expiry=fri_exp, max_stale_min=max_stale)
            if r is None:
                reasons[why] = reasons.get(why, 0) + 1
                return None
            r["entry"] = entry
            if macro is not None:
                r["macro_in_window"] = bool(((macro > entry) & (macro <= fri_exp)).any())
            return r

        ev = leg(exp)
        if ev is None:
            continue
        funnel["event ok"] += 1
        cts = [leg(exp - pd.Timedelta(weeks=w)) for w in CONTROL_WEEKS]
        cts = [c for c in cts if c is not None]
        if not cts:
            reasons["no control"] = reasons.get("no control", 0) + 1
            continue
        funnel["paired"] += 1
        rows.append(
            {
                "event_date": f.date(),
                **{f"ev_{k}": v for k, v in ev.items()},
                "ct_n": len(cts),
                "ct_ret_notional": float(np.mean([c["ret_notional"] for c in cts])),
                "ct_ret_premium": float(np.mean([c["ret_premium"] for c in cts])),
                "ct_ret_mid_gross": float(np.mean([c["ret_mid_gross"] for c in cts])),
                "ct_implied_var": float(np.mean([c["implied_var"] for c in cts])),
                "ct_realised_var": float(np.mean([c["realised_var"] for c in cts])),
                "ct_abs_move": float(np.mean([c["abs_move"] for c in cts])),
                "ct_z": float(np.mean([c["abs_move"] / np.sqrt(c["implied_var"]) for c in cts])),
                "ct_premium_mark_share": float(
                    np.mean([c["premium_mark"] / c["index"] for c in cts])
                ),
                "ct_macro": any(c.get("macro_in_window", False) for c in cts),
            }
        )
    print(f"  funnel {block}: {funnel}; drops (any leg): {reasons}")
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pilot B scorer")
    ap.add_argument("--block", choices=list(BLOCKS), required=True)
    ap.add_argument("--trial", type=int, required=True)
    ap.add_argument("--quarterly", action="store_true")
    ap.add_argument("--exclude-macro", action="store_true")
    ap.add_argument("--max-stale", type=float, default=None)
    ap.add_argument("--entry-hour", type=int, default=9)
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--stat",
        choices=["notional", "premium", "z"],
        default="notional",
        help="statistic for the verdict and trials row (pre-registered: notional)",
    )
    args = ap.parse_args()

    d = build(args.block, args.quarterly, args.max_stale, args.entry_hour)
    if len(d) < 8:
        raise SystemExit(f"{len(d)} pairs: too few to score")
    if args.exclude_macro:
        n0 = len(d)
        d = d[~(d["ev_macro_in_window"] | d["ct_macro"])]
        print(f"  macro exclusion: {n0} -> {len(d)} pairs")
    d["pair"] = d["ev_ret_notional"] - d["ct_ret_notional"]
    d["pair_prem"] = d["ev_ret_premium"] - d["ct_ret_premium"]
    d["mech"] = (d["ev_implied_var"] - d["ct_implied_var"]) - (
        d["ev_realised_var"] - d["ct_realised_var"]
    )
    d["impl_diff"] = d["ev_implied_var"] - d["ct_implied_var"]
    d["real_diff"] = d["ev_realised_var"] - d["ct_realised_var"]
    # move in units of the straddle-implied standard deviation; pinning predicts event < control
    d["ev_z"] = d["ev_abs_move"] / np.sqrt(d["ev_implied_var"])
    d["z_diff"] = d["ev_z"] - d["ct_z"]
    dates = pd.to_datetime(d["event_date"]).to_numpy()
    out: dict[str, object] = {"trial": args.trial, "block": args.block, "n_pairs": len(d)}
    for name, col in [
        ("pair_notional", "pair"),
        ("pair_premium", "pair_prem"),
        ("event_ret_notional", "ev_ret_notional"),
        ("control_ret_notional", "ct_ret_notional"),
        ("event_ret_premium", "ev_ret_premium"),
        ("event_mid_gross", "ev_ret_mid_gross"),
        ("mech", "mech"),
        ("implied_var_diff", "impl_diff"),
        ("realised_var_diff", "real_diff"),
        ("z_diff", "z_diff"),
    ]:
        p, lo, hi, n = mean_ci(d[col].to_numpy(), dates)
        out[name] = p
        out[f"{name}_lo"] = lo
        out[f"{name}_hi"] = hi
        print(f"  {name:22s} {p:+.5f}  [{lo:+.5f}, {hi:+.5f}]  N={n}")
    out["median_seller_discount"] = float(d["ev_seller_discount"].median())
    out["median_premium_share_event"] = float((d["ev_premium_mark"] / d["ev_index"]).median())
    out["median_stale_min"] = float(d["ev_stale_min"].median())
    out["event_hit"] = float((d["ev_ret_notional"] > 0).mean())
    print(
        f"  median seller discount {out['median_seller_discount']:.4f}, event premium/notional "
        f"{out['median_premium_share_event']:.5f}, stale {out['median_stale_min']:.0f} min, "
        f"hit {out['event_hit']:.3f}"
    )
    key = {"notional": "pair_notional", "premium": "pair_premium", "z": "z_diff"}[args.stat]
    lo_, hi_ = float(out[f"{key}_lo"]), float(out[f"{key}_hi"])  # type: ignore[arg-type]
    if args.stat == "z":  # a lower normalised move on the event favours the short
        lo_, hi_ = -hi_, -lo_
    verdict = "PASS short" if lo_ > 0 else ("PASS long" if hi_ < 0 else "FAIL")
    print(f"  PRIMARY ({args.block}): {verdict}")
    tag = (
        f"{args.block}{'_q' if args.quarterly else ''}{'_nomacro' if args.exclude_macro else ''}"
        f"{'_stale' + str(int(args.max_stale)) if args.max_stale else ''}_h{args.entry_hour}"
    )
    stat_txt = {
        "notional": "mean paired net return on notional, event minus control, at est. touch",
        "premium": "mean paired net return on premium, event minus control, at est. touch",
        "z": "mean |move| in implied sd, event minus control (negative favours the short)",
    }[args.stat]
    d.to_csv(HERE / f"pilot_b_pairs_{tag}.csv", index=False)
    row = {
        "trial": args.trial,
        "lane": "N10",
        "pilot": "B monthly expiry",
        "config": tag,
        "block": args.block,
        "n": len(d),
        "statistic": stat_txt,
        "point": round(float(out[key]), 6),  # type: ignore[arg-type]
        "ci_low": round(float(out[f"{key}_lo"]), 6),  # type: ignore[arg-type]
        "ci_high": round(float(out[f"{key}_hi"]), 6),  # type: ignore[arg-type]
        "verdict": verdict,
        "note": args.note,
        "scored_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    }
    f = HERE / "trials.csv"
    new = not f.exists()
    with f.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


if __name__ == "__main__":
    main()
