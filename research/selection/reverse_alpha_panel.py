"""
reverse_alpha_panel.py
Build the one marked, feature-carrying event panel every reverse-engineering phase reads.

Why this exists
---------------
``market_validate._prepare`` re-marks every leg off the cached quote chains, which costs
about two minutes per block and is paid again by every script that wants the book. The
reverse-engineering programme needs the same panel a dozen times over, sliced differently
each time, so it is built once here and cached.

Two commitments make the cache safe to reuse:

* **Ungated.** The panel holds every event in the causal window, not the q=0.80 selection.
  The whole exercise is to ask what the gate selects, which is unanswerable from a frame
  the gate has already filtered.
* **The gate is stored as a continuous variable, not a boolean.** ``term_rank`` is the
  expanding percentile of ``iv_term_spread`` against strictly earlier events, which is the
  exact quantity ``expanding_high_term_mask`` thresholds. Any percentile gate is then a cut
  on one stored column, so the response surface is a sweep rather than a re-mark.

Derived economics carried alongside the raw features, each with its interpretation:

``event_var``      front total variance in excess of the back-month diffusive baseline,
                   ``(front_iv^2 - back_iv^2) * t_entry``. The variance the market
                   attributes to the announcement itself (Dubinsky and Johannes 2006).
``implied_jump``   ``sqrt(event_var)``, a one-standard-deviation event move as a fraction
                   of spot. The term spread's economic content, in move units.
``event_share``    ``event_var / (front_iv^2 * t_entry)``, the fraction of front-month
                   variance that is event rather than diffusion.
``jump_richness``  ``implied_jump`` over the name's own trailing mean absolute realised
                   event move, strictly prior events only. How rich this event is priced
                   against what this name actually does on its announcements.

Usage:
    python research/selection/reverse_alpha_panel.py
    python research/selection/reverse_alpha_panel.py --rebuild

References
----------
Dubinsky, A. and Johannes, M. (2006). Fundamental Uncertainty, Earnings Announcements and
Equity Options. *Working paper, Columbia University*.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.engine.pnl import (  # noqa: E402
    ACCOUNT_SIZE,
    regt_straddle_margin,
    size_contracts,
)
from earnings_iv_crush.research.gates import MIN_HIST  # noqa: E402
from earnings_iv_crush.strategy.filters import BELOW_ALL, expanding_gate_rank  # noqa: E402,F401

OUT = Path("outputs/research/reverse_alpha")
CACHE = OUT / "panel.parquet"

# The two disjoint blocks. Discovery is where the gate was searched and where it is
# materially profitable; holdout is the block the frozen spec failed on, which is what
# makes it the honest validation sample rather than a second helping of the same regime.
BLOCKS = {
    "discovery_2019_2024": "outputs/research/events_megacap_databento.parquet",
    "holdout_2013_2018": "data/processed/events_megacap_quotes_2013_2018.parquet",
}

# Sizing fraction and account are the frozen spec's, so per-trade returns on this panel are
# on the same basis as the settled N=391 book.
FRACTION = mv.FRACTION


# ── derived economics ────────────────────────────────────────────────────────


#: Sentinel rank for an event below every prior observation. Such an event fails the gate
def trailing_name_move(df: pd.DataFrame, min_hist: int = 3) -> np.ndarray:
    """Mean absolute realised event move over the name's own strictly earlier events.

    The denominator of the richness ratio. Kept name-specific and strictly causal: a
    cross-sectional average would import the fact that some names simply move more, which
    is the confound the ratio exists to remove.
    """
    out = np.full(len(df), np.nan)
    mv_abs = pd.to_numeric(df["realised_move"], errors="coerce").abs().to_numpy(dtype=float)
    dates = df["announce_date"].to_numpy()
    tick = df["ticker"].to_numpy()
    for i in range(len(df)):
        prior = mv_abs[(tick == tick[i]) & (dates < dates[i])]
        prior = prior[np.isfinite(prior)]
        if len(prior) >= min_hist:
            out[i] = float(prior.mean())
    return out


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the economically motivated transformations of the raw at-entry features."""
    d = df.copy()
    f = pd.to_numeric(d["front_atm_iv"], errors="coerce")
    b = pd.to_numeric(d["back_atm_iv"], errors="coerce")
    t = pd.to_numeric(d["t_entry"], errors="coerce")

    # Variance in excess of the back-month diffusive baseline, over the front tenor.
    # Clipped at zero: an inverted term structure prices no event variance, it does not
    # price negative variance, and a negative under the root would propagate NaN into
    # every downstream ratio.
    d["front_var"] = f**2 * t
    d["event_var"] = np.maximum(f**2 - b**2, 0.0) * t
    d["implied_jump"] = np.sqrt(d["event_var"])
    d["event_share"] = np.where(d["front_var"] > 0, d["event_var"] / d["front_var"], np.nan)

    d["name_move_hist"] = trailing_name_move(d)
    d["jump_richness"] = np.where(
        d["name_move_hist"] > 0, d["implied_jump"] / d["name_move_hist"], np.nan
    )
    # The same richness idea built on the whole straddle rather than the event component,
    # carried so the two can be told apart rather than assumed equivalent.
    d["move_richness"] = np.where(
        d["name_move_hist"] > 0,
        pd.to_numeric(d["implied_move"], errors="coerce") / d["name_move_hist"],
        np.nan,
    )
    return d


# ── marking ──────────────────────────────────────────────────────────────────


