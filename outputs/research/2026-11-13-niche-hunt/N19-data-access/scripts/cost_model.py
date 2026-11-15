"""cost_model.py: price the historical quote pulls lanes N01 to N13 would need, without any vendor call.

Inputs are public price-list figures, the project's own Databento OPRA cost ledger, and stated
pull designs. Every rate carries a provenance label. Output: ../data/pull_costs.csv and a printed
table. Rebuild: python outputs/research/2026-11-13-niche-hunt/N19-data-access/scripts/cost_model.py

No figure here is a vendor quote. The free metadata.get_cost call is the definitive price and must
be run by the team lead before any pull.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parents[1] / "data" / "pull_costs.csv"
LEDGER = ROOT / "data" / "cache" / "index_chains" / "_cost_ledger.csv"

# ── rates ──────────────────────────────────────────────────────────────────

# Databento GLBX.MDP3 usage-based $/GB is not printed on any public page fetched (pricing page,
# dataset page, metered-pricing docs). Bracket it: $0.50 is Databento's own "from $0.50/GB"
# headline; $10 is the published IFUS.IMPACT usage rate (blog, 2025-06-18); $280 is the largest
# per-GB figure in Databento's docs example for list_unit_prices (example values, not a quote).
GLBX_RATES = {"floor_0.50": 0.50, "ifus_like_10": 10.0, "docs_example_280": 280.0}
IFUS_RATE = 10.0  # verified: databento.com/blog/introducing-ice-futures-us
STANDARD_PLAN = 199.0  # verified: databento.com/pricing; 1 yr L1 + 16 yr L0 for CME venues

# DBN record sizes in bytes (recalled from the DBN v2/v3 layout; not re-verified here).
BYTES = {"bbo-1m": 80, "cbbo-1m": 80, "mbp-10": 368, "definition": 520}


def opra_cost_per_snapshot() -> tuple[float, float, int]:
    """Mean and max per-ticker cost of one 1-minute cbbo-1m snapshot from the project ledger."""
    d = pd.read_csv(LEDGER)
    if d.empty:
        raise RuntimeError("index_chains cost ledger is empty")
    per_ticker = d.groupby("ticker").cost.mean()
    return float(d.cost.mean()), float(per_ticker.max()), len(d)


# ── pull designs ───────────────────────────────────────────────────────────
# events_hist: events in the historical window (10 years unless stated), counted from public
# release calendars (conjecture-level counts: monthly 12/yr, weekly about 50/yr, FOMC 8/yr).
# contracts: series per snapshot (front two or three expiries, about +/-10% strikes, both rights).
# snaps: 1-minute snapshots per event (entry, exit) doubled for a matched non-event control.

DESIGNS = [
    # lane, venue, products, events_hist, years, contracts, snaps
    ("N01 grains", "GLBX", "ZC ZS ZW", 16 * 10 * 3, 10, 150, 4),
    ("N02 livestock", "GLBX", "HE LE GF", 16 * 10 * 3, 10, 80, 4),
    ("N03 natgas", "GLBX", "NG (LNE, weeklies)", 50 * 10, 10, 200, 4),
    ("N04 crude", "GLBX", "CL (LO, weeklies)", 54 * 10, 10, 250, 4),
    ("N05 treasuries", "GLBX", "ZN ZB ZF ZT", 32 * 10 * 4, 10, 150, 4),
    ("N06 sofr", "GLBX", "SR3 + mid-curves", 8 * 10 * 4, 10, 300, 4),
    ("N07 fx", "GLBX", "6E 6J 6B 6A 6C", 16 * 10 * 5, 10, 100, 4),
    ("N10 crypto CME", "GLBX", "BTC ETH (from 2020/2021)", 20 * 6 * 2, 6, 120, 4),
    ("N12 metals", "GLBX", "GC SI HG", 32 * 10 * 3, 10, 150, 4),
    ("N13 softs", "IFUS", "KC CC SB CT", 12 * 7 * 4, 7, 100, 4),
]

OPRA_DESIGNS = [
    # lane, underlyings, sessions in a full daily panel (2016-2026 unless stated), n_underlyings
    ("N09 VIX options", "VIX", 2724, 1),
    ("N12 metals ETFs", "GLD SLV", 2724, 2),
    ("N17 commodity ETFs", "USO UNG GLD SLV TLT", 2724, 5),
    ("N16 country ETFs", "EWZ EWW FXI EWJ EWG INDA EWT", 2724, 7),
    ("N10 IBIT", "IBIT (listed Nov 2024)", 490, 1),
]


def main() -> None:
    mean_snap, max_ticker_snap, n_ledger = opra_cost_per_snapshot()
    print(f"OPRA ledger: N={n_ledger} snapshots, mean ${mean_snap:.6f}, worst ticker mean "
          f"${max_ticker_snap:.6f} per 1-minute snapshot (SPY-sized strip)")
    rows: list[dict[str, object]] = []
    for lane, venue, prods, ev, yrs, k, s in DESIGNS:
        if venue == "IFUS":
            # IFUS options are normalised as MBP-10 only (tick-level, each record carries the
            # full 10-level book). Pull a 30-minute window before each snapshot so every quoted
            # series has a record; book updates per series per minute are a conjecture, so the
            # cost is bracketed at 1 and 5 updates a minute.
            window_min = 30
            cost = {}
            nbytes = 0.0
            for rate_name, upm in (("ifus_10_lo", 1), ("ifus_10_hi", 5)):
                nb = ev * k * s * window_min * upm * BYTES["mbp-10"]
                cost[rate_name] = nb / 1e9 * IFUS_RATE
                nbytes = max(nbytes, nb)
        else:
            nbytes = ev * k * s * BYTES["bbo-1m"]
            cost = {name: nbytes / 1e9 * r for name, r in GLBX_RATES.items()}
        rows.append({"lane": lane, "venue": venue, "products": prods, "events": ev,
                     "years": yrs, "contracts": k, "snaps": s, "MB": round(nbytes / 1e6, 2),
                     **{f"usd_{n}": round(v, 2) for n, v in cost.items()}})
    for lane, und, sessions, n in OPRA_DESIGNS:
        snaps = sessions * 2 * n
        rows.append({"lane": lane, "venue": "OPRA", "products": und, "events": sessions,
                     "years": round(sessions / 252, 1), "contracts": None, "snaps": 2,
                     "MB": None, "usd_opra_mean": round(snaps * mean_snap, 2),
                     "usd_opra_worst": round(snaps * max_ticker_snap, 2)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for r in rows for k in r}, key=lambda c: list(rows[0]).index(c)
                  if c in rows[0] else 99)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
