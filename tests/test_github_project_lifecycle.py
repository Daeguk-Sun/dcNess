"""Regression tests for GitHub Project lifecycle bootstrap (#663)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
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
    def run_cli_with_fake_gh(self, args: list[str], fake_gh_body: str) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            log_path = tmp / "gh-calls.jsonl"
            fake_gh = bin_dir / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "log_path = Path(os.environ['GH_FAKE_LOG'])\n"
                "with log_path.open('a', encoding='utf-8') as handle:\n"
                "    handle.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                + textwrap.dedent(fake_gh_body).lstrip(),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "GH_FAKE_LOG": str(log_path),
            }
            completed = subprocess.run(
                ["node", str(SCRIPT), *args],
                cwd=ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            calls = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            return completed, calls

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

    def test_lifecycle_label_validation_requires_in_progress_label(self) -> None:
        labels = [
            {"name": "epic"},
            {"name": "feature"},
            {"name": "story"},
            {"name": "task"},
            {"name": "subTask"},
            {"name": "bug"},
        ]

        result = run_node(f"lifecycle.validateLifecycleLabels({json.dumps(labels)})")

        self.assertFalse(result["ok"])
        self.assertEqual(["in-progress"], result["missingLabels"])

    def test_select_next_candidates_uses_label_status_priority_and_epic_order(self) -> None:
        issues = [
            {
                "number": 210,
                "title": "Epic bundle is not a direct work item",
                "body": "**Priority:** blocker\n",
                "labels": [{"name": "epic"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/210",
            },
            {
                "number": 301,
                "title": "Epic 02 story 1",
                "body": "**Priority:** major\n",
                "labels": [{"name": "story"}, {"name": "epic-02-beta"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/301",
            },
            {
                "number": 201,
                "title": "Epic 01 story 1",
                "body": "**Priority:** trivial\n",
                "labels": [{"name": "story"}, {"name": "epic-01-alpha"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/201",
            },
            {
                "number": 202,
                "title": "Epic 01 story 2",
                "body": "**Priority:** minor\n",
                "labels": [{"name": "story"}, {"name": "epic-01-alpha"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/202",
            },
            {
                "number": 250,
                "title": "Manual story without epic slug",
                "body": "**Priority:** major\n",
                "labels": [{"name": "story"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/250",
            },
            {
                "number": 230,
                "title": "Critical bug",
                "body": "**Priority:** critical\n",
                "labels": [{"name": "bug"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/230",
            },
            {
                "number": 220,
                "title": "Resume this feature",
                "body": "**Priority:** trivial\n",
                "labels": [{"name": "feature"}, {"name": "in-progress"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/220",
            },
            {
                "number": 221,
                "title": "Child task under the active feature",
                "body": "**Priority:** major\nPart of #220\n",
                "labels": [{"name": "subTask"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/221",
            },
            {
                "number": 222,
                "title": "Child task whose parent is not active",
                "body": "**Priority:** major\nPart of #999\n",
                "labels": [{"name": "subTask"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/222",
            },
            {
                "number": 240,
                "title": "Feature without priority line",
                "body": "no issue brief here",
                "labels": [{"name": "feature"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/240",
            },
            {
                "number": 235,
                "title": "Minor feature",
                "body": "**Priority:** minor\n",
                "labels": [{"name": "feature"}],
                "url": "https://github.com/Daeguk-Sun/dcNess/issues/235",
            },
        ]

        result = run_node(f"lifecycle.selectNextCandidates({json.dumps(issues)})")

        self.assertEqual([220], [item["number"] for item in result["l1"]])
        self.assertEqual([221], [item["number"] for item in result["l1"][0]["subTasks"]])
        self.assertEqual([230], [item["number"] for item in result["l2"]])
        self.assertEqual(
            [
                {"label": "epic-01-alpha", "numbers": [201, 202]},
                {"label": "epic-02-beta", "numbers": [301]},
                {"label": None, "numbers": [250]},
            ],
            [
                {
                    "label": group["epicSlugLabel"],
                    "numbers": [item["number"] for item in group["items"]],
                }
                for group in result["l3"]["storyGroups"]
            ],
        )
        self.assertEqual([235, 240], [item["number"] for item in result["l3"]["feature"]])
        self.assertTrue(result["l3"]["feature"][-1]["priorityMissing"])
        self.assertEqual([210], [item["number"] for item in result["excluded"]["epic"]])
        self.assertEqual([222], [item["number"] for item in result["excluded"]["subTask"]])

    def test_next_alias_is_not_supported_after_next_work_rename(self) -> None:
        completed = subprocess.run(
            ["node", str(SCRIPT), "next"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("unknown command: next", completed.stderr)

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

    def test_lifecycle_label_state_rejects_closed_in_progress_issue(self) -> None:
        result = run_node(
            "lifecycle.validateLifecycleIssueLabels({"
            "issueNumber: 42,"
            "state: 'CLOSED',"
            "labels: ['bug', 'in-progress']"
            "})"
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any("closed issue retains in-progress label" in message for message in result["messages"])
        )

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

    def test_project_coordinate_resolution_uses_flag_env_variable_default_order(self) -> None:
        result = run_node(
            "lifecycle.resolveProjectCoordinatesFromSources({"
            "repo: 'Daeguk-Sun/dcNess',"
            "ownerArg: 'flag-owner',"
            "projectArg: '9',"
            "env: {DCNESS_PROJECT_NUMBER: '8', DCNESS_PROJECT_OWNER: 'env-owner'},"
            "variables: {DCNESS_PROJECT_NUMBER: '7', DCNESS_PROJECT_OWNER: 'var-owner'}"
            "})"
        )

        self.assertEqual(
            {"repo": "Daeguk-Sun/dcNess", "owner": "flag-owner", "project": "9"},
            result,
        )

    def test_project_coordinate_resolution_falls_back_to_env_variable_repo_owner(self) -> None:
        result = run_node(
            "lifecycle.resolveProjectCoordinatesFromSources({"
            "repo: 'Daeguk-Sun/dcNess',"
            "env: {DCNESS_PROJECT_NUMBER: '8'},"
            "variables: {DCNESS_PROJECT_NUMBER: '7'}"
            "})"
        )

        self.assertEqual(
            {"repo": "Daeguk-Sun/dcNess", "owner": "Daeguk-Sun", "project": "8"},
            result,
        )

    def test_project_coordinate_resolution_uses_repo_variable_when_env_missing(self) -> None:
        result = run_node(
            "lifecycle.resolveProjectCoordinatesFromSources({"
            "repo: 'Daeguk-Sun/dcNess',"
            "env: {},"
            "variables: {DCNESS_PROJECT_NUMBER: '7', DCNESS_PROJECT_OWNER: 'var-owner'}"
            "})"
        )

        self.assertEqual(
            {"repo": "Daeguk-Sun/dcNess", "owner": "var-owner", "project": "7"},
            result,
        )

    def test_project_coordinate_resolution_allows_missing_project_for_readonly_next(self) -> None:
        result = run_node(
            "lifecycle.resolveProjectCoordinatesFromSources({"
            "repo: 'Daeguk-Sun/dcNess',"
            "env: {},"
            "variables: {}"
            "})"
        )

        self.assertEqual(
            {"repo": "Daeguk-Sun/dcNess", "owner": "Daeguk-Sun", "project": None},
            result,
        )

    def test_summarize_board_groups_in_progress_todo_done_items(self) -> None:
        items = {
            "items": [
                {
                    "content": {
                        "number": 824,
                        "title": "Next entrypoint",
                        "repository": "Daeguk-Sun/dcNess",
                        "url": "https://github.com/Daeguk-Sun/dcNess/issues/824",
                    },
                    "status": "In progress",
                    "issueType": "feature",
                    "priority": "major",
                },
                {
                    "content": {"number": 825, "title": "Todo candidate"},
                    "fieldValues": [
                        {"field": {"name": "Status"}, "name": "Todo"},
                        {"field": {"name": "IssueType"}, "name": "story"},
                    ],
                },
                {
                    "content": {"number": 700, "title": "Done item"},
                    "status": "Done",
                },
            ]
        }

        result = run_node(f"lifecycle.summarizeBoard({json.dumps(items)})")

        self.assertEqual([824], [item["number"] for item in result["inProgress"]])
        self.assertEqual([825], [item["number"] for item in result["todo"]])
        self.assertEqual([700], [item["number"] for item in result["done"]])
        self.assertEqual("feature", result["inProgress"][0]["issueType"])

    def test_gh_calls_use_large_output_buffer_for_big_project_boards(self) -> None:
        self.assertGreaterEqual(
            run_node("({maxBuffer: lifecycle.GH_MAX_BUFFER_BYTES})")["maxBuffer"],
            64 * 1024 * 1024,
        )
        self.assertIn("maxBuffer: GH_MAX_BUFFER_BYTES", SCRIPT.read_text())

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

    def test_start_work_apply_keeps_label_success_when_project_lookup_fails(self) -> None:
        completed, calls = self.run_cli_with_fake_gh(
            [
                "start-work",
                "--repo",
                "Daeguk-Sun/dcNess",
                "--owner",
                "Daeguk-Sun",
                "--project",
                "7",
                "--issue",
                "891",
                "--apply",
            ],
            """
            args = sys.argv[1:]
            if args[:2] == ['issue', 'view']:
                print(json.dumps({
                    'number': 891,
                    'labels': [{'name': 'feature'}],
                    'state': 'OPEN',
                    'url': 'https://github.com/Daeguk-Sun/dcNess/issues/891',
                }))
                sys.exit(0)
            if args[:2] == ['label', 'create']:
                sys.exit(0)
            if args[:2] == ['issue', 'edit']:
                sys.exit(0)
            if args[:2] == ['project', 'view']:
                print('HTTP 403: resource not accessible', file=sys.stderr)
                sys.exit(1)
            print('unexpected gh call: ' + ' '.join(args), file=sys.stderr)
            sys.exit(2)
            """,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("WARN", completed.stderr)
        self.assertIn(["issue", "edit", "891", "--repo", "Daeguk-Sun/dcNess", "--add-label", "in-progress"], calls)
        self.assertLess(
            calls.index(["issue", "edit", "891", "--repo", "Daeguk-Sun/dcNess", "--add-label", "in-progress"]),
            calls.index(["project", "view", "7", "--owner", "Daeguk-Sun", "--format", "json"]),
        )

    def test_start_work_apply_fails_when_label_transition_fails(self) -> None:
        completed, calls = self.run_cli_with_fake_gh(
            [
                "start-work",
                "--repo",
                "Daeguk-Sun/dcNess",
                "--owner",
                "Daeguk-Sun",
                "--project",
                "7",
                "--issue",
                "891",
                "--apply",
            ],
            """
            args = sys.argv[1:]
            if args[:2] == ['issue', 'view']:
                print(json.dumps({
                    'number': 891,
                    'labels': [{'name': 'feature'}],
                    'state': 'OPEN',
                    'url': 'https://github.com/Daeguk-Sun/dcNess/issues/891',
                }))
                sys.exit(0)
            if args[:2] == ['label', 'create']:
                sys.exit(0)
            if args[:2] == ['issue', 'edit']:
                print('HTTP 403: resource not accessible', file=sys.stderr)
                sys.exit(1)
            if args[:2] == ['project', 'view']:
                print(json.dumps({'id': 'project-id'}))
                sys.exit(0)
            print('unexpected gh call: ' + ' '.join(args), file=sys.stderr)
            sys.exit(2)
            """,
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("gh issue edit 891", completed.stderr)
        self.assertNotIn(["project", "view", "7", "--owner", "Daeguk-Sun", "--format", "json"], calls)

    def test_pr_merged_apply_warns_but_succeeds_when_project_item_missing(self) -> None:
        completed, calls = self.run_cli_with_fake_gh(
            [
                "pr-merged",
                "--repo",
                "Daeguk-Sun/dcNess",
                "--owner",
                "Daeguk-Sun",
                "--project",
                "7",
                "--body",
                "Closes #891",
                "--apply",
            ],
            """
            args = sys.argv[1:]
            if args[:2] == ['project', 'view']:
                print(json.dumps({'id': 'project-id'}))
                sys.exit(0)
            if args[:2] == ['project', 'field-list']:
                print(json.dumps({'fields': []}))
                sys.exit(0)
            if args[:2] == ['issue', 'view']:
                print(json.dumps({
                    'number': int(args[2]),
                    'labels': [{'name': 'feature'}, {'name': 'in-progress'}],
                    'state': 'CLOSED',
                    'url': 'https://github.com/Daeguk-Sun/dcNess/issues/' + args[2],
                }))
                sys.exit(0)
            if args[:2] == ['issue', 'edit']:
                sys.exit(0)
            if args[:2] == ['project', 'item-list']:
                print(json.dumps({'items': []}))
                sys.exit(0)
            print('unexpected gh call: ' + ' '.join(args), file=sys.stderr)
            sys.exit(2)
            """,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("WARN", completed.stderr)
        self.assertIn(["issue", "edit", "891", "--repo", "Daeguk-Sun/dcNess", "--remove-label", "in-progress"], calls)
        self.assertLess(
            calls.index(["issue", "edit", "891", "--repo", "Daeguk-Sun/dcNess", "--remove-label", "in-progress"]),
            calls.index(["project", "view", "7", "--owner", "Daeguk-Sun", "--format", "json"]),
        )
        self.assertNotIn("item-edit", " ".join(" ".join(call) for call in calls))

    def test_pr_merged_apply_fails_when_label_cleanup_fails(self) -> None:
        completed, calls = self.run_cli_with_fake_gh(
            [
                "pr-merged",
                "--repo",
                "Daeguk-Sun/dcNess",
                "--owner",
                "Daeguk-Sun",
                "--project",
                "7",
                "--body",
                "Closes #891",
                "--apply",
            ],
            """
            args = sys.argv[1:]
            if args[:2] == ['issue', 'view']:
                print(json.dumps({
                    'number': int(args[2]),
                    'labels': [{'name': 'feature'}, {'name': 'in-progress'}],
                    'state': 'CLOSED',
                    'url': 'https://github.com/Daeguk-Sun/dcNess/issues/' + args[2],
                }))
                sys.exit(0)
            if args[:2] == ['issue', 'edit']:
                print('HTTP 403: resource not accessible', file=sys.stderr)
                sys.exit(1)
            if args[:2] == ['project', 'view']:
                print(json.dumps({'id': 'project-id'}))
                sys.exit(0)
            print('unexpected gh call: ' + ' '.join(args), file=sys.stderr)
            sys.exit(2)
            """,
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("gh issue edit 891", completed.stderr)
        self.assertNotIn(["project", "view", "7", "--owner", "Daeguk-Sun", "--format", "json"], calls)

    def test_validate_issue_reports_project_drift_as_warning_without_failing(self) -> None:
        completed, _calls = self.run_cli_with_fake_gh(
            [
                "validate-issue",
                "--repo",
                "Daeguk-Sun/dcNess",
                "--owner",
                "Daeguk-Sun",
                "--project",
                "7",
                "--issue",
                "891",
                "--expected-status",
                "In progress",
            ],
            """
            args = sys.argv[1:]
            if args[:2] == ['project', 'view']:
                print(json.dumps({'id': 'project-id'}))
                sys.exit(0)
            if args[:2] == ['project', 'field-list']:
                print(json.dumps({'fields': []}))
                sys.exit(0)
            if args[:2] == ['issue', 'view']:
                print(json.dumps({
                    'number': 891,
                    'labels': [{'name': 'feature'}],
                    'state': 'OPEN',
                    'url': 'https://github.com/Daeguk-Sun/dcNess/issues/891',
                }))
                sys.exit(0)
            if args[:2] == ['project', 'item-list']:
                print(json.dumps({'items': [{
                    'id': 'item-id',
                    'content': {'number': 891, 'repository': 'Daeguk-Sun/dcNess'},
                    'status': 'Todo',
                    'issueType': 'feature',
                    'priority': 'major',
                }]}))
                sys.exit(0)
            print('unexpected gh call: ' + ' '.join(args), file=sys.stderr)
            sys.exit(2)
            """,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("IssueType label=feature", completed.stdout)
        self.assertIn("WARN", completed.stderr)
        self.assertIn("expected=In progress", completed.stderr)

    def test_validate_issue_still_fails_on_label_contract_violation(self) -> None:
        completed, _calls = self.run_cli_with_fake_gh(
            [
                "validate-issue",
                "--repo",
                "Daeguk-Sun/dcNess",
                "--owner",
                "Daeguk-Sun",
                "--project",
                "7",
                "--issue",
                "891",
            ],
            """
            args = sys.argv[1:]
            if args[:2] == ['project', 'view']:
                print(json.dumps({'id': 'project-id'}))
                sys.exit(0)
            if args[:2] == ['project', 'field-list']:
                print(json.dumps({'fields': []}))
                sys.exit(0)
            if args[:2] == ['issue', 'view']:
                print(json.dumps({
                    'number': 891,
                    'labels': [{'name': 'feature'}, {'name': 'bug'}],
                    'state': 'OPEN',
                    'url': 'https://github.com/Daeguk-Sun/dcNess/issues/891',
                }))
                sys.exit(0)
            if args[:2] == ['project', 'item-list']:
                print(json.dumps({'items': [{
                    'id': 'item-id',
                    'content': {'number': 891, 'repository': 'Daeguk-Sun/dcNess'},
                    'status': 'Todo',
                    'issueType': 'feature',
                    'priority': 'major',
                }]}))
                sys.exit(0)
            print('unexpected gh call: ' + ' '.join(args), file=sys.stderr)
            sys.exit(2)
            """,
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("expected exactly one IssueType label", completed.stdout)


class NextWorkStoryGroupPhaseTests(unittest.TestCase):
    """`next-work` L3 Story 나열이 epic 설계 산출물 존재로 `/design` vs `/impl` 을 구분하는지 (#951)."""

    def _epic(
        self,
        root: Path,
        slug: str,
        *,
        stories: bool = True,
        architecture: bool = False,
        impl_task: bool = False,
    ) -> None:
        epic_dir = root / "docs" / "epics" / slug
        epic_dir.mkdir(parents=True, exist_ok=True)
        if stories:
            (epic_dir / "stories.md").write_text("# stories\n", encoding="utf-8")
        if architecture:
            (epic_dir / "architecture.md").write_text("# arch\n", encoding="utf-8")
        if impl_task:
            impl_dir = epic_dir / "impl"
            impl_dir.mkdir(exist_ok=True)
            (impl_dir / "01-foo.md").write_text("# task\n", encoding="utf-8")

    def _format(self, groups: list, root: Path) -> str:
        return run_node(
            f"lifecycle.formatStoryGroups({json.dumps(groups)}, {json.dumps(str(root))})"
        )

    def test_design_incomplete_epic_marks_design_action_without_impl_footnote(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._epic(root, "epic-01-alpha", stories=True)
            groups = [
                {
                    "epicSlugLabel": "epic-01-alpha",
                    "epicNumber": 1,
                    "items": [{"number": 201, "title": "Story one"}],
                }
            ]
            out = self._format(groups, root)
            self.assertIn("설계 미완", out)
            self.assertIn("/design docs/epics/epic-01-alpha", out)
            self.assertIn("#201 Story one", out)
            self.assertNotIn("구현 순서 진본", out)

    def test_design_complete_epic_promotes_impl_with_footnote(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._epic(root, "epic-02-beta", stories=True, architecture=True, impl_task=True)
            groups = [
                {
                    "epicSlugLabel": "epic-02-beta",
                    "epicNumber": 2,
                    "items": [{"number": 301, "title": "Beta story"}],
                }
            ]
            out = self._format(groups, root)
            self.assertRegex(out, r"epic-02-beta.*설계 완료")
            self.assertIn("/impl", out)
            self.assertIn("구현 순서 진본", out)

    def test_architecture_without_impl_task_is_still_design_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # architecture.md 는 있으나 impl/NN-*.md 부재 = 설계 미완 (핵심 엣지, #950 SSOT 와 동일)
            self._epic(root, "epic-03-gamma", stories=True, architecture=True, impl_task=False)
            groups = [
                {
                    "epicSlugLabel": "epic-03-gamma",
                    "epicNumber": 3,
                    "items": [{"number": 401, "title": "Gamma story"}],
                }
            ]
            out = self._format(groups, root)
            self.assertIn("설계 미완", out)
            self.assertIn("/design docs/epics/epic-03-gamma", out)
            self.assertNotIn("구현 순서 진본", out)

    def test_mixed_epics_are_labeled_per_epic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._epic(root, "epic-01-alpha", stories=True)
            self._epic(root, "epic-02-beta", stories=True, architecture=True, impl_task=True)
            groups = [
                {
                    "epicSlugLabel": "epic-01-alpha",
                    "epicNumber": 1,
                    "items": [{"number": 201, "title": "A"}],
                },
                {
                    "epicSlugLabel": "epic-02-beta",
                    "epicNumber": 2,
                    "items": [{"number": 301, "title": "B"}],
                },
            ]
            out = self._format(groups, root)
            self.assertRegex(out, r"epic-01-alpha.*설계 미완")
            self.assertIn("/design docs/epics/epic-01-alpha", out)
            self.assertRegex(out, r"epic-02-beta.*설계 완료")
            self.assertIn("구현 순서 진본", out)

    def test_missing_local_epic_dir_holds_judgment(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # docs/epics 자체가 없음 (repo 밖 실행 / stale checkout) — 오탐으로 /design 단정 금지
            groups = [
                {
                    "epicSlugLabel": "epic-09-late",
                    "epicNumber": 9,
                    "items": [{"number": 901, "title": "Late"}],
                }
            ]
            out = self._format(groups, root)
            self.assertIn("판정 보류", out)
            self.assertIn("#901 Late", out)
            self.assertNotIn("/design docs/epics/epic-09-late", out)
            self.assertNotIn("구현 순서 진본", out)

    def test_unlabeled_story_group_holds_judgment(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            groups = [
                {
                    "epicSlugLabel": None,
                    "epicNumber": None,
                    "items": [{"number": 250, "title": "Manual"}],
                }
            ]
            out = self._format(groups, root)
            self.assertIn("미분류 story", out)
            self.assertIn("판정 보류", out)
            self.assertIn("#250 Manual", out)
            self.assertNotIn("구현 순서 진본", out)

    def test_empty_groups_still_report_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = self._format([], Path(td))
            self.assertIn("후보 없음", out)

    def test_null_root_holds_all_judgment_with_cross_repo_note(self) -> None:
        # root 부재(대상 repo != 로컬 checkout) → 로컬 산출물 무시하고 전부 보류, 이유 명시.
        groups = [
            {
                "epicSlugLabel": "epic-01-alpha",
                "epicNumber": 1,
                "items": [{"number": 201, "title": "Cross"}],
            }
        ]
        out = run_node(f"lifecycle.formatStoryGroups({json.dumps(groups)}, null)")
        self.assertIn("현재 로컬 checkout 과 달라", out)
        self.assertIn("판정 보류", out)
        self.assertIn("#201 Cross", out)
        self.assertNotIn("/design docs/epics/epic-01-alpha", out)
        self.assertNotIn("구현 순서 진본", out)

    def test_should_use_local_phase_root_matrix(self) -> None:
        cases = [
            # (repoArg, resolvedRepo, localRepo, expected)
            (None, "A/B", "A/B", True),          # --repo 미지정 → 자동 감지값이라 항상 로컬 일치
            ("A/B", "A/B", "A/B", True),         # 명시했지만 로컬과 일치
            ("a/b", "a/b", "A/B", True),         # 대소문자 무시 일치
            ("A/B", "A/B", "C/D", False),        # 로컬 checkout 이 다른 repo
            ("A/B", "A/B", None, False),         # repo 밖 실행 (로컬 감지 실패)
        ]
        for repo_arg, resolved, local, expected in cases:
            expr = (
                "lifecycle.shouldUseLocalPhaseRoot("
                f"{json.dumps(repo_arg)}, {json.dumps(resolved)}, {json.dumps(local)})"
            )
            self.assertEqual(run_node(expr), expected, msg=f"{repo_arg=} {resolved=} {local=}")


if __name__ == "__main__":
    unittest.main()
