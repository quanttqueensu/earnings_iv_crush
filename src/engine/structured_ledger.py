"""structured_ledger.py
Book the regime-selected trade structure, not just the naked straddle.

Last night's iron-fly and calendar variants were priced and regime-selected but
the booked economics stayed the naked straddle. This module closes that gap: it
dispatches each event to the structure the regime selector picked, sizes it by
worst-case loss (1% of NAV), charges costs, and emits a common ledger schema the
backtester already scores. The naked-straddle path is unchanged and remains the
default elsewhere.

This module implements:

* ``STRUCTURED_COLUMNS``      — the common per-trade schema.
* ``build_structured_ledger`` — dispatch straddle / iron fly / calendar to a
  sized, costed ledger.

Notes
-----
Costs for the multi-leg structures are charged on the net premium turned over per
side; the four-leg iron fly therefore under-charges spread slightly versus a
per-leg model. Calendar back-month exit IV and tenor are derived from documented
defaults on the synthetic harness; real surfaces (the historical pipeline) supply
them directly.
"""

from __future__ import annotations

import pandas as pd

from ..config import STRATEGY
from ..strategy.regime import CALENDAR, IRON_FLY
from ..strategy.structures import calendar_pnl, iron_fly_pnl
from .costs import CostModel
from .greeks import straddle_price
from .pnl import ACCOUNT_SIZE, CONTRACT_MULTIPLIER, straddle_pnl
from .risk import RISK_FRAC_PER_TRADE, worst_case_size

STRUCTURED_COLUMNS = [
    "ticker", "entry_date", "exit_date", "structure", "contracts",
    "entry_credit", "exit_value", "cost", "pnl",
    "capital_at_risk", "return_on_risk",
]

PREMIUM_STOP_MULTIPLE = STRATEGY.premium_stop_multiple   # central config
DEFAULT_BACK_GAP_YEARS = 30.0 / 365.0
DEFAULT_BACK_CRUSH = 0.92


def _straddle_ps(spot: float, strike: float, t: float, r: float, sigma: float) -> float:
    """Straddle price per share, intrinsic at/after expiry."""
    if t <= 0 or sigma <= 0:
        return abs(spot - strike)
    return straddle_price(spot, strike, t, r, sigma)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────


def build_structured_ledger(events: pd.DataFrame, structures,
                            account: float = ACCOUNT_SIZE,
                            risk_frac: float = RISK_FRAC_PER_TRADE,
                            r: float = 0.0, costs: CostModel | None = None,
                            wing_mult: float = 1.5,
                            back_gap_years: float = DEFAULT_BACK_GAP_YEARS,
                            back_crush: float = DEFAULT_BACK_CRUSH) -> pd.DataFrame:
    """
    Book one trade per event in its regime-selected structure.

    Parameters
    ----------
    events : pd.DataFrame
        Per-event frame with the execution columns (``spot_entry``, ``strike``,
        ``t_entry``, ``t_exit``, ``iv_entry`` or ``front_atm_iv``, ``iv_exit``,
        ``spot_exit``) plus ``implied_move`` (iron fly) and ``back_atm_iv``
        (calendar).
    structures : sequence of str
        Structure label per event, aligned by position (``"straddle"``,
        ``"iron_fly"`` or ``"calendar"``), e.g. from ``regime.assign_structures``.
    account : float
        Net asset value for sizing. Defaults to ``250k``.
    risk_frac : float
        Fraction of NAV risked per position. Defaults to ``0.01`` (1%).
    r : float
        Risk-free rate (annualised). Defaults to ``0.0``.
    costs : CostModel, optional
        Cost model; ``None`` charges the commission-only default for the naked
        straddle and zero explicit cost for the defined-risk variants.
    wing_mult : float
        Iron-fly wing distance in implied-move multiples. Defaults to ``1.5``.
    back_gap_years, back_crush : float
        Synthetic-harness defaults for the calendar's back-month tenor gap and
        post-event back-month IV retention.

    Returns
    -------
    pd.DataFrame
        Ledger with ``STRUCTURED_COLUMNS``; ``pnl`` is net of costs and
        ``return_on_risk`` is ``pnl / capital_at_risk``. Events that size to zero
        contracts are skipped.
    """
    rows = []
    for (_, e), label in zip(events.iterrows(), list(structures)):
        spot = float(e["spot_entry"])
        strike = float(e["strike"])
        t_entry, t_exit = float(e["t_entry"]), float(e["t_exit"])
        iv_entry = float(e["iv_entry"] if "iv_entry" in e else e["front_atm_iv"])
        iv_exit, spot_exit = float(e["iv_exit"]), float(e["spot_exit"])

        if label == IRON_FLY:
            row = _book_iron_fly(e, spot, strike, t_entry, t_exit, iv_entry,
                                 iv_exit, spot_exit, account, risk_frac, r,
                                 costs, wing_mult)
        elif label == CALENDAR:
            row = _book_calendar(e, spot, strike, t_entry, t_exit, iv_entry,
                                 iv_exit, spot_exit, account, risk_frac, r,
                                 costs, back_gap_years, back_crush)
        else:
            row = _book_straddle(e, spot, strike, t_entry, t_exit, iv_entry,
                                 iv_exit, spot_exit, account, risk_frac, r, costs)
        if row is not None:
            rows.append(row)

    return pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)


