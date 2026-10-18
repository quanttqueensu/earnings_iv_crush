# Amendment 01 to the parity-spread pre-registration

Written before any signal, 15:59 price or outcome was computed.

The pre-registered outcome divides a dividend-adjusted yfinance close by a raw 15:59 IEX price. A
later dividend scales the adjusted close down, which would bias the outcome in a way correlated with
the signal's own dividend term. The outcome is therefore built in two pieces that each use a
consistent basis:

    ret = (1 + r_adj(close_t -> close_t+2)) * (close_raw_t / S_1559) - 1

where r_adj uses the P1 adjusted-close file and close_raw_t is yfinance's split-adjusted,
dividend-unadjusted close on the entry session. An event with |close_raw_t / S_1559 - 1| above 10%
is treated as a split or price-basis mismatch and dropped (funnel count). SPY is built the same
way. The parity forward uses the mean of K + (C - P) exp(r t) over the three strikes, as written.
Nothing else changes.
