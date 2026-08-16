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
A tearsheet and metrics CSV under ``outputs/research/real/`` or
``outputs/research/synthetic/`` (per mode, so one never clobbers the other).
Real-mode event and panel caches make subsequent runs instant. Runtime:
seconds (synthetic) / minutes (real, network-bound).
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

# Keep the live progress bar clean: silence third-party deprecation chatter
# (notably yfinance's pandas warnings) that would otherwise interleave with it.
warnings.filterwarnings("ignore")

from earnings_iv_crush.baseline.agent0 import run_agent0  # noqa: E402
from earnings_iv_crush.config import GLOBAL, STRATEGY  # noqa: E402
from earnings_iv_crush.data import providers  # noqa: E402
from earnings_iv_crush.data.chain_cache import cached_chain_fetcher  # noqa: E402
from earnings_iv_crush.data.quality import exclusion_table  # noqa: E402
from earnings_iv_crush.data.real_events import build_execution_events  # noqa: E402
from earnings_iv_crush.data.term_panel import build_term_panel  # noqa: E402
from earnings_iv_crush.data.universe import cohort_labels  # noqa: E402
from earnings_iv_crush.engine.backtester import backtest, compare  # noqa: E402
from earnings_iv_crush.engine.cohorts import cohort_table, compare_cohorts  # noqa: E402
from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.reporting import (  # noqa: E402
    aggregate_pnl_attribution,
    build_tearsheet,
)
from earnings_iv_crush.engine.simulate import simulate_events  # noqa: E402
from earnings_iv_crush.strategy.fair_move_model import FairMoveModel  # noqa: E402
from earnings_iv_crush.strategy.filters import (  # noqa: E402
    IMPLIED_FAIR_RATIO,
    TERM_SPREAD_PCTL,
    TRAILING_WINDOW,
    passes_move_filter,
    passes_term_filter,
    passes_term_filter_panel,
    select_events,
)
from earnings_iv_crush.strategy.regime import assign_structures  # noqa: E402
from earnings_iv_crush.strategy.strategy import run_strategy  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs" / "research"

# Per-market universes and coverage start now live in data/providers.py; the
# default window end stays the config value.
DEFAULT_END = GLOBAL.end_date
N_FILTER_TRIALS = 20  # filter-threshold grid points effectively tried
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


def _save_frame(df: pd.DataFrame, path: Path) -> Path:
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


def _provenance_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".provenance.json")


def _write_provenance(path: Path, stamp: dict) -> None:
    """Record the config that produced a cache file next to it."""
    import json

    _provenance_path(path).write_text(json.dumps(stamp, indent=2, default=str))


def _check_provenance(path: Path, stamp: dict, allow_stale: bool) -> None:
    """Refuse a cache produced under a different config unless overridden.

    A cache file loaded purely on existence silently mixes stale events or
    panel rows into a run whose --start/--end/--universe/--min-exit-dte or
    chain source has changed. Every mismatch is printed; without
    ``--allow-stale-cache`` a mismatch is fatal.
    """
    import json

    prov = _provenance_path(path)
    if not prov.exists():
        print(
            f"WARNING: {path.name} has no provenance stamp (predates cache "
            "provenance); cannot verify it matches the current config. "
            "Rebuild the cache (delete the file) to clear this warning."
        )
        return
    recorded = json.loads(prov.read_text())
    mismatches = {
        k: (recorded.get(k), v) for k, v in stamp.items() if str(recorded.get(k)) != str(v)
    }
    if not mismatches:
        return
    for k, (old, new) in mismatches.items():
        print(f"CACHE MISMATCH {path.name}: {k} was {old!r}, run wants {new!r}")
    if not allow_stale:
        raise SystemExit(
            f"{path} was built under a different config (see mismatches above). "
            "Rebuild it (delete the file) or pass --allow-stale-cache to force."
        )
    print("--allow-stale-cache: proceeding with the mismatched cache anyway.")


