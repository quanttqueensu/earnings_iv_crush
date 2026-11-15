"""r1_stack.py: round 1, the stacked execution book on the tick panel (real data, cached cmbp-1 ticks).

Arms, all in fractions of the common margin m0 = 0.20 x forward + 15:59 bid premium, net of
USD 0.65 per contract per leg per side:
  B0   sell both legs at the 15:59:00 bids, buy back at the 15:59:00 asks next session (the book).
  E45  sell at the 15:45:00 bids.                    X<t>  buy back at the <t> asks.
  PKf  entry as one package at mid x (1 - 1.34%) (flat measured seller-side cost).
  PKs  entry package paying the measured share of the event's own half-spread.
  PKo  package only where a late seller-side package printed (own measured cost), touch elsewhere.

Usage
-----
    python r1_stack.py [--blocks disc_broad_2025,megacap_2023_24] [--log]
"""
from __future__ import annotations

import argparse

from common import COMM, OUT, ci, fmt, load_ticks, log_trial, split_ticks, tstat

import pandas as pd

PK_FLAT = 0.0134  # late-window seller-side package cost, share of straddle mid (package study)


def build_arms(g: pd.DataFrame, pk_share: float, xpk_share: float) -> pd.DataFrame:
    """Per-event net return on m0 for every execution arm. g must be pre-filtered to scoreable events."""
    fb45 = ~g["en_two_15:45"]
    m0 = g["m0"]
    sell59, buy59 = g["en_bid_15:59"], g["ex_ask_15:59"]
    sell45 = g["en_bid_15:45"].where(~fb45, sell59)
    mid45 = ((g["en_bid_15:45"] + g["en_ask_15:45"]) / 2).where(~fb45, g["mid0"])
    hs45 = ((g["en_ask_15:45"] - g["en_bid_15:45"]) / 2).where(~fb45, g["hs0"] * g["mid0"])
    hs59 = g["hs0"] * g["mid0"]
    xmid = (g["ex_bid0_15:59"] + g["ex_ask_15:59"]) / 2
    xhs = (g["ex_ask_15:59"] - g["ex_bid0_15:59"]) / 2
    two_x = g["ex_two_15:59"]
    c4 = 4 * COMM
    arm = {}
    arm["B0"] = (sell59 - buy59 - c4) / m0
    arm["gross_mid"] = (g["mid0"] - xmid) / m0
    arm["E45"] = (sell45 - buy59 - c4) / m0
    for t in ("15:01", "15:15", "15:30", "15:45", "15:55"):
        arm[f"X{t}"] = (sell59 - g[f"ex_ask_{t}"].fillna(buy59) - c4) / m0
        arm[f"Xmid{t}"] = (g["mid0"] - ((g[f"ex_bid0_{t}"] + g[f"ex_ask_{t}"]) / 2).fillna(xmid)) / m0
    arm["PKf59"] = (g["mid0"] * (1 - PK_FLAT) - buy59 - c4) / m0
    arm["PKs59"] = (g["mid0"] - pk_share * hs59 - buy59 - c4) / m0
    has = g["en_pk_sell_n"].fillna(0) > 0
    own = g["mid0"] * (1 - g["en_pk_sell_cost"])
    arm["PKo59"] = (own.where(has, sell59) - buy59 - c4) / m0
    arm["E45+PKs"] = (mid45 - pk_share * hs45 - buy59 - c4) / m0
    arm["E45+PKf"] = (mid45 * (1 - PK_FLAT) - buy59 - c4) / m0
    # exit package only where the exit quote is two-sided: a one-sided quote has no mid
    xpk = (xmid + xpk_share * xhs).where(two_x, buy59)
    arm["XPKs"] = (sell59 - xpk - c4) / m0
    arm["E45+XPKs"] = (sell45 - xpk - c4) / m0
    arm["E45+PKs+XPKs"] = (mid45 - pk_share * hs45 - xpk - c4) / m0
    for p in (0.25, 0.5, 0.75):  # package fills with probability p, else cross the touch at 15:59
        arm[f"stack_p{p}"] = p * arm["E45+PKs+XPKs"] + (1 - p) * arm["B0"]
        arm[f"entrystack_p{p}"] = p * arm["E45+PKs"] + (1 - p) * arm["B0"]
    A = pd.DataFrame(arm)
    A["has_pk"] = has
    return A


