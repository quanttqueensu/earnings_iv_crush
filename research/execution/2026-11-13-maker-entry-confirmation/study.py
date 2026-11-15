"""
study.py
Confirmation of the resting-entry lever on an unseen block: broad earnings events with entries from
2023-03-28 to 2024-12-31, where resting-order fills have never been measured.

Trial A (1,629) re-scores the rule frozen in prereg 53aa4898 exactly: rest each leg at the 15:00
mid (rounded down to a legal penny tick), sell what has not filled at the 15:59:00 bid. Trial B
(1,630) re-pegs each leg to the current mid every minute from 15:00 and sells what has not filled
at the 15:45:00 bid, against a plain cross at 15:45:00. Both arms of each trial take the same
position, so the event outcome cancels and the statistic is the entry price improvement alone.

Develop on sign-blinded improvements (the default); run ``--unblind`` once, after the pre-freeze
review says go and the freeze records this file (``docs/PROTOCOL.md`` P16 to P21).

Usage
-----
    python research/execution/2026-11-13-maker-entry-confirmation/study.py --price
    python research/execution/2026-11-13-maker-entry-confirmation/study.py --pull --cap 10
    python research/execution/2026-11-13-maker-entry-confirmation/study.py            # blind
    python research/execution/2026-11-13-maker-entry-confirmation/study.py --unblind  # real run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

import research.execution.research_flow_liquidity as f1  # noqa: E402
from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    date_clustered_pvalue,
    log_block_view,
    staged_scoring,
    verify_prereg,
)
from research.execution.research_fills_study import _straddle_symbols  # noqa: E402

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
LEDGER = ROOT / "research" / "ledger" / "blocks.csv"
EVENTS = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
CACHE = ROOT / "data" / "cache" / "flow" / "broad_2023_2024"
MANIFEST = CACHE / "manifest.json"
PULL_STATUS = CACHE / "pull_status.json"
# Frozen with the prereg: the fill logic is imported from these, so a change to them is a change
# to the scorer (review_pre item 6).
FROZEN_INPUTS = (
    EVENTS,
    ROOT / "research" / "execution" / "research_flow_liquidity.py",
    ROOT / "research" / "execution" / "research_fills_study.py",
)

# ── frozen parameters (each from prereg 53aa4898 or this study's prereg) ──
START, END = pd.Timestamp("2023-03-28"), pd.Timestamp("2024-12-31")  # cmbp-1 begins 2023-03-28
CONTRACT_COLS = ["ticker", "entry_date", "expiry", "status", "strike", "m0"]  # never outcomes
PULL_FROM, PULL_TO = "14:55", "16:00"  # a quote at or before 15:00 for the 15:00 mid
SCHEDULE, RULE = "penny", "strict"  # 53aa4898
PEG_FROM, PEG_TO = 15 * 60, 15 * 60 + 45  # trial B: re-peg each minute 15:00 to 15:44
BLOCKS = ("confirmation_2023_2024",)
T_MIN, ALPHA = 3.0, 0.05  # P20: t >= 3 and Benjamini-Hochberg at 5% across the slate
TRIALS = {"A": 1779, "B": 1780}  # amendment_01_renumber.md: were 1,629 and 1,630
PANEL, PERIOD, OUTCOME_FAMILY = "broad_entry_ticks", "2023-03-28..2024-12-31", "entry_execution"
FEATURE_FAMILY = {"A": "resting_static_mid", "B": "resting_pegged_mid"}


# ── events and data ──────────────────────────────────────────────────────────


def load_events() -> pd.DataFrame:
    """Contract and margin fields of every eligible event; outcome columns are never read."""
    d = pd.read_parquet(EVENTS, columns=CONTRACT_COLS)
    d["entry_date"] = pd.to_datetime(d["entry_date"])
    d["expiry"] = pd.to_datetime(d["expiry"])
    win = d[(d["entry_date"] >= START) & (d["entry_date"] <= END)]
    ok = win[win["status"] == "ok"].copy()
    print(f"funnel: window {len(win)}, hedged-hold status ok {len(ok)}")
    ok = ok.rename(columns={"strike": "strike_mkt", "expiry": "expiry_mkt"})
    return ok.reset_index(drop=True)


def _path(e: pd.Series) -> Path:
    return CACHE / f"{e['ticker']}_{pd.Timestamp(e['entry_date']).date()}_entry.parquet"


def _requests(ev: pd.DataFrame) -> list[dict[str, Any]]:
    out, no_symbols = [], 0
    for _, e in ev.iterrows():
        syms = _straddle_symbols(e)
        if not syms:
            no_symbols += 1
            continue
        day = pd.Timestamp(e["entry_date"])
        out.append(
            {
                "path": _path(e),
                "symbols": syms,
                "start": f1._utc(day, PULL_FROM),
                "end": f1._utc(day, PULL_TO),
            }
        )
    if no_symbols:
        print(f"funnel: {no_symbols} events with no contract symbols (not requested)")
    return out


def _iso(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def price() -> float:
    """Total cost of every request not yet cached, from the vendor's free cost call."""
    reqs = [r for r in _requests(load_events()) if not r["path"].exists()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        costs = list(
            pool.map(
                lambda r: dbo.get_cost(
                    r["symbols"], _iso(r["start"]), _iso(r["end"]), schema=f1.SCHEMA
                ),
                reqs,
            )
        )
    total = float(sum(costs))
    print(f"{len(reqs)} requests, estimated USD {total:.4f}")
    return total


def pull(cap: float, workers: int = 8) -> None:
    """Pull every uncached request, pricing each first and halting before the cap."""
    reqs = [r for r in _requests(load_events()) if not r["path"].exists()]
    lock, halted = threading.Lock(), threading.Event()
    state: dict[str, Any] = {"spent": 0.0, "done": 0, "fail": 0, "failed": []}
    print(f"{len(reqs)} to pull, cap USD {cap:.2f}", flush=True)

    def one(r: dict[str, Any]) -> None:
        if halted.is_set():
            return
        s, e = _iso(r["start"]), _iso(r["end"])
        try:
            c = float(dbo.get_cost(r["symbols"], s, e, schema=f1.SCHEMA))
            with lock:
                if state["spent"] + c > cap:
                    halted.set()
                    return
                state["spent"] += c
            df = dbo._get_df(f1.SCHEMA, r["symbols"], s, e, stype_in="raw_symbol")
            df = df if df is not None else pd.DataFrame()
            f1._verify(df, r["start"], r["end"])
            r["path"].parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(r["path"])
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - counted and printed, never treated as empty
            with lock:
                state["fail"] += 1
                state["failed"].append(r["path"].name)
                if state["fail"] <= 5:
                    print(f"  failed {r['path'].name}: {exc!r}"[:200], flush=True)
        with lock:
            state["done"] += 1
            if state["done"] % 200 == 0:
                print(f"  {state['done']}/{len(reqs)}, spent USD {state['spent']:.4f}", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, reqs))
    tag = "HALTED AT CAP" if halted.is_set() else "PULL DONE"
    print(
        f"{tag}: spent USD {state['spent']:.4f}, {state['fail']} failed, "
        f"{(time.time() - t0) / 60:.1f} min"
    )
    files = sorted(CACHE.glob("*_entry.parquet"))
    MANIFEST.write_text(
        json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, indent=0)
    )
    print(f"manifest of {len(files)} files written")
    PULL_STATUS.write_text(
        json.dumps(
            {
                "halted_at_cap": halted.is_set(),
                "spent_usd": state["spent"],
                "requested": len(reqs),
                "failed": state["failed"],
            },
            indent=1,
        )
    )
    if halted.is_set() or state["fail"]:
        print("pull incomplete: rerun --pull for the missing files before scoring")


