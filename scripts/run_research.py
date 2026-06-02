"""
run_research.py
Enriched end-to-end research run: filtered strategy vs Agent 0, net of costs.

Runs the full chain: fit the fair-move model, select through both filters, book
the ledger gross (commission-only) and net (full cost stack), score with the
expanded metric set, run the significance comparison (Sharpe spread, paired
t-test, bootstrap CI, Deflated Sharpe), report the regime structure mix and the
Greek P&L attribution, and write a tearsheet.

The default run uses a synthetic, planted-edge event set and validates the
machinery against a known answer. ``--real`` swaps in the live pipeline: Yahoo
earnings dates, Alpaca historical chains with locally inverted IV, and (with
``--term-gate panel``) the per-name daily term-spread panel. Real mode needs
``ALPACA_KEY``/``ALPACA_SECRET`` and shows a live progress bar with an ETA.

Usage
-----
From the project root::

    python scripts/run_research.py                       # synthetic, planted edge
    python scripts/run_research.py --real --term-gate panel \\
        --cache outputs/research/events.parquet \\
        --term-panel-cache outputs/research/panel.parquet

Outputs
-------
A tearsheet and metrics CSV under ``outputs/research/``. Real-mode event and
panel caches make subsequent runs instant. Runtime: seconds (synthetic) /
minutes (real, network-bound).
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd

# Keep the live progress bar clean: silence third-party deprecation chatter
# (notably yfinance's pandas warnings) that would otherwise interleave with it.
warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.baseline.agent0 import run_agent0                  # noqa: E402
from src.data.earnings import fetch_earnings_dates          # noqa: E402
from src.data.real_events import build_execution_events     # noqa: E402
from src.data.term_panel import build_term_panel            # noqa: E402
from src.engine.backtester import backtest, compare         # noqa: E402
from src.engine.costs import CostModel                      # noqa: E402
from src.engine.reporting import (                          # noqa: E402
    aggregate_pnl_attribution, build_tearsheet,
)
from src.engine.simulate import simulate_events             # noqa: E402
from src.strategy.fair_move_model import FairMoveModel      # noqa: E402
from src.strategy.filters import (                          # noqa: E402
    IMPLIED_FAIR_RATIO, TRAILING_WINDOW,
    passes_move_filter, passes_term_filter, passes_term_filter_panel,
    select_events,
)
from src.strategy.regime import assign_structures           # noqa: E402
from src.strategy.strategy import run_strategy              # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs" / "research"

# Liquid large-caps with dense Alpaca option history since 2024 - the default
# --real universe. Override with --tickers.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD", "NFLX",
    "JPM", "BAC", "XOM", "WMT", "DIS", "INTC", "CRM", "QCOM", "MU",
]
# Alpaca free option history starts ~Feb 2024; default to a settled window.
DEFAULT_START = "2024-02-01"
DEFAULT_END = "2024-12-31"
N_FILTER_TRIALS = 20      # filter-threshold grid points effectively tried
# Per-period (daily) Sharpe dispersion across those trials. A daily Sharpe of
# ~0.06 corresponds to an annual Sharpe of ~1, so trial dispersion is small in
# per-period units; 0.02 is a realistic spread for a modest threshold grid.
SR_TRIALS_STD = 0.02


def _show(name: str, stats: dict, keys) -> None:
    print(f"\n{name}")
    print("-" * len(name))
    for k in keys:
        v = stats.get(k)
        if isinstance(v, float):
            print(f"  {k:24s} {v:,.4f}")
        else:
            print(f"  {k:24s} {v}")


def _save_frame(df: "pd.DataFrame", path: Path) -> Path:
    """Persist a frame to `path`, falling back to a .csv sibling when no parquet
    engine is installed (pyarrow/fastparquet may be absent)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path)
        return path
    except (ImportError, ValueError):
        csv = path.with_suffix(".csv")
        df.to_csv(csv, index=False)
        return csv


def _load_frame(path: Path):
    """Load a cached frame from `path` (parquet) or its .csv sibling, else None.

    Date columns are left as-is; downstream code coerces them with pd.to_datetime.
    """
    if path.exists():
        try:
            return pd.read_parquet(path)
        except (ImportError, ValueError):
            pass
    csv = path.with_suffix(".csv")
    if csv.exists():
        return pd.read_csv(csv)
    return None


