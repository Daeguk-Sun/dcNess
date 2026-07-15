"""Spec story-level vertical-slice contract tests.

/spec 의 story 분할·순서 기준과 SPEC_ACCEPTANCE 검수 축이
"사용자 검증 가능한 동작 증분 / 얇은 골격 우선" 원칙을 유지하는지 회귀로 보존한다.
"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SpecStorySliceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stories_reference = (
            ROOT / "skills" / "spec" / "spec-stories-reference.md"
        ).read_text(encoding="utf-8")
        self.spec_skill = (
            ROOT / "skills" / "spec" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.product_acceptance = (
            ROOT / "docs" / "plugin" / "agents" / "product-acceptance" / "product-acceptance-agent.md"
        ).read_text(encoding="utf-8")
        self.system_architect = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "system-architect-agent.md"
        ).read_text(encoding="utf-8")
        self.shared_principles = (
            ROOT / "docs" / "plugin" / "agents" / "_shared" / "module-design-principles.md"
        ).read_text(encoding="utf-8")

    def test_stories_reference_requires_behavior_increment_split(self) -> None:
        for needle in (
            "## Story 분할 기준 — 사용자 검증 가능한 동작 증분",
            "제품 경계(UI/API/CLI/worker entrypoint/통합 wiring)",
            "같은 원칙의 Story 수준 적용",
            "완료되면 사용자가 무엇을 실행하거나 확인할 수 있는가",
            "다른 Story 와 합쳐져야 동작",
            "부품 Story 묶음 신호",
            "동작 증분 단위로 재분할",
            "어느 후행 Story 에서 그 동작이 확인되는지 명시",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.stories_reference)

    def test_stories_reference_requires_walking_skeleton_ordering(self) -> None:
        for needle in (
            "## Story 순서 기준 — 얇은 골격 우선",
            "walking skeleton",
            "입력에서 결과까지 한 줄로 통과하는 최소 동선",
            "골격 위에 확인 가능한 증분을 쌓는다",
            "마지막 Story 까지 밀리는 순서(부품을 다 만든 뒤에야 처음 동작)는 그대로 두지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.stories_reference)

    def test_stories_reference_template_has_story_acceptance_criteria(self) -> None:
        for needle in (
            "**Acceptance criteria:**",
            "AC-001 [command]",
            "AC-002 [agent-read]",
            "Given <상황>, When <행동>, Then <검증 가능한 결과>",
        ):
            self.assertIn(needle, self.stories_reference)

    def test_spec_skill_acceptance_prompt_checks_behavior_increment(self) -> None:
        for needle in (
            "사용자 검증 가능한 동작 증분 / 얇은 골격 우선 기준",
            "Story 분할·순서가 사용자 검증 가능한 동작 증분인지를 본다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.spec_skill)

    def test_product_acceptance_spec_mode_flags_component_stories_and_ordering(
        self,
    ) -> None:
        for needle in (
            "각 Story 가 완료 시 사용자가 확인 가능한 동작 증분을 명시하는가",
            "부품 Story 묶음(기능 영역/레이어 분할)은 gap 으로 식별한다",
            "순서 판단 단일 규칙",
            "sequence defect",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.product_acceptance)

    def test_product_acceptance_spec_mode_tracks_first_core_e2e_closure(
        self,
    ) -> None:
        for needle in (
            "순서 판단 단일 규칙",
            "명세 자체가 완전한 사용자 흐름의 최초 end-to-end 검증을 후속 Story로 지연했음을 보여주면",
            "Story AC 또는 동작 증거 부족과 별개의 sequence defect",
            "Story AC가 없더라도 PRD 목표·유저 시나리오, Epic 완료 기준, Story 목적·영향 모듈이 Story별 제품 경계를 드러내면 지연 근거로 사용한다",
            "sequence defect 판정은 Story AC 충족 여부와 독립적으로 먼저 수행한다",
            "지연을 입증하는 Story 순서·제품 경계 근거가 없으면",
            "Story AC 또는 동작 증거 부족만 보고하고 sequence defect를 추측하지 않는다",
            "export·upload·publish·download·delivery",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.product_acceptance)

        self.assertEqual(self.product_acceptance.count("순서 판단 단일 규칙"), 1)
        self.assertNotIn(
            "Story 순서가 얇은 end-to-end 골격을 앞당기는가",
            self.product_acceptance,
        )
        self.assertNotIn(
            "SPEC_ACCEPTANCE에서 핵심 제품 약속의 첫 end-to-end 동작 검증이 뒤 Story 로 밀렸는데",
            self.product_acceptance,
        )

    def test_product_acceptance_report_includes_user_runnable_path(self) -> None:
        self.assertIn(
            "사용자가 지금 직접 확인할 수 있는 실행 동선(실행 명령, 화면 진입 경로 등) 안내",
            self.product_acceptance,
        )

    def test_system_architect_orders_for_early_product_boundary_evidence(self) -> None:
        for needle in (
            "첫 제품 경계 동작 증거를 앞당기는 순서를 설명하는가",
            "부품을 다 만든 뒤에야 처음 동작하는 순서는 epic `architecture.md` 의 "
            "`Story -> 모듈 매핑` 또는 stories.md epic 완료 기준 근처에 경고와 사유로 남긴다",
            "첫 제품 경계 동작 증거를 앞당기는 관점을 포함한다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.system_architect)

    def test_shared_principles_apply_to_spec_story_level(self) -> None:
        for needle in (
            "`/spec` stories.md — Story 분할·순서 자체가 동작 증분 단위가 되도록 "
            "같은 원칙을 Story 수준에 적용한다",
            "../../skills/spec/spec-stories-reference.md",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.shared_principles)

    def test_git_spec_story_issue_body_includes_story_acceptance_criteria(self) -> None:
        git_spec = (ROOT / "docs" / "plugin" / "git-spec.md").read_text(encoding="utf-8")
        self.assertIn("`As a / I want / So that` + Story AC 목록", git_spec)
        self.assertIn("AC-NNN", git_spec)

    def test_spec_acceptance_axes_keep_documented_exceptions(self) -> None:
        for needle in (
            "어느 후행 Story 에서 그 동작이 확인되는지 명시했으면 gap 이 아니다",
            "더 이른 얇은 end-to-end 검증이 불가능한 사유를 명시하면 warning",
            "최종 사용자 가치 경계까지 실제 도달하면 이후 기능 풍부화는 정상 walking skeleton",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.product_acceptance)

    def test_spec_acceptance_ordering_gap_not_retracted_or_reframed(self) -> None:
        """순서 gap 을 하위 동작·의존 순서로 철회하거나, 사유를 지어내거나,
        형식/export 프레이밍으로 덮는 razor-thin 경계 흔들림을 회귀로 차단한다 (#1139)."""
        for needle in (
            "앞 Story의 하위 동작이나 합리적인 의존 순서로 철회하지 않는다",
            "불가능 사유를 검수자가 지어내지 않는다",
            "형식 gap이나 제품 경계 모호성으로 대체·흡수하지 않는다",
            "sequence defect로 보고하고 PASS하지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.product_acceptance)

    def test_product_acceptance_reads_stories_reference_for_spec_mode(self) -> None:
        self.assertIn(
            "../../skills/spec/spec-stories-reference.md", self.product_acceptance
        )

    def test_story_acceptance_consumes_typed_story_ac(self) -> None:
        self.assertIn("Story AC 전항목", self.product_acceptance)

    def test_report_guidance_is_evidence_bounded(self) -> None:
        self.assertIn("불명이면 불명이라고 쓴다", self.product_acceptance)

    def test_stories_reference_maps_library_boundary(self) -> None:
        self.assertIn(
            "라이브러리/SDK 는 공개 API 사용 예제(컴파일·실행 가능한)가 제품 경계다",
            self.stories_reference,
        )

if __name__ == "__main__":
    unittest.main()
