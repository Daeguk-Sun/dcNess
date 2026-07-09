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
    EXPECTED_FINAL_ENUMS,
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

    def test_agent_entrypoint_exists_and_points_to_prompt(self) -> None:
        text = self.entry.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name:\s*product-acceptance$")
        self.assertIn("tools: Read, Glob, Grep", text)
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
        text = self.impl_loop_routing.read_text(encoding="utf-8")
        self.assertIn("impl-validator 는 계획 대비 구현 정합", text)
        self.assertIn("impl-validator 는 계획 대비 구현 정합과 merge candidate diff 위험", text)
        self.assertIn("여러 PR 이 합쳐진 story 동작", text)
        self.assertIn("여러 story 가 합쳐진 epic 동작", text)
        self.assertIn("마감 product-acceptance 가 맡는다", text)

    def test_read_only_boundary_and_no_codex_route(self) -> None:
        self.assertEqual(ALLOW_MATRIX["product-acceptance"], ())
        self.assertNotIn("product-acceptance", ROUTABLE_VALIDATION_AGENTS)

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
        self.assertEqual(EXPECTED_FINAL_ENUMS["product-acceptance"], {None: "PASS"})
        self.assertIn("product-acceptance", EXPECTED_AGENT_BUDGETS)
        self.assertIn("product-acceptance", DCNESS_AGENT_NAMES)
        self.assertIn("product-acceptance", READONLY_AGENTS)
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
