# Selection

What to trade: the P&L decomposition that diagnosed the term gate (reverse_alpha), forecasts of the realised move and the crush, own-history and peer-informed richness, the frozen ML predictor and the 15:59 model zoo, skew and parity signals for the stock reaction, earnings-date shifts, retail ownership, the strangle. All closed. The open thread is selection scored on residual value (docs/ROADMAP.md R1).

Closed studies here are frozen: their logic is not edited, so each recorded result reproduces. Import their helpers if useful, but start new work from `research/_template/` (see `research/README.md`). Run a study from the repository root, for example `python research/selection/research_clean_iv.py --help`.

Moved here from `scripts/` on 2026-10-18; a pre-registration or findings note that cites `scripts/<name>.py` or `_private/<name>.md` means the file of the same name in this folder.

## Code

| Module | What it does |
|---|---|
| `research_clean_iv.py` | Does the event-stripped ("clean") implied volatility forecast where post-event IV settles? |
| `research_crush_forecast.py` | Forecast the implied-volatility crush and sell the events where it is largest |
| `research_date_shift.py` | Pre-registered test: do earnings-date delays predict a worse short earnings straddle? |
| `research_final_earnings_set.py` | The final pre-registered test set for the single-name earnings straddle |
| `research_ml_nested.py` | Nested walk-forward: the model choice itself is made out of sample, so the final result carries no |
| `research_ml_ratio.py` | Pre-registered test: a frozen machine-learned predictor of realised over implied earnings move |
| `research_ml_ratio_confirm2.py` | Second, separately declared confirmation of the frozen ML ratio model on July-August 2026 events |
| `research_ml_zoo.py` | Walk-forward model zoo for earnings straddle selection: many model families, targets, parameters |
| `research_ml_zoo_1559.py` | Rebuild the broad-universe event features from the 15:59 ET consolidated quotes and re-run the |
| `research_ml_zoo_full.py` | The model zoo and the nested walk-forward on the full 15:59-quote event set, 2013-2026 |
| `research_name_persistence.py` | Test whether persistent name-level straddle richness is a tradeable selection |
| `research_name_persistence_exec.py` | Does a name's own prior event richness predict its next event, on executable marks? |
| `research_p1_skew_reaction.py` | P1: does the pre-announcement put skew predict the earnings-window stock return? |
| `research_p5_strangle.py` | Pre-registered test P5: short strangle at plus or minus one implied move against the straddle |
| `research_parity_spread.py` | Pre-registered test: does the option-implied forward premium predict the earnings-window return? |
| `research_realised_move.py` | Stage 1: forecast the realised earnings-announcement move out of sample on the |
| `research_retail_share.py` | T3 of the final earnings test set: retail ownership as the selector |
| `research_section21_peer.py` | Peer-informed selection scored on repricing, not size: the frozen section 2.1 test |
| `reverse_alpha_lib.py` | Shared scoring, inference and bookkeeping for the reverse-engineering programme |
| `reverse_alpha_p1.py` | Phase 1: map the whole profitable region, not just the cell that was chosen |
| `reverse_alpha_p2.py` | Phases 2 and 3: what the gate selects, and whether one economic variable replaces it |
| `reverse_alpha_p4.py` | Phases 4, 5, 7, 8 and 9 on the surviving candidate |
| `reverse_alpha_panel.py` | Build the one marked, feature-carrying event panel every reverse-engineering phase reads |
| `reverse_alpha_quotes.py` | Attach the real two-sided quotes for the contract each event actually trades |

## Pre-registrations

Frozen texts, verified byte for byte against `outputs/research/prereg_*.json` by `tests/test_preregistrations.py`. Never edit one; amend with a new dated file.

