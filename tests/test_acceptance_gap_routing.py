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
        self.issue_report_routing = (
            ROOT / "skills" / "issue-report" / "issue-report-routing.md"
        )
        self.workflow_router = ROOT / "docs" / "plugin" / "workflow-router.md"

    def test_gap_taxonomy_routes_to_follow_up_loops(self) -> None:
        text = self.acceptance_routing.read_text(encoding="utf-8")
        expected_rows = {
            "PRD / AC 미충족": "issue 등록 후보 + `/impl`",
            "설계 결함 / 범위 재정의 필요": "`/design` 또는 `/spec`",
            "검수 증거 부족 / 스모크 실패": "gap 또는 bug issue 후보 + `/impl`",
            "UX 미완성": "`/ux`",
            "성능 병목 / 리팩토링 필요": "issue 등록 후보 + `/impl` 또는 `/design`",
            "보안 / 권한 / 데이터 리스크": "issue 등록 후보 + `/design` 또는 사용자 위임",
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
        self.assertIn("E2E gap loop", text)
        self.assertIn("MVP 범위 밖", text)

    def test_issue_report_boundary_is_distinct_from_acceptance_gap(self) -> None:
        acceptance = self.acceptance_routing.read_text(encoding="utf-8")
        issue_report = self.issue_report_routing.read_text(encoding="utf-8")
        workflow_router = self.workflow_router.read_text(encoding="utf-8")

        for text in (acceptance, issue_report, workflow_router):
            self.assertIn("미분류 버그 접수", text)
            self.assertIn("acceptance gap issue", text)
            self.assertIn("제품 검수 후속", text)

        self.assertIn("/issue-report", acceptance)
        self.assertIn("사용자 승인 없이 `/issue-report` 로 되돌리지 않는다", acceptance)

    def test_gap_routing_uses_design_after_surface_flip(self) -> None:
        text = self.acceptance_routing.read_text(encoding="utf-8")
        self.assertIn("`/design` 또는 `/spec`", text)
        self.assertNotIn("#649 시점", text)
        self.assertNotIn("surface flip 이후", text)
        self.assertNotIn("[/design", text)


if __name__ == "__main__":
    unittest.main()