def _load_real_events(args) -> "pd.DataFrame":
    """Pull the historical calendar (Yahoo) and assemble real events.

    Finnhub free only serves current/future dates, so historical earnings dates
    come from Yahoo per ticker (the planned fallback leg). When ``--cache PATH``
    is given and the file exists, events are loaded from it (skipping the slow
    network assembly); otherwise they are assembled and saved there.
    """
    cache = Path(args.cache) if args.cache else None
    if cache:
        cached = _load_frame(cache)
        if cached is not None:
            print(f"Loaded {len(cached)} cached real events from {cache}")
            return cached

    cal = fetch_earnings_dates(args.tickers, args.start, args.end)
    if cal is None or cal.empty:
        raise SystemExit(f"No historical earnings dates for {sorted(set(args.tickers))} "
                         f"in [{args.start}, {args.end}].")
    print(f"Earnings events in window: {len(cal)}  (assembling entry+exit chains)…")
    events = build_execution_events(cal, holding_days=args.holding_days, progress=True)
    # Keep only rows with the columns the model + filters need populated.
    needed = ["realised_move", "implied_move", "iv_term_spread", "trailing_rv",
              "skew_25d", "iv_entry", "iv_exit", "spot_exit"]
    events = events.dropna(subset=needed)
    if len(events) < 10:
        raise SystemExit(f"Only {len(events)} usable real events — too few to fit. "
                         "Widen the window or universe.")
    if cache:
        written = _save_frame(events, cache)
        print(f"Cached {len(events)} real events to {written}")
    return events


def _load_term_panel(args, events):
    """Build (or load) the per-name daily term-spread panel for the events."""
    cache = Path(args.term_panel_cache) if args.term_panel_cache else None
    if cache:
        cached = _load_frame(cache)
        if cached is not None:
            print(f"Loaded term-spread panel ({len(cached)} daily rows) from {cache}")
            return cached
    print(f"Building per-name daily term-spread panel for {events['ticker'].nunique()} "
          f"names x trailing {TRAILING_WINDOW} days (network-bound)…")
    panel = build_term_panel(events, window_days=TRAILING_WINDOW, progress=True)
    print(f"Term-spread panel: {len(panel)} daily rows.")
    if cache and not panel.empty:
        written = _save_frame(panel, cache)
        print(f"Cached term-spread panel to {written}")
    return panel


