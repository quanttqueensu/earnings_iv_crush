"""describe.py: where do straddle package prints execute inside the quote?

Descriptive measurement, not a trial. No strategy return is computed and no selection rule is
fitted. The paper book sends the two legs of its straddle as separate orders and the cost model
charges the full touch on each. A two-leg order sent as one package can instead trade against a
complex order book or an auction at a net price inside the sum of the leg quotes. This script
measures, on the cached tick files for the two contracts the book held, how often both legs print
together and where those prints sit between the summed bid and the summed ask, beside the same
measure for single-leg prints in the same files.

A print pair is a package candidate when a call print and a put print share the venue, the size
and an event timestamp within ``PAIR_WINDOW_NS``. Location is 0 at the bid and 1 at the ask.
Pairs whose legs carry opposite aggressor sides, or sit at opposite touches, are reported apart as
synthetic-stock candidates (reversals and conversions) because their summed price sits at the mid
by construction and says nothing about a straddle.

Usage
-----
    python outputs/research/2026-11-11-package-prints-descriptive/describe.py [--limit N]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# ── constants ──────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
FLOW = ROOT / "data" / "cache" / "flow"
OUT = Path(__file__).resolve().parent
BLOCKS = ("broad_2025_2026", "megacap_2023_2024")
PAIR_WINDOW_NS = 1_000_000  # 1 ms: package legs are reported together; wider admits coincidences
OPPOSITE_TOUCH = 0.8  # leg locations further apart than this are read as a synthetic, not a straddle
COLS = ["ts_event", "publisher_id", "action", "side", "price", "size", "bid_px_00", "ask_px_00",
        "symbol"]
BINS = np.array([-np.inf, -1e-9, 0.05, 0.25, 0.45, 0.55, 0.75, 0.95, 1 + 1e-9, np.inf])
BIN_LABELS = ["below bid", "at bid", "0.05-0.25", "0.25-0.45", "mid", "0.55-0.75", "0.75-0.95",
              "at ask", "above ask"]


# ── per-file extraction ────────────────────────────────────────────────────────────────────
def _trades(path: Path, session_date: str | None) -> pd.DataFrame:
    """Trade prints with a two-sided, uncrossed quote on the row, regular session only."""
    df = pq.read_table(path, columns=COLS, filters=[("action", "=", "T")]).to_pandas()
    if df.empty:
        return df
    et = df["ts_event"].dt.tz_convert("America/New_York")
    keep = (et.dt.time >= pd.Timestamp("09:30").time()) & (et.dt.time < pd.Timestamp("16:00").time())
    if session_date is not None:
        keep &= et.dt.strftime("%Y-%m-%d") == session_date
    df = df[keep].copy()
    df["et"] = et[keep]
    width = df["ask_px_00"] - df["bid_px_00"]
    df = df[(df["bid_px_00"] > 0) & (width > 0)].copy()
    df["loc"] = (df["price"] - df["bid_px_00"]) / (df["ask_px_00"] - df["bid_px_00"])
    df["right"] = df["symbol"].str.strip().str[-9]
    return df


def _pair(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split prints into package candidates (call and put together) and single-leg prints."""
    calls = df[df["right"] == "C"].sort_values("ts_event")
    puts = df[df["right"] == "P"].sort_values("ts_event")
    if calls.empty or puts.empty:
        return pd.DataFrame(), df
    m = pd.merge_asof(
        calls.reset_index(drop=True).reset_index(names="ci"),
        puts.reset_index(drop=True).reset_index(names="pi"),
        on="ts_event", by=["publisher_id", "size"], direction="nearest",
        tolerance=pd.Timedelta(PAIR_WINDOW_NS, "ns"), suffixes=("_c", "_p"),
    ).dropna(subset=["pi"])
    m = m.drop_duplicates("pi")  # one put print serves one call print
    if m.empty:
        return m, df
    used_c = calls.reset_index(drop=True).index.isin(m["ci"])
    used_p = puts.reset_index(drop=True).index.isin(m["pi"].astype(int))
    singles = pd.concat([calls[~used_c], puts[~used_p]])
    bid = m["bid_px_00_c"] + m["bid_px_00_p"]
    ask = m["ask_px_00_c"] + m["ask_px_00_p"]
    m["pkg_loc"] = (m["price_c"] + m["price_p"] - bid) / (ask - bid)
    m["half_spread_rel"] = (ask - bid) / (ask + bid)
    opp_side = (m["side_c"].isin(["A", "B"]) & m["side_p"].isin(["A", "B"])
                & (m["side_c"] != m["side_p"]))
    m["synthetic"] = opp_side | ((m["loc_c"] - m["loc_p"]).abs() > OPPOSITE_TOUCH)
    return m, singles


