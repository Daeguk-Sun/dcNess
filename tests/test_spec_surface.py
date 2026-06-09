"""Spec public surface contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SpecSurfaceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec_dir = ROOT / "skills" / "spec"
        self.skill = (self.spec_dir / "SKILL.md").read_text(encoding="utf-8")
        self.routing = (self.spec_dir / "spec-routing.md").read_text(encoding="utf-8")
        self.prd_ref = (self.spec_dir / "spec-prd-reference.md").read_text(
            encoding="utf-8"
        )
        self.stories_ref = (self.spec_dir / "spec-stories-reference.md").read_text(
            encoding="utf-8"
        )
        self.delivery_ref = (self.spec_dir / "spec-delivery-reference.md").read_text(
            encoding="utf-8"
        )
        self.prd_template = (self.spec_dir / "templates" / "prd.md").read_text(
            encoding="utf-8"
        )

    def test_spec_skill_owns_planning_flow_without_product_plan_alias(self) -> None:
        self.assertFalse((ROOT / "skills" / "product-plan").exists())
        self.assertRegex(self.skill, r"(?m)^name:\s*spec$")
        self.assertIn("사용자-facing 기본 surface 의 `/spec` 진입점", self.skill)
        self.assertIn("`/spec` public entrypoint", self.routing)
        self.assertIn("SPEC_ACCEPTANCE", self.skill)
        self.assertIn("/spec -> /design -> /impl -> /acceptance", self.skill)

        for text in (self.skill, self.routing):
            self.assertNotIn("`/product-plan`", text)
            self.assertNotIn('"/product-plan"', text)
            self.assertNotIn("product-plan", text)
            self.assertNotIn("호환", text)

    def test_spec_acceptance_and_issue_registration_are_documented(self) -> None:
        for text in (self.skill, self.routing):
            self.assertIn("product-acceptance", text)
            self.assertIn("SPEC_ACCEPTANCE", text)
            self.assertIn("full E2E", text)
            self.assertIn("범위 밖", text)

        self.assertIn("PR 머지 → 이슈 등록 여부 확인 → `/design`", self.skill)
        self.assertIn("이슈 등록 완료 또는 보류 marker 확인 후", self.skill)
        self.assertIn("MERGE[PR 머지]", self.routing)
        self.assertIn("ISSUE{이슈 등록?}", self.routing)
        self.assertIn("이슈 등록 보류 marker 기록/머지 후 Step 12", self.routing)
        self.assertNotIn("PR 머지 + 이슈 등록", self.routing)

    def test_spec_flow_keeps_prd_draft_review_before_tech_review(self) -> None:
        expected_order = [
            "PRD 초안 작성",
            "사용자 PRD 초안 확인",
            "tech-review preflight",
            "PRD 최종화",
            "stories.md 작성",
            "사용자 최종 OK",
            "product-acceptance:SPEC_ACCEPTANCE",
        ]
        headings = re.findall(r"(?m)^### Step \d+ — (.+)$", self.skill)
        cursor = -1
        for phrase in expected_order:
            try:
                next_pos = next(
                    index
                    for index, heading in enumerate(headings[cursor + 1 :], cursor + 1)
                    if phrase in heading
                )
            except StopIteration as exc:
                raise AssertionError(
                    f"{phrase!r} should appear in a later Step heading"
                ) from exc
            cursor = next_pos

    def test_tech_review_uses_prd_review_area_not_main_written_skeleton(self) -> None:
        files = [
            self.spec_dir / "SKILL.md",
            self.spec_dir / "spec-routing.md",
            ROOT / "skills" / "tech-review" / "SKILL.md",
            ROOT / "skills" / "tech-review" / "tech-review-routing.md",
            ROOT / "agents" / "tech-reviewer" / "tech-reviewer-agent.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

        self.assertIn("기술 검토 필요 영역", combined)
        self.assertIn("docs/tech-review.md", combined)
        self.assertIn("생성/갱신", combined)

        reviewer = (
            ROOT / "agents" / "tech-reviewer" / "tech-reviewer-agent.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "PRD의 기술 검토 필요 영역에 명시된 검토 질문을 정식 항목으로 확인한다",
            reviewer,
        )
        for phrase in ("비용", "라이선스", "성능", "품질", "실현성"):
            self.assertIn(phrase, reviewer)
        self.assertNotIn("PRD에서 명시된 외부 의존을 정식 항목으로 확인한다", reviewer)

        for phrase in (
            "tech-review.md 스켈레톤",
            "`docs/tech-review.md` 스켈레톤",
            "스켈레톤 존재",
            "스켈레톤 작성",
            "스켈레톤 갱신",
            "스켈레톤 부재",
            "PRD/stories/tech-review 스켈레톤",
        ):
            self.assertNotIn(phrase, combined)

    def test_tech_review_preflight_routes_from_prd_review_area(self) -> None:
        step2 = re.search(
            r"### Step 2 — PRD 초안 작성(?P<body>.*?)### Step 3",
            self.skill,
            flags=re.S,
        )
        step4 = re.search(
            r"### Step 4 — tech-review preflight 확인과 실행(?P<body>.*?)### Step 5",
            self.skill,
            flags=re.S,
        )
        self.assertIsNotNone(step2)
        self.assertIsNotNone(step4)
        step2_body = step2.group("body")
        step4_body = step4.group("body")

        for criterion in (
            "새 외부 API / SDK / model / 라이브러리 도입",
            "비용, 라이선스, 성능, 품질이 MVP 성패를 좌우",
            '"이게 되는지"가 기능 정의 자체를 바꿀 수 있음',
        ):
            self.assertIn(criterion, self.prd_ref)
            self.assertNotIn(criterion, step4_body)

        self.assertIn("기술 검토 필요 영역", step2_body)
        self.assertIn("PRD 초안 작성 때", self.prd_ref)
        self.assertIn("기술 검토 필요 영역", step4_body)
        self.assertIn('검토 항목 0 개 또는 "해당 없음"', step4_body)
        self.assertIn("검토 항목 1 개 이상", step4_body)
        self.assertNotIn("trigger 기준은", step4_body)

    def test_spec_skill_is_step_focused_with_split_references(self) -> None:
        self.assertLessEqual(
            len(self.skill.splitlines()),
            240,
            "spec/SKILL.md should stay focused on Step execution",
        )
        self.assertEqual(
            [str(i) for i in range(13)],
            re.findall(r"(?m)^### Step (\d+) —", self.skill),
        )
        for ref in (
            "spec-prd-reference.md",
            "spec-stories-reference.md",
            "spec-delivery-reference.md",
            "templates/prd.md",
        ):
            self.assertIn(ref, self.skill)

        self.assertIn("PRD 산출물 의무", self.prd_ref)
        self.assertIn("templates/prd.md", self.prd_ref)
        self.assertIn("자연어 대화", self.prd_ref)
        self.assertIn("맥락을 누적", self.prd_ref)
        self.assertIn("객관식 후보", self.prd_ref)
        self.assertIn("기술 검토 필요 영역 작성 기준", self.prd_ref)
        self.assertIn("AC-ID", self.prd_ref)

        for section in (
            "# PRD —",
            "## 서비스 개요",
            "## 기능 범위",
            "## 기능별 스펙",
            "## 화면 인벤토리 + 대략적 플로우",
            "## 비즈니스 모델",
            "## 외부 의존 보호",
            "## 기술 검토 필요 영역",
            "## 스코프 결정",
        ):
            self.assertIn(section, self.prd_template)

        self.assertIn("AC-001", self.prd_template)
        self.assertIn('검토 항목 0 개면 "해당 없음"', self.prd_template)
        self.assertIn("stories.md 산출물", self.stories_ref)
        self.assertIn("Story 크기 가이드", self.stories_ref)
        self.assertIn("# Story Backlog", self.stories_ref)
        self.assertIn("git checkout -b docs/<slug> main", self.delivery_ref)
        self.assertIn("create_epic_story_issues.sh", self.delivery_ref)

        self.assertNotIn("Interview me relentlessly", self.skill)
        self.assertNotIn("# Story Backlog", self.skill)
        self.assertNotIn("git checkout -b docs/<slug> main", self.skill)

    def test_public_surface_keeps_spec_default_without_internal_planning_skill(self) -> None:
        script = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        default_match = re.search(r"defaultSkills:\s*\[([^\]]+)\]", script)
        self.assertIsNotNone(default_match)
        defaults = default_match.group(1)
        self.assertIn("'spec'", defaults)
        self.assertNotIn("'product-plan'", defaults)
        self.assertNotIn("internalWorkflowSkills", script)
        self.assertNotIn("compatSkills", script)
        self.assertIn("`/spec`", positioning)
        self.assertNotIn("`/product-plan`", positioning)
        self.assertNotIn("호환 alias", positioning)


if __name__ == "__main__":
    unittest.main()
