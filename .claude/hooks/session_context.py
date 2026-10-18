"""
session_context.py
SessionStart hook: put the measured project state in front of the agent before it does anything.

Runs ``orient`` (without hashing the caches, so it stays fast) and prints its report followed by
the three reminders that matter most. Whatever is printed becomes session context. The hook never
fails the session: if orient cannot run, it says so and exits zero.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))

REMINDERS = """\
Before acting: read docs/SYSTEM.md and docs/RESEARCH_STATE.md (the closed list).
Never transmit an order, create _private/TRANSMIT_OK, or remove HALT/STOP unless the team lead
asks in this session. Never edit research/*/preregs/. Numbers come from findings files or orient,
never memory."""


def main() -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        out = subprocess.run(
            [sys.executable, "-m", "earnings_iv_crush.ops.orient"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=25,
            env=env,
        )
        report = out.stdout.strip() or f"orient produced no output ({out.stderr.strip()[-300:]})"
    except Exception as exc:  # noqa: BLE001 - a hook must never block the session
        report = f"orient UNMEASURED: {type(exc).__name__}: {exc}"
    print(report)
    print()
    print(REMINDERS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
