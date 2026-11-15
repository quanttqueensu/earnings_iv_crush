# Niche hunt: scheduled-event volatility beyond US single-name earnings

Twenty lanes, run in parallel. Each lane reads this brief, then its own section in `LANES.md`.

## Objective

Find a premium that a trader can harvest net of costs at the touch, in a market the team can
paper trade at Interactive Brokers, with historical data the team can obtain at zero cost (free,
already on disk, or scrapable within the rules below). The template is the project's own trade:
sell implied volatility into a scheduled information event and let it crush. Variants are in
scope: buying under-priced event variance, selling the event through a different vehicle, or a
closely related scheduled-event premium. A lane succeeds if it delivers either a tested candidate
with real-data evidence, or a precise, sourced case for why its market is or is not worth a
metered data pull, with the pull priced.

## What the project already knows (read before anything else)

- `docs/RESEARCH_STATE.md` section 2 lists closed directions, including "Away from earnings, and
  other markets": DoltHub SPY macro straddles (not testable, N=5), index VRP timing, Deribit BTC
  macro events (ordinary variance premium, no event surplus), Kalshi tails and maker, India and
  Brazil, and the 2026-11-13 hunts (index options on mega-cap earnings nights, FDA committees and
  product events). Do not re-run a closed test; a new angle must say how it differs.
- `docs/REFERENCES.md` and `CLAUDE.local.md` name the core literature (Dubinsky et al. 2019; Gao,
  Xing and Zhang 2018; Alexiou et al. 2025; Goyal and Saretto 2009).
- `outputs/research/2026-11-13-alpha-hunt-2/SUMMARY.md` explains the core failure on equities:
  the event premium is positive at the mid and the spread at the touch eats it. Any market you
  propose must clear that bar: name the half-spread as a share of premium, and say why it is
  smaller there or why the premium is larger.

## Stages, in order

1. **Prior work.** Search the academic literature (SSRN, NBER, journal sites, Google Scholar,
   arXiv q-fin, central-bank and exchange research, agricultural-economics journals) and
   practitioner sources (exchange white papers, CME and Cboe research notes, desk commentary).
   Name the closest paper, its sample, its effect size and whether it measured costs. Say plainly
   if the idea is crowded. Peer-reviewed beats blogs.
2. **Mechanism.** Who pays the premium, why it persists, and when the information arrives
   relative to the trading session. An event released while the market is closed (like earnings
   after the close) behaves differently from one released mid-session.
3. **Tradability at IB.** Exact product (exchange, root, expiry cycle including weeklies and
   short-dated contracts), trading hours against the event time, whether IB offers it on a paper
   account, the market-data subscription needed (without one, IB quotes are about fifteen minutes
   late and fills on them are not evidence), commissions, and margin (SPAN or Reg-T). Cite IB's
   own pages.
4. **Data.** The exact historical source, its cost, coverage and granularity. Settlement-only or
   end-of-day data cannot measure what a taker pays; say so when that is all there is, and
   estimate the touch from any intraday source you can find. Check `data/cache/` first:
   `index_chains` holds SPY, QQQ and IWM option snapshots at 15:59 and 10:00 for 2016-2026,
   `deribit`, `kalshi`, `spy_macro`, `dolthub_*` and `wikipedia` hold other caches. For paid
   sources, price the pull from the vendor's public price list; never call a vendor API.
5. **Pilot, if the data is in hand at zero cost.** State the hypothesis, mechanism and pass rule
   in `diagnosis.log` before computing any outcome. Split discovery from held-out by time. Score
   net at the touch against a matched control (non-event windows on the same instrument, same
   weekday and tenor where possible), with date-clustered 95% intervals
   (`earnings_iv_crush.research.protocol.date_clustered_ci`). Iterate on discovery: diagnose what
   went wrong per event, fix it, re-score; do not stop after one failure. Freeze once: a
   `freeze_*.md` note that records the SHA-256 of itself and of the held-out scorer, with the
   scorer written before the note. Read the held-out block once.
6. **Verdict.** Viable, viable pending a priced data pull, or not viable, with the kill criterion
   and what a forward paper test would look like.

## Standard

- Every number carries its N, interval and basis (per trade or per year, net or gross, at the mid
  or at the touch, on premium or on margin) and a source: a file you wrote or a URL.
- Label every empirical claim verified (you read it at the source), recalled, or conjecture. A
  regularity does not transfer across asset classes or venues without its own evidence.
- Never annualise an event book with the daily square root of 252.
- Settle-to-settle P&L, mid-to-mid P&L and Black-Scholes-inverted marks are not tradeable levels.
- Prefer the conservative reading. Report attrition, and test whether drops depend on the outcome.

## Hard limits

- Zero spend. No vendor API calls (the project's keys are in `.env`, which is off limits), no
  WRDS or broker logins, no order path, no IB connection.
- No SEC EDGAR fetches. Never put the user's name, email or project in a request; use the
  User-Agent `research-client`. Respect robots.txt and rate limits (at most one request a second
  per host), no login-walled, paywalled or CAPTCHA-protected pages, no circumventing access
  controls. Public pages, public APIs without keys, and free downloads are fine.
- Write only inside your lane folder `outputs/research/2026-11-13-niche-hunt/<lane>/`. Keep raw
  scraped data under 300 MB and delete anything larger after use, saying how to rebuild it.
- No licensed vendor rows (Databento, WRDS) in any text file you write; computed aggregates are
  fine.
- Do not write `report.md` or `findings.md`: findings are the analyst's. Write `evidence.md` (the
  dossier), `sources.csv` (claim, URL, source type, verified/recalled/conjecture), and for a
  pilot `trials.csv`, `diagnosis.log`, scripts and logs.
- Trial numbers only from your block in `RESERVED_TRIAL_IDS.md`; every scored configuration
  counts, abandoned ones too.
- British spelling, commas or full stops instead of em dashes, plain statements.

## Your final message

Under 600 words, verdict first: the candidate, its best evidence with N, interval and basis, the
closest prior work, the IB route, the data route and its cost, and the single next step. List
what you could not verify.
