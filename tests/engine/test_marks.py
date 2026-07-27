"""Tests for engine.marks: parity marking and the no-arbitrage audit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine.marks import (
    VIOLATION_TOL,
    audit_marks,
    implied_forward,
    mark_straddle,
)

EXPIRY = pd.Timestamp("2024-02-02")


def _chain(spot: float, strikes, disc: float = 1.0, vol: float = 0.30, t: float = 7 / 365):
    """A clean synthetic chain that satisfies put-call parity exactly."""
    from earnings_iv_crush.engine.greeks import bs_price

    fwd = spot / disc
    rows = []
    for k in strikes:
        c = bs_price(spot, k, t, 0.0, vol, "C")
        # Put from parity so the chain is internally consistent by construction.
        p = c - (fwd - k) * disc
        rows.append(
            {
                "expiry": EXPIRY,
                "strike": float(k),
                "right": "C",
                "bid": c,
                "ask": c,
                "iv": vol,
                "open_interest": None,
            }
        )
        rows.append(
            {
                "expiry": EXPIRY,
                "strike": float(k),
                "right": "P",
                "bid": p,
                "ask": p,
                "iv": vol,
                "open_interest": None,
            }
        )
    return pd.DataFrame(rows)


def test_implied_forward_recovers_spot_on_a_clean_chain():
    chain = _chain(100.0, np.arange(92, 109, 1.0))
    fwd, disc = implied_forward(chain, expiry=EXPIRY, spot=100.0)
    assert fwd == pytest.approx(100.0, abs=0.05)
    assert disc == pytest.approx(1.0, abs=1e-3)


def test_clean_chain_is_left_alone():
    """A mark that clears intrinsic must not be touched by the conditional repair."""
    chain = _chain(100.0, np.arange(92, 109, 1.0))
    m = mark_straddle(chain, expiry=EXPIRY, strike=100.0, spot=100.0)
    assert not m.violated
    assert not m.repaired
    assert m.price == pytest.approx(m.raw_price)


def test_stale_itm_leg_is_detected_and_repaired():
    """The exact failure seen in the book: the stock gapped, so the chain is priced at
    the *new* spot, but the deep-ITM leg's own last print is stale and marks the
    straddle below |S - K|. The repair must fire and restore no-arbitrage."""
    spot = 112.0  # post-gap; the rest of the chain reprices, one leg does not
    chain = _chain(spot, np.arange(104, 121, 1.0))
    # The traded strike (100, struck at the money pre-gap) is now deep ITM. Add it back
    # carrying a stale pre-gap price.
    stale = pd.DataFrame(
        [
            {
                "expiry": EXPIRY,
                "strike": 100.0,
                "right": "C",
                "bid": 3.0,
                "ask": 3.0,
                "iv": 0.3,
                "open_interest": None,
            },
            {
                "expiry": EXPIRY,
                "strike": 100.0,
                "right": "P",
                "bid": 0.20,
                "ask": 0.20,
                "iv": 0.3,
                "open_interest": None,
            },
        ]
    )
    chain = pd.concat([chain, stale], ignore_index=True)

    m = mark_straddle(chain, expiry=EXPIRY, strike=100.0, spot=spot)
    assert m.violated, "a straddle marked below |S-K| must be flagged"
    assert m.repaired
    assert m.raw_price < m.intrinsic
    assert m.price >= m.intrinsic - VIOLATION_TOL, "the repair must restore no-arbitrage"


def test_repair_never_emits_a_sub_intrinsic_price_even_on_a_stale_chain():
    """Backstop: if the whole chain is stale, the implied forward is stale too and the
    parity rebuild would itself land below intrinsic. It must fall back to the bound
    rather than emit a second impossible price."""
    chain = _chain(100.0, np.arange(92, 109, 1.0))  # chain priced at 100...
    spot = 112.0  # ...but the stock is actually at 112: everything is stale
    m = mark_straddle(chain, expiry=EXPIRY, strike=100.0, spot=spot)
    assert m.price >= m.intrinsic - VIOLATION_TOL


def test_repair_can_be_disabled_to_reproduce_the_raw_book():
    spot = 112.0
    chain = _chain(spot, np.arange(104, 121, 1.0))
    stale = pd.DataFrame(
        [
            {
                "expiry": EXPIRY,
                "strike": 100.0,
                "right": "C",
                "bid": 3.0,
                "ask": 3.0,
                "iv": 0.3,
                "open_interest": None,
            },
            {
                "expiry": EXPIRY,
                "strike": 100.0,
                "right": "P",
                "bid": 0.20,
                "ask": 0.20,
                "iv": 0.3,
                "open_interest": None,
            },
        ]
    )
    chain = pd.concat([chain, stale], ignore_index=True)
    m = mark_straddle(chain, expiry=EXPIRY, strike=100.0, spot=spot, repair=False)
    assert m.violated
    assert not m.repaired
    assert m.price == pytest.approx(m.raw_price)


def test_missing_leg_yields_nan_not_a_half_mark():
    """A one-legged straddle would silently understate a short's buy-back."""
    chain = _chain(100.0, np.arange(92, 109, 1.0))
    chain = chain[~((chain["strike"] == 100.0) & (chain["right"] == "P"))]
    m = mark_straddle(chain, expiry=EXPIRY, strike=100.0, spot=100.0)
    assert np.isnan(m.raw_price)


def test_audit_warns_on_below_intrinsic_marks():
    marks = pd.DataFrame({"price": [5.0, 1.0], "intrinsic": [0.0, 4.0]})
    with pytest.warns(RuntimeWarning, match="below intrinsic"):
        stats = audit_marks(marks)
    assert stats["n_violating"] == 1
    assert stats["rate"] == pytest.approx(0.5)


def test_audit_raises_when_over_threshold():
    marks = pd.DataFrame({"price": [1.0, 1.0], "intrinsic": [4.0, 4.0]})
    with pytest.raises(ValueError, match="below intrinsic"):
        audit_marks(marks, raise_above=0.10)


def test_audit_is_silent_on_a_clean_book():
    marks = pd.DataFrame({"price": [5.0, 6.0], "intrinsic": [0.0, 4.0]})
    stats = audit_marks(marks)
    assert stats["n_violating"] == 0
    assert stats["rate"] == 0.0
