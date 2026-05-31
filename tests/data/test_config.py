"""Tests for src.data.config: .env parsing and the require() guard."""
from __future__ import annotations

import pytest

from src.data import config


def test_parse_env_basic():
    text = (
        "# a comment\n"
        "\n"
        "FOO=bar\n"
        "SEC_USER_AGENT=Jordan Odorico jodorico06@gmail.com\n"
    )
    parsed = config._parse_env_text(text)
    assert parsed["FOO"] == "bar"
    # Values may contain spaces (the SEC contact string).
    assert parsed["SEC_USER_AGENT"] == "Jordan Odorico jodorico06@gmail.com"


def test_parse_env_strips_quotes_and_empty_values():
    parsed = config._parse_env_text("A=\"quoted\"\nB='single'\nC=\nD")
    assert parsed["A"] == "quoted"
    assert parsed["B"] == "single"
    assert parsed["C"] == ""          # empty value is kept
    assert "D" not in parsed          # a line with no '=' is ignored


def test_parse_env_ignores_inline_noise():
    parsed = config._parse_env_text("   # spaced comment\n   \nKEY = value with spaces ")
    assert parsed == {"KEY": "value with spaces"}


def test_require_returns_value(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "abc123")
    assert config.require("FINNHUB_API_KEY") == "abc123"


def test_require_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Missing MISSING_KEY"):
        config.require("MISSING_KEY")
