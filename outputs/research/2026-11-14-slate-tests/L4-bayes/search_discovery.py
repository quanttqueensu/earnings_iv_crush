"""
search_discovery.py
Lane L4 iteration round: staged search of model class, likelihood, target transform, features,
discounting, shrinkage and hierarchy on 2013-18 only, scored by rolling-origin mean log
predictive density over the discovery years 2015 to 2018 (see ``l4iter``).

Every configuration scored is appended to ``search_log.csv`` as it finishes, so an interrupted
search resumes where it stopped and the count beside the champion is the count of rows. The
feature model and the no-feature baseline (intercept and name effect only) are searched as two
classes; each is tuned on its own, which is the conservative comparison. Only 2013-18 events
are passed to the model, so no later outcome is computed on.

Stages, each starting from the best configuration so far in its class:
  1 likelihood and target: Gaussian or Student-t (nu 30, 10, 6, 4, 3), on y with a premium-share
    variance weight (none, power 1, 2, 3) or on the Yeo-Johnson loss ratio (power 0 to 1,
    weight none or premium share power 1);
  2 dynamics and shrinkage: coefficient discount 1 to 0.95, coefficient prior scale 3e-4 to
    0.1, declared or wide feature set; then the variance discount;
  3 hierarchy: name prior scale 0 to 0.1, industry level (two-digit SIC or SIC division) with
    prior scale 0 to 0.03 (the baseline keeps the declared intercept-and-name form);
  4 polish: the likelihood grid again at the stage-3 point.

The expected-value rule's Monte Carlo is switched off here (``ev_draws`` 1): it does not enter
the log score, and the frozen configuration restores the declared 2,000 draws.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/search_discovery.py --target H_corr
    python outputs/research/2026-11-14-slate-tests/L4-bayes/search_discovery.py --target residual_value
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4iter  # noqa: E402
import l4lib  # noqa: E402

from earnings_iv_crush.config import OnlineBayesConfig  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402
from earnings_iv_crush.research.protocol import log_block_view  # noqa: E402

LOG = HERE / "search_log.csv"
BLOCK = "2013-18"
TIE = 1e-4  # ties within this go to the configuration logged first
INF = float("inf")
NU_GRID = (INF, 30.0, 10.0, 6.0, 4.0, 3.0)
PLAIN_WEIGHTS = (
    ("none", 2.0),
    ("premium_share", 1.0),
    ("premium_share", 2.0),
    ("premium_share", 3.0),
)
YJ_POWERS = (0.0, 0.15, 0.25, 0.35, 0.5, 0.75, 1.0)
YJ_WEIGHTS = (("none", 2.0), ("premium_share", 1.0))
DISCOUNTS = (1.0, 0.998, 0.995, 0.99, 0.98, 0.95)
COEF_SCALES = (0.0003, 0.001, 0.003, 0.01, 0.03, 0.1)
VAR_DISCOUNTS = (1.0, 0.998, 0.99)
NAME_SCALES = (0.0, 0.001, 0.003, 0.01, 0.03, 0.1)
GROUP_SCALES = (0.001, 0.003, 0.01, 0.03)
WIDE_CLIP = 5.0
FIELDS = [
    "row",
    "target",
    "stage",
    "kind",
    "group_level",
    "discount",
    "variance_discount",
    "coef_prior_scale",
    "name_prior_scale",
    "group_prior_scale",
    "variance_weight",
    "variance_power",
    "obs_df",
    "target_transform",
    "yj_power",
    "feature_set",
    "z_clip",
    "mean_log_score",
    "ls_2015",
    "ls_2016",
    "ls_2017",
    "ls_2018",
    "coverage90",
    "pit_lo5",
    "pit_hi5",
    "n_decide",
    "n",
    "seconds",
    "utc",
]
SEARCHED = [f for f in FIELDS[5:17]]


def _key(target: str, kind: str, cfg: OnlineBayesConfig, level: str) -> str:
    c = asdict(cfg)
    return json.dumps([target, kind, level] + [str(c[f]) for f in SEARCHED])


class Search:
    """One target's staged search, resumable from ``search_log.csv``."""

    def __init__(self, target: str) -> None:
        self.target = target
        d_all = l4iter.load_all()
        self.d = d_all[d_all["block"] == BLOCK].reset_index(drop=True)
        print(f"[search] {self.target}: discovery events {len(self.d)}; later blocks not passed")
        self.D = l4iter.Design(self.d)
        self.base = replace(OnlineBayesConfig(), ev_draws=1)
        self.y = l4lib.target(self.d, target, self.base)
        self.mask = l4iter.discovery_mask(self.d, self.D.usable, self.y)
        print(f"[search] scored events (entry 2015-18, usable, outcome) {int(self.mask.sum())}")
        self.done: dict[str, dict[str, Any]] = {}
        self.rows = 0
        if LOG.exists():
            with LOG.open(encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    self.rows += 1
                    cfg = self._cfg_from_row(r)
                    self.done[_key(r["target"], r["kind"], cfg, r["group_level"])] = r
        print(f"[search] {self.rows} configurations already logged")

    @staticmethod
    def _cfg_from_row(r: dict[str, str]) -> OnlineBayesConfig:
        kw: dict[str, Any] = {}
        for f in SEARCHED:
            v = r[f]
            kw[f] = v if f in ("variance_weight", "target_transform", "feature_set") else float(v)
        return replace(OnlineBayesConfig(), ev_draws=1, **kw)

    def score(self, stage: str, kind: str, cfg: OnlineBayesConfig, level: str = "none") -> float:
        k = _key(self.target, kind, cfg, level)
        if k in self.done:
            return float(self.done[k]["mean_log_score"])
        t0 = time.time()
        run = self.D.run(cfg, self.y, with_features=(kind == "model"), group_level=level)
        s = l4iter.score(run, self.d, self.mask)
        row = {
            "row": self.rows + 1,
            "target": self.target,
            "stage": stage,
            "kind": kind,
            "group_level": level,
            **{f: asdict(cfg)[f] for f in SEARCHED},
            **{f: s[f] for f in FIELDS[17:27]},
            "seconds": round(time.time() - t0, 2),
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        new = not LOG.exists()
        with LOG.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
        self.rows += 1
        self.done[k] = {kk: str(vv) for kk, vv in row.items()}
        print(
            f"  {self.rows:4d} {stage:<10} {kind:<8} {level:<7} ls {s['mean_log_score']:+.4f} "
            f"cov {s['coverage90']:.3f} tails {s['pit_lo5']:.3f}/{s['pit_hi5']:.3f} "
            f"{_short(cfg)}"
        )
        return s["mean_log_score"]

    def best(
        self, cands: list[tuple[OnlineBayesConfig, str]], stage: str, kind: str
    ) -> tuple[OnlineBayesConfig, str, float]:
        scores = [self.score(stage, kind, c, lv) for c, lv in cands]
        top = max(scores)
        i = next(j for j, s in enumerate(scores) if s >= top - TIE)
        return cands[i][0], cands[i][1], scores[i]


def _short(cfg: OnlineBayesConfig) -> str:
    return (
        f"nu={cfg.obs_df:g} tr={cfg.target_transform}:{cfg.yj_power:g} "
        f"w={cfg.variance_weight}^{cfg.variance_power:g} disc={cfg.discount:g}/"
        f"{cfg.variance_discount:g} g={cfg.coef_prior_scale:g} ku={cfg.name_prior_scale:g} "
        f"kg={cfg.group_prior_scale:g} fs={cfg.feature_set}"
    )


def _likelihood_grid(c: OnlineBayesConfig, allow_transform: bool) -> list[OnlineBayesConfig]:
    out = [
        replace(c, obs_df=nu, target_transform="none", yj_power=1.0, variance_weight=w,
                variance_power=pw)  # fmt: skip
        for w, pw in PLAIN_WEIGHTS
        for nu in NU_GRID
    ]
    if allow_transform:
        out += [
            replace(c, obs_df=nu, target_transform="yj_loss", yj_power=k, variance_weight=w,
                    variance_power=pw)  # fmt: skip
            for k in YJ_POWERS
            for w, pw in YJ_WEIGHTS
            for nu in NU_GRID
        ]
    return out


def run_class(s: Search, kind: str, allow_transform: bool) -> tuple[OnlineBayesConfig, str, float]:
    c0 = replace(s.base, discount=1.0, coef_prior_scale=0.01, name_prior_scale=0.01)
    lv = "none"
    # Stage 1: likelihood and target.
    c, lv, sc = s.best([(x, lv) for x in _likelihood_grid(c0, allow_transform)], "1-lik", kind)
    # Stage 2: dynamics and shrinkage.
    if kind == "model":
        cands = [
            (replace(c, discount=dd, coef_prior_scale=g, feature_set=fs,
                     z_clip=WIDE_CLIP if fs == "wide" else INF), lv)  # fmt: skip
            for fs in ("declared", "wide")
            for dd in DISCOUNTS
            for g in COEF_SCALES
        ]
    else:
        cands = [(replace(c, discount=dd), lv) for dd in DISCOUNTS]
    c, lv, sc = s.best(cands, "2-dyn", kind)
    c, lv, sc = s.best(
        [(replace(c, variance_discount=vd), lv) for vd in VAR_DISCOUNTS], "2-var", kind
    )
    # Stage 3: hierarchy.
    cands = [(replace(c, name_prior_scale=u, group_prior_scale=0.0), "none") for u in NAME_SCALES]
    if kind == "model":
        cands += [
            (replace(c, name_prior_scale=u, group_prior_scale=g), level)
            for level in ("sic2", "sic_div")
            for u in NAME_SCALES
            for g in GROUP_SCALES
        ]
    c, lv, sc = s.best(cands, "3-hier", kind)
    # Stage 4: the likelihood grid again at this point.
    c, lv, sc = s.best([(x, lv) for x in _likelihood_grid(c, allow_transform)], "4-polish", kind)
    print(f"[search] {s.target} {kind} best {sc:+.5f} {_short(c)} level={lv}")
    return c, lv, sc


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=list(l4lib.TARGETS), required=True)
    args = ap.parse_args(argv)
    fam = "hedged_hold_H_corr" if args.target == "H_corr" else "residual_value"
    log_block_view(
        l4lib.BLOCKS_VIEWED,
        panel="base_corrected",
        period=BLOCK,
        outcome_family=fam,
        feature_family="online_bayes_iteration_round_1",
        viewed_by="L4 search_discovery (rolling origin 2015-18)",
        kind="trial",
    )
    s = Search(args.target)
    # The loss-ratio transform needs an outcome bounded near the premium; residual value is not.
    allow = args.target == "H_corr"
    model = run_class(s, "model", allow)
    base = run_class(s, "baseline", allow)
    out = {
        "target": args.target,
        "model": {**ob.describe_config(model[0]), "group_level": model[1], "score": model[2]},
        "baseline": {**ob.describe_config(base[0]), "group_level": base[1], "score": base[2]},
        "rows_logged_total": s.rows,
    }
    dest = HERE / f"search_best_{args.target}.json"
    dest.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"written {dest.name}; search_log.csv holds {s.rows} rows")


if __name__ == "__main__":
    main()