def _cache_only_chain_fetcher(variant: str = "entry", source: str = "alpaca"):
    """A ``fetch_chain(ticker, asof)`` that reads the disk cache and never the API.

    Returns the cached snapshot when present, else an empty frame (so the event
    assembler skips that leg). Lets an early read run against a partially-warm
    cache while a parallel fetch is still downloading the cold snapshots.
    """
    from earnings_iv_crush.data import cache
    from earnings_iv_crush.data.chain_cache import chain_key
    from earnings_iv_crush.data.options import CHAIN_COLUMNS

    def fetch_chain(ticker: str, asof: str) -> pd.DataFrame:
        key = chain_key(ticker, asof, variant, source)
        if cache.has_frame(key):
            df = cache.read_frame(key)
            if not df.empty:
                df["expiry"] = pd.to_datetime(df["expiry"])
            return df
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    return fetch_chain


def _load_real_events(args) -> pd.DataFrame:
    """Pull the historical calendar (Yahoo) and assemble real events.

    Finnhub free only serves current/future dates, so historical earnings dates
    come from Yahoo per ticker (the planned fallback leg). When ``--cache PATH``
    is given and the file exists, events are loaded from it (skipping the slow
    network assembly); otherwise they are assembled and saved there.
    """
    stamp = {
        "kind": "events",
        "start": args.start,
        "end": args.end,
        "universe": args.universe,
        "tickers": None if args.universe else sorted(set(args.tickers)),
        "min_exit_dte": args.min_exit_dte,
        "market": args.market,
        "chain_source": args.mkt.chain_source,
        # Without these two a quote-marked events cache and a close-marked one are
        # indistinguishable to the staleness check, so the wrong book could be served
        # silently under an identical start/end/universe key.
        "option_source": GLOBAL.option_source,
        "mark_basis": GLOBAL.mark_basis,
    }
    cache = Path(args.cache) if args.cache else None
    if cache:
        cached = _load_frame(cache)
        if cached is not None:
            _check_provenance(cache, stamp, args.allow_stale_cache)
            print(f"Loaded {len(cached)} cached real events from {cache}")
            if "iv_term_spread_nearest" not in cached.columns:
                print(
                    "WARNING: events cache predates the nearest-expiry term statistic; "
                    "the panel gate will fall back to the executed-expiry spread, which "
                    "runs high against the panel distribution. Rebuild the events cache."
                )
            return cached

    if args.universe:
        # Pre-built calendar (scripts/build_calendar.py) with validated sessions,
        # fetched through the disk-cached Alpaca fetcher (scripts/fetch_chains.py
        # pre-warms it; cold snapshots are fetched and cached on the fly).
        cal_path = OUTPUT_DIR / f"events_master_{args.universe}.parquet"
        if not cal_path.exists():
            raise SystemExit(f"{cal_path} not found - run scripts/build_calendar.py first")
        cal = pd.read_parquet(cal_path)
        cal = cal[(cal["announce_date"] >= args.start) & (cal["announce_date"] <= args.end)]
        print(f"Earnings events in window: {len(cal)}  (assembling entry+exit chains)...")
        # --cache-only: read snapshots from disk only, never hitting the API, so
        # an early read can run against a partially-warm cache without cold
        # fetches (events with any uncached chain are skipped). Used while a
        # parallel scripts/fetch_chains.py warm is still in flight.
        mkt = args.mkt
        entry_fetch = (
            _cache_only_chain_fetcher("entry", source=mkt.chain_source)
            if args.cache_only
            else cached_chain_fetcher(
                "entry",
                source=mkt.chain_source,
                fetch=mkt.fetch_chain,
                refresh_empty=args.refresh_empty_chains,
            )
        )
        events = build_execution_events(
            cal,
            fetch_chain=entry_fetch,
            fetch_prices=mkt.fetch_prices,
            min_exit_dte_days=args.min_exit_dte,
            progress=True,
        )
        n_empty = getattr(entry_fetch, "empty_served", 0)
        if n_empty:
            print(
                f"NOTE: {n_empty} chain request(s) were served a cached EMPTY sentinel; "
                "if any were written during a provider outage they are silent data loss. "
                "Re-run once with --refresh-empty-chains to refetch them."
            )
        if args.cache_only and len(events):
            # A cold (uncached) exit chain makes the assembler fall back to
            # iv_exit = iv_entry (no crush). Drop those so the early read is not
            # diluted by events whose exit leg has not been fetched yet.
            degenerate = events["iv_exit"] == events["iv_entry"]
            if degenerate.any():
                print(
                    f"cache-only: dropping {int(degenerate.sum())} of {len(events)} events "
                    "with an uncached exit chain (iv_exit == iv_entry)."
                )
                events = events[~degenerate].reset_index(drop=True)
        # Exclusion accounting before the usability dropna: what fell and why.
        events["cohort"] = events["ticker"].map(cohort_labels())
        excl = exclusion_table(events)
        if not excl.empty:
            print("\nEvent exclusion table (pre-filter data quality):")
            print(excl.to_string(index=False))
    else:
        mkt = args.mkt
        cal = mkt.fetch_earnings(args.tickers, args.start, args.end)
        if cal is None or cal.empty:
            raise SystemExit(
                f"No historical earnings dates for {sorted(set(args.tickers))} "
                f"in [{args.start}, {args.end}]."
            )
        print(f"Earnings events in window: {len(cal)}  (assembling entry+exit chains)...")
        entry_fetch = cached_chain_fetcher("entry", source=mkt.chain_source, fetch=mkt.fetch_chain)
        events = build_execution_events(
            cal,
            fetch_chain=entry_fetch,
            fetch_prices=mkt.fetch_prices,
            min_exit_dte_days=args.min_exit_dte,
            progress=True,
        )
    # Keep only rows with the columns the model + filters need populated.
    needed = [
        "realised_move",
        "implied_move",
        "iv_term_spread",
        "trailing_rv",
        "skew_25d",
        "iv_entry",
        "iv_exit",
        "spot_exit",
    ]
    events = events.dropna(subset=needed)
    if len(events) < 10:
        raise SystemExit(
            f"Only {len(events)} usable real events - too few to fit. "
            "Widen the window or universe."
        )
    if cache:
        written = _save_frame(events, cache)
        _write_provenance(written, stamp)
        print(f"Cached {len(events)} real events to {written}")
    return events


