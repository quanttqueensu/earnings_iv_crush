"""
paper_radar.py
Free, full-universe forward paper recorder for the name-persistence overlay.

Each run does two things for the S&P universe (``universe.BROAD_300``):

  exits    for open paper positions whose exit session is today, fetch the spot,
           compute the realised move, book the short-straddle return on premium
           ``ret = 1 - |realised_move| / implied_move`` net of the 11.6% cost, and
           close the position into the ledger.
  entries  find names with earnings in the next few sessions (free Finnhub
           calendar), and for any whose session-aware entry is today, snapshot the
           ATM straddle (free yfinance chain, real bid/ask) for the implied move and
           open a paper position. Every event is recorded and labelled against the
           richness seed (``data/rich_set.csv``, built by scripts/build_rich_seed.py)
           rather than filtered on it, so the book carries both the overlay and the
           unconditional arm it is judged against, and a revised seed can be applied
           to an existing book.

No broker, no capital, no metered data. Intended to run once per weekday after the
US close, either locally or from the GitHub Actions workflow (.github/workflows/
paper_radar.yml) so it keeps booking with the machine off. Run it post-close: before
the open, yfinance serves chains with every bid/ask zeroed and nothing can be marked.

Books (CSV, git-friendly):
    outputs/paper/radar_open_positions.csv
    outputs/paper/radar_ledger.csv

Every ledger row is stamped ``source``. This recorder only ever writes ``live``: the
position was opened before the announcement and booked after it, so no entry decision
could see its own outcome. Trades scored after the fact live in
``outputs/research/backfill_ledger.csv`` and are never merged into this file.

Usage:
    python scripts/paper_radar.py [--date YYYY-MM-DD] [--universe broad|megacap] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

from earnings_iv_crush.data import (  # noqa: E402
    earnings,
    features,
    options,
    universe,
)

BOOK_DIR = Path("outputs/paper")
OPEN_CSV = BOOK_DIR / "radar_open_positions.csv"
LEDGER_CSV = BOOK_DIR / "radar_ledger.csv"
RICH_SEED = Path("data/rich_set.csv")

LOOKAHEAD_DAYS = 6
COST = 0.116  # break-even round-trip as a fraction of premium

OPEN_COLS = [
    "ticker",
    "announce_date",
    "session",
    "entry_date",
    "exit_date",
    "spot_entry",
    "strike",
    "expiry",
    "straddle_mid",
    "implied_move",
    "in_rich_set",
]
LEDGER_COLS = [
    "ticker",
    "announce_date",
    "entry_date",
    "exit_date",
    "spot_entry",
    "spot_exit",
    "implied_move",
    "realised_move",
    "ret",
    "net_ret",
    "in_rich_set",
    "source",
]

# Every ledger row carries how it came to exist. "live" means this recorder opened the
# position before the announcement and booked its exit afterwards, so the entry decision
# could not see the outcome. Anything scored after the fact belongs in the backfill
# ledger (outputs/research/) and is inadmissible as forward evidence. Without the column
# the two are indistinguishable once they share a file, which is how a backtest ends up
# quoted as a paper record.
LIVE = "live"


def _load(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path)
    if cols is LEDGER_COLS and len(df) and "source" not in df.columns:
        raise SystemExit(
            f"ERROR: {path} has {len(df)} rows and no 'source' column, so live trades "
            f"cannot be told from backfilled ones. Refusing to append to an "
            f"unattributable book. Move the existing rows to outputs/research/ and "
            f"restart the live ledger, or stamp the column by hand."
        )
    return df


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _spot(ticker: str, asof: pd.Timestamp) -> float | None:
    start = (asof - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (asof + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        h = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)["Close"]
    except Exception:
        return None
    if h is None or h.empty:
        return None
    return float(h.dropna().iloc[-1])


def _rich_set() -> set[str] | None:
    """Names in the top 30% by prior-mean return on premium, or None if unseeded.

    Read from the tracked seed at ``data/rich_set.csv`` so the cloud runner sees the
    same universe as a local run. The seed is built from the validated event tables
    (megacap Databento plus broad 2024/2025) by ``scripts/build_rich_seed.py``; every
    event in it predates the forward book, so the label is causal for trades booked
    from here on.

    Returning None means *unseeded*, not *everything is rich* - callers must label the
    trade's rich status unknown rather than assuming inclusion.
    """
    if not RICH_SEED.exists():
        return None
    try:
        seed = pd.read_csv(RICH_SEED)
    except Exception:
        return None
    if seed.empty or "is_rich" not in seed.columns:
        return None
    return set(seed.loc[seed["is_rich"].astype(bool), "ticker"].astype(str))


def _snapshot(ticker: str, asof: pd.Timestamp, announce: pd.Timestamp):
    """Snapshot the ATM straddle, or return (None, reason) saying why not.

    The reason matters: "unquoted" means the chain came back with strikes and open
    interest but every bid/ask zeroed, which is what yfinance serves outside US
    market hours. That is a scheduling problem, not a thin-market skip, and the two
    must not be summed into one silent zero.
    """
    try:
        chain = options.fetch_option_chain(ticker, asof.strftime("%Y-%m-%d"))
    except Exception as exc:
        return None, f"chain error: {type(exc).__name__}"
    if chain is None or chain.empty:
        return None, "no chain"
    if not ((chain["bid"] > 0) | (chain["ask"] > 0)).any():
        return None, "unquoted chain (market closed or feed degraded)"
    spot = _spot(ticker, asof)
    if spot is None:
        return None, "no spot"
    fwd = chain[pd.to_datetime(chain["expiry"]) >= announce]
    if fwd.empty:
        return None, "no expiry at or beyond the announcement"
    expiry = pd.to_datetime(fwd["expiry"]).min()
    strike = features.atm_strike(chain, spot)
    straddle = features.atm_straddle_mid(chain, expiry, strike)
    im = features.implied_move(chain, spot, expiry, strike)
    if not straddle or not im:
        return None, "no ATM straddle mid"
    if im < 0.02:
        return None, f"implied move {im:.4f} below the 0.02 floor"
    return (spot, float(strike), expiry.strftime("%Y-%m-%d"), float(straddle), float(im)), "ok"


def run_exits(today: pd.Timestamp, dry: bool) -> int:
    openpos = _load(OPEN_CSV, OPEN_COLS)
    if openpos.empty:
        return 0
    ledger = _load(LEDGER_CSV, LEDGER_COLS)
    due = openpos[pd.to_datetime(openpos["exit_date"]) <= today]
    booked = 0
    for _, r in due.iterrows():
        # Mark at the position's own exit session, not the run date. A missed run
        # (machine off, cloud job failed) would otherwise measure a multi-day move
        # and book it as the earnings-day move.
        exit_on = pd.Timestamp(r["exit_date"])
        spot_exit = _spot(str(r["ticker"]), exit_on)
        if spot_exit is None:
            continue
        # Corporate-action guard. spot_entry was stored from a live snapshot; the
        # history feed is split-adjusted retroactively, so a split between entry and
        # exit makes the two incomparable and shows up as a fictitious huge move.
        # Re-read the entry session from the same series the exit came from and use
        # that as the denominator, so both legs sit on one adjustment basis.
        spot_entry_now = _spot(str(r["ticker"]), pd.Timestamp(r["entry_date"]))
        spot_entry = float(r["spot_entry"])
        if spot_entry_now is not None:
            ratio = spot_entry / spot_entry_now
            if abs(ratio - 1.0) > 0.02:
                print(
                    f"  [corp-action] {r['ticker']}: booked entry {spot_entry:.2f} vs "
                    f"adjusted {spot_entry_now:.2f} (x{ratio:.4f}) - marking on the "
                    f"adjusted basis"
                )
                spot_entry = spot_entry_now
        rm = abs(spot_exit / spot_entry - 1.0)
        ret = 1.0 - rm / float(r["implied_move"])
        ledger.loc[len(ledger)] = {
            "ticker": r["ticker"],
            "announce_date": r["announce_date"],
            "entry_date": r["entry_date"],
            "exit_date": r["exit_date"],
            "spot_entry": spot_entry,
            "spot_exit": spot_exit,
            "implied_move": r["implied_move"],
            "realised_move": rm,
            "ret": ret,
            "net_ret": ret - COST,
            "in_rich_set": r["in_rich_set"],
            "source": LIVE,
        }
        booked += 1
    keep = openpos[pd.to_datetime(openpos["exit_date"]) > today]
    if not dry:
        _write(ledger, LEDGER_CSV)
        _write(keep, OPEN_CSV)
    return booked


def run_entries(
    today: pd.Timestamp, names: list[str], rich: set[str] | None, dry: bool
) -> tuple[int, int, list[str]]:
    end = (today + timedelta(days=LOOKAHEAD_DAYS)).strftime("%Y-%m-%d")
    cal = earnings.fetch_earnings_calendar(today.strftime("%Y-%m-%d"), end)
    if cal.empty:
        return 0, 0
    cal = cal[cal["ticker"].isin(names)].copy()
    openpos = _load(OPEN_CSV, OPEN_COLS)
    held = set(zip(openpos["ticker"], openpos["announce_date"].astype(str), strict=False))
    session_col = "session" if "session" in cal.columns else "hour"
    seen, opened = 0, 0
    skips: list[str] = []
    for _, e in cal.iterrows():
        announce = pd.Timestamp(e["announce_date"])
        dates = earnings.trade_dates_for_session(announce, e.get(session_col))
        if dates is None:
            continue
        entry_date, exit_date = dates
        if entry_date.normalize() != today.normalize():
            continue
        seen += 1
        if (e["ticker"], str(announce.date())) in held:
            continue
        # Record every event and label it, rather than hard-filtering to the rich
        # set. The book stays re-analysable if the seed is later revised, and the
        # unconditional arm is the comparison the overlay is judged against. An
        # unseeded run must label "unknown" - stamping it rich would silently mark
        # an unconditional book as the overlay.
        in_rich = "unknown" if rich is None else str(e["ticker"] in rich).lower()
        snap, reason = _snapshot(e["ticker"], today, announce)
        if snap is None:
            print(f"  [skip] {e['ticker']}: {reason}")
            skips.append(reason)
            continue
        spot, strike, expiry, straddle, im = snap
        openpos.loc[len(openpos)] = {
            "ticker": e["ticker"],
            "announce_date": str(announce.date()),
            "session": e.get(session_col),
            "entry_date": str(entry_date.date()),
            "exit_date": str(exit_date.date()),
            "spot_entry": spot,
            "strike": strike,
            "expiry": expiry,
            "straddle_mid": straddle,
            "implied_move": im,
            "in_rich_set": in_rich,
        }
        opened += 1
    if not dry:
        _write(openpos, OPEN_CSV)
    return seen, opened, skips


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="run date YYYY-MM-DD (default today)")
    ap.add_argument("--universe", default="broad", choices=["broad", "megacap"])
    ap.add_argument("--dry-run", action="store_true", help="compute but do not write the books")
    args = ap.parse_args()

    today = pd.Timestamp(args.date) if args.date else pd.Timestamp.now().normalize()
    names = universe.get_universe(args.universe)
    rich = _rich_set()
    seed = (
        f"{RICH_SEED} ({len(rich)} rich names)"
        if rich is not None
        else "UNSEEDED - recording all, rich status labelled unknown"
    )

    booked = run_exits(today, args.dry_run)
    seen, opened, skips = run_entries(today, names, rich, args.dry_run)

    ledger = _load(LEDGER_CSV, LEDGER_COLS)
    print(
        f"=== paper radar {today.date()}  universe={args.universe} ({len(names)} names)  seed: {seed} ==="
    )
    print(f"exits booked today: {booked}   entries: {opened} opened of {seen} whose entry is today")
    print(f"open positions: {len(_load(OPEN_CSV, OPEN_COLS))}   ledger trades: {len(ledger)}")
    # Report the live book only. Rows scored after the fact are excluded from every
    # statistic printed here rather than pooled and footnoted, because the pooled number
    # is the one that gets quoted.
    if len(ledger):
        src = ledger["source"].astype(str).str.lower()
        n_other = int((src != LIVE).sum())
        if n_other:
            print(
                f"  WARNING: {n_other} non-live row(s) present and excluded from every "
                f"figure below. They are not forward evidence."
            )
        live = ledger[src == LIVE]
        flag = live["in_rich_set"].astype(str).str.lower()
        books = [("all booked", live), ("rich only", live[flag == "true"])]
        if (flag == "unknown").any():
            n_unk = int((flag == "unknown").sum())
            print(f"  WARNING: {n_unk} trades booked unseeded - excluded from the rich arm")
        for lbl, book in books:
            if len(book):
                x = book["net_ret"].astype(float)
                print(
                    f"  {lbl:10s} N={len(book):4d} netMean={x.mean():+.4f} hit={(x>0).mean():.3f} "
                    f"cum={x.sum():+.3f}"
                )
        if not len(live):
            print("  live book is empty - no completed forward trade yet, so no inference")
    if args.dry_run:
        print("(dry-run: books not written)")

    # Fail loudly rather than book a silent zero. Events were due today and not one
    # could be snapshotted, which means the chain or spot feed is broken (yfinance is
    # rate-limited from datacenter IPs), not that the calendar was empty. A job that
    # exits green on this would accrue an empty book for weeks - the exact failure
    # that produced the current one.
    if seen > 0 and opened == 0:
        tally = pd.Series(skips).value_counts().to_dict() if skips else {}
        detail = ", ".join(f"{k} x{v}" for k, v in tally.items()) or "no reason recorded"
        print(
            f"ERROR: {seen} event(s) had their entry today and none could be "
            f"snapshotted ({detail}). Not booking a silent zero.",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
