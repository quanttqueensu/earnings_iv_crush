"""
research_name_persistence_exec.py
Does a name's own prior event richness predict its next event, on executable marks?

The completed move-space study found the overlay roughly doubled per-trade Sharpe in and
out of sample, but measured the payoff as ret = 1 - |realised| / implied, which is a
proxy and not a traded straddle. This runs the identical signal against an actual two-leg
mark from consolidated quotes at 15:59 on the entry and exit sessions.

Frozen before running:
    research/selection/preregs/name_persistence_prereg.md
      sha256 9f60331977c2e964adfe112724029cfa5bc88ef21eda3258dddac832890ff3e2
    research/selection/preregs/name_persistence_prereg_amendment_01.md
      sha256 1f12b025cb6ad0411637c5e64809c233b05df1e0c17931644675b990d061d1fe

The primary estimand is the incremental advantage of the overlay over the *eligible*
universe, not the overlay's own level:

    delta = E[R | overlay] - E[R | eligible]

Testing the overlay's own interval would test whether short earnings straddles pay in
absolute terms, which is not the hypothesis. Comparing against the eligible universe
rather than all events also keeps the three-prior requirement from entering as a
confound. The overlay is a subset of the eligible set, so every resample redraws the
underlying clusters and recomputes both means inside the draw.

Usage:
    python research/selection/research_name_persistence_exec.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.pnl import (  # noqa: E402
    ACCOUNT_SIZE,
    regt_straddle_margin,
    size_contracts,
)
from earnings_iv_crush.research.market_marks import FRACTION, _prepare  # noqa: E402

EVENTS = "outputs/research/events_megacap_databento.parquet"
OUT = Path("outputs/research/name_persistence_exec.csv")

# ── inherited from the completed study, unchanged (see the pre-registration) ─────────
MIN_PRIORS = 3
TOP_Q = 0.70
WINSOR = (0.01, 0.99)
N_BOOT = 5000
SEED = 0
FLAT_COST = 0.116  # of premium, round trip; the pre-specified sensitivity arm

# Measured fixed-boundary execution: 1.7871%/side, asymmetric. CostModel takes the FULL
# quoted width and charges cross_fraction of it, so the widths are twice the half-cross.
MEASURED = CostModel(cross_fraction=0.5)
ENTRY_W, EXIT_W = 0.025428, 0.060364


# ── payoff ──────────────────────────────────────────────────────────────────────────


def payoff(ev: pd.DataFrame, arm: str) -> pd.DataFrame:
    """Per-event executable return on margin under one cost arm, index preserved.

    Mirrors ``market_validate._ledger`` but keeps the event index so the result can be
    grouped by overlay membership, and prints the exclusion funnel rather than silently
    shrinking the sample.
    """
    rows, dropped = [], 0
    for idx, e in ev.iterrows():
        credit, exit_ = float(e["credit_mkt"]), float(e["exit_mkt"])
        if not (np.isfinite(credit) and np.isfinite(exit_) and credit > 0):
            dropped += 1
            continue
        spot, strike = float(e["spot_entry"]), float(e["strike_mkt"])
        contracts = size_contracts(ACCOUNT_SIZE, spot, strike, credit, FRACTION)
        if contracts <= 0:
            dropped += 1
            continue
        gross = (credit - exit_) * 100 * contracts
        if arm == "gross":
            cost = 0.0
        elif arm == "measured":
            cost = MEASURED.round_trip_cost(credit, exit_, contracts, ENTRY_W, EXIT_W).total_cost
        elif arm == "flat11.6":
            cost = FLAT_COST * credit * 100 * contracts
        else:
            raise ValueError(arm)
        margin = regt_straddle_margin(spot, strike, credit, contracts)
        if not margin:
            dropped += 1
            continue
        rows.append(
            {
                "idx": idx,
                "ticker": e["ticker"],
                "entry_date": e["entry_date"],
                "pnl": gross - cost,
                "rom": (gross - cost) / margin,
            }
        )
    if dropped:
        print(f"    [funnel] {dropped} event(s) unmarkable or zero-sized under arm '{arm}'")
    return pd.DataFrame(rows).set_index("idx")


# ── signal ──────────────────────────────────────────────────────────────────────────


def prior_richness(ev: pd.DataFrame) -> pd.Series:
    """Causal expanding mean of a name's own past move-space return, leave-current-out.

    The signal is deliberately left in move space, as frozen: holding it fixed is what
    makes the payoff measurement the only thing under test.
    """
    ret = 1.0 - (ev["realised_move"].abs() / ev["implied_move"])
    lo, hi = ret.quantile(list(WINSOR))
    ret = ret.clip(lo, hi)
    out = pd.Series(np.nan, index=ev.index)
    for _name, g in ev.groupby("ticker"):
        g = g.sort_values("announce_date")
        r = ret.loc[g.index]
        csum = r.shift(1).expanding().sum()
        cnt = r.shift(1).expanding().count()
        out.loc[g.index] = np.where(cnt >= MIN_PRIORS, csum / cnt, np.nan)
    return out


# ── inference ───────────────────────────────────────────────────────────────────────


def delta_of(pay: pd.DataFrame, rich: np.ndarray) -> float:
    if rich.sum() == 0 or len(pay) == 0:
        return np.nan
    return pay["rom"].to_numpy()[rich].mean() - pay["rom"].to_numpy().mean()


def cluster_boot(pay: pd.DataFrame, rich: np.ndarray, key: str, seed: int = SEED) -> tuple:
    """Bootstrap delta by resampling whole clusters of `key`, recomputing both means."""
    groups = {k: np.flatnonzero(pay[key].to_numpy() == k) for k in pay[key].unique()}
    keys = list(groups)
    rng = np.random.default_rng(seed)
    rom = pay["rom"].to_numpy()
    boots = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, len(keys), len(keys))
        sel = np.concatenate([groups[keys[j]] for j in pick])
        r, m = rom[sel], rich[sel]
        if m.sum() == 0:
            continue
        boots.append(r[m].mean() - r.mean())
    boots = np.asarray(boots)
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)), float(boots.var())


def two_way(pay: pd.DataFrame, rich: np.ndarray, d: float) -> tuple:
    """Two-way name-by-date interval via the additive decomposition V_n + V_d - V_iid.

    A common earnings season could make a favourable quarter look like firm persistence;
    name clustering alone cannot see that, and date clustering alone cannot see repeated
    bets on one name.
    """
    _, _, vn = cluster_boot(pay, rich, "ticker")
    _, _, vd = cluster_boot(pay, rich, "entry_date", seed=SEED + 1)
    _, _, vi = cluster_boot(pay.assign(_i=np.arange(len(pay))), rich, "_i", seed=SEED + 2)
    v = vn + vd - vi
    if v <= 0:
        return np.nan, np.nan, max(vn, vd), True
    se = np.sqrt(v)
    return d - 1.96 * se, d + 1.96 * se, v, False


# ── main ────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("loading and marking on consolidated quotes ...")
    ev, _ = _prepare(EVENTS, chain_path=dq.cache_path)
    ev = ev.dropna(subset=["realised_move", "implied_move"])
    ev = ev[ev["implied_move"] > 0].copy()
    ev["prior_mean"] = prior_richness(ev)
    print(
        f"  window {len(ev)} events, {ev['ticker'].nunique()} names; "
        f"eligible (>= {MIN_PRIORS} priors) {ev['prior_mean'].notna().sum()}"
    )

    windows = {
        "full 2019-2024": ev["entry_date"].notna(),
        "OOS 2022-2024": pd.to_datetime(ev["entry_date"]) >= pd.Timestamp("2022-01-01"),
    }

    rows = []
    for arm in ("gross", "measured", "flat11.6"):
        print(f"\n=== cost arm: {arm} ===")
        for wname, wmask in windows.items():
            sub = ev[wmask & ev["prior_mean"].notna()]
            if len(sub) < 50:
                print(f"  {wname}: only {len(sub)} eligible events, skipped")
                continue
            pay = payoff(sub, arm)
            elig = sub.loc[pay.index]
            thr = elig["prior_mean"].quantile(TOP_Q)
            rich = (elig["prior_mean"] >= thr).to_numpy()

            d = delta_of(pay, rich)
            lo_n, hi_n, _ = cluster_boot(pay, rich, "ticker")
            lo_d, hi_d, _ = cluster_boot(pay, rich, "entry_date", seed=SEED + 1)
            lo_2, hi_2, _, degen = two_way(pay, rich, d)

            # drop the single name contributing most to overlay P&L
            ov = pay[rich]
            worst = ov.groupby("ticker")["pnl"].sum().idxmax()
            keep = (pay["ticker"] != worst).to_numpy()
            d_drop = delta_of(pay[keep], rich[keep])

            rows.append(
                {
                    "arm": arm,
                    "window": wname,
                    "n_eligible": len(pay),
                    "n_overlay": int(rich.sum()),
                    "n_names": pay["ticker"].nunique(),
                    "mean_overlay": pay["rom"].to_numpy()[rich].mean(),
                    "mean_eligible": pay["rom"].mean(),
                    "delta": d,
                    "name_ci_lo": lo_n,
                    "name_ci_hi": hi_n,
                    "date_ci_lo": lo_d,
                    "date_ci_hi": hi_d,
                    "twoway_ci_lo": lo_2,
                    "twoway_ci_hi": hi_2,
                    "twoway_degenerate": degen,
                    "largest_name": worst,
                    "delta_ex_largest": d_drop,
                }
            )
            print(
                f"  {wname}: n_elig={len(pay)} n_ov={int(rich.sum())} "
                f"overlay={pay['rom'].to_numpy()[rich].mean():+.5f} "
                f"elig={pay['rom'].mean():+.5f}"
            )
            print(
                f"    delta {d:+.5f}  name[{lo_n:+.5f},{hi_n:+.5f}]  "
                f"date[{lo_d:+.5f},{hi_d:+.5f}]  2way[{lo_2:+.5f},{hi_2:+.5f}]"
                f"{'  (degenerate)' if degen else ''}"
            )
            print(f"    ex-{worst}: delta {d_drop:+.5f}")

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    # ── verdicts against the amended rule ────────────────────────────────────────────
    print("\n" + "=" * 74)
    for arm, verdict in (
        ("gross", "VERDICT 1 (persistence)"),
        ("measured", "VERDICT 2 (tradable)"),
    ):
        a = df[df.arm == arm].set_index("window")
        if len(a) < 2:
            print(f"{verdict}: NOT EVALUABLE, missing a window")
            continue
        c1 = bool((a["mean_overlay"] > a["mean_eligible"]).all())
        oos = a.loc["OOS 2022-2024"]
        c2n = oos["name_ci_lo"] > 0
        c2d = oos["date_ci_lo"] > 0
        c2t = (oos["twoway_ci_lo"] > 0) if not oos["twoway_degenerate"] else False
        c2 = bool(c2n and c2d and c2t)
        c3 = bool((a["delta_ex_largest"] > 0).all())
        print(f"{verdict}  [{arm}]")
        print(f"  1 overlay beats eligible, both windows ........ {c1}")
        print(
            f"  2 OOS delta excludes zero, all three clusterings {c2}"
            f"   (name {c2n}, date {c2d}, two-way {c2t})"
        )
        print(f"  3 survives dropping largest name .............. {c3}")
        print(f"  -> {'SUPPORTED' if (c1 and c2 and c3) else 'NOT SUPPORTED'}")
    print("=" * 74)
    print(f"\nwrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
