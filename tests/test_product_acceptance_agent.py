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
            / "agents"
            / "product-acceptance"
            / "product-acceptance-agent.md"
        )
        self.acceptance_routing = (
            ROOT / "skills" / "acceptance" / "acceptance-routing.md"
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
        self.assertIn("code-validator", text)
        self.assertIn("architecture-validator", text)
        self.assertIn("pr-reviewer", text)
        self.assertIn("대체하지 않는다", text)

    def test_prompt_keeps_full_e2e_out_of_mvp(self) -> None:
        text = self.prompt.read_text(encoding="utf-8")
        self.assertIn("full E2E", text)
        self.assertIn("MVP", text)
        self.assertIn("범위 밖", text)

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
            "acceptance gap 후속 라우팅(`/impl`/`/design`/`/spec`/`/ux`) 예상",
        )
        self.assertEqual(
            infer_next_action(
                "product-acceptance",
                "EPIC_ACCEPTANCE",
                must_fix=False,
                enum="FAIL",
            ),
            "acceptance gap 후속 라우팅(`/impl`/`/design`/`/spec`/`/ux`) 예상",
        )

    def test_prompt_uses_acceptance_routing_surface_names(self) -> None:
        prompt = self.prompt.read_text(encoding="utf-8")
        routing = self.acceptance_routing.read_text(encoding="utf-8")

        self.assertIn("issue 등록 후보 + `/impl` 또는 `/design`", prompt)
        self.assertIn("issue 등록 후보 + `/design` 또는 사용자 위임", prompt)
        self.assertIn("issue 등록 후보 + `/impl` 또는 `/design`", routing)
        self.assertIn("issue 등록 후보 + `/design` 또는 사용자 위임", routing)
        self.assertNotIn("performance improvement", prompt)
        self.assertNotIn("security deep-dive", prompt)


if __name__ == "__main__":
    unittest.main()
