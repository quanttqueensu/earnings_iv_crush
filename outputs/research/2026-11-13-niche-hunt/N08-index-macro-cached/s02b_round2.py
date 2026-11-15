"""s02b_round2.py: N08 discovery round 2. Remove the exit crossing on release nights.

Round 1 (s02_round1.log) showed the release night is rich at the mid (short T1 +0.87% of P0 against
-0.06% on clean nights) but a round trip at 15:59 and 10:00 costs about 2.7% of P0. Two vehicles
avoid the 10:00 crossing; both are scored on block D only:

- T3b (trial 2,304): the release-day expiry sold at the 15:59 bids on the session before D and
  settled at intrinsic on D's close, with the forward pre-registration's disposal rule (1 bp of the
  D close per delivered share plus the actual D-close to next-open move on the delivered share,
  and its dividend if the next session is the ex-date) instead of the frozen 5 bp. The 1 bp rule
  was fixed after stream 17 saw the unconditional outcome; recorded as such.
- T4 (trial 2,305): the T1 contract (shortest expiry after D) sold at 15:59 on the session before
  D, delta-hedged at each close with the ETF at the entry implied volatility, settled at
  intrinsic, `hedged_short_straddle` with the adopted netting `HEDGED_NET`.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s02b_round2.py
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.config import HEDGED_NET
from earnings_iv_crush.research.hedged_hold import hedged_short_straddle, straddle_iv, year_frac

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRICED = ROOT / "outputs" / "research" / "2026-11-01-index-event-crush" / "priced_trades.parquet"
NDE = ROOT / "outputs" / "research" / "2026-11-02-next-day-expiry-settle" / "trades.parquet"
COMMISSION = 0.0065
DISPOSAL_BP = 1.0  # forward pre-registration of the next-day-expiry settle
FROZEN_DISPOSAL_BP = 5.0  # stream 17, used only to reconcile with its column N
MARGIN_SPOT_FRAC = 0.15

_s = importlib.util.spec_from_file_location("disc", HERE / "s02_discovery.py")
assert _s is not None and _s.loader is not None
disc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(disc)


def bars() -> dict[str, pd.DataFrame]:
    px = pd.read_parquet(HERE / "yahoo_ohlc.parquet")
    out = {}
    for tk, g in px.groupby("ticker"):
        g = g.set_index(pd.to_datetime(g["Date"]).dt.tz_localize(None).dt.normalize()).sort_index()
        out[str(tk)] = pd.DataFrame({"open": g["Open"], "close": g["Close"],
                                     "ret": g["Adj Close"].pct_change(),
                                     "div": g["Dividends"].fillna(0.0),
                                     "split": g["Stock Splits"].fillna(0.0)})
    return out


def t3b(bx: dict[str, pd.DataFrame]) -> pd.DataFrame:
    n = pd.read_parquet(NDE)
    n = n[n["status"] == "ok"].copy()
    rows = []
    for r in n.itertuples():
        g = bx[r.ticker]
        ex = pd.Timestamp(r.exit)
        if ex not in g.index:
            rows.append({"status": "no_bar"})
            continue
        i = g.index.get_loc(ex)
        if i + 1 >= len(g):
            rows.append({"status": "no_next_open"})
            continue
        s1, o2 = float(g["close"].iloc[i]), float(g["open"].iloc[i + 1])
        d2 = float(g["div"].iloc[i + 1])
        k = float(r.strike)
        intr = abs(s1 - k)
        base = r.sale - intr - 2 * COMMISSION
        frozen = (base - FROZEN_DISPOSAL_BP / 1e4 * s1 * (s1 != k)) / r.p0
        if s1 > k:  # short call assigned: short one share overnight
            move = -(o2 - s1) - d2
        elif s1 < k:  # short put assigned: long one share overnight
            move = (o2 - s1) + d2
        else:
            move = 0.0
        net = (base - DISPOSAL_BP / 1e4 * s1 * (s1 != k) + move) / r.p0
        rows.append({"status": "ok", "ticker": r.ticker, "entry": pd.Timestamp(r.entry),
                     "event_date": ex, "frozen_check": frozen - r.N, "short_net": net,
                     "short_net_rom": net * r.p0 / (r.p0 + MARGIN_SPOT_FRAC * r.fwd0),
                     "move_share": move / r.p0, "dte": 1.0 * (ex - pd.Timestamp(r.entry)).days,
                     "half_spread_entry": r.half_spread, "short_mid": r.N_mid})
    out = pd.DataFrame(rows)
    print("T3b funnel", Counter(out["status"]))
    out = out[out["status"] == "ok"]
    dev = out["frozen_check"].abs().max()
    print(f"T3b reconciliation to frozen N at 5 bp, no move: max |diff| {dev:.2e}")
    if dev > 1e-6:
        raise ValueError("T3b does not reconcile to the frozen next-day-expiry rows")
    return out


def t4(bx: dict[str, pd.DataFrame]) -> pd.DataFrame:
    d = pd.read_parquet(PRICED)
    d = d[(d["exit_snap"].astype(str) == "1000") & (d["status"] == "ok")].copy()
    for c in ("entry", "exit", "expiry"):
        d[c] = pd.to_datetime(d[c])
    rows, funnel = [], Counter()
    for r in d.itertuples():
        g = bx[r.ticker]
        w = g.loc[r.entry:r.expiry]
        if len(w) < 2 or w.index[0] != r.entry:
            funnel["missing_bars"] += 1
            continue
        if (w["split"].iloc[1:] != 0).any():
            funnel["split"] += 1
            continue
        sig = straddle_iv(r.p0, r.fwd0, r.strike, year_frac(r.entry, r.expiry))
        if not np.isfinite(sig):
            funnel["no_iv"] += 1
            continue
        cl = w["close"].to_numpy(float)
        n = len(cl) - 1
        res = hedged_short_straddle(
            sale_price=r.c0b + r.p0b, sale_mid=r.p0, strike=r.strike, fwd=r.fwd0,
            closes=cl[:-1], rets=w["ret"].to_numpy(float)[1:],
            taus=np.array([year_frac(x, r.expiry) for x in w.index[:-1]]),
            sigmas=np.full(n, sig), half_spreads=np.zeros(n), settle_close=float(cl[-1]),
            cfg=HEDGED_NET,
        )
        funnel["ok"] += 1
        rows.append({"status": "ok", "ticker": r.ticker, "entry": r.entry, "event_date": r.exit,
                     "dte": r.dte, "short_net": res.net_pnl / r.p0,
                     "short_mid": res.gross_pnl_mid / r.p0,
                     "short_net_rom": res.net_pnl / (r.p0 + MARGIN_SPOT_FRAC * r.fwd0),
                     "half_spread_entry": (r.c0a - r.c0b + r.p0a - r.p0b) / 2 / r.p0})
    print("T4 funnel", dict(funnel))
    return pd.DataFrame(rows)


def attach(df: pd.DataFrame, fam: str, base: pd.DataFrame) -> pd.DataFrame:
    keys = base[base["family"] == "T1"][["ticker", "entry", "entry_pos", "weekday", "block"]
                                       + [c for c in base.columns if c.startswith(("ev_", "en_"))]]
    keys = keys.drop_duplicates(["ticker", "entry"])
    out = df.merge(keys, on=["ticker", "entry"], how="left", validate="many_to_one")
    miss = out["entry_pos"].isna().sum()
    if miss:
        print(f"  {fam}: {miss} rows without a T1 key (dropped)")
    out = out.dropna(subset=["entry_pos"])
    # T3b events key on its own exit date; rebuild the event flags from the calendar
    cal = pd.read_parquet(HERE / "calendar_flags.parquet")
    for k in ("cpi", "nfp", "fomc", "pce"):
        out[f"ev_{k}"] = out["event_date"].map(cal[k]).astype("boolean").fillna(False).astype(bool)
        out[f"en_{k}"] = out[f"en_{k}"].astype(bool)
    out["family"] = fam
    return out


def main() -> None:
    base = pd.read_parquet(HERE / "trades_all.parquet")
    bx = bars()
    a = attach(t3b(bx), "T3b", base)
    b = attach(t4(bx), "T4", base)
    allr = pd.concat([a, b], ignore_index=True)
    allr.to_parquet(HERE / "trades_round2.parquet")
    df = allr[allr["block"] == "D"].copy()
    if df["entry"].max() >= pd.Timestamp("2025-01-01"):
        sys.exit("held-out rows leaked into discovery")
    r_mask = df["ev_cpi"] | df["ev_nfp"]
    rows: list[dict[str, object]] = []
    disc.score(df, "T3b", "SPY", r_mask, "R=cpi|nfp settle 1bp+move", 2304, rows=rows)
    print("  T3b overnight share move, event mean "
          f"{df[(df.family == 'T3b') & (df.ticker == 'SPY') & r_mask]['move_share'].mean():+.4f}")
    disc.score(df, "T4", "SPY", r_mask, "R=cpi|nfp hedged hold", 2305, rows=rows)
    pd.DataFrame(rows).to_csv(HERE / "discovery_round2.csv", index=False)


if __name__ == "__main__":
    main()
