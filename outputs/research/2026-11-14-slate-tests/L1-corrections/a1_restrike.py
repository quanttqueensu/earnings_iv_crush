"""
a1_restrike.py
A1: re-strike the 2025-26 out-of-sample ledger at the strike nearest the 15:59 parity forward and
re-score its three arms exactly as ``research/frozen_selector/score_oos_2026.py`` does.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L1-corrections/a1_restrike.py

The frozen scorer and ``earnings_iv_crush.research.chains`` call ``load_dotenv`` at import.
``.env`` is never read here: a no-op ``dotenv`` stub is placed in ``sys.modules`` before the
import, so the frozen logic (``_load_events``, ``_cached``, ``_straddle``, ``_mark``, ``_arm``,
``regt_straddle_margin``) is imported unedited and nothing reaches a vendor. The only change is
the spot handed to ``_straddle`` and to the margin: the 15:59 parity forward of the front expiry
on the cached entry chain, in place of the dividend-adjusted Yahoo close that put the strike
below the money. Writes ``oos_2026_ledger_restrike.csv``, ``a1_results.json``, ``a1.log``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # the frozen scorer's paths are relative to the repository root

sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=lambda *a, **k: False)  # type: ignore

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import N_BOOT, SEED, date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
FROZEN = ROOT / "research" / "frozen_selector" / "score_oos_2026.py"
LEDGER = ROOT / "outputs" / "research" / "oos_2026_ledger.csv"
OUT = HERE / "oos_2026_ledger_restrike.csv"

_spec = importlib.util.spec_from_file_location("score_oos_2026", FROZEN)
assert _spec is not None and _spec.loader is not None
so = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(so)
ch = sys.modules["earnings_iv_crush.research.chains"]


def parity_forward(chain: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """15:59 parity forward on the front expiry, the expiry ``_straddle`` sells."""
    d = ch._parse_chain(chain)
    if d is None or d.empty:
        return None
    exp = d["expiry"].min()
    q = hh.atm_quote(d, exp, pd.Timestamp(exp) - pd.Timedelta(days=1))
    return (q.fwd, exp) if q is not None else None


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def paired_sharpe_diff(a: np.ndarray, b: np.ndarray, keys: pd.Series) -> tuple[float, float, float]:
    """Sharpe(b) - Sharpe(a) on paired rows, percentile interval resampling whole dates."""
    k = pd.to_datetime(keys).dt.normalize().to_numpy()
    uniq, inv = np.unique(k, return_inverse=True)
    groups = [np.flatnonzero(inv == i) for i in range(uniq.size)]

    def sh(x: np.ndarray) -> float:
        return float(x.mean() / x.std(ddof=1))

    point = sh(b) - sh(a)
    rng = np.random.default_rng(SEED)
    draws = np.empty(N_BOOT)
    for j in range(N_BOOT):
        idx = np.concatenate([groups[i] for i in rng.integers(0, uniq.size, uniq.size)])
        draws[j] = sh(b[idx]) - sh(a[idx])
    return point, float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def _diff_ci(frame: pd.DataFrame, subset: pd.Index, col: str) -> tuple[float, float, float]:
    """Mean of ``col`` on ``subset`` minus the rest of ``frame``, date-clustered interval."""
    inside = frame.set_index(["ticker", "entry_date"]).index.isin(subset)
    return hh.top_minus_bottom_ci(frame[col].to_numpy(float), inside, ~inside, frame["entry_date"])


def rescore(ev: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """The frozen ``_score_rows`` loop with the parity forward as spot; funnel by reason."""
    reasons: Counter = Counter()
    rows, fwd_rows = [], []
    for _, e in ev.iterrows():
        tkr, d_in, d_out = str(e["ticker"]), e["entry_date"], e["exit_date"]
        ch_in = so._cached(tkr, d_in)
        if ch_in is None:
            reasons["no entry chain"] += 1
            continue
        pf = parity_forward(ch_in)
        if pf is None:
            reasons["no parity forward on the front expiry"] += 1
            continue
        f_in, _ = pf
        fwd_rows.append({"ticker": tkr, "entry_date": d_in, "fwd_entry": f_in})
        built = ch._straddle(ch_in, f_in)
        if built is None:
            reasons["entry chain unquoted at the money"] += 1
            continue
        straddle_in, implied_move, strike, expiry = built
        ch_out = so._cached(tkr, d_out)
        if ch_out is None:
            reasons["no exit chain"] += 1
            continue
        straddle_out = ch._mark(ch_out, strike, expiry)
        if straddle_out is None:
            reasons["exit leg unquoted at the sold strike"] += 1
            continue
        po = parity_forward(ch_out)
        f_out = po[0] if po is not None else np.nan
        credit = straddle_in * so.CONTRACT_MULTIPLIER
        exit_value = straddle_out * so.CONTRACT_MULTIPLIER
        margin = so.regt_straddle_margin(f_in, strike, straddle_in, 1)
        if margin <= 0:
            reasons["non-positive margin"] += 1
            continue
        cost = so.COST * credit
        rows.append(
            {
                "ticker": tkr,
                "announce_date": e["announce_date"],
                "entry_date": d_in,
                "exit_date": d_out,
                "strike": strike,
                "expiry": expiry,
                "spot_entry": f_in,
                "spot_exit": f_out,
                "straddle_entry": straddle_in,
                "straddle_exit": straddle_out,
                "implied_move": implied_move,
                "realised_move": abs(f_out / f_in - 1.0),
                "credit": credit,
                "exit_value": exit_value,
                "margin": margin,
                "cost": cost,
                "gross_rom": (credit - exit_value) / margin,
                "net_rom": (credit - exit_value - cost) / margin,
                "gross_rop": (credit - exit_value) / credit,
                "net_rop": (credit - exit_value - cost) / credit,
                "term_gate": bool(e["term_gate"]),
                "random_gate": bool(e["random_gate"]),
                "iv_term_spread": e["iv_term_spread"],
                "mark_source": "quote",
                "source": "restrike_parity_forward_1559",
                "lnFK": float(np.log(f_in / strike)),
            }
        )
    return pd.DataFrame(rows), dict(reasons), pd.DataFrame(fwd_rows)


def main() -> None:
    ev = so._load_events()
    print(
        f"block: {len(ev)} events; term gate {int(ev['term_gate'].sum())}, "
        f"random {int(ev['random_gate'].sum())}"
    )
    new, reasons, fwd = rescore(ev)
    print("funnel (re-strike):")
    print(f"  events considered {len(ev)}")
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  dropped, {k:<40} {v}")
    print(f"  scored {len(new)}")
    new.to_csv(OUT, index=False)

    old = pd.read_csv(LEDGER, parse_dates=["entry_date", "exit_date", "announce_date"])
    fwd = fwd.drop_duplicates(["ticker", "entry_date"])  # the frozen block lists two events twice
    old = old.merge(fwd, on=["ticker", "entry_date"], how="left", validate="many_to_one")
    old["lnFK"] = np.log(old["fwd_entry"] / old["strike"])
    res: dict = {"funnel_restrike": reasons, "n_old": int(len(old)), "n_new": int(len(new))}
    for lab, x in (("old", old), ("new", new)):
        v = x["lnFK"].dropna()
        iv = date_clustered_ci(v.to_numpy(float), x.loc[v.index, "entry_date"], _mean)
        res[f"lnFK_{lab}_bp"] = {
            "mean": 1e4 * iv.point,
            "low": 1e4 * iv.low,
            "high": 1e4 * iv.high,
            "median": float(1e4 * v.median()),
            "n": iv.n,
        }
    arms = {}
    for lab, x in (("old", old), ("new", new)):
        arms[lab] = [
            so._arm(x, "agent0_unconditional", None, 1),
            so._arm(x, "term_gate_q80_frozen", "term_gate", 1),
            so._arm(x, "random_gate_matched", "random_gate", 1),
        ]
    res["arms"] = arms
    # paired change on events in both ledgers
    res["duplicate_keys"] = {
        "old": int(old.duplicated(["ticker", "entry_date"]).sum()),
        "new": int(new.duplicated(["ticker", "entry_date"]).sum()),
        "events": int(ev.duplicated(["ticker", "entry_date"]).sum()),
    }
    k = ["ticker", "entry_date"]
    p = old.drop_duplicates(k).merge(
        new.drop_duplicates(k), on=k, suffixes=("_o", "_n"), validate="one_to_one"
    )
    res["paired_n"] = int(len(p))
    res["paired_same_strike"] = int((p["strike_o"] == p["strike_n"]).sum())
    for arm, mask in (
        ("unconditional", np.ones(len(p), bool)),
        ("term_gate", p["term_gate_o"].to_numpy(bool)),
        ("random_gate", p["random_gate_o"].to_numpy(bool)),
    ):
        q = p[mask]
        dm = date_clustered_ci(
            (q["net_rom_n"] - q["net_rom_o"]).to_numpy(float), q["entry_date"], _mean
        )
        sd = paired_sharpe_diff(
            q["net_rom_o"].to_numpy(float), q["net_rom_n"].to_numpy(float), q["entry_date"]
        )
        res[f"paired_{arm}"] = {
            "n": int(len(q)),
            "mean_net_rom_change": [dm.point, dm.low, dm.high],
            "sharpe_change": list(sd),
            "lnFK_old_bp": float(1e4 * q["lnFK_o"].mean()),
            "lnFK_new_bp": float(1e4 * q["lnFK_n"].mean()),
        }
    # attrition: events in the old ledger that the re-strike cannot score, on the old outcome
    lost = old.drop_duplicates(k).merge(new[k].drop_duplicates(), how="left", indicator=True)
    lost = lost[lost["_merge"] == "left_only"]
    res["lost_vs_old"] = {
        "n": int(len(lost)),
        "old_net_rom_lost_mean": float(lost["net_rom"].mean()) if len(lost) else None,
        "old_net_rom_paired_mean": float(p["net_rom_o"].mean()),
        "lost_diff_ci": list(_diff_ci(old.drop_duplicates(k), lost.set_index(k).index, "net_rom")),
    }
    gained = new.drop_duplicates(k).merge(old[k].drop_duplicates(), how="left", indicator=True)
    gained = gained[gained["_merge"] == "left_only"]
    res["gained_vs_old"] = {
        "n": int(len(gained)),
        "new_net_rom_gained_mean": float(gained["net_rom"].mean()) if len(gained) else None,
        "new_net_rom_paired_mean": float(p["net_rom_n"].mean()),
        "gained_diff_ci": list(
            _diff_ci(new.drop_duplicates(k), gained.set_index(k).index, "net_rom")
        ),
    }
    (HERE / "a1_results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
