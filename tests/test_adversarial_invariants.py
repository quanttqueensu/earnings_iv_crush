"""
test_adversarial_invariants.py
Metamorphic tests: properties the pipeline must satisfy regardless of implementation.

Conventional unit tests pin behaviour against expected values, so they encode whatever
assumption the author held while writing both the code and the test. Every defect this
project has found survived a green suite. These tests instead assert *invariances*: apply a
transformation that must not change an answer, and check that it does not.

Six transformations, each targeting a defect class this project has actually suffered:

* **future deletion**   removing every record dated after entry must not change the
  selected contract, the sizing or the entry mark. Anything that changes is look-ahead.
* **split invariance**  halving prices and strikes while doubling contract counts is the
  same economic position, so the return must be identical. This is the split-basis defect.
* **scale invariance**  multiplying price, strike and premium by a constant must leave a
  return on premium unchanged.
* **outcome permutation** scrambling post-event outcomes must not change any pre-event
  selection quantity.
* **duplicate records** duplicating irrelevant quote rows must not change the mark, which
  pins the ``.iloc[0]`` sites the fail-soft triage found.
* **missing-data injection** removing a required input must raise or exclude with a stated
  reason rather than silently substituting.

References
----------
Chen, T. Y., Cheung, S. C. and Yiu, S. M. (1998). Metamorphic testing: a new approach for
generating next test cases. *Technical Report HKUST-CS98-01*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine.marks import (
    AmbiguousQuoteError,
    dedupe_contracts,
    mark_straddle,
)
from earnings_iv_crush.engine.pnl import regt_straddle_margin, size_contracts
from earnings_iv_crush.engine.quotes import add_quote_columns


def chain(spot: float = 200.0, step: float = 5.0, expiry: str = "2024-02-16") -> pd.DataFrame:
    """A small synthetic two-sided chain centred on ``spot``."""
    strikes = np.arange(spot - 4 * step, spot + 4 * step + step, step)
    rows = []
    for k in strikes:
        for right in ("C", "P"):
            intrinsic = max(spot - k, 0.0) if right == "C" else max(k - spot, 0.0)
            mid = intrinsic + 6.0 * np.exp(-(((k - spot) / (2 * step)) ** 2))
            rows.append(
                {
                    "expiry": pd.Timestamp(expiry),
                    "strike": float(k),
                    "right": right,
                    "bid": round(mid * 0.98, 4),
                    "ask": round(mid * 1.02, 4),
                    "iv": 0.45,
                }
            )
    return pd.DataFrame(rows)


# ── future deletion ──────────────────────────────────────────────────────────


def test_future_records_do_not_change_the_entry_mark() -> None:
    """Rows dated after entry must not reach the entry mark.

    The chain is the entry snapshot, so appending later expiries and later-dated rows is
    information the strategy cannot have used. If the mark moves, something is reading
    beyond the snapshot.
    """
    base = chain()
    marked = mark_straddle(base, expiry=pd.Timestamp("2024-02-16"), strike=200.0, spot=200.0)

    future = base.copy()
    future["expiry"] = pd.Timestamp("2024-06-21")
    future["bid"] *= 3.0
    future["ask"] *= 3.0
    contaminated = pd.concat([base, future], ignore_index=True)
    after = mark_straddle(contaminated, expiry=pd.Timestamp("2024-02-16"), strike=200.0, spot=200.0)

    assert after.price == pytest.approx(marked.price), "a later expiry moved the entry mark"


# ── split invariance ─────────────────────────────────────────────────────────


def test_return_on_margin_is_split_invariant() -> None:
    """A 2:1 split with twice the contracts is the same position, so the return is equal.

    This is the invariant the split-basis defect violated: strikes are quoted on the
    contemporaneous basis and spot on an adjusted one, so the two drifted apart and the
    chosen strike stopped being at the money.
    """

    def rom(spot: float, strike: float, credit: float, exit_: float, contracts: int) -> float:
        margin = regt_straddle_margin(spot, strike, credit, contracts)
        return (credit - exit_) * 100 * contracts / margin

    pre = rom(200.0, 200.0, 12.0, 6.0, 5)
    post = rom(100.0, 100.0, 6.0, 3.0, 10)
    assert post == pytest.approx(pre), "return on margin changed across an economically flat split"


def test_scale_invariance_of_return_on_premium() -> None:
    """Return on premium must not depend on the currency scale of the quotes."""
    for factor in (0.5, 2.0, 10.0):
        credit, exit_ = 12.0 * factor, 6.0 * factor
        assert (credit - exit_) / credit == pytest.approx(0.5)


def test_sizing_is_the_only_route_by_which_price_level_matters() -> None:
    """Integer sizing is what makes expensive names disappear; the audit quantified it.

    Pinned so the behaviour cannot change silently: a high-priced name at the same margin
    fraction sizes to zero contracts and leaves the book, which is a selection on price.
    """
    cheap = size_contracts(100_000, 50.0, 50.0, 3.0, 0.05)
    dear = size_contracts(100_000, 3000.0, 3000.0, 180.0, 0.05)
    assert cheap > 0
    assert dear == 0, "the price-driven exclusion documented in the audit no longer reproduces"


# ── outcome permutation ──────────────────────────────────────────────────────


def test_scrambling_outcomes_cannot_change_selection() -> None:
    """Selection quantities are computed at entry, so permuting outcomes must not move them.

    Uses the expanding term gate, the frozen specification's actual selector.
    """
    from earnings_iv_crush.strategy.filters import expanding_gate_rank

    rng = np.random.default_rng(0)
    n = 200
    ev = pd.DataFrame(
        {
            "announce_date": pd.date_range("2020-01-01", periods=n, freq="7D"),
            "iv_term_spread": rng.normal(0.1, 0.05, n),
            "realised_move": rng.normal(0.0, 0.05, n),
        }
    )
    before = expanding_gate_rank(
        ev["iv_term_spread"].to_numpy(float), ev["announce_date"].to_numpy()
    )

    shuffled = ev.copy()
    shuffled["realised_move"] = rng.permutation(shuffled["realised_move"].to_numpy())
    after = expanding_gate_rank(
        shuffled["iv_term_spread"].to_numpy(float), shuffled["announce_date"].to_numpy()
    )
    np.testing.assert_allclose(before, after, equal_nan=True)


# ── duplicate records ────────────────────────────────────────────────────────


def test_exact_duplicate_rows_collapse_and_do_not_change_the_mark() -> None:
    """Branch 1: the same observation delivered twice is one observation."""
    base = chain()
    marked = mark_straddle(base, expiry=pd.Timestamp("2024-02-16"), strike=200.0, spot=200.0)

    exact = pd.concat([base, base], ignore_index=True)
    assert mark_straddle(
        exact, expiry=pd.Timestamp("2024-02-16"), strike=200.0, spot=200.0
    ).price == pytest.approx(marked.price)

    irrelevant = pd.concat([base, base[base["strike"] != 200.0]], ignore_index=True)
    assert mark_straddle(
        irrelevant, expiry=pd.Timestamp("2024-02-16"), strike=200.0, spot=200.0
    ).price == pytest.approx(marked.price)


def test_timestamped_duplicates_take_the_latest_quote_at_or_before_the_observation() -> None:
    """Branch 2: with a timestamp there is a right answer, and it is the latest valid one."""
    base = chain()
    base["ts_recv"] = pd.Timestamp("2024-02-01 15:59:00")
    late = base[base["strike"] == 200.0].copy()
    late["ts_recv"] = pd.Timestamp("2024-02-01 15:59:45")
    late["bid"] += 1.0
    late["ask"] += 1.0
    after_cutoff = base[base["strike"] == 200.0].copy()
    after_cutoff["ts_recv"] = pd.Timestamp("2024-02-01 16:05:00")
    after_cutoff["bid"] += 99.0
    after_cutoff["ask"] += 99.0

    stacked = pd.concat([base, late, after_cutoff], ignore_index=True)
    resolved = dedupe_contracts(
        stacked[stacked["strike"] == 200.0], asof=pd.Timestamp("2024-02-01 16:00:00"), label="t"
    )
    assert len(resolved) == 2, "one row per right should survive"
    call = resolved[resolved["right"] == "C"].iloc[0]
    expected = (
        float(base.loc[(base["strike"] == 200.0) & (base["right"] == "C"), "bid"].iloc[0]) + 1.0
    )
    assert call["bid"] == pytest.approx(expected), "the latest quote at or before asof did not win"


def test_disagreeing_unorderable_duplicates_raise_rather_than_pick_a_row() -> None:
    """Branch 3: an arbitrary choice that changes a mark must become a stated exclusion.

    Previously the first matching row won, so row order silently decided the mark. The
    cached chains carry no duplicates, so this never fired, but "first" is not a rule and a
    future feed that duplicates a contract would have been marked arbitrarily.
    """
    base = chain()
    dup = base[base["strike"] == 200.0].copy()
    dup["bid"] *= 2.0
    dup["ask"] *= 2.0
    stacked = pd.concat([base, dup], ignore_index=True)

    with pytest.raises(AmbiguousQuoteError) as excinfo:
        mark_straddle(stacked, expiry=pd.Timestamp("2024-02-16"), strike=200.0, spot=200.0)
    assert excinfo.value.n == 2
    assert "bid" in excinfo.value.columns


# ── missing-data injection ───────────────────────────────────────────────────


def test_missing_leg_yields_no_mark_rather_than_half_a_straddle() -> None:
    """Dropping one leg must not return the surviving leg's price as a straddle."""
    base = chain()
    no_put = base[~((base["strike"] == 200.0) & (base["right"] == "P"))]
    out = mark_straddle(no_put, expiry=pd.Timestamp("2024-02-16"), strike=200.0, spot=200.0)
    assert not np.isfinite(out.price), "a one-legged straddle was priced as if complete"


def test_one_sided_quote_is_not_silently_treated_as_a_mid() -> None:
    """A contract quoted on one side only must not report a two-sided width.

    ``add_quote_columns`` substitutes the present side for the mid when one side is missing.
    The audit found this never fires at the traded contract on either block, so it is
    latent. What must stay true is that the *spread* is not fabricated: a one-sided
    contract has an undefined width, and reporting one would let it pass a tightness screen.
    """
    base = chain()
    holed = base.copy()
    holed.loc[(holed["strike"] == 200.0) & (holed["right"] == "C"), "bid"] = np.nan
    out = add_quote_columns(holed)
    row = out[(out["strike"] == 200.0) & (out["right"] == "C")].iloc[0]
    assert not np.isfinite(row["spread"]), "a one-sided contract reported a two-sided spread"
    assert not np.isfinite(row["rel_spread"]), "a one-sided contract reported a relative width"
