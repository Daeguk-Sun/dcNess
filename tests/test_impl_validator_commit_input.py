"""Contract tests for commit-first impl-validator review inputs."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ImplValidatorCommitInputContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_claude_agent_exposes_bash_for_read_only_git_queries(self) -> None:
        entrypoint = self.read("agents/impl-validator.md")
        frontmatter_end = entrypoint.index("\n---\n", 4)
        frontmatter = entrypoint[4:frontmatter_end]

        self.assertIn("tools: Read, Glob, Grep, Bash", frontmatter)

    def test_validator_prompt_accepts_commit_as_first_class_input(self) -> None:
        prompts = (
            self.read(
                "docs/plugin/agents/impl-validator/impl-validator-agent.md"
            ),
            self.read("codex/skills/dcness-impl-validator/SKILL.md"),
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt[:40]):
                for needle in (
                    "커밋 id",
                    "변경 파일 목록",
                    "git show",
                    "git diff",
                    "git log",
                    "파일 수정",
                    "외부 상태 변경",
                    "읽기 전용",
                ):
                    self.assertIn(needle, prompt)
                self.assertNotIn("Bash를 쓰지 않는다.", prompt)

    def test_impl_callers_prefer_commit_id_and_keep_diff_file_as_fallback(
        self,
    ) -> None:
        callers = (
            self.read("skills/impl/SKILL.md"),
            self.read("skills/impl-loop/SKILL.md"),
        )

        for caller in callers:
            with self.subTest(caller=caller[:40]):
                for needle in (
                    "커밋 id",
                    "변경 파일 목록",
                    "diff 파일",
                    "uncommitted local diff",
                    "폴백",
                ):
                    self.assertIn(needle, caller)


if __name__ == "__main__":
    unittest.main()
