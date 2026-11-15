# Narrow-spread events with large premiums carry more residual value than a matched random selection, on the forward paper book

| | |
|---|---|
| **Study** | `2026-11-07-forward-combined-gates` |
| **Line** | `selection` |
| **Owner** | `jordanodorico` |
| **Status** | planned |
| **Pre-registration** | [`prereg.md`](prereg.md), record `outputs/research/prereg_2026-11-07-forward-combined-gates.json` |

## Why it matters

Every liquidity-taking version of the earnings straddle has lost its premium to the bid-ask spread.
A gate that keeps rich premiums only where the spread is narrow would be the first selector built
around that failure rather than around premium size. The other side (conjecture, not tested here) is the option market maker who
quotes a wide spread on illiquid names to cover inventory risk; on narrow-spread names that cover is
thinner, so any surplus in the premium is more likely to reach the seller.

## Closest prior work and closed studies

Nearest closed rows in `docs/RESEARCH_STATE.md`: the term gate q=0.80 (does not carry forward), the
causal spread gate (megacap: no net premium left) and the broad 2025-26 spread gate (gated events
carried no gross premium), and the 375-strategy model zoo on 15:59 features (no selection skill),
which could in principle represent these interactions. Published: Goyal and Saretto (JFE 2009) sort
on the gap between implied and historical volatility; Gao, Xing and Zhang (JFQA 2018) on
pre-announcement implied volatility levels. This study differs in three ways: it intersects a premium
feature with the entry spread, it scores residual value rather than P&L, and its only block is the
forward book, which no earlier study has seen. The prior is low and the idea is crowded; the forward
block is what makes it a clean test.

## Changes

None.