# ─────────────────────────────────────────────────────────────────────────────
# Per-structure booking
# ─────────────────────────────────────────────────────────────────────────────


def _common(e, structure: str, contracts: int, entry_credit: float,
            exit_value: float, cost: float, pnl: float,
            capital_at_risk: float) -> dict:
    """Assemble one row in the common structured-ledger schema."""
    return {
        "ticker": e["ticker"],
        "entry_date": e["entry_date"],
        "exit_date": e["exit_date"],
        "structure": structure,
        "contracts": int(contracts),
        "entry_credit": float(entry_credit),
        "exit_value": float(exit_value),
        "cost": float(cost),
        "pnl": float(pnl),
        "capital_at_risk": float(capital_at_risk),
        "return_on_risk": float(pnl / capital_at_risk) if capital_at_risk else float("nan"),
    }


def _book_straddle(e, spot, strike, t_entry, t_exit, iv_entry, iv_exit,
                   spot_exit, account, risk_frac, r, costs):
    credit_ps = _straddle_ps(spot, strike, t_entry, r, iv_entry)
    contracts = worst_case_size(account, credit_ps, risk_frac=risk_frac)
    if contracts <= 0:
        return None
    exit_ps = _straddle_ps(spot_exit, strike, t_exit, r, iv_exit)
    pnl = straddle_pnl(spot, strike, t_entry, t_exit, iv_entry, iv_exit,
                       spot_exit, r, contracts, costs=costs)
    scale = CONTRACT_MULTIPLIER * contracts
    entry_credit = credit_ps * scale
    exit_value = exit_ps * scale
    gross = (credit_ps - exit_ps) * scale
    cost = gross - pnl   # whatever straddle_pnl deducted (commission-only or full)
    capital_at_risk = PREMIUM_STOP_MULTIPLE * entry_credit
    return _common(e, "straddle", contracts, entry_credit, exit_value, cost, pnl,
                   capital_at_risk)


def _book_iron_fly(e, spot, strike, t_entry, t_exit, iv_entry, iv_exit,
                   spot_exit, account, risk_frac, r, costs, wing_mult):
    implied_move = float(e["implied_move"])
    unit = iron_fly_pnl(spot, strike, t_entry, t_exit, iv_entry, iv_exit,
                        spot_exit, implied_move, r, contracts=1, wing_mult=wing_mult)
    credit_ps = unit["entry_credit"] / CONTRACT_MULTIPLIER
    max_loss_ps = unit["max_loss"] / CONTRACT_MULTIPLIER
    contracts = worst_case_size(account, credit_ps, risk_frac=risk_frac,
                                defined_max_loss_per_share=max_loss_ps)
    if contracts <= 0:
        return None
    res = iron_fly_pnl(spot, strike, t_entry, t_exit, iv_entry, iv_exit,
                       spot_exit, implied_move, r, contracts=contracts,
                       wing_mult=wing_mult)
    cost = _structure_cost(res["entry_credit"], res["exit_value"], contracts, costs)
    pnl = res["pnl"] - cost
    return _common(e, IRON_FLY, contracts, res["entry_credit"], res["exit_value"],
                   cost, pnl, res["max_loss"])


def _book_calendar(e, spot, strike, t_entry, t_exit, iv_entry, iv_exit,
                   spot_exit, account, risk_frac, r, costs, back_gap_years,
                   back_crush):
    iv_back_entry = float(e["back_atm_iv"] if "back_atm_iv" in e else iv_entry)
    iv_back_exit = iv_back_entry * back_crush
    t_back_entry = t_entry + back_gap_years
    t_back_exit = t_exit + back_gap_years

    front_credit_ps = _straddle_ps(spot, strike, t_entry, r, iv_entry)
    contracts = worst_case_size(account, front_credit_ps, risk_frac=risk_frac)
    if contracts <= 0:
        return None
    res = calendar_pnl(spot, strike, t_entry, t_exit, t_back_entry, t_back_exit,
                       iv_entry, iv_exit, iv_back_entry, iv_back_exit, spot_exit,
                       r, contracts=contracts)
    cost = _structure_cost(res["entry_credit"], res["exit_value"], contracts, costs)
    pnl = res["pnl"] - cost
    capital_at_risk = PREMIUM_STOP_MULTIPLE * front_credit_ps * CONTRACT_MULTIPLIER * contracts
    return _common(e, CALENDAR, contracts, res["entry_credit"], res["exit_value"],
                   cost, pnl, capital_at_risk)


def _structure_cost(entry_credit: float, exit_value: float, contracts: int,
                    costs: CostModel | None) -> float:
    """Cost on the net premium turned over each side (zero if no cost model)."""
    if costs is None:
        return 0.0
    scale = CONTRACT_MULTIPLIER * contracts
    entry_ps = abs(entry_credit) / scale if scale else 0.0
    exit_ps = abs(exit_value) / scale if scale else 0.0
    return costs.round_trip_cost(entry_ps, exit_ps, contracts).total_cost
