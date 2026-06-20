"""
pnl.py
Short-straddle trade economics: margin, sizing, P&L, ledger schema.

Pure functions shared by the live strategy and the Agent 0 control, so both
book trades identically and only the *selection* differs. P&L follows the agreed
convention: collect the straddle credit at entry (front-week IV), buy it back at
exit using the post-event IV (the crush) and the realised spot move, both priced
with the Black-Scholes engine. Commissions are Khan & Khan (2024): $0.65 per
contract per fill, and a straddle is two legs opened and closed (four fills).
"""

from __future__ import annotations

import pandas as pd

from ..config import GLOBAL
from .costs import CostModel
from .greeks import straddle_price

# Sourced from the central GlobalConfig (see ``earnings_iv_crush/config.py``).
COST_PER_CONTRACT = GLOBAL.cost_per_contract  # USD per contract per fill (Khan & Khan 2024)
ACCOUNT_SIZE = GLOBAL.account_size  # Reg-T account
CONTRACT_MULTIPLIER = GLOBAL.contract_multiplier  # shares per option contract
FILLS_PER_STRADDLE = GLOBAL.fills_per_straddle  # 2 legs x (open + close)

LEDGER_COLUMNS = [
    "ticker",
    "entry_date",
    "exit_date",
    "strike",
    "contracts",
    "spot_entry",
    "spot_exit",
    "iv_entry",
    "iv_exit",
    "t_entry",
    "t_exit",
    "entry_credit",
    "exit_value",
    "commissions",
    "pnl",
    "margin",
    "return_on_margin",
]

# Extra columns appended when a full CostModel is supplied (spread + slippage).
# The default commission-only path leaves the schema at LEDGER_COLUMNS.
COST_COLUMNS = ["exchange_fee", "spread_cost", "slippage_cost", "total_cost"]


# ─────────────────────────────────────────────────────────────────────────────
# Margin and sizing
# ─────────────────────────────────────────────────────────────────────────────


def _straddle_value(spot, strike, t, r, sigma):
    """Straddle price per share, falling back to intrinsic at/after expiry."""
    if t <= 0 or sigma <= 0:
        return abs(spot - strike)
    return straddle_price(spot, strike, t, r, sigma)


def regt_straddle_margin(spot, strike, premium_per_share, contracts=1):
    """Approximate Reg-T initial margin for a short ATM straddle (USD).

    Naked short-option margin per share is the larger leg,
    max(0.20*spot - OTM, 0.10*spot) + option premium. For an ATM straddle the
    OTM amount is ~0, so we use 0.20*spot plus the straddle premium per share,
    scaled by the contract multiplier and contract count. This is a documented
    approximation adequate for a crude backtest, not a broker-exact figure.
    """
    per_share = 0.20 * spot + premium_per_share
    return per_share * CONTRACT_MULTIPLIER * contracts


