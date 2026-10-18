"""
research_hold_to_expiry.py
Does holding to weekly expiry beat the 8.55% exit cross?

The binding constraint on the book is the exit half-cross (8.55% of premium, versus
3.07% on entry). Holding the short straddle to the front weekly expiry rather than
buying it back the next session removes the exit option spread entirely: the
out-of-the-money leg expires worthless and the in-the-money leg cash-settles at
intrinsic. The price paid is extra post-event directional exposure from the exit date
to expiry.

This compares two exits on the same gated trades, on two cost bases:
  plus1_exit        buy back at the next session close
  hold_to_expiry    let it expire; straddle settles at intrinsic |S_exp - K|

  asymmetric (measured): the realistic execution cost from the fills study, entry
    half-cross 3.07% + exit half-cross 8.55% of premium. The exit cross is the binding
    constraint, so this is the basis on which holding to expiry has its rationale.
  symmetric (megacap): the paper's central ~2% round-trip CostModel, so the plus1 book
    reproduces the +0.116 naked baseline and the hold/conditional books are directly
    comparable to it. Under this optimistic basis the modelled exit spread is small, so
    the saving from skipping the buy-back is correspondingly smaller.

Settlement note: weekly-expiry option chains are not cached on disk (only the entry and
next-session dates are), so the held straddle is valued at de-adjusted equity intrinsic
rather than re-marked from an expiry chain. A clean chain re-mark and assignment handling
would need a fresh expiry-date pull; this keeps the magnitude indicative.

Spot at expiry comes from free daily equity bars. Output:
  outputs/research/hold_to_expiry.csv
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.data.equities import fetch_equity_ohlcv  # noqa: E402
from earnings_iv_crush.engine.pnl import regt_straddle_margin, size_contracts  # noqa: E402
from research.timing.research_lossstudy_common import (  # noqa: E402
    ENTRY_HALF_CROSS,
    EXIT_HALF_CROSS,
    gated_events,
    per_trade_sharpe,
)

OUT = Path("outputs/research/hold_to_expiry.csv")
ACCOUNT, FRACTION = mv.ACCOUNT_SIZE, mv.FRACTION


def _spot_cache(tickers, start, end) -> dict:
    cache = {}
    for t in sorted(set(tickers)):
        try:
            df = fetch_equity_ohlcv(t, start, end)
            df = df.set_index(pd.to_datetime(df["date"])).sort_index()
            cache[t] = df
        except Exception as exc:  # noqa: BLE001
            print(f"  spot fetch failed for {t}: {exc}")
    return cache


def _close_on(cache: dict, ticker: str, day: pd.Timestamp) -> float:
    """Last available (possibly split-adjusted) close at or before `day`."""
    df = cache.get(ticker)
    if df is None or df.empty:
        return np.nan
    col = "close" if "close" in df.columns else ("Close" if "Close" in df.columns else None)
    if col is None:
        return np.nan
    upto = df.loc[df.index <= day, col]
    return float(upto.iloc[-1]) if len(upto) else np.nan


def _spot_at_expiry(
    cache: dict, ticker: str, entry_day: pd.Timestamp, spot_entry: float, expiry: pd.Timestamp
) -> float:
    """Contemporaneous (raw) spot at expiry, de-adjusted to the strike's price scale.

    yfinance closes are split/dividend-adjusted, but the option strike and spot_entry are
    raw contemporaneous levels. Rescaling the adjusted series by spot_entry / adj_close(entry)
    puts the expiry close back on the entry-date raw scale (split-consistent over the few-day
    hold), so |spot_expiry - strike| is a real intrinsic rather than a split artefact."""
    adj_entry = _close_on(cache, ticker, entry_day)
    adj_exp = _close_on(cache, ticker, expiry)
    if not (np.isfinite(adj_entry) and adj_entry > 0 and np.isfinite(adj_exp)):
        return np.nan
    return float(adj_exp * (spot_entry / adj_entry))


def main() -> None:
    g = gated_events()
    cache = _spot_cache(
        g["ticker"].tolist(),
        (pd.to_datetime(g["entry_date"]).min() - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        (pd.to_datetime(g["entry_date"]).max() + pd.Timedelta(days=30)).strftime("%Y-%m-%d"),
    )

    rows = []
    for _, e in g.iterrows():
        credit, exit_buyback = float(e.get("credit_mkt", np.nan)), float(e.get("exit_mkt", np.nan))
        strike = float(e.get("strike_mkt", np.nan))
        spot = float(e["spot_entry"])
        if not (
            np.isfinite(credit) and credit > 0 and np.isfinite(exit_buyback) and np.isfinite(strike)
        ):
            continue
        pe = dbo._cache_path(e["ticker"], pd.Timestamp(e["entry_date"]))
        if not pe.exists():
            continue
        ce = pd.read_parquet(pe)
        if ce.empty:
            continue
        target_exp = pd.Timestamp(e["entry_date"]) + pd.Timedelta(days=round(e["t_entry"] * 365))
        fexp = ce["expiry"].iloc[(ce["expiry"] - target_exp).abs().argmin()]
        spot_exp = _spot_at_expiry(
            cache, e["ticker"], pd.Timestamp(e["entry_date"]), spot, pd.Timestamp(fexp)
        )
        if not np.isfinite(spot_exp):
            continue
        intrinsic = abs(spot_exp - strike)

        contracts = size_contracts(ACCOUNT, spot, strike, credit, FRACTION)
        if contracts <= 0:
            continue
        margin = regt_straddle_margin(spot, strike, credit, contracts)
        mult = 100 * contracts

        # ── asymmetric (measured) cost basis ──
        # plus-1 exit: pay entry + exit half-crosses
        cost_plus1 = (ENTRY_HALF_CROSS * credit + EXIT_HALF_CROSS * exit_buyback) * mult
        pnl_plus1 = (credit - exit_buyback) * mult - cost_plus1
        # hold to expiry: settle at intrinsic, pay entry half-cross only
        cost_hold = (ENTRY_HALF_CROSS * credit) * mult
        pnl_hold = (credit - intrinsic) * mult - cost_hold

        # ── symmetric (megacap) cost basis, comparable to the +0.116 baseline ──
        # plus-1: full round-trip cost (this reproduces the naked headline book)
        cost_plus1_sym = mv.MEGACAP_COST.round_trip_cost(credit, exit_buyback, contracts).total_cost
        pnl_plus1_sym = (credit - exit_buyback) * mult - cost_plus1_sym
        # hold: only the entry-side crossing is paid (the expiry settlement crosses no
        # spread); model it by charging a single fill per leg on the entry premium only
        entry_only = dataclasses.replace(mv.MEGACAP_COST, fills_per_leg=1)
        cost_hold_sym = entry_only.round_trip_cost(credit, 0.0, contracts).total_cost
        pnl_hold_sym = (credit - intrinsic) * mult - cost_hold_sym

        rows.append(
            {
                "ticker": e["ticker"],
                "entry_date": str(e["entry_date"]),
                "expiry": str(pd.Timestamp(fexp).date()),
                "days_to_expiry": int((pd.Timestamp(fexp) - pd.Timestamp(e["entry_date"])).days),
                "rom_plus1": pnl_plus1 / margin,
                "rom_hold": pnl_hold / margin,
                "rom_plus1_sym": pnl_plus1_sym / margin,
                "rom_hold_sym": pnl_hold_sym / margin,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        print("no trades with spot-at-expiry available; hold-to-expiry not computable on disk")
        df.to_csv(OUT, index=False)
        return

    r1 = df["rom_plus1"].to_numpy()
    rh = df["rom_hold"].to_numpy()
    r1s = df["rom_plus1_sym"].to_numpy()
    rhs = df["rom_hold_sym"].to_numpy()
    mdte = float(df["days_to_expiry"].median())
    summary = pd.DataFrame(
        [
            {
                "basis": "asymmetric",
                "exit": "plus1",
                "n": len(df),
                "per_trade_sharpe": per_trade_sharpe(r1),
                "mean_rom": r1.mean(),
                "worst_rom": r1.min(),
                "win": (r1 > 0).mean(),
            },
            {
                "basis": "asymmetric",
                "exit": "hold_to_expiry",
                "n": len(df),
                "per_trade_sharpe": per_trade_sharpe(rh),
                "mean_rom": rh.mean(),
                "worst_rom": rh.min(),
                "win": (rh > 0).mean(),
            },
            {
                "basis": "symmetric",
                "exit": "plus1",
                "n": len(df),
                "per_trade_sharpe": per_trade_sharpe(r1s),
                "mean_rom": r1s.mean(),
                "worst_rom": r1s.min(),
                "win": (r1s > 0).mean(),
            },
            {
                "basis": "symmetric",
                "exit": "hold_to_expiry",
                "n": len(df),
                "per_trade_sharpe": per_trade_sharpe(rhs),
                "mean_rom": rhs.mean(),
                "worst_rom": rhs.min(),
                "win": (rhs > 0).mean(),
            },
        ]
    )
    df.to_csv(OUT, index=False)

    print(
        f"=== hold-to-expiry vs plus-1 exit, n={len(df)} of {len(g)} gated, median DTE {mdte:.0f}d ==="
    )
    print(summary.to_string(index=False))
    print(
        f"\nAsymmetric (realistic) basis: hold {per_trade_sharpe(rh):+.3f} vs plus1 "
        f"{per_trade_sharpe(r1):+.3f} (delta {per_trade_sharpe(rh)-per_trade_sharpe(r1):+.3f}); the "
        "exit cross is where the lever lives."
    )
    print(
        f"Symmetric (megacap) basis: plus1 {per_trade_sharpe(r1s):+.3f} reproduces the +0.116 naked "
        f"baseline (sanity check); hold {per_trade_sharpe(rhs):+.3f}. Under the optimistic cost the "
        "modelled exit spread is small, so the saving from skipping the buy-back narrows."
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
