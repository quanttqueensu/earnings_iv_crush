"""
simulate.py
Synthetic earnings-event generator for the crude backtest and tests.

NOT a production data source and NOT a claim of edge. It plants a controlled
structure so the end-to-end wiring (fair-move model -> filter -> ledger ->
backtest) can be validated against a known answer: a fraction of events are
"rich" (the market overprices the move, the term spread is wide, and IV crushes
hard post-event) while the rest are fairly priced. A working filter should
concentrate on the rich events and beat the unfiltered Agent 0 control. Whether
a real edge exists is an empirical question for the historical backtest.

The generated frame carries both the filter features and the execution columns
the ledger builder needs, so it stands in for `data_pipeline.build_event_dataset`
joined to realised outcomes until historical option data lands.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ATM straddle price ~= 0.8 * spot * sigma * sqrt(t), so implied move (straddle
# / spot) ~= 0.8 * sigma * sqrt(t). We invert this to keep iv_entry and
# implied_move mutually consistent.
_STRADDLE_K = 0.8


_SECTORS = ("Tech", "Financials", "Healthcare", "Energy", "Consumer", "Industrials")


def simulate_events(
    n: int = 300,
    seed: int = 0,
    edge_frac: float = 0.35,
    holding_days: int = 2,
    days_to_expiry: int = 7,
    spot: float = 100.0,
    with_vix: bool = False,
    high_vix_frac: float = 0.20,
    vix_low: float = 15.0,
    vix_high: float = 30.0,
    with_sectors: bool = False,
) -> pd.DataFrame:
    """
    Generate ``n`` synthetic pre-earnings events with a planted edge.

    ``edge_frac`` of events are rich (profitable to short); the rest are fair
    (break-even before costs, ~0 Sharpe like Agent 0).

    Optional enrichment (all defaulting off, so existing callers are unchanged):

    * ``with_vix`` adds a ``vix`` column where ``high_vix_frac`` of events sit at
      ``vix_high`` (a defensive, iron-fly regime) and the rest at ``vix_low`` with
      mild jitter. Lets the regime selector (``strategy.regime``) be exercised.
    * ``with_sectors`` adds a GICS-like ``sector`` column so the concentration
      caps (``engine.risk``) can be exercised.

    Parameters
    ----------
    n : int
        Number of events to generate. Defaults to ``300``.
    seed : int
        Seed for the random generator. Defaults to ``0``.
    edge_frac : float
        Fraction of events that are rich (overpriced move, wide term spread,
        hard post-event crush). Defaults to ``0.35``.
    holding_days : int
        Business days the position is held after entry. Defaults to ``2``.
    days_to_expiry : int
        Calendar days from entry to the front expiry. Defaults to ``7``.
    spot : float
        Underlying spot at entry. Defaults to ``100.0``.
    with_vix : bool
        Add a ``vix`` column for the regime selector. Defaults to ``False``.
    high_vix_frac : float
        Fraction of events placed in the defensive high-VIX regime when
        ``with_vix`` is set. Defaults to ``0.20``.
    vix_low, vix_high : float
        Calm and defensive VIX levels. Default to ``15.0`` and ``30.0``.
    with_sectors : bool
        Add a GICS-like ``sector`` column for the concentration caps. Defaults
        to ``False``.

    Returns
    -------
    pd.DataFrame
        One row per event carrying both the filter features and the execution
        columns the ledger builder needs, plus an ``is_rich`` ground-truth flag
        (and ``vix`` / ``sector`` when the corresponding flags are set).
    """
    rng = np.random.default_rng(seed)
    t_entry = days_to_expiry / 365.0
    t_exit = (days_to_expiry - holding_days) / 365.0

    rich = rng.random(n) < edge_frac
    trailing_rv = rng.uniform(0.20, 0.50, n)
    skew_25d = rng.uniform(-0.02, 0.08, n)

    # True fair move fraction (a function of the features the model can see).
    fair_move = 0.03 + 0.05 * trailing_rv + 0.20 * skew_25d

    # Market pricing: rich events overprice the move; fair events price it right.
    mult = np.where(rich, rng.uniform(1.30, 1.80, n), rng.uniform(0.90, 1.10, n))
    implied_move = fair_move * mult
    iv_entry = implied_move / (_STRADDLE_K * np.sqrt(t_entry))

    # Term structure: rich events show a wide front-minus-back spread.
    ts = np.where(rich, rng.uniform(0.15, 0.30, n), rng.uniform(-0.02, 0.05, n))
    back_atm_iv = iv_entry * (1 - ts)
    iv_term_spread = iv_entry - back_atm_iv

    # Post-event crush: rich events crush harder.
    crush = np.where(rich, rng.uniform(0.25, 0.40, n), rng.uniform(0.45, 0.65, n))
    iv_exit = iv_entry * crush

    # Realised move depends on the truth, not on mispricing. Wide dispersion
    # plus an occasional gap (fat tail) so even rich shorts sometimes lose.
    realised_abs = np.clip(rng.normal(fair_move, 0.45 * fair_move), 0.0, None)
    gap = rng.random(n) < 0.10
    realised_abs = np.where(gap, realised_abs * rng.uniform(2.5, 4.0, n), realised_abs)
    sign = rng.choice([-1.0, 1.0], size=n)
    spot_exit = spot * (1 + sign * realised_abs)

    strike = round(spot / 5) * 5
    entry = pd.bdate_range("2026-01-02", periods=n)
    exit_ = entry + pd.tseries.offsets.BDay(holding_days)

    out = pd.DataFrame(
        {
            "ticker": [f"SYN{i:04d}" for i in range(n)],
            "announce_date": entry,
            "entry_date": entry.astype(str),
            "exit_date": exit_.astype(str),
            "spot_entry": spot,
            "strike": float(strike),
            "t_entry": t_entry,
            "t_exit": t_exit,
            "iv_entry": iv_entry,
            "iv_exit": iv_exit,
            "spot_exit": spot_exit,
            "front_atm_iv": iv_entry,
            "back_atm_iv": back_atm_iv,
            "iv_term_spread": iv_term_spread,
            "implied_move": implied_move,
            "trailing_rv": trailing_rv,
            "skew_25d": skew_25d,
            "realised_move": realised_abs,
            "is_rich": rich,
        }
    )

    if with_vix:
        defensive = rng.random(n) < high_vix_frac
        out["vix"] = np.where(defensive, vix_high, vix_low + rng.uniform(-2.0, 4.0, n))
    if with_sectors:
        out["sector"] = rng.choice(_SECTORS, size=n)

    return out
