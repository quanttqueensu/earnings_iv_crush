"""
edgar_sessions.py
Check an earnings calendar's BMO/AMC session against SEC EDGAR 8-K Item 2.02 filings.

An earnings release is furnished to the SEC on Form 8-K under Item 2.02 (Results of
Operations and Financial Condition). The time EDGAR accepted that filing is an independent,
timestamped record of when the results were public, so it can confirm or contradict the
session column of a vendor calendar. The session decides which overnight gap a straddle
spans and whether a 15:59 snapshot on the announcement day precedes or follows the news,
so a wrong label corrupts both P&L and any at-entry signal without raising an error.

Three properties of EDGAR shape the design.

1. **Acceptance time comes from the filing index page.** The submissions JSON field
   ``acceptanceDateTime`` carries a trailing ``Z`` but its offset from Eastern time is not
   consistent across filers: on a live check some filers show true UTC (Eastern plus four or
   five hours) and others Eastern plus eight or ten hours. The "Accepted" field on the
   filing's ``-index.htm`` page is Eastern wall-clock and agrees with known release times,
   so it is the authority here; the JSON value is kept only to report the offset.
2. **After 17:30 ET the filing date rolls to the next business day.** A filer that submits
   its 8-K the evening before a pre-market release (PepsiCo does) is accepted at, say, 17:57
   with the next day's filing date. Such a filing is treated as released before the open on
   its filing date.
3. **The 8-K can lag the press release.** Item 2.02 allows the 8-K after the release, so an
   acceptance time is an upper bound on when the news was public. An EDGAR slot *earlier*
   than the calendar's is a hard contradiction; a *later* one is consistent with a late
   filing and is reported separately.

Agreement is therefore scored on the **reaction session**: the first NYSE session whose open
follows the release (BMO on day D -> D; AMC on D -> the next session; intraday on D -> D).
AMC on D and an evening filing dated D+1 share a reaction session, which is what the trade
timing depends on. The literal label agreement is reported beside it.

Fair access: every request carries a User-Agent, requests are spaced to stay under ten per
second, and every response is cached under ``data/cache/edgar/``.

Usage
-----
    python -m earnings_iv_crush.data.edgar_sessions
    python -m earnings_iv_crush.data.edgar_sessions --start 2025-01-01 --end 2026-06-30
    python -m earnings_iv_crush.data.edgar_sessions --limit 20 --out outputs/research/edgar_sessions

References
----------
SEC (2024). Accessing EDGAR Data; Fair Access policy (ten requests per second, declared
User-Agent). https://www.sec.gov/os/accessing-edgar-data
SEC. EDGAR Filer Manual, Volume II, section 3 (filing date for submissions accepted after
5:30 p.m. Eastern).
SEC. Form 8-K General Instructions, Item 2.02 Results of Operations and Financial Condition.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from ..engine.stats import nyse_sessions
from .config import SEC_USER_AGENT

# ── constants ────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _ROOT / "data" / "cache" / "edgar"
DEFAULT_CALENDAR = _ROOT / "outputs" / "research" / "events_master_broad.parquet"
DEFAULT_OUT = _ROOT / "outputs" / "research" / "edgar_sessions"

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{acc}-index.htm"

# SEC fair-access ceiling is 10 requests/second; spacing at 0.11 s keeps a margin of ~10%.
MIN_REQUEST_INTERVAL_S = 0.11
MAX_RETRIES = 4
RETRY_BACKOFF_S = 2.0
REQUEST_TIMEOUT_S = 30

# Without a configured contact the request still identifies itself; it never invents one.
FALLBACK_USER_AGENT = "earnings-iv-crush research script (EDGAR session checker)"

MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)
EASTERN = "America/New_York"

# A filing matches an event when its release date lies within this many calendar days of
# the calendar's announcement date. Four days spans a weekend either side of a Monday or
# Friday print without reaching the previous or next quarter's release.
MATCH_WINDOW_DAYS = 4

# Unscheduled NYSE closures absent from engine.stats.NYSE_AD_HOC_CLOSURES (national day of
# mourning, 9 January 2025).
EXTRA_CLOSURES: tuple[str, ...] = ("2025-01-09",)

EARNINGS_FORM = "8-K"
EARNINGS_ITEM = "2.02"

_ACCEPTED_RE = re.compile(
    r"Accepted\s*</div>\s*<div[^>]*class=\"info\"[^>]*>\s*([0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
    re.IGNORECASE,
)
_ITEM_RE = re.compile(r"\d{1,2}\.\d{2}")


class SecAccessRefused(RuntimeError):
    """SEC refused a request (HTTP 403): the User-Agent or request rate was rejected."""


# ── pure helpers ─────────────────────────────────────────────────────────────


def normalise_ticker(ticker: str) -> str:
    """Upper-case a ticker and map share-class separators to SEC's hyphen form.

    Parameters
    ----------
    ticker : str
        Symbol as written in the calendar (``BRK.B``, ``brk/b``).

    Returns
    -------
    str
        SEC form (``BRK-B``).
    """
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def parse_items(items: str | None) -> frozenset[str]:
    """Parse the submissions ``items`` field into a set of item numbers.

    Parameters
    ----------
    items : str or None
        Comma-separated item list as EDGAR serves it (``"2.02,9.01"``); may be empty.

    Returns
    -------
    frozenset of str
        Item numbers in ``N.NN`` form. Tokens that are not item numbers are dropped.
    """
    if not items or not isinstance(items, str):
        return frozenset()
    return frozenset(m.group(0) for m in _ITEM_RE.finditer(items))


def is_earnings_8k(form: str, items: str | None) -> bool:
    """Whether a filing is an original 8-K furnishing Item 2.02.

    Amendments (``8-K/A``) are excluded: they refile an earlier release and would match a
    date that is not the announcement.
    """
    return form == EARNINGS_FORM and EARNINGS_ITEM in parse_items(items)


def to_eastern(ts: Any) -> pd.Timestamp:
    """Convert a timestamp to naive Eastern wall-clock time.

    Parameters
    ----------
    ts : str or datetime-like
        A tz-aware value is converted to ``America/New_York`` (so daylight saving is applied
        by date); a naive value is taken to be Eastern wall-clock already.

    Returns
    -------
    pandas.Timestamp
        Naive timestamp in Eastern wall-clock.
    """
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert(EASTERN).tz_localize(None)
    return t


def classify_time(ts_et: Any) -> str:
    """BMO, AMC or intraday from an Eastern wall-clock time.

    Before 09:30 is ``"bmo"``, at or after 16:00 is ``"amc"``, anything in between is
    ``"intraday"`` (the market was open, so the release cannot be placed in a gap).

    Parameters
    ----------
    ts_et : str or datetime-like
        Acceptance time; tz-aware values are converted to Eastern first.

    Returns
    -------
    str
        One of ``"bmo"``, ``"amc"``, ``"intraday"``.
    """
    t = to_eastern(ts_et).time()
    if t < MARKET_OPEN:
        return "bmo"
    if t >= MARKET_CLOSE:
        return "amc"
    return "intraday"


def parse_accepted(html: str) -> pd.Timestamp | None:
    """Extract the Eastern "Accepted" timestamp from an EDGAR filing index page.

    Parameters
    ----------
    html : str
        Body of ``{accession}-index.htm``.

    Returns
    -------
    pandas.Timestamp or None
        Naive Eastern timestamp, or ``None`` when the field is absent.
    """
    m = _ACCEPTED_RE.search(html)
    return pd.Timestamp(m.group(1)) if m else None


def trading_sessions(start: Any, end: Any) -> pd.DatetimeIndex:
    """NYSE sessions between two dates, inclusive, including the extra closures.

    Parameters
    ----------
    start, end : datetime-like
        Inclusive bounds.

    Returns
    -------
    pandas.DatetimeIndex
        Ascending session dates.
    """
    s = nyse_sessions(pd.Timestamp(start), pd.Timestamp(end))
    return s.difference(pd.to_datetime(list(EXTRA_CLOSURES)))


def _next_session(day: pd.Timestamp, sessions: pd.DatetimeIndex, *, strict: bool) -> pd.Timestamp:
    """First session after ``day`` (``strict``) or on or after it."""
    i = int(sessions.searchsorted(day, side="right" if strict else "left"))
    if i >= len(sessions):
        raise ValueError(f"no NYSE session after {day.date()} in the supplied calendar")
    return pd.Timestamp(sessions[i])


@dataclass(frozen=True)
class ReleaseSlot:
    """When an 8-K made the results public.

    Attributes
    ----------
    session : str
        ``"bmo"``, ``"amc"`` or ``"intraday"`` relative to ``release_date``.
    release_date : pandas.Timestamp
        The session date the label refers to.
    reaction_date : pandas.Timestamp
        First session whose open follows the release (the intraday case reacts the same day).
    rolled : bool
        True when the filing was accepted after the filing-date cutoff and dated the next
        business day, or accepted on a non-session day.
    """

    session: str
    release_date: pd.Timestamp
    reaction_date: pd.Timestamp
    rolled: bool


def release_slot(accepted_et: Any, filing_date: Any, sessions: pd.DatetimeIndex) -> ReleaseSlot:
    """Place an 8-K acceptance in a trading session.

    Parameters
    ----------
    accepted_et : datetime-like
        Acceptance time (Eastern; tz-aware values are converted).
    filing_date : datetime-like
        EDGAR filing date. Later than the acceptance date when the filing was accepted after
        17:30 ET (or on a non-business day) and dated forward.
    sessions : pandas.DatetimeIndex
        NYSE sessions covering the dates involved.

    Returns
    -------
    ReleaseSlot
        Session label, release date and reaction date.
    """
    acc = to_eastern(accepted_et)
    day = acc.normalize()
    fdate = pd.Timestamp(filing_date).normalize()
    if fdate > day or day not in sessions:
        # Dated forward or accepted on a closed day: public before the next open.
        rel = _next_session(max(fdate, day), sessions, strict=False)
        return ReleaseSlot("bmo", rel, rel, True)
    label = classify_time(acc)
    if label == "amc":
        return ReleaseSlot("amc", day, _next_session(day, sessions, strict=True), False)
    return ReleaseSlot(label, day, day, False)


def calendar_reaction(
    announce_date: Any, session: str, sessions: pd.DatetimeIndex
) -> pd.Timestamp | None:
    """Reaction session implied by a calendar row.

    Parameters
    ----------
    announce_date : datetime-like
        Calendar announcement date.
    session : str
        ``"bmo"`` or ``"amc"``; anything else returns ``None``.
    sessions : pandas.DatetimeIndex
        NYSE sessions covering the date.

    Returns
    -------
    pandas.Timestamp or None
        The first session whose open follows the release.
    """
    day = pd.Timestamp(announce_date).normalize()
    if session == "bmo":
        return _next_session(day, sessions, strict=False)
    if session == "amc":
        return _next_session(day, sessions, strict=True)
    return None


def match_nearest(
    filings: pd.DataFrame, announce_date: Any, window_days: int = MATCH_WINDOW_DAYS
) -> pd.Series | None:
    """The earnings 8-K whose release date is nearest the calendar date.

    Parameters
    ----------
    filings : pandas.DataFrame
        One ticker's earnings 8-Ks with ``release_date`` and ``accepted_et``.
    announce_date : datetime-like
        Calendar announcement date.
    window_days : int, optional
        Maximum absolute distance in calendar days. Defaults to ``MATCH_WINDOW_DAYS``.

    Returns
    -------
    pandas.Series or None
        The matched row, ties broken by the earlier acceptance; ``None`` when nothing lies
        inside the window.
    """
    if filings.empty:
        return None
    day = pd.Timestamp(announce_date).normalize()
    dist = (pd.to_datetime(filings["release_date"]) - day).abs().dt.days
    inside = filings.assign(_dist=dist)[dist <= window_days]
    if inside.empty:
        return None
    best = inside.sort_values(["_dist", "accepted_et"], kind="mergesort").iloc[0]
    return best.drop(labels="_dist")


def compare_reaction(calendar: pd.Timestamp | None, edgar: pd.Timestamp) -> str:
    """Verdict on a calendar reaction session against EDGAR's.

    Returns
    -------
    str
        ``"agree"``; ``"edgar_earlier"`` (EDGAR proves the news was public before the
        calendar says, a hard contradiction); ``"edgar_later"`` (consistent with a late
        8-K); or ``"calendar_ambiguous"``.
    """
    if calendar is None:
        return "calendar_ambiguous"
    if edgar == calendar:
        return "agree"
    return "edgar_earlier" if edgar < calendar else "edgar_later"


def wilson_ci(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return (lo, hi)


# ── EDGAR client ─────────────────────────────────────────────────────────────


class EdgarClient:
    """Rate-limited, disk-cached EDGAR reader.

    Parameters
    ----------
    cache_dir : pathlib.Path, optional
        Cache root. Defaults to ``data/cache/edgar``.
    user_agent : str or None, optional
        Declared User-Agent. Defaults to ``SEC_USER_AGENT`` from the environment, falling
        back to a descriptive string with no contact details.
    session : requests.Session or None, optional
        HTTP session (injectable for testing).
    min_interval : float, optional
        Minimum seconds between requests.
    refresh : bool, optional
        Re-fetch submissions even when cached (index pages never change and stay cached).
    sleep, clock : callable, optional
        Injectable for testing the rate limiter.
    """

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        user_agent: str | None = None,
        session: requests.Session | None = None,
        min_interval: float = MIN_REQUEST_INTERVAL_S,
        refresh: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        ua = user_agent if user_agent is not None else SEC_USER_AGENT
        self.user_agent = ua.strip() or FALLBACK_USER_AGENT
        self.session = session or requests.Session()
        self.min_interval = min_interval
        self.refresh = refresh
        self._sleep = sleep
        self._clock = clock
        self._last = -math.inf
        self.n_requests = 0
        self._cik: dict[str, int] | None = None

    # ── transport ──

    def _throttle(self) -> None:
        wait = self.min_interval - (self._clock() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()

    def get(self, url: str) -> requests.Response:
        """GET with throttling and retry on 429/5xx; raise on refusal.

        Raises
        ------
        SecAccessRefused
            On HTTP 403.
        requests.HTTPError
            On any other non-retryable failure.
        """
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        for attempt in range(MAX_RETRIES):
            self._throttle()
            self.n_requests += 1
            r = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_S)
            if r.status_code == 403:
                raise SecAccessRefused(f"SEC returned 403 for {url}; check SEC_USER_AGENT")
            if r.status_code == 429 or r.status_code >= 500:
                self._sleep(RETRY_BACKOFF_S * (2**attempt))
                continue
            r.raise_for_status()
            return r
        raise requests.HTTPError(f"{url}: gave up after {MAX_RETRIES} attempts")

    def _cached_json(self, rel: str, url: str, *, refresh: bool) -> Any:
        path = self.cache_dir / rel
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        data = self.get(url).json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    # ── endpoints ──

    def cik_map(self) -> dict[str, int]:
        """Ticker (SEC form) to integer CIK from ``company_tickers.json``."""
        if self._cik is None:
            raw = self._cached_json("company_tickers.json", TICKERS_URL, refresh=self.refresh)
            self._cik = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in raw.values()}
        return self._cik

    def submissions(self, cik: int) -> dict[str, Any]:
        """The ``CIK##########.json`` submissions document."""
        name = f"CIK{cik:010d}.json"
        return dict(
            self._cached_json(
                f"submissions/{name}", SUBMISSIONS_URL.format(name=name), refresh=self.refresh
            )
        )

    def filings(self, cik: int, since: pd.Timestamp) -> pd.DataFrame:
        """All filings from the recent block plus any older shard reaching ``since``.

        Returns
        -------
        pandas.DataFrame
            Columns ``form``, ``items``, ``accession``, ``filing_date``, ``acceptance_json``.
        """
        sub = self.submissions(cik)
        frames = [_filings_frame(sub["filings"]["recent"])]
        for shard in sub["filings"].get("files", []):
            if pd.Timestamp(shard["filingTo"]) >= since:
                raw = self._cached_json(
                    f"submissions/{shard['name']}",
                    SUBMISSIONS_URL.format(name=shard["name"]),
                    refresh=False,  # shards are closed history
                )
                frames.append(_filings_frame(raw))
        out = pd.concat(frames, ignore_index=True)
        return out.drop_duplicates("accession").reset_index(drop=True)

    def accepted_et(self, cik: int, accession: str) -> pd.Timestamp | None:
        """Eastern acceptance time from the filing index page (cached; pages are immutable)."""
        path = self.cache_dir / "index" / f"{accession}.txt"
        if path.exists():
            txt = path.read_text(encoding="utf-8").strip()
            return pd.Timestamp(txt) if txt else None
        url = INDEX_URL.format(cik=cik, acc_nodash=accession.replace("-", ""), acc=accession)
        ts = parse_accepted(self.get(url).text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("" if ts is None else ts.isoformat(), encoding="utf-8")
        return ts


def _filings_frame(block: dict[str, list[Any]]) -> pd.DataFrame:
    """Columnar submissions block to a frame, tolerating a missing ``items`` column."""
    n = len(block.get("accessionNumber", []))
    return pd.DataFrame(
        {
            "form": block.get("form", [""] * n),
            "items": block.get("items", [""] * n),
            "accession": block.get("accessionNumber", []),
            "filing_date": pd.to_datetime(block.get("filingDate", [None] * n)),
            "acceptance_json": block.get("acceptanceDateTime", [""] * n),
        }
    )


# ── calendar check ───────────────────────────────────────────────────────────


def earnings_filings(
    client: EdgarClient,
    cik: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    sessions: pd.DatetimeIndex,
) -> pd.DataFrame:
    """One filer's Item 2.02 8-Ks in a window, each placed in a release slot.

    Returns
    -------
    pandas.DataFrame
        ``accession``, ``filing_date``, ``acceptance_json``, ``accepted_et``, ``session``,
        ``release_date``, ``reaction_date``, ``rolled``. Filings whose index page carries no
        acceptance time are dropped.
    """
    f = client.filings(cik, since=start)
    lo = start - pd.Timedelta(days=MATCH_WINDOW_DAYS + 1)
    hi = end + pd.Timedelta(days=MATCH_WINDOW_DAYS + 1)
    mask = [is_earnings_8k(fm, it) for fm, it in zip(f["form"], f["items"], strict=True)]
    f = f[np.asarray(mask, dtype=bool) & f["filing_date"].between(lo, hi)]
    rows = []
    for _, r in f.iterrows():
        acc = client.accepted_et(cik, str(r["accession"]))
        if acc is None:
            continue
        slot = release_slot(acc, r["filing_date"], sessions)
        rows.append(
            {
                "accession": r["accession"],
                "filing_date": r["filing_date"],
                "acceptance_json": r["acceptance_json"],
                "accepted_et": acc,
                "session": slot.session,
                "release_date": slot.release_date,
                "reaction_date": slot.reaction_date,
                "rolled": slot.rolled,
            }
        )
    cols = [
        "accession",
        "filing_date",
        "acceptance_json",
        "accepted_et",
        "session",
        "release_date",
        "reaction_date",
        "rolled",
    ]
    return pd.DataFrame(rows, columns=cols)


def check_calendar(
    calendar: pd.DataFrame,
    client: EdgarClient,
    start: Any,
    end: Any,
    progress: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Match every calendar event to its nearest earnings 8-K and compare sessions.

    Parameters
    ----------
    calendar : pandas.DataFrame
        Needs ``ticker``, ``announce_date``, ``session``; ``session_source`` is carried
        through when present.
    client : EdgarClient
        EDGAR reader.
    start, end : datetime-like
        Inclusive announcement-date window.
    progress : bool, optional
        Print one line per 25 tickers.

    Returns
    -------
    tuple
        ``(rows, funnel)``: one row per in-window event with the match and verdict, and the
        coverage funnel as ordered counts.

    Raises
    ------
    ValueError
        When no calendar event falls in the window.
    """
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    cal = calendar.copy()
    cal["announce_date"] = pd.to_datetime(cal["announce_date"]).dt.normalize()
    cal = cal[cal["announce_date"].between(s, e)].reset_index(drop=True)
    if cal.empty:
        raise ValueError(f"no calendar events between {s.date()} and {e.date()}")
    sessions = trading_sessions(s - pd.Timedelta(days=15), e + pd.Timedelta(days=15))
    cmap = client.cik_map()

    out: list[dict[str, Any]] = []
    tickers = sorted(cal["ticker"].unique())
    for i, tkr in enumerate(tickers, start=1):
        grp = cal[cal["ticker"] == tkr]
        cik = cmap.get(normalise_ticker(tkr))
        filings = None
        status = "no_cik"
        if cik is not None:
            try:
                filings = earnings_filings(client, cik, s, e, sessions)
                status = "ok"
            except SecAccessRefused:
                raise
            except (requests.RequestException, KeyError, ValueError) as exc:
                status = f"fetch_error:{type(exc).__name__}"
        for _, ev in grp.iterrows():
            row: dict[str, Any] = {
                "ticker": tkr,
                "announce_date": ev["announce_date"],
                "calendar_session": ev["session"],
                "session_source": ev.get("session_source", ""),
                "cik": cik,
                "status": status,
            }
            cal_react = calendar_reaction(ev["announce_date"], str(ev["session"]), sessions)
            row["calendar_reaction"] = cal_react
            match = None
            if filings is not None:
                match = match_nearest(filings, ev["announce_date"])
                if match is None:
                    row["status"] = "no_8k_in_window" if not filings.empty else "no_8k_2_02"
            if match is not None:
                row.update(
                    {
                        "accession": match["accession"],
                        "accepted_et": match["accepted_et"],
                        "filing_date": match["filing_date"],
                        "acceptance_json": match["acceptance_json"],
                        "edgar_session": match["session"],
                        "edgar_release_date": match["release_date"],
                        "edgar_reaction": match["reaction_date"],
                        "rolled": bool(match["rolled"]),
                        "verdict": compare_reaction(cal_react, match["reaction_date"]),
                        "label_agree": match["session"] == ev["session"],
                    }
                )
            out.append(row)
        if progress and (i % 25 == 0 or i == len(tickers)):
            print(f"  [{i}/{len(tickers)}] tickers, {client.n_requests} requests", flush=True)

    rows = pd.DataFrame(out)
    matched = rows["verdict"].notna() if "verdict" in rows else pd.Series(False, index=rows.index)
    funnel = {
        "calendar_events_in_window": len(rows),
        "ticker_mapped_to_cik": int(rows["cik"].notna().sum()),
        "submissions_fetched": int((rows["status"] != "no_cik").sum())
        - int(rows["status"].astype(str).str.startswith("fetch_error").sum()),
        "matched_8k_2_02_in_window": int(matched.sum()),
        "comparable_calendar_session": int(
            (matched & rows.get("verdict", pd.Series(dtype=str)).ne("calendar_ambiguous")).sum()
        ),
    }
    return rows, funnel


def json_offset_hours(rows: pd.DataFrame) -> pd.Series:
    """Hours by which the submissions-JSON acceptance time leads the index-page time."""
    j = pd.to_datetime(rows["acceptance_json"], utc=True).dt.tz_localize(None)
    return ((j - pd.to_datetime(rows["accepted_et"])).dt.total_seconds() / 3600).round(2)


def summarise(rows: pd.DataFrame, funnel: dict[str, int]) -> dict[str, Any]:
    """Agreement statistics over the comparable events.

    Returns
    -------
    dict
        Funnel, reaction-session agreement with Wilson CI, label agreement, verdict counts,
        a breakdown by calendar ``session_source`` and the JSON offset distribution.
    """
    comp = rows[
        rows.get("verdict", pd.Series(dtype=str)).isin(["agree", "edgar_earlier", "edgar_later"])
    ]
    n = len(comp)
    k = int((comp["verdict"] == "agree").sum())
    lab = int(comp["label_agree"].astype(bool).sum())
    by_src = {
        str(src): {
            "n": len(g),
            "agree": int((g["verdict"] == "agree").sum()),
            "edgar_earlier": int((g["verdict"] == "edgar_earlier").sum()),
            "edgar_later": int((g["verdict"] == "edgar_later").sum()),
        }
        for src, g in comp.groupby("session_source")
    }
    by_cal = {
        str(sess): {
            "n": len(g),
            "agree": int((g["verdict"] == "agree").sum()),
            "edgar_session_counts": {
                str(a): int(b) for a, b in g["edgar_session"].value_counts().items()
            },
        }
        for sess, g in comp.groupby("calendar_session")
    }
    offs = json_offset_hours(comp) if n else pd.Series(dtype=float)
    return {
        "funnel": funnel,
        "status_counts": {str(a): int(b) for a, b in rows["status"].value_counts().items()},
        "n_comparable": n,
        "reaction_agree": k,
        "reaction_agree_rate": k / n if n else math.nan,
        "reaction_agree_wilson95": list(wilson_ci(k, n)),
        "label_agree": lab,
        "label_agree_rate": lab / n if n else math.nan,
        "verdict_counts": {str(a): int(b) for a, b in comp["verdict"].value_counts().items()},
        "edgar_rolled_forward": int(comp["rolled"].astype(bool).sum()) if n else 0,
        "by_session_source": by_src,
        "by_calendar_session": by_cal,
        "json_offset_hours_counts": {str(a): int(b) for a, b in offs.value_counts().items()},
    }


def _report_text(summary: dict[str, Any], rows: pd.DataFrame, calendar_path: Path) -> str:
    """Plain-text agreement report."""
    f = summary["funnel"]
    lo, hi = summary["reaction_agree_wilson95"]
    lines = [
        "# EDGAR 8-K session check",
        "",
        f"Calendar: `{calendar_path.name}`. Acceptance times from EDGAR filing index pages "
        "(Eastern); release slot per the 17:30 filing-date rollover; agreement scored on the "
        "reaction session (first session whose open follows the release).",
        "",
        "## Coverage funnel",
        "",
    ]
    lines += [f"- {k.replace('_', ' ')}: {v}" for k, v in f.items()]
    lines += [
        "",
        "## Agreement",
        "",
        f"- Reaction session agrees: {summary['reaction_agree']} of {summary['n_comparable']} "
        f"({summary['reaction_agree_rate']:.1%}, Wilson 95% [{lo:.1%}, {hi:.1%}]; events "
        "treated as independent, which overstates precision for repeat filers).",
        f"- Literal label agrees: {summary['label_agree']} ({summary['label_agree_rate']:.1%}).",
        f"- Verdicts: {summary['verdict_counts']}.",
        f"- Filings dated forward past the 17:30 cutoff: {summary['edgar_rolled_forward']}.",
        f"- JSON acceptance offset from index time, hours: {summary['json_offset_hours_counts']}.",
        "",
        "## By calendar session source",
        "",
    ]
    for src, d in summary["by_session_source"].items():
        lines.append(
            f"- {src}: n={d['n']}, agree {d['agree']}, EDGAR earlier {d['edgar_earlier']}, "
            f"EDGAR later {d['edgar_later']}"
        )
    hard = rows[rows.get("verdict", pd.Series(dtype=str)) == "edgar_earlier"]
    lines += ["", f"## Hard contradictions (EDGAR earlier than calendar): {len(hard)}", ""]
    for _, r in hard.sort_values("announce_date").iterrows():
        lines.append(
            f"- {r['ticker']} {r['announce_date'].date()} calendar {r['calendar_session']}: "
            f"8-K accepted {pd.Timestamp(r['accepted_et'])} ET ({r['edgar_session']})"
        )
    return "\n".join(lines) + "\n"


# ── entry point ──────────────────────────────────────────────────────────────


def main(argv: Iterable[str] | None = None) -> None:
    """Run the checker on a calendar and write the agreement report."""
    ap = argparse.ArgumentParser(
        description="Check calendar BMO/AMC sessions against EDGAR 8-K Item 2.02 filings."
    )
    ap.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0, help="first N tickers only (0 = all)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch cached submissions")
    args = ap.parse_args(list(argv) if argv is not None else None)

    cal = pd.read_parquet(args.calendar)
    if args.limit:
        keep = sorted(cal["ticker"].unique())[: args.limit]
        cal = cal[cal["ticker"].isin(keep)]
    client = EdgarClient(refresh=args.refresh)
    if client.user_agent == FALLBACK_USER_AGENT:
        print("  SEC_USER_AGENT unset: using a descriptive User-Agent with no contact.")
    try:
        rows, funnel = check_calendar(cal, client, args.start, args.end)
    except SecAccessRefused as exc:
        raise SystemExit(f"SEC refused access, stopping: {exc}") from exc

    print("  funnel:")
    for k, v in funnel.items():
        print(f"    {k:<32} {v}")
    if funnel["comparable_calendar_session"] == 0:
        raise SystemExit("no event could be compared with EDGAR - refusing to report a rate")
    summary = summarise(rows, funnel)
    args.out.mkdir(parents=True, exist_ok=True)
    rows.to_csv(args.out / "agreement.csv", index=False)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), "utf-8")
    (args.out / "report.md").write_text(_report_text(summary, rows, args.calendar), "utf-8")
    lo, hi = summary["reaction_agree_wilson95"]
    print(
        f"  reaction-session agreement {summary['reaction_agree']}/{summary['n_comparable']} "
        f"= {summary['reaction_agree_rate']:.1%} [{lo:.1%}, {hi:.1%}]; "
        f"verdicts {summary['verdict_counts']}; {client.n_requests} requests"
    )
    print(f"  wrote {args.out.resolve()}")


if __name__ == "__main__":
    main()
