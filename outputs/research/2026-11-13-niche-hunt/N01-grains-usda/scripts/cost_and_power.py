"""cost_and_power.py: touch cost as a share of premium, and power, for grain report straddles.

No outcome data is used. Every input is a published aggregate (cited in ``evidence.md``) or a
stated assumption, so the output is a calculation, not a result. It answers two questions the
brief asks before any data pull: what share of an at-the-money straddle premium the CBOT
corn quoted half-spread consumes, by tenor, and how many independent report dates a test needs
to resolve a net edge of the size the literature suggests.

Inputs (published, verified at source unless marked):
- Corn option quoted spread, day session, Jan 2019 to Jun 2020: mean 0.38 c/bu, median 0.23
  c/bu (Ma and Serra 2024, Table 1 Panel B, CME Market Depth, all actively quoted strikes).
- Option tick 0.125 c/bu, futures tick 0.25 c/bu, 5,000 bu (same paper, section 2).
- Pooled implied volatility 0.22, median option tenor 32 days (same paper, Table 3).
- Corn nearby daily high-low range 2017-2021: 14.19 c on report dates, 8.08 c otherwise
  (Diersen and Wang 2023, Table 1).
- IBKR futures-option commission USD 0.85 per contract plus exchange fees (IB page, 2026-11-13);
  the CBOT exchange fee is not verified and is set by assumption below.

Usage
-----
    python -I scripts/cost_and_power.py > logs/cost_and_power.log
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

# ── inputs ──


@dataclass(frozen=True)
class Inputs:
    """Published aggregates and stated assumptions (cents per bushel unless noted)."""

    spread_median_c: float = 0.23  # Ma and Serra 2024, Table 1, corn options, day session
    spread_mean_c: float = 0.38  # same
    spread_one_tick_c: float = 0.125  # best case: a one-tick ATM market
    fut_half_spread_c: float = 0.125  # futures one tick 0.25 c, so half-spread 0.125 c
    futures_c: float = 430.0  # corn near 4.30 USD/bu, roughly the 2025-26 level (assumption)
    iv_front: float = 0.22  # Ma and Serra pooled IV
    tenor_front_d: float = 32.0  # calendar days, Ma and Serra median
    range_report_c: float = 14.19  # Diersen and Wang 2023 Table 1, nearby corn
    range_normal_c: float = 8.08
    bushels: int = 5000
    commission_usd: float = 0.85  # IBKR fixed, per contract per side
    exch_fee_usd: float = 1.50  # ASSUMPTION, not verified: CBOT ag option fee per contract
    he_bian_gross_lo: float = 0.03  # He and Bian 2025 abstract: long straddle loses 3-7%
    he_bian_gross_hi: float = 0.07


_SQRT_2_OVER_PI = math.sqrt(2.0 / math.pi)  # E|Z| for a standard normal
_PARKINSON = 2.0 * math.sqrt(math.log(2.0))  # E[range] = 1.665 sigma for Brownian motion
_Z_A, _Z_B = 1.96, 0.84  # two-sided 5% test, 80% power


def n_needed(mean: float, sd: float) -> float:
    """Independent observations to detect ``mean`` with per-trade ``sd`` (normal approximation)."""
    return ((_Z_A + _Z_B) * sd / mean) ** 2


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    p = Inputs()
    sd_report = p.range_report_c / _PARKINSON
    sd_normal = p.range_normal_c / _PARKINSON
    sd_event = math.sqrt(max(sd_report**2 - sd_normal**2, 0.0))
    print("# ── report-day move scale (Diersen and Wang ranges, Parkinson conversion) ──")
    print(f"report-day sd {sd_report:.2f} c, normal-day sd {sd_normal:.2f} c, "
          f"event-only sd {sd_event:.2f} c ({sd_event / p.futures_c:.2%} of a {p.futures_c:.0f} c future)")

    sd_front = p.futures_c * p.iv_front * math.sqrt(p.tenor_front_d / 365.0)
    tenors = {
        "front 32d straddle, 1-day hold over report": _SQRT_2_OVER_PI * sd_front,
        "weekly ~5 trading days incl. report (IV 0.30)": _SQRT_2_OVER_PI
        * math.sqrt((p.futures_c * 0.30 * math.sqrt(4 / 252)) ** 2 + sd_event**2),
        "same-day expiry, sold before 11:00 CT (event + 2.3h)": _SQRT_2_OVER_PI
        * math.sqrt(sd_event**2 + (sd_normal * math.sqrt(2.3 / 4.83)) ** 2),
    }
    print("\n# ── half-spread per side, both legs, as a share of straddle premium ──")
    print("tenor | premium c | one-tick | median | mean   (cost per side, % of premium)")
    for name, prem in tenors.items():
        row = [s / prem for s in (p.spread_one_tick_c, p.spread_median_c, p.spread_mean_c)]
        # two legs x half-spread = one full quoted spread per side of the straddle
        print(f"{name} | {prem:.2f} | " + " | ".join(f"{x:.1%}" for x in row))

    prem_front = tenors["front 32d straddle, 1-day hold over report"]
    fee_c = 2 * (p.commission_usd + p.exch_fee_usd) / p.bushels * 100.0  # 2 contracts, cents/bu
    print("\n# ── round trip on the front straddle (1-day hold) vs He and Bian gross ──")
    for lab, s in (("one-tick", p.spread_one_tick_c), ("median", p.spread_median_c),
                   ("mean", p.spread_mean_c)):
        rt = (2 * s + 2 * fee_c) / prem_front
        print(f"{lab}: round trip {rt:.1%} of premium (spread {2 * s / prem_front:.1%}, "
              f"fees {2 * fee_c / prem_front:.1%}); net range "
              f"{p.he_bian_gross_lo - rt:+.1%} to {p.he_bian_gross_hi - rt:+.1%}")

    print("\n# ── power: independent report dates needed (80% power, 5% two-sided) ──")
    gamma = 2.0 * 0.3989 / sd_front  # straddle gamma per cent, normal approximation
    gam_pnl_sd = math.sqrt(2.0) * 0.5 * gamma * sd_report**2 / prem_front  # sd of 0.5*G*m^2
    vega_sd = 1.5 / (p.iv_front * 100)  # assume 1.5 vol-point sd of the report-day IV change
    sd_1day = math.sqrt(gam_pnl_sd**2 + vega_sd**2)
    print(f"front straddle 1-day P&L sd ~ {sd_1day:.1%} of premium "
          f"(gamma {gam_pnl_sd:.1%}, vega {vega_sd:.1%})")
    for m in (0.01, 0.02, 0.03):
        print(f"  net mean {m:.0%}: N = {n_needed(m, sd_1day):.0f} dates")
    cv_abs = math.sqrt(1.0 - 2.0 / math.pi) / _SQRT_2_OVER_PI  # sd/mean of |Z|
    print(f"same-day straddle held to expiry: P&L sd ~ {cv_abs:.0%} of premium (normal moves)")
    for m in (0.05, 0.10, 0.20):
        print(f"  net mean {m:.0%}: N = {n_needed(m, cv_abs):.0f} dates")
    print("dates per year (ESMIS calendar, 2013-2025): about 15; the three grains share a date")


if __name__ == "__main__":
    main()
