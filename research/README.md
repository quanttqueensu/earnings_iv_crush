# Research

How the team tests an idea. Read [`docs/RESEARCH_STATE.md`](../docs/RESEARCH_STATE.md) first:
most ideas that sound new have been tested, and the closed list says with what result. The rules
every study follows are [`docs/PROTOCOL.md`](../docs/PROTOCOL.md).

## Layout

| Folder | What is in it |
|---|---|
| `frozen_selector/` | The term-structure selector, its verdicts and the attrition audit |
| `execution/` | Fills, measured costs, spread gates, the liquidity-provider study |
| `timing/` | Holding to expiry, conditional holds, post-event and pre-event trades |
| `selection/` | The P&L decomposition, forecasts, peer and ML selectors, stock-reaction signals |
| `off_earnings/` | The same signals away from earnings; macro-release trades; PEAD |
| `other_markets/` | Deribit and Kalshi |
| `_template/` | Copy this to start a study |

Each line's README lists its code, pre-registrations and findings. Closed studies are frozen:
their code is not edited, so every recorded number reproduces. Shared infrastructure they use
lives in the package (`earnings_iv_crush/research/`), and new work imports it rather than
copying a closed study.

## Starting a study

1. **Check the closed list** in `docs/RESEARCH_STATE.md` and say in your card how your idea
   differs from the nearest closed one and from the closest published work.
2. **Claim it** on [`docs/ROADMAP.md`](../docs/ROADMAP.md) in a pull request, or add a row.
3. **Copy the template** to `research/<line>/<YYYY-MM-DD-short-slug>/`.
4. **Write the pre-registration** (`prereg.md`): hypothesis, mechanism, data and blocks, the
   primary statistic, the success criterion and the kill criterion. Commit it, then freeze it
   before touching any outcome:
   ```bash
   python -c "from earnings_iv_crush.research.protocol import freeze_prereg as f; f('research/<line>/<slug>/prereg.md', 'outputs/research/prereg_<slug>.json', trial_id='<slug>', n_trials_declared=1, declared_utc='YYYY-MM-DD')"
   ```
   Commit the record (`outputs/research/prereg_*.json` is tracked) and add the trial to
   `docs/RESEARCH_STATE.md` in the same commit. In Claude Code, `/prereg` walks through this.
5. **Write the scorer** (`study.py`). It calls `verify_prereg` first, scores through the package
   (`engine.pnl.build_trade`, `research.protocol.date_clustered_ci`,
   `research.protocol.matched_random_null`), prints an attrition funnel, and writes its outputs
   under `outputs/research/<slug>/`.
6. **Run it once** on the declared blocks. Every run is a trial.
7. **Write `findings.md` yourself**, in your own words: hypothesis, scope and criteria first, then
   the result with N, the interval and the basis of every number, the funnel, the matched-null
   comparison and the verdict against the pre-registered criterion.
8. **Record it**: update `docs/RESEARCH_STATE.md` and the roadmap row in the same pull request.

A study that passes moves toward the forward book only through a decision record in
`docs/decisions/` and a pre-registered forward test; it never goes straight to the paper account.

## Rules

- Import package code, never copy it, so a passing result tests the code that would trade.
- Every parameter is a named constant at the top of `study.py` with its rationale.
- Raw licensed rows never go in a findings note or a commit (`docs/DATA.md`).
- Holdouts are touched once. A block whose outcomes were viewed is declared as viewed.
