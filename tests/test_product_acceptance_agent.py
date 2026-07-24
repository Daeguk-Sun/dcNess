"""Product acceptance agent contract tests."""
from __future__ import annotations

import unittest
from pathlib import Path

from harness.agent_boundary import ALLOW_MATRIX
from harness.agent_routing import ROUTABLE_VALIDATION_AGENTS
from harness.ledger import infer_next_action, infer_phase
from harness.run_review import (
    DCNESS_AGENT_NAMES,
    EXPECTED_AGENT_BUDGETS,
    READONLY_AGENTS,
)


ROOT = Path(__file__).resolve().parents[1]


class ProductAcceptanceAgentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = ROOT / "agents" / "product-acceptance.md"
        self.prompt = (
            ROOT
            / "docs" / "plugin" / "agents"
            / "product-acceptance"
            / "product-acceptance-agent.md"
        )
        self.acceptance_routing = (
            ROOT / "skills" / "acceptance" / "acceptance-routing.md"
        )
        self.impl_loop_routing = (
            ROOT / "skills" / "impl-loop" / "impl-loop-routing.md"
        )
        self.impl_loop_finish = (
            ROOT / "skills" / "impl-loop" / "impl-loop-finish.md"
        )
        self.acceptance_skill = ROOT / "skills" / "acceptance" / "SKILL.md"
        self.impl_loop_skill = ROOT / "skills" / "impl-loop" / "SKILL.md"
        self.module_architect_prompt = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "module-architect"
            / "module-architect-agent.md"
        )
        self.impl_task_template = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "module-architect"
            / "templates"
            / "impl-task.md"
        )
        self.build_worker_prompt = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "build-worker"
            / "build-worker-agent.md"
        )
        self.product_journey = ROOT / "docs" / "plugin" / "product-journey.md"
        self.init_dcness = ROOT / "docs" / "plugin" / "init-dcness.md"

    def test_agent_entrypoint_exists_and_points_to_prompt(self) -> None:
        text = self.entry.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name:\s*product-acceptance$")
        self.assertIn("tools: Read, Glob, Grep, Bash", text)
        self.assertIn("product-acceptance-agent.md", text)

    def test_prompt_defines_four_modes_and_final_enums(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        for mode in (
            "SPEC_ACCEPTANCE",
            "STORY_ACCEPTANCE",
            "EPIC_ACCEPTANCE",
            "RELEASE_ACCEPTANCE",
        ):
            self.assertIn(mode, text)
        for enum in ("PASS", "FAIL", "ESCALATE"):
            self.assertRegex(text, rf"\b{enum}\b")
        self.assertIn("마지막 단락", text)

    def test_prompt_uses_shared_agent_doc_sections(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        expected = [
            "## 목적",
            "## 입력",
            "## 먼저 읽을 문서",
            "## 판단 축",
            "## 작업 흐름",
            "## 완료 기준",
            "## 권한 경계",
            "## 결론과 보고",
            "## 템플릿과 참고 문서",
        ]
        positions = [text.index(heading) for heading in expected]
        self.assertEqual(positions, sorted(positions))

    def test_prompt_distinguishes_acceptance_from_existing_validators(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        self.assertIn("impl-validator", text)
        self.assertIn("architecture-validator", text)
        self.assertIn("impl-validator", text)
        self.assertIn("대체하지 않는다", text)

    def test_prompt_keeps_full_e2e_out_of_mvp(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        self.assertIn("사람 full E2E", text)
        self.assertIn("MVP", text)
        self.assertIn("범위 밖", text)

    def test_prompt_classifies_behavior_evidence_and_mock_only_gap(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        for needle in (
            "동작 증거 판정",
            "정적 타입검사/compile",
            "실데이터(non-mock) 통합 테스트",
            "UI 자동화",
            "API/CLI smoke",
            "mock-only green",
            "핵심 AC가 mock-only green으로만 닫혔으면 PASS 하지 않는다",
        ):
            self.assertIn(needle, text)

    def test_prompt_reports_typecheck_gap_as_warning_unless_core_ac_unproven(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        self.assertIn("품질 게이트 warning", text)
        self.assertIn("warning 자체만으로 FAIL", text)
        self.assertIn("핵심 AC의 wiring/contract 동작을 증명할 수 없으면 FAIL gap", text)

    def test_prompt_classifies_ui_mock_alignment_and_screen_evidence_gap(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        for needle in (
            "UI 목업 정합 판정",
            "확정 목업",
            "화면 증거",
            "스크린샷",
            "Read 로 열어",
            "레이아웃 계층",
            "상태(default/empty/error",
            "토큰",
            "pixel-diff",
            "화면 증거 부재",
            "목업 불일치",
        ):
            self.assertIn(needle, text)

    def test_prompt_classifies_user_flow_fit_and_internal_contract_exposure(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        for needle in (
            "사용자 동선 적합성 판정",
            "대상 사용자가 제품의 언어와 자연스러운 진행 흐름",
            "금지어 체크리스트가 아니다",
            "내부 schema, DB shape, API payload, prompt/config shape, 내부 ID",
            "개발자용 CLI/API",
            "안정된 공개 계약",
            "핵심 AC가 대상 사용자에게 부적합한 입력/진행 동선",
        ):
            self.assertIn(needle, text)

    def test_pipeline_assigns_cross_pr_story_behavior_to_product_acceptance(self) -> None:
        text = self.impl_loop_finish.read_text(encoding="utf-8")
        self.assertIn("impl-validator는 계획 대비 구현 정합", text)
        self.assertIn("merge candidate diff 위험", text)
        self.assertIn("여러 PR이 합쳐진 story 동작", text)
        self.assertIn("여러 story가 합쳐진 epic 동작", text)
        self.assertIn("마감 product-acceptance가 맡는다", text)

    def test_write_zero_boundary_and_no_codex_route(self) -> None:
        self.assertEqual(ALLOW_MATRIX["product-acceptance"], ())
        self.assertNotIn("product-acceptance", ROUTABLE_VALIDATION_AGENTS)

    def test_prompt_executes_declared_journey_without_modifying_tracked_sources(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        for needle in (
            "dcness-product-journey run",
            "tracked 구현·설계 소스",
            ".dcness-work/product-journey/",
            "receipt 경로",
            "사람 확인 잔여 목록",
        ):
            self.assertIn(needle, text)

    def test_journey_taxonomy_build_handoff_and_acceptance_execution_align(self) -> None:
        module_prompt = self.module_architect_prompt.read_text(encoding="utf-8")
        template = self.impl_task_template.read_text(encoding="utf-8")
        build_worker = self.build_worker_prompt.read_text(encoding="utf-8")
        product_journey = self.product_journey.read_text(encoding="utf-8")
        init_dcness = self.init_dcness.read_text(encoding="utf-8")
        acceptance_skill = self.acceptance_skill.read_text(encoding="utf-8")
        acceptance_routing = self.acceptance_routing.read_text(encoding="utf-8")
        impl_loop_skill = (
            ROOT / "skills" / "impl-loop" / "impl-loop-finish.md"
        ).read_text(encoding="utf-8")
        impl_loop_routing = self.impl_loop_routing.read_text(encoding="utf-8")

        self.assertIn("(JOURNEY) <flow/매니페스트 경로>", template)
        self.assertIn("양성 프록시", module_prompt)
        self.assertIn("sub-second", module_prompt)
        self.assertIn("setup/teardown/상태전이 스크립트", build_worker)
        self.assertIn("PASS 블로커에서 제외", build_worker)
        self.assertIn("acceptance 인계", build_worker)
        self.assertIn("owner module/소스 영역", product_journey)
        self.assertIn("build-worker", product_journey)
        self.assertIn("product-acceptance", product_journey)
        self.assertIn("owner module/소스 영역", init_dcness)
        self.assertNotIn("project-local 계약 `.dcness/product-journey.json`", init_dcness)
        self.assertIn("product-acceptance가", acceptance_skill)
        self.assertIn("journey 매니페스트", acceptance_skill)
        self.assertIn("--config <매니페스트 경로>", acceptance_skill)
        self.assertNotIn(".dcness/product-journey.json", acceptance_skill)
        self.assertIn("product-acceptance가", acceptance_routing)
        self.assertIn("journey 매니페스트", acceptance_routing)
        self.assertIn("외부 상태 변경", impl_loop_skill)
        self.assertIn("`(JOURNEY)` REQ는 PASS 블로커가 아니다", impl_loop_routing)

    def test_public_surface_contract_mentions_internal_agent(self) -> None:
        script = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("'product-acceptance'", script)
        self.assertIn("`product-acceptance`", positioning)

    def test_harness_review_and_ledger_track_product_acceptance(self) -> None:
        self.assertIn("product-acceptance", EXPECTED_AGENT_BUDGETS)
        self.assertIn("product-acceptance", DCNESS_AGENT_NAMES)
        self.assertNotIn("product-acceptance", READONLY_AGENTS)
        self.assertEqual(
            infer_phase("acceptance", "product-acceptance", "STORY_ACCEPTANCE"),
            "acceptance",
        )
        self.assertEqual(
            infer_next_action(
                "product-acceptance",
                "STORY_ACCEPTANCE",
                must_fix=True,
                enum="FAIL",
            ),
            "acceptance gap 후속 분기(`/impl`/`/design`/`/spec`/`/ux`/`/to-issue`) 예상",
        )
        self.assertEqual(
            infer_next_action(
                "product-acceptance",
                "EPIC_ACCEPTANCE",
                must_fix=False,
                enum="FAIL",
            ),
            "acceptance gap 후속 분기(`/impl`/`/design`/`/spec`/`/ux`/`/to-issue`) 예상",
        )

    def test_prompt_uses_acceptance_routing_surface_names(self) -> None:
        prompt = self.prompt.read_text(encoding="utf-8")
        routing = self.acceptance_routing.read_text(encoding="utf-8")

        self.assertIn("`/to-issue` 후보 + `/impl` 또는 `/design`", prompt)
        self.assertIn("`/to-issue` 후보 + `/design` 또는 사용자 위임", prompt)
        self.assertIn("`/to-issue` 후보 + `/impl` 또는 `/design`", routing)
        self.assertIn("`/to-issue` 후보 + `/design` 또는 사용자 위임", routing)
        self.assertNotIn("performance improvement", prompt)
        self.assertNotIn("security deep-dive", prompt)


if __name__ == "__main__":
    unittest.main()
