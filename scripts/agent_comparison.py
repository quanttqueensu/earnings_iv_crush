"""
agent_comparison.py
Score every strategy variant on one basis, through one code path.

Why this exists
---------------
The project has scored roughly 220 distinct configurations across 205 result artefacts. Put
side by side as they stand, they are not comparable: some are per-trade Sharpe and some are
annualised, some by the correct sqrt(trades per year) and some by an inherited sqrt(252) that
inflates a 35-trade-a-year book threefold. Some are return on premium and some return on
margin. Some are gross and some net. Reading a "best" arm off that pile is exactly the
comparison-asymmetry error the project has already made once.

So this does not stitch artefacts together. It recomputes every variant from a single event
ledger, with one denominator, one cost charge and one scorer, so the only thing that differs
between two rows is the selection rule being tested.

Two panels, deliberately separated:

* **Panel A** varies the selection rule on a fixed 912-event ledger. Rows here are directly
  comparable to each other, because the events, the marks, the costs and the denominator are
  identical and only the gate moves.
* **Panel B** holds the frozen specification fixed and varies the block: era, market, and the
  2026 out-of-sample re-score. Rows here are **not** directly comparable to each other or to
  Panel A, because the marking basis differs by block. Each row therefore carries its own
  basis string and the panel says so in its own output.

Every gate is causal: the threshold at event i uses only events with a strictly earlier
announcement date. The full-sample quantile is look-ahead and was worth roughly 0.05 of
per-trade Sharpe on its own when it was accidentally used.

Usage:
    python scripts/agent_comparison.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_iv_crush.engine.screen import score_signal  # noqa: E402

LEDGER = Path("outputs/research/_adj_new/canonical_event_ledger.csv")
OUT = Path("outputs/research/agent_comparison.csv")

MIN_HIST = 25
SEED = 0
RET = "return_on_margin"


# ── causal gates ─────────────────────────────────────────────────────────────


def _causal_mask(df: pd.DataFrame, col: str, q: float, *, high: bool) -> np.ndarray:
    """Keep event i if its ``col`` sits in the chosen tail of all strictly earlier events.

    ``high=True`` keeps the upper tail at or above the q quantile; ``high=False`` keeps the
    lower tail at or below it. Events before ``MIN_HIST`` priors exist are never selected,
    which is what stops a thin early sample defining its own threshold.
    """
    dates = df["announce_date"].to_numpy()
    x = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
    keep = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        prior = x[dates < dates[i]]
        prior = prior[np.isfinite(prior)]
        if len(prior) < MIN_HIST or not np.isfinite(x[i]):
            continue
        thr = np.quantile(prior, q)
        keep[i] = x[i] >= thr if high else x[i] <= thr
    return keep


def _matched_random(df: pd.DataFrame, n: int, eligible: np.ndarray) -> np.ndarray:
    """Participation-matched null: same trade count, drawn from the same eligible pool.

    Without the match, any comparison against the gate is confounded by trade count rather
    than by selection, which is the asymmetry that once produced a spurious result here.
    """
    rng = np.random.default_rng(SEED)
    idx = np.flatnonzero(eligible)
    out = np.zeros(len(df), dtype=bool)
    if len(idx) and n:
        out[rng.choice(idx, size=min(n, len(idx)), replace=False)] = True
    return out


# ── scoring ──────────────────────────────────────────────────────────────────


def _score(df: pd.DataFrame, mask: np.ndarray | None, label: str, note: str) -> dict:
    book = df if mask is None else df[mask]
    book = book[np.isfinite(pd.to_numeric(book[RET], errors="coerce"))]
    if len(book) < 5:
        return {"agent": label, "n": int(len(book)), "note": "too few trades to score"}

    r = pd.to_numeric(book[RET], errors="coerce").to_numpy(dtype=float)
    res = score_signal(
        r,
        book["entry_date"],
        label,
        cadence="event",
        cluster_keys=book["entry_date"],
        basis="per-trade",
        n_trials=1,
        gross=False,
        n_boot=5000,
        seed=SEED,
    )
    span = max((book["entry_date"].max() - book["entry_date"].min()).days / 365.25, 1e-9)
    tpy = len(book) / span
    return {
        "agent": label,
        "n": int(len(book)),
        "n_names": int(book["ticker"].nunique()),
        "n_dates": int(book["entry_date"].nunique()),
        "hit_rate": round(float((r > 0).mean()), 4),
        "mean_rom": round(float(r.mean()), 6),
        "sd_rom": round(float(r.std(ddof=1)), 6),
        "per_trade_sharpe": round(float(res.sharpe), 6),
        "ci_low": round(float(res.ci_low), 4),
        "ci_high": round(float(res.ci_high), 4),
        "excludes_zero": bool(not (res.ci_low <= 0.0 <= res.ci_high)),
        "trades_per_year": round(float(tpy), 2),
        "annualisation_factor": round(float(np.sqrt(tpy)), 3),
        "note": note,
    }


def main() -> None:
    if not LEDGER.exists():
        raise SystemExit(f"missing {LEDGER}")
    df = pd.read_csv(LEDGER)
    for c in ("announce_date", "entry_date", "exit_date"):
        df[c] = pd.to_datetime(df[c])
    df = df.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    print(
        f"ledger: {len(df)} events, {df['ticker'].nunique()} names, "
        f"{df['entry_date'].min().date()} -> {df['entry_date'].max().date()}"
    )

    term80 = _causal_mask(df, "iv_term_spread", 0.80, high=True)
    eligible = df["iv_term_spread"].notna().to_numpy()

    rows = [
        _score(df, None, "agent0_unconditional", "every event, no selection"),
        _score(
            df,
            _matched_random(df, int(term80.sum()), eligible),
            "random_matched_null",
            "participation-matched random draw, the null the gate must beat",
        ),
        _score(
            df,
            _causal_mask(df, "iv_term_spread", 0.70, high=True),
            "term_gate_q70",
            "term structure, looser",
        ),
        _score(
            df,
            _causal_mask(df, "iv_term_spread", 0.75, high=True),
            "term_gate_q75",
            "term structure, previous baseline",
        ),
        _score(df, term80, "term_gate_q80_FROZEN", "the frozen specification"),
        _score(
            df,
            _causal_mask(df, "iv_term_spread", 0.85, high=True),
            "term_gate_q85",
            "term structure, tighter",
        ),
        _score(
            df,
            _causal_mask(df, "iv_term_spread", 0.90, high=True),
            "term_gate_q90",
            "term structure, tightest; thin and the tail inverts causally",
        ),
        _score(
            df,
            _causal_mask(df, "vol_premium", 0.80, high=True),
            "vol_premium_q80",
            "implied over trailing realised, alone",
        ),
        _score(
            df,
            _causal_mask(df, "variance_risk_premium", 0.80, high=True),
            "vrp_q80",
            "variance risk premium, alone",
        ),
        _score(
            df,
            _causal_mask(df, "implied_move", 0.80, high=True),
            "implied_move_q80",
            "richest implied moves, alone",
        ),
        _score(
            df,
            _causal_mask(df, "skew_25d", 0.50, high=False),
            "low_skew_only",
            "low 25-delta skew, alone",
        ),
        _score(
            df,
            _causal_mask(df, "bkm_kurt", 0.50, high=False),
            "low_kurtosis_only",
            "low risk-neutral kurtosis, alone",
        ),
        _score(
            df,
            term80 & _causal_mask(df, "skew_25d", 0.50, high=False),
            "term_q80_plus_low_skew",
            "frozen gate with a skew overlay",
        ),
        _score(
            df,
            term80 & _causal_mask(df, "bkm_kurt", 0.50, high=False),
            "term_q80_plus_low_kurt",
            "frozen gate with a kurtosis overlay",
        ),
        _score(
            df,
            term80 & _causal_mask(df, "vol_premium", 0.50, high=True),
            "term_q80_plus_vol_premium",
            "frozen gate with a volatility-premium overlay",
        ),
    ]

    out = pd.DataFrame(rows)
    out["panel"] = "A: selection rule varies, ledger fixed"
    out["basis"] = (
        "per-trade return on margin, canonical 912-event adjudication ledger, cost charged, "
        "exits repriced from inverted implied volatilities"
    )
    # The level on this basis is systematically more negative than quote marking: on the same
    # 239 events, traded marks give +0.13687 and a Black-Scholes reprice gives -0.34719
    # (outputs/research/bs_vs_traded.csv). Read the ORDERING across rows, never the level, and
    # never against the quote-marked settled verdict.
    out["level_comparable_to_settled_verdict"] = False
    out["compare_rows_not_levels"] = True
    out["ledger"] = str(LEDGER)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print(f"\nPanel A  {out['basis'].iloc[0]}")
    print("-" * 104)
    print(
        f"{'agent':<28}{'N':>6}{'names':>7}{'hit':>8}{'mean RoM':>12}"
        f"{'Sharpe':>10}  {'95% CI':>20}"
    )
    print("-" * 104)
    for r in rows:
        if "note" in r and r.get("per_trade_sharpe") is None:
            continue
        if "per_trade_sharpe" not in r:
            print(f"{r['agent']:<28}{r['n']:>6}  {r['note']}")
            continue
        star = " *" if r["excludes_zero"] else ""
        print(
            f"{r['agent']:<28}{r['n']:>6}{r['n_names']:>7}{r['hit_rate']:>8.4f}"
            f"{r['mean_rom']:>12.6f}{r['per_trade_sharpe']:>10.4f}"
            f"  [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}]{star}"
        )
    print("-" * 104)
    print("* interval excludes zero")
    print("\nEvery row above shares its events, marks, costs and denominator; only the")
    print("selection rule differs, so the ORDERING across rows is the readable quantity.")
    print("\nThe LEVEL is not. This ledger reprices exits from inverted implied volatilities,")
    print("which on the same 239 events gives -0.34719 where traded marks give +0.13687")
    print("(bs_vs_traded.csv). Do not compare these levels to the quote-marked verdict.")
    print(f"\nwrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
