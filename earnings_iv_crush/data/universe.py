"""
universe.py
Static backtest universes with survivorship treatment.

Two cohorts, both frozen at the start of the sample window (2024-01) so the
selection is point-in-time:

* ``MEGACAP_50`` — the fifty largest S&P 100 names by market capitalisation as
  of January 2024, all with weekly options and deep books. This is the
  liquidity-clean cohort.
* ``BROAD_300``  — three hundred S&P 500 constituents as of January 2024,
  spanning the capitalisation and liquidity spectrum. ``MEGACAP_50`` is a
  strict subset.

Names that were later delisted or acquired stay in the lists deliberately:
they surface as logged missing-data exclusions in the quality filter rather
than disappearing silently, which keeps the residual survivorship bias visible
and documentable. The lists must never be refreshed against a current
constituent snapshot mid-sample.

``liquidity_screen`` is annotation-only: it labels names with a liquidity
decile from a current snapshot so results can be cut by liquidity, but it must
never be used to drop names ex post (that would reintroduce look-ahead).
"""

from __future__ import annotations

import logging

import pandas as pd

_logger = logging.getLogger(__name__)

# Fifty largest S&P 100 names by market cap as of 2024-01, weekly options.
MEGACAP_50: list[str] = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "BRK-B",
    "LLY",
    "AVGO",
    "JPM",
    "V",
    "UNH",
    "XOM",
    "MA",
    "JNJ",
    "PG",
    "HD",
    "COST",
    "MRK",
    "ABBV",
    "CVX",
    "CRM",
    "ADBE",
    "AMD",
    "PEP",
    "KO",
    "WMT",
    "NFLX",
    "ACN",
    "MCD",
    "TMO",
    "CSCO",
    "ABT",
    "LIN",
    "ORCL",
    "INTC",
    "CMCSA",
    "DIS",
    "WFC",
    "INTU",
    "VZ",
    "QCOM",
    "IBM",
    "CAT",
    "TXN",
    "GE",
    "AMGN",
    "PFE",
    "NOW",
]

# S&P 500 constituents as of 2024-01 (subset of 300, alphabetical past the
# megacap block). Frozen at sample start; do not refresh.
_BROAD_EXTRA: list[str] = [
    "A",
    "AAL",
    "ABNB",
    "ADI",
    "ADM",
    "ADP",
    "ADSK",
    "AEP",
    "AFL",
    "AIG",
    "AJG",
    "ALB",
    "ALGN",
    "ALL",
    "AMAT",
    "AME",
    "AMP",
    "AMT",
    "ANET",
    "AON",
    "APA",
    "APD",
    "APH",
    "APTV",
    "ARE",
    "AXP",
    "AZO",
    "BA",
    "BAC",
    "BAX",
    "BBY",
    "BDX",
    "BEN",
    "BIIB",
    "BK",
    "BKNG",
    "BKR",
    "BLK",
    "BMY",
    "BSX",
    "BX",
    "BXP",
    "C",
    "CAG",
    "CAH",
    "CARR",
    "CB",
    "CBRE",
    "CCI",
    "CCL",
    "CDNS",
    "CDW",
    "CE",
    "CF",
    "CHD",
    "CHTR",
    "CI",
    "CINF",
    "CL",
    "CLX",
    "CMA",
    "CME",
    "CMG",
    "CMI",
    "CNC",
    "CNP",
    "COF",
    "COP",
    "CPB",
    "CPRT",
    "CPT",
    "CRL",
    "CSGP",
    "CSX",
    "CTAS",
    "CTRA",
    "CTSH",
    "CTVA",
    "CVS",
    "CZR",
    "D",
    "DAL",
    "DD",
    "DE",
    "DFS",
    "DG",
    "DGX",
    "DHI",
    "DHR",
    "DLR",
    "DLTR",
    "DOV",
    "DOW",
    "DPZ",
    "DRI",
    "DTE",
    "DUK",
    "DVN",
    "DXCM",
    "EA",
    "EBAY",
    "ECL",
    "ED",
    "EFX",
    "EIX",
    "EL",
    "EMR",
    "ENPH",
    "EOG",
    "EQIX",
    "EQR",
    "EQT",
    "ES",
    "ESS",
    "ETN",
    "ETR",
    "EVRG",
    "EW",
    "EXC",
    "EXPE",
    "F",
    "FANG",
    "FAST",
    "FCX",
    "FDX",
    "FE",
    "FI",
    "FICO",
    "FIS",
    "FITB",
    "FSLR",
    "FTNT",
    "GD",
    "GILD",
    "GIS",
    "GLW",
    "GM",
    "GPN",
    "GS",
    "GWW",
    "HAL",
    "HAS",
    "HBAN",
    "HCA",
    "HES",
    "HIG",
    "HLT",
    "HON",
    "HPE",
    "HPQ",
    "HRL",
    "HST",
    "HSY",
    "HUM",
    "IDXX",
    "IEX",
    "ILMN",
    "IP",
    "IQV",
    "IR",
    "IRM",
    "ISRG",
    "IT",
    "ITW",
    "IVZ",
    "JBHT",
    "JCI",
    "JNPR",
    "K",
    "KDP",
    "KEY",
    "KHC",
    "KIM",
    "KLAC",
    "KMB",
    "KMI",
    "KMX",
    "KR",
    "L",
    "LEN",
    "LH",
    "LHX",
    "LMT",
    "LOW",
    "LRCX",
    "LULU",
    "LUV",
    "LVS",
    "LYB",
    "LYV",
    "MAR",
    "MAS",
    "MCHP",
    "MCK",
    "MDLZ",
    "MDT",
    "MET",
    "MGM",
    "MKC",
    "MLM",
    "MMC",
    "MMM",
    "MNST",
    "MO",
    "MOS",
    "MPC",
    "MPWR",
    "MRNA",
    "MS",
    "MSCI",
    "MSI",
    "MTB",
    "MTCH",
    "MU",
    "NCLH",
    "NDAQ",
    "NEE",
    "NEM",
    "NKE",
    "NOC",
    "NRG",
    "NSC",
    "NTAP",
    "NTRS",
    "NUE",
    "NXPI",
    "O",
    "ODFL",
    "OKE",
    "OMC",
    "ON",
    "ORLY",
    "OTIS",
    "OXY",
    "PANW",
    "PARA",
    "PAYX",
    "PCAR",
    "PEG",
    "PGR",
    "PH",
    "PHM",
    "PLD",
    "PM",
    "PNC",
    "PPG",
    "PPL",
    "PRU",
    "PSA",
    "PSX",
    "PWR",
    "PYPL",
    "RCL",
    "REGN",
    "RF",
    "RJF",
    "RMD",
    "ROK",
    "ROP",
    "ROST",
    "RTX",
    "SBUX",
    "SCHW",
    "SHW",
    "SJM",
    "SLB",
    "SMCI",
    "SNPS",
    "SO",
    "SPG",
    "SPGI",
    "SRE",
    "STT",
    "STX",
    "STZ",
    "SWK",
    "SYF",
    "SYK",
    "SYY",
    "T",
    "TAP",
    "TDG",
    "TER",
    "TFC",
    "TGT",
    "TJX",
    "TMUS",
    "TPR",
    "TRV",
    "TSCO",
    "TSN",
    "TT",
    "TTWO",
    "TXT",
    "UAL",
    "ULTA",
    "UNP",
    "UPS",
    "URI",
    "USB",
]

