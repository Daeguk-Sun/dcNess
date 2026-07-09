"""Design token enforcement contract tests for design:required UI tasks."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


class DesignTokenEnforcementContractTests(unittest.TestCase):
    def test_build_worker_requires_design_tokens_as_independent_completion_axis(self) -> None:
        prompt = read("docs/plugin/agents/build-worker/build-worker-agent.md")

        for needle in (
            "design:required",
            "`docs/design.md` 토큰 적용은 필수 입력",
            "node-id 구조 대응과 분리된 별개 완료 조건",
            "앱 테마·컴포넌트 색이 `docs/design.md` 토큰대로 적용됐는가",
            "boilerplate 테마 잔존 금지",
            "목업과 다른 색 테마",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, prompt)

    def test_agent_prompt_slots_force_design_tokens_for_build_worker(self) -> None:
        slots = read("docs/plugin/templates/agent-prompt-slots.md")

        self.assertIn("impl-loop(build-worker)", slots)
        self.assertIn("design:required", slots)
        self.assertIn("build-worker 읽을 진본", slots)
        self.assertIn("`docs/design.md` 토큰", slots)
        self.assertIn("필수 포함", slots)

    def test_impl_task_template_records_core_tokens_next_to_node_mapping(self) -> None:
        template = read("docs/plugin/agents/module-architect/templates/impl-task.md")
        module_architect = read("docs/plugin/agents/module-architect/module-architect-agent.md")

        for text in (template, module_architect):
            with self.subTest(text=text[:60]):
                self.assertIn("핵심 디자인 토큰", text)
                self.assertIn("색/spacing/typography", text)
                self.assertIn("node-id 매핑과 나란히", text)

        self.assertIn("색 토큰", template)
        self.assertIn("spacing 토큰", template)
        self.assertIn("typography 토큰", template)

    def test_impl_validator_has_static_token_application_axis(self) -> None:
        prompt = read("docs/plugin/agents/impl-validator/impl-validator-agent.md")
        finding_classes = read("docs/plugin/agents/impl-validator/references/finding-classes.md")
        codex_skill = read("codex/skills/dcness-impl-validator/SKILL.md")

        for needle in (
            "design:required",
            "목업 디자인 토큰을 실제로 적용했는가",
            "self-report 와 분리",
            "토큰 참조 유무",
            "boilerplate 색 상수 잔존",
            "스캐폴딩 기본 테마 상수",
            "`spec-gap`/`quality-gap`",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, prompt)

        self.assertIn("boilerplate 색 상수 잔존", finding_classes)
        self.assertIn("디자인 토큰 적용 누락", finding_classes)

        for needle in (
            "design:required",
            "토큰 참조 유무",
            "boilerplate 색 상수 잔존",
            "self-report 와 분리",
        ):
            with self.subTest(codex_needle=needle):
                self.assertIn(needle, codex_skill)

    def test_product_acceptance_documents_visual_evidence_recipe(self) -> None:
        prompt = read("docs/plugin/agents/product-acceptance/product-acceptance-agent.md")

        for needle in (
            "UI 시각 증거 생성 권장 레시피",
            "앱 화면 자동화 스크린샷",
            "목업 headless 렌더",
            "같은 viewport",
            "구현 화면 증거",
            "실제 모양·토큰 일치",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, prompt)


if __name__ == "__main__":
    unittest.main()
