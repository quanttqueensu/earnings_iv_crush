"""
b10_fees.py
L2 idea B10: fee arithmetic. Re-price the option commission of every event under IBKR Pro Fixed
and Tiered (taking, or resting for a maker rebate), and price the stock-hedge commission that
H_corr omits, under Fixed and Tiered, with IB's 1%-of-trade-value cap. Declared in diagnosis.log
entries [3] and [5]; the cap, the single-plan headline and the sell-fee bound follow the lane
review (entry [22]).

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b10_fees.py --block 2013-18
    python outputs/research/2026-11-14-slate-tests/L2-execution/b10_fees.py --commission-file

The straddle is sent as one combo order of 2N contracts (so the per-order minimum applies once);
each hedge rebalance and the expiry residual is one stock order (``l2fees.stock_commission``).
Exercise and assignment carry no commission (recalled). The headline adds one plan, Tiered, to
both the stock and the option side; it never picks the cheaper plan per event, since an account
is on one plan. SEC Section 31 and FINRA TAF are not charged; their size is bounded and reported.

Outputs: ``b10_<block>.json``; with ``--commission-file``, ``hedge_commission.parquet``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l2fees as F  # noqa: E402
import l2lib as L  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import EXECUTION_LEVERS as XL  # noqa: E402
from earnings_iv_crush.config import HEDGED_NET  # noqa: E402

COMMISSION_FILE = L.HERE / "hedge_commission.parquet"
COMMISSION_DOC = (
    "hedge_commission.parquet: per-event IBKR Pro Tiered stock-hedge commission that H_corr omits. "
    "Keys ticker, entry_date (one row per base_corrected event with h_status ok). "
    "n_hedge_orders: stock orders at 1 contract (nonzero rebalances at the hedging closes plus "
    "the netted expiry residual; 0 for unhedged holds). comm_1c, comm_5c: commission as a "
    "fraction of m0 (same basis as H_corr, so H_corr minus comm is net of it) for 1 and 5 "
    "straddles, positive numbers to subtract. Assumptions: one marketable order per nonzero "
    "rebalance rounded to whole shares; USD 0.0035 per share, minimum USD 0.35, maximum 1% of "
    "trade value, plus USD 0.003 per share exchange take fee and USD 0.0002 clearing; no "
    "commission on exercise or assignment; SEC Section 31 and FINRA TAF not included. The IB "
    "Tiered figures are recalled, not verified (IB pages refuse automated clients). Source "
    "script L2-execution/b10_fees.py."
)


def option_fee(schedule: str, contracts: int) -> float:
    """USD per straddle-share for the entry combo of ``contracts`` straddles."""
    legs = 2 * contracts
    if schedule == "current":
        usd = legs * HEDGED_NET.fee_per_contract_leg
    elif schedule == "fixed":
        usd = max(legs * XL.option_fixed_per_contract, XL.option_min_per_order)
    else:
        comm = max(legs * XL.option_tiered_per_contract, XL.option_min_per_order)
        pass_through = legs * (XL.option_clearing_per_contract + XL.option_regulatory_per_contract)
        venue = {
            "tiered_take_c1": XL.option_customer_take_fee,
            "tiered_take_maker_taker": XL.option_maker_taker_take_fee,
            "tiered_rest_rebate": -XL.option_maker_rebate,
        }[schedule]
        usd = comm + pass_through + legs * venue
    return usd / (100.0 * contracts)


OPTION_SCHEDULES = ("fixed", "tiered_take_c1", "tiered_take_maker_taker", "tiered_rest_rebate")


def event_rows(d: pd.DataFrame) -> pd.DataFrame:
    """One row per event: stock commission by plan and size, orders, cap hits, sell-fee bound."""
    paths = L.load_paths()
    rows = []
    for _, r in d.iterrows():
        kw = paths[(r["ticker"], r["entry_date"])]["kw"]
        row = {
            "ticker": r["ticker"],
            "entry_date": r["entry_date"],
            "m0": r["m0"],
            "date": r["exit_date"],
            "c_fees": r["c_fees"],
            "H": r["H_corr"],
        }
        if kw is None:
            # Unhedged hold: no stock order exists, so every stock charge is exactly zero.
            for nc in XL.commission_contract_sizes:
                for s in ("fixed", "tiered"):
                    row[f"stock_{s}_{nc}"] = 0.0
                    row[f"capped_{s}_{nc}"] = 0
                row[f"orders_{nc}"] = 0
            row["sell_fee_bound"] = XL.sec_fee_rate_bound * float(r["c_premium"] * r["m0"])
            rows.append(row)
            continue
        h, t = L.hedge_sequence(kw)
        px = F.order_prices(kw)
        for nc in XL.commission_contract_sizes:
            for s in ("fixed", "tiered"):
                usd, n_ord, n_cap = F.stock_commission(t, px, nc, s)
                row[f"stock_{s}_{nc}"] = usd
                row[f"capped_{s}_{nc}"] = n_cap
            row[f"orders_{nc}"] = n_ord
        row["sell_fee_bound"] = F.sell_fee_bound(kw, h, float(kw["sale_price"]))
        rows.append(row)
    e = pd.DataFrame(rows)
    e["date"] = pd.to_datetime(e["date"])
    return e


def write_commission_file() -> None:
    """Write ``hedge_commission.parquet`` for every block (descriptive cost, no outcome read)."""
    d = L.load_base()
    d = d[d["h_status"] == "ok"].reset_index(drop=True)
    e = event_rows(d)
    out = pd.DataFrame(
        {
            "ticker": e["ticker"],
            "entry_date": e["entry_date"],
            "n_hedge_orders": e["orders_1"].astype(int),
            "comm_1c": e["stock_tiered_1"] / e["m0"],
            "comm_5c": e["stock_tiered_5"] / e["m0"],
        }
    )
    if (
        out[["comm_1c", "comm_5c"]].isna().any().any()
        or out.duplicated(["ticker", "entry_date"]).any()
    ):
        raise AssertionError("hedge_commission has NaN or duplicate keys")
    tmp = COMMISSION_FILE.with_suffix(".tmp")
    out.attrs["doc"] = COMMISSION_DOC
    out.to_parquet(tmp, index=False)
    tmp.replace(COMMISSION_FILE)
    (L.HERE / "hedge_commission.README.txt").write_text(COMMISSION_DOC + "\n", newline="\n")
    print(
        f"funnel: base ok {len(d)}; written {len(out)}; hedged (orders > 0) {(out.n_hedge_orders > 0).sum()}"
    )
    print(out.groupby(d["block"])[["n_hedge_orders", "comm_1c", "comm_5c"]].mean())


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--block", choices=L.BLOCKS)
    ap.add_argument("--commission-file", action="store_true")
    a = ap.parse_args(argv)
    if a.commission_file:
        write_commission_file()
        return
    if a.block is None:
        ap.error("--block or --commission-file is required")
    d = L.load_base()
    d = d[(d["block"] == a.block) & (d["h_status"] == "ok")].reset_index(drop=True)
    e = event_rows(d)
    m0, dates = e["m0"].to_numpy(), e["date"]
    cur = option_fee("current", 1)
    if not np.allclose(-cur / m0, e["c_fees"].to_numpy(), rtol=1e-12, atol=1e-15):
        raise AssertionError("current option fee does not reproduce c_fees")
    res: dict = {"block": a.block, "n_events": len(e)}
    res["c_fees"] = L.iv_dict(L.mean_ci(e["c_fees"], dates))
    res["sell_fee_bound_not_charged"] = L.iv_dict(L.mean_ci(-e["sell_fee_bound"] / m0, dates))
    for nc in XL.commission_contract_sizes:
        hedged = e[f"orders_{nc}"] > 0
        res[f"mean_stock_orders_per_event_N{nc}"] = float(e[f"orders_{nc}"].mean())
        for s in OPTION_SCHEDULES:
            dh = (cur - option_fee(s, nc)) / m0
            res[f"option_{s}_N{nc}"] = L.iv_dict(L.mean_ci(dh, dates))
        for s in ("fixed", "tiered"):
            res[f"stock_{s}_N{nc}"] = L.iv_dict(L.mean_ci(-e[f"stock_{s}_{nc}"] / m0, dates))
            res[f"cap_binding_share_of_orders_{s}_N{nc}"] = float(
                e[f"capped_{s}_{nc}"].sum() / max(int(e[f"orders_{nc}"].sum()), 1)
            )
            res[f"cap_binding_events_{s}_N{nc}"] = int((e[f"capped_{s}_{nc}"] > 0).sum())
        res[f"hedged_events_N{nc}"] = int(hedged.sum())
        h_all = (
            e["H"] - e[f"stock_tiered_{nc}"] / m0 + (cur - option_fee("tiered_take_c1", nc)) / m0
        )
        res[f"H_corr_plus_tiered_N{nc}"] = L.iv_dict(L.mean_ci(h_all, dates))
        print(
            f"{a.block} N={nc}: stock tiered {L.fmt(L.mean_ci(-e[f'stock_tiered_{nc}'] / m0, dates))}"
        )
    res["H_corr"] = L.iv_dict(L.mean_ci(e["H"], dates))
    L.write_json(L.HERE / f"b10_{a.block}.json", res)
    L.record_view(a.block, "execution_fee_schedule", "L2-execution b10_fees.py", kind="descriptive")
    for k, v in res.items():
        print(k, v)


if __name__ == "__main__":
    main()