BROAD_300: list[str] = MEGACAP_50 + _BROAD_EXTRA

_UNIVERSES: dict[str, list[str]] = {"megacap": MEGACAP_50, "broad": BROAD_300}


def get_universe(name: str) -> list[str]:
    """Return the ticker list for a named universe (``"megacap"`` or ``"broad"``)."""
    try:
        return list(_UNIVERSES[name])
    except KeyError:
        raise ValueError(
            f"unknown universe {name!r}; expected one of {sorted(_UNIVERSES)}"
        ) from None


def cohort_labels() -> pd.Series:
    """Ticker-indexed cohort label: ``"megacap"`` or ``"broad-only"``.

    Covers the broad universe; megacap names carry the ``"megacap"`` label so
    results can be cut by cohort without re-deriving membership.
    """
    labels = {t: "megacap" for t in MEGACAP_50}
    labels.update({t: "broad-only" for t in _BROAD_EXTRA})
    return pd.Series(labels, name="cohort")


def liquidity_screen(
    tickers: list[str],
    snapshot: pd.DataFrame,
    n_deciles: int = 10,
) -> pd.DataFrame:
    """Annotate tickers with a liquidity decile from a current option snapshot.

    Annotation only — never use this to drop names from a backtest, because the
    snapshot is taken after the sample and conditioning membership on it would
    reintroduce look-ahead.

    Parameters
    ----------
    tickers : list[str]
        Names to annotate.
    snapshot : pandas.DataFrame
        One row per ticker with a ``liquidity`` column (e.g. total near-dated
        open interest, or OI x volume).
    n_deciles : int
        Number of quantile buckets. Defaults to ``10``.

    Returns
    -------
    pandas.DataFrame
        Columns ``ticker``, ``liquidity``, ``liquidity_decile`` (1 = least
        liquid). Tickers missing from the snapshot get NaN.
    """
    out = pd.DataFrame({"ticker": tickers})
    snap = snapshot[["ticker", "liquidity"]].drop_duplicates("ticker")
    out = out.merge(snap, on="ticker", how="left")
    valid = out["liquidity"].notna()
    if valid.sum() >= n_deciles:
        out.loc[valid, "liquidity_decile"] = (
            pd.qcut(out.loc[valid, "liquidity"], n_deciles, labels=False, duplicates="drop") + 1
        )
    else:
        out["liquidity_decile"] = pd.NA
        _logger.warning("too few liquidity observations to form deciles")
    return out
