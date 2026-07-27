"""Quote-side selection and hygiene.

The load-bearing property is backward compatibility: on a close-marked chain
(``bid == ask == close``) every function here must reproduce the close exactly, because
the entire historical book was marked that way and the quote migration is only safe if
it is a no-op until real two-sided quotes arrive. That is asserted first and hardest.

The second is that a locked market must not be treated as an error. Every cached chain
in this repo is locked by construction, so disqualifying locked quotes would empty the
whole book; only a crossed market is a genuine data fault.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine.quotes import (
    REASON_CROSSED,
    REASON_WIDE,
    REASON_ZERO_BID,
    add_quote_columns,
    clean_chain,
    flag_quotes,
    format_funnel,
    side_price,
)


def _close_marked() -> pd.DataFrame:
    """A chain as the trade-based adapters build it: bid == ask == close."""
    close = [1.25, 2.50, 0.75, 3.10]
    return pd.DataFrame(
        {
            "expiry": pd.to_datetime(["2024-02-02"] * 4),
            "strike": [180.0, 185.0, 190.0, 185.0],
            "right": ["C", "C", "C", "P"],
            "bid": close,
            "ask": close,
        }
    )


def _quoted() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "expiry": pd.to_datetime(["2024-02-02"] * 5),
            "strike": [180.0, 185.0, 190.0, 195.0, 200.0],
            "right": ["C"] * 5,
            "bid": [1.20, 2.45, 0.00, 3.00, 5.00],  # third has no bid
            "ask": [1.30, 2.55, 0.10, 2.90, 5.60],  # fourth is crossed
        }
    )


# ── backward compatibility on close-marked data ──────────────────────────────


def test_close_marked_mid_equals_close_exactly() -> None:
    chain = _close_marked()
    out = add_quote_columns(chain)
    assert (out["mid"].to_numpy() == chain["bid"].to_numpy()).all()
    assert (out["spread"] == 0.0).all()
    assert (out["rel_spread"] == 0.0).all()


def test_close_marked_chain_is_entirely_usable() -> None:
    """The historical book must survive the hygiene layer untouched."""
    flagged = flag_quotes(_close_marked())
    assert flagged["usable"].all()
    assert flagged["is_locked"].all()  # locked is the normal state, not a fault
    assert not flagged["is_crossed"].any()
    assert not flagged["is_wide"].any()


def test_clean_chain_drops_nothing_when_close_marked() -> None:
    chain = _close_marked()
    funnel: dict[str, int] = {}
    kept = clean_chain(chain, funnel=funnel)
    assert len(kept) == len(chain)
    assert funnel["kept"] == funnel["seen"] == len(chain)


# ── side selection ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("side", "expected"),
    [("mid", 1.25), ("bid", 1.20), ("ask", 1.30)],
)
def test_side_price_selects_the_requested_side(side: str, expected: float) -> None:
    assert side_price(1.20, 1.30, side) == pytest.approx(expected)


@pytest.mark.parametrize("side", ["mid", "bid", "ask"])
def test_one_sided_quote_falls_back_to_the_present_side(side: str) -> None:
    assert side_price(np.nan, 2.0, side) == pytest.approx(2.0)
    assert side_price(2.0, np.nan, side) == pytest.approx(2.0)


def test_side_price_is_nan_when_wholly_unquoted() -> None:
    assert np.isnan(side_price(np.nan, np.nan, "mid"))


def test_mid_sits_between_the_sides() -> None:
    """The property that motivates the module: no directional bias."""
    assert side_price(1.20, 1.30, "bid") < side_price(1.20, 1.30, "mid")
    assert side_price(1.20, 1.30, "mid") < side_price(1.20, 1.30, "ask")


# ── hygiene ──────────────────────────────────────────────────────────────────


def test_crossed_quote_is_flagged_and_dropped() -> None:
    flagged = flag_quotes(_quoted())
    crossed = flagged[flagged["strike"] == 195.0].iloc[0]  # bid 3.00 > ask 2.90
    assert bool(crossed["is_crossed"])
    assert not bool(crossed["usable"])


def test_locked_quote_is_flagged_but_kept() -> None:
    chain = pd.DataFrame(
        {
            "expiry": pd.to_datetime(["2024-02-02"]),
            "strike": [185.0],
            "right": ["C"],
            "bid": [2.50],
            "ask": [2.50],
        }
    )
    flagged = flag_quotes(chain)
    assert bool(flagged["is_locked"].iloc[0])
    assert bool(flagged["usable"].iloc[0])


def test_zero_bid_is_flagged_and_dropped() -> None:
    flagged = flag_quotes(_quoted())
    zero = flagged[flagged["strike"] == 190.0].iloc[0]
    assert bool(zero["is_zero_bid"])
    assert not bool(zero["usable"])


def test_wide_quote_is_dropped_at_the_configured_threshold() -> None:
    """5.00/5.60 is an 11.3% relative spread: kept at 0.20, dropped at 0.10."""
    wide_only = _quoted()[lambda d: d["strike"] == 200.0]
    assert flag_quotes(wide_only, max_rel_spread=0.20)["usable"].all()
    assert not flag_quotes(wide_only, max_rel_spread=0.10)["usable"].any()


def test_funnel_accounts_for_every_contract() -> None:
    funnel: dict[str, int] = {}
    kept = clean_chain(_quoted(), max_rel_spread=0.10, funnel=funnel)
    assert funnel["seen"] == 5
    assert funnel["kept"] == len(kept) == 2  # 180 and 185 survive
    assert funnel[REASON_CROSSED] == 1
    assert funnel[REASON_ZERO_BID] == 1
    # Flags are independent, so a contract may trip several: the 190 strike is both
    # zero-bid and wide (0.00/0.10 is a 200% relative spread). The reason counts are a
    # diagnosis of what is wrong with the chain, not a partition of the dropped rows.
    assert funnel[REASON_WIDE] == 2


def test_funnel_accumulates_across_calls() -> None:
    """Callers pass one dict across a whole build; counts must add, not reset."""
    funnel: dict[str, int] = {}
    clean_chain(_quoted(), max_rel_spread=0.10, funnel=funnel)
    clean_chain(_quoted(), max_rel_spread=0.10, funnel=funnel)
    assert funnel["seen"] == 10
    assert funnel[REASON_CROSSED] == 2


def test_format_funnel_reports_only_nonzero_reasons() -> None:
    funnel: dict[str, int] = {}
    clean_chain(_quoted(), max_rel_spread=0.10, funnel=funnel)
    text = format_funnel(funnel, label="entry chain")
    assert "entry chain funnel: 5 contracts -> 2 usable (dropped 3)" in text
    assert REASON_CROSSED in text
    assert "no_quote" not in text  # zero count, so omitted


def test_rel_spread_is_nan_rather_than_infinite_at_zero_mid() -> None:
    chain = pd.DataFrame(
        {
            "expiry": pd.to_datetime(["2024-02-02"]),
            "strike": [185.0],
            "right": ["C"],
            "bid": [0.0],
            "ask": [0.0],
        }
    )
    assert np.isnan(add_quote_columns(chain)["rel_spread"].iloc[0])
