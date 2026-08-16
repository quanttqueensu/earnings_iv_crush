"""
score_oos_2026.py
Score the 2025-2026 broad-universe block on the settled book's own basis.

Why this exists
---------------
``outputs/research/events_broad_oos_2025.parquet`` holds 2,037 events across 346 names
from 2025-01-09 to 2026-06-04. It was built after the 1,476-trial search concluded, so no
parameter in the frozen specification was chosen with reference to any observation in it.
It is the only genuinely untouched block the project has.

It is currently scored only in ``broad_oos_2025_verdict.csv`` on basis
``gross_at_mid_alpaca_bs_inverted``: gross, at the mid, on Black-Scholes-inverted marks.
That number is a diagnostic, not an investable result, and it is roughly an order of
magnitude more flattering than the same book scored honestly.

This module re-scores the same events the way the settled verdict is scored: exits marked
off the exit session's own chain at the strike and expiry actually sold, return on margin
rather than return on premium, and cost charged. The specification and both kill criteria
were written to ``outputs/research/prereg_oos_2026.json`` before the first pull.

The exit mark is the point. A short straddle closed before expiry is bought back at
intrinsic *plus* the premium still in the contract; substituting intrinsic leaves that
premium uncharged, which on the 912-event canonical ledger averages 55.1% of entry credit
and turns a mean return on margin of -0.1142 into +0.1928. It inverts the sign rather than
merely inflating it.

Chain acquisition, parsing and marking are imported from ``scripts.backfill_forward_window``
rather than reimplemented, so both forward paths share one marking convention and the
provenance tests cover both.

Usage:
    python scripts/score_oos_2026.py --dry-run          # price everything, pull nothing
    python scripts/score_oos_2026.py --cap 15 --workers 6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from earnings_iv_crush.engine.pnl import regt_straddle_margin  # noqa: E402
from earnings_iv_crush.engine.screen import score_signal  # noqa: E402
from scripts.backfill_forward_window import (  # noqa: E402
    _chain,
    _client,
    _mark,
    _prefetch,
    _spot_at,
    _spot_table,
    _straddle,
)
from scripts.validate_skew_oos import expanding_high_term_mask  # noqa: E402

EVENTS = Path("outputs/research/events_broad_oos_2025.parquet")
PREREG = Path("outputs/research/prereg_oos_2026.json")
OUT_LEDGER = Path("outputs/research/oos_2026_ledger.csv")
OUT_VERDICT = Path("outputs/research/oos_2026_verdict.csv")

Q = 0.80  # frozen term-gate percentile; earnings_iv_crush/frozen.py
COST = 0.116  # canonical break-even, fraction of entry premium, round trip
CONTRACT_MULTIPLIER = 100
SEED = 0


# ── event preparation ────────────────────────────────────────────────────────


def _load_events() -> pd.DataFrame:
    """The block, sorted causally, with the frozen gate and its matched null attached."""
    ev = pd.read_parquet(EVENTS)
    for c in ("announce_date", "entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c])
    ev = ev.sort_values(["announce_date", "ticker"]).reset_index(drop=True)

    ev["term_gate"] = expanding_high_term_mask(ev, Q)

    # Participation-matched null: the same number of trades drawn at random from the
    # events the gate could have chosen from. Without the match, any comparison is
    # confounded by trade count rather than by selection.
    eligible = ev["iv_term_spread"].notna().to_numpy()
    n_gate = int(ev["term_gate"].sum())
    rng = np.random.default_rng(SEED)
    idx = np.flatnonzero(eligible)
    pick = rng.choice(idx, size=min(n_gate, len(idx)), replace=False)
    ev["random_gate"] = False
    ev.loc[pick, "random_gate"] = True
    return ev


# ── scoring ──────────────────────────────────────────────────────────────────


def _score_rows(ev: pd.DataFrame, spots: pd.DataFrame) -> pd.DataFrame:
    """Mark every event off its own cached chains and build the per-trade ledger.

    Attrition is counted by reason rather than dropped silently: an empty result from a
    marking pass is indistinguishable from a quiet calendar unless the funnel is printed.
    """
    reasons: dict[str, int] = {}

    def drop(why: str) -> None:
        reasons[why] = reasons.get(why, 0) + 1

    rows = []
    for _, e in ev.iterrows():
        tkr = str(e["ticker"])
        d_in, d_out = e["entry_date"], e["exit_date"]

        s_in = _spot_at(spots, tkr, d_in)
        s_out = _spot_at(spots, tkr, d_out)
        if s_in is None or s_out is None:
            drop("no spot")
            continue

        ch_in = _cached(tkr, d_in)
        if ch_in is None:
            drop("no entry chain")
            continue
        built = _straddle(ch_in, s_in)
        if built is None:
            drop("entry chain unquoted at the money")
            continue
        straddle_in, implied_move, strike, expiry = built

        ch_out = _cached(tkr, d_out)
        if ch_out is None:
            drop("no exit chain")
            continue
        straddle_out = _mark(ch_out, strike, expiry)
        if straddle_out is None:
            drop("exit leg unquoted at the sold strike")
            continue

        credit = straddle_in * CONTRACT_MULTIPLIER
        exit_value = straddle_out * CONTRACT_MULTIPLIER
        margin = regt_straddle_margin(s_in, strike, straddle_in, 1)
        if margin <= 0:
            drop("non-positive margin")
            continue

        cost = COST * credit
        rows.append(
            {
                "ticker": tkr,
                "announce_date": e["announce_date"],
                "entry_date": d_in,
                "exit_date": d_out,
                "strike": strike,
                "expiry": expiry,
                "spot_entry": s_in,
                "spot_exit": s_out,
                "straddle_entry": straddle_in,
                "straddle_exit": straddle_out,
                "implied_move": implied_move,
                "realised_move": abs(s_out / s_in - 1.0),
                "credit": credit,
                "exit_value": exit_value,
                "margin": margin,
                "cost": cost,
                "gross_rom": (credit - exit_value) / margin,
                "net_rom": (credit - exit_value - cost) / margin,
                "gross_rop": (credit - exit_value) / credit,
                "net_rop": (credit - exit_value - cost) / credit,
                "term_gate": bool(e["term_gate"]),
                "random_gate": bool(e["random_gate"]),
                "iv_term_spread": e["iv_term_spread"],
                "mark_source": "quote",
                "source": "backtest_oos_2026",
            }
        )

    print("\n  marking funnel:")
    print(f"    events considered           {len(ev)}")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    dropped, {why:<32} {n}")
    print(f"    scored                      {len(rows)}")
    if not rows:
        raise SystemExit("no events could be marked - refusing to write an empty verdict")
    return pd.DataFrame(rows)


_CACHE = Path("data/cache/backfill_chains")


def _cached(ticker: str, day: pd.Timestamp) -> pd.DataFrame | None:
    """Read a chain from the shared cache. Never pulls; the prefetch owns spend."""
    p = _CACHE / f"{ticker}_{pd.Timestamp(day).date()}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def _arm(led: pd.DataFrame, label: str, col: str | None, trials: int) -> dict:
    """Score one book through the shared screen contract."""
    book = led if col is None else led[led[col]]
    if len(book) < 2:
        return {"arm": label, "n": len(book), "note": "too few trades to score"}
    res = score_signal(
        book["net_rom"].to_numpy(dtype=float),
        book["entry_date"],
        label,
        cadence="event",
        cluster_keys=book["entry_date"],
        basis="per-trade",
        n_trials=trials,
        gross=False,
        n_boot=5000,
        seed=SEED,
    )
    span_yr = max((book["entry_date"].max() - book["entry_date"].min()).days / 365.25, 1e-9)
    tpy = len(book) / span_yr
    return {
        "arm": label,
        "n": int(len(book)),
        "n_names": int(book["ticker"].nunique()),
        "n_clusters": int(book["entry_date"].nunique()),
        "hit_rate": float((book["net_rom"] > 0).mean()),
        "mean_gross_rom": float(book["gross_rom"].mean()),
        "mean_net_rom": float(book["net_rom"].mean()),
        "sd_net_rom": float(book["net_rom"].std(ddof=1)),
        "per_trade_sharpe": float(res.sharpe),
        "ci_low": float(res.ci_low),
        "ci_high": float(res.ci_high),
        "contains_zero": bool(res.ci_low <= 0.0 <= res.ci_high),
        "trades_per_year": float(tpy),
        "annualisation_factor": float(np.sqrt(tpy)),
        "annualised_sharpe": float(res.sharpe * np.sqrt(tpy)),
        "basis": "per-trade return on margin, net of 11.6% of premium round trip",
        "n_trials_charged": trials,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cap", type=float, default=15.0, help="hard USD spend cap")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true", help="price everything, pull nothing")
    args = ap.parse_args()

    print(f"pre-registration: {PREREG}")
    if not PREREG.exists():
        raise SystemExit("pre-registration missing - refusing to run")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    print(f"  trial_id  {prereg['trial_id']}")
    print(f"  declared  {prereg['declared_utc']}")

    ev = _load_events()
    print(
        f"\nblock: {len(ev)} events, {ev['ticker'].nunique()} names, "
        f"{ev['entry_date'].min().date()} -> {ev['entry_date'].max().date()}"
    )
    print(
        f"  term gate selects {int(ev['term_gate'].sum())}, "
        f"matched random null {int(ev['random_gate'].sum())}"
    )

    jobs = sorted(
        {(str(r.ticker), pd.Timestamp(r.entry_date)) for r in ev.itertuples()}
        | {(str(r.ticker), pd.Timestamp(r.exit_date)) for r in ev.itertuples()}
    )
    have = sum(1 for t, d in jobs if (_CACHE / f"{t}_{d.date()}.parquet").exists())
    print(f"\nchains required {len(jobs)}, already cached {have}, to fetch {len(jobs) - have}")

    cap_state = {"cap": args.cap, "spent": 0.0, "estimated": 0.0}
    if args.dry_run:
        cl = _client()
        sample = [j for j in jobs if not (_CACHE / f"{j[0]}_{j[1].date()}.parquet").exists()][:40]
        print(f"\npricing a {len(sample)}-chain sample to extrapolate...")
        for t, d in sample:
            _chain(cl, t, d, cap_state, dry=True)
        if not sample:
            print("  nothing to fetch")
            return
        per = cap_state["estimated"] / len(sample)
        print(f"\n  per-chain ${per:.6f}")
        print(
            f"  extrapolated total ${per * (len(jobs) - have):.4f} "
            f"for {len(jobs) - have} chains, cap ${args.cap:.2f}"
        )
        return

    print(f"\nfetching (cap ${args.cap:.2f})...")
    cl = _client()
    _prefetch(cl, jobs, cap_state, args.workers)
    print(f"\nactual spend ${cap_state['spent']:.4f} against cap ${args.cap:.2f}")

    tickers = sorted(ev["ticker"].unique())
    spots = _spot_table(
        tickers,
        ev["entry_date"].min().strftime("%Y-%m-%d"),
        ev["exit_date"].max().strftime("%Y-%m-%d"),
    )

    led = _score_rows(ev, spots)
    OUT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    led.to_csv(OUT_LEDGER, index=False)

    arms = [
        _arm(led, "agent0_unconditional", None, 1),
        _arm(led, "term_gate_q80_frozen", "term_gate", 1),
        _arm(led, "random_gate_matched", "random_gate", 1),
    ]
    out = pd.DataFrame(arms)
    out["spend_usd"] = round(cap_state["spent"], 4)
    out["block"] = "2025-01-09..2026-06-04"
    out.to_csv(OUT_VERDICT, index=False)

    print("\n" + "=" * 92)
    for a in arms:
        if "note" in a:
            print(f"{a['arm']:<24} {a['note']}")
            continue
        star = "" if a["contains_zero"] else "  <- interval excludes zero"
        print(
            f"{a['arm']:<24} N={a['n']:<5} hit={a['hit_rate']:.4f}  "
            f"mean RoM={a['mean_net_rom']:+.6f}  Sharpe={a['per_trade_sharpe']:+.6f} "
            f"[{a['ci_low']:+.4f}, {a['ci_high']:+.4f}]{star}"
        )
    print("=" * 92)
    print(f"\nledger  {OUT_LEDGER.resolve()}")
    print(f"verdict {OUT_VERDICT.resolve()}")


if __name__ == "__main__":
    main()