def price_events(ev: pd.DataFrame) -> pd.DataFrame:
    """Size and margin every marked event, ungated, carrying the components of P&L.

    Mirrors ``market_validate._ledger`` exactly on the frozen cost basis, but keeps the
    gross credit, gross buy-back and contract count so P&L can be decomposed downstream
    instead of arriving as a single net number.
    """
    rows: list[dict] = []
    for _, e in ev.iterrows():
        credit, exit_ = float(e.get("credit_mkt", np.nan)), float(e.get("exit_mkt", np.nan))
        if not (np.isfinite(credit) and np.isfinite(exit_) and credit > 0):
            continue
        spot, strike = float(e["spot_entry"]), float(e["strike_mkt"])
        contracts = size_contracts(ACCOUNT_SIZE, spot, strike, credit, FRACTION)
        if contracts <= 0:
            continue
        margin = regt_straddle_margin(spot, strike, credit, contracts)
        gross = (credit - exit_) * 100 * contracts
        cost = mv.MEGACAP_COST.round_trip_cost(credit, exit_, contracts).total_cost
        rows.append(
            {
                "ticker": e["ticker"],
                "announce_date": e["announce_date"],
                "entry_date": e["entry_date"],
                "exit_date": e["exit_date"],
                "strike_mkt": strike,
                "spot_entry": spot,
                "spot_exit": float(e["spot_exit"]),
                "credit_mkt": credit,
                "exit_mkt": exit_,
                "exit_ask": float(e.get("exit_ask", np.nan)),
                "intr_exit": float(e.get("intr_exit", np.nan)),
                "contracts": contracts,
                "margin": margin,
                "gross_pnl": gross,
                "cost_frozen": cost,
                "pnl": gross - cost,
                "return_on_margin": (gross - cost) / margin if margin else np.nan,
                "rom_gross": gross / margin if margin else np.nan,
                "stale_exit": bool(e.get("stale_exit", False)),
                "repaired_exit": bool(e.get("repaired_exit", False)),
            }
        )
    return pd.DataFrame(rows)


def marked_events(label: str, path: str, rebuild: bool = False) -> pd.DataFrame:
    """The causal-window event frame with market marks attached, cached per block."""
    cache = OUT / f"marked_{label}.parquet"
    if cache.exists() and not rebuild:
        return pd.read_parquet(cache)
    print(f"  {label}: marking off cached quotes ...")
    events, fair = mv._prepare(path, chain_path=dq.cache_path)
    events = events.copy()
    events["fair_move"] = fair.to_numpy()
    OUT.mkdir(parents=True, exist_ok=True)
    events.to_parquet(cache, index=False)
    return events


def build_block(label: str, path: str, rebuild: bool = False) -> pd.DataFrame:
    """Mark, price and enrich one block over its causal window."""
    events = marked_events(label, path, rebuild=rebuild)
    events = events.sort_values(["announce_date", "ticker"]).reset_index(drop=True)

    # Ranked on the FULL causal window, before pricing drops anything. The frozen gate is
    # applied to that frame in ``validate_screen``, so ranking only the priceable subset
    # would silently change every prior distribution and with it the selection.
    events["term_rank"] = expanding_gate_rank(
        pd.to_numeric(events["iv_term_spread"], errors="coerce").to_numpy(dtype=float),
        events["announce_date"].to_numpy(),
    )

    priced = price_events(events)
    keys = ["ticker", "entry_date"]
    carry = [c for c in events.columns if c not in priced.columns or c in keys]
    panel = priced.merge(events[carry].drop_duplicates(keys), on=keys, how="left")
    panel["block"] = label
    panel["announce_date"] = pd.to_datetime(panel["announce_date"])
    panel = panel.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    panel = add_derived(panel)

    iv_e = pd.to_numeric(panel["iv_entry"], errors="coerce")
    iv_x = pd.to_numeric(panel["iv_exit"], errors="coerce")
    panel["crush"] = np.where(iv_e > 0, (iv_e - iv_x) / iv_e, np.nan)

    print(
        f"  {label}: {len(panel):4d} priced events, {panel['ticker'].nunique()} names, "
        f"{panel['announce_date'].dt.date.nunique()} dates, "
        f"{panel['announce_date'].min():%Y-%m} to {panel['announce_date'].max():%Y-%m}"
    )
    return panel


def load_panel(rebuild: bool = False) -> pd.DataFrame:
    """The cached panel, built on first use."""
    if CACHE.exists() and not rebuild:
        return pd.read_parquet(CACHE)
    OUT.mkdir(parents=True, exist_ok=True)
    print("building the marked panel (this pays the marking cost once) ...")
    panel = pd.concat(
        [build_block(k, v, rebuild=rebuild) for k, v in BLOCKS.items()],
        ignore_index=True,
    )
    panel.to_parquet(CACHE, index=False)
    print(f"\nwrote {CACHE.resolve()}  ({len(panel)} events)")
    return panel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild", action="store_true", help="re-mark even if the cache exists")
    args = ap.parse_args()
    panel = load_panel(rebuild=args.rebuild)

    print("\nper-block summary on the frozen cost basis, ungated:")
    for blk, g in panel.groupby("block"):
        rom = pd.to_numeric(g["return_on_margin"], errors="coerce").dropna()
        print(
            f"  {blk:22s} n={len(rom):4d}  mean RoM {rom.mean():+.5f}  "
            f"per-trade Sharpe {rom.mean() / rom.std(ddof=1):+.5f}  hit {(rom > 0).mean():.3f}"
        )

    have = panel["term_rank"].notna().sum()
    print(
        f"\nterm_rank populated on {have} of {len(panel)} events (the rest lack {MIN_HIST} priors)"
    )


if __name__ == "__main__":
    main()
