"""
post_edit_check.py
PostToolUse hook for Edit and Write: flag, on the text just added, the defect classes this
project has actually shipped.

Advisory only: it never blocks. It reads the tool call from stdin, scans the added text for each
pattern below, and returns any warnings as context for the agent's next step. Each pattern names
the incident behind it, so the warning says why it matters.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# (pattern, applies to path regex, message)
CHECKS: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (
        re.compile(r"sqrt\(\s*252\s*\)|252\s*\*\*\s*0?\.5"),
        re.compile(r"\.py$"),
        "square root of 252: correct only for a daily series. An event book annualises by the "
        "square root of its own trades per year (engine.stats.infer_periods_per_year); this "
        "error once inflated a headline Sharpe 3.2 times.",
    ),
    (
        re.compile(r"\.fillna\("),
        re.compile(r"\.py$"),
        "fillna: an invented value for missing data is a silent fallback. Drop with a counted "
        "reason, or raise.",
    ),
    (
        re.compile(r"except\s*:|except\s+(Base)?Exception\s*:\s*\n\s*pass"),
        re.compile(r"\.py$"),
        "a swallowed exception: a failure must raise, warn or print a funnel, never vanish.",
    ),
    (
        re.compile(r"sys\.path\.insert"),
        re.compile(r"^earnings_iv_crush/"),
        "sys.path manipulation inside the package: import through the package instead.",
    ),
    (
        re.compile(r"alpaca", re.IGNORECASE),
        re.compile(r"^research/.*\.py$"),
        "Alpaca end-of-day data in research code: never use it to build selection features; it "
        "leaks relative to a 15:59 decision.",
    ),
    (
        # Code that would create or remove the marker, not prose that names it.
        re.compile(
            r"(touch|New-Item|write_text|write_bytes|unlink|Remove-Item|open\().{0,80}TRANSMIT_OK"
            r"|TRANSMIT_OK.{0,40}\.(write_text|write_bytes|touch|unlink)\("
        ),
        re.compile(r"^(?!\.claude/|tests/).*\.(py|ps1|sh)$"),
        "code that creates or removes TRANSMIT_OK: an agent never touches the transmit marker.",
    ),
]

EXEMPT = re.compile(r"^(tests/|\.claude/hooks/)")

FROZEN = [
    (
        re.compile(r"^research/[^/]+/preregs/"),
        "this is a frozen pre-registration: its hash is recorded and tests/test_preregistrations.py "
        "will fail. Revert, and write a dated amendment file instead.",
    ),
    (
        re.compile(r"^research/[a-z_]+/[a-z0-9_]+\.py$"),
        "this is a closed, frozen study: editing its logic breaks the reproducibility of a "
        "recorded result. Start new work from research/_template/.",
    ),
    (
        re.compile(r"^earnings_iv_crush/live/|^scripts/paper_trade_ibkr\.py$"),
        "the order path: add or update fake-gateway tests in tests/live/ and attach a dry-run log "
        "from a real gateway to the pull request.",
    ),
]


def _relpath(path: str, root: str) -> str:
    p = path.replace("\\", "/")
    r = root.replace("\\", "/").rstrip("/") + "/"
    return p[len(r) :] if p.lower().startswith(r.lower()) else p


def warnings_for(payload: dict[str, Any], root: str = "") -> list[str]:
    """Warnings for one Edit or Write call; empty when nothing matches."""
    tool_input = payload.get("tool_input") or {}
    path = _relpath(str(tool_input.get("file_path", "")), root)
    added = "\n".join(
        str(tool_input.get(k, "")) for k in ("new_string", "content") if tool_input.get(k)
    )
    for edit in tool_input.get("edits") or []:
        added += "\n" + str(edit.get("new_string", ""))
    out = [f"{path}: {msg}" for pat, msg in FROZEN if pat.search(path)]
    # Tests and the hooks themselves contain these patterns on purpose.
    if not EXEMPT.search(path):
        out += [
            f"{path}: {msg}"
            for pattern, scope, msg in CHECKS
            if scope.search(path) and pattern.search(added)
        ]
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    warnings = warnings_for(payload, payload.get("cwd", ""))
    if warnings:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": "Project checks:\n- " + "\n- ".join(warnings),
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
