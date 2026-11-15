# EDGAR 8-K session check

Calendar: `events_master_broad.parquet`. Acceptance times from EDGAR filing index pages (Eastern); release slot per the 17:30 filing-date rollover; agreement scored on the reaction session (first session whose open follows the release).

## Coverage funnel

- calendar events in window: 2055
- ticker mapped to cik: 2005
- submissions fetched: 2005
- matched 8k 2 02 in window: 1991
- comparable calendar session: 1990

## Agreement

- Reaction session agrees: 1973 of 1990 (99.1%, Wilson 95% [98.6%, 99.5%]; events treated as independent, which overstates precision for repeat filers).
- Literal label agrees: 1916 (96.3%).
- Verdicts: {'agree': 1973, 'edgar_later': 15, 'edgar_earlier': 2}.
- Filings dated forward past the 17:30 cutoff: 34.
- JSON acceptance offset from index time, hours: {'8.0': 619, '4.0': 616, '10.0': 388, '5.0': 367}.

## By calendar session source

- conflict: n=39, agree 33, EDGAR earlier 0, EDGAR later 6
- edgar_override: n=1, agree 0, EDGAR earlier 0, EDGAR later 1
- yahoo: n=1161, agree 1153, EDGAR earlier 1, EDGAR later 7
- yahoo+edgar: n=789, agree 787, EDGAR earlier 1, EDGAR later 1

## Hard contradictions (EDGAR earlier than calendar): 2

- UAL 2025-01-21 calendar amc: 8-K accepted 2025-01-21 15:59:53 ET (intraday)
- LMT 2025-04-22 calendar amc: 8-K accepted 2025-04-22 07:31:37 ET (bmo)
