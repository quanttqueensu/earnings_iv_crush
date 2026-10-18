"""
research_flow_liquidity.py
Pre-registered tests of the liquidity-provider side from signed OPRA trades.

``research/execution/preregs/flow_liquidity_side_prereg.md``. Two tests on the two contracts each event trades:

    F1  resting orders at the mid from 15:00, crossing at 15:59 only if unfilled, against always
        crossing; filled only when a trade prints strictly through the limit
    F2  net customer buying before entry (trades signed against the prevailing mid) as the selector

Data: Databento OPRA ``cmbp-1``. Every request is priced with ``get_cost`` before it is made, the
running spend is checked against a hard cap, and every returned file is verified to lie inside its
intended America/New_York window, the check that would have caught the earlier UTC mislabelling.

Usage:
    python research/execution/research_flow_liquidity.py --pull --cap 10
    python research/execution/research_flow_liquidity.py --score

References
----------
Muravyev, D. (2016). Order Flow and Expected Option Returns. *Journal of Finance* 71(2), 673-708.
de Silva, T., So, E. C. and Smith, K. (2026). Losing is Optional: Retail Option Trading and
Expected Announcement Volatility. *Review of Finance* 30(2), 489-.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from research.execution.research_fills_study import _straddle_symbols  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy"))
from session_check import is_early_close  # noqa: E402

LEDGER = Path("outputs/research/oos_2026_ledger.csv")
PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
CACHE = Path("data/cache/flow")
OUT = Path("outputs/research/flow_liquidity")

SCHEMA = "cmbp-1"
TZ = "America/New_York"
CMBP_START = pd.Timestamp("2023-03-28")
ENTRY_HALF, EXIT_HALF = 0.012714, 0.030182  # measured basis, megacap outcome for F2
MIN_SIGNED = 10
Q, MIN_HIST, N_NULL = 0.80, 25, 1000
N_BOOT, SEED = 5000, 0


# ── plan ─────────────────────────────────────────────────────────────────────


def _utc(day: pd.Timestamp, hm: str) -> pd.Timestamp:
    h, m = map(int, hm.split(":"))
    local = (pd.Timestamp(day).normalize() + pd.Timedelta(hours=h, minutes=m)).tz_localize(TZ)
    return local.tz_convert("UTC")


def events() -> pd.DataFrame:
    """Both blocks with the per-contract fields the tests need."""
    led = pd.read_csv(LEDGER, parse_dates=["entry_date", "exit_date", "expiry", "announce_date"])
    b = led.rename(columns={"strike": "strike_mkt", "expiry": "expiry_mkt"}).assign(
        block="broad_2025_2026",
        margin_1=led["margin"],
        credit_1=led["credit"],
        net_rop_flat=led["net_rop"],
    )
    p = pd.read_parquet(PANEL)
    p = p[p["block"] == "discovery_2019_2024"].copy()
    for c in ("entry_date", "exit_date", "announce_date", "expiry_mkt"):
        p[c] = pd.to_datetime(p[c])
    p = p[p["entry_date"] >= CMBP_START]
    k = p["contracts"]
    cost = ENTRY_HALF * p["credit_mkt"] + EXIT_HALF * p["exit_mkt"]
    p = p.assign(
        block="megacap_2023_2024",
        margin_1=p["margin"] / k,
        credit_1=p["credit_mkt"] * 100,
        net_rop_flat=(p["credit_mkt"] - p["exit_mkt"] - cost) / p["credit_mkt"],
    )
    cols = [
        "block",
        "ticker",
        "announce_date",
        "entry_date",
        "exit_date",
        "strike_mkt",
        "expiry_mkt",
        "implied_move",
        "margin_1",
        "credit_1",
        "net_rop_flat",
    ]
    return pd.concat([b[cols], p[cols]], ignore_index=True)


def plan(ev: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, e in ev.iterrows():
        syms = _straddle_symbols(e)
        if not syms:
            continue
        pre_start = e["entry_date"] - 2 * pd.offsets.BDay()
        rows.append(
            {
                **e.to_dict(),
                "kind": "pre",
                "symbols": syms,
                "start": _utc(pre_start, "09:30"),
                "end": _utc(e["entry_date"], "16:00"),
            }
        )
        rows.append(
            {
                **e.to_dict(),
                "kind": "exit",
                "symbols": syms,
                "start": _utc(e["exit_date"], "15:00"),
                "end": _utc(e["exit_date"], "16:00"),
            }
        )
    return pd.DataFrame(rows)


def _path(r: dict) -> Path:
    return (
        CACHE
        / r["block"]
        / f"{r['ticker']}_{pd.Timestamp(r['entry_date']).date()}_{r['kind']}.parquet"
    )


def _verify(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> None:
    if df.empty:
        return
    idx = pd.DatetimeIndex(df.index if df.index.name in {"ts_recv", "ts_event"} else df["ts_recv"])
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    # Consolidated feeds can stamp the opening snapshot a few seconds before the request start.
    bad = ((idx < start - pd.Timedelta(minutes=1)) | (idx > end + pd.Timedelta(minutes=1))).sum()
    if bad:
        raise SystemExit(
            f"{bad} records outside {start}..{end} - wrong pull window, not measuring it"
        )


# ── pull ─────────────────────────────────────────────────────────────────────


def pull(cap: float, workers: int) -> None:
    pl = plan(events())
    todo = [r for r in pl.to_dict("records") if not _path(r).exists()]
    print(
        f"  {len(pl)} requests planned, {len(pl) - len(todo)} cached, {len(todo)} to pull, cap ${cap:.2f}",
        flush=True,
    )
    lock, halted = threading.Lock(), threading.Event()
    state = {"spent": 0.0, "done": 0, "fail": 0}

    def one(r: dict) -> None:
        if halted.is_set():
            return
        s = r["start"].strftime("%Y-%m-%dT%H:%M:%SZ")
        e = r["end"].strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            c = float(dbo.get_cost(r["symbols"], s, e, schema=SCHEMA))
            with lock:
                if state["spent"] + c > cap:
                    halted.set()
                    return
                state["spent"] += c
            df = dbo._get_df(SCHEMA, r["symbols"], s, e, stype_in="raw_symbol")
            df = df if df is not None else pd.DataFrame()
            _verify(df, r["start"], r["end"])
            _path(r).parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(_path(r))
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - counted, never silently treated as empty
            with lock:
                state["fail"] += 1
                if state["fail"] <= 5:
                    print(f"  failed {r['ticker']} {r['kind']}: {exc!r}"[:200], flush=True)
        with lock:
            state["done"] += 1
            if state["done"] % 100 == 0 or state["done"] == len(todo):
                print(
                    f"  {state['done']}/{len(todo)} pulled, spent ${state['spent']:.4f}, "
                    f"{state['fail']} failed",
                    flush=True,
                )

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))
    msg = "HALTED AT CAP" if halted.is_set() else "PULL DONE"
    print(
        f"  {msg}: spent ${state['spent']:.4f} (estimate $2.12 broad), {state['fail']} failed, "
        f"{(time.time() - t0) / 60:.1f} min",
        flush=True,
    )


# ── measurement ──────────────────────────────────────────────────────────────


def _frame(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.empty:
        return None
    ts = df.index if df.index.name in {"ts_recv", "ts_event"} else df["ts_recv"]
    idx = pd.DatetimeIndex(ts)
    df = df.assign(t=(idx.tz_localize("UTC") if idx.tz is None else idx).tz_convert(TZ))
    df["right"] = df["symbol"].astype(str).str.replace(" ", "").str[-9]
    return df.sort_values("t")


def _quote_after(
    leg: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[float, float] | None:
    """First valid quote in (start, end]."""
    q = leg[
        (leg["t"] > start)
        & (leg["t"] <= end)
        & (leg["bid_px_00"] > 0)
        & (leg["ask_px_00"] > leg["bid_px_00"])
    ]
    if q.empty:
        return None
    r = q.iloc[0]
    return float(r["bid_px_00"]), float(r["ask_px_00"])


def _quote_at(leg: pd.DataFrame, when: pd.Timestamp) -> tuple[float, float] | None:
    q = leg[(leg["t"] <= when) & (leg["bid_px_00"] > 0) & (leg["ask_px_00"] > leg["bid_px_00"])]
    if q.empty:
        return None
    r = q.iloc[-1]
    return float(r["bid_px_00"]), float(r["ask_px_00"])


TICKS = {"penny": (0.01, 0.05), "nonpenny": (0.05, 0.10)}  # (below 3.00, at or above 3.00)
RULES = ("strict", "optimistic")
MARKOUTS = (1, 5, 15)  # minutes after the fill; 15:59 is added separately
RECON_TOL, RECON_MAX_SHARE = 0.01, 0.25  # addendum 01, item 6
MIN_BLOCK_EVENTS = 100
GO_IMPROVEMENT, GO_MARKOUT, GO_FILL = 0.0065, -0.5, 0.30


def _round_limit(mid: float, side: str, schedule: str) -> float:
    """Legal tick, P&L-unfavourable direction: sells round down, buys round up."""
    lo, hi = TICKS[schedule]
    tick = lo if mid < 3.0 else hi
    steps = mid / tick
    n = np.floor(steps + 1e-9) if side == "sell" else np.ceil(steps - 1e-9)
    return float(round(n * tick, 4))


def _first_fill(leg: pd.DataFrame, t0, t1, limit: float, side: str, rule: str):
    """First moment a resting order at ``limit`` fills under ``rule``, or None.

    A sell fills when a trade prints above the limit (or at it under the optimistic rule) or
    the NBBO bid reaches the limit; a buy mirrors this on the ask.
    """
    w = leg[(leg["t"] >= t0) & (leg["t"] <= t1)]
    if w.empty:
        return None
    trade = w["action"] == "T"
    if side == "sell":
        through = w["price"] > limit if rule == "strict" else w["price"] >= limit
        quote = w["bid_px_00"] >= limit
    else:
        through = w["price"] < limit if rule == "strict" else w["price"] <= limit
        quote = (w["ask_px_00"] <= limit) & (w["ask_px_00"] > 0)
    hit = w[(trade & through) | quote]
    return None if hit.empty else hit["t"].iloc[0]


def _mid_at(leg: pd.DataFrame, when) -> float | None:
    q = _quote_at(leg, when)
    return None if q is None else (q[0] + q[1]) / 2


def _leg(leg: pd.DataFrame, day, side: str, schedule: str, rule: str) -> dict | None:
    t15 = (day + pd.Timedelta(hours=15)).tz_localize(TZ)
    t1559 = (day + pd.Timedelta(hours=15, minutes=59, seconds=59)).tz_localize(TZ)
    # Addendum 02: exit files begin at 15:00:00, so fall back to the first quote in the next minute.
    q15 = _quote_at(leg, t15) or _quote_after(leg, t15, t15 + pd.Timedelta(minutes=1))
    qx = _quote_at(leg, t1559)
    if q15 is None or qx is None:
        return None
    limit = _round_limit(sum(q15) / 2, side, schedule)
    cross = qx[0] if side == "sell" else qx[1]
    tf = _first_fill(leg, t15, t1559, limit, side, rule)
    out: dict = {
        "limit": limit,
        "cross": cross,
        "filled": tf is not None,
        "price": limit if tf is not None else cross,
    }
    if tf is not None:
        qf = _quote_at(leg, tf)
        half = (qf[1] - qf[0]) / 2 if qf else np.nan
        sign = 1.0 if side == "sell" else -1.0
        for m in (*MARKOUTS, "1559"):
            when = t1559 if m == "1559" else min(tf + pd.Timedelta(minutes=int(m)), t1559)
            mid = _mid_at(leg, when)
            if mid is not None and half == half and half > 0:
                out[f"mk_{m}"] = sign * (limit - mid) / half
            else:
                out[f"mk_{m}"] = np.nan
    return out


def measure_event(e: pd.Series) -> dict | None:
    pre = _frame(_path({**e.to_dict(), "kind": "pre"}))
    ex = _frame(_path({**e.to_dict(), "kind": "exit"}))
    if pre is None or ex is None:
        return None
    d_in = pd.Timestamp(e["entry_date"]).normalize()
    d_out = pd.Timestamp(e["exit_date"]).normalize()
    if is_early_close(d_in) or is_early_close(d_out):
        return {"early_close": True}

    row: dict = {
        "block": e["block"],
        "ticker": e["ticker"],
        "entry_date": e["entry_date"],
        "announce_date": e["announce_date"],
        "implied_move": e["implied_move"],
        "net_rop_flat": e["net_rop_flat"],
        "early_close": False,
    }
    m = float(e["margin_1"])
    marks = []
    for schedule in ("penny", "nonpenny"):
        for rule in RULES:
            legs = {}
            for right in ("C", "P"):
                li, lo = pre[pre["right"] == right], ex[ex["right"] == right]
                a = _leg(li, d_in, "sell", schedule, rule)
                b = _leg(lo, d_out, "buy", schedule, rule)
                if a is None or b is None:
                    return None
                legs[right] = (a, b)
            sell_rest = sum(a["price"] for a, _ in legs.values())
            buy_rest = sum(b["price"] for _, b in legs.values())
            sell_cross = sum(a["cross"] for a, _ in legs.values())
            buy_cross = sum(b["cross"] for _, b in legs.values())
            tag = f"{rule}_{schedule}"
            row["rom_cross"] = (sell_cross - buy_cross) * 100 / m
            row[f"rom_both_{tag}"] = (sell_rest - buy_rest) * 100 / m
            row[f"rom_entry_{tag}"] = (sell_rest - buy_cross) * 100 / m
            row[f"rom_exit_{tag}"] = (sell_cross - buy_rest) * 100 / m
            row[f"entry_legs_{tag}"] = sum(a["filled"] for a, _ in legs.values())
            row[f"exit_legs_{tag}"] = sum(b["filled"] for _, b in legs.values())
            if schedule == "penny":
                for right, (a, b) in legs.items():
                    for side, f in (("entry", a), ("exit", b)):
                        if f["filled"]:
                            mk = {k: v for k, v in f.items() if k.startswith("mk_")}
                            marks.append(
                                {
                                    "ticker": e["ticker"],
                                    "entry_date": e["entry_date"],
                                    "block": e["block"],
                                    "rule": rule,
                                    "side": side,
                                    "leg": right,
                                    **mk,
                                }
                            )
    row["_markouts"] = marks

    # Addendum 03: the reconciliation cross is taken at 15:59:00, the chain's own sampling instant.
    recon = 0.0
    for right in ("C", "P"):
        a = _quote_at(
            pre[pre["right"] == right], (d_in + pd.Timedelta(hours=15, minutes=59)).tz_localize(TZ)
        )
        b = _quote_at(
            ex[ex["right"] == right], (d_out + pd.Timedelta(hours=15, minutes=59)).tz_localize(TZ)
        )
        if a is None or b is None:
            recon = float("nan")
            break
        recon += a[0] - b[1]
    row["rom_cross_recon"] = recon * 100 / m

    t15_in = (d_in + pd.Timedelta(hours=15)).tz_localize(TZ)
    tr = pre[(pre["action"] == "T") & (pre["t"] <= t15_in) & (pre["bid_px_00"] > 0)]
    mid = (tr["bid_px_00"] + tr["ask_px_00"]) / 2
    buys = float(tr.loc[tr["price"] > mid, "size"].sum())
    sells = float(tr.loc[tr["price"] < mid, "size"].sum())
    row["signed_contracts"] = buys + sells
    row["imbalance"] = (buys - sells) / (buys + sells) if buys + sells > 0 else np.nan
    return row


def _sharpe(x: np.ndarray) -> float:
    return float(x.mean() / x.std(ddof=1)) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")


def _keys(d: pd.DataFrame) -> np.ndarray:
    return pd.to_datetime(d["entry_date"]).dt.strftime("%Y-%m-%d").to_numpy()


def _mean_ci(x: np.ndarray, keys: np.ndarray) -> tuple[float, float]:
    return cluster_bootstrap_ci(x, keys, lambda v: float(v.mean()), n_boot=N_BOOT, seed=SEED)


def reconcile(d: pd.DataFrame) -> dict:
    """Addendum item 6: tick-built cross book against the cached 15:59 chain touch."""
    from research.selection.research_final_earnings_set import broad_quotes

    ref = broad_quotes()
    ref["rom_touch_chain"] = (ref["entry_bid"] - ref["exit_ask"]) * 100 / ref["margin"]
    ref["entry_date"] = pd.to_datetime(ref["entry_date"])
    b = d[d["block"] == "broad_2025_2026"].copy()
    b["entry_date"] = pd.to_datetime(b["entry_date"])
    j = b.merge(ref[["ticker", "entry_date", "rom_touch_chain"]], on=["ticker", "entry_date"])
    gap = (j["rom_cross_recon"] - j["rom_touch_chain"]).abs().dropna()
    share = float((gap > RECON_TOL).mean()) if len(j) else float("nan")
    res = {
        "n_matched": len(gap),
        "median_abs_gap": float(gap.median()) if len(j) else float("nan"),
        "share_over_tol": share,
    }
    print(f"  reconciliation: {res}")
    if len(j) and share > RECON_MAX_SHARE:
        raise SystemExit(
            "cross book disagrees with the 15:59 chain touch on more than a quarter of events - "
            "stopping before any paired result (addendum 01, item 6)"
        )
    return res


def f1(d: pd.DataFrame, marks: pd.DataFrame, block: str) -> list[dict]:
    k = _keys(d)
    c = d["rom_cross"].to_numpy()
    out = []
    for arm in ("both", "entry", "exit"):
        for rule in RULES:
            for schedule in ("penny", "nonpenny"):
                if schedule == "nonpenny" and arm != "both":
                    continue
                tag = f"{rule}_{schedule}"
                x = d[f"rom_{arm}_{tag}"].to_numpy()
                lo, hi = _mean_ci(x - c, k)
                slo, shi = cluster_bootstrap_ci(x, k, _sharpe, n_boot=N_BOOT, seed=SEED)
                sides = ["entry", "exit"] if arm == "both" else [arm]
                sel = (
                    marks[(marks["rule"] == rule) & (marks["side"].isin(sides))]
                    if len(marks)
                    else marks
                )
                mk = sel["mk_5"].dropna() if len(sel) else pd.Series(dtype=float)
                out.append(
                    {
                        "block": block,
                        "arm": arm,
                        "rule": rule,
                        "ticks": schedule,
                        "n": len(d),
                        "improvement": float((x - c).mean()),
                        "impr_ci_low": lo,
                        "impr_ci_high": hi,
                        "sharpe_resting": _sharpe(x),
                        "sharpe_ci_low": slo,
                        "sharpe_ci_high": shi,
                        "sharpe_cross": _sharpe(c),
                        "entry_both_legs_filled": float((d[f"entry_legs_{tag}"] == 2).mean()),
                        "exit_both_legs_filled": float((d[f"exit_legs_{tag}"] == 2).mean()),
                        "markout_5m_vs_half_spread": float(mk.mean()) if len(mk) else float("nan"),
                        "n_fills_markout": len(mk),
                    }
                )
    return out


def f1_verdict(rows: pd.DataFrame) -> dict:
    verdict = {}
    for block, g in rows.groupby("block"):
        prim = g[(g["arm"] == "both") & (g["ticks"] == "penny")]
        if int(prim["n"].iloc[0]) < MIN_BLOCK_EVENTS:
            verdict[block] = "underpowered"
            continue
        gates = all(
            (r["improvement"] >= GO_IMPROVEMENT)
            and (r["impr_ci_low"] > 0)
            and (r["markout_5m_vs_half_spread"] >= GO_MARKOUT)
            for _, r in prim.iterrows()
        )
        fill = float(prim[prim["rule"] == "strict"]["entry_both_legs_filled"].iloc[0])
        verdict[block] = "PASS" if gates and fill >= GO_FILL else "FAIL"
    return verdict


def f2_discovery(d: pd.DataFrame) -> dict:
    d = d[
        (d["signed_contracts"] >= MIN_SIGNED) & d["imbalance"].notna() & d["net_rop_flat"].notna()
    ]
    d = d.assign(
        dec=pd.qcut(d["imbalance"].rank(method="first"), 10, labels=False),
        q=pd.qcut(d["imbalance"].rank(method="first"), 5, labels=False),
    )
    dec = d.groupby("dec")["net_rop_flat"].mean()
    rho = float(stats.spearmanr(dec.index, dec.values)[0])
    y, top, bot = d["net_rop_flat"].to_numpy(), (d["q"] == 4).to_numpy(), (d["q"] == 0).to_numpy()

    def tmb(i: np.ndarray) -> float:
        i = i.astype(int)
        return float(y[i][top[i]].mean() - y[i][bot[i]].mean())

    lo, hi = cluster_bootstrap_ci(
        np.arange(len(d), dtype=float), _keys(d), tmb, n_boot=N_BOOT, seed=SEED
    )
    im_rho = float(stats.spearmanr(d["imbalance"], d["implied_move"])[0])
    return {
        "n": len(d),
        "decile_spearman": rho,
        "top_minus_bottom": tmb(np.arange(len(d), dtype=float)),
        "tmb_ci_low": lo,
        "tmb_ci_high": hi,
        "spearman_imbalance_vs_implied_move": im_rho,
        "decile_means": [round(v, 4) for v in dec.values],
        "pass": rho >= 0.60 and lo > 0 and abs(im_rho) < 0.30,
    }


def score() -> None:
    ev = events()
    rows, missing, early = [], 0, 0
    for _, e in ev.iterrows():
        r = measure_event(e)
        if r is None:
            missing += 1
        elif r.get("early_close"):
            early += 1
        else:
            rows.append(r)
    print(
        f"  funnel: {len(ev)} events, measured {len(rows)}, early-close excluded {early}, "
        f"unmeasurable (not pulled or unquoted) {missing}"
    )
    if not rows:
        raise SystemExit("nothing measurable - refusing to report")
    marks = pd.DataFrame([m for r in rows for m in r.pop("_markouts")])
    d = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "events.csv", index=False)
    marks.to_csv(OUT / "markouts.csv", index=False)
    recon = reconcile(d)

    f1_rows: list[dict] = []
    for block, g in d.groupby("block"):
        f1_rows += f1(g, marks[marks["block"] == block] if len(marks) else marks, str(block))
    f1_tab = pd.DataFrame(f1_rows)
    f1_tab.to_csv(OUT / "f1.csv", index=False)
    print(f1_tab.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    verdict = f1_verdict(f1_tab)
    print(f"\n  F1 VERDICT by block: {verdict}")

    r2 = f2_discovery(d[d["block"] == "broad_2025_2026"])
    print(f"\n  F2 discovery (broad): {r2}")
    pd.DataFrame([{"test": "F2", **r2}]).to_csv(OUT / "f2.csv", index=False)
    pd.Series({"reconciliation": recon, "f1_verdict": verdict}).to_json(OUT / "verdict.json")
    print(f"  wrote {OUT.resolve()}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--cap", type=float, default=10.0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if args.pull:
        pull(args.cap, args.workers)
    if args.score:
        score()


if __name__ == "__main__":
    main()
