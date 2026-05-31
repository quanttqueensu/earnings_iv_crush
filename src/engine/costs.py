"""costs.py
Transaction-cost model for short-straddle round trips.

The entire project thesis is that a cross-sectionally *filtered* short-straddle
book beats the unfiltered Agent 0 control **net of costs** — Khan & Khan (2024)
show the unfiltered trade returns ~0.65% out-of-sample and does not survive
realistic costs. A backtester that models only commissions cannot test that
claim, so this module makes the full cost stack explicit and configurable.

This module implements:

* ``CostModel``        — frozen dataclass holding the commission, exchange-fee,
  bid-ask and slippage assumptions, with sensible defaults drawn from the
  project spec (§6).
* ``CostBreakdown``    — the itemised cost of one round trip, in USD and as a
  fraction of the entry credit.
* ``CostModel.round_trip_cost`` — price a short-straddle open-and-close.

Cost stack (project spec §6, conservative average for liquid front-month ATM):

    commission   : ``commission_per_contract`` per contract per fill, four fills
                   per straddle round trip (two legs, opened and closed).
    exchange fee : flat ``exchange_fee_per_fill`` per fill (the spec notes a
                   ~$1.00 per-leg floor; defaults to 0 so the headline
                   commission matches the spec's ~$2.60 figure).
    bid-ask      : ``bid_ask_pct`` is the *full* quoted spread as a fraction of
                   the option mid. ``cross_fraction`` is how much of that width
                   is paid per crossing — ``1.0`` charges the full quoted spread
                   on both entry and exit (the spec's conservative ~16% round-
                   trip premium cost); ``0.5`` recovers the mid-cross
                   (half-spread) economics.
    slippage     : ``slippage_ticks`` ticks of ``tick_size`` worse than mid, per
                   leg per crossing (four crossings per round trip).

References
----------
Khan, W., & Khan, H. (2024). A 17-year backtest of straddles around S&P 500
earnings announcements. *SSRN Working Paper 4832160*.
"""

from __future__ import annotations

from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# Cost breakdown container
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CostBreakdown:
    """
    Itemised round-trip cost of one short straddle.

    Attributes
    ----------
    commission : float
        Broker commission across all fills (USD).
    exchange_fee : float
        Exchange / routing fees across all fills (USD).
    spread_cost : float
        Bid-ask spread paid crossing in and out (USD).
    slippage_cost : float
        Slippage versus mid across all crossings (USD).
    total_cost : float
        Sum of the four components (USD).
    cost_frac_of_credit : float
        ``total_cost`` divided by the gross entry credit (dimensionless).
        ``nan`` when the entry credit is non-positive.
    """

    commission: float
    exchange_fee: float
    spread_cost: float
    slippage_cost: float
    total_cost: float
    cost_frac_of_credit: float


# ─────────────────────────────────────────────────────────────────────────────
# Cost model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CostModel:
    """
    Configurable transaction-cost assumptions for a short ATM straddle.

    Defaults reproduce the project spec (§6): IBKR Pro $0.65 per contract,
    an 8% bid-ask spread on liquid front-month ATM options, and one tick of
    slippage per leg per crossing.

    Attributes
    ----------
    commission_per_contract : float
        Broker commission per option contract per fill (USD). Defaults to
        ``0.65`` (IBKR Pro).
    exchange_fee_per_fill : float
        Flat exchange / routing fee per fill (USD). Defaults to ``0.0``; set to
        model the spec's ~$1.00 per-leg floor.
    bid_ask_pct : float
        Full quoted bid-ask spread as a fraction of the option mid. Defaults to
        ``0.08`` (8%).
    cross_fraction : float
        Fraction of the full quoted spread paid per crossing. ``1.0`` (default)
        charges the full spread on both entry and exit — the spec's conservative
        ~16% round-trip premium cost. ``0.5`` models crossing at the half-spread
        from mid.
    slippage_ticks : float
        Ticks of slippage worse than mid, per leg per crossing. Defaults to
        ``1.0``.
    tick_size : float
        Price of one tick per share (USD). Defaults to ``0.01``.
    legs_per_straddle : int
        Option legs in the structure. Defaults to ``2`` (one call, one put).
    fills_per_leg : int
        Fills per leg over a round trip. Defaults to ``2`` (open, close).
    contract_multiplier : int
        Shares per option contract. Defaults to ``100``.
    """

    commission_per_contract: float = 0.65
    exchange_fee_per_fill: float = 0.0
    bid_ask_pct: float = 0.08
    cross_fraction: float = 1.0
    slippage_ticks: float = 1.0
    tick_size: float = 0.01
    legs_per_straddle: int = 2
    fills_per_leg: int = 2
    contract_multiplier: int = 100

    @property
    def n_fills(self) -> int:
        """Total fills over a round trip (``legs_per_straddle * fills_per_leg``)."""
        return self.legs_per_straddle * self.fills_per_leg

    def round_trip_cost(
        self,
        entry_premium_per_share: float,
        exit_premium_per_share: float,
        contracts: int,
    ) -> CostBreakdown:
        """
        Cost of opening and closing one short straddle position.

        Parameters
        ----------
        entry_premium_per_share : float
            Straddle mid (call + put) per share collected at entry (USD).
        exit_premium_per_share : float
            Straddle mid per share paid to close at exit (USD).
        contracts : int
            Number of straddles (each ``contract_multiplier`` shares).

        Returns
        -------
        CostBreakdown
            Itemised cost in USD plus the cost as a fraction of the gross entry
            credit. All components are non-negative; a zero-size trade costs
            nothing.
        """
        if contracts <= 0:
            return CostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, float("nan"))

        notional = self.contract_multiplier * contracts

        commission = self.commission_per_contract * contracts * self.n_fills
        exchange_fee = self.exchange_fee_per_fill * self.n_fills

        # Full quoted spread paid on the premium traded at each crossing.
        per_crossing = self.bid_ask_pct * self.cross_fraction
        spread_cost = per_crossing * (
            max(entry_premium_per_share, 0.0) + max(exit_premium_per_share, 0.0)
        ) * notional

        # Slippage: ticks worse than mid, per leg, on every crossing.
        slippage_cost = (
            self.slippage_ticks
            * self.tick_size
            * self.legs_per_straddle
            * self.fills_per_leg
            * notional
        )

        total_cost = commission + exchange_fee + spread_cost + slippage_cost

        entry_credit = max(entry_premium_per_share, 0.0) * notional
        cost_frac = total_cost / entry_credit if entry_credit > 0 else float("nan")

        return CostBreakdown(
            commission=commission,
            exchange_fee=exchange_fee,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            total_cost=total_cost,
            cost_frac_of_credit=cost_frac,
        )
