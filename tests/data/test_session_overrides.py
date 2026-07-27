from __future__ import annotations

import pandas as pd

from earnings_iv_crush.data.session_overrides import apply_session_overrides


def test_applies_matching_override():
    cal = pd.DataFrame(
        {
            "ticker": ["GE", "GE"],
            "announce_date": ["2019-01-31", "2019-04-30"],
            "session": ["bmo", "bmo"],
        }
    )
    out = apply_session_overrides(cal, overrides={("GE", "2019-01-31"): "amc"})
    assert out.loc[0, "session"] == "amc"
    assert out.loc[0, "session_source"] == "wrds_override"
    assert out.loc[1, "session"] == "bmo"
    assert pd.isna(out.loc[1, "session_source"])


def test_no_match_leaves_calendar_unchanged():
    cal = pd.DataFrame({"ticker": ["AAPL"], "announce_date": ["2020-01-01"], "session": ["bmo"]})
    out = apply_session_overrides(cal, overrides={("GE", "2019-01-31"): "amc"})
    assert out.loc[0, "session"] == "bmo"


def test_does_not_mutate_input():
    cal = pd.DataFrame({"ticker": ["GE"], "announce_date": ["2019-01-31"], "session": ["bmo"]})
    apply_session_overrides(cal, overrides={("GE", "2019-01-31"): "amc"})
    assert cal.loc[0, "session"] == "bmo"


def test_default_overrides_cover_ge_and_lin_only():
    from earnings_iv_crush.data.session_overrides import WRDS_SESSION_OVERRIDES

    tickers = {t for t, _ in WRDS_SESSION_OVERRIDES}
    assert tickers == {"GE", "LIN"}
    assert all(v == "amc" for v in WRDS_SESSION_OVERRIDES.values())
