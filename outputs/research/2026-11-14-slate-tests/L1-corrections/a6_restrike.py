"""
a6_restrike.py
A6: re-strike the 53aa4898 resting-entry panel at the strike nearest the 15:59 parity forward,
re-score its lever where that is possible, and trace the contract source of the 1,779 and 1,780
confirmation.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L1-corrections/a6_restrike.py

Inputs, all read-only: the 53aa4898 panel
(``outputs/research/2026-11-02-maker-entry-hedged-hold/events.parquet``), its tick files
(``data/cache/flow/broad_2025_2026/*_pre.parquet``), the 15:59 backfill chains
(``data/cache/backfill_chains/``), ``base_corrected.parquet`` and the 2023-24 confirmation's
contract list and tick files. ``.env`` is never read: ``chains`` is imported behind a no-op
``dotenv`` stub, and nothing is fetched.

The lever (``improve``, the 15:00 resting limit minus the 15:59:00 bid, in m0) is measured on
tick files that hold only the two contracts at the ledger strike, so it can be re-scored only on
events where the ledger strike already is the strike nearest the forward. The hedged hold at the
forward strike is ``base_corrected``'s ``H_net``. Writes ``a6_results.json`` and
``a6_events.parquet``.
"""

from __future__ import annotations

import json
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *a, **k: False))  # type: ignore[arg-type]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci, per_trade_sharpe  # noqa: E402

HERE = Path(__file__).resolve().parent
P53 = ROOT / "outputs" / "research" / "2026-11-02-maker-entry-hedged-hold" / "events.parquet"
FLOW25 = ROOT / "data" / "cache" / "flow" / "broad_2025_2026"
FLOW23 = ROOT / "data" / "cache" / "flow" / "broad_2023_2024"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
BASE = HERE / "base_corrected.parquet"
CONF_EVENTS = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
CONF_OUT = ROOT / "outputs" / "research" / "2026-11-13-maker-entry-confirmation" / "events.parquet"
CONF_START, CONF_END = pd.Timestamp("2023-03-28"), pd.Timestamp("2024-12-31")


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _ci(x: pd.Series, dates: pd.Series, stat=_mean) -> list[float]:  # noqa: ANN001
    ok = x.notna()
    iv = date_clustered_ci(x[ok].to_numpy(float), dates[ok], stat)
    return [iv.point, iv.low, iv.high, iv.n]


def _tick_strikes(path: Path) -> set[float]:
    s = pd.read_parquet(path, columns=["symbol"])["symbol"].astype(str).unique()
    return {float(x.replace(" ", "")[-8:]) / 1000.0 for x in s}


