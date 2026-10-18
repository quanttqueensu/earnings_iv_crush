"""
research_fills_study.py
Where inside the quoted spread do these options actually trade?

The book's verdict is that the volatility crush is real and is not monetisable. The one
mechanism that could still explain the gap is execution: the book is charged a half-cross
from mid to the touch on both sides, and if real trades print better than the touch then
the cost model overstates what the strategy would actually pay.

This measures that directly rather than assuming it. ``cmbp-1`` carries trade prints
alongside the prevailing consolidated bid and ask, so for every trade in the contracts the
book holds we can locate the print inside the spread:

    fill location  = (price - bid) / (ask - bid)      0 = bid, 0.5 = mid, 1 = ask
    effective half = |price - mid| / mid
    quoted half    = (ask - bid) / 2 / mid
    improvement    = 1 - effective / quoted           0 = pays the touch, 1 = trades at mid

The improvement ratio is the deliverable. It is a microstructure measurement, not an edge
test, which is why a sample of 81 events is adequate here and would not be adequate for a
Sharpe: each event contributes many prints, and the quantity being estimated is a property
of the market rather than of the strategy.

Two limits are structural and are printed with every result:

* ``cmbp-1`` begins 2023-03-28. This reaches only the last two years of the book, which are
  also its two weakest. The 2013-2018 block that failed to replicate cannot be studied this
  way at all.
* Applying a 2023-2024 improvement ratio to earlier years is a cross-regime transfer, not an
  extension of the measurement. Option spreads tightened materially over the decade, so the
  backward transfer is optimistic by construction and is reported as a bound rather than an
  estimate.

Run: ``python research/execution/research_fills_study.py --dry-run``   (free, prices the pull)
     ``python research/execution/research_fills_study.py --pull --cap 40``
     ``python research/execution/research_fills_study.py --score``
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.research.gates import expanding_high_term_mask  # noqa: E402

SCHEMA = "cmbp-1"
CMBP_START = pd.Timestamp("2023-03-28")  # earliest cmbp-1 on OPRA.PILLAR
CACHE = Path("data/cache/fills_et")
PRINTS = Path("outputs/research/fill_prints.parquet")
SUMMARY = Path("outputs/research/fills_study.csv")
LEDGER = Path("outputs/research/fills_study_spend.csv")
Q = 0.80

# The window either side of the marking snapshot. The book marks at 15:59 ET, but a print
# exactly at 15:59 is rare on a single-name option, so the measurement takes the closing
# stretch and reports how far each print sits from the mark rather than demanding one.
#
# WINDOW is exchange-local and must be converted before it reaches the vendor. Databento
# reads a timezone-naive timestamp as UTC, so passing "15:30" straight through pulls
# 11:30 ET in summer and 10:30 ET in winter. The first run of this study did exactly that
# and measured a late-morning book while reporting it as the 15:59 mark; the superseded
# cache is retained under data/cache/fills. Everything downstream of the request goes
# through _request_range, and _prints asserts the returned records land where intended.
_EXCHANGE_TZ = "America/New_York"
WINDOW = ("15:30", "16:00")

# Per-pull cost assumed before any pull has completed, used only by the pre-submit margin
# that stops the worker pool overshooting the cap. It matters that this is roughly right
# for THIS schema: a two-symbol cmbp-1 half-hour prices at $0.0002, whereas the inherited
# prior of $0.41 was calibrated on full-chain cbbo-1m pulls and reserved more headroom than
# a sane cap for this study contains, halting the pool before it submitted anything. Set
# 50x above the measured figure so the margin stays conservative without being absurd.
_PRIOR_PER_PULL = 0.01


def _request_range(day: pd.Timestamp) -> tuple[str, str]:
    """The exchange-local WINDOW on ``day`` as explicit UTC instants for the vendor.

    Built by localising to ``_EXCHANGE_TZ`` and converting, never by string
    concatenation, so the offset follows daylight saving instead of being assumed:
    15:30 ET is 19:30 UTC in summer and 20:30 UTC in winter.

    Parameters
    ----------
    day : pd.Timestamp
        Session date. Any time component is discarded.

    Returns
    -------
    tuple[str, str]
        ``(start, end)`` ISO-8601 UTC strings with an explicit ``Z``.
    """
    session = pd.Timestamp(day).normalize()
    if session.tzinfo is not None:
        session = session.tz_convert(_EXCHANGE_TZ).normalize().tz_localize(None)
    out = []
    for clock in WINDOW:
        h, m = (int(x) for x in clock.split(":"))
        local = (session + pd.Timedelta(hours=h, minutes=m)).tz_localize(_EXCHANGE_TZ)
        out.append(local.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    return out[0], out[1]


# ── event selection ───────────────────────────────────────────────────────────


def _gated() -> pd.DataFrame:
    """The gated book, restricted to events cmbp-1 can actually reach."""
    ev, _ = mv._prepare(mv.EVENTS_FULL, chain_path=dq.cache_path)
    mask = np.asarray(expanding_high_term_mask(ev, Q), dtype=bool)
    g = ev[mask].reset_index(drop=True).copy()
    g["entry_date"] = pd.to_datetime(g["entry_date"])
    g["exit_date"] = pd.to_datetime(g["exit_date"])
    out = g[g["entry_date"] >= CMBP_START].reset_index(drop=True)
    print(f"gated events {len(g)}, reachable by {SCHEMA} (>= {CMBP_START:%Y-%m-%d}) {len(out)}")
    if out.empty:
        raise SystemExit("no events in range; nothing to price or pull")
    return out


def _straddle_symbols(row: pd.Series) -> list[str]:
    """The two OSI symbols the book actually holds for one event.

    Only the traded strike and expiry are pulled. Pulling the whole chain would price the
    study at several hundred dollars and measure fills in contracts the book never touches.
    """
    strike, expiry = row.get("strike_mkt"), row.get("expiry_mkt")
    if not (np.isfinite(pd.to_numeric(strike, errors="coerce")) and pd.notna(expiry)):
        return []
    root = dbo._opra_root(str(row["ticker"]), row["entry_date"])
    return [dq.osi_symbol(root, expiry, r, float(strike)) for r in ("C", "P")]


def _plan(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    skipped = 0
    for _, e in events.iterrows():
        syms = _straddle_symbols(e)
        if not syms:
            skipped += 1
            continue
        for leg, day in (("entry", e["entry_date"]), ("exit", e["exit_date"])):
            rows.append(
                {"ticker": e["ticker"], "leg": leg, "day": pd.Timestamp(day), "symbols": syms}
            )
    if skipped:
        print(f"  {skipped} event(s) skipped: no marked strike/expiry to address")
    plan = pd.DataFrame(rows)
    print(f"  {len(plan)} snapshot pulls ({len(plan)//2} events x entry+exit)")
    return plan


# ── pricing and pulling ───────────────────────────────────────────────────────


def _snap_path(ticker: str, leg: str, day: pd.Timestamp) -> Path:
    return CACHE / ticker / f"{day:%Y-%m-%d}_{leg}.parquet"


def _price(plan: pd.DataFrame, sample: int = 8) -> float:
    """Extrapolate the pull cost from real ``get_cost`` calls on a sample. Free.

    A full per-row sweep would be exact but makes as many metadata calls as there are
    pulls; the sample is stratified across distinct names so one unusually dense
    underlying cannot set the whole estimate, which is the error that put the earlier
    cbbo-1m projection out by a factor of 2.5.
    """
    take = plan.drop_duplicates("ticker").head(sample)
    costs = []
    for _, r in take.iterrows():
        day = r["day"]
        start, end = _request_range(day)
        try:
            c = dbo.get_cost(r["symbols"], start, end, schema=SCHEMA)
        except Exception as exc:  # noqa: BLE001 - a pricing failure must not read as free
            print(f"  price failed {r['ticker']} {day:%Y-%m-%d}: {exc!r}")
            continue
        costs.append(c)
        print(f"  {r['ticker']:6s} {day:%Y-%m-%d}  ${c:.4f}")
    if not costs:
        raise SystemExit("could not price any sample pull; refusing to guess")
    per = float(np.mean(costs))
    total = per * len(plan)
    print(
        f"\n  sampled {len(costs)} of {len(plan)} pulls\n"
        f"  mean ${per:.4f}/pull  x {len(plan)} = ESTIMATE ${total:.2f}\n"
        f"  spread across sample: min ${min(costs):.4f} max ${max(costs):.4f}"
    )
    return total


def _pull(plan: pd.DataFrame, cap: float, workers: int) -> None:
    cached = [_snap_path(r["ticker"], r["leg"], r["day"]).exists() for r in plan.to_dict("records")]
    n_cached = int(sum(cached))
    plan = plan[[not c for c in cached]].reset_index(drop=True)
    print(f"  {n_cached} already cached, {len(plan)} to pull")
    if plan.empty:
        print("  nothing to do")
        return

    spent, rows, errors = 0.0, [], []
    lock, halted = threading.Lock(), threading.Event()
    t0 = time.time()

    def one(rec: dict) -> dict:
        nonlocal spent
        if halted.is_set():
            return {}
        day = rec["day"]
        start, end = _request_range(day)
        try:
            df = dbo._get_df(SCHEMA, rec["symbols"], start, end, stype_in="raw_symbol")
            billed = dbo.get_cost(rec["symbols"], start, end, schema=SCHEMA)
        except Exception as exc:  # noqa: BLE001 - recorded so the funnel shows it
            with lock:
                errors.append({"ticker": rec["ticker"], "day": day, "error": repr(exc)[:200]})
            return {}
        p = _snap_path(rec["ticker"], rec["leg"], day)
        p.parent.mkdir(parents=True, exist_ok=True)
        # An empty frame is cached deliberately: it means this contract genuinely did not
        # print in the window, which is itself a finding, and re-pulling it would be paid.
        df.to_parquet(p)
        with lock:
            spent += billed
            if spent >= cap:
                halted.set()
        return {
            "ticker": rec["ticker"],
            "day": day,
            "leg": rec["leg"],
            "rows": len(df),
            "actual": billed,
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {}
        for rec in plan.to_dict("records"):
            if halted.is_set():
                break
            with lock:
                mean = (spent / max(len(rows), 1)) if rows else _PRIOR_PER_PULL
                if spent + workers * mean >= cap:
                    halted.set()
                    break
            futs[pool.submit(one, rec)] = rec
        for i, fut in enumerate(as_completed(futs), 1):
            out = fut.result()
            if out:
                rows.append(out)
            if i % 20 == 0:
                print(f"  {i:4d}/{len(futs)}  ${spent:6.2f}", flush=True)

    if rows:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(LEDGER, mode="a", header=not LEDGER.exists(), index=False)
    print(f"\npull complete in {(time.time()-t0)/60:.1f} min")
    print(f"  pulls: {len(rows)}   failed: {len(errors)}   ACTUAL ${spent:.4f}")
    if errors:
        for msg, k in pd.DataFrame(errors)["error"].value_counts().head(5).items():
            print(f"    {k:4d}  {msg}")
    if halted.is_set() and not rows:
        print(
            f"  HALTED before submitting anything: the pre-submit margin reserves "
            f"{workers} x ${_PRIOR_PER_PULL:.4f} against a ${cap:.2f} cap. Raise the cap "
            f"above that reservation, or lower _PRIOR_PER_PULL if it overstates this schema."
        )
    elif halted.is_set():
        print(f"  HALTED at the ${cap:.2f} cap; rerun to continue.")


# ── measurement ───────────────────────────────────────────────────────────────


def _assert_window(raw: pd.DataFrame) -> None:
    """Refuse to measure records that did not land in the intended exchange-local window.

    The whole point of the study is the spread prevailing at the mark, so a cache pulled
    against the wrong instant is not a degraded measurement but a different one. This
    raises rather than warns: the first run of this study silently reported a late-morning
    book as the 15:59 mark, and a warning in a long stdout stream would not have caught it.
    """
    ts = raw.index if raw.index.name in {"ts_recv", "ts_event"} else raw.get("ts_recv")
    if ts is None:
        raise SystemExit("cached records carry no ts_recv; cannot verify the pull window")
    idx = pd.DatetimeIndex(pd.Series(ts).to_numpy())
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    local = idx.tz_convert(_EXCHANGE_TZ)
    lo, hi = (pd.Timestamp(c).time() for c in WINDOW)
    outside = ((local.time < lo) | (local.time > hi)).sum()
    span = f"{local.time.min()}-{local.time.max()}"
    if outside:
        raise SystemExit(
            f"{outside:,} of {len(local):,} records fall outside {WINDOW[0]}-{WINDOW[1]} "
            f"{_EXCHANGE_TZ} (observed {span}). The pull window is wrong; do not measure "
            f"this cache. Rebuild it with _request_range and re-pull."
        )
    print(f"  window verified: all records within {span} {_EXCHANGE_TZ}")


def _prints() -> pd.DataFrame:
    """Every trade print in the cached windows, located inside its prevailing spread."""
    files = sorted(CACHE.rglob("*.parquet"))
    if not files:
        raise SystemExit(f"no cached pulls under {CACHE}; run --pull first")
    frames = []
    empty = 0
    for f in files:
        df = pd.read_parquet(f)
        if df.empty:
            empty += 1
            continue
        ticker, leg = f.parts[-2], f.stem.split("_")[-1]
        # ts_recv arrives as the index and the concat below is ignore_index, so it has to
        # become a column here or the window verification has nothing left to check.
        df = df.reset_index()
        df = df.assign(ticker=ticker, leg=leg, day=f.stem.split("_")[0])
        frames.append(df)
    if not frames:
        raise SystemExit("every cached window is empty; nothing printed in these contracts")
    raw = pd.concat(frames, ignore_index=True)
    print(f"  {len(files)} windows ({empty} with no data), {len(raw):,} records")
    _assert_window(raw)

    # cmbp-1 carries book updates and trades in one stream; only trades locate a fill.
    if "action" in raw.columns:
        raw = raw[raw["action"].astype(str).str.upper().str[0] == "T"]
    px = pd.to_numeric(raw.get("price"), errors="coerce")
    bid = pd.to_numeric(raw.get("bid_px_00"), errors="coerce")
    ask = pd.to_numeric(raw.get("ask_px_00"), errors="coerce")

    out = pd.DataFrame(
        {
            "ticker": raw["ticker"].to_numpy(),
            "leg": raw["leg"].to_numpy(),
            "day": raw["day"].to_numpy(),
            "price": px.to_numpy(),
            "bid": bid.to_numpy(),
            "ask": ask.to_numpy(),
            "size": pd.to_numeric(raw.get("size"), errors="coerce").to_numpy(),
        }
    )
    out["mid"] = (out["bid"] + out["ask"]) / 2
    out["width"] = out["ask"] - out["bid"]
    # A locked or crossed book gives no spread to locate a print inside, and a print
    # outside the touch is a late or out-of-sequence report rather than a fill to model.
    good = (
        out[["price", "bid", "ask"]].notna().all(axis=1)
        & (out["width"] > 0)
        & (out["mid"] > 0)
        & (out["price"] >= out["bid"] - 1e-9)
        & (out["price"] <= out["ask"] + 1e-9)
    )
    dropped = int((~good).sum())
    out = out[good].reset_index(drop=True)
    print(f"  {len(out):,} usable prints ({dropped:,} dropped: no book, locked, or outside touch)")

    out["fill_loc"] = (out["price"] - out["bid"]) / out["width"]
    out["quoted_half"] = (out["width"] / 2) / out["mid"]
    out["effective_half"] = (out["price"] - out["mid"]).abs() / out["mid"]
    out["improvement"] = 1 - out["effective_half"] / out["quoted_half"]
    return out


def _snapshot_spreads() -> pd.DataFrame:
    """The prevailing quoted spread at the 15:59 mark, unconditional on a trade occurring.

    This is the number a strategy committed to transacting at a fixed timestamp actually
    faces, and it is the one the rescore charges. It differs from the trade-conditional
    spread measured over prints because trades are not placed uniformly through the window:
    they cluster where the book is tight, so conditioning on a print observed having
    happened selects the favourable states. Reporting only the print-conditional figure
    would understate the cost by that selection, which is why both are carried.

    Taken as the last book update at or before 15:59 exchange-local for each contract in
    each window, mirroring ``databento_quotes`` snapshot marking.
    """
    rows = []
    for f in sorted(CACHE.rglob("*.parquet")):
        df = pd.read_parquet(f)
        if df.empty:
            continue
        idx = pd.DatetimeIndex(df.index)
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        df = df.assign(_local=idx.tz_convert(_EXCHANGE_TZ))
        cut = pd.Timestamp(f"{f.stem.split('_')[0]} 15:59").tz_localize(_EXCHANGE_TZ)
        df = df[df["_local"] <= cut]
        if df.empty:
            continue
        last = df.sort_values("_local").groupby("symbol", as_index=False).tail(1)
        bid = pd.to_numeric(last["bid_px_00"], errors="coerce")
        ask = pd.to_numeric(last["ask_px_00"], errors="coerce")
        mid = (bid + ask) / 2
        ok = (ask > bid) & (mid > 0)
        for h in ((ask - bid) / 2 / mid)[ok]:
            rows.append({"ticker": f.parts[-2], "leg": f.stem.split("_")[-1], "quoted_half": h})
    out = pd.DataFrame(rows)
    if out.empty:
        raise SystemExit("no two-sided book at the 15:59 cut in any cached window")
    return out


def _summarise(pr: pd.DataFrame) -> dict:
    def q(s: pd.Series, p: float) -> float:
        return float(np.nanpercentile(s, p))

    row = {
        "n_prints": len(pr),
        "n_windows": int(pr.groupby(["ticker", "day", "leg"]).ngroups),
        "quoted_half_median": q(pr["quoted_half"], 50),
        "effective_half_median": q(pr["effective_half"], 50),
        "improvement_median": q(pr["improvement"], 50),
        "improvement_mean": float(pr["improvement"].mean()),
        "fill_loc_median": q(pr["fill_loc"], 50),
        "frac_at_or_better_than_mid": float((pr["fill_loc"].between(0.4, 0.6)).mean()),
        "frac_worse_than_touch_half": float((pr["improvement"] < 0.1).mean()),
        "size_weighted_improvement": float(
            np.average(pr["improvement"], weights=pr["size"].clip(lower=1))
        ),
    }

    # The fixed-time book, unconditional on a print. This is the arm the rescore charges;
    # everything above it is conditioned on a trade having occurred and is diagnostic.
    snap = _snapshot_spreads()
    row["snapshot_quoted_half_median"] = float(snap["quoted_half"].median())
    row["snapshot_n_contracts"] = int(len(snap))
    for leg in ("entry", "exit"):
        s = snap[snap["leg"] == leg]["quoted_half"]
        if len(s):
            row[f"snapshot_{leg}_quoted_half_median"] = float(s.median())
    row["selection_ratio"] = row["snapshot_quoted_half_median"] / row["quoted_half_median"]
    for leg in ("entry", "exit"):
        s = pr[pr["leg"] == leg]
        if s.empty:
            continue
        row[f"{leg}_quoted_half_median"] = q(s["quoted_half"], 50)
        row[f"{leg}_effective_half_median"] = q(s["effective_half"], 50)
        row[f"{leg}_improvement_median"] = q(s["improvement"], 50)
    return row


def _report(r: dict) -> None:
    print("\n  FIXED-TIME BOOK AT THE 15:59 MARK (unconditional; the arm to charge)")
    print(
        f"    quoted half-spread    {r['snapshot_quoted_half_median']:.4%}  "
        f"({r['snapshot_n_contracts']} contracts)"
    )
    for leg in ("entry", "exit"):
        k = f"snapshot_{leg}_quoted_half_median"
        if k in r:
            print(f"    {leg:5s}: {r[k]:.4%}")
    print(
        f"    selection ratio       {r['selection_ratio']:.2f}x wider than the "
        f"print-conditional spread below"
    )
    print("\n  FILL LOCATION")
    print(f"    prints / windows      {r['n_prints']:,} / {r['n_windows']}")
    print(f"    quoted half-spread    {r['quoted_half_median']:.4%}  (median, of mid)")
    print(f"    effective half-spread {r['effective_half_median']:.4%}  (median, |px-mid|/mid)")
    print(
        f"    price improvement     {r['improvement_median']:.1%} median, "
        f"{r['improvement_mean']:.1%} mean"
    )
    print(f"    fill location         {r['fill_loc_median']:.3f}  (0=bid, 0.5=mid, 1=ask)")
    print(f"    prints near mid       {r['frac_at_or_better_than_mid']:.1%}")
    print(f"    prints at ~full touch {r['frac_worse_than_touch_half']:.1%}")
    for leg in ("entry", "exit"):
        k = f"{leg}_improvement_median"
        if k in r:
            print(
                f"    {leg:5s}: quoted {r[f'{leg}_quoted_half_median']:.4%}  "
                f"effective {r[f'{leg}_effective_half_median']:.4%}  "
                f"improvement {r[k]:.1%}"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="price the pull, spend nothing")
    ap.add_argument("--pull", action="store_true", help="fetch cmbp-1 windows (spends)")
    ap.add_argument("--score", action="store_true", help="measure fills from the cache")
    ap.add_argument("--cap", type=float, default=40.0, help="hard USD ceiling")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if not (args.dry_run or args.pull or args.score):
        ap.error("choose one of --dry-run / --pull / --score")

    if args.dry_run or args.pull:
        plan = _plan(_gated())
        if args.dry_run:
            _price(plan)
            print("\n  dry run: nothing was pulled and nothing was billed.")
            return
        _pull(plan, args.cap, args.workers)

    if args.score:
        pr = _prints()
        r = _summarise(pr)
        _report(r)
        PRINTS.parent.mkdir(parents=True, exist_ok=True)
        pr.to_parquet(PRINTS, index=False)
        pd.DataFrame([r]).to_csv(SUMMARY, index=False)
        print(f"\nwritten: {SUMMARY.resolve()}")
        print(f"written: {PRINTS.resolve()}")
        print(
            "\n  cmbp-1 reaches 2023-03-28 onward only. Transferring this improvement ratio "
            "to earlier years is a cross-regime claim, not a measurement: spreads tightened "
            "over the decade, so the backward transfer is an optimistic bound."
        )


if __name__ == "__main__":
    main()
