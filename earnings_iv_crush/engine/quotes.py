"""
quotes.py
Quote-side selection and hygiene for option chains.

Why this module exists
----------------------
Every chain in this project carries ``bid`` and ``ask`` columns, but until now they
were the same number: the close-marked adapters set ``bid = ask = close`` because the
feeds were trade-based (``data.databento_options._to_chain``, ``data.alpaca_options``).
That degeneracy hid a convention error. Several consumers read ``bid`` directly while
documenting themselves as reading "the close" - harmless when the two coincide, and
badly wrong the moment a real two-sided quote arrives, because marking both ends of a
round trip at the bid understates the buy-back and flatters a short book.

This module makes the quote side an explicit choice rather than an accident:

* **mid** for valuation. What a position is worth is the midpoint; using a single side
  embeds half a spread of directional bias into every mark.
* **bid/ask** only where a crossing is actually being modelled, i.e. in the cost layer.

It also supplies the hygiene the option path never had. ``engine.event_study``
already does this for equities (``equity_roundtrip_cost_bps``); options had nothing.

Backward compatibility
----------------------
On a close-marked chain (``bid == ask == close > 0``) the mid equals the close exactly,
the relative spread is zero, and every contract is usable. Switching a caller from
``bid`` to ``side="mid"`` is therefore a no-op on all existing cached data and only
changes behaviour once genuinely two-sided quotes are supplied. That property is what
makes the migration safe, and it is asserted in the tests.

A note on locked markets
------------------------
``bid == ask`` (a locked market) is the *normal* state of every cached chain in this
repo, so it is flagged and counted but never treated as unusable. Only a **crossed**
market (``ask < bid``) is a genuine data error. Getting this backwards would empty the
entire historical book.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from ..config import GLOBAL

MarkSide = Literal["mid", "bid", "ask"]


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    """A float Series for ``column``, all-NaN when the column is absent."""
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


# Quote-quality reason codes, in the order they are applied. Kept as module constants
# so the funnel keys cannot drift between the cleaner and its callers.
REASON_CROSSED = "crossed"  # ask < bid: impossible, a data error
REASON_ZERO_BID = "zero_bid"  # no real bid; the mid is ask/2 and overstates the contract
REASON_WIDE = "wide_spread"  # relative spread beyond the configured tolerance
REASON_NO_QUOTE = "no_quote"  # bid and/or ask absent entirely
FUNNEL_REASONS = (REASON_NO_QUOTE, REASON_CROSSED, REASON_ZERO_BID, REASON_WIDE)


# ─────────────────────────────────────────────────────────────────────────────
# Side selection
# ─────────────────────────────────────────────────────────────────────────────


def side_price(bid: float, ask: float, side: MarkSide = "mid") -> float:
    """Price for one contract on the requested quote side.

    Falls back to whichever side is present when only one is quoted, because a
    one-sided quote is still information and refusing it would drop contracts that
    the close-marked history has always carried.

    Parameters
    ----------
    bid, ask : float
        The two quote sides. Either may be NaN.
    side : {"mid", "bid", "ask"}, optional
        ``mid`` for valuation (the default); ``bid``/``ask`` only when modelling a
        crossing. Defaults to ``"mid"``.

    Returns
    -------
    float
        The selected price, or NaN when neither side is available.
    """
    b, a = float(bid), float(ask)
    has_b, has_a = np.isfinite(b), np.isfinite(a)
    if side == "bid":
        return b if has_b else (a if has_a else float("nan"))
    if side == "ask":
        return a if has_a else (b if has_b else float("nan"))
    if has_b and has_a:
        return 0.5 * (b + a)
    if has_b:
        return b
    if has_a:
        return a
    return float("nan")


def add_quote_columns(chain: pd.DataFrame) -> pd.DataFrame:
    """Return ``chain`` with ``mid``, ``spread`` and ``rel_spread`` attached.

    ``rel_spread`` is the full quoted width as a fraction of the mid, matching the
    basis of ``GlobalConfig.max_rel_spread`` and ``CostModel.bid_ask_pct``. It is NaN
    where the mid is non-positive, so a zero-bid/zero-ask contract cannot masquerade
    as a tight one.
    """
    out = chain.copy()
    bid = _numeric(out, "bid")
    ask = _numeric(out, "ask")
    both = bid.notna() & ask.notna()
    mid = pd.Series(np.where(both, 0.5 * (bid + ask), bid.fillna(ask)), index=out.index)
    spread = pd.Series(np.where(both, ask - bid, np.nan), index=out.index)
    out["mid"] = mid
    out["spread"] = spread
    # NaN rather than inf at a non-positive mid, so a wholly unquoted contract cannot
    # masquerade as a tight one when the width is compared against a tolerance.
    out["rel_spread"] = pd.Series(
        np.where(mid > 0, spread.to_numpy() / mid.to_numpy(), np.nan), index=out.index
    )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Hygiene
# ─────────────────────────────────────────────────────────────────────────────


def flag_quotes(
    chain: pd.DataFrame,
    *,
    max_rel_spread: float = GLOBAL.max_rel_spread,
) -> pd.DataFrame:
    """Attach per-contract quote-quality flags plus a single ``usable`` column.

    Flags are independent, so a contract may trip more than one; ``usable`` is the
    conjunction of "none of the disqualifying conditions". A locked market
    (``bid == ask``) is recorded in ``is_locked`` for reporting but does **not**
    disqualify a contract: it is the normal state of every close-marked chain in this
    repo, and it is legitimate in a real quote stream too.

    Parameters
    ----------
    chain : pd.DataFrame
        Canonical chain carrying ``bid`` and ``ask``.
    max_rel_spread : float, optional
        Full quoted width as a fraction of mid, beyond which a contract is judged
        untradeable. Defaults to ``GlobalConfig.max_rel_spread`` (0.10), which is inert
        on close-marked data (every spread is zero) and binds on real quotes.

    Returns
    -------
    pd.DataFrame
        ``chain`` plus ``mid``, ``spread``, ``rel_spread``, ``is_locked``,
        ``is_crossed``, ``is_zero_bid``, ``is_wide``, ``no_quote`` and ``usable``.
    """
    out = add_quote_columns(chain)
    bid = _numeric(out, "bid")
    ask = _numeric(out, "ask")

    out["no_quote"] = bid.isna() & ask.isna()
    # Strictly less-than: equality is a locked market, which is normal, not an error.
    out["is_crossed"] = (bid.notna() & ask.notna() & (ask < bid)).fillna(False)
    out["is_locked"] = (bid.notna() & ask.notna() & (ask == bid)).fillna(False)
    # Only meaningful when an ask exists; a wholly unquoted contract is `no_quote`.
    out["is_zero_bid"] = (ask.notna() & (bid.isna() | (bid <= 0))).fillna(False)
    out["is_wide"] = (_numeric(out, "rel_spread") > max_rel_spread).fillna(False)

    out["usable"] = ~(out["no_quote"] | out["is_crossed"] | out["is_zero_bid"] | out["is_wide"])
    return out


def clean_chain(
    chain: pd.DataFrame,
    *,
    max_rel_spread: float = GLOBAL.max_rel_spread,
    funnel: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Drop unusable contracts, recording why in ``funnel``.

    A filter that can silently empty a chain is the failure mode this repo's
    exclusion-funnel convention exists to prevent (see ``data.real_events``), so every
    rejection is counted by reason into a caller-owned dict rather than vanishing.

    Parameters
    ----------
    chain : pd.DataFrame
        Canonical chain.
    max_rel_spread : float, optional
        See :func:`flag_quotes`.
    funnel : dict, optional
        Mutable counter, incremented in place. Keys are :data:`FUNNEL_REASONS` plus
        ``kept`` and ``seen``. Created internally when omitted.

    Returns
    -------
    pd.DataFrame
        The usable rows, with the quote columns retained for downstream cost work.
    """
    flagged = flag_quotes(chain, max_rel_spread=max_rel_spread)
    if funnel is None:
        funnel = {}
    for key, col in (
        (REASON_NO_QUOTE, "no_quote"),
        (REASON_CROSSED, "is_crossed"),
        (REASON_ZERO_BID, "is_zero_bid"),
        (REASON_WIDE, "is_wide"),
    ):
        funnel[key] = funnel.get(key, 0) + int(flagged[col].sum())
    funnel["seen"] = funnel.get("seen", 0) + len(flagged)
    kept = flagged[flagged["usable"]]
    funnel["kept"] = funnel.get("kept", 0) + len(kept)
    return kept


def format_funnel(funnel: dict[str, int], label: str = "quotes") -> str:
    """One-line-per-reason funnel summary, matching the repo's logging convention."""
    seen, kept = funnel.get("seen", 0), funnel.get("kept", 0)
    lines = [f"{label} funnel: {seen} contracts -> {kept} usable (dropped {seen - kept})"]
    for reason in FUNNEL_REASONS:
        n = funnel.get(reason, 0)
        if n:
            lines.append(f"  {reason:12s} {n}")
    return "\n".join(lines)
