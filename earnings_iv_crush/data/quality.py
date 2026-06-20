"""
quality.py
Data-quality gates for chains and events, with logged exclusion reasons.

Free-tier data is shallow (Alpaca closes stand in for bid/ask, OI is a
snapshot), so rather than trading through bad prints the pipeline drops them —
but never silently. ``filter_chain`` returns the quote-level report and
``event_quality`` flags whole events; the exclusion table built from these
reasons feeds the research document, where the per-cohort drop rates are part
of the result, not a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import GLOBAL


@dataclass(frozen=True)
class ChainReport:
    """Quote counts per drop reason for one chain."""

    n_in: int
    n_out: int
    n_bad_price: int
    n_low_oi: int
    n_wide_spread: int
    n_far_strike: int


def filter_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    min_oi: int = GLOBAL.min_oi,
    max_rel_spread: float = GLOBAL.max_rel_spread,
    max_moneyness: float = 0.25,
) -> tuple[pd.DataFrame, ChainReport]:
    """Drop untradeable quotes; return the survivors and a per-reason report.

    Gates, in order: non-positive or NaN mid price; open interest below
    ``min_oi`` (NaN OI passes — Alpaca's snapshot OI is often missing and
    absence is not evidence of illiquidity); relative spread above
    ``max_rel_spread`` (only binds with real NBBO — with close-as-bid/ask the
    spread is zero); strikes beyond ``max_moneyness`` of spot.

    Parameters
    ----------
    chain : pd.DataFrame
        Canonical chain schema (``bid``, ``ask``, ``strike``, ``open_interest``).
    spot : float
        Underlying price for the moneyness gate.

    Returns
    -------
    (pd.DataFrame, ChainReport)
        The filtered chain (same schema) and the drop counts.
    """
    if chain is None or chain.empty:
        empty = chain if chain is not None else pd.DataFrame()
        return empty, ChainReport(0, 0, 0, 0, 0, 0)

    df = chain.copy()
    bid = pd.to_numeric(df["bid"], errors="coerce")
    ask = pd.to_numeric(df["ask"], errors="coerce")
    mid = (bid + ask) / 2
    oi = pd.to_numeric(df.get("open_interest"), errors="coerce")
    strike = pd.to_numeric(df["strike"], errors="coerce")

    bad_price = ~(mid > 0)
    low_oi = oi.notna() & (oi < min_oi)
    rel_spread = (ask - bid) / mid.where(mid > 0)
    wide_spread = rel_spread.notna() & (rel_spread > max_rel_spread)
    far_strike = (
        (strike - spot).abs() / spot > max_moneyness
        if spot and spot == spot
        else pd.Series(False, index=df.index)
    )

    keep = ~(bad_price | low_oi | wide_spread | far_strike)
    report = ChainReport(
        n_in=len(df),
        n_out=int(keep.sum()),
        n_bad_price=int(bad_price.sum()),
        n_low_oi=int(low_oi.sum()),
        n_wide_spread=int(wide_spread.sum()),
        n_far_strike=int(far_strike.sum()),
    )
    return df[keep].reset_index(drop=True), report


def event_quality(event: pd.Series) -> str | None:
    """Exclusion reason for an execution-ready event row, or None if usable.

    Checks, in order: missing entry spot or IV, missing exit spot, fewer than
    the front/back expiry pair (no term spread), no implied move.
    """

    def bad(x) -> bool:
        return x is None or pd.isna(x)

    if bad(event.get("spot_entry")) or bad(event.get("iv_entry")):
        return "missing_entry"
    if bad(event.get("spot_exit")):
        return "missing_exit"
    if bad(event.get("iv_term_spread")):
        return "no_term_spread"
    if bad(event.get("implied_move")):
        return "no_implied_move"
    return None


def exclusion_table(events: pd.DataFrame) -> pd.DataFrame:
    """Per-reason (and per-cohort, when present) exclusion counts.

    Returns a tidy frame with columns ``reason``, ``cohort`` (when the events
    carry one) and ``n``; usable events appear under reason ``"ok"``.
    """
    if events is None or events.empty:
        return pd.DataFrame(columns=["reason", "n"])
    reasons = events.apply(event_quality, axis=1).fillna("ok")
    if "cohort" in events.columns:
        out = (
            pd.DataFrame({"reason": reasons, "cohort": events["cohort"]})
            .value_counts()
            .rename("n")
            .reset_index()
        )
    else:
        out = reasons.value_counts().rename("n").rename_axis("reason").reset_index()
    return out