def shares(d0: pd.DataFrame) -> tuple[float, float]:
    """Share of the quoted half-spread paid by late package prints, from the discovery block only."""
    return (float((d0["en_pk_sell_cost"] / d0["en_pk_sell_hs"]).dropna().mean()),
            float((d0["ex_pk_buy_cost"] / d0["ex_pk_buy_hs"]).dropna().mean()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default="disc_broad_2025")
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    S = split_ticks(load_ticks())
    d0 = S["disc_broad_2025"]
    pk_share, xpk_share = shares(d0)
    print(f"discovery package shares of half-spread: entry seller {pk_share:.3f} (events "
          f"{int((d0['en_pk_sell_n'] > 0).sum())}), exit buyer {xpk_share:.3f} (events {int((d0['ex_pk_buy_n'] > 0).sum())})")
    for name in a.blocks.split(","):
        g = S[name].copy()
        n0 = len(g)
        g = g[g["en_two_15:59"] & g["ex_ask_15:59"].notna()]
        print(f"\n=== {name}: files {n0}, scored {len(g)}, 15:45 not two-sided (falls back to 15:59) "
              f"{int((~g['en_two_15:45']).sum())}, exit one-sided {int((~g['ex_two_15:59']).sum())}")
        dt = g["exit_date"]
        A = build_arms(g, pk_share, xpk_share)
        has = A.pop("has_pk")
        print(f"{'arm':16s} level, % of m0 net per trade            paired diff vs B0, % of m0                 t")
        for k in A:
            print(f"{k:16s} {fmt(ci(A[k], dt)):38s} {fmt(ci(A[k] - A['B0'], dt)):38s} {tstat(A[k] - A['B0'], dt):+.2f}")
        print("additivity: E45 lift + PKs59 lift =",
              round(100 * ((A["E45"] - A["B0"]).mean() + (A["PKs59"] - A["B0"]).mean()), 3),
              "vs stacked E45+PKs lift", round(100 * (A["E45+PKs"] - A["B0"]).mean(), 3))
        print("package-print selection: events with a late seller-side print", int(has.sum()), "of", len(g),
              "| hs0 median with", round(100 * g.loc[has, "hs0"].median(), 2), "without", round(100 * g.loc[~has, "hs0"].median(), 2),
              "| B0 with", round(100 * A.loc[has, "B0"].mean(), 2), "without", round(100 * A.loc[~has, "B0"].mean(), 2),
              "| gross with", round(100 * A.loc[has, "gross_mid"].mean(), 2), "without", round(100 * A.loc[~has, "gross_mid"].mean(), 2))
        print("entry stack on print events:", fmt(ci(A.loc[has, "E45+PKs"], dt[has])), "| no-print events:",
              fmt(ci(A.loc[~has, "E45+PKs"], dt[~has])))
        print("own-cost package on print events, diff vs B0:", fmt(ci((A["PKo59"] - A["B0"])[has], dt[has])))
        print("size (contracts, min of the two legs): entry bid 15:45 median", g["en_minsz_bid_15:45"].median(), "p25",
              g["en_minsz_bid_15:45"].quantile(0.25), "| exit ask 15:59 median", g["ex_minsz_ask_15:59"].median(),
              "| late seller package print size median", g["en_pk_sell_size_med"].median(), "contracts per event median",
              g["en_pk_sell_size_sum"].median())
        A.assign(ticker=g["ticker"], entry_date=g["entry_date"], exit_date=dt, m0=g["m0"], hs0=g["hs0"], dte=g["dte"],
                 has_pk=has).to_parquet(OUT / f"r1_arms_{name}.parquet")
        if a.log:
            mech = {
                "E45": (1719, "entry at 15:45 bid instead of 15:59", "broad-name quotes widen in the last minutes"),
                "PKs59": (1720, "package entry at measured share of own half-spread, at 15:59", "complex orders trade inside the summed leg quotes"),
                "E45+PKs": (1721, "stack: 15:45 clock + package entry (fill prob 1)", "the two entry levers may overlap: both avoid the 15:59 bid"),
                "XPKs": (1722, "package exit at measured buyer-side share (fill prob 1)", "the exit spread is about 70% of the round trip"),
                "E45+PKs+XPKs": (1723, "full stack: clock + package entry + package exit (fill prob 1)", "upper bound of the execution stack"),
                "stack_p0.5": (1724, "full stack at 50% fill haircut, else touch at 15:59", "fill probability not measured"),
                "X15:30": (1725, "exit clock 15:30 ask instead of 15:59", "exit quotes widen into the close"),
                "X15:01": (1726, "exit clock 15:01 ask instead of 15:59", "earlier exit removes last-hour variance"),
            }
            for k, (tid, h, m) in mech.items():
                log_trial(tid, h, m, name, A[k] - A["B0"], dt, "paired diff vs B0, fraction of m0, net, per trade", "scored")


if __name__ == "__main__":
    main()
