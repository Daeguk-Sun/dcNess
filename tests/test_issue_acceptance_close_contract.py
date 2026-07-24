"""Contract tests for target GitHub issue acceptance at implementation close."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IssueAcceptanceCloseContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_impl_reads_target_issue_once_and_blocks_clean_close_on_unchecked_ac(self) -> None:
        skill = self.read("skills/impl/SKILL.md") + self.read(
            "skills/impl/impl-finish.md"
        )
        routing = self.read("skills/impl/impl-routing.md")

        for text in (skill, routing):
            self.assertIn("target GitHub issue AC", text)
            self.assertIn("require-complete", text)
            self.assertIn("미체크", text)
        self.assertIn("본문과 댓글을 한 번", skill)
        self.assertIn("close 경계에서 한 번", skill)

    def test_impl_loop_clean_contract_includes_target_issue_ac(self) -> None:
        skill = self.read("skills/impl-loop/SKILL.md") + self.read(
            "skills/impl-loop/impl-loop-finish.md"
        )

        for text in (skill,):
            self.assertIn("target GitHub issue AC", text)
            self.assertIn("require-complete", text)
            self.assertIn("미체크", text)

    def test_build_worker_treats_target_issue_ac_as_upper_contract(self) -> None:
        worker = self.read("docs/plugin/agents/build-worker/build-worker-agent.md")

        self.assertIn("target GitHub issue AC", worker)
        self.assertIn("상위 완료 계약", worker)
        self.assertIn("issue mutation", worker)

    def test_impl_validator_uses_plan_union_target_issue_ac_in_both_providers(self) -> None:
        surfaces = (
            self.read("docs/plugin/agents/impl-validator/impl-validator-agent.md"),
            self.read("codex/skills/dcness-impl-validator/SKILL.md"),
            self.read("agents/impl-validator.md"),
        )

        for text in surfaces:
            self.assertIn("plan ∪ target GitHub issue AC", text)
            self.assertIn("direct", text)

    def test_human_verification_wait_is_not_blocked(self) -> None:
        surfaces = (
            self.read("skills/impl/impl-finish.md"),
            self.read("skills/impl-loop/impl-loop-finish.md"),
            self.read("docs/plugin/issue-lifecycle.md"),
        )

        for text in surfaces:
            self.assertIn("human verification", text)
            self.assertIn("blocked", text)

    def test_to_issue_documents_three_verification_classes(self) -> None:
        skill = self.read("skills/to-issue/SKILL.md")
        template = self.read("skills/to-issue/templates/issue-brief.md")

        for text in (skill, template):
            self.assertIn("[command]", text)
            self.assertIn("[agent-read]", text)
            self.assertIn("Human verification / 사람 확인 안내", text)
        self.assertIn("체크박스를 쓰지 않는다", skill)
        self.assertIn("일반론", skill)

    def test_repo_self_contract_requires_issue_ac_close_audit(self) -> None:
        repo_contract = self.read("CLAUDE.md")

        self.assertIn("target GitHub issue AC", repo_contract)
        self.assertIn("require-complete", repo_contract)

    def test_impl_validator_eval_prompts_declare_issue_absence(self) -> None:
        prompts = (
            self.read("evals/cases/flow-ownership-entrypoint-bad/prompt.md"),
            self.read("evals/cases/flow-ownership-owner-good/prompt.md"),
        )

        for prompt in prompts:
            self.assertIn("대상 GitHub issue: 없음", prompt)


if __name__ == "__main__":
    unittest.main()
