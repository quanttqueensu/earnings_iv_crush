# Addendum 02 to the flow and liquidity-side pre-registration

Written after the first scoring attempt returned no measurable event and before any outcome (fill,
P&L, markout or signed flow) was computed.

The exit-day tick window was pulled from 15:00:00 ET, and the scorer takes the resting limit from
the last valid quote at or before 15:00:00. No quote at or before 15:00:00 exists in an exit file
that begins at 15:00:00, so every event failed on its exit legs. The limit reference becomes: the
last valid quote at or before 15:00:00 if one exists, otherwise the first valid quote in
(15:00:00, 15:01:00]. The resting window, fill rules, crossing rule at 15:59:59, tick rounding,
markouts, reconciliation gate, go criteria and blocks are unchanged.