def _check_manifest() -> None:
    """The tick files scored are the files pulled; a changed or added file stops the run.

    A pull that halted at the cap or left failed requests is refused outright, so a partial
    block can never be scored as if it were whole.
    """
    if not MANIFEST.exists() or not PULL_STATUS.exists():
        raise SystemExit("no tick manifest or pull status: pull first")
    status = json.loads(PULL_STATUS.read_text())
    if status["halted_at_cap"] or status["failed"]:
        raise SystemExit(f"last pull incomplete: {status}")
    man = json.loads(MANIFEST.read_text())
    files = {p.name for p in CACHE.glob("*_entry.parquet")}
    if files != set(man):
        raise SystemExit("tick files differ from the manifest")
    for name, sha in man.items():
        if hashlib.sha256((CACHE / name).read_bytes()).hexdigest() != sha:
            raise SystemExit(f"{name} changed since the pull")


# ── fills ────────────────────────────────────────────────────────────────────


def _at(day: pd.Timestamp, minutes: int, seconds: int = 0) -> pd.Timestamp:
    return (day + pd.Timedelta(minutes=minutes, seconds=seconds)).tz_localize(f1.TZ)


def _quote_fill(leg: pd.DataFrame, t0, t1, limit: float):
    """Conservative rule: a resting sell fills only when the NBBO bid reaches its limit."""
    w = leg[(leg["t"] >= t0) & (leg["t"] <= t1) & (leg["bid_px_00"] >= limit)]
    return None if w.empty else w["t"].iloc[0]


