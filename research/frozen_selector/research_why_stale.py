"""
research_why_stale.py
Root-cause of the below-intrinsic exit marks.

``research_mark_integrity`` established that 20% of exit marks in the gated book
price the straddle below ``|S - K|``, concentrated in the big-move events. This
script asks *why*, by isolating the offending leg and cross-checking it against an
independent feed.

Three candidate causes, which the data can separate:

1. **Thin/absent trading.** After the gap the deep-ITM leg has little reason to
   trade (you would trade the stock instead), so its daily bar rests on a handful
   of contracts, or it does not print at all.
2. **Venue consolidation.** ``databento_options._consolidate`` takes the close of
   the single highest-volume OPRA venue, not the day's last consolidated print. A
   busy-venue morning print then beats a quiet-venue afternoon one.
3. **A bad spot.** If ``spot_exit`` were mis-scaled (splits), ``|S - K|`` would be
   wrong and the "violation" would be an artefact of the underlying, not the
   option. Ruled in or out by re-deriving intrinsic from the chain's own put-call
   parity, which never touches the equity feed.

The LSE daily vault is an independent feed that carries per-contract ``volume`` and
filters to contracts that actually traded, so it can arbitrate all three.

Usage:
    python research/frozen_selector/research_why_stale.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.data.databento_options as dbo  # noqa: E402
import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.research.gates import expanding_high_term_mask  # noqa: E402
from research.timing.research_lossstudy_common import TERM_Q  # noqa: E402

LSE_RAW = Path("data/processed/lse_raw")
OUT = Path("outputs/research/why_stale.csv")
TOL = 0.01


def _lse_day(ticker: str, day: pd.Timestamp) -> pd.DataFrame:
    """One session of LSE daily option bars for *ticker*, or empty."""
    p = LSE_RAW / f"{ticker}.parquet"
    if not p.exists():
        return pd.DataFrame()
    raw = pd.read_parquet(p)
    if raw.empty:
        return raw
    ts = pd.to_datetime(raw["ts"]).dt.tz_localize(None).dt.normalize()
    return raw[ts == pd.Timestamp(day).normalize()]


def main() -> int:
    ev, _ = mv._prepare(mv.EVENTS_FULL)
    g = ev[expanding_high_term_mask(ev, TERM_Q)].reset_index(drop=True).copy()

    k = g["strike_mkt"].astype(float)
    g["intr_exit"] = (g["spot_exit"].astype(float) - k).abs()
    g["viol"] = g["intr_exit"] - g["exit_mkt"].astype(float)
    bad = g[(g["viol"] > TOL)].dropna(subset=["exit_mkt"]).reset_index(drop=True)
    print(f"gated book {len(g)} events; {len(bad)} exit marks below intrinsic\n")

    rows = []
    for _, e in bad.iterrows():
        tkr = str(e["ticker"])
        xd = pd.Timestamp(e["exit_date"])
        k_ = float(e["strike_mkt"])
        s_ = float(e["spot_exit"])
        exp = pd.Timestamp(e["entry_date"]) + pd.Timedelta(days=round(float(e["t_entry"]) * 365))

        px = dbo._cache_path(tkr, xd)
        cx = pd.read_parquet(px) if px.exists() else pd.DataFrame()
        fexp = cx["expiry"].iloc[(cx["expiry"] - exp).abs().argmin()] if len(cx) else exp

        itm_right = "C" if s_ > k_ else "P"  # spot above strike -> the call is ITM
        otm_right = "P" if s_ > k_ else "C"
        db_itm = mv._legs(cx, fexp, k_, itm_right)
        db_otm = mv._legs(cx, fexp, k_, otm_right)

        # The ITM leg alone must be worth at least intrinsic. Is *it* the culprit?
        itm_short = e["intr_exit"] - db_itm

        # Independent feed: same contract, same day, from the LSE vault (with volume).
        day = _lse_day(tkr, xd)
        lse_itm = lse_vol = lse_otm_vol = np.nan
        if not day.empty:
            m = (
                (pd.to_datetime(day["expiry"]).dt.normalize() == pd.Timestamp(fexp).normalize())
                & (np.isclose(day["strike"].astype(float), k_))
                & (day["opt_type"].astype(str).str.upper().str[0] == itm_right)
            )
            hit = day[m]
            if len(hit):
                lse_itm = float(hit["close"].iloc[0])
                lse_vol = float(hit["volume"].iloc[0])
            mo = (
                (pd.to_datetime(day["expiry"]).dt.normalize() == pd.Timestamp(fexp).normalize())
                & (np.isclose(day["strike"].astype(float), k_))
                & (day["opt_type"].astype(str).str.upper().str[0] == otm_right)
            )
            ho = day[mo]
            if len(ho):
                lse_otm_vol = float(ho["volume"].iloc[0])

        rows.append(
            {
                "ticker": tkr,
                "exit_date": xd.date(),
                "strike": k_,
                "spot_exit": s_,
                "abs_move": abs(float(e["realised_move"])),
                "intrinsic": e["intr_exit"],
                "db_straddle": float(e["exit_mkt"]),
                "violation": float(e["viol"]),
                "itm_right": itm_right,
                "db_itm_leg": db_itm,
                "db_otm_leg": db_otm,
                "itm_shortfall": itm_short,
                "lse_itm_close": lse_itm,
                "lse_itm_volume": lse_vol,
                "lse_otm_volume": lse_otm_vol,
            }
        )

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    print("=" * 78)
    print("1. WHICH LEG IS BROKEN?")
    print("=" * 78)
    itm_bad = (df["itm_shortfall"] > TOL).mean()
    print(f"  the ITM leg alone is below intrinsic on {itm_bad:.0%} of violating events")
    print(f"  median ITM-leg shortfall: ${df['itm_shortfall'].median():+.2f}")
    print("  (the ITM leg must be worth >= |S-K| on its own; the OTM leg cannot be negative,")
    print("   so if the straddle is short, the ITM leg is where the price went missing)")

    print("\n" + "=" * 78)
    print("2. IS IT A LIQUIDITY / STALE-PRINT PROBLEM?")
    print("=" * 78)
    v = df["lse_itm_volume"].dropna()
    ov = df["lse_otm_volume"].dropna()
    if len(v):
        print(f"  ITM-leg volume on the exit session (independent LSE feed), n={len(v)}:")
        print(
            f"    median {v.median():.0f} contracts   p25 {v.quantile(.25):.0f}   "
            f"p75 {v.quantile(.75):.0f}   max {v.max():.0f}"
        )
        print(f"    traded < 10 contracts all day: {(v < 10).mean():.0%}")
        print(f"    never printed at all (absent) : {df['lse_itm_volume'].isna().mean():.0%}")
    if len(ov):
        print(f"\n  OTM-leg volume, same events: median {ov.median():.0f} contracts")
        print("  (the OTM leg is the one the parity repair keeps - it should be far busier)")

    print("\n" + "=" * 78)
    print("3. DO THE TWO INDEPENDENT FEEDS AGREE ON THE BROKEN LEG?")
    print("=" * 78)
    both = df.dropna(subset=["lse_itm_close"])
    if len(both):
        both = both.copy()
        both["lse_shortfall"] = both["intrinsic"] - (both["lse_itm_close"] + both["db_otm_leg"])
        agree = np.isclose(both["db_itm_leg"], both["lse_itm_close"], rtol=0.02).mean()
        lse_also_bad = (both["intrinsic"] - both["lse_itm_close"] > TOL).mean()
        print(f"  n with the contract in both feeds: {len(both)}")
        print(f"  Databento and LSE closes agree (2%): {agree:.0%}")
        print(f"  LSE's own ITM close is ALSO below intrinsic: {lse_also_bad:.0%}")
        print("\n  If both feeds are below intrinsic, the print is real but unrepresentative")
        print("  (a genuine stale/odd trade), not a feed bug. If only Databento is, the")
        print("  venue-consolidation rule in _consolidate is picking the wrong bar.")

    print("\n" + "=" * 78)
    print("4. IS THE SPOT TO BLAME? (splits / equity feed)")
    print("=" * 78)
    # Rebuild intrinsic from the chain alone via parity: C - P = S - K, so the
    # chain's own implied spot is K + (C - P). If that agrees with spot_exit, the
    # equity feed is fine and the option leg really is the problem.
    imp_spot = df["strike"] + (
        np.where(
            df["itm_right"] == "C",
            df["db_itm_leg"] - df["db_otm_leg"],
            df["db_otm_leg"] - df["db_itm_leg"],
        )
    )
    err = (imp_spot - df["spot_exit"]) / df["spot_exit"]
    print(
        f"  chain-implied spot vs equity-feed spot: median {err.median():+.2%}, "
        f"mean {err.mean():+.2%}"
    )
    print("  (a large negative gap means the option legs are cheap relative to the")
    print("   underlying - i.e. the options are stale, not the spot)")

    print(f"\nwrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
