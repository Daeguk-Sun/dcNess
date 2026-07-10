"""Acceptance gap routing contract tests."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AcceptanceGapRoutingContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.acceptance_routing = (
            ROOT / "skills" / "acceptance" / "acceptance-routing.md"
        )
        self.workflow_router = ROOT / "docs" / "plugin" / "workflow-router.md"

    def test_gap_taxonomy_routes_to_follow_up_loops(self) -> None:
        text = self.acceptance_routing.read_text(encoding="utf-8")
        expected_rows = {
            "PRD 유저 시나리오 / Story AC 미충족": "`/to-issue` 후보 + `/impl`",
            "설계 결함 / 범위 재정의 필요": "`/design` 또는 `/spec`",
            "검수 증거 부족 / 스모크 실패": "gap 또는 bug `/to-issue` 후보 + `/impl`",
            "mock-only green / 동작 증거 부족": "gap 또는 bug `/to-issue` 후보 + `/impl`",
            "화면 증거 부재": "gap 또는 bug `/to-issue` 후보 + `/impl`",
            "목업 불일치": "gap 또는 bug `/to-issue` 후보 + `/ux` 또는 `/impl`",
            "사용자 동선 부적합 / 내부 계약 노출": "gap 또는 bug `/to-issue` 후보 + `/ux` 또는 `/impl` 또는 `/design`",
            "UX 미완성": "`/ux`",
            "성능 병목 / 리팩토링 필요": "`/to-issue` 후보 + `/impl` 또는 `/design`",
            "보안 / 권한 / 데이터 리스크": "`/to-issue` 후보 + `/design` 또는 사용자 위임",
        }
        for gap_kind, follow_up in expected_rows.items():
            with self.subTest(gap_kind=gap_kind):
                self.assertIn(gap_kind, text)
                self.assertIn(follow_up, text)

    def test_issue_creation_requires_user_approval_or_explicit_option(self) -> None:
        text = self.acceptance_routing.read_text(encoding="utf-8")
        self.assertIn("1차", text)
        self.assertIn("2차", text)
        self.assertIn("3차", text)
        self.assertIn("자동 issue 생성하지 않는다", text)
        self.assertIn("사용자 승인", text)
        self.assertIn("명시 옵션", text)
        self.assertIn("GitHub issue", text)
        self.assertIn("story/epic sub-issue", text)
        self.assertIn("사람 full E2E gap loop", text)
        self.assertIn("MVP 범위 밖", text)

    def test_acceptance_distinguishes_behavior_evidence_from_mock_only(self) -> None:
        text = self.acceptance_routing.read_text(encoding="utf-8")
        for needle in (
            "동작 증거 판정",
            "정적 타입검사/compile",
            "실데이터(non-mock) 통합 테스트",
            "UI 자동화",
            "API/CLI smoke",
            "mock-only green",
            "화면 증거 부재",
            "목업 불일치",
            "품질 게이트 warning",
        ):
            self.assertIn(needle, text)

    def test_acceptance_gap_classifies_internal_contract_exposure_by_user_fit(self) -> None:
        text = self.acceptance_routing.read_text(encoding="utf-8")
        for needle in (
            "사용자 동선 적합성 판정",
            "특정 표현을 찾는 체크리스트가 아니라",
            "내부 schema, DB shape, API payload, prompt/config shape, 내부 ID",
            "사용자 동선 부적합 / 내부 계약 노출",
            "개발자용 CLI/API",
            "문서화된 계약이면 gap 이 아니며",
        ):
            self.assertIn(needle, text)

    def test_acceptance_gap_uses_to_issue_not_removed_issue_report(self) -> None:
        acceptance = self.acceptance_routing.read_text(encoding="utf-8")
        workflow_router = self.workflow_router.read_text(encoding="utf-8")

        for text in (acceptance, workflow_router):
            self.assertIn("acceptance gap issue", text)
            self.assertIn("제품 검수 후속", text)

        self.assertIn("/to-issue", acceptance)
        self.assertNotIn("/issue-report", acceptance)
        self.assertNotIn("/issue-report", workflow_router)

    def test_gap_routing_uses_design_after_surface_flip(self) -> None:
        text = self.acceptance_routing.read_text(encoding="utf-8")
        self.assertIn("`/design` 또는 `/spec`", text)
        self.assertNotIn("#649 시점", text)
        self.assertNotIn("공개 진입점 전환 이후", text)
        self.assertNotIn("[/design", text)


if __name__ == "__main__":
    unittest.main()