def size_contracts(account, spot, strike, premium_per_share, fraction=0.05):
    """Number of straddles so margin is about `fraction` of the account."""
    margin_one = regt_straddle_margin(spot, strike, premium_per_share, 1)
    if margin_one <= 0:
        return 0
    return int((fraction * account) // margin_one)


# ─────────────────────────────────────────────────────────────────────────────
# P&L and ledger
# ─────────────────────────────────────────────────────────────────────────────


def straddle_pnl(
    spot_entry,
    strike,
    t_entry,
    t_exit,
    iv_entry,
    iv_exit,
    spot_exit,
    r,
    contracts,
    cost_per_contract=COST_PER_CONTRACT,
    costs: CostModel | None = None,
):
    """Short-straddle P&L (USD) = entry credit - exit value - costs.

    With ``costs=None`` (default) the only cost is commissions at
    ``cost_per_contract`` per fill, matching the original commission-only model.
    Pass a ``CostModel`` to charge the full stack (commission, exchange fee,
    bid-ask spread and slippage); the per-contract commission argument is then
    ignored in favour of the model's own commission assumption.
    """
    credit = _straddle_value(spot_entry, strike, t_entry, r, iv_entry)
    exit_val = _straddle_value(spot_exit, strike, t_exit, r, iv_exit)
    gross = (credit - exit_val) * CONTRACT_MULTIPLIER * contracts
    if costs is None:
        commissions = cost_per_contract * FILLS_PER_STRADDLE * contracts
        return gross - commissions
    return gross - costs.round_trip_cost(credit, exit_val, contracts).total_cost


def build_trade(
    ticker,
    entry_date,
    exit_date,
    spot_entry,
    strike,
    t_entry,
    t_exit,
    iv_entry,
    iv_exit,
    spot_exit,
    contracts,
    r=0.0,
    cost_per_contract=COST_PER_CONTRACT,
    costs: CostModel | None = None,
) -> dict:
    """Assemble one ledger row for a short straddle.

    With ``costs=None`` the row keys are exactly ``LEDGER_COLUMNS`` and the only
    cost is commissions. Pass a ``CostModel`` to charge the full cost stack; the
    row then also carries ``COST_COLUMNS`` (``exchange_fee``, ``spread_cost``,
    ``slippage_cost``, ``total_cost``) and ``pnl`` is net of every component.
    """
    credit_ps = _straddle_value(spot_entry, strike, t_entry, r, iv_entry)
    exit_ps = _straddle_value(spot_exit, strike, t_exit, r, iv_exit)
    entry_credit = credit_ps * CONTRACT_MULTIPLIER * contracts
    exit_value = exit_ps * CONTRACT_MULTIPLIER * contracts
    margin = regt_straddle_margin(spot_entry, strike, credit_ps, contracts)

    if costs is None:
        commissions = cost_per_contract * FILLS_PER_STRADDLE * contracts
        extra: dict = {}
    else:
        breakdown = costs.round_trip_cost(credit_ps, exit_ps, contracts)
        commissions = breakdown.commission
        extra = {
            "exchange_fee": breakdown.exchange_fee,
            "spread_cost": breakdown.spread_cost,
            "slippage_cost": breakdown.slippage_cost,
            "total_cost": breakdown.total_cost,
        }
    total_deducted = commissions + sum(extra.get(c, 0.0) for c in COST_COLUMNS[:-1])
    pnl = entry_credit - exit_value - total_deducted

    row = {
        "ticker": ticker,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "strike": strike,
        "contracts": contracts,
        "spot_entry": spot_entry,
        "spot_exit": spot_exit,
        "iv_entry": iv_entry,
        "iv_exit": iv_exit,
        "t_entry": t_entry,
        "t_exit": t_exit,
        "entry_credit": entry_credit,
        "exit_value": exit_value,
        "commissions": commissions,
        "pnl": pnl,
        "margin": margin,
        "return_on_margin": pnl / margin if margin else float("nan"),
    }
    row.update(extra)
    return row


# Columns a per-event frame must supply for the ledger builder. `iv_entry` may
# instead be provided as `front_atm_iv` (the pipeline's name for it).
EXECUTION_COLUMNS = [
    "ticker",
    "entry_date",
    "exit_date",
    "spot_entry",
    "strike",
    "t_entry",
    "t_exit",
    "iv_entry",
    "iv_exit",
    "spot_exit",
]


def build_ledger(
    events: pd.DataFrame, account=ACCOUNT_SIZE, fraction=0.05, r=0.0, costs: CostModel | None = None
) -> pd.DataFrame:
    """Turn a per-event frame into a short-straddle ledger.

    Each row is priced at entry (front IV) to set the credit, sized to the
    margin fraction, then booked with `build_trade`. Events that size to zero
    contracts are skipped. Shared by the live strategy and the Agent 0 control
    so both book trades identically.

    With ``costs=None`` the ledger schema is ``LEDGER_COLUMNS`` (commission-only).
    Pass a ``CostModel`` to charge the full cost stack; the ledger then also
    carries ``COST_COLUMNS`` and every ``pnl`` is net of spread and slippage.
    """
    rows = []
    for _, e in events.iterrows():
        iv_entry = float(e["iv_entry"] if "iv_entry" in e else e["front_atm_iv"])
        spot, strike, t_entry = float(e["spot_entry"]), float(e["strike"]), float(e["t_entry"])
        credit_ps = _straddle_value(spot, strike, t_entry, r, iv_entry)
        contracts = size_contracts(account, spot, strike, credit_ps, fraction)
        if contracts <= 0:
            continue
        rows.append(
            build_trade(
                ticker=e["ticker"],
                entry_date=e["entry_date"],
                exit_date=e["exit_date"],
                spot_entry=spot,
                strike=strike,
                t_entry=t_entry,
                t_exit=float(e["t_exit"]),
                iv_entry=iv_entry,
                iv_exit=float(e["iv_exit"]),
                spot_exit=float(e["spot_exit"]),
                contracts=contracts,
                r=r,
                costs=costs,
            )
        )
    columns = LEDGER_COLUMNS + (COST_COLUMNS if costs is not None else [])
    return pd.DataFrame(rows, columns=columns)