# ── aggregation ────────────────────────────────────────────────────────────────────────────
def _hist(loc: pd.Series, weight: pd.Series | None = None) -> pd.Series:
    cut = pd.cut(loc, BINS, labels=BIN_LABELS)
    w = pd.Series(1.0, index=loc.index) if weight is None else weight.astype(float)
    h = w.groupby(cut, observed=False).sum()
    return h / h.sum()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0, help="files per block and leg (0 = all)")
    args = ap.parse_args()

    pk_rows, sg_rows, funnel = [], [], []
    for block in BLOCKS:
        for leg in ("pre", "exit"):
            files = sorted((FLOW / block).glob(f"*_{leg}.parquet"))
            if args.limit:
                files = files[:: max(1, len(files) // args.limit)][: args.limit]
            n_tr = n_pk = n_ev_pk = 0
            for f in files:
                ticker, date = f.stem.split("_")[:2]
                tr = _trades(f, date if leg == "pre" else None)
                if tr.empty:
                    continue
                pk, sg = _pair(tr)
                n_tr += len(tr)
                if len(pk):
                    n_pk += len(pk)
                    n_ev_pk += 1
                    pk_rows.append(pk.assign(block=block, leg=leg, ticker=ticker, date=date)[
                        ["block", "leg", "ticker", "date", "ts_event", "size", "publisher_id",
                         "side_c", "side_p", "loc_c", "loc_p", "pkg_loc", "half_spread_rel",
                         "synthetic"]])
                sg_rows.append(sg.assign(block=block, leg=leg, ticker=ticker, date=date)[
                    ["block", "leg", "ticker", "date", "size", "loc"]])
            funnel.append(dict(block=block, leg=leg, files=len(files), trades=n_tr,
                               package_pairs=n_pk, files_with_package=n_ev_pk))
    fun = pd.DataFrame(funnel)
    print("FUNNEL (prints with a two-sided quote on the row, regular session)")
    print(fun.to_string(index=False))
    if not pk_rows:
        raise SystemExit("no package candidates found: nothing to describe")
    pk = pd.concat(pk_rows, ignore_index=True)
    sg = pd.concat(sg_rows, ignore_index=True)
    pk.to_parquet(OUT / "packages.parquet")
    fun.to_csv(OUT / "funnel.csv", index=False)

    pd.set_option("display.width", 200)
    for (block, leg), g in pk.groupby(["block", "leg"]):
        s = sg[(sg["block"] == block) & (sg["leg"] == leg)]
        st = g[~g["synthetic"]]
        print(f"\n== {block} / {leg}: {len(g)} pairs, {int(g['synthetic'].sum())} read as "
              f"synthetic, {len(st)} straddle candidates on {st.groupby(['ticker', 'date']).ngroups}"
              f" events; {len(s)} single-leg prints ==")
        tab = pd.DataFrame({
            "single (prints)": _hist(s["loc"]),
            "single (contracts)": _hist(s["loc"], s["size"]),
            "straddle pkg (prints)": _hist(st["pkg_loc"]),
            "straddle pkg (contracts)": _hist(st["pkg_loc"], st["size"]),
            "pkg call leg": _hist(st["loc_c"]),
            "pkg put leg": _hist(st["loc_p"]),
        })
        print((100 * tab).round(1).to_string())
        if len(st):
            dist = (st["pkg_loc"] - 0.5).abs() * 2  # share of the half-spread paid by either side
            ev = dist.groupby([st["ticker"], st["date"]]).mean()
            rng = np.random.default_rng(0)
            boot = [ev.sample(len(ev), replace=True, random_state=rng).mean() for _ in range(2000)]
            print(f"share of the package half-spread paid, event-equal mean: {ev.mean():.3f} "
                  f"[{np.percentile(boot, 2.5):.3f}, {np.percentile(boot, 97.5):.3f}] over "
                  f"{len(ev)} events; median package half-spread {100 * st['half_spread_rel'].median():.2f}%"
                  f" of mid; median size {st['size'].median():.0f}")
            print("aggressor sides on straddle candidates (call/put):")
            print(st.groupby(["side_c", "side_p"]).size().to_string())


if __name__ == "__main__":
    main()
