"""breakeven_grid.py: synthetic break-even arithmetic for selling a livestock report straddle.

Purpose. With no obtainable option data, this states how large an event-variance overpricing
must be for a short ATM straddle to clear the touch, given the event's size in units of an
ordinary session's variance. Every input is a labelled assumption; nothing here is a measured
premium. Output is SYNTHETIC.

Model. ATM straddle value is proportional to the square root of priced variance to expiry.
Priced variance = b + j * (1 + o), where b is ordinary (diffusive) variance to expiry in
session units, priced fairly, j is the true event jump variance in session units, and o is the
proportional overpricing of the event variance. Fair value uses b + j. The seller's expected
edge at the mid, as a share of the premium received, is 1 - sqrt((b + j) / (b + j * (1 + o))).

Inputs and sources.
- j for live cattle on Cattle on Feed: 0.41 session units from Isengildina, Irwin and Good
  (2005 conference version, Table 2: close-to-open mean squared return 0.538 on COF days vs
  0.126 on non-report days, 1985-2003), scaled by an assumed close-to-close session variance of
  1.0 %^2 (about 16% annualised). Karali et al. (2018) report smaller reactions after 2003, so
  0.2 is also shown.
- j for lean hogs on Hogs and Pigs: 3.946 - 0.431 = 3.515 %^2 over an assumed 2.56 %^2
  session variance (about 25% annualised), so about 1.37 session units.
- b: 1.0 for a Monday weekly sold at Friday's close (Monday session only); 5 for a weekly with
  a week left; 15 for a serial or regular option about three weeks out.
- Cost: commission 2 x USD 2.96 (IB tiered, two legs, one side) plus a quoted half-spread of
  h ticks per leg (tick 0.025 cents/lb = USD 10 on a 40,000 lb contract), as a share of the
  straddle premium, with premium = 0.8 * F * sigma_session * sqrt(b + j), F = 225 cents/lb,
  sigma_session = 1.0% (LE) or 1.6% with F = 85 cents/lb (HE). Both h values are conjecture.

Usage
-----
    python breakeven_grid.py
"""

from __future__ import annotations

import itertools
import math

# ── assumptions (all labelled in the module docstring) ──
TICK_USD = 10.0
COMMISSION_PER_LEG_USD = 2.96
CONTRACT_LB = 40_000
CASES = {
    # name: (F cents/lb, session sd as a fraction, event units j)
    "LE COF (1985-2003 size)": (225.0, 0.010, 0.41),
    "LE COF (halved, post-2003)": (225.0, 0.010, 0.20),
    "HE Hogs and Pigs": (85.0, 0.016, 1.37),
}
B_GRID = (1.0, 5.0, 15.0)
O_GRID = (0.2, 0.5, 1.0)
H_TICKS = (1.0, 2.0, 4.0)


def _edge(b: float, j: float, o: float) -> float:
    """Seller's expected edge at the mid as a share of premium received."""
    return 1.0 - math.sqrt((b + j) / (b + j * (1.0 + o)))


def _premium_usd(f_cents: float, sd: float, b: float, j: float) -> float:
    """ATM straddle premium in USD per straddle (0.8 * F * sigma * sqrt(T) approximation)."""
    cents = 0.8 * f_cents * sd * math.sqrt(b + j)
    return cents / 100.0 * CONTRACT_LB


def main() -> None:
    print("SYNTHETIC break-even grid; inputs are assumptions, see module docstring")
    print(f"{'case':28s} {'b':>4s} {'prem$':>7s} {'event%var':>9s} "
          + " ".join(f"edge o={o:.1f}" for o in O_GRID)
          + "  " + " ".join(f"cost h={h:.0f}" for h in H_TICKS))
    for (name, (f, sd, j)), b in itertools.product(CASES.items(), B_GRID):
        prem = _premium_usd(f, sd, b, j)
        share = j / (b + j)
        edges = " ".join(f"{_edge(b, j, o):10.1%}" for o in O_GRID)
        costs = " ".join(
            f"{(2 * h * TICK_USD + 2 * COMMISSION_PER_LEG_USD) / prem:8.1%}" for h in H_TICKS
        )
        print(f"{name:28s} {b:4.0f} {prem:7.0f} {share:9.1%} {edges}  {costs}")
    print("cost = one side (entry) at the touch: half-spread of h ticks on each of two legs plus"
          " commission; holding to expiry adds the exercise or futures exit, not shown.")


if __name__ == "__main__":
    main()
