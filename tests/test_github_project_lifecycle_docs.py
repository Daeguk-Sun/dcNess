"""Static contract tests for GitHub Project lifecycle docs (#663)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GithubProjectLifecycleDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_doc = ROOT / "docs" / "plugin" / "github-project.md"
        self.issue_lifecycle = (
            ROOT / "docs" / "plugin" / "issue-lifecycle.md"
        ).read_text(encoding="utf-8")
        self.issue_fields = (
            ROOT / "skills" / "to-issue" / "issue-fields.md"
        ).read_text(encoding="utf-8")
        self.to_issue = (
            ROOT / "skills" / "to-issue" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.init_dcness = (
            ROOT / "commands" / "init-dcness.md"
        ).read_text(encoding="utf-8")
        self.init_reference = (
            ROOT / "docs" / "plugin" / "init-dcness.md"
        ).read_text(encoding="utf-8")
        self.setup_labels = (
            ROOT / "scripts" / "setup_labels.sh"
        ).read_text(encoding="utf-8")

    def test_project_axes_ssot_documents_status_issue_type_priority(self) -> None:
        text = self.project_doc.read_text(encoding="utf-8")

        self.assertIn("# GitHub Project Lifecycle", text)
        for field in ("Status", "IssueType", "Priority"):
            self.assertRegex(text, rf"(?m)^## {field}$")
            self.assertRegex(text, rf"(?ms)^## {field}$.+Usage example")

        for value in ("Todo", "In progress", "Done"):
            self.assertRegex(text, rf"(?m)^\|\s*`{re.escape(value)}`\s*\|")

        for value in ("epic", "feature", "story", "task", "subTask", "bug"):
            self.assertRegex(text, rf"(?m)^\|\s*`{re.escape(value)}`\s*\|")
            self.assertRegex(text, rf"(?m)^\|\s*`{re.escape(value)}`\s*\|")

        for value in ("blocker", "critical", "major", "minor", "trivial"):
            self.assertRegex(text, rf"(?m)^\|\s*`{re.escape(value)}`\s*\|")

    def test_repo_labels_match_issue_type_axis_and_are_bootstrapped(self) -> None:
        for value in ("epic", "feature", "story", "task", "subTask", "bug"):
            self.assertIn(f"`{value}`", self.issue_fields)
            self.assertIn(f"_upsert_label \"{value}\"", self.setup_labels)
        self.assertIn("_upsert_label \"in-progress\"", self.setup_labels)

        self.assertIn("lifecycle repo label 7종", self.project_doc.read_text(encoding="utf-8"))
        self.assertIn("IssueType repo label 6종", self.issue_fields)

    def test_issue_type_set_is_identical_across_script_docs_and_labels(self) -> None:
        """lifecycle 스크립트·SSOT 문서·label bootstrap 의 IssueType 집합이 정확히 같다 (#1254).

        한쪽에만 값이 추가되면 그 label 을 쓴 issue 가 lifecycle 검사에서 실패한다.
        """
        script = (ROOT / "scripts" / "github_project_lifecycle.mjs").read_text(encoding="utf-8")
        match = re.search(r"IssueType: Object\.freeze\(\[([^\]]*)\]\)", script)
        self.assertIsNotNone(match)
        script_types = re.findall(r"'([^']+)'", match.group(1))

        def table_types(text: str) -> list[str]:
            section = re.search(r"(?ms)^## IssueType$(.+?)^## ", text)
            self.assertIsNotNone(section)
            return re.findall(r"(?m)^\|\s*`([^`]+)`\s*\|", section.group(1))

        label_types = [
            name
            for name in re.findall(r'(?m)^_upsert_label "([^"]+)"', self.setup_labels)
            if name != "in-progress"
        ]
        expected = sorted(script_types)
        self.assertEqual(expected, sorted(table_types(self.project_doc.read_text(encoding="utf-8"))))
        self.assertEqual(expected, sorted(table_types(self.issue_fields)))
        self.assertEqual(expected, sorted(label_types))

    def test_init_dcness_checks_project_and_label_bootstrap(self) -> None:
        text = self.init_dcness + "\n" + self.init_reference

        self.assertIn("GitHub Project lifecycle bootstrap", text)
        self.assertIn("scripts/github_project_lifecycle.mjs bootstrap", text)
        self.assertIn("Status / IssueType / Priority", text)
        self.assertIn("lifecycle repo label 7종", text)
        self.assertIn("Project가 없거나 필드가 부족", text)
        self.assertIn("label 이 부족", text)
        self.assertIn("--apply", text)
        self.assertIn("다른 repo", text)

    def test_to_issue_contract_references_project_lifecycle_ssot(self) -> None:
        self.assertIn("[`../../docs/plugin/github-project.md`]", self.issue_fields)
        self.assertIn("open issue + `in-progress` label 없음", self.to_issue)
        self.assertIn('github_project_lifecycle.mjs" validate-issue', self.to_issue)
        self.assertIn("Project backfill 을 수행한 경우", self.to_issue)
        self.assertIn("--expected-issue-type", self.to_issue)
        self.assertIn("--expected-priority", self.to_issue)
        self.assertIn("IssueType repo label", self.to_issue)

    def test_work_start_and_pr_merge_lifecycle_are_documented(self) -> None:
        text = self.issue_lifecycle

        self.assertIn("in-progress` label", text)
        self.assertIn('github_project_lifecycle.mjs" start-work', text)
        self.assertIn("/spec", text)
        self.assertIn("/design", text)
        self.assertIn("/impl", text)
        self.assertIn("close 를 발동", text)
        self.assertIn('github_project_lifecycle.mjs" pr-merged', text)
        self.assertIn("Part of #N", text)
        self.assertIn("완료 신호가 아니다", text)
        self.assertRegex(text, r"(?s)closed issue.+in-progress")
        self.assertIn("IssueType repo label 을 정확히 하나", text)

    def test_priority_inference_policy_differs_single_vs_bulk(self) -> None:
        """Project SSOT must distinguish single /to-issue inference from bulk major-pin (#676)."""
        text = self.project_doc.read_text(encoding="utf-8")

        # 단발 /to-issue 는 Priority 를 맥락에서 추론해 명시한다.
        self.assertIn("맥락에서 추론", text)
        # epic/story 일괄 생성은 전부 major 고정이다.
        self.assertIn("`major` 고정", text)
        # register-issue --priority 생략 시 major fallback 은 일괄 경로를 위한 동작임을 명시.
        self.assertIn("fallback", text)


if __name__ == "__main__":
    unittest.main()
