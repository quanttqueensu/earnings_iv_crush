# Lanes

Each lane is a starting point: follow the evidence, but stay inside your idea so lanes do not
duplicate each other. Seeds marked "recalled" are leads to verify at the source.

## E1 gamma-scalp

Long gamma after the crush. On the reaction session the straddle has already crushed, but the
stock often keeps discovering its price for hours and days. Test buying the front ATM straddle
on the reaction session (at a time the data supports, e.g. 10:00 or later, at the ask) and
delta-hedging it intraday at a fixed frequency or on fixed price bands, closing at a pre-declared
horizon (reaction-session close, D+2, D+5). The question is whether realised variance sampled
intraday exceeds the post-crush implied enough to pay both option touches and the hedging cost.
Mechanism to check: intraday mean reversion (negative autocorrelation) raises the scalper's take
above close-to-close variance. Closest closed work: alpha hunt 2 lane C (post-event diffusive
premium, close-to-close, about zero net of hedging) and lane A (post-announcement decisions on the
short); the post-announcement straddle held to expiry. Say how intraday hedging and the long side
differ. Also test, briefly, the mirror: whether the short hedged hold earns more or less when
hedged intraday rather than at closes. Recalled leads: Muravyev and Ni (2020) day-night option
returns; Bakshi and Kapadia (2003) delta-hedged gains; Patton and Verardo (2012) on post-earnings
beta and volatility; the realised-variance literature on sampling frequency and microstructure
noise (Bandi and Russell; Zhang, Mykland and Ait-Sahalia). Stock intraday prices: find them in the
caches (option-implied parity, flow files, alpaca 1-minute) before considering anything else.

## E2 informed-flow

Pre-event option order flow as a directional signal, traded in the stock (cheap touch), not in
volatility. Options carry information before earnings: signed volume, the option-to-stock volume
ratio, call minus put volume, out-of-the-money put buying, aggressor-signed premium. Use the
`flow/*_pre.parquet` files to build signals at a decision time strictly before the 15:59 entry,
and score the next-session stock return (close to close and close to open) net of the stock
half-spread, against random direction and against a matched null. Closest closed work: P1 put
skew predicts the reaction (wrong sign), the parity-forward premium (no effect), demand pressure
F2 (a volatility test, not direction). Say how flow differs from skew and parity. Recalled leads:
Pan and Poteshman (2006, RFS); Johnson and So (2012, JFE) O/S ratio; Roll, Schwartz and
Subrahmanyam (2010); Jin, Livnat and Zhang (2012); Augustin, Brenner and Subrahmanyam on informed
options trading; Muravyev (2016) order flow and option prices. Also report whether the signal
improves the short straddle's residual value (as a selector, against the random null).

## E3 spillover

Information transfer to names that are not reporting. When a bellwether reports (first in its
industry, or a mega-cap supplier or customer), peers' stocks move overnight, but peers' options
may not price that night as an event. Test whether non-reporting peers' straddles (or sector ETF
straddles) bought at the bellwether's 15:59 and sold at the next 15:59 earn more than matched
ordinary nights, and the directional version: does the bellwether's reaction predict the peer's
next-session return net of the stock touch. Closest closed work: section 2.1 peer-informed
selection (which events to sell), lane5 "early in industry" (a selector), earnings covariance,
and lane G (QQQ on mega-cap nights, priced fairly). Say how buying peer variance and the peer
directional trade differ. First establish data feasibility: which chains exist for a peer on
another name's event night (DoltHub sampled chains have the lookback and rotating-expiry
landmines; index_chains covers SPY, QQQ and IWM only). Recalled leads: Foster (1981); Thomas and
Zhang (2008) on overreaction to intra-industry transfers; Hann, Kim and Zheng (2019) on intra-
industry information transfers; Cohen and Frazzini (2008) on customer-supplier links. Industry
classification: use what the project already has (SIC from the WRDS calendar).

## E4 expiry-mechanics

Option-market mechanics on the calendar the project already trades. (a) Pinning and dealer gamma
on the post-earnings expiry: the hedged hold settles on the Friday expiry after the report; do
closes pin to high open-interest strikes, and does choosing the strike (or strangle wings)
relative to open-interest peaks change hold-to-expiry P&L under `HEDGED_NET`, causally? (b)
Ex-dividend early exercise: holders of in-the-money calls who fail to exercise before an
ex-dividend date hand value to writers; is a writer's edge reachable at the touch for a small
account at IB, or is it a market-maker trade only? Closest closed work: alpha hunt 2 lane B
(contract choice, tightest strike, strangle wings) and the netting correction (trial 1,856). Say
how open-interest-based choice differs from spread-based choice. Recalled leads: Ni, Pearson and
Poteshman (2005, JFE) on stock-price clustering at expiry; Golez and Jackwerth (2012) on pinning
in S&P futures; Avellaneda and Lipkin (2003) on a pinning model; Pool, Stoll and Whaley (2008) and
Hao, Kalay and Mayhew (2010, RFS) on failure to exercise before ex-dividend; Jensen and Pedersen
(2016) on early exercise. Check whether the chains carry open interest and whether CRSP
distributions (via the R2 mirror) give ex-dividend dates.

## E5 literature-and-practice

A systematic map of documented return sources attached to earnings events or to the equity option
market's own calendar that are not on the closed list: gamma scalping evidence, earnings-week
weekly and daily-expiry options on single names (daily expiries on mega-caps, if listed), retail
lottery demand into earnings, dealer positioning and hedging flows, post-earnings implied-vol
drift, conference-call and guidance timing, the earnings-date announcement itself, analyst-day and
investor-day events, index inclusion and rebalancing, and anything else the literature supports.
For each: the paper, sample, effect size, whether costs at the touch were measured, the closest
closed study here, and whether the project's caches can test it at zero cost. Where a zero-cost
screen is possible in under an hour, run it (declared first, trial numbers from your block) and
report it as exploratory. Start `evidence.md` early; the other lanes may cite it. Finish with a
ranked list of the five most promising ideas not already closed, each with the cheapest test.
