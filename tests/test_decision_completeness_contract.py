"""Decision-completeness semantic contract regression tests."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DecisionCompletenessContractTests(unittest.TestCase):
    def test_contract_defines_scope_evidence_and_completion_without_schema(self) -> None:
        contract = (ROOT / "docs" / "plugin" / "decision-completeness.md").read_text(
            encoding="utf-8"
        )

        for scope in (
            "actor",
            "데이터와 관계",
            "상태와 lifecycle",
            "실패와 복구",
            "권한과 보안",
            "외부 연동",
            "사용자 경험과 정책",
            "운영 제약",
        ):
            with self.subTest(scope=scope):
                self.assertIn(scope, contract)

        for evidence in (
            "사용자 확정",
            "프로젝트 근거",
            "목표에서 도출",
            "명시적 위임",
            "미결정",
            "근거 없는 가정",
        ):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, contract)

        for rule in (
            "구현 방향을 바꿀 수 있는",
            "0개",
            "질문 개수",
            "고정 questionnaire",
            "출력 형식",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, contract)

    def test_existing_spec_and_validation_surfaces_consume_the_contract(self) -> None:
        paths = (
            "skills/spec/SKILL.md",
            "skills/spec/spec-prd-reference.md",
            "docs/plugin/agents/product-acceptance/product-acceptance-agent.md",
            "docs/plugin/agents/architecture-validator/architecture-validator-agent.md",
            "codex/skills/dcness-architecture-validator/SKILL.md",
        )
        for relpath in paths:
            text = (ROOT / relpath).read_text(encoding="utf-8")
            with self.subTest(relpath=relpath):
                self.assertIn("decision-completeness.md", text)
                self.assertIn("근거 없는 가정", text)
                self.assertIn("중요한 미결정", text)

        product_acceptance = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "product-acceptance"
            / "product-acceptance-agent.md"
        ).read_text(encoding="utf-8")
        architecture_validator = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        self.assertIn("고정 표", product_acceptance)
        self.assertIn("고정 표", architecture_validator)

        codex_validator = (
            ROOT / "codex" / "skills" / "dcness-architecture-validator" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for semantic_anchor in (
            "actor",
            "데이터와 관계",
            "상태와 lifecycle",
            "실패와 복구",
            "권한과 보안",
            "외부 연동",
            "사용자 경험과 정책",
            "운영 제약",
            "사용자 확정",
            "프로젝트 근거",
            "목표에서 도출",
            "명시적 위임",
            "미결정",
        ):
            with self.subTest(codex_semantic_anchor=semantic_anchor):
                self.assertIn(semantic_anchor, codex_validator)
        self.assertIn("skill 본문만으로", codex_validator)

    def test_behavior_eval_has_two_missing_cases_and_one_grounded_control(self) -> None:
        cases = ROOT / "evals" / "cases"
        names = (
            "decision-completeness-unresolved",
            "decision-completeness-ungrounded",
            "decision-completeness-grounded",
        )
        for name in names:
            case = cases / name
            with self.subTest(case=name):
                self.assertTrue((case / "prompt.md").is_file())
                self.assertTrue((case / "expected.md").is_file())
                self.assertTrue((case / "prd.md").is_file())
                self.assertTrue((case / "stories.md").is_file())

        unresolved = (cases / names[0] / "expected.md").read_text(encoding="utf-8")
        ungrounded = (cases / names[1] / "expected.md").read_text(encoding="utf-8")
        grounded = (cases / names[2] / "expected.md").read_text(encoding="utf-8")
        self.assertIn("[MUST]", unresolved)
        self.assertIn("[MUST]", ungrounded)
        self.assertIn("[MUST_NOT]", grounded)

    def test_two_real_pilots_trace_decisions_and_record_human_approval(self) -> None:
        pilots = (
            ROOT / "docs" / "internal" / "decision-completeness-pilots.md"
        ).read_text(encoding="utf-8")

        for pilot in ("Pilot A", "Pilot B"):
            with self.subTest(pilot=pilot):
                self.assertIn(pilot, pilots)

        for evidence in (
            "사용자 확정",
            "프로젝트 근거",
            "목표에서 도출",
            "명시적 위임",
            "미결정 처리",
            "명세 또는 수용 기준",
            "human verification 승인 (2026-07-12)",
        ):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, pilots)

        self.assertNotIn("human verification 대기", pilots)
        self.assertIn("추가로 빠진 구현 방향 선택은 보고되지 않았다", pilots)

        for source in (
            "실제 작업 fixture: 세로 영상 제작 기능",
            "실제 외부 작업 — 기본 메시지 앱 목표",
            "원본 확인 시각",
            "원본 위치",
            "원본 PRD SHA-256",
            "원본 Story SHA-256",
            "첫 발신 전이 결정 SHA-256",
        ):
            with self.subTest(source=source):
                self.assertIn(source, pilots)

        for external_name in (
            "GitHub",
            "Daeguk-Sun",
            "dcNess",
            "jajang",
            "youTubeGenerator",
            "NexusMessenger",
            "BMAD",
        ):
            with self.subTest(external_name=external_name):
                self.assertNotIn(external_name, pilots)


if __name__ == "__main__":
    unittest.main()
