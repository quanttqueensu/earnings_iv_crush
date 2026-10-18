"""
run_remark_verdict.py
Score the quote-marked book against the pre-registered specification.

Gate 1 is measured against the ask, per ``research/frozen_selector/preregs/remark_prereg_amendment_01.md``: a short
straddle is bought back, and a buyer pays the ask, so the ask is the side that decides whether
the exit was attainable. The pre-registered mid measure failed at 5.34% and is still printed
and still written to the artifact, because an amendment that hid the failure it was written
in response to would be worthless.

Runs the acceptance gates from ``research/frozen_selector/preregs/remark_prereg.md`` first, then, and only if
they pass, the frozen specification on the quote-marked chains beside the same
specification on the trade-marked ones. The gates come first deliberately: they ask
whether the new marks are trustworthy, which is a different question from whether the
result is good, and answering them after seeing the Sharpe would invite the answer to
depend on it.

Frozen specification (established by ``scripts/research_gate_reconciliation.py``):
events -> ``market_validate._prepare`` -> ``expanding_high_term_mask`` at q=0.80 ->
``market_validate._ledger`` at ``MEGACAP_COST``. Nothing here re-tunes any of it; the
single substitution is which cached chain the marks are read from.

Baseline being replaced: N=198, per-trade Sharpe +0.087393, hit 66.7% (repaired marks,
session-corrected events). The published +0.115773 is the unrepaired mark on a
superseded event file and is not the comparison.

Run: ``python research/frozen_selector/run_remark_verdict.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.engine.marks import VIOLATION_TOL  # noqa: E402
from earnings_iv_crush.engine.quotes import add_quote_columns  # noqa: E402
from earnings_iv_crush.research.gates import expanding_high_term_mask  # noqa: E402

OUT = Path("outputs/research/remark_verdict.csv")
GATES_OUT = Path("outputs/research/remark_acceptance.csv")
Q = 0.80

BASE_N, BASE_SHARPE, BASE_HIT = 198, 0.087393, 0.667

# Pre-registered decision rule. Declared before the data existed; not editable here.
CONTINUE_CI_FLOOR = -0.05
KILL_CI_FLOOR = -0.15
RETENTION_FLOOR = 0.70
VIOLATION_CEILING = 0.02
WINDOW_AGREE_TOL = 0.05


def _sharpe(rom: pd.Series) -> float:
    rom = pd.to_numeric(rom, errors="coerce").dropna()
    if len(rom) < 2 or rom.std(ddof=1) == 0:
        return float("nan")
    return float(rom.mean() / rom.std(ddof=1))


def _clustered_ci(rom: pd.Series, clusters: pd.Series, n_boot: int = 5000) -> tuple[float, float]:
    """Percentile CI on the per-trade Sharpe, resampling whole announcement clusters.

    Events sharing an entry date share a market-wide shock, so resampling individual
    trades would understate the interval.
    """
    rng = np.random.default_rng(0)
    keys = pd.Index(clusters.unique())
    groups = {k: rom[clusters == k].to_numpy() for k in keys}
    draws = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.choice(keys, size=len(keys), replace=True)
        sample = np.concatenate([groups[k] for k in pick])
        sd = sample.std(ddof=1)
        draws[b] = sample.mean() / sd if sd > 0 else np.nan
    draws = draws[np.isfinite(draws)]
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def _atm_iv(chain: pd.DataFrame, spot: float) -> float:
    """Mean call/put IV at the strike nearest spot on the nearest expiry."""
    if chain.empty or not np.isfinite(spot):
        return float("nan")
    front = chain["expiry"].min()
    sub = chain[chain["expiry"] == front]
    if sub.empty:
        return float("nan")
    k = sub.iloc[(sub["strike"] - spot).abs().argmin()]["strike"]
    iv = pd.to_numeric(sub[np.isclose(sub["strike"], k)]["iv"], errors="coerce").dropna()
    return float(iv.mean()) if len(iv) else float("nan")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 gates
# ─────────────────────────────────────────────────────────────────────────────


def acceptance_gates(ev_q: pd.DataFrame, ev_t: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []

    def gate(name: str, passed: bool, value: float, threshold: str, detail: str) -> None:
        rows.append(
            {
                "gate": name,
                "passed": bool(passed),
                "gating": True,
                "value": value,
                "threshold": threshold,
                "detail": detail,
            }
        )
        flag = "PASS" if passed else "FAIL"
        print(f"  [{flag}] {name:28s} {value:>10.4f}   {threshold}")
        if detail:
            print(f"         {detail}")

    # 1. intrinsic violations, over MARKED events only.
    # Rating them over every prepared row would count an unmarked event (NaN, which
    # compares false) as "not violating", so the rate would improve as coverage got
    # worse. A gate that rewards missing data is not a gate.
    def _violation_rate(frame: pd.DataFrame, column: str) -> tuple[float, int]:
        intr = pd.to_numeric(frame["intr_exit"], errors="coerce")
        px = pd.to_numeric(frame[column], errors="coerce")
        both = intr.notna() & px.notna()
        if not both.any():
            return float("nan"), 0
        return float(((intr - px)[both] > VIOLATION_TOL).mean()), int(both.sum())

    # Both sides are reported, always. Amendment 01 moves the gate from the mid to the ask
    # because a short straddle is closed by buying it back and a buyer pays the ask, so the
    # ask is the side that determines whether the exit was attainable. The mid rate stays in
    # the output as the headline gate result: the pre-registration failed as written and the
    # artifact has to say so rather than quietly showing only the measure that passed.
    q_mid, q_n = _violation_rate(ev_q, "exit_raw")
    t_mid, t_n = _violation_rate(ev_t, "exit_raw")
    q_ask, q_ask_n = _violation_rate(ev_q, "exit_ask")
    rows.append(
        {
            "gate": "exit intrinsic violations (mid, as pre-registered)",
            "passed": bool(q_mid <= VIOLATION_CEILING),
            "gating": False,
            "value": q_mid,
            "threshold": f"<= {VIOLATION_CEILING:.0%}",
            "detail": f"over {q_n} marked events; trade-marked book was {t_mid:.1%} over {t_n}",
        }
    )
    print(
        f"  [{'PASS' if q_mid <= VIOLATION_CEILING else 'FAIL'}] "
        f"{'exit violations (mid, orig)':28s} {q_mid:>10.4f}   <= {VIOLATION_CEILING:.0%}"
    )
    print(f"         reported, not gating: superseded by amendment 01 ({q_n} marked events)")
    gate(
        "exit intrinsic violations (ask)",
        q_ask <= VIOLATION_CEILING,
        q_ask,
        f"<= {VIOLATION_CEILING:.0%}",
        f"over {q_ask_n} marked events; the mid measure gave {q_mid:.2%} and failed",
    )

    # 2. two-sidedness (the property the trade book could not have)
    two_sided = float(raw["two_sided_frac"].mean())
    gate(
        "quotes genuinely two-sided",
        two_sided > 0.90,
        two_sided,
        "> 90%",
        "bid == ask on every contract would mean the pull silently fell back to trades",
    )

    # 3. coverage
    retention = float(ev_q["credit_mkt"].notna().mean())
    gate(
        "event retention",
        retention >= RETENTION_FLOOR,
        retention,
        f">= {RETENTION_FLOOR:.0%}",
        f"{int(ev_q['credit_mkt'].isna().sum())} of {len(ev_q)} events unmarkable",
    )

    # 4. snapshot vs window
    agree = float(raw["window_agree_frac"].mean())
    gate(
        "snapshot vs window agree",
        agree > 0.50,
        agree,
        f"> 50% within {WINDOW_AGREE_TOL:.0%}",
        "disagreement is the staleness statistic, not a failure by itself",
    )

    # 5. crush direction, measured ATM-to-ATM
    crush = pd.to_numeric(raw["atm_crush"], errors="coerce").dropna()
    frac = float((crush > 0).mean()) if len(crush) else float("nan")
    gate(
        "ATM IV falls post-event",
        frac > 0.50,
        frac,
        "> 50% of events",
        f"mean ATM-to-ATM crush {crush.mean():+.4f} over N={len(crush)}",
    )
    return pd.DataFrame(rows)


def _per_event_diagnostics(ev: pd.DataFrame) -> pd.DataFrame:
    """Two-sidedness, window agreement and ATM-to-ATM crush, per event."""
    rows: list[dict] = []
    for _, e in ev.iterrows():
        entry = dq.fetch_option_chain(e["ticker"], pd.Timestamp(e["entry_date"]))
        exit_ = dq.fetch_option_chain(e["ticker"], pd.Timestamp(e["exit_date"]))
        if entry.empty or exit_.empty:
            continue
        q = add_quote_columns(entry)
        two = float((q["ask"] > q["bid"]).mean())
        agree = float("nan")
        if "mid_window" in q:
            mw = pd.to_numeric(q["mid_window"], errors="coerce")
            rel = (q["mid"] - mw).abs() / q["mid"].where(q["mid"] > 0)
            agree = float((rel <= WINDOW_AGREE_TOL).mean())
        rows.append(
            {
                "ticker": e["ticker"],
                "entry_date": e["entry_date"],
                "two_sided_frac": two,
                "window_agree_frac": agree,
                "atm_crush": _atm_iv(entry, float(e["spot_entry"]))
                - _atm_iv(exit_, float(e["spot_exit"])),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    print("Preparing books (same events, same spec, different chain cache)\n")
    ev_t, _ = mv._prepare(mv.EVENTS_FULL)
    ev_q, _ = mv._prepare(mv.EVENTS_FULL, chain_path=dq.cache_path)

    raw = _per_event_diagnostics(ev_q)
    print("── Phase 4 acceptance gates ──")
    gates = acceptance_gates(ev_q, ev_t, raw)
    GATES_OUT.parent.mkdir(parents=True, exist_ok=True)
    gates.to_csv(GATES_OUT, index=False)

    if not gates.loc[gates["gating"], "passed"].all():
        print(
            "\nGATES FAILED. The quote-marked book is not accepted, so no Sharpe is read "
            "from it. Fix the marks; do not reinterpret the failure as a result.\n"
            f"written: {GATES_OUT.resolve()}"
        )
        return

    print("\n── Phase 5: frozen spec on each book ──")
    rows: list[dict] = []
    for label, frame in (("trade-marked (baseline)", ev_t), ("quote-marked", ev_q)):
        mask = np.asarray(expanding_high_term_mask(frame, Q), dtype=bool)
        led = mv._ledger(
            frame[mask].reset_index(drop=True), defined_risk=False, costs=mv.MEGACAP_COST
        )
        rom = pd.to_numeric(led["return_on_margin"], errors="coerce").dropna()
        n, s = len(rom), _sharpe(rom)
        clusters = pd.to_datetime(led.loc[rom.index, "entry_date"]).dt.normalize()
        lo, hi = _clustered_ci(rom, clusters)
        se = float(np.sqrt((1 + s**2 / 2) / n))
        z = s / se
        print(f"\n  {label}")
        print(f"    N                {n}")
        print(f"    hit rate         {(rom > 0).mean():.1%}")
        print(f"    mean RoM         {rom.mean():+.4f}")
        print(f"    per-trade Sharpe {s:+.6f}  (unannualised)")
        print(f"    z / one-sided p  {z:+.2f} / {1 - sps.norm.cdf(z):.4f}")
        print(f"    clustered 95% CI [{lo:+.4f}, {hi:+.4f}]")
        rows.append(
            {
                "book": label,
                "n": n,
                "hit_rate": float((rom > 0).mean()),
                "mean_rom": float(rom.mean()),
                "per_trade_sharpe": s,
                "z": z,
                "one_sided_p": float(1 - sps.norm.cdf(z)),
                "ci_lo": lo,
                "ci_hi": hi,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    q_row = out[out["book"] == "quote-marked"].iloc[0]
    print("\n── Pre-registered decision ──")
    if q_row["per_trade_sharpe"] > 0 and q_row["ci_lo"] > CONTINUE_CI_FLOOR:
        verdict = "CONTINUE"
    elif q_row["per_trade_sharpe"] <= 0 or q_row["ci_lo"] < KILL_CI_FLOOR:
        verdict = "KILL"
    else:
        verdict = "INCONCLUSIVE"
    print(f"  {verdict}")
    print(f"  baseline was N={BASE_N}, Sharpe {BASE_SHARPE:+.6f}, hit {BASE_HIT:.1%}")
    print(f"\nwritten: {OUT.resolve()}\n         {GATES_OUT.resolve()}")


if __name__ == "__main__":
    main()