- [`date_shift_prereg.md`](preregs/date_shift_prereg.md)
- [`earnings_covariance_prereg.md`](preregs/earnings_covariance_prereg.md)
- [`earnings_covariance_prereg_amendment_01.md`](preregs/earnings_covariance_prereg_amendment_01.md)
- [`final_earnings_set_prereg.md`](preregs/final_earnings_set_prereg.md)
- [`ml_ratio_amendment_01.md`](preregs/ml_ratio_amendment_01.md)
- [`ml_ratio_confirm2_prereg.md`](preregs/ml_ratio_confirm2_prereg.md)
- [`ml_ratio_prereg.md`](preregs/ml_ratio_prereg.md)
- [`name_persistence_prereg.md`](preregs/name_persistence_prereg.md)
- [`name_persistence_prereg_amendment_01.md`](preregs/name_persistence_prereg_amendment_01.md)
- [`p1_skew_reaction_prereg.md`](preregs/p1_skew_reaction_prereg.md)
- [`p5_strangle_amendment_01.md`](preregs/p5_strangle_amendment_01.md)
- [`p5_strangle_prereg.md`](preregs/p5_strangle_prereg.md)
- [`parity_spread_amendment_01.md`](preregs/parity_spread_amendment_01.md)
- [`parity_spread_prereg.md`](preregs/parity_spread_prereg.md)
- [`season_state_prereg.md`](preregs/season_state_prereg.md)
- [`section21_peer_prereg.md`](preregs/section21_peer_prereg.md)

## Findings

- [`clean_iv.md`](findings/clean_iv.md): Event-cleaned implied volatility: construction, convergence, drivers, and the calendar
- [`crush_forecast.md`](findings/crush_forecast.md): Forecasting the crush: real skill, no monetisation
- [`date_shift.md`](findings/date_shift.md): Earnings-date shifts and the short earnings straddle
- [`dolthub_persistence_do_not_quote.md`](findings/dolthub_persistence_do_not_quote.md): Do not quote `dolthub_sp500_persistence.csv`
- [`final_earnings_set.md`](findings/final_earnings_set.md): The final earnings test set: all three fail, and the failures locate the premium
- [`forward_variance_reset.md`](findings/forward_variance_reset.md): Forward-variance reset: terminated at the measurement stage
- [`ml_ratio.md`](findings/ml_ratio.md): A frozen machine-learned predictor of realised over implied earnings move
- [`ml_ratio_confirm2.md`](findings/ml_ratio_confirm2.md): Second confirmation of the frozen ML ratio model: July-August 2026
- [`ml_zoo.md`](findings/ml_zoo.md): Walk-forward model zoo: the broad-universe edge was a data-source artefact
- [`p1_skew_reaction.md`](findings/p1_skew_reaction.md): P1: pre-announcement put skew and the earnings-window stock return
- [`p5_strangle.md`](findings/p5_strangle.md): P5: short strangle at plus or minus one implied move
- [`parity_spread.md`](findings/parity_spread.md): Option-implied forward premium and the earnings-window stock return
- [`reverse_alpha.md`](findings/reverse_alpha.md): Reverse-engineering the term gate: the profitable region is a jump-risk premium, not an inefficiency
- [`season_state_and_earnings_covariance.md`](findings/season_state_and_earnings_covariance.md): Pivot experiments: season state and earnings covariance
- [`section21_peer.md`](findings/section21_peer.md): Peer-informed selection scored on repricing: findings
- [`2026-11-13-alpha-hunt.md`](findings/2026-11-13-alpha-hunt.md): Alpha hunt, five lanes: no selector survives a held-out read (exploratory)
- [`2026-11-13-alpha-hunt-2.md`](findings/2026-11-13-alpha-hunt-2.md): Alpha hunt, round 2: ten lanes (exploratory)
- [`2026-11-14-idea-slate.md`](findings/2026-11-14-idea-slate.md): Idea slate: fifty candidates after the earnings-adjacent hunt, with test status
- [`2026-11-15-deep-learning.md`](findings/2026-11-15-deep-learning.md): Deep learning on the 15:59 chain: the surface adds nothing; the gain over L4 is its scale by tenor (exploratory)

Verdicts and key figures for every study are tabulated in [`docs/RESEARCH_STATE.md`](../../docs/RESEARCH_STATE.md).