def _fill(leg: pd.DataFrame, t0, t1, limit: float, rule: str):
    if rule == "quote_only":
        return _quote_fill(leg, t0, t1, limit)
    return f1._first_fill(leg, t0, t1, limit, "sell", rule)


def _print_outside_nbbo(leg: pd.DataFrame, t: pd.Timestamp, limit: float) -> bool:
    """Whether the strict fill at ``t`` came from a trade printed above the prevailing ask."""
    rows = leg[(leg["t"] == t) & (leg["action"] == "T") & (leg["price"] > limit)]
    if rows.empty:
        return False  # triggered by the bid reaching the limit, not by a print
    q = f1._quote_at(leg[leg["t"] < t], t)
    return q is not None and float(rows["price"].iloc[0]) > q[1]


def _filled_leg(limit: float, qx: tuple[float, float]) -> dict[str, float]:
    """Improvement of one filled leg, split into drift and half-spread (review_pre, recommended).

    ``limit - bid = (limit - mid) + (mid - bid)``: the second term is the half-spread a taker
    would have paid at the baseline time, the first is how the leg's mid moved against the limit.
    """
    mid = (qx[0] + qx[1]) / 2
    return {"improve": limit - qx[0], "drift": limit - mid, "half": mid - qx[0]}


def trial_a(leg: pd.DataFrame, day: pd.Timestamp) -> dict[str, Any] | None:
    """Rule 53aa4898: 15:00 mid, rounded down; unfilled legs sell at the 15:59:00 bid."""
    t15, t1559 = _at(day, 900), _at(day, 959)
    q15, qx = f1._quote_at(leg, t15), f1._quote_at(leg, t1559)
    if q15 is None or qx is None:
        return None
    limit = f1._round_limit(sum(q15) / 2, "sell", SCHEDULE)
    tf = f1._first_fill(leg, t15, t1559, limit, "sell", RULE)
    tq = _quote_fill(leg, t15, t1559, limit)
    parts = (
        _filled_leg(limit, qx) if tf is not None else {"improve": 0.0, "drift": 0.0, "half": 0.0}
    )
    return {
        **parts,
        "improve_quote_only": (limit - qx[0]) if tq is not None else 0.0,
        "filled": tf is not None,
        "outside": tf is not None and _print_outside_nbbo(leg, tf, limit),
        "mid15": sum(q15) / 2,
    }


def trial_b(leg: pd.DataFrame, day: pd.Timestamp) -> dict[str, Any] | None:
    """Re-peg to the current mid each minute 15:00 to 15:44; unfilled sell at the 15:45:00 bid."""
    t1545 = _at(day, PEG_TO)
    qx = f1._quote_at(leg, t1545)
    if qx is None or f1._quote_at(leg, _at(day, PEG_FROM)) is None:
        return None
    out: dict[str, Any] = {
        "improve": 0.0,
        "drift": 0.0,
        "half": 0.0,
        "improve_quote_only": 0.0,
        "filled": False,
    }
    limit = np.nan
    done = {"strict": False, "quote_only": False}
    for m in range(PEG_FROM, PEG_TO):
        # Half-open minute [m:00, m+1:00): the last nanosecond is excluded so no record is
        # tested in two minutes and none after second 59 is skipped (review_pre item 3).
        t0, t1 = _at(day, m), _at(day, m + 1) - pd.Timedelta(nanoseconds=1)
        q = f1._quote_at(leg, t0)
        if q is not None:
            limit = f1._round_limit(sum(q) / 2, "sell", SCHEDULE)
        if not np.isfinite(limit):
            continue
        if not done["strict"] and _fill(leg, t0, t1, limit, "strict") is not None:
            done["strict"] = True
            out.update(_filled_leg(limit, qx))
        if not done["quote_only"] and _fill(leg, t0, t1, limit, "quote_only") is not None:
            done["quote_only"] = True
            out["improve_quote_only"] = limit - qx[0]
        if done["strict"] and done["quote_only"]:
            break
    out["filled"] = done["strict"]
    return out


