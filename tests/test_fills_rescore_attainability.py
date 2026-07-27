"""
test_fills_rescore_attainability.py
The cheapest execution arm must never become the reported one.

``run_fills_rescore`` scores three cost bases. The cheapest, ``trade_conditional_print``,
is measured on completed prints, and prints cluster where the book happens to be tight, so
it describes spreads in states a strategy committed to transacting at a fixed timestamp
cannot select into. It produces the highest Sharpe of the three and is the one a reader
skimming the output is most likely to quote.

The risk is not forgetting. It is that a future collaborator, or an automated report
generator sorting arms by Sharpe, promotes it silently. These tests fail if the metadata
that marks it unusable is dropped, or if a "best" arm is selected without consulting it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

RESCORE = Path("outputs/research/fills_rescore.csv")
_REQUIRED = {
    "cost_basis",
    "attainability_status",
    "selection_condition",
    "recommended_for_inference",
    "charged_per_side",
    "sharpe_pooled",
}


@pytest.fixture(scope="module")
def rescore() -> pd.DataFrame:
    if not RESCORE.exists():
        pytest.skip(f"{RESCORE} absent; run scripts/run_fills_rescore.py")
    return pd.read_csv(RESCORE)


def test_attainability_metadata_is_present(rescore: pd.DataFrame) -> None:
    """Without these columns the distinction is invisible to anything reading the file."""
    assert _REQUIRED <= set(rescore.columns)


def test_trade_conditional_arm_is_marked_unusable(rescore: pd.DataFrame) -> None:
    row = rescore.set_index("cost_basis").loc["trade_conditional_print"]
    assert row["attainability_status"] == "selection_biased"
    assert str(row["recommended_for_inference"]).lower() == "no"


def test_the_recommended_arm_is_not_merely_the_highest_sharpe(rescore: pd.DataFrame) -> None:
    """The headline must not be selectable by sorting on Sharpe.

    This is the actual failure mode being guarded: the biased arm wins that sort. If this
    ever stops holding, the selection story has changed and the guard needs rewriting
    rather than deleting.
    """
    best = rescore.sort_values("sharpe_pooled").iloc[-1]
    assert best["cost_basis"] == "trade_conditional_print"
    assert str(best["recommended_for_inference"]).lower() == "no"


def test_a_recommended_arm_exists_and_is_the_fixed_time_book(rescore: pd.DataFrame) -> None:
    rec = rescore[rescore["recommended_for_inference"].astype(str).str.lower() == "yes"]
    assert len(rec) >= 1
    assert "measured_1559_snapshot" in set(rec["cost_basis"])


def test_the_biased_arm_is_cheaper_than_the_attainable_one(rescore: pd.DataFrame) -> None:
    """Sanity on the direction of the selection: conditioning on a print buys a tighter book."""
    idx = rescore.set_index("cost_basis")["charged_per_side"]
    assert idx["trade_conditional_print"] < idx["measured_1559_snapshot"]
