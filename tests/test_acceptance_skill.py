"""Acceptance skill MVP contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AcceptanceSkillContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = ROOT / "skills" / "acceptance" / "SKILL.md"
        self.routing = ROOT / "skills" / "acceptance" / "acceptance-routing.md"
        self.impl_loop = ROOT / "skills" / "impl-loop" / "impl-loop-routing.md"

    def test_acceptance_skill_exists_as_story_epic_mvp(self) -> None:
        text = self.skill.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name:\s*acceptance$")
        self.assertIn("story issue", text)
        self.assertIn("epic issue", text)
        self.assertIn("`docs/index.md`", text)
        self.assertIn("`docs/epics/<epic>/stories.md`", text)
        self.assertIn("`docs/decisions/`", text)
        self.assertIn("구현 PR 목록", text)
        self.assertIn("STORY_ACCEPTANCE", text)
        self.assertIn("EPIC_ACCEPTANCE", text)
        self.assertNotIn("SPEC_ACCEPTANCE", text)
        self.assertIn("full E2E", text)
        self.assertIn("MVP 범위", text)
        self.assertIn("mock-only green", text)

    def test_acceptance_routing_defines_pass_fail_without_auto_mutation(self) -> None:
        text = self.routing.read_text(encoding="utf-8")
        self.assertIn("product-acceptance:STORY_ACCEPTANCE", text)
        self.assertIn("product-acceptance:EPIC_ACCEPTANCE", text)
        self.assertIn("PASS", text)
        self.assertIn("FAIL", text)
        self.assertIn("ESCALATE", text)
        self.assertIn("자동 수정", text)
        self.assertIn("자동 issue 생성", text)
        self.assertIn("사용자 승인", text)

    def test_story_and_epic_depth_are_distinct(self) -> None:
        skill = self.skill.read_text(encoding="utf-8")
        routing = self.routing.read_text(encoding="utf-8")
        for text in (skill, routing):
            self.assertIn("AC / PR / test evidence", text)
            self.assertIn("동작 증거", text)
            self.assertIn("mock-only green", text)
            self.assertIn("PRD Must", text)
            self.assertIn("cross-story gap", text)
            self.assertIn("security/ops risk", text)

    def test_acceptance_recognizes_automated_behavior_evidence(self) -> None:
        skill = self.skill.read_text(encoding="utf-8")
        routing = self.routing.read_text(encoding="utf-8")

        for text in (skill, routing):
            self.assertIn("동작 증거", text)
            self.assertIn("정적 타입검사", text)
            self.assertIn("실데이터(non-mock) 통합 테스트", text)
            self.assertIn("UI 자동화", text)
            self.assertIn("API/CLI smoke", text)
            self.assertIn("사람 E2E", text)
            self.assertIn("mock-only green", text)

    def test_acceptance_recognizes_user_flow_fit_as_separate_axis(self) -> None:
        skill = self.skill.read_text(encoding="utf-8")
        routing = self.routing.read_text(encoding="utf-8")

        for text in (skill, routing):
            self.assertIn("사용자 동선", text)
            self.assertIn("대상 사용자", text)
            self.assertIn("입력/진행 동선", text)
            self.assertIn("내부 schema", text)
            self.assertIn("체크리스트가 아니라", text)
            self.assertIn("개발자용 CLI/API", text)

    def test_inline_acceptance_owns_cross_pr_story_behavior(self) -> None:
        text = self.impl_loop.read_text(encoding="utf-8")
        self.assertIn("여러 PR 이 합쳐진 story 동작", text)
        self.assertIn("여러 story 가 합쳐진 epic 동작", text)
        self.assertIn("product-acceptance 가 맡는다", text)
        self.assertIn("mock-only green / 동작 증거 부족", text)
        self.assertIn("사용자 동선 부적합 / 내부 계약 노출", text)

    def test_lite_impl_is_not_forced_into_acceptance(self) -> None:
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("Lite `/impl`", text)
        self.assertIn("강제하지 않는다", text)

    def test_acceptance_prefers_design_surface_and_valid_mermaid(self) -> None:
        skill = self.skill.read_text(encoding="utf-8")
        routing = self.routing.read_text(encoding="utf-8")

        self.assertIn("설계 산출물 작성/수정 → `/design`", skill)
        self.assertNotIn("`/architect-loop`", skill)

        self.assertIn('TAX --> NEXT1["/impl · /design · /spec · /ux', routing)
        self.assertNotIn("TAX --> NEXT1[/impl", routing)

        self.assertIn("성능 병목 / 리팩토링 필요 | `/to-issue` 후보 + `/impl` 또는 `/design`", routing)
        self.assertIn("보안 / 권한 / 데이터 리스크 | `/to-issue` 후보 + `/design` 또는 사용자 위임", routing)
        self.assertIn("사용자 동선 부적합 / 내부 계약 노출", routing)
        self.assertNotIn("performance improvement loop", routing)
        self.assertNotIn("security deep-dive", routing)

    def test_public_surface_tracks_acceptance_as_lifecycle_default(self) -> None:
        script = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        default_match = re.search(r"defaultSkills:\s*\[([^\]]+)\]", script)
        advanced_match = re.search(r"advancedSkills:\s*\[([^\]]+)\]", script)
        self.assertIsNotNone(default_match)
        self.assertIsNotNone(advanced_match)
        self.assertIn("'acceptance'", default_match.group(1))
        self.assertNotIn("'acceptance'", advanced_match.group(1))
        self.assertIn("`/acceptance`", positioning)
        self.assertIn("제품 검수", positioning)


if __name__ == "__main__":
    unittest.main()