def _forward_strike(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> tuple | None:
    p = CHAINS / f"{ticker}_{day.date()}.parquet"
    if not p.exists():
        return None
    d = _parse_chain(pd.read_parquet(p).reset_index())
    if d is None or d.empty:
        return None
    q = hh.atm_quote(d, expiry, day)
    return None if q is None else (q.fwd, q.strike, q.bid)


def restrike_53() -> dict:
    d = pd.read_parquet(P53)
    for c in ("entry_date", "exit_date", "expiry"):
        d[c] = pd.to_datetime(d[c])
    funnel: Counter = Counter()
    rows = []
    for _, e in d.iterrows():
        r = {"ticker": e["ticker"], "entry_date": e["entry_date"]}
        tick = FLOW25 / f"{e['ticker']}_{e['entry_date'].date()}_pre.parquet"
        r["tick_strikes"] = sorted(_tick_strikes(tick)) if tick.exists() else []
        fs = _forward_strike(e["ticker"], e["entry_date"], e["expiry"])
        if fs is None:
            funnel["no backfill chain or no two-sided pair on the expiry"] += 1
            rows.append({**r, "rs_status": "no_chain"})
            continue
        funnel["re-struck"] += 1
        rows.append({**r, "rs_status": "ok", "fwd": fs[0], "k_new": fs[1], "bid_new": fs[2]})
    rs = pd.DataFrame(rows).drop_duplicates(["ticker", "entry_date"])
    dup = int(d.duplicated(["ticker", "entry_date"]).sum())
    print(f"panel rows {len(d)}, duplicated keys {dup} (kept, as the frozen panel scored them)")
    d = d.merge(rs, on=["ticker", "entry_date"], how="left", validate="many_to_one")
    b = pd.read_parquet(BASE, columns=["ticker", "entry_date", "strike", "H_net", "H_corr"])
    b["entry_date"] = pd.to_datetime(b["entry_date"])
    d = d.merge(b, on=["ticker", "entry_date"], how="left", suffixes=("", "_base"))
    d["tick_is_ledger_strike"] = [
        bool(t) and all(np.isclose(x, k) for x in t)
        for t, k in zip(d["tick_strikes"], d["strike"], strict=True)
    ]
    d["lnFK_old"] = np.log(d["fwd"] / d["strike"])
    d["lnFK_new"] = np.log(d["fwd"] / d["k_new"])
    d["same_strike"] = np.isclose(d["strike"], d["k_new"])
    d["base_strike_is_new"] = np.isclose(d["strike_base"], d["k_new"])
    ok = d["rs_status"].eq("ok")
    same = ok & d["same_strike"]
    moved = ok & ~d["same_strike"]
    res: dict = {
        "n_panel": int(len(d)),
        "duplicated_keys": dup,
        "funnel": dict(funnel),
        "tick_files_hold_only_the_ledger_strike": int(d["tick_is_ledger_strike"].sum()),
        "lnFK_old_bp": [1e4 * v for v in _ci(d.loc[ok, "lnFK_old"], d.loc[ok, "exit_date"])[:3]]
        + [int(ok.sum())],
        "lnFK_new_bp": [1e4 * v for v in _ci(d.loc[ok, "lnFK_new"], d.loc[ok, "exit_date"])[:3]]
        + [int(ok.sum())],
        "n_same_strike": int(same.sum()),
        "n_moved": int(moved.sum()),
        "base_corrected_strike_equals_new": [
            int((ok & d["base_strike_is_new"]).sum()),
            int((ok & d["strike_base"].notna()).sum()),
        ],
        "base_H_net_available": int((ok & d["H_net"].notna()).sum()),
        # the lever as stored (all events, at the ledger strike), and where it can be re-scored
        "improve_stored_all": _ci(d["improve"], d["exit_date"]),
        "improve_same_strike": _ci(d.loc[same, "improve"], d.loc[same, "exit_date"]),
        "improve_moved_strike": _ci(d.loc[moved, "improve"], d.loc[moved, "exit_date"]),
        "improve_moved_minus_same": list(
            hh.top_minus_bottom_ci(d["improve"].to_numpy(float), moved, same, d["exit_date"])
        ),
        "H_stored_moved_minus_same": list(
            hh.top_minus_bottom_ci(d["H"].to_numpy(float), moved, same, d["exit_date"])
        ),
        "fill_rate_both_legs_same_moved": [
            float((d.loc[same, "legs_filled"] == 2).mean()),
            float((d.loc[moved, "legs_filled"] == 2).mean()),
        ],
    }
    hn = ok & d["H_net"].notna()
    res["H_net_forward_strike_all"] = _ci(d.loc[hn, "H_net"], d.loc[hn, "exit_date"])
    res["H_stored_ledger_strike_same_events"] = _ci(d.loc[hn, "H"], d.loc[hn, "exit_date"])
    hs = same & d["H_net"].notna()
    hm = d.loc[hs, "H_net"] + d.loc[hs, "improve"]
    res["HM_net_same_strike_mean"] = _ci(hm, d.loc[hs, "exit_date"])
    res["HM_net_same_strike_sharpe"] = _ci(hm, d.loc[hs, "exit_date"], per_trade_sharpe)
    res["H_net_same_strike_sharpe"] = _ci(
        d.loc[hs, "H_net"], d.loc[hs, "exit_date"], per_trade_sharpe
    )
    res["improve_by_lnFK_old_tercile"] = {
        str(k): [float(v.mean()), int(len(v))]
        for k, v in d.loc[ok, "improve"].groupby(pd.qcut(d.loc[ok, "lnFK_old"].abs(), 3))
    }
    d.drop(columns=["tick_strikes"]).to_parquet(HERE / "a6_events.parquet")
    return res


def confirmation_source() -> dict:
    """Contract source of 1,779 and 1,780: the strike in the CRSP-era hedged-event-hold panel."""
    ev = pd.read_parquet(CONF_EVENTS, columns=["ticker", "entry_date", "status", "strike"])
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    win = ev[(ev["entry_date"] >= CONF_START) & (ev["entry_date"] <= CONF_END)]
    win = win[win["status"] == "ok"]
    out = pd.read_parquet(CONF_OUT, columns=["ticker", "entry_date"])
    out["entry_date"] = pd.to_datetime(out["entry_date"])
    j = out.merge(win, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    match, missing, n_files = 0, 0, 0
    for _, e in j.iterrows():
        p = FLOW23 / f"{e['ticker']}_{e['entry_date'].date()}_entry.parquet"
        if not p.exists():
            missing += 1
            continue
        n_files += 1
        ks = _tick_strikes(p)
        match += int(bool(ks) and all(np.isclose(x, e["strike"]) for x in ks))
    b = pd.read_parquet(BASE, columns=["ticker", "entry_date", "lnFK", "strike"])
    b["entry_date"] = pd.to_datetime(b["entry_date"])
    m = j.merge(b, on=["ticker", "entry_date"], how="left", suffixes=("", "_base"))
    return {
        "n_scored_events": int(len(j)),
        "contract_list": str(CONF_EVENTS.relative_to(ROOT)),
        "window_ok_events": int(len(win)),
        "tick_files_present": n_files,
        "tick_files_missing": missing,
        "tick_files_whose_strike_is_the_panel_strike": match,
        "panel_strike_equals_base_corrected_strike": int(
            np.isclose(m["strike"], m["strike_base"]).sum()
        ),
        "lnFK_bp_mean_median_absmean": [
            float(1e4 * m["lnFK"].mean()),
            float(1e4 * m["lnFK"].median()),
            float(1e4 * m["lnFK"].abs().mean()),
            int(m["lnFK"].notna().sum()),
        ],
    }


def main() -> None:
    res = {"panel_53aa4898": restrike_53(), "confirmation_1779_1780": confirmation_source()}
    (HERE / "a6_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
