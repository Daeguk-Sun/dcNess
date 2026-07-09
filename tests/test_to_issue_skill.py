"""Regression tests for the /to-issue issue drafting flow (#662)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ToIssueSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_path = ROOT / "skills" / "to-issue" / "SKILL.md"
        self.field_ssot_path = ROOT / "skills" / "to-issue" / "issue-fields.md"
        self.template_path = (
            ROOT / "skills" / "to-issue" / "templates" / "issue-brief.md"
        )
        self.workflow_router = (
            ROOT / "docs" / "plugin" / "workflow-router.md"
        ).read_text(encoding="utf-8")

    def test_to_issue_skill_exists_as_main_driven_entrypoint(self) -> None:
        text = self.skill_path.read_text(encoding="utf-8")

        self.assertRegex(text, r"(?m)^name:\s*to-issue$")
        self.assertIn("메인 Claude", text)
        self.assertIn("서브에이전트", text)
        self.assertIn("호출하지 않는다", text)
        self.assertIn("초안 승인 대기 없이", text)
        self.assertIn("web 에서 확인", text)

    def test_issue_brief_template_has_required_contract_sections(self) -> None:
        skill = self.skill_path.read_text(encoding="utf-8")
        text = self.template_path.read_text(encoding="utf-8")

        self.assertIn("[`templates/issue-brief.md`](templates/issue-brief.md)", skill)
        self.assertNotIn("```markdown\n## Issue Brief", skill)

        required = (
            "IssueType",
            "Priority",
            "Summary",
            "Current behavior / Context",
            "Desired behavior / What to build",
            "Key interfaces / Contracts",
            "Acceptance criteria",
            "Blocked by",
            "Out of scope",
        )
        for section in required:
            self.assertIn(section, text)

        self.assertIn("독립적으로 검증", text)
        self.assertIn("구현 파일 경로", text)
        self.assertIn("line number", text)
        self.assertIn("layer-by-layer", text)
        self.assertIn("{{IssueType}}", text)
        self.assertIn("{{Priority}}", text)

    def test_issue_field_options_are_defined_in_ssot_not_skill(self) -> None:
        skill = self.skill_path.read_text(encoding="utf-8")
        text = self.field_ssot_path.read_text(encoding="utf-8")

        self.assertIn("[`issue-fields.md`](issue-fields.md)", skill)

        for field in ("IssueType", "Priority"):
            self.assertRegex(text, rf"(?m)^## {field}$")

        for value in ("epic", "feature", "story", "task", "subTask", "bug"):
            self.assertRegex(text, rf"(?m)^\|\s*`{re.escape(value)}`\s*\|")

        for value in ("blocker", "critical", "major", "minor", "trivial"):
            self.assertRegex(text, rf"(?m)^\|\s*`{re.escape(value)}`\s*\|")

        forbidden_inline_lists = (
            "IssueType: `epic`, `feature`, `story`, `task`, `subTask`, `bug`",
            "Priority: `blocker`, `critical`, `major`, `minor`, `trivial`",
            "**IssueType:** epic / feature / story / task / subTask / bug",
            "**Priority:** blocker / critical / major / minor / trivial",
        )
        for inline_list in forbidden_inline_lists:
            self.assertNotIn(inline_list, skill)

    def test_issue_creation_records_lifecycle_and_label_fields(self) -> None:
        text = self.skill_path.read_text(encoding="utf-8")

        for phrase in (
            "중복 이슈",
            "granularity",
            "dependency",
            "HITL/AFK",
            "Project `IssueType`",
            "Project `Priority`",
            "Status=Todo",
            "repo label",
            "IssueType 과 같은 repo label",
            "lifecycle state: open issue + `in-progress` label 없음 (`Todo`)",
            "parent issue",
            "닫거나 임의 수정하지 않는다",
        ):
            self.assertIn(phrase, text)

    def test_issue_creation_runs_body_validator_before_gh_create(self) -> None:
        text = self.skill_path.read_text(encoding="utf-8")
        validator = "scripts/check_issue_body.mjs"
        create = "gh issue create"

        self.assertTrue((ROOT / validator).exists())
        self.assertIn(validator, text)
        self.assertIn("--body-file <brief.md>", text)
        self.assertLess(text.index(validator), text.index(create))
        self.assertIn("validator 실패", text)

    def test_internal_classification_enums_are_not_to_issue_criteria(self) -> None:
        text = self.skill_path.read_text(encoding="utf-8")
        enum_pattern = (
            r"FUNCTIONAL_BUG|CLEANUP|DESIGN_ISSUE|KNOWN_ISSUE|SCOPE_ESCALATE"
        )

        self.assertNotRegex(text, enum_pattern)
        self.assertNotIn("/issue-report", text)

    def test_issue_report_skill_and_qa_agent_are_removed(self) -> None:
        self.assertFalse((ROOT / "skills" / "issue-report").exists())
        self.assertFalse((ROOT / "agents" / "qa.md").exists())
        self.assertFalse((ROOT / "agents" / "qa").exists())

    def test_router_sends_issue_drafting_to_to_issue_without_issue_report(self) -> None:
        text = self.workflow_router

        to_issue_gate = "GitHub issue 초안/등록 요청인가? → `/to-issue`"
        self.assertIn(to_issue_gate, text)
        self.assertNotIn("/issue-report", text)
        self.assertIn(
            "issue 생성, Project field 설정, repo label 부여가 목표인 요청은 `/to-issue`",
            text,
        )
        self.assertIn("버그를 바로 고칠 요청은 `/impl`", text)

    def test_field_ssot_documents_priority_inference_heuristic(self) -> None:
        """issue-fields.md must guide priority inference, not just list 5 values (#676)."""
        text = self.field_ssot_path.read_text(encoding="utf-8")

        # 값 의미 나열을 넘어 '언제 어떤 값' 추론 신호를 제공한다.
        self.assertIn("추론 신호", text)
        self.assertIn("맥락에서 추론", text)
        # 단발 to-issue 는 기본값 없이 추론 — major 로 조용히 자동 수렴 금지.
        self.assertIn("기본값", text)
        self.assertIn("자동 수렴", text)
        # 매번 되묻지 않고 추론 근거를 초안에 제시 (사용자는 교정만).
        self.assertIn("되묻지 않는다", text)
        self.assertIn("근거", text)
        # epic/story 일괄 생성의 major 고정 정책과 구분 (범위 밖).
        self.assertIn("`major` 고정", text)

    def test_skill_infers_priority_with_rationale_not_silent_default(self) -> None:
        """SKILL.md must make Priority a context-inferred value with rationale (#676)."""
        text = self.skill_path.read_text(encoding="utf-8")

        # Priority 를 맥락에서 추론한다 (Status=Todo 고정과 대칭으로 케이스별 추론값).
        self.assertIn("맥락에서 추론", text)
        # 매번 사용자에게 되묻지 않는다 (반복 확인은 마찰).
        self.assertIn("되묻지 않는다", text)
        # 추론 근거를 Issue Brief 초안과 함께 제시한다.
        self.assertIn("추론 근거", text)
        # register-issue 호출 시 추론값을 명시 — 생략해 스크립트 기본값(major)로 fallback 금지.
        self.assertIn("fallback", text)
        self.assertIn("기본값(major)", text)

    def test_ui_issues_include_visual_reference_contract(self) -> None:
        """#1023 — UI issues must carry the baseline /impl will use."""
        skill = self.skill_path.read_text(encoding="utf-8")
        template = self.template_path.read_text(encoding="utf-8")

        for text in (skill, template):
            self.assertIn("UI 성격", text)
            self.assertIn("UI 기준", text)
            self.assertIn("canvas / 목업 / flow", text)
            self.assertIn("목업 없이", text)

        self.assertIn("후속 `/impl`", skill)
        self.assertIn("docs/design-variants/<screen-id>.html", skill)
        self.assertIn("docs/design-variants/canvas.html", skill)
        self.assertIn("docs/epics/.../ux-flow.md", skill)
        self.assertIn("나중에 정함", skill)


if __name__ == "__main__":
    unittest.main()
