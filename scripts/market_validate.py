"""
market_validate.py
OOS validation on *market-marked* straddles (actual two-leg closes), not the
single-IV BS round-trip. Iteration harness toward a sharper book.

The event builder marks the exit by inverting each leg to one ATM IV and repricing
via Black-Scholes; on asynchronous daily closes that round-trip destroys the signal
(see the diagnosis). Here every trade is marked on the real straddle prices
(call_close + put_close at the entry strike, same expiry, entry vs exit), then the
causal gates (term, low-skew, move) and a defined-risk variant are scored per-trade
and annualised. No network, no credits.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.engine.backtester import backtest  # noqa: E402
from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.marks import dedupe_contracts, mark_straddle  # noqa: E402
from earnings_iv_crush.engine.pnl import (  # noqa: E402
    ACCOUNT_SIZE,
    regt_straddle_margin,
    size_contracts,
)
from earnings_iv_crush.engine.quotes import side_price  # noqa: E402
from earnings_iv_crush.strategy.fair_move_model import FairMoveModel  # noqa: E402
from earnings_iv_crush.strategy.filters import passes_move_filter  # noqa: E402
from scripts.validate_skew_oos import (  # noqa: E402
    MIN_HIST,
    MOVE_RATIO,
    SKEW_KEEP,
    TERM_PCTL,
    expanding_high_term_mask,
    expanding_low_skew_mask,
)

EVENTS_OOS = "outputs/research/events_megacap_databento_oos.parquet"  # clean OOS (<=2023)
EVENTS_FULL = "outputs/research/events_megacap_databento.parquet"  # 2019-2024, Databento-marked
OUT_DIR = Path("outputs/research")  # where the result CSVs (figure/paper sources) land
FRACTION = 0.05
WING_MULT = 1.5  # defined-risk wings at +/- this x the implied move
# How far, in log terms, the chosen ATM entry strike may sit from spot before the two are
# judged to be quoted on different split bases. The strike is at the money by
# construction, so the real distribution is a rounding artefact of the strike ladder
# (median |log-moneyness| ~0.002); 0.15 is far outside it and catches only the genuine
# basis breaks, which on this book are GE's seven pre-reverse-split events.
_BASIS_TOL = 0.15


def _legs(chain: pd.DataFrame, expiry, strike, right, side: str = "mid") -> float:
    """One leg's price, on the mid by default.

    Read ``bid`` unconditionally until the quote migration. That was invisible while the
    close-marked feeds set ``bid == ask == close``, and wrong on real quotes: marking the
    entry and the exit both at the bid understates the buy-back a short pays.
    """
    s = chain[
        (chain["expiry"] == expiry)
        & (np.isclose(chain["strike"], strike))
        & (chain["right"] == right)
    ]
    if not len(s):
        return np.nan
    # Same duplicate rule as ``engine.marks``: identical rows collapse, timestamped rows
    # order, and disagreeing rows that cannot be ordered raise rather than letting row
    # order pick a price. Uniform across every site that resolves a contract to one quote.
    s = dedupe_contracts(s, label=f"_legs({expiry}, {strike}, {right})")
    row = s.iloc[0]
    return side_price(row.get("bid", np.nan), row.get("ask", np.nan), side)  # type: ignore[arg-type]


def _nearest(chain: pd.DataFrame, expiry, target: float) -> float:
    sub = chain[chain["expiry"] == expiry]
    if sub.empty or not np.isfinite(target):
        return np.nan
    return float(sub.iloc[(sub["strike"] - target).abs().argmin()]["strike"])


def market_marks(ev: pd.DataFrame, chain_path=None) -> pd.DataFrame:
    """Augment events with the real ATM straddle credit/exit (per share) and the
    defined-risk strangle wing prices, all from the cached chains.

    The straddle marks are repaired for per-leg staleness via ``engine.marks``: after
    an earnings gap the in-the-money leg's last print goes stale relative to its
    partner, which marks the straddle below its own intrinsic value and lets a short
    book "buy back" cheaper than was physically possible. Set ``IVCRUSH_MARK=raw`` to
    reproduce the unrepaired historical book (Sharpe +0.116) for comparison.

    Parameters
    ----------
    chain_path : callable or None, optional
        ``(ticker, timestamp) -> Path`` locating a cached chain. Defaults to the
        trade-marked Databento cache, which is the frozen specification. Pass
        ``databento_quotes.cache_path`` to score the identical specification on
        quote-marked chains; that substitution is the entire re-mark experiment, so it
        lives here as one argument rather than as a forked copy of this function.
    """
    locate = chain_path if chain_path is not None else dbo._cache_path
    repair = os.environ.get("IVCRUSH_MARK", "parity").lower() != "raw"
    rows: list[dict] = []
    n_basis = [0]  # events refused because spot and strikes are on different bases
    for _, e in ev.iterrows():
        pe, px = (
            locate(e["ticker"], pd.Timestamp(e["entry_date"])),
            locate(e["ticker"], pd.Timestamp(e["exit_date"])),
        )
        if not (pe.exists() and px.exists()):
            rows.append({})
            continue
        ce, cx = pd.read_parquet(pe), pd.read_parquet(px)
        if ce.empty or cx.empty:
            rows.append({})
            continue
        target_exp = pd.Timestamp(e["entry_date"]) + pd.Timedelta(days=round(e["t_entry"] * 365))
        fexp = ce["expiry"].iloc[(ce["expiry"] - target_exp).abs().argmin()]
        k = _nearest(ce, fexp, e["spot_entry"])

        # Basis check. The entry strike is at the money by construction, so it cannot sit
        # far from spot. When it does, the spot and the strikes are quoted on different
        # bases: the chain builder recovers the RAW price OPRA lists strikes in (via
        # `databento_options._split_factor`), while the event table's `spot_entry` comes
        # from the adjusted yfinance series. For a name with a later split or spin-off the
        # two diverge, and `_nearest` then picks a strike that was never near the money -
        # on GE's pre-2021 events, a $14 strike against a $65 "spot". Every mark built on
        # that is meaningless and would surface downstream as a huge fake intrinsic
        # violation, so refuse it here instead of pricing it.
        if np.isfinite(k) and abs(np.log(float(e["spot_entry"]) / float(k))) > _BASIS_TOL:
            n_basis[0] += 1
            rows.append({})
            continue

        m_in = mark_straddle(ce, expiry=fexp, strike=k, spot=float(e["spot_entry"]), repair=repair)
        m_out = mark_straddle(cx, expiry=fexp, strike=k, spot=float(e["spot_exit"]), repair=repair)
        credit, buyback = m_in.price, m_out.price
        # Defined-risk wings: long OTM call+put at ~WING_MULT x implied move.
        off = WING_MULT * float(e["implied_move"]) * e["spot_entry"]
        kc, kp = _nearest(ce, fexp, e["spot_entry"] + off), _nearest(
            ce, fexp, e["spot_entry"] - off
        )
        wing_credit = _legs(ce, fexp, kc, "C") + _legs(ce, fexp, kp, "P")
        wing_exit = _legs(cx, fexp, kc, "C") + _legs(cx, fexp, kp, "P")
        rows.append(
            {
                "strike_mkt": k,
                "credit_mkt": credit,
                "exit_mkt": buyback,
                "wing_credit": wing_credit,
                "wing_exit": wing_exit,
                # Audit trail: what the feed said before repair, and whether it was
                # physically possible. Downstream studies can filter on these.
                "credit_raw": m_in.raw_price,
                "exit_raw": m_out.raw_price,
                # The exit at the ask, and the expiry it was struck on. A short straddle is
                # closed by buying it back, so the ask is the side that has to clear the
                # intrinsic floor for the exit to be attainable at all; the mid can sit
                # below it purely because a deep-ITM bid does, which is ordinary market
                # structure rather than a mispricing. Emitted so the acceptance gate can
                # test both sides without re-deriving the strike and expiry.
                "expiry_mkt": fexp,
                "exit_ask": (
                    _legs(cx, fexp, k, "C", side="ask") + _legs(cx, fexp, k, "P", side="ask")
                ),
                "intr_entry": m_in.intrinsic,
                "intr_exit": m_out.intrinsic,
                "stale_entry": m_in.violated,
                "stale_exit": m_out.violated,
                "repaired_exit": m_out.repaired,
            }
        )
    if n_basis[0]:
        print(
            f"market_marks: {n_basis[0]} event(s) refused - the entry strike sits more than "
            f"{_BASIS_TOL:.0%} in log terms from spot, so the spot and the chain's strikes are "
            "on different split bases and no mark is possible."
        )
    return ev.join(pd.DataFrame(rows, index=ev.index))


def _ledger(ev: pd.DataFrame, defined_risk: bool, costs: CostModel) -> pd.DataFrame:
    """Per-trade market-marked ledger for the naked straddle or the iron fly."""
    out = []
    for _, e in ev.iterrows():
        credit, exit_ = float(e["credit_mkt"]), float(e["exit_mkt"])
        if not (np.isfinite(credit) and np.isfinite(exit_) and credit > 0):
            continue
        spot, strike = float(e["spot_entry"]), float(e["strike_mkt"])
        contracts = size_contracts(ACCOUNT_SIZE, spot, strike, credit, FRACTION)
        if contracts <= 0:
            continue
        net_credit, net_exit = credit, exit_
        if defined_risk and np.isfinite(e["wing_credit"]) and np.isfinite(e["wing_exit"]):
            net_credit = credit - float(e["wing_credit"])  # pay for wings up front
            net_exit = exit_ - float(e["wing_exit"])  # wings offset the buy-back
        gross = (net_credit - net_exit) * 100 * contracts
        cost = costs.round_trip_cost(credit, exit_, contracts).total_cost
        if defined_risk:
            cost *= 2  # four legs instead of two
        margin = regt_straddle_margin(spot, strike, credit, contracts)
        pnl = gross - cost
        out.append(
            {
                "ticker": e["ticker"],
                "entry_date": e["entry_date"],
                "exit_date": e["exit_date"],
                "pnl": pnl,
                "return_on_margin": pnl / margin if margin else np.nan,
            }
        )
    return pd.DataFrame(out)


def _stats(led: pd.DataFrame) -> dict:
    rom = led["return_on_margin"].astype(float)
    ann = backtest(led, ACCOUNT_SIZE)["sharpe"] if len(led) else np.nan
    return {
        "n": len(led),
        "win": (led["pnl"] > 0).mean() if len(led) else np.nan,
        "mean_rom": rom.mean(),
        "per_trade_sharpe": rom.mean() / rom.std(ddof=1) if len(led) > 1 else np.nan,
        "ann_sharpe": ann,
    }


MEGACAP_COST = CostModel(bid_ask_pct=0.04, cross_fraction=0.5)  # the central ~2% RT case


def _prepare(events_path: str, chain_path=None) -> tuple[pd.DataFrame, pd.Series]:
    """Load + market-mark an event set and return the causal-window slice and its
    walk-forward fair-move predictions, ready for gating. ``min_train``/``MIN_HIST``
    are applied here so every arm below is scored on one common past-only window.

    ``chain_path`` is forwarded to :func:`market_marks`; the default is the frozen
    trade-marked specification.
    """
    ev = (
        pd.read_parquet(events_path).sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    )
    ev = market_marks(ev, chain_path=chain_path)
    fair = FairMoveModel().fit_predict_walk_forward(ev, ev["realised_move"], min_train=20)
    oos = (np.arange(len(ev)) >= MIN_HIST) & fair.notna().to_numpy()
    return ev[oos].reset_index(drop=True), fair[oos].reset_index(drop=True)


def _gate_masks(
    eo: pd.DataFrame,
    fair_o: pd.Series,
    *,
    term_pctl: float = TERM_PCTL,
    skew_keep: float = SKEW_KEEP,
    move_ratio: float = MOVE_RATIO,
) -> dict[str, np.ndarray]:
    """The causal gate masks over a prepared window, keyed by the arm they compose."""
    term = expanding_high_term_mask(eo, term_pctl)
    skew = expanding_low_skew_mask(eo, skew_keep)
    move = passes_move_filter(eo["implied_move"], fair_o, ratio=move_ratio).fillna(False).to_numpy()
    return {
        "all (control)": np.ones(len(eo), bool),
        "term": term,
        "term+skew": term & skew,
        "term+move": term & move,
        "term+skew+move": term & skew & move,
    }


def _boot_ci(rom: np.ndarray, n_boot: int = 5000, seed: int = 0) -> tuple[float, float, float]:
    """Point per-trade Sharpe and its bootstrap 95% CI (lo, hi) over the trade ROMs."""
    pt = rom.mean() / rom.std(ddof=1) if len(rom) > 1 else np.nan
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        s = rng.choice(rom, size=len(rom), replace=True)
        sd = s.std(ddof=1)
        boots.append(s.mean() / sd if sd > 0 else 0.0)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return pt, lo, hi


def _arm_table(eo: pd.DataFrame, arms: dict[str, np.ndarray], scenarios: dict) -> pd.DataFrame:
    """Per-arm win/ROM/Sharpe across the cost scenarios; prints and returns tidy rows."""
    rows = []
    for sc_name, sc in scenarios.items():
        print(f"--- costs: {sc_name} ---")
        print(f"{'arm':18s} {'n':>4s} {'win':>6s} {'meanROM':>8s} {'perTrSh':>8s} {'annSh':>7s}")
        for name, mask in arms.items():
            led = _ledger(eo[mask], defined_risk=False, costs=sc)
            if led.empty:
                continue
            s = _stats(led)
            print(
                f"{name:18s} {s['n']:4d} {s['win']:6.1%} {s['mean_rom']:+8.2%} "
                f"{s['per_trade_sharpe']:+8.3f} {s['ann_sharpe']:+7.2f}"
            )
            rows.append({"scenario": sc_name, "arm": name, **s})
        print()
    return pd.DataFrame(rows)


def _robustness(eo: pd.DataFrame, mask: np.ndarray, label: str) -> pd.DataFrame:
    """Per-year ROM and the bootstrap Sharpe CI for one arm at the megacap cost;
    prints and returns the per-year table (with the CI carried on every row)."""
    led = _ledger(eo[mask], defined_risk=False, costs=MEGACAP_COST)
    rom = led["return_on_margin"].astype(float).to_numpy()
    yr = pd.to_datetime(led["entry_date"]).dt.year
    by = led.assign(rom=rom, year=yr).groupby("year")["rom"]
    yearly = by.mean()
    print(f"--- robustness: {label} @ megacap ~2% RT ---")
    print("per-year mean ROM / n:")
    for y, g in led.assign(rom=rom, year=yr).groupby("year"):
        print(f"  {int(y)}: {g['rom'].mean():+.2%}  (n={len(g)})")
    pt, lo, hi = _boot_ci(rom)
    print(f"per-trade Sharpe {pt:+.3f}, bootstrap 95% CI [{lo:+.3f}, {hi:+.3f}]  (n={len(rom)})")
    print(f"years with positive mean ROM: {(yearly > 0).sum()}/{len(yearly)}\n")
    out = yearly.rename("mean_rom").reset_index()
    out["n"] = by.size().to_numpy()
    out["label"] = label
    out["per_trade_sharpe"] = pt
    out["ci_lo"], out["ci_hi"], out["n_total"] = lo, hi, len(rom)
    return out


def _breakeven(eo: pd.DataFrame, mask: np.ndarray, label: str) -> pd.DataFrame:
    """Annualised Sharpe of one arm as a function of the assumed round-trip cost,
    with the bid_ask_pct at which it crosses Sharpe 0 and Sharpe 2. The megacap
    case is bid_ask_pct=0.04 crossed at the half (cross_fraction=0.5), i.e. ~2% RT."""
    grid = np.round(np.arange(0.0, 0.165, 0.01), 3)
    print(f"--- breakeven cost: {label} (cross_fraction=0.5) ---")
    print(f"{'bid_ask_pct':>11s} {'~RT cost':>9s} {'annSh':>7s}")
    sharpes = []
    for p in grid:
        led = _ledger(
            eo[mask], defined_risk=False, costs=CostModel(bid_ask_pct=p, cross_fraction=0.5)
        )
        sh = backtest(led, ACCOUNT_SIZE)["sharpe"] if len(led) > 1 else np.nan
        sharpes.append(sh)
        print(f"{p:11.2%} {p * 0.5:9.2%} {sh:+7.2f}")
    sh = np.array(sharpes, float)

    def _cross(level: float) -> float:
        # last grid point at/above ``level``, linearly interpolated to the next.
        below = np.where(sh < level)[0]
        if not len(below) or below[0] == 0:
            return np.nan
        i = below[0]
        x0, x1, y0, y1 = grid[i - 1], grid[i], sh[i - 1], sh[i]
        return float(x0 + (level - y0) * (x1 - x0) / (y1 - y0)) if y1 != y0 else float(x0)

    z, two = _cross(0.0), _cross(2.0)
    print(
        f"edge survives up to bid_ask ~{z:.1%} (RT ~{z * 0.5:.1%}); "
        f"clears Sharpe 2 below bid_ask ~{two:.1%} (RT ~{two * 0.5:.1%})\n"
    )
    out = pd.DataFrame({"bid_ask_pct": grid, "rt_cost": grid * 0.5, "ann_sharpe": sh})
    out.attrs["cross_zero"], out.attrs["cross_two"] = z, two
    return out


def _plateau(eo: pd.DataFrame, fair_o: pd.Series) -> pd.DataFrame:
    """term x move plateau: per-trade Sharpe (and n) over a small threshold grid,
    so the headline is not one lucky cut. Skew is excluded (it does not pay here)."""
    term_grid = [0.70, 0.75, 0.80]
    move_grid = [1.10, 1.20, 1.30]
    print(
        "--- plateau: term+move per-trade Sharpe (n) over TERM_PCTL x MOVE_RATIO @ megacap ~2% RT ---"
    )
    corner = "term v move"
    print(f"{corner:>11s}" + "".join(f"{m:>14.2f}" for m in move_grid))
    rows = []
    for tp in term_grid:
        term = expanding_high_term_mask(eo, tp)
        cells = []
        for mr in move_grid:
            move = passes_move_filter(eo["implied_move"], fair_o, ratio=mr).fillna(False).to_numpy()
            led = _ledger(eo[term & move], defined_risk=False, costs=MEGACAP_COST)
            rom = led["return_on_margin"].astype(float).to_numpy()
            pt = rom.mean() / rom.std(ddof=1) if len(rom) > 1 else np.nan
            cells.append(f"{pt:+.3f} ({len(rom)})")
            rows.append({"term_pctl": tp, "move_ratio": mr, "per_trade_sharpe": pt, "n": len(rom)})
        print(f"{tp:>10.2f}" + "".join(f"{c:>14s}" for c in cells))
    print()
    return pd.DataFrame(rows)


def _equity(eo: pd.DataFrame, mask: np.ndarray, label: str) -> pd.DataFrame:
    """Sequential per-trade equity for the gated arm at the megacap cost: the
    return-on-margin stream, its running mean-equity and the peak-to-trough drawdown,
    used for the equity/drawdown figure. Ordered by entry then exit date."""
    led = _ledger(eo[mask], defined_risk=False, costs=MEGACAP_COST)
    led = led.sort_values(["entry_date", "exit_date"]).reset_index(drop=True)
    rom = led["return_on_margin"].astype(float).to_numpy()
    # One unit of margin risked per trade; cumulative ROM is the equity in margin units.
    equity = np.cumsum(rom)
    peak = np.maximum.accumulate(equity)
    return pd.DataFrame(
        {
            "trade": np.arange(1, len(led) + 1),
            "entry_date": led["entry_date"].to_numpy(),
            "return_on_margin": rom,
            "cum_rom": equity,
            "drawdown": equity - peak,
            "label": label,
        }
    )


def main() -> None:
    scenarios = {
        "commission-only": CostModel(bid_ask_pct=0.0, slippage_ticks=0.0),
        "megacap ~2% RT": MEGACAP_COST,
        "default ~16% RT": CostModel(),
    }

    # The clean OOS window (<=2023) and the full Databento-marked set (2019-2024).
    # 2024 was held out of the OOS subset as Alpaca in-sample overlap, but this path
    # marks every leg off Databento, not Alpaca, so the 2024 rows are clean extra
    # sample here, not look-ahead - reported as a separate, larger-n cross-check.
    eo, fair_o = _prepare(EVENTS_OOS)
    ef, fair_f = _prepare(EVENTS_FULL)

    print(f"Market-marked OOS book (<=2023): {len(eo)} causal-window events (naked straddle)\n")
    arms = _arm_table(eo, _gate_masks(eo, fair_o), scenarios)

    # Headline arm: term+move (skew removed - it cuts trades and lowers Sharpe here).
    head_o = _gate_masks(eo, fair_o)["term+move"]
    head_f = _gate_masks(ef, fair_f)["term+move"]
    by_oos = _robustness(eo, head_o, "term+move (OOS <=2023)")
    by_full = _robustness(ef, head_f, "term+move (full 2019-2024)")
    breakeven = _breakeven(ef, head_f, "term+move (full 2019-2024)")
    plateau = _plateau(ef, fair_f)
    equity = _equity(ef, head_f, "term+move (full 2019-2024)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    arms.to_csv(OUT_DIR / "market_marked_arms.csv", index=False)
    pd.concat([by_oos, by_full], ignore_index=True).to_csv(
        OUT_DIR / "market_marked_by_year.csv", index=False
    )
    breakeven.to_csv(OUT_DIR / "breakeven_cost.csv", index=False)
    plateau.to_csv(OUT_DIR / "gate_plateau.csv", index=False)
    equity.to_csv(OUT_DIR / "gated_equity.csv", index=False)
    print(f"wrote 5 result CSVs to {OUT_DIR}/")


if __name__ == "__main__":
    main()
