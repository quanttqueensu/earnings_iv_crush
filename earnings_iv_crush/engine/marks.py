"""
marks.py
Straddle marking that survives per-contract staleness, and the checks that catch it.

Why this module exists
----------------------
Option daily bars are last-trade prints. Across a chain most contracts print near
the close, so the chain as a whole is well synchronised with the 16:00 underlying
mark: on the mega-cap book the chain-implied spot ``K + C - P`` tracks the exit-day
close to a 0.26% median absolute error. But that is an *aggregate* property. At the
level of a single contract the last print can be hours old, and the staleness is
**not symmetric across the two legs of a strike**.

After an earnings gap the traded strike is pushed away from the money, and it is the
deep in-the-money leg whose print goes stale relative to its partner. The result is a
straddle marked below its own intrinsic value ``|S - K|``, which is not merely noisy
but *directionally* wrong: the short appears to buy the straddle back cheaper than was
physically possible, so the loss is never booked. On the q=0.80 mega-cap book this hit
20.1% of exit marks, rising to 35% on the largest-move tercile - precisely the loss
tail the strategy is exposed to.

The repair
----------
Put-call parity gives ``C - P = (F - K) * D``, with ``F`` the forward and ``D`` the
discount factor. Rearranged, the straddle is

    C + P = |F - K| * D + 2 * OTM_leg

where the out-of-the-money leg is measured against the *forward*, not spot. The OTM leg
is the cheap one that keeps trading; the in-the-money leg is the one that goes stale. So
the straddle is rebuilt from forward intrinsic plus twice the OTM leg, which **discards
the unreliable leg and keeps the reliable one**.

``F`` and ``D`` are not taken from a rate curve. They are regressed out of the chain
itself: across strikes where both legs print, ``C - P`` is linear in ``K`` with slope
``-D`` and intercept ``F * D``. Estimating them from the same chain being marked absorbs
the financing rate *and* the dividend, and keeps the mark self-consistent. Using a naive
``|S - K|`` instead biases the rebuild by ``K * (1 - D)``, which is ~$0.19 on a $200 name
at 5% over a week - 1-4% of a typical straddle credit, and not ignorable.

Validated on the mega-cap book: on events whose raw mark is trustworthy the rebuild
agrees with it, while on the violating events it raises the buy-back materially. It is
targeting the stale prints rather than reshaping the book.

Quote side
----------
All marking here is on the **mid** (``engine.quotes.side_price``). On the close-marked
feeds this module was built against, ``bid == ask == close``, so the mid is the close
and nothing changes; on a genuinely two-sided feed it avoids embedding half a spread of
directional bias in every mark. The bid/ask sides are used only by ``engine.costs``,
where a crossing is actually being modelled.

What this does NOT fix
----------------------
Parity leans on the OTM leg's print being fresh; only an intraday feed can verify that
(see ``data.lse_intraday``). On a trade-marked feed the spread also remains an
assumption in ``engine.costs`` rather than a measurement, though a quote-marked chain
supplies the real width in ``rel_spread``.

References
----------
Stoll, H. R. (1969). The relationship between put and call option prices.
*The Journal of Finance*, 24(5), 801-824.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .quotes import MarkSide, add_quote_columns, side_price

# A straddle mark below intrinsic by more than this cannot be explained by tick
# granularity or the strike discount; it is a stale print.
VIOLATION_TOL = 0.01

# How far the chain-implied forward may sit from spot before the chain itself is judged
# stale. A sub-90-day equity forward lives within a fraction of a percent of spot, so
# 2% is already generous; beyond it the fit is reading stale legs, not a real forward.
FORWARD_SANITY_BAND = 0.02


@dataclass(frozen=True)
class StraddleMark:
    """One straddle mark, with the evidence needed to judge it.

    Attributes
    ----------
    price : float
        Straddle price per share. NaN when the chain cannot support a mark.
    call, put : float
        The raw leg closes as the feed reported them (NaN when absent).
    intrinsic : float
        ``|spot - strike|``.
    raw_price : float
        The naive ``call + put`` mark, kept so the repair's effect is auditable.
    otm_leg : float
        The out-of-the-money leg the parity rebuild rests on.
    violated : bool
        True when the *raw* mark breached intrinsic, i.e. the feed was stale.
    repaired : bool
        True when ``price`` came from the parity rebuild rather than ``raw_price``.
    """

    price: float
    call: float
    put: float
    intrinsic: float
    raw_price: float
    otm_leg: float
    violated: bool
    repaired: bool


def _leg(chain: pd.DataFrame, expiry, strike: float, right: str, side: MarkSide = "mid") -> float:
    """One leg's price from a canonical chain, or NaN.

    Defaults to the **mid**. This previously read ``bid`` unconditionally, which was
    invisible while the close-marked adapters set ``bid == ask == close`` but marks a
    round trip at the bid on both ends the moment real quotes arrive - understating the
    buy-back and flattering a short. On close-marked data the mid equals the close, so
    the default is bit-identical to the historical behaviour.
    """
    s = chain[
        (chain["expiry"] == expiry)
        & (np.isclose(chain["strike"], strike))
        & (chain["right"] == right)
    ]
    if not len(s):
        return float("nan")
    row = s.iloc[0]
    return side_price(row.get("bid", float("nan")), row.get("ask", float("nan")), side)


def implied_forward(
    chain: pd.DataFrame,
    *,
    expiry,
    spot: float,
    band: float = 0.10,
    min_strikes: int = 3,
) -> tuple[float, float]:
    """Regress the forward and discount factor out of the chain via put-call parity.

    Across strikes carrying both legs, ``C - K`` is linear in ``K``::

        C - P = F * D - K * D

    so an OLS of ``C - P`` on ``K`` returns slope ``-D`` and intercept ``F * D``. Only
    strikes within ``band`` of spot are used: far strikes have one near-worthless leg
    whose print is unreliable and whose parity residual is dominated by staleness.

    Falls back to ``(spot, 1.0)`` when the chain cannot support the fit, which reduces
    the mark to the naive spot-intrinsic form rather than failing outright.

    Parameters
    ----------
    chain : pd.DataFrame
        Canonical chain.
    expiry : datetime-like
        The expiry to fit.
    spot : float
        Underlying price, used only to centre the strike band.
    band : float, optional
        Half-width of the strike window as a fraction of spot. Defaults to ``0.10``.
    min_strikes : int, optional
        Minimum paired strikes required to attempt the fit. Defaults to ``3``.

    Returns
    -------
    tuple of float
        ``(forward, discount_factor)``.
    """
    sub = chain[chain["expiry"] == expiry]
    if sub.empty or not np.isfinite(spot) or spot <= 0:
        return float(spot), 1.0

    # Mid on both sides. A bid-bid regression biases the fitted forward and discount by
    # the difference in the two legs' half-spreads, which is not zero once quotes are
    # real: the call and put at one strike are not equally liquid after an earnings gap.
    quoted = add_quote_columns(sub)
    calls = quoted[quoted["right"] == "C"].set_index("strike")["mid"]
    puts = quoted[quoted["right"] == "P"].set_index("strike")["mid"]
    ks = calls.index.intersection(puts.index)
    ks = ks[(ks >= spot * (1 - band)) & (ks <= spot * (1 + band))]
    if len(ks) < min_strikes:
        return float(spot), 1.0

    k = np.asarray(ks, dtype=float)
    y = np.asarray(calls.loc[ks], dtype=float) - np.asarray(puts.loc[ks], dtype=float)
    ok = np.isfinite(k) & np.isfinite(y)
    if ok.sum() < min_strikes:
        return float(spot), 1.0

    slope, intercept = np.polyfit(k[ok], y[ok], 1)
    disc = -float(slope)
    # A discount factor outside this range is a fitting artefact on stale legs, not a
    # real financing rate at these maturities. Fall back rather than propagate nonsense.
    if not (0.90 <= disc <= 1.02):
        return float(spot), 1.0
    fwd = float(intercept) / disc
    if not np.isfinite(fwd):
        return float(spot), 1.0
    # The forward on a sub-90-day equity option cannot sit far from spot. A wide gap
    # means the *chain* is stale, not that the forward is exotic - and a stale forward
    # would silently corrupt every mark built on it. Distrust it and use spot.
    if abs(fwd / spot - 1.0) > FORWARD_SANITY_BAND:
        return float(spot), 1.0
    return fwd, disc


def mark_straddle(
    chain: pd.DataFrame,
    *,
    expiry,
    strike: float,
    spot: float,
    repair: bool = True,
    uniform: bool = False,
) -> StraddleMark:
    """Mark an ATM-struck straddle off a chain, immune to a stale in-the-money leg.

    Parameters
    ----------
    chain : pd.DataFrame
        Canonical chain (``expiry``, ``strike``, ``right``, ``bid``, ``ask``, ...).
        On close-marked feeds ``bid == ask == close``.
    expiry : datetime-like
        Contract expiry.
    strike : float
        The traded strike.
    spot : float
        Underlying price contemporaneous with the chain.
    repair : bool, optional
        Use the parity rebuild. False reproduces the unrepaired historical book.
    uniform : bool, optional
        Apply the rebuild to every event (True) or only where the raw mark is
        physically impossible (False). **False is the correct default**, for a reason
        worth stating because the opposite looks tempting.

        The raw mark is an actual traded price and is the best available estimate
        whenever it is valid. The parity rebuild is a *reconstruction*, and it is
        biased: it doubles the OTM leg, so any bid-side bias in that cheap leg is
        doubled too. Measured on the mega-cap book, the rebuild sits a median 1.2% of
        the entry credit *below* the raw mark on events whose raw mark is trustworthy.
        A low exit mark understates the buy-back and flatters a short.

        So applying it uniformly would inject that flattering bias into all 192 trades
        (which is exactly what it does: uniform lifts the per-trade Sharpe to +0.087
        against +0.060 conditional). Repairing only the impossible marks is data-validity
        cleaning, not outcome-correlated selection, and it is the conservative read.

    Returns
    -------
    StraddleMark

    Notes
    -----
    Even the conditional repair remains mildly optimistic, because the ~1.2% rebuild
    bias still applies to the 48 events it does touch. The honest floor on those events
    is forward intrinsic itself, which is a hard no-arbitrage bound.
    """
    call = _leg(chain, expiry, strike, "C")
    put = _leg(chain, expiry, strike, "P")
    raw = call + put  # NaN-propagating by design

    fwd, disc = implied_forward(chain, expiry=expiry, spot=spot)
    # Moneyness is judged against the forward, which is what parity actually prices.
    otm = put if fwd > strike else call
    fwd_intrinsic = abs(fwd - float(strike)) * disc
    intr = abs(float(spot) - float(strike))  # spot intrinsic, for the audit bound

    violated = bool(np.isfinite(raw) and (intr - raw) > VIOLATION_TOL)

    price, repaired = raw, False
    if repair and np.isfinite(otm) and (uniform or violated):
        price = fwd_intrinsic + 2.0 * otm
        repaired = True
        # Backstop. If the rebuild *still* lands below spot intrinsic, the chain's own
        # forward was stale too and the parity fit cannot be trusted for this event.
        # Fall back to the hard no-arbitrage bound rather than emit a second impossible
        # price - a repair that quietly reintroduces the bug it exists to fix is worse
        # than no repair at all.
        if np.isfinite(price) and (intr - price) > VIOLATION_TOL:
            price = intr + 2.0 * max(otm, 0.0)

    return StraddleMark(
        price=price,
        call=call,
        put=put,
        intrinsic=intr,
        raw_price=raw,
        otm_leg=otm,
        violated=violated,
        repaired=repaired,
    )


def audit_marks(
    marks: pd.DataFrame,
    *,
    price_col: str = "price",
    intrinsic_col: str = "intrinsic",
    label: str = "marks",
    raise_above: float | None = None,
) -> dict[str, float]:
    """Funnel a set of marks and complain when they breach no-arbitrage.

    A gate that can silently emit an impossible price is worse than one that
    fails, because the impossible price is *directional*: a below-intrinsic exit
    mark flatters a short straddle and hides the loss. This function makes the
    breach visible, and optionally fatal.

    Parameters
    ----------
    marks : pd.DataFrame
        Must carry ``price_col`` and ``intrinsic_col``.
    raise_above : float or None
        Raise when the violation rate exceeds this fraction. None only warns.

    Returns
    -------
    dict
        ``n``, ``n_violating``, ``rate``, ``median_violation``, ``max_violation``.

    Raises
    ------
    ValueError
        When the violation rate exceeds ``raise_above``.
    """
    d = marks.dropna(subset=[price_col, intrinsic_col])
    short = d[intrinsic_col] - d[price_col]
    bad = short > VIOLATION_TOL
    stats = {
        "n": float(len(d)),
        "n_violating": float(bad.sum()),
        "rate": float(bad.mean()) if len(d) else 0.0,
        "median_violation": float(short[bad].median()) if bad.any() else 0.0,
        "max_violation": float(short[bad].max()) if bad.any() else 0.0,
    }
    if bad.any():
        msg = (
            f"{label}: {int(stats['n_violating'])}/{int(stats['n'])} "
            f"({stats['rate']:.1%}) marks below intrinsic; "
            f"median ${stats['median_violation']:.2f}, max ${stats['max_violation']:.2f}. "
            "A straddle cannot trade below |S-K|; these are stale prints and they "
            "flatter a short book."
        )
        if raise_above is not None and stats["rate"] > raise_above:
            raise ValueError(msg)
        warnings.warn(msg, RuntimeWarning, stacklevel=2)
    return stats
