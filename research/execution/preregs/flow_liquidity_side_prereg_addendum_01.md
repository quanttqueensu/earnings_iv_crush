# Addendum 01 to the liquidity-side pre-registration (F1 measurement)

Dated 2026-10-14. Frozen while the data pull was in progress and before any F1 or F2 outcome was
computed or viewed. SHA-256 recorded in `outputs/research/prereg_flow_liquidity_side.json`. It tightens
how F1 is measured; F2 is unchanged.

## Why

An adversarial review of the original F1 design found three ways it could flatter the result: a
resting sell also fills when the bid rises to its price without a trade, and those are the most
adversely selected fills, which the original rule omitted; an unrounded mid is not an order that can
be sent; and comparing filled with unfilled events measures which events moved, not adverse selection.

## Changes

1. **Fill rules, both reported, both required for a pass.**
   - Strict (primary): a resting sell at limit `L` fills at the first moment either a trade on that
     leg prints strictly above `L`, or the NBBO bid reaches `L` or higher. A resting buy fills when a
     trade prints strictly below `L` or the NBBO ask reaches `L` or lower.
   - Optimistic: as strict, but a trade printing exactly at `L` also fills.
2. **Tick rounding.** Limits are rounded to a legal tick in the P&L-unfavourable direction (sells down,
   buys up) on the penny-program schedule (0.01 below 3.00, 0.05 at or above). The non-penny schedule
   (0.05 / 0.10) is reported as a sensitivity.
3. **Markouts replace the filled-versus-unfilled comparison.** For each filled leg, the leg mid at
   +1, +5 and +15 minutes after the fill and at 15:59, minus the fill price for sells (fill price minus
   later mid for buys, sign-adjusted so positive is favourable), reported relative to the half-spread at
   the fill.
4. **Entry and exit scored separately as well as together.** Arms: rest at entry only (cross the exit),
   rest at exit only (cross the entry), rest at both. The primary arm is both; the exit-only arm answers
   pivot P3 and carries no separate pass claim beyond its reported CI.
5. **Early-close sessions excluded** (entry or exit on a 13:00 close), counted in the funnel.
6. **Reconciliation before any paired result.** The always-cross book built from these ticks is
   compared event by event with the touch-basis return built from the cached 15:59 chains
   (`data/cache/backfill_chains`) for the broad block. If more than a quarter of events differ by more
   than 1% of margin, the run stops and the discrepancy is investigated before anything is reported.

## Go criteria (unchanged in spirit, now numeric)

Primary arm, in each block that has at least 100 measured events: paired improvement over always-
crossing at least +0.65% of margin, with a date-clustered 95% CI above zero under **both** fill rules;
mean 5-minute markout no worse than minus half of the half-spread captured; both legs filled on entry
in at least 30% of events. A block with fewer than 100 measured events is reported as underpowered,
not as a pass or fail. F2 criteria as in the original pre-registration.
