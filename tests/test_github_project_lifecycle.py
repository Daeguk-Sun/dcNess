"""Regression tests for GitHub Project lifecycle bootstrap (#663)."""
from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "github_project_lifecycle.mjs"


def run_node(expression: str) -> dict:
    code = textwrap.dedent(
        f"""
        import * as lifecycle from {json.dumps(SCRIPT.as_posix())};
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


class GithubProjectLifecycleScriptTests(unittest.TestCase):
    def test_standard_project_fields_require_all_options(self) -> None:
        fields = [
            {
                "name": "Status",
                "dataType": "SINGLE_SELECT",
                "options": [
                    {"name": "Todo"},
                    {"name": "In progress"},
                    {"name": "Done"},
                ],
            },
            {
                "name": "IssueType",
                "dataType": "SINGLE_SELECT",
                "options": [
                    {"name": "epic"},
                    {"name": "feature"},
                    {"name": "story"},
                    {"name": "task"},
                    {"name": "subTask"},
                    {"name": "bug"},
                ],
            },
            {
                "name": "Priority",
                "dataType": "SINGLE_SELECT",
                "options": [
                    {"name": "blocker"},
                    {"name": "critical"},
                    {"name": "major"},
                    {"name": "minor"},
                    {"name": "trivial"},
                ],
            },
        ]

        result = run_node(
            f"lifecycle.validateProjectFields({json.dumps(fields)})"
        )

        self.assertEqual([], result["missingFields"])
        self.assertEqual([], result["missingOptions"])
        self.assertTrue(result["ok"])

    def test_project_field_validation_accepts_gh_project_v2_type_names(self) -> None:
        fields = [
            {
                "name": "Status",
                "type": "ProjectV2SingleSelectField",
                "options": [
                    {"name": "Todo"},
                    {"name": "In progress"},
                    {"name": "Done"},
                ],
            },
            {
                "name": "IssueType",
                "type": "ProjectV2SingleSelectField",
                "options": [
                    {"name": "epic"},
                    {"name": "feature"},
                    {"name": "story"},
                    {"name": "task"},
                    {"name": "subTask"},
                    {"name": "bug"},
                ],
            },
            {
                "name": "Priority",
                "type": "ProjectV2SingleSelectField",
                "options": [
                    {"name": "blocker"},
                    {"name": "critical"},
                    {"name": "major"},
                    {"name": "minor"},
                    {"name": "trivial"},
                ],
            },
        ]

        result = run_node(
            f"lifecycle.validateProjectFields({json.dumps(fields)})"
        )

        self.assertTrue(result["ok"])
        self.assertEqual([], result["wrongTypeFields"])

    def test_project_field_validation_reports_missing_status_option(self) -> None:
        fields = [
            {
                "name": "Status",
                "dataType": "SINGLE_SELECT",
                "options": [{"name": "Todo"}, {"name": "Done"}],
            },
        ]

        result = run_node(
            f"lifecycle.validateProjectFields({json.dumps(fields)})"
        )

        self.assertFalse(result["ok"])
        self.assertIn("IssueType", result["missingFields"])
        self.assertIn("Priority", result["missingFields"])
        self.assertIn(
            {"field": "Status", "option": "In progress"},
            result["missingOptions"],
        )

    def test_issue_type_label_validation_uses_same_six_values(self) -> None:
        labels = [
            {"name": "epic"},
            {"name": "feature"},
            {"name": "story"},
            {"name": "task"},
            {"name": "subTask"},
            {"name": "bug"},
        ]

        result = run_node(f"lifecycle.validateIssueTypeLabels({json.dumps(labels)})")

        self.assertTrue(result["ok"])
        self.assertEqual([], result["missingLabels"])

    def test_completion_candidates_ignore_part_of_references(self) -> None:
        body = """
        ## 관련 이슈 번호
        Part of #10
        Closes #11
        fixes alruminum/dcNess#12
        Resolves #13, closes #14
        """

        result = run_node(
            f"lifecycle.parseCompletionIssueNumbers({json.dumps(body)})"
        )

        self.assertEqual({"numbers": [11, 12, 13, 14]}, result)

    def test_completion_candidates_include_comma_separated_issue_refs(self) -> None:
        body = """
        Closes #101, #102
        Fixes #103 and #104
        Resolves alruminum/dcNess#105, #106
        """

        result = run_node(
            f"lifecycle.parseCompletionIssueNumbers({json.dumps(body)})"
        )

        self.assertEqual({"numbers": [101, 102, 103, 104, 105, 106]}, result)

    def test_completion_refs_preserve_repo_identity(self) -> None:
        body = """
        Part of other/repo#100
        Closes other/repo#101, #102
        Fixes #103
        """

        result = run_node(
            f"lifecycle.parseCompletionIssueRefs({json.dumps(body)}, 'alruminum/dcNess')"
        )

        self.assertEqual(
            {
                "refs": [
                    {"repo": "other/repo", "number": 101},
                    {"repo": "alruminum/dcNess", "number": 102},
                    {"repo": "alruminum/dcNess", "number": 103},
                ]
            },
            result,
        )

    def test_completion_refs_do_not_include_part_of_segment_on_same_line(self) -> None:
        body = "Closes #663, Part of #662"

        result = run_node(
            f"lifecycle.parseCompletionIssueRefs({json.dumps(body)}, 'alruminum/dcNess')"
        )

        self.assertEqual(
            {"refs": [{"repo": "alruminum/dcNess", "number": 663}]},
            result,
        )

    def test_project_item_lookup_matches_repo_and_issue_number(self) -> None:
        items = [
            {
                "id": "wrong",
                "content": {"number": 663, "repository": "other/repo"},
            },
            {
                "id": "right",
                "content": {"number": 663, "repository": "alruminum/dcNess"},
            },
        ]

        result = run_node(
            f"lifecycle.findProjectItem({json.dumps(items)}, "
            "{repo: 'alruminum/dcNess', number: 663})"
        )

        self.assertEqual("right", result["id"])

    def test_completion_refs_can_apply_default_repo_after_context_load(self) -> None:
        refs = [{"repo": None, "number": 663}]

        result = run_node(
            f"lifecycle.applyDefaultRepoToRefs({json.dumps(refs)}, 'alruminum/dcNess')"
        )

        self.assertEqual([{"repo": "alruminum/dcNess", "number": 663}], result)

    def test_resolve_completion_refs_uses_detected_repo_when_cli_repo_missing(self) -> None:
        result = run_node(
            "lifecycle.resolveCompletionRefsForProject('Closes #663', null, 'alruminum/dcNess')"
        )

        self.assertEqual(
            [{"repo": "alruminum/dcNess", "number": 663}],
            result,
        )

    def test_pr_view_args_include_target_repo(self) -> None:
        result = run_node(
            "lifecycle.prViewArgs({pr: 17, repo: 'alruminum/dcNess'})"
        )

        self.assertEqual(
            [
                "pr",
                "view",
                "17",
                "--repo",
                "alruminum/dcNess",
                "--json",
                "body,closingIssuesReferences",
            ],
            result,
        )

    def test_issue_type_drift_message_names_issue_field_and_label(self) -> None:
        result = run_node(
            "lifecycle.detectIssueTypeDrift({"
            "issueNumber: 42,"
            "projectIssueType: 'feature',"
            "labels: ['bug']"
            "})"
        )

        self.assertFalse(result["ok"])
        self.assertIn("issue #42", result["message"])
        self.assertIn("Project IssueType=feature", result["message"])
        self.assertIn("repo label=bug", result["message"])

    def test_status_drift_message_can_name_repo_scoped_issue(self) -> None:
        result = run_node(
            "lifecycle.statusDriftMessage({"
            "repo: 'other/repo',"
            "issueNumber: 42,"
            "expected: 'Done',"
            "actual: 'Todo'"
            "})"
        )

        self.assertIn("issue other/repo#42", result)
        self.assertIn("Project field Status", result)

    def test_project_item_field_value_reads_gh_item_top_level_fields(self) -> None:
        item = {
            "status": "Todo",
            "issueType": "feature",
            "priority": "major",
        }

        result = run_node(
            "{"
            f"status: lifecycle.projectItemFieldValue({json.dumps(item)}, 'Status'),"
            f"issueType: lifecycle.projectItemFieldValue({json.dumps(item)}, 'IssueType'),"
            f"priority: lifecycle.projectItemFieldValue({json.dumps(item)}, 'Priority')"
            "}"
        )

        self.assertEqual(
            {"status": "Todo", "issueType": "feature", "priority": "major"},
            result,
        )

    def test_registration_validation_requires_todo_status(self) -> None:
        item = {
            "status": "In progress",
            "issueType": "feature",
            "priority": "major",
        }

        result = run_node(
            "lifecycle.validateIssueProjectRegistration({"
            "repo: 'alruminum/dcNess',"
            "issueNumber: 663,"
            f"item: {json.dumps(item)},"
            "labels: ['feature']"
            "})"
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                "issue alruminum/dcNess#663" in message
                and "expected=Todo" in message
                and "actual=In progress" in message
                for message in result["messages"]
            )
        )

    def test_registration_validation_requires_priority_value(self) -> None:
        item = {
            "status": "Todo",
            "issueType": "feature",
            "priority": None,
        }

        result = run_node(
            "lifecycle.validateIssueProjectRegistration({"
            "issueNumber: 663,"
            f"item: {json.dumps(item)},"
            "labels: ['feature']"
            "})"
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                "Project Priority=<unset>" in message
                for message in result["messages"]
            )
        )

    def test_registration_validation_can_pin_selected_issue_type_and_priority(self) -> None:
        item = {
            "status": "Todo",
            "issueType": "bug",
            "priority": "minor",
        }

        result = run_node(
            "lifecycle.validateIssueProjectRegistration({"
            "issueNumber: 663,"
            f"item: {json.dumps(item)},"
            "labels: ['bug'],"
            "expectedIssueType: 'feature',"
            "expectedPriority: 'major'"
            "})"
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                "Project IssueType=bug" in message
                and "expected=feature" in message
                for message in result["messages"]
            )
        )
        self.assertTrue(
            any(
                "Project Priority=minor" in message
                and "expected=major" in message
                for message in result["messages"]
            )
        )

    def test_registration_validation_accepts_expected_status_override(self) -> None:
        item = {
            "status": "In progress",
            "issueType": "feature",
            "priority": "major",
        }

        result = run_node(
            "lifecycle.validateIssueProjectRegistration({"
            "issueNumber: 663,"
            f"item: {json.dumps(item)},"
            "labels: ['feature'],"
            "expectedStatus: 'In progress'"
            "})"
        )

        self.assertTrue(result["ok"])

    def test_registration_validation_can_skip_lifecycle_fields_for_drift_only(self) -> None:
        item = {
            "status": "In progress",
            "issueType": "feature",
            "priority": None,
        }

        result = run_node(
            "lifecycle.validateIssueProjectRegistration({"
            "issueNumber: 663,"
            f"item: {json.dumps(item)},"
            "labels: ['feature'],"
            "expectedStatus: 'any',"
            "expectedPriority: 'any'"
            "})"
        )

        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
