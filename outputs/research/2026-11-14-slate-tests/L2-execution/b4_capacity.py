"""
b4_capacity.py
L2 idea B4: capacity of the two passing entry levers, 1,779 (resting entry at the 15:00 mid) and
1,819 (tightest of three central strikes), at 1, 5, 10 and 25 contracts per leg against the
displayed top-of-book size. Declared in diagnosis.log entry [11].

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b4_capacity.py --lever 1819
    python outputs/research/2026-11-14-slate-tests/L2-execution/b4_capacity.py --lever 1779

Both closed studies are imported, never edited. Output: ``b4_<lever>.json``.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l2lib as L  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import EXECUTION_LEVERS as XL  # noqa: E402
from earnings_iv_crush.research.protocol import log_block_view  # noqa: E402

LANEB = L.ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt-2" / "laneB-contract-choice"
MAKER = L.ROOT / "research" / "execution" / "2026-11-13-maker-entry-confirmation" / "study.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def log_view(panel: str, period: str, family: str) -> None:
    log_block_view(
        L.BLOCKS_VIEWED,
        panel=panel,
        period=period,
        outcome_family="entry_execution",
        feature_family=family,
        viewed_by="L2-execution b4_capacity.py",
        kind="descriptive",
    )


def tick(price: float) -> float:
    return 0.01 if price < 3.0 else 0.05


def ladder_price(bid: float, size: float, n: int) -> float:
    """Average fill price of a marketable sell of ``n`` against ``size`` per level below ``bid``."""
    if n <= 0:
        return bid
    if not size >= 1:
        return float("nan")
    lv = np.floor(np.arange(n) / size) * XL.depth_beyond_book_ticks
    return float(bid - tick(bid) * lv.mean())


# ── 1,819 ────────────────────────────────────────────────────────────────────


def lever_1819() -> dict:
    sc = _load("laneB_score", LANEB / "score.py")
    d = sc.add_entry_night_hedge(sc.load())
    out: dict = {"lever": 1819}
    for blk, (y0, y1) in {"2013-18": (2013, 2018), "2019-24": (2019, 2024)}.items():
        b = d[(d["year"] >= y0) & (d["year"] <= y1)]
        elig = b["k0_ok"] & (b["km1_ok"] | b["kp1_ok"])
        e = b[elig].copy()
        choice = sc._pick(e, ["km1", "kp1"], "spr", "min")
        gain = pd.Series(0.0, index=e.index)
        for lab in ("km1", "kp1"):
            m = choice == lab
            gain[m] = e.loc[m, f"{lab}_gdn"]
        ref = L.mean_ci(gain, e["exit_date"])
        res: dict = {"n": len(e), "share_switched": float((choice != "k0").mean())}
        res["frozen_N1"] = L.iv_dict(ref)
        print(f"1819 {blk}: frozen gain reproduced {L.fmt(ref)}")
        for n in XL.depth_sizes:
            conc = {}
            for lab in ("k0", "km1", "kp1"):
                leg_bid = e[f"{lab}_bid"] / 2.0  # ATM legs: half the straddle bid
                lp = [
                    ladder_price(lb, q, n) if np.isfinite(lb) else np.nan
                    for lb, q in zip(leg_bid, e[f"{lab}_bid_sz"], strict=True)
                ]
                conc[lab] = 2.0 * (leg_bid - np.asarray(lp)) / e["m0"]  # per straddle-share
            extra = pd.Series(0.0, index=e.index)
            for lab in ("km1", "kp1"):
                m = choice == lab
                extra[m] = conc["k0"][m] - conc[lab][m]
            g = gain + extra
            ok = np.isfinite(g)
            res[f"N{n}"] = {
                "paired_gain": L.iv_dict(L.mean_ci(g[ok], e.loc[ok, "exit_date"])),
                "dropped_no_size": int((~ok).sum()),
                "book_concession_k0": L.iv_dict(
                    L.mean_ci(
                        -conc["k0"][np.isfinite(conc["k0"])],
                        e.loc[np.isfinite(conc["k0"]), "exit_date"],
                    )
                ),
                "share_k0_size_below_N": float((e["k0_bid_sz"] < n).mean()),
                "share_chosen_size_below_N": float(
                    np.mean([e.loc[i, f"{c}_bid_sz"] < n for i, c in choice.items()])
                ),
            }
            print(f"  N={n}: {L.fmt(L.mean_ci(g[ok], e.loc[ok, 'exit_date']))}")
        out[blk] = res
        log_view("laneB_arms", blk, "capacity_1819")
    return out


# ── 1,779 ────────────────────────────────────────────────────────────────────

_W: dict[str, Any] = {}


def _init() -> None:
    _W["st"] = _load("maker_confirmation_study", MAKER)


def _leg_sizes(leg: pd.DataFrame, day: pd.Timestamp) -> dict | None:
    st = _W["st"]
    f1 = st.f1
    t15, t1559 = st._at(day, 900), st._at(day, 959)
    q15, qx = f1._quote_at(leg, t15), f1._quote_at(leg, t1559)
    if q15 is None or qx is None:
        return None
    lim = f1._round_limit(sum(q15) / 2, "sell", st.SCHEDULE)
    w = leg[(leg["t"] >= t15) & (leg["t"] <= t1559)]
    v = float(w.loc[(w["action"] == "T") & (w["price"] > lim), "size"].sum())
    hit = w[w["bid_px_00"] >= lim]
    bsz = float(hit["bid_sz_00"].iloc[0]) if not hit.empty else 0.0
    xq = leg[(leg["t"] <= t1559) & (leg["bid_px_00"] > 0) & (leg["ask_px_00"] > leg["bid_px_00"])]
    qsz = float(xq["bid_sz_00"].iloc[-1])
    tf = f1._first_fill(leg, t15, t1559, lim, "sell", st.RULE)
    return {"lim": lim, "bid": qx[0], "v": v, "b": bsz, "q": qsz, "strict": tf is not None}


def _event_1779(e: dict) -> dict | None:
    st = _W["st"]
    path = st._path(pd.Series(e))
    if not path.exists():
        return None
    pre = st.f1._frame(path)
    if pre is None:
        return None
    day = pd.Timestamp(e["entry_date"]).normalize()
    if st.f1.is_early_close(day):
        return None
    legs = [_leg_sizes(pre[pre["right"] == r], day) for r in "CP"]
    if any(x is None for x in legs):
        return None
    m0 = float(e["m0"])
    out: dict = {"ticker": e["ticker"], "entry_date": day, "m0": m0}
    # N = 1 under the frozen rule, for reconciliation
    out["imp_frozen"] = sum((x["lim"] - x["bid"]) if x["strict"] else 0.0 for x in legs) / m0
    for n in XL.depth_sizes:
        imp = 0.0
        for x in legs:
            filled = min(n, x["v"] + x["b"])
            rest = ladder_price(x["bid"], x["q"], int(n - filled))
            base = ladder_price(x["bid"], x["q"], n)
            px = (filled * x["lim"] + (n - filled) * rest) / n if n > filled else x["lim"]
            imp += px - base
        out[f"imp_{n}"] = imp / m0
        out[f"fill_share_{n}"] = float(np.mean([min(n, x["v"] + x["b"]) / n for x in legs]))
        out[f"conc_{n}"] = sum(x["bid"] - ladder_price(x["bid"], x["q"], n) for x in legs) / m0
    return out


def lever_1779(workers: int) -> dict:
    _init()
    ev = _W["st"].load_events()
    jobs = [dict(r) for _, r in ev.iterrows()]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        res = [r for r in ex.map(_event_1779, jobs, chunksize=10) if r is not None]
    d = pd.DataFrame(res)
    print(f"1779: events measured {len(d)} of {len(jobs)}")
    dates = d["entry_date"]  # 1,779 clusters on the entry date
    out: dict = {"lever": 1779, "n": len(d)}
    out["frozen_N1"] = L.iv_dict(L.mean_ci(d["imp_frozen"], dates))
    print(f"  frozen rule reproduced: {L.fmt(L.mean_ci(d['imp_frozen'], dates))}")
    for n in XL.depth_sizes:
        ok = np.isfinite(d[f"imp_{n}"])
        out[f"N{n}"] = {
            "paired_improvement": L.iv_dict(L.mean_ci(d.loc[ok, f"imp_{n}"], dates[ok])),
            "dropped_no_size": int((~ok).sum()),
            "mean_fill_share": float(d[f"fill_share_{n}"].mean()),
            "book_concession_1559": L.iv_dict(L.mean_ci(-d.loc[ok, f"conc_{n}"], dates[ok])),
        }
        print(f"  N={n}: {out[f'N{n}']['paired_improvement']}")
    log_view("broad_entry_ticks", "2023-24", "capacity_1779")
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lever", required=True, choices=("1779", "1819"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    a = ap.parse_args(argv)
    res = lever_1819() if a.lever == "1819" else lever_1779(a.workers)
    L.write_json(L.HERE / f"b4_{a.lever}.json", res)
    print(f"wrote b4_{a.lever}.json")


if __name__ == "__main__":
    main()
