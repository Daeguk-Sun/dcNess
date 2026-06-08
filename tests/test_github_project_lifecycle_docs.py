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

        self.assertIn("repo label 6종", self.project_doc.read_text(encoding="utf-8"))
        self.assertIn("IssueType 축과 같은 의미", self.issue_fields)

    def test_init_dcness_checks_project_and_label_bootstrap(self) -> None:
        text = self.init_dcness

        self.assertIn("GitHub Project lifecycle bootstrap", text)
        self.assertIn("scripts/github_project_lifecycle.mjs bootstrap", text)
        self.assertIn("Status / IssueType / Priority", text)
        self.assertIn("repo label 6종", text)
        self.assertIn("Project가 없거나 필드가 부족", text)
        self.assertIn("repo label이 부족", text)
        self.assertIn("--apply", text)
        self.assertIn("다른 repo", text)

    def test_to_issue_contract_references_project_lifecycle_ssot(self) -> None:
        self.assertIn("[`../../docs/plugin/github-project.md`]", self.issue_fields)
        self.assertIn("Status=Todo", self.to_issue)
        self.assertIn("scripts/github_project_lifecycle.mjs validate-issue", self.to_issue)
        self.assertIn("--expected-status Todo", self.to_issue)
        self.assertIn("--expected-issue-type", self.to_issue)
        self.assertIn("--expected-priority", self.to_issue)
        self.assertIn("Project `IssueType`과 같은 repo label", self.to_issue)

    def test_work_start_and_pr_merge_lifecycle_are_documented(self) -> None:
        text = self.issue_lifecycle

        self.assertIn("Status=In progress", text)
        self.assertIn("scripts/github_project_lifecycle.mjs start-work", text)
        self.assertIn("/spec", text)
        self.assertIn("/design", text)
        self.assertIn("/impl", text)
        self.assertIn("Status=Done", text)
        self.assertIn("scripts/github_project_lifecycle.mjs pr-merged", text)
        self.assertIn("Part of #N", text)
        self.assertIn("완료 신호가 아니다", text)
        self.assertRegex(text, r"(?s)status drift.+어떤 issue.+어떤 field")
        self.assertRegex(text, r"(?s)IssueType.+repo label.+어떤 issue.+어떤 값")


if __name__ == "__main__":
    unittest.main()
