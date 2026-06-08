"""Regression tests for issue pre-create validation (#667)."""
from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_issue_body.mjs"


VALID_BODY = textwrap.dedent(
    """
    ## Issue Brief

    **IssueType:** feature
    **Priority:** major
    **Summary:**
    Validate issue body before agent workflows create GitHub issues.

    **Current behavior / Context:**
    Agents can prepare issue text from an existing conversation.

    **Desired behavior / What to build:**
    Agents run a local validator before gh issue create.

    **Key interfaces / Contracts:**
    - scripts/check_issue_body.mjs validates Issue Brief structure and labels.

    **Acceptance criteria:**
    - [ ] Invalid bodies fail before issue creation.

    **Blocked by:**
    None - can start immediately

    **Out of scope:**
    - Blocking human GitHub UI issue creation.
    """
).strip()


def run_validator(body: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(SCRIPT), "--stdin", *args],
        cwd=ROOT,
        input=body,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_validator_file(body: str, *args: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(body)
        path = handle.name
    try:
        return subprocess.run(
            ["node", str(SCRIPT), "--body-file", path, *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    finally:
        Path(path).unlink(missing_ok=True)


class IssueBodyValidationTests(unittest.TestCase):
    def test_valid_issue_brief_with_matching_label_passes(self) -> None:
        result = run_validator(VALID_BODY, "--labels", "feature")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_valid_issue_brief_body_file_passes(self) -> None:
        result = run_validator_file(VALID_BODY, "--labels", "feature")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_missing_required_issue_brief_section_fails(self) -> None:
        body = VALID_BODY.replace("**Acceptance criteria:**", "**Checks:**")

        result = run_validator(body, "--labels", "feature")

        self.assertEqual(1, result.returncode)
        self.assertIn("Acceptance criteria", result.stderr)

    def test_invalid_issue_type_fails(self) -> None:
        body = VALID_BODY.replace("**IssueType:** feature", "**IssueType:** chore")

        result = run_validator(body, "--labels", "chore")

        self.assertEqual(1, result.returncode)
        self.assertIn("IssueType=chore", result.stderr)

    def test_empty_issue_type_value_fails(self) -> None:
        body = VALID_BODY.replace("**IssueType:** feature", "**IssueType:**")

        result = run_validator(body, "--labels", "feature")

        self.assertEqual(1, result.returncode)
        self.assertIn("IssueType=<empty>", result.stderr)

    def test_invalid_priority_fails(self) -> None:
        body = VALID_BODY.replace("**Priority:** major", "**Priority:** urgent")

        result = run_validator(body, "--labels", "feature")

        self.assertEqual(1, result.returncode)
        self.assertIn("Priority=urgent", result.stderr)

    def test_empty_priority_value_fails(self) -> None:
        body = VALID_BODY.replace("**Priority:** major", "**Priority:**")

        result = run_validator(body, "--labels", "feature")

        self.assertEqual(1, result.returncode)
        self.assertIn("Priority=<empty>", result.stderr)

    def test_label_must_match_issue_type_when_labels_are_provided(self) -> None:
        result = run_validator(VALID_BODY, "--labels", "bug")

        self.assertEqual(1, result.returncode)
        self.assertIn("repo label=bug", result.stderr)
        self.assertIn("IssueType=feature", result.stderr)

    def test_exactly_one_issue_type_label_is_required_when_labels_are_provided(self) -> None:
        result = run_validator(VALID_BODY, "--labels", "feature,bug")

        self.assertEqual(1, result.returncode)
        self.assertIn("exactly one IssueType label", result.stderr)

    def test_labels_are_required_by_default_for_create_preflight(self) -> None:
        result = run_validator(VALID_BODY)

        self.assertEqual(1, result.returncode)
        self.assertIn("exactly one IssueType label", result.stderr)

    def test_body_only_preflight_allows_missing_labels_when_explicit(self) -> None:
        result = run_validator(VALID_BODY, "--body-only")

        self.assertEqual(0, result.returncode, result.stderr)


class IssueBodyValidationDocsTests(unittest.TestCase):
    def test_issue_lifecycle_documents_pre_create_validation_not_hard_gate(self) -> None:
        text = (ROOT / "docs" / "plugin" / "issue-lifecycle.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Issue pre-create validation", text)
        self.assertIn("scripts/check_issue_body.mjs", text)
        self.assertIn("gh issue create", text)
        self.assertIn("GitHub UI", text)
        self.assertIn("hard gate", text)

    def test_workflow_router_mentions_non_to_issue_agent_creation_still_validates(self) -> None:
        text = (ROOT / "docs" / "plugin" / "workflow-router.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("check_issue_body.mjs", text)
        self.assertIn("/to-issue 외", text)


if __name__ == "__main__":
    unittest.main()
