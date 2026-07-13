"""`/impl-loop` story branch stack topology contract regression tests.

The filename is retained so existing test selection remains stable after the legacy
Base Branch marker contract was retired.
"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class StoryBranchStackContractTests(unittest.TestCase):
    def _read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_active_topology_surfaces_retire_base_branch_marker(self) -> None:
        surfaces = (
            "docs/plugin/git-spec.md",
            "docs/plugin/loop-procedure.md",
            "skills/spec/SKILL.md",
            "skills/spec/spec-delivery-reference.md",
            "skills/design/SKILL.md",
            "skills/design-ux/SKILL.md",
            "skills/design-system/SKILL.md",
            "skills/impl-loop/SKILL.md",
            "skills/impl-loop/impl-loop-routing.md",
        )

        for rel in surfaces:
            with self.subTest(path=rel):
                body = self._read(rel)
                self.assertNotIn("**Base Branch:**", body)
                self.assertNotIn("통합 브랜치", body)

    def test_loop_procedure_owns_stack_mechanics_and_no_merge_boundary(self) -> None:
        body = self._read("docs/plugin/loop-procedure.md")
        for needle in (
            "story 브랜치 스택",
            "직전 story 브랜치",
            "자동 merge 금지",
            "base=`main` 으로 리타겟",
            "리베이스",
            "downstream branch",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_git_spec_owns_stack_pr_and_close_contract(self) -> None:
        body = self._read("docs/plugin/git-spec.md")
        for needle in (
            "story 브랜치 스택",
            "PR 생성 시",
            "PR 머지 시점",
            "Closes #story",
            "사용자가 유일한 merge gate",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_spec_delivery_uses_one_main_based_docs_pr(self) -> None:
        skill = self._read("skills/spec/SKILL.md")
        reference = self._read("skills/spec/spec-delivery-reference.md")

        self.assertIn("docs/<slug>", skill)
        self.assertIn("story 브랜치 스택", skill)
        self.assertNotIn("feature/<slug>", reference)
        self.assertIn("gh pr create --base main", reference)

    def test_impl_validator_surfaces_use_stack_tip_merge_candidate(self) -> None:
        surfaces = (
            "docs/plugin/agents/impl-validator/impl-validator-agent.md",
            "docs/plugin/agents/impl-validator/templates/validation-report.md",
            "docs/plugin/agents/impl-validator/references/finding-classes.md",
            "codex/skills/dcness-impl-validator/SKILL.md",
        )

        for rel in surfaces:
            with self.subTest(path=rel):
                body = self._read(rel)
                self.assertIn("stack tip vs main", body)
                self.assertNotIn("합쳐진 diff", body)


if __name__ == "__main__":
    unittest.main()
