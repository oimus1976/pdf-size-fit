from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_public_pr_workflow_uses_untrusted_safe_trigger_and_read_only_token() -> None:
    text = _workflow_text()

    assert "pull_request_target" not in text
    assert "permissions:\n  contents: read\n" in text
    assert "secrets." not in text


def test_all_actions_are_pinned_to_full_commit_shas() -> None:
    text = _workflow_text()
    uses_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("- uses:")]

    assert uses_lines
    for line in uses_lines:
        action_ref = line.split("#", 1)[0].strip().removeprefix("- uses:").strip()
        assert "@" in action_ref
        _, ref = action_ref.rsplit("@", 1)
        assert FULL_SHA.fullmatch(ref), line


def test_checkout_does_not_persist_credentials_and_job_is_bounded() -> None:
    text = _workflow_text()

    assert "persist-credentials: false" in text
    assert re.search(r"(?m)^\s+timeout-minutes:\s*[1-9][0-9]*\s*$", text)