def _load_term_panel(args, events):
    """Build (or load) the per-name daily term-spread panel for the events."""
    stamp = {
        "kind": "term_panel",
        "start": args.start,
        "end": args.end,
        "universe": args.universe,
        "window_days": TRAILING_WINDOW,
        "market": args.market,
        "chain_source": args.mkt.chain_source,
    }
    cache = Path(args.term_panel_cache) if args.term_panel_cache else None
    if cache:
        cached = _load_frame(cache)
        if cached is not None:
            _check_provenance(cache, stamp, args.allow_stale_cache)
            print(f"Loaded term-spread panel ({len(cached)} daily rows) from {cache}")
            return cached
    print(
        f"Building per-name daily term-spread panel for {events['ticker'].nunique()} "
        f"names x trailing {TRAILING_WINDOW} days (network-bound)..."
    )
    mkt = args.mkt
    fetch_chain = cached_chain_fetcher(
        "panel",
        source=mkt.chain_source,
        fetch=mkt.fetch_chain,
        refresh_empty=args.refresh_empty_chains,
    )
    panel = build_term_panel(
        events,
        fetch_chain=fetch_chain,
        fetch_prices=mkt.fetch_prices,
        window_days=TRAILING_WINDOW,
        progress=True,
    )
    print(f"Term-spread panel: {len(panel)} daily rows.")
    if cache and not panel.empty:
        written = _save_frame(panel, cache)
        _write_provenance(written, stamp)
        print(f"Cached term-spread panel to {written}")
    return panel