def _filter_funnel(events, model, term_panel=None) -> None:
    """Print how many events clear each gate - diagnoses an empty selection."""
    fair = pd.Series(list(model.predict(events)), index=events.index)
    move_ok = passes_move_filter(events["implied_move"], fair).fillna(False)
    if term_panel is not None:
        term_ok = passes_term_filter_panel(events, term_panel).fillna(False)
        gate_desc = "per-name trailing 30-day"
    else:
        term_ok = passes_term_filter(events).fillna(False)
        gate_desc = "legacy 30-event rolling"
    both = (move_ok & term_ok).fillna(False)
    print(f"\nFilter funnel (term gate: {gate_desc}):")
    print(f"  events                              {len(events)}")
    print(f"  pass move gate (>= {IMPLIED_FAIR_RATIO}x fair move)   {int(move_ok.sum())}")
    print(f"  pass term gate (> trailing 75th pct) {int(term_ok.sum())}")
    print(f"  pass BOTH (traded)                  {int(both.sum())}")
    if term_panel is None and int(term_ok.sum()) == 0 and len(events) <= TRAILING_WINDOW:
        print(f"  NOTE: the legacy term gate is a rolling {TRAILING_WINDOW}-event percentile, so "
              f"it rejects all until > {TRAILING_WINDOW} events exist; this sample has "
              f"{len(events)}. Use --term-gate panel, or widen --start/--end/--tickers.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Earnings IV-Crush research run.")
    ap.add_argument("--real", action="store_true",
                    help="Use real Alpaca surfaces instead of synthetic events.")
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--tickers", nargs="+", default=DEFAULT_UNIVERSE)
    ap.add_argument("--holding-days", type=int, default=2)
    ap.add_argument("--cache", default=None,
                    help="Parquet path to load/save assembled real events "
                         "(skips network re-assembly on reload).")
    ap.add_argument("--term-gate", choices=["events", "panel"], default="events",
                    help="Term filter: 'panel' = spec-faithful per-name trailing "
                         "30-day percentile (real mode); 'events' = legacy rolling.")
    ap.add_argument("--term-panel-cache", default=None,
                    help="Parquet path to load/save the daily term-spread panel.")
    args = ap.parse_args()

    mode = "REAL (Alpaca surfaces)" if args.real else "synthetic, planted edge"
    print("=" * 70)
    print(f"Earnings IV-Crush — enriched research run ({mode})")
    print("=" * 70)

    if args.real:
        events = _load_real_events(args)
        print(f"Usable real events: {len(events)}  |  output: {OUTPUT_DIR}")
    else:
        events = simulate_events(n=600, seed=11, edge_frac=0.35,
                                 with_vix=True, with_sectors=True)
        rich = int(events["is_rich"].sum())
        print(f"Events: {len(events)}  |  rich (planted): {rich}  |  output: {OUTPUT_DIR}")

    model = FairMoveModel().fit(events, events["realised_move"])
    costs = CostModel()

    term_panel = None
    if args.real and args.term_gate == "panel":
        term_panel = _load_term_panel(args, events)

    if args.real:
        _filter_funnel(events, model, term_panel=term_panel)

    # Gross (commission-only) vs net (full cost stack) — the thesis is net.
    gross = backtest(run_strategy(events, model, term_panel=term_panel))
    net_strat_ledger = run_strategy(events, model, costs=costs, term_panel=term_panel)
    net_agent0_ledger = run_agent0(events, seed=11, costs=costs)
    net_strat = backtest(net_strat_ledger)
    net_agent0 = backtest(net_agent0_ledger)

    metric_keys = ("n_trades", "total_return", "hit_rate", "sharpe", "sortino",
                   "profit_factor", "win_loss_ratio", "max_drawdown",
                   "max_dd_duration", "avg_return_on_margin")
    _show("Filtered strategy — GROSS (commission only)", gross, metric_keys)
    _show("Filtered strategy — NET (full cost stack)", net_strat, metric_keys)
    _show("Agent 0 control — NET", net_agent0, metric_keys)

    cost_drag = gross["total_return"] - net_strat["total_return"]
    print(f"\nCost drag (gross - net total return): {cost_drag:+.4%}")

    # Significance of the filter, net of costs.
    cmp = compare(net_strat_ledger, net_agent0_ledger,
                  n_trials=N_FILTER_TRIALS, sr_trials_std=SR_TRIALS_STD, seed=1)
    _show("Filter significance (net of costs)", cmp,
          ("sharpe_strategy", "sharpe_agent0", "sharpe_delta",
           "sharpe_delta_ci_low", "sharpe_delta_ci_high",
           "spread_tstat", "spread_pvalue", "psr_strategy", "dsr_strategy"))

    # Regime structure mix over the selected events.
    selected = select_events(events, model.predict(events), term_panel=term_panel)
    structure_counts = (
        assign_structures(selected, model.predict(selected)).value_counts().to_dict()
    )
    print("\nStructure mix (selected events):")
    for label, count in structure_counts.items():
        print(f"  {label:10s} {count}")

    # Greek P&L attribution.
    attrib = aggregate_pnl_attribution(net_strat_ledger)
    print("\nP&L attribution (USD, net book):")
    for k, v in attrib.items():
        print(f"  {k:12s} {v:,.0f}")

    png = build_tearsheet(net_strat_ledger, net_agent0_ledger, cmp,
                          account=net_strat["final_equity"] - net_strat["total_pnl"],
                          outdir=OUTPUT_DIR, structure_counts=structure_counts)

    label = "REAL data" if args.real else "synthetic"
    print("\n" + "=" * 70)
    if net_strat["n_trades"] == 0:
        # A strategy that never trades is not "beating" the control - the positive
        # Sharpe delta is just non-participation. Say so plainly.
        print(f"Verdict ({label}): the filter selected 0 events, so there is NO "
              f"strategy book to evaluate. The +{cmp['sharpe_delta']:.2f} Sharpe "
              f"'delta' is non-participation, not edge. See the filter funnel above.")
    else:
        gate = "PASS" if cmp["filter_gate_pass"] else "below gate"
        print(f"Verdict ({label}): filter beats control by "
              f"{cmp['sharpe_delta']:+.2f} Sharpe net of costs — {gate} "
              f"(>= +0.50 gate) over {net_strat['n_trades']} trades.")
    print(f"Tearsheet: {png}")


if __name__ == "__main__":
    main()
