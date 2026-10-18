"""
research_lossstudy_common.py
Shared reconstruction of the honest q=0.80 term-only mega-cap book for the
tail-risk / loss-cap / hold-to-expiry study.

Everything here reuses the validation layer so the book is byte-identical to the
paper's headline figure: the Databento-marked event frame, the expanding
strictly-earlier term gate at q=0.80, the two-leg market-marked return on margin at
the central mega-cap ~2% round-trip cost. The reconstructed naked book is 192 trades
with a per-trade Sharpe of about +0.116 and a worst trade of about -0.965.

No tracked package code is modified; this is a research-only helper.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.research.gates import expanding_high_term_mask  # noqa: E402

TERM_Q = 0.80
CALENDAR = Path("outputs/research/calendar_databento.parquet")

# ── measured asymmetric execution cost, as half-crosses of premium ──────────────
ENTRY_HALF_CROSS = 0.0307  # 3.07% of entry premium
EXIT_HALF_CROSS = 0.0855  # 8.55% of exit premium


def prepared_gated() -> tuple[pd.DataFrame, pd.Series]:
    """The prepared causal window and the boolean q=0.80 expanding term gate over it."""
    ev, fair = mv._prepare(mv.EVENTS_FULL)
    mask = expanding_high_term_mask(ev, TERM_Q)
    return ev, pd.Series(mask, index=ev.index)


def gated_events() -> pd.DataFrame:
    """The gated event rows (with real market marks: credit_mkt/exit_mkt/wing_*)."""
    ev, mask = prepared_gated()
    return ev[mask.to_numpy()].reset_index(drop=True)


def naked_ledger() -> pd.DataFrame:
    """The 192-trade naked book, ROM-ordered as the paper builds it, with the
    announcement session (amc/bmo) joined on. Columns include ticker, entry_date,
    exit_date, announce_date, return_on_margin, session."""
    g = gated_events()
    led = mv._ledger(g, defined_risk=False, costs=mv.MEGACAP_COST)
    led = led.sort_values(["entry_date", "exit_date"]).reset_index(drop=True)

    # carry announce_date from the gated frame (key on ticker + entry_date)
    keyed = g[["ticker", "entry_date", "announce_date"]].copy()
    keyed["entry_date"] = keyed["entry_date"].astype(str)
    led["entry_date"] = led["entry_date"].astype(str)
    led = led.merge(
        keyed.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left"
    )

    if CALENDAR.exists():
        cal = pd.read_parquet(CALENDAR)
        cal["announce_date"] = pd.to_datetime(cal["announce_date"])
        led["announce_date"] = pd.to_datetime(led["announce_date"])
        led = led.merge(
            cal[["ticker", "announce_date", "session"]].drop_duplicates(
                ["ticker", "announce_date"]
            ),
            on=["ticker", "announce_date"],
            how="left",
        )
    else:
        led["session"] = np.nan
    return led


def per_trade_sharpe(rom: np.ndarray) -> float:
    rom = np.asarray(rom, dtype=float)
    sd = rom.std(ddof=1)
    return float(rom.mean() / sd) if sd > 0 and len(rom) > 1 else float("nan")
