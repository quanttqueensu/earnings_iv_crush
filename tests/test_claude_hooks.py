"""
test_claude_hooks.py
The Claude Code hooks shipped in ``.claude/hooks`` behave as documented.

The edit check must flag each defect class on the text just added, warn on frozen files and the
order path, stay quiet on clean edits, and never fail on malformed input. The session hook must
exit zero and print the orient report and the reminders.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load("post_edit_check")


def _edit(path: str, new: str) -> dict:
    return {"tool_input": {"file_path": str(ROOT / path), "new_string": new}, "cwd": str(ROOT)}


@pytest.mark.parametrize(
    "path, text, needle",
    [
        ("research/x/2026-10-20-a/study.py", "sr * np.sqrt(252)", "square root of 252"),
        ("earnings_iv_crush/engine/x.py", "df.fillna(0)", "fillna"),
        ("earnings_iv_crush/engine/x.py", "try:\n    f()\nexcept:\n    pass", "swallowed"),
        ("earnings_iv_crush/data/x.py", "sys.path.insert(0, p)", "sys.path"),
        ("research/selection/2026-10-20-a/study.py", "from data import alpaca_options", "Alpaca"),
        ("scripts/x.py", "Path('_private/TRANSMIT_OK').write_text('')", "transmit marker"),
    ],
)
def test_each_defect_class_is_flagged(path: str, text: str, needle: str) -> None:
    warnings = check.warnings_for(_edit(path, text), str(ROOT))
    assert any(needle in w for w in warnings), warnings


@pytest.mark.parametrize(
    "path, needle",
    [
        ("research/selection/preregs/p1_skew_reaction_prereg.md", "frozen pre-registration"),
        ("research/selection/research_ml_zoo.py", "closed, frozen study"),
        ("earnings_iv_crush/live/ladder.py", "order path"),
    ],
)
def test_frozen_files_and_the_order_path_warn(path: str, needle: str) -> None:
    warnings = check.warnings_for(_edit(path, "x = 1"), str(ROOT))
    assert any(needle in w for w in warnings), warnings


def test_clean_edit_and_prose_are_quiet() -> None:
    assert (
        check.warnings_for(_edit("docs/RUNBOOK.md", "Create TRANSMIT_OK yourself."), str(ROOT))
        == []
    )
    assert check.warnings_for(_edit("earnings_iv_crush/engine/x.py", "y = x + 1"), str(ROOT)) == []


def test_edit_hook_never_fails_on_bad_input() -> None:
    out = subprocess.run(
        [sys.executable, str(HOOKS / "post_edit_check.py")],
        input="not json",
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out.returncode == 0 and out.stdout == ""


def test_edit_hook_emits_additional_context() -> None:
    out = subprocess.run(
        [sys.executable, str(HOOKS / "post_edit_check.py")],
        input=json.dumps(_edit("earnings_iv_crush/engine/x.py", "df.fillna(0)")),
        capture_output=True,
        text=True,
        timeout=20,
    )
    body = json.loads(out.stdout)
    assert body["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "fillna" in body["hookSpecificOutput"]["additionalContext"]


def test_session_hook_prints_orient_and_reminders() -> None:
    out = subprocess.run(
        [sys.executable, str(HOOKS / "session_context.py")],
        capture_output=True,
        text=True,
        timeout=60,
        env={"CLAUDE_PROJECT_DIR": str(ROOT), "PATH": "", "SYSTEMROOT": "C:\\Windows"},
        cwd=ROOT,
    )
    assert out.returncode == 0
    assert "Before acting" in out.stdout
    assert "REPO" in out.stdout or "UNMEASURED" in out.stdout
