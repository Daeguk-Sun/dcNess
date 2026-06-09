"""Regression tests for GitHub Project lifecycle bootstrap (#663)."""
from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "github_project_lifecycle.mjs"


STANDARD_FIELDS = [
    {
        "name": "Status",
        "id": "fld-status",
        "dataType": "SINGLE_SELECT",
        "options": [
            {"name": "Todo", "id": "opt-todo"},
            {"name": "In progress", "id": "opt-inprog"},
            {"name": "Done", "id": "opt-done"},
        ],
    },
    {
        "name": "IssueType",
        "id": "fld-type",
        "dataType": "SINGLE_SELECT",
        "options": [
            {"name": "epic", "id": "opt-epic"},
            {"name": "feature", "id": "opt-feature"},
            {"name": "story", "id": "opt-story"},
            {"name": "task", "id": "opt-task"},
            {"name": "subTask", "id": "opt-subtask"},
            {"name": "bug", "id": "opt-bug"},
        ],
    },
    {
        "name": "Priority",
        "id": "fld-prio",
        "dataType": "SINGLE_SELECT",
        "options": [
            {"name": "blocker", "id": "opt-blocker"},
            {"name": "critical", "id": "opt-critical"},
            {"name": "major", "id": "opt-major"},
            {"name": "minor", "id": "opt-minor"},
            {"name": "trivial", "id": "opt-trivial"},
        ],
    },
]


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

    def test_plan_registration_for_new_item_adds_and_sets_all_three(self) -> None:
        result = run_node(
            "lifecycle.planRegistration({"
            "item: null,"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'epic'"
            "})"
        )

        self.assertTrue(result["needsAdd"])
        set_map = {entry["fieldName"]: entry["optionName"] for entry in result["sets"]}
        self.assertEqual(
            {"Status": "Todo", "IssueType": "epic", "Priority": "major"},
            set_map,
        )

    def test_plan_registration_for_story_uses_story_issue_type(self) -> None:
        result = run_node(
            "lifecycle.planRegistration({"
            "item: null,"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'story'"
            "})"
        )

        set_map = {entry["fieldName"]: entry["optionName"] for entry in result["sets"]}
        self.assertEqual("story", set_map["IssueType"])
        self.assertEqual("Todo", set_map["Status"])
        self.assertEqual("major", set_map["Priority"])

    def test_plan_registration_skips_fields_already_correct(self) -> None:
        item = {"status": "Todo", "issueType": "epic", "priority": "major"}

        result = run_node(
            "lifecycle.planRegistration({"
            f"item: {json.dumps(item)},"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'epic'"
            "})"
        )

        self.assertFalse(result["needsAdd"])
        self.assertEqual([], result["sets"])

    def test_plan_registration_sets_only_drifted_field(self) -> None:
        item = {"status": "In progress", "issueType": "epic", "priority": "major"}

        result = run_node(
            "lifecycle.planRegistration({"
            f"item: {json.dumps(item)},"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'epic'"
            "})"
        )

        self.assertFalse(result["needsAdd"])
        self.assertEqual(
            [
                {
                    "fieldName": "Status",
                    "optionName": "Todo",
                    "fieldId": "fld-status",
                    "optionId": "opt-todo",
                }
            ],
            result["sets"],
        )

    def test_plan_registration_preserve_existing_keeps_triaged_state(self) -> None:
        # 백필 회귀 가드 (#669): preserveExisting 이면 사용자가 옮긴 In progress /
        # 바뀐 priority 를 Todo/major 로 되돌리지 않는다 (이미 값 있으면 보존).
        item = {"status": "In progress", "issueType": "story", "priority": "minor"}

        result = run_node(
            "lifecycle.planRegistration({"
            f"item: {json.dumps(item)},"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'story',"
            "preserveExisting: true"
            "})"
        )

        self.assertFalse(result["needsAdd"])
        self.assertEqual([], result["sets"])

    def test_plan_registration_preserve_existing_fills_only_empty_field(self) -> None:
        # preserveExisting 이라도 비어있는 필드(부분 등록 실패 잔여)는 채운다.
        item = {"issueType": "story", "priority": "major"}  # status 미설정

        result = run_node(
            "lifecycle.planRegistration({"
            f"item: {json.dumps(item)},"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'story',"
            "preserveExisting: true"
            "})"
        )

        self.assertFalse(result["needsAdd"])
        set_map = {entry["fieldName"]: entry["optionName"] for entry in result["sets"]}
        self.assertEqual({"Status": "Todo"}, set_map)

    def test_plan_registration_preserve_existing_new_item_sets_all(self) -> None:
        # 보드에 없던 item 은 preserveExisting 여도 풀 등록 (Todo/story/major).
        result = run_node(
            "lifecycle.planRegistration({"
            "item: null,"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'story',"
            "preserveExisting: true"
            "})"
        )

        self.assertTrue(result["needsAdd"])
        set_map = {entry["fieldName"]: entry["optionName"] for entry in result["sets"]}
        self.assertEqual(
            {"Status": "Todo", "IssueType": "story", "Priority": "major"},
            set_map,
        )

    def test_plan_registration_preserve_existing_still_corrects_issue_type(self) -> None:
        # IssueType 은 정체성이라 preserve 모드여도 drift 교정 (Status/Priority 만 보존).
        item = {"status": "In progress", "issueType": "epic", "priority": "minor"}

        result = run_node(
            "lifecycle.planRegistration({"
            f"item: {json.dumps(item)},"
            f"fields: {json.dumps(STANDARD_FIELDS)},"
            "issueType: 'story',"
            "preserveExisting: true"
            "})"
        )

        self.assertFalse(result["needsAdd"])
        set_map = {entry["fieldName"]: entry["optionName"] for entry in result["sets"]}
        self.assertEqual({"IssueType": "story"}, set_map)

    def test_plan_registration_rejects_unknown_issue_type(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            run_node(
                "lifecycle.planRegistration({"
                "item: null,"
                f"fields: {json.dumps(STANDARD_FIELDS)},"
                "issueType: 'nope'"
                "})"
            )

    def test_plan_registration_requires_issue_type(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            run_node(
                "lifecycle.planRegistration({"
                "item: null,"
                f"fields: {json.dumps(STANDARD_FIELDS)}"
                "})"
            )

    def test_plan_registration_throws_when_board_option_missing(self) -> None:
        broken_fields = [
            {
                "name": "Status",
                "id": "fld-status",
                "dataType": "SINGLE_SELECT",
                "options": [{"name": "Done", "id": "opt-done"}],
            },
            {
                "name": "IssueType",
                "id": "fld-type",
                "dataType": "SINGLE_SELECT",
                "options": [{"name": "epic", "id": "opt-epic"}],
            },
            {
                "name": "Priority",
                "id": "fld-prio",
                "dataType": "SINGLE_SELECT",
                "options": [{"name": "major", "id": "opt-major"}],
            },
        ]

        with self.assertRaises(subprocess.CalledProcessError):
            run_node(
                "lifecycle.planRegistration({"
                "item: null,"
                f"fields: {json.dumps(broken_fields)},"
                "issueType: 'epic'"
                "})"
            )

    def test_resolve_validation_relaxes_only_preserved_non_empty_field(self) -> None:
        # preserve + 원래 값이 있던 필드 → 완화('any')로 보존값을 drift 오판 안 함.
        item = {"status": "In progress", "priority": "minor"}
        result = run_node(
            "lifecycle.resolveValidationExpectations({"
            f"item: {json.dumps(item)},"
            "preserveExisting: true"
            "})"
        )
        self.assertEqual(
            {"validateStatus": "any", "validatePriority": "any"}, result
        )

    def test_resolve_validation_keeps_strict_for_blank_field(self) -> None:
        # 백필 회귀 가드 (#669 round3): preserve 라도 원래 비어있던 Status 는 채우기 대상이라
        # strict('Todo') 유지 → apply 가 실제로 채웠는지(부분 백필 실패) 검증한다.
        item = {"priority": "major"}  # status 미설정 → 채움 대상
        result = run_node(
            "lifecycle.resolveValidationExpectations({"
            f"item: {json.dumps(item)},"
            "preserveExisting: true"
            "})"
        )
        self.assertEqual(
            {"validateStatus": "Todo", "validatePriority": "any"}, result
        )

    def test_resolve_validation_new_item_all_strict(self) -> None:
        # 신규 add(item 없음)는 보존 대상 없음 → 전부 strict.
        result = run_node(
            "lifecycle.resolveValidationExpectations({"
            "item: null,"
            "preserveExisting: true"
            "})"
        )
        self.assertEqual(
            {"validateStatus": "Todo", "validatePriority": "major"}, result
        )

    def test_resolve_validation_non_preserve_all_strict(self) -> None:
        # preserve 아님(fresh) → 기존 값 있어도 전부 strict (Todo/major 강제 검증).
        item = {"status": "In progress", "priority": "minor"}
        result = run_node(
            "lifecycle.resolveValidationExpectations({"
            f"item: {json.dumps(item)},"
            "preserveExisting: false"
            "})"
        )
        self.assertEqual(
            {"validateStatus": "Todo", "validatePriority": "major"}, result
        )


if __name__ == "__main__":
    unittest.main()
