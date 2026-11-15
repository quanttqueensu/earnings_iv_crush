"""multisignal.py: H1 with every qualifying print as a signal (trial 2,386), next-print fills.

For each H1 contract, each ForecastEx print in (R - 24 h, R - 1 h] is a candidate signal; the
Kalshi mid is the last two-sided hourly candle ending at or before the print (at most 2 h old);
if |mid - print| >= gap the bet fills at the next print on that contract before R - 5 min, at
that price plus a, plus the 0.01 fee. Each fill print serves at most one signal.

Usage
-----
    python scripts/multisignal.py --block discovery --trial 2386
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pilot  # noqa: E402
from fexlib import load_pairs  # noqa: E402


def signals(block: str, cfg: pilot.PilotConfig, blind: bool = False) -> pd.DataFrame:
    log: list[str] = []
    p = load_pairs()
    p = p[p["prod"].isin(pilot.H1_PRODUCTS)].sort_values("t")
    p["release_date"] = p.exp.dt.tz_convert("UTC").dt.date
    split = pd.Timestamp(cfg.split).date()
    p = p[(p.release_date < split) if block == "discovery" else (p.release_date >= split)]
    p["nt"] = p.groupby("event_contract").t.shift(-1)
    p["ny"] = p.groupby("event_contract").y.shift(-1)
    p["nh"] = p.groupby("event_contract").h.shift(-1)
    sig = p[(p.h > cfg.lead_h) & (p.h <= cfg.window_h) & p.ny.notna() & (p.nh > cfg.last_fill_h)]
    pilot._funnel("signal prints with a later fill print", len(sig), log)
    # map contract to its Kalshi twin once, through the per-contract matcher
    one = sig.groupby("event_contract", as_index=False).first()
    one["strike"] = one.event_contract.str.split("_").str[-1]
    one["settle"] = np.nan
    one["y_fill"] = one.ny
    one["t_fill"] = one.nt
    tw = pilot.attach_kalshi(one, cfg, log)[["event_contract", "kticker"]]
    sig = sig.merge(tw, on="event_contract")
    cd = pd.read_parquet(pilot.DATA / "kalshi_candles.parquet")
    cd["end"] = pd.to_datetime(cd.ts.astype(float), unit="s", utc=True).astype("datetime64[us, UTC]")
    cd["bid"] = pd.to_numeric(cd.bid, errors="coerce")
    cd["ask"] = pd.to_numeric(cd.ask, errors="coerce")
    cd = cd.sort_values("end")
    sig = pd.merge_asof(sig.sort_values("t"), cd[["ticker", "end", "bid", "ask"]].rename(
        columns={"ticker": "kticker"}), left_on="t", right_on="end", by="kticker",
        direction="backward", tolerance=pd.Timedelta(hours=cfg.max_stale_h))
    ok = (sig.bid > 0) & (sig.bid < sig.ask) & (sig.ask < 1)
    sig = sig[ok].copy()
    sig["kq"] = (sig.bid + sig.ask) / 2
    sig["g"] = sig.kq - sig.y
    sig = sig[sig.g.abs() >= cfg.gap]
    pilot._funnel("qualifying signals", len(sig), log)
    if not blind:
        s = pilot.settlements()
        sig = sig.merge(s, on="event_contract", how="inner")
        sig = sig[sig.settle.isin([0.0, 1.0])]
    return sig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    ap.add_argument("--trial", type=int, required=True)
    ap.add_argument("--blind", action="store_true")
    args = ap.parse_args()
    if args.block == "heldout" and not args.blind and not list(pilot.LANE.glob("freeze_*.md")):
        raise SystemExit("held-out block refused: no freeze note")
    cfg = pilot.PilotConfig(entry="next")
    sig = signals(args.block, cfg, blind=args.blind)
    res: dict = {"trial": args.trial, "block": args.block, "n_bets": len(sig),
                 "dates": int(sig.release_date.nunique()),
                 "contracts": int(sig.event_contract.nunique()),
                 "by_product": sig["prod"].value_counts().to_dict()}
    if not args.blind:
        for a in (0.01, 0.02, 0.03):
            buy = (sig.g > 0).to_numpy()
            entry = np.where(buy, sig.ny + a, 1 - sig.ny + a).clip(max=cfg.max_price)
            pay = np.where(buy, sig.settle, 1 - sig.settle)
            pnl = pay - entry - cfg.fee
            res[f"a={a}"] = pilot._ci(pd.Series(pnl), sig.release_date)
        cap = np.sign(sig.g) * (sig.settle - sig.ny)
        res["gross_gap_capture"] = pilot._ci(cap, sig.release_date)
        per_c = sig.assign(pnl=np.where(sig.g > 0, sig.settle, 1 - sig.settle)
                           - np.where(sig.g > 0, sig.ny + 0.02, 1 - sig.ny + 0.02) - 0.01)
        res["contract_mean_then_date_ci"] = pilot._ci(
            per_c.groupby("event_contract").pnl.mean(),
            per_c.groupby("event_contract").release_date.first())
    out = pilot.LANE / "logs" / f"multisignal_{args.block}_trial{args.trial}{'_blind' if args.blind else ''}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