def _trial_fields(k: str, legs: list[dict[str, Any]], m0: float) -> dict[str, Any]:
    return {
        k: sum(x["improve"] for x in legs) / m0,
        f"{k}_quote_only": sum(x["improve_quote_only"] for x in legs) / m0,
        f"{k}_drift": sum(x["drift"] for x in legs) / m0,
        f"{k}_half": sum(x["half"] for x in legs) / m0,
        f"{k}_legs_filled": sum(x["filled"] for x in legs),
    }


def measure(ev: pd.DataFrame) -> pd.DataFrame:
    """Per-event improvement of each trial, in units of m0, with a funnel per trial.

    Each trial has its own eligibility (review_pre item 2): an event missing a 15:45 quote is
    dropped from trial B only, and one missing a 15:59 quote from trial A only. An ineligible
    trial's columns are NaN and that trial is scored on its own events.
    """
    rows: list[dict[str, Any]] = []
    funnel: dict[str, Counter[str]] = {"common": Counter(), "A": Counter(), "B": Counter()}
    for _, e in ev.iterrows():
        path = _path(e)
        if not path.exists():
            funnel["common"]["no_tick_file"] += 1
            continue
        pre = f1._frame(path)
        if pre is None:
            funnel["common"]["empty_tick_file"] += 1
            continue
        day = pd.Timestamp(e["entry_date"]).normalize()
        if f1.is_early_close(day):
            funnel["common"]["early_close"] += 1
            continue
        legs = {r: pre[pre["right"] == r] for r in "CP"}
        m0 = float(e["m0"])
        row: dict[str, Any] = {"ticker": e["ticker"], "entry_date": day}
        for k, fn in (("A", trial_a), ("B", trial_b)):
            res = [fn(legs[r], day) for r in "CP"]
            if any(x is None for x in res):
                funnel[k]["leg_unquoted"] += 1
                row[k] = np.nan
                continue
            funnel[k]["ok"] += 1
            row.update(_trial_fields(k, res, m0))  # type: ignore[arg-type]
            if k == "A":
                row["A_fills_outside_nbbo"] = sum(x["outside"] for x in res)  # type: ignore[index]
                c_mid, p_mid = (x["mid15"] for x in res)  # type: ignore[index]
                row["parity_offset"] = abs(c_mid - p_mid) / m0
        rows.append(row)
    print("funnel:", {k: dict(v) for k, v in funnel.items()})
    if not rows:
        raise SystemExit("no event survived the funnel")
    return pd.DataFrame(rows)


# ── scoring ──────────────────────────────────────────────────────────────────


def cluster_t(x: np.ndarray, dates: pd.Series) -> float:
    """Mean over its date-clustered (CR1) standard error."""
    keys = pd.to_datetime(dates).dt.normalize().to_numpy()
    dev = pd.Series(x - x.mean()).groupby(keys).sum().to_numpy()
    g = dev.size
    se = np.sqrt(g / (g - 1) * np.sum(dev**2)) / x.size
    return float(x.mean() / se)


def sign_blind(d: pd.DataFrame, cols: list[str], seed: int = 0) -> pd.DataFrame:
    """Flip every value of a date by one random sign: keeps the clustering, hides the mean."""
    rng = np.random.default_rng(seed)
    keys = d["entry_date"].dt.normalize()
    sign = pd.Series(rng.choice([-1.0, 1.0], size=keys.nunique()), index=keys.unique())
    s = keys.map(sign).to_numpy()
    return d.assign(**{c: d[c].to_numpy() * s for c in cols})


