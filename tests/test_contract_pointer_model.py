"""Regression tests for module/decision based design artifacts (#969)."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


class ModuleDecisionContractModelTests(unittest.TestCase):
    def test_impl_task_template_uses_lightweight_module_decision_references_not_ledger_keys(self) -> None:
        template = read("docs/plugin/agents/module-architect/templates/impl-task.md")
        legacy_template = read(
            "docs/plugin/agents/module-architect/templates/contract-sweep-report.md"
        )

        self.assertNotIn("## 계약 / 결정 참조", template)
        self.assertNotIn("| kind | ref | action | note |", template)
        self.assertIn("계약/결정 링크", template)
        self.assertIn("module", template)
        self.assertIn("decision", template)
        self.assertNotIn("## Contract References", template)
        self.assertNotIn("Ledger row key", template)
        self.assertNotIn("row keys only", template)
        self.assertNotIn("## Contract\n", template)
        self.assertNotIn("## Module Design Check", template)
        self.assertIn("모듈 설계 주의", template)

        self.assertIn("Legacy Contract Sync Report", legacy_template)
        self.assertIn("module/decision 참조", legacy_template)
        self.assertIn("구양식", legacy_template)

    def test_impl_task_template_defaults_to_owner_dir_scope_and_command_acceptance(
        self,
    ) -> None:
        template = read("docs/plugin/agents/module-architect/templates/impl-task.md")
        module_architect = read("docs/plugin/agents/module-architect/module-architect-agent.md")

        for text in (template, module_architect):
            with self.subTest(text=text[:40]):
                self.assertIn("docs/conventions.md", text)
                self.assertIn("owner module directory", text)
                self.assertIn("끝 `/`", text)
                self.assertIn("신규 파일", text)
                self.assertIn("구현자 재량", text)
                self.assertIn("같은 owner directory", text)
                self.assertIn("file-level", text)
                self.assertIn("실행 가능한 명령", text)
                self.assertIn("(AGENT READ)", text)
                self.assertIn("사람 판정", text)

    def test_impl_task_scope_narrows_test_grants_to_owner_module_subdir(self) -> None:
        template = read("docs/plugin/agents/module-architect/templates/impl-task.md")
        module_architect = read("docs/plugin/agents/module-architect/module-architect-agent.md")

        for text in (template, module_architect):
            with self.subTest(text=text[:40]):
                self.assertIn("테스트 grant", text)
                self.assertIn("test root 전체", text)
                self.assertIn("owner module 에 대응하는 하위", text)
                self.assertIn("공통 기반 task", text)
                self.assertIn("사유를 주석", text)

    def test_agents_treat_module_list_and_decisions_as_contract_sources(self) -> None:
        module_architect = read("docs/plugin/agents/module-architect/module-architect-agent.md")
        validator = read(
            "docs/plugin/agents/architecture-validator/architecture-validator-agent.md"
        )
        amendment = read("docs/plugin/agents/module-architect/references/contract-amendment.md")

        for text in (module_architect, validator, amendment):
            with self.subTest(text=text[:40]):
                self.assertIn("module", text)
                self.assertIn("decision", text)
                self.assertIn("구양식", text)

        self.assertIn("module responsibility 한 줄과 decision 문서", module_architect)
        self.assertIn("impl 문서는 module/decision 참조", module_architect)
        self.assertIn("task 내부 한정 private interface", module_architect)
        self.assertIn("형식만으로 FAIL 하지 않는다", validator)
        self.assertIn("Should finding", validator)
        self.assertNotIn("CONTRACT_PROPAGATION", validator)

    def test_deliverables_map_records_doc_budget_and_contract_hierarchy(self) -> None:
        deliverables = read("docs/plugin/deliverables-map.md")

        self.assertIn("## 문서 총량 예산", deliverables)
        self.assertRegex(deliverables, r"normal epic.*1,500 lines")
        self.assertRegex(deliverables, r"hard warning.*2,000 lines")
        self.assertIn("Cross-task 계약 의미", deliverables)
        self.assertIn("## 모듈 목록", deliverables)
        self.assertIn("docs/decisions/NNNN-slug.md", deliverables)
        self.assertIn("impl/NN-*.md", deliverables)
        self.assertIn("module id 와 decision id/link", deliverables)

    def test_epic_architecture_template_is_minimal_agent_first_shape(self) -> None:
        template = read("docs/plugin/agents/system-architect/templates/epic-architecture.md")
        reference = read("docs/plugin/agents/system-architect/references/contract-ledger.md")

        for heading in ("## 모듈 목록", "## 의존 그래프", "## Story -> 모듈 매핑"):
            self.assertIn(heading, template)

        for stale in (
            "## Contract Ledger",
            "## Flow Ownership Map",
            "## Decisions",
            "## Module Design Check",
            "| contract | owner | producer | consumer |",
        ):
            self.assertNotIn(stale, template)

        self.assertIn("Legacy Contract Ledger", reference)
        self.assertIn("신규 `/design` 산출물은 Ledger row key 를 만들지 않는다", reference)


if __name__ == "__main__":
    unittest.main()