def _filter_funnel(events, model, term_panel=None) -> None:
    """Print how many events clear each gate - diagnoses an empty selection."""
    fair = pd.Series(list(model.predict(events)), index=events.index)
    move_ok = passes_move_filter(events["implied_move"], fair).fillna(False)
    gate_stats: dict = {}
    if term_panel is not None:
        term_ok = passes_term_filter_panel(events, term_panel, stats_out=gate_stats).fillna(False)
        gate_desc = "per-name trailing 30-day"
    else:
        term_ok = passes_term_filter(events).fillna(False)
        gate_desc = "legacy 30-event rolling"
    both = (move_ok & term_ok).fillna(False)
    print(f"\nFilter funnel (term gate: {gate_desc}):")
    print(f"  events                              {len(events)}")
    print(f"  pass move gate (>= {IMPLIED_FAIR_RATIO}x fair move)   {int(move_ok.sum())}")
    print(f"  pass term gate (> trailing {TERM_SPREAD_PCTL:.0%} pctl) {int(term_ok.sum())}")
    if gate_stats:
        print(
            f"    term-gate attrition: no panel history {gate_stats['no_panel_history']}, "
            f"window < {STRATEGY.term_min_periods} obs {gate_stats['below_min_periods']}, "
            f"no event statistic {gate_stats['no_event_stat']}, "
            f"below threshold {gate_stats['below_threshold']}"
        )
    print(f"  pass BOTH (traded)                  {int(both.sum())}")
    if term_panel is None and int(term_ok.sum()) == 0 and len(events) <= TRAILING_WINDOW:
        print(
            f"  NOTE: the legacy term gate is a rolling {TRAILING_WINDOW}-event percentile, so "
            f"it rejects all until > {TRAILING_WINDOW} events exist; this sample has "
            f"{len(events)}. Use --term-gate panel, or widen --start/--end/--tickers."
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Earnings IV-Crush research run.")
    ap.add_argument(
        "--real", action="store_true", help="Use real Alpaca surfaces instead of synthetic events."
    )
    ap.add_argument(
        "--market",
        choices=["us", "india", "brazil"],
        default=GLOBAL.market,
        help="Market bundle (calendar/spot/chain). 'india' routes to the free "
        "NSE UDiFF F&O bhavcopy, 'brazil' to the free B3 COTAHIST file; see "
        "data/providers.py.",
    )
    ap.add_argument(
        "--chain-source",
        choices=["alpaca", "dolthub", "nse", "b3"],
        default=GLOBAL.chain_source,
        help="Override the market's default chain provider. None keeps the "
        "market default (us -> dolthub, india -> nse, brazil -> b3).",
    )
    ap.add_argument(
        "--start",
        default=None,
        help="Start date (YYYY-MM-DD); defaults to the market's coverage start.",
    )
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="Ticker set; defaults to the market's universe.",
    )
    ap.add_argument(
        "--universe",
        choices=["megacap", "broad"],
        default=None,
        help="Use a pre-built universe calendar (scripts/build_calendar.py) and the "
        "disk-cached Alpaca fetcher; enables the cohort comparison on 'broad'.",
    )
    ap.add_argument(
        "--min-exit-dte",
        type=int,
        default=STRATEGY.min_exit_dte_days,
        help="Min trading days of option life left at exit; the executed expiry "
        "is rolled out until it qualifies so the crush is marked, not intrinsic.",
    )
    ap.add_argument(
        "--holding-days",
        type=int,
        default=None,
        help="Deprecated and ignored: exit timing is now session-aware "
        "(one overnight across the crush). Use --min-exit-dte instead.",
    )
    ap.add_argument(
        "--cache",
        default=None,
        help="Parquet path to load/save assembled real events "
        "(skips network re-assembly on reload).",
    )
    ap.add_argument(
        "--term-gate",
        choices=["events", "panel"],
        default="panel",
        help="Term filter: 'panel' = per-name trailing 30-day percentile "
        "(default; the point-in-time gate used for every reported figure); "
        "'events' = legacy rolling form, kept for the synthetic path only - "
        "its rolling window includes the current row, so it is in-sample "
        "contaminated on real data.",
    )
    ap.add_argument(
        "--refresh-empty-chains",
        action="store_true",
        help="Refetch chain snapshots whose cache entry is an empty sentinel "
        "(heals entries written during a transient provider outage).",
    )
    ap.add_argument(
        "--allow-stale-cache",
        action="store_true",
        help="Proceed even when a cached events/panel file was built under a "
        "different config (default: refuse, listing every mismatch).",
    )
    ap.add_argument(
        "--term-panel-cache",
        default=None,
        help="Parquet path to load/save the daily term-spread panel.",
    )
    ap.add_argument(
        "--cache-only",
        action="store_true",
        help="Read chain snapshots from disk only (no API); events with any "
        "uncached chain are skipped. For an early read against a partial cache.",
    )
    args = ap.parse_args()
    # Resolve the market bundle and fill market-defaulted args (start/universe).
    args.mkt = providers.resolve(args.market, args.chain_source)
    if args.start is None:
        args.start = args.mkt.default_start
    if args.tickers is None:
        args.tickers = (
            providers.india_full_universe() if args.market == "india" else args.mkt.universe
        )
    if args.holding_days is not None:
        print(
            "NOTE: --holding-days is deprecated and ignored; exit timing is now "
            "session-aware (one overnight across the crush). See --min-exit-dte."
        )

    mode = "REAL (Alpaca surfaces)" if args.real else "synthetic, planted edge"
    print("=" * 70)
    print(f"Earnings IV-Crush - enriched research run ({mode})")
    print("=" * 70)

    if args.real:
        events = _load_real_events(args)
        print(f"Usable real events: {len(events)}  |  output: {OUTPUT_DIR}")
    else:
        events = simulate_events(n=600, seed=11, edge_frac=0.35, with_vix=True, with_sectors=True)
        rich = int(events["is_rich"].sum())
        print(f"Events: {len(events)}  |  rich (planted): {rich}  |  output: {OUTPUT_DIR}")

    model = FairMoveModel().fit(events, events["realised_move"])
    costs = CostModel()

    term_panel = None
    if args.real and args.term_gate == "panel":
        term_panel = _load_term_panel(args, events)

    if args.real:
        _filter_funnel(events, model, term_panel=term_panel)

    # Gross (commission-only) vs net (full cost stack) - the thesis is net.
    gross = backtest(run_strategy(events, model, term_panel=term_panel))
    net_strat_ledger = run_strategy(events, model, costs=costs, term_panel=term_panel)
    net_agent0_ledger = run_agent0(events, seed=11, costs=costs)
    net_strat = backtest(net_strat_ledger)
    net_agent0 = backtest(net_agent0_ledger)

    metric_keys = (
        "n_trades",
        "total_return",
        "hit_rate",
        "per_trade_sharpe",
        "sharpe",
        "periods_per_year",
        "sortino",
        "profit_factor",
        "win_loss_ratio",
        "max_drawdown",
        "max_dd_duration",
        "avg_return_on_margin",
    )
    _show("Filtered strategy - GROSS (commission only)", gross, metric_keys)
    _show("Filtered strategy - NET (full cost stack)", net_strat, metric_keys)
    _show("Agent 0 control - NET", net_agent0, metric_keys)

    cost_drag = gross["total_return"] - net_strat["total_return"]
    print(f"\nCost drag (gross - net total return): {cost_drag:+.4%}")

    # Significance of the filter, net of costs.
    cmp = compare(
        net_strat_ledger,
        net_agent0_ledger,
        n_trials=N_FILTER_TRIALS,
        sr_trials_std=SR_TRIALS_STD,
        seed=1,
    )
    _show(
        "Filter significance - daily-Sharpe, annualised at the book's own cadence "
        "(zero-fills flat days; frequency-confounded)",
        cmp,
        (
            "sharpe_strategy",
            "sharpe_agent0",
            "sharpe_delta",
            "periods_per_year",
            "sharpe_delta_ci_low",
            "sharpe_delta_ci_high",
            "spread_tstat",
            "spread_pvalue",
            "psr_strategy",
            "dsr_strategy",
        ),
    )
    # The daily Sharpe above charges the selective filter a zero-return day on
    # every date the control traded but it did not, penalising selectivity rather
    # than per-trade edge. These statistics score the two books frequency-neutral.
    _show(
        "Filter edge - frequency-neutral (per-trade + size-matched control)",
        cmp,
        (
            "mean_rom_strategy",
            "mean_rom_agent0",
            "per_trade_sharpe_strategy",
            "per_trade_sharpe_agent0",
            "per_trade_sharpe_delta",
            "size_matched_delta_mean",
            "size_matched_delta_ci_low",
            "size_matched_delta_ci_high",
            "size_matched_win_prob",
        ),
    )

    # Regime structure mix over the selected events.
    selected = select_events(events, model.predict(events), term_panel=term_panel)
    structure_counts = assign_structures(selected, model.predict(selected)).value_counts().to_dict()
    print("\nStructure mix (selected events):")
    for label, count in structure_counts.items():
        print(f"  {label:10s} {count}")

    # Cohort cut: does the edge survive outside the most liquid names?
    if args.real and args.universe == "broad" and len(net_strat_ledger):
        ledger_c = net_strat_ledger.copy()
        ledger_c["cohort"] = ledger_c["ticker"].map(cohort_labels())
        table = cohort_table(ledger_c)
        if not table.empty:
            print("\nPer-cohort performance (net strategy book):")
            print(table.to_string(index=False))
            cc = compare_cohorts(ledger_c)
            print(
                f"\nMegacap minus broad-only mean P&L per trade: {cc['mean_diff']:,.0f} "
                f"(95% CI [{cc['diff_ci_low']:,.0f}, {cc['diff_ci_high']:,.0f}]; "
                f"{'significant' if cc['significant'] else 'not significant'})"
            )

    # Greek P&L attribution.
    attrib = aggregate_pnl_attribution(net_strat_ledger)
    print("\nP&L attribution (USD, net book):")
    for k, v in attrib.items():
        print(f"  {k:12s} {v:,.0f}")

    # Synthetic and real runs write to separate directories so a synthetic
    # smoke run can never silently overwrite the real tearsheet/metrics.
    tearsheet_dir = OUTPUT_DIR / ("real" if args.real else "synthetic")
    png = build_tearsheet(
        net_strat_ledger,
        net_agent0_ledger,
        cmp,
        account=net_strat["final_equity"] - net_strat["total_pnl"],
        outdir=tearsheet_dir,
        structure_counts=structure_counts,
    )

    label = "REAL data" if args.real else "synthetic"
    print("\n" + "=" * 70)
    if net_strat["n_trades"] == 0:
        # A strategy that never trades is not "beating" the control - the positive
        # Sharpe delta is just non-participation. Say so plainly.
        print(
            f"Verdict ({label}): the filter selected 0 events, so there is NO "
            f"strategy book to evaluate. The +{cmp['sharpe_delta']:.2f} Sharpe "
            f"'delta' is non-participation, not edge. See the filter funnel above."
        )
    else:
        # Two reads, because they disagree by construction. The daily Sharpe gate
        # zero-fills the selective filter on dates only the control traded, so it
        # penalises selectivity; the per-trade and size-matched reads do not.
        edge = "above" if cmp["per_trade_sharpe_delta"] > 0 else "at/below"
        print(
            f"Verdict ({label}) over {net_strat['n_trades']} trades:\n"
            f"  Daily-Sharpe gate (frequency-confounded): {cmp['sharpe_delta']:+.2f} "
            f"- {'PASS' if cmp['filter_gate_pass'] else 'below +0.50 gate'}. This charges the "
            f"filter a flat-day return on every date only the control traded.\n"
            f"  Frequency-neutral: per-trade Sharpe {edge} control "
            f"({cmp['per_trade_sharpe_strategy']:.2f} vs {cmp['per_trade_sharpe_agent0']:.2f}); "
            f"size-matched control wins {cmp['size_matched_win_prob']:.0%} of draws "
            f"(95% CI [{cmp['size_matched_delta_ci_low']:+.2f}, "
            f"{cmp['size_matched_delta_ci_high']:+.2f}], straddles 0 - not conclusive at this N)."
        )
    print(f"Tearsheet: {png}")


if __name__ == "__main__":
    main()