def score_trial(d: pd.DataFrame, col: str, *, unblind: bool) -> dict[str, Any]:
    """Primary statistic for one trial on its own eligible events.

    Blind runs report only the primary on sign-flipped values. Fill rates, the fill audit and
    the decomposition are withheld until the real run, because fill rate times half-spread
    approximates the answer (review_pre item 4).
    """
    s = d[d[col].notna()]
    x = s[col].to_numpy(float)
    ci = date_clustered_ci(x, s["entry_date"], np.mean)
    p = date_clustered_pvalue(x, s["entry_date"], np.mean)
    t = cluster_t(x, s["entry_date"])
    print(
        f"{col}: N {x.size}, mean {ci.point:+.5f} [{ci.low:+.5f}, {ci.high:+.5f}] of m0, "
        f"t {t:.2f}, p {p:.4g}"
    )
    out: dict[str, Any] = {
        "n": int(x.size),
        "dates": int(s["entry_date"].nunique()),
        "mean": [ci.point, ci.low, ci.high],
        "t": t,
        "p": p,
        "p_normal": float(2 * norm.sf(abs(t))),
    }
    if not unblind:
        return out
    qo = date_clustered_ci(s[f"{col}_quote_only"].to_numpy(float), s["entry_date"], np.mean)
    out.update(
        {
            "quote_only_mean": [qo.point, qo.low, qo.high],
            "drift_mean": float(s[f"{col}_drift"].mean()),
            "half_spread_mean": float(s[f"{col}_half"].mean()),
            "both_legs_filled": float((s[f"{col}_legs_filled"] == 2).mean()),
            "any_leg_filled": float((s[f"{col}_legs_filled"] >= 1).mean()),
        }
    )
    if col == "A":
        terc = pd.qcut(s["parity_offset"], 3, labels=["low", "mid", "high"])
        out["by_parity_offset_tercile"] = s.groupby(terc, observed=True)[col].mean().to_dict()
        out["fill_audit"] = {
            "strict_leg_fills": int(s["A_legs_filled"].sum()),
            "fill_from_print_above_ask": int(s["A_fills_outside_nbbo"].sum()),
        }
    return out


def bh_pass(ps: dict[str, float], alpha: float = ALPHA) -> dict[str, bool]:
    """Benjamini-Hochberg at ``alpha`` across the slate's p-values."""
    order = sorted(ps, key=ps.get)  # type: ignore[arg-type]
    m, k_max = len(order), 0
    for k, name in enumerate(order, start=1):
        if ps[name] <= alpha * k / m:
            k_max = k
    return {name: (i < k_max) for i, name in enumerate(order)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--price", action="store_true", help="vendor cost estimate only")
    ap.add_argument("--pull", action="store_true", help="pull the ticks under --cap")
    ap.add_argument("--cap", type=float, default=None, help="hard cap in USD for --pull")
    ap.add_argument("--unblind", action="store_true", help="the one real run")
    ap.add_argument("--rerun-reason", default=None, help="required for a second real run")
    args = ap.parse_args(argv)
    if args.price:
        price()
        return
    if args.pull:
        if args.cap is None:
            raise SystemExit("--pull needs --cap")
        verify_prereg(PREREG, RECORD)
        pull(args.cap)
        return

    sha = verify_prereg(PREREG, RECORD, unblind=args.unblind, rerun_reason=args.rerun_reason)
    print(
        f"pre-registration verified, sha256 {sha[:12]}; {'UNBLINDED' if args.unblind else 'blind'}"
    )
    _check_manifest()
    d = measure(load_events())
    if not args.unblind:
        d = sign_blind(d, [f"{k}{s}" for k in "AB" for s in ("", "_quote_only", "_drift", "_half")])

    res: dict[str, Any] = {"n_events": int(len(d))}
    for k in ("A", "B"):

        def one(_block: str, k: str = k) -> dict[str, Any]:
            return score_trial(d, k, unblind=args.unblind)

        res[k] = staged_scoring(BLOCKS, one, lambda r: True)
    ps = {k: res[k]["blocks"][BLOCKS[0]]["p"] for k in ("A", "B")}
    bh = bh_pass(ps)
    for k in ("A", "B"):
        r = res[k]["blocks"][BLOCKS[0]]
        r["bh_pass"] = bh[k]
        r["passes"] = bool(r["mean"][1] > 0 and r["t"] >= T_MIN and bh[k])
        res[k]["trial"] = TRIALS[k]
        res[k]["verdict"] = "PASS" if r["passes"] else "FAIL"
        print(f"trial {TRIALS[k]} ({k}): {res[k]['verdict']}")
    if args.unblind:
        for k in ("A", "B"):
            r = res[k]["blocks"][BLOCKS[0]]
            print(k, {x: r[x] for x in r if x not in ("mean", "t", "p", "p_normal", "n", "dates")})
        for k in ("A", "B"):
            log_block_view(
                LEDGER,
                panel=PANEL,
                period=PERIOD,
                outcome_family=OUTCOME_FAMILY,
                feature_family=FEATURE_FAMILY[k],
                viewed_by=f"trial {TRIALS[k]} ({HERE.name})",
            )
        OUT.mkdir(parents=True, exist_ok=True)
        d.to_parquet(OUT / "events.parquet")
        (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float))
        print(f"written {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
