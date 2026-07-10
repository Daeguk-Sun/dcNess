"""고위험 상태 계약 추적 문서 계약 테스트 (#1046)."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StateContractSharedPrinciplesTests(unittest.TestCase):
    """공유 SSOT — module-design-principles.md 의 고위험 상태 계약 절."""

    def setUp(self) -> None:
        self.shared = (
            ROOT / "docs" / "plugin" / "agents" / "_shared" / "module-design-principles.md"
        ).read_text(encoding="utf-8")

    def test_high_risk_state_contract_section_traces_transitions(self) -> None:
        """#1046 — 상태 계약은 추상 문구가 아니라 실제 전이로 추적한다."""
        for needle in (
            "## 고위험 상태 계약",
            "동일 identity 의 가변 필드 변경",
            "empty 와 read failure 구분",
            "source 일부 실패와 기존 상태 보존",
            "no-change/idempotence",
            "trigger → producer → state owner → mutation/write → persistence/read model → consumer",
        ):
            self.assertIn(needle, self.shared)

    def test_stateful_code_ssot_surface_extends_beyond_public_ports(self) -> None:
        """#1046 — 상태성 작업의 코드 SSOT 는 공개 포트만이 아니다."""
        for needle in (
            "schema",
            "mapper",
            "DAO",
            "sync/reconcile",
            "lifecycle producer",
            "관련 기존 테스트",
        ):
            self.assertIn(needle, self.shared)

    def test_confirmed_decision_is_not_verification_exempt(self) -> None:
        """#1046 — 확정 결정 재논쟁 금지 != 검증 면제."""
        self.assertIn("재논쟁", self.shared)
        self.assertIn("검증 면제", self.shared)

    def test_qualitative_findings_are_promotable_with_evidence(self) -> None:
        """#1046 — '질적 판단은 finding 아님' 충돌 문구 교체."""
        self.assertNotIn(
            "질적 판단이 필요한 영역은 finding 이 아니라 수동 review 권고로 분리",
            self.shared,
        )
        self.assertIn("질적 판단이라는 이유만으로", self.shared)
        self.assertIn("방치 시 영향", self.shared)


class ArchitectureValidatorStateContractTests(unittest.TestCase):
    """#1046 — validator 정의 / Codex mirror / design 입력 계약 정렬."""

    def setUp(self) -> None:
        self.validator = (
            ROOT
            / "docs" / "plugin" / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        self.codex_validator = (
            ROOT / "codex" / "skills" / "dcness-architecture-validator" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.design_skill = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.examples = (
            ROOT
            / "docs" / "plugin" / "agents"
            / "architecture-validator"
            / "references"
            / "finding-examples.md"
        ).read_text(encoding="utf-8")

    def test_validator_tracks_high_risk_state_contracts(self) -> None:
        for needle in (
            "고위험 상태 계약",
            "module-design-principles.md#고위험-상태-계약",
            "실제 update 경로",
            "재논쟁 금지는 검증 면제가 아니다",
        ):
            self.assertIn(needle, self.validator)

    def test_validator_composes_cross_story_state_and_reports_pass_evidence(self) -> None:
        self.assertIn("공유 identity", self.validator)
        self.assertIn("핵심 상태 전이", self.validator)
        self.assertIn("질적 판단이라는 이유만으로", self.validator)

    def test_codex_mirror_keeps_same_state_contract_semantics(self) -> None:
        for needle in (
            "고위험 상태 계약",
            "전체 implementation task 를 읽고",
            "검증 면제",
            "핵심 상태 전이",
            "질적 판단이라는 이유만으로",
        ):
            self.assertIn(needle, self.codex_validator)

    def test_design_skill_prompt_extends_stateful_code_ssot_pointers(self) -> None:
        self.assertIn(
            "sync/reconcile·adapter·lifecycle producer·관련 테스트",
            self.design_skill,
        )
        self.assertIn("고위험 상태 계약 추적", self.design_skill)

    def test_finding_examples_include_state_contract_false_pass(self) -> None:
        self.assertIn("## 고위험 상태 계약", self.examples)
        self.assertIn("mirror 에 반영되지 않음", self.examples)


if __name__ == "__main__":
    unittest.main()
