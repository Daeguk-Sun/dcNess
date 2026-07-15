"""Regression tests for issue pre-create validation (#667)."""
from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
import json
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
    - [ ] [command] Invalid bodies fail before issue creation when the validator exits non-zero.
    - [ ] [agent-read] The issue brief describes the validation boundary without implementation details.

    **Human verification / 사람 확인 안내:**
    - None.

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


def run_node(expression: str) -> object:
    code = textwrap.dedent(
        f"""
        import * as issueBody from {json.dumps(SCRIPT.as_posix())};
        const result = {expression};
        console.log(JSON.stringify(result));
        """
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", code],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(completed.stdout)


class IssueBodyValidationTests(unittest.TestCase):
    def test_field_parser_is_exported_for_lifecycle_selection(self) -> None:
        body = "**IssueType:** story\n**Priority:** critical\n"

        result = run_node(
            f"issueBody.parseField({json.dumps(body)}, 'Priority')"
        )

        self.assertEqual("critical", result)

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

    def test_close_audit_rejects_unchecked_heading_acceptance_criteria(self) -> None:
        body = textwrap.dedent(
            """
            ## Acceptance criteria

            - [ ] [command] The close audit detects this unchecked criterion.
            """
        ).strip()

        result = run_validator(
            body,
            "--acceptance-only",
            "--require-complete",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("unchecked acceptance criteria remain: 1", result.stderr)

    def test_close_audit_counts_asterisk_acceptance_checkbox(self) -> None:
        body = textwrap.dedent(
            """
            **Acceptance criteria:**
            * [ ] [command] The close audit counts an asterisk checklist item.
            """
        ).strip()

        result = run_validator(
            body,
            "--acceptance-only",
            "--require-complete",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("unchecked acceptance criteria remain: 1", result.stderr)

    def test_close_audit_rejects_unclassified_criteria(self) -> None:
        legacy_body = textwrap.dedent(
            """
            **Acceptance criteria:**
            - [x] 정상 동작한다.
            - [x] 사용자가 최종 시각 결과를 확인한다.
            """
        ).strip()

        result = run_validator(
            legacy_body,
            "--acceptance-only",
            "--require-complete",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("must declare [command] or [agent-read]", result.stderr)

    def test_close_audit_rejects_issue_without_acceptance_section(self) -> None:
        legacy_story_body = textwrap.dedent(
            """
            **As a** user,
            **I want** the old story format,
            **So that** existing projects remain valid.

            **완료 시 확인 가능한 동작**: 기존 smoke 결과를 확인한다.
            """
        ).strip()

        result = run_validator(
            legacy_story_body,
            "--acceptance-only",
            "--require-complete",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("must contain at least one checklist item", result.stderr)

    def test_acceptance_criterion_requires_agent_verification_class(self) -> None:
        body = VALID_BODY.replace(
            "[command] Invalid bodies fail before issue creation when the validator exits non-zero.",
            "Invalid bodies fail before issue creation.",
        )

        result = run_validator(body, "--labels", "feature")

        self.assertEqual(1, result.returncode)
        self.assertIn("[command] or [agent-read]", result.stderr)

    def test_generic_acceptance_criterion_is_rejected(self) -> None:
        body = VALID_BODY.replace(
            "[agent-read] The issue brief describes the validation boundary without implementation details.",
            "[agent-read] 구현이 완료된다.",
        )

        result = run_validator(body, "--labels", "feature")

        self.assertEqual(1, result.returncode)
        self.assertIn("generic acceptance criterion", result.stderr)

    def test_human_verification_must_not_use_checkboxes(self) -> None:
        body = VALID_BODY.replace(
            "**Human verification / 사람 확인 안내:**\n- None.",
            "**Human verification / 사람 확인 안내:**\n- [ ] A person approves the visual result.",
        )

        result = run_validator(body, "--labels", "feature")

        self.assertEqual(1, result.returncode)
        self.assertIn("human verification", result.stderr)

    def test_acceptance_only_close_audit_supports_story_issue_format(self) -> None:
        story_body = textwrap.dedent(
            """
            **As a** creator,
            **I want** to render a video,
            **So that** I can publish it.

            **Acceptance criteria:**
            - [x] AC-001 [command]: Given a prompt, When rendering finishes, Then the command exits zero.
            - [x] AC-1002 [agent-read]: Given the output, When metadata is read, Then provenance is present.
            """
        ).strip()

        result = run_validator(
            story_body,
            "--acceptance-only",
            "--require-complete",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS — acceptance criteria complete (2)", result.stdout)
        self.assertNotIn("REVIEW", result.stdout)

    def test_story_human_verification_checkbox_is_rejected(self) -> None:
        story_body = textwrap.dedent(
            """
            **Acceptance criteria:**
            - [x] AC-001 [command]: Given input, When the test runs, Then it exits zero.

            **사람 확인 안내:**
            - [ ] 사람이 시각 결과를 승인한다.
            """
        ).strip()

        result = run_validator(
            story_body,
            "--acceptance-only",
            "--require-complete",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("human verification", result.stderr)

    def test_heading_human_verification_plus_checkbox_is_rejected(self) -> None:
        story_body = textwrap.dedent(
            """
            ## Acceptance criteria
            - [x] AC-001 [command]: Given input, When the test runs, Then it exits zero.

            ## 사람 확인 안내
            + [ ] 사람이 시각 결과를 승인한다.
            """
        ).strip()

        result = run_validator(
            story_body,
            "--acceptance-only",
            "--require-complete",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("human verification", result.stderr)


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
        self.assertIn("AC 또는 Acceptance criteria가 없는 body는 실패", text)

        for relative in ("CLAUDE.md", "skills/impl/SKILL.md", "skills/impl-loop/SKILL.md"):
            skill = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("현행 typed AC로 갱신", skill, relative)
            self.assertIn("임의 추론", skill, relative)

    def test_workflow_router_mentions_non_to_issue_agent_creation_still_validates(self) -> None:
        text = (ROOT / "docs" / "plugin" / "workflow-router.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("check_issue_body.mjs", text)
        self.assertIn("/to-issue 외", text)


if __name__ == "__main__":
    unittest.main()
