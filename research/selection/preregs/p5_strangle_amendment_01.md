# Amendment 01 to the P5 strangle pre-registration

Written before any outcome was computed. The ledger's `net_rom` charges a modelled cost basis
(average measured spreads), while the strangle is priced at each event's own touch. Pairing the two
would mix cost conventions. Criterion (ii) therefore compares the strangle with the same event's
straddle (the ledger's strike and expiry) priced identically: sold at the entry bids, bought back at
the exit asks, USD 0.65 per contract per leg each way, Reg-T margin 0.2 S + premium. The paired
difference against the ledger `net_rom` is reported as secondary. Nothing else changes.
