"""Short-straddle trade economics: margin, sizing, P&L, ledger schema.

Pure functions shared by the live strategy and the Agent 0 control, so both
book trades identically and only the *selection* differs. P&L follows the agreed
convention: collect the straddle credit at entry (front-week IV), buy it back at
exit using the post-event IV (the crush) and the realised spot move, both priced
with the Black-Scholes engine. Commissions are Khan & Khan (2024): $0.65 per
contract per fill, and a straddle is two legs opened and closed (four fills).
"""
from __future__ import annotations

import pandas as pd

from .greeks import straddle_price

COST_PER_CONTRACT = 0.65    # USD per contract per fill (Khan & Khan 2024)
ACCOUNT_SIZE = 250_000      # Reg-T account
CONTRACT_MULTIPLIER = 100   # shares per option contract
FILLS_PER_STRADDLE = 4      # 2 legs x (open + close)

LEDGER_COLUMNS = [
    "ticker", "entry_date", "exit_date", "strike", "contracts",
    "spot_entry", "spot_exit", "iv_entry", "iv_exit", "t_entry", "t_exit",
    "entry_credit", "exit_value", "commissions", "pnl", "margin",
    "return_on_margin",
]


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


def straddle_pnl(spot_entry, strike, t_entry, t_exit, iv_entry, iv_exit,
                 spot_exit, r, contracts, cost_per_contract=COST_PER_CONTRACT):
    """Short-straddle P&L (USD) = entry credit - exit value - commissions."""
    credit = _straddle_value(spot_entry, strike, t_entry, r, iv_entry)
    exit_val = _straddle_value(spot_exit, strike, t_exit, r, iv_exit)
    gross = (credit - exit_val) * CONTRACT_MULTIPLIER * contracts
    commissions = cost_per_contract * FILLS_PER_STRADDLE * contracts
    return gross - commissions


def build_trade(ticker, entry_date, exit_date, spot_entry, strike, t_entry,
                t_exit, iv_entry, iv_exit, spot_exit, contracts, r=0.0,
                cost_per_contract=COST_PER_CONTRACT) -> dict:
    """Assemble one ledger row for a short straddle. Keys = LEDGER_COLUMNS."""
    credit_ps = _straddle_value(spot_entry, strike, t_entry, r, iv_entry)
    exit_ps = _straddle_value(spot_exit, strike, t_exit, r, iv_exit)
    entry_credit = credit_ps * CONTRACT_MULTIPLIER * contracts
    exit_value = exit_ps * CONTRACT_MULTIPLIER * contracts
    commissions = cost_per_contract * FILLS_PER_STRADDLE * contracts
    pnl = entry_credit - exit_value - commissions
    margin = regt_straddle_margin(spot_entry, strike, credit_ps, contracts)
    return {
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


# Columns a per-event frame must supply for the ledger builder. `iv_entry` may
# instead be provided as `front_atm_iv` (the pipeline's name for it).
EXECUTION_COLUMNS = [
    "ticker", "entry_date", "exit_date", "spot_entry", "strike",
    "t_entry", "t_exit", "iv_entry", "iv_exit", "spot_exit",
]


def build_ledger(events: pd.DataFrame, account=ACCOUNT_SIZE, fraction=0.05,
                 r=0.0) -> pd.DataFrame:
    """Turn a per-event frame into a short-straddle ledger.

    Each row is priced at entry (front IV) to set the credit, sized to the
    margin fraction, then booked with `build_trade`. Events that size to zero
    contracts are skipped. Shared by the live strategy and the Agent 0 control
    so both book trades identically.
    """
    rows = []
    for _, e in events.iterrows():
        iv_entry = float(e["iv_entry"] if "iv_entry" in e else e["front_atm_iv"])
        spot, strike, t_entry = float(e["spot_entry"]), float(e["strike"]), float(e["t_entry"])
        credit_ps = _straddle_value(spot, strike, t_entry, r, iv_entry)
        contracts = size_contracts(account, spot, strike, credit_ps, fraction)
        if contracts <= 0:
            continue
        rows.append(build_trade(
            ticker=e["ticker"], entry_date=e["entry_date"], exit_date=e["exit_date"],
            spot_entry=spot, strike=strike, t_entry=t_entry, t_exit=float(e["t_exit"]),
            iv_entry=iv_entry, iv_exit=float(e["iv_exit"]), spot_exit=float(e["spot_exit"]),
            contracts=contracts, r=r,
        ))
    return pd.DataFrame(rows, columns=LEDGER_COLUMNS)
