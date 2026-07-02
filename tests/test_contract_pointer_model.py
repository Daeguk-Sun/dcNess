"""Regression tests for Contract Ledger pointer-based design artifacts (#832)."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


class ContractPointerModelTests(unittest.TestCase):
    def test_impl_task_template_uses_ledger_row_references_not_contract_copies(self) -> None:
        template = read("agents/module-architect/templates/impl-task.md")
        sweep_template = read(
            "agents/module-architect/templates/contract-sweep-report.md"
        )

        self.assertIn("## Contract References", template)
        self.assertIn("Ledger row key", template)
        self.assertIn("row keys only", template)
        self.assertNotIn("## Contract\n", template)
        for text in (template, sweep_template):
            self.assertNotRegex(
                text,
                r"\|\s*contract\s*\|\s*owner\s*\|\s*producer\s*\|\s*consumer\s*\|"
                r"\s*invariant\s*\|\s*ordering\s*\|\s*error mode\s*\|",
            )
        self.assertIn("Canonical Ledger Row", sweep_template)
        self.assertIn("행 키 참조", sweep_template)

    def test_agents_treat_epic_contract_ledger_as_single_source_of_truth(self) -> None:
        module_architect = read("agents/module-architect/module-architect-agent.md")
        validator = read(
            "agents/architecture-validator/architecture-validator-agent.md"
        )
        amendment = read("agents/module-architect/references/contract-amendment.md")

        for text in (module_architect, validator, amendment):
            with self.subTest(text=text[:40]):
                self.assertIn("Contract Ledger", text)
                self.assertIn("행 키", text)
                self.assertIn("구양식", text)

        self.assertIn("cross-task 계약 전문은 Contract Ledger 에만", module_architect)
        self.assertIn("impl/compact plan 은 Ledger 행 키", module_architect)
        self.assertIn("task 내부 한정 private interface", module_architect)
        self.assertIn("신규 산출물", validator)
        self.assertIn("구양식 산출물", validator)
        self.assertIn("전문 사본", validator)

    def test_deliverables_map_records_doc_budget_and_contract_hierarchy(self) -> None:
        deliverables = read("docs/plugin/deliverables-map.md")

        self.assertIn("## 문서 총량 예산", deliverables)
        self.assertRegex(deliverables, r"normal epic.*1,500 lines")
        self.assertRegex(deliverables, r"hard warning.*2,000 lines")
        self.assertIn("Contract Ledger", deliverables)
        self.assertIn("stable row key", deliverables)
        self.assertIn("impl/NN-*.md", deliverables)
        self.assertIn("row-key references", deliverables)

    def test_contract_ledger_template_keeps_parser_header_and_declares_key_stability(self) -> None:
        template = read("agents/system-architect/templates/epic-architecture.md")
        reference = read("agents/system-architect/references/contract-ledger.md")

        self.assertIn(
            "| contract | owner | producer | consumer | invariant | ordering | error mode | config | forbidden alternative | refs |",
            template,
        )
        self.assertIn("stable row key", template)
        self.assertIn("발급 후 재사용·의미 변경 금지", reference)
        self.assertIn("사본을 만들지 않는다", reference)


if __name__ == "__main__":
    unittest.main()
