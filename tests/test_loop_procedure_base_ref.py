"""docs/plugin/loop-procedure.md §1.1.1 의 base-ref 추출 sh 명령 검증 (#424).

§1.1.1 의 sh 블록:

    BASE_BRANCH=$(grep -m1 -E '^\\*\\*Base Branch:\\*\\*' docs/stories.md 2>/dev/null \\
      | sed -E 's/.*Base Branch:\\*\\*[[:space:]]+//')

이 추출 로직이 다양한 stories.md 입력에 대해 정상 동작하는지 검증.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path


def extract_base_branch(stories_content: str) -> str:
    """loop-procedure.md §1.1.1 의 grep+sed 로직 wrapping."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(stories_content)
        path = f.name
    try:
        cmd = (
            f"grep -m1 -E '^\\*\\*Base Branch:\\*\\*' {path} 2>/dev/null | "
            f"sed -E 's/.*Base Branch:\\*\\*[[:space:]]+//'"
        )
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
        )
        return result.stdout.strip()
    finally:
        Path(path).unlink()


class TestBaseBranchExtraction(unittest.TestCase):
    """§1.1.1 sh 추출 로직 검증."""

    def test_integration_branch_extracted(self):
        content = (
            "**GitHub Epic Issue:** [#19]\n"
            "**Base Branch:** feature/local-dsp\n"
            "\n# stories\n"
        )
        self.assertEqual(extract_base_branch(content), "feature/local-dsp")

    def test_no_marker_returns_empty(self):
        content = "# stories\n\nno marker here\n"
        self.assertEqual(extract_base_branch(content), "")

    def test_main_value(self):
        """Base Branch 가 main 으로 명시되면 'main' 추출."""
        content = "**Base Branch:** main\n"
        self.assertEqual(extract_base_branch(content), "main")

    def test_marker_with_extra_whitespace(self):
        """`**Base Branch:**` 와 값 사이 다중 공백/탭 허용."""
        content = "**Base Branch:**    feature/foo-bar\n"
        self.assertEqual(extract_base_branch(content), "feature/foo-bar")

    def test_first_match_only(self):
        """여러 줄 매치 시 첫 줄만 추출 (-m1)."""
        content = (
            "**Base Branch:** feature/first\n"
            "**Base Branch:** feature/second\n"
        )
        self.assertEqual(extract_base_branch(content), "feature/first")

    def test_marker_not_at_line_start_ignored(self):
        """`^` anchor — 줄 시작에 없으면 매치 X."""
        content = "prefix **Base Branch:** feature/foo\n"
        self.assertEqual(extract_base_branch(content), "")

    def test_marker_with_slash_in_value(self):
        """feature/<slug> 안 `/` 문자 유지."""
        content = "**Base Branch:** feature/epic-19/integration\n"
        self.assertEqual(
            extract_base_branch(content), "feature/epic-19/integration"
        )


class TestSSOTReferencePresent(unittest.TestCase):
    """SSOT (loop-procedure.md §1.1.1) 참조가 skill 본문에 박혀있는지 검증."""

    ROOT = Path(__file__).resolve().parent.parent

    def _read(self, rel: str) -> str:
        return (self.ROOT / rel).read_text(encoding="utf-8")

    def test_loop_procedure_section_present(self):
        body = self._read("docs/plugin/loop-procedure.md")
        self.assertIn("### 1.1.1 base-ref 분기", body)
        self.assertIn("**Base Branch:**", body)
        self.assertIn("git worktree add -b", body)
        self.assertIn("EnterWorktree(path=", body)

    def test_impl_loop_references_section(self):
        # impl + impl-loop 통합 — skills/impl-loop/SKILL.md 단일 진본
        body = self._read("skills/impl-loop/SKILL.md")
        self.assertIn("§1.1.1", body)
        self.assertIn("Base ref 분기", body)

    def test_architect_loop_references_section(self):
        body = self._read("skills/architect-loop/SKILL.md")
        self.assertIn("§1.1.1", body)
        self.assertIn("Base ref 분기", body)


if __name__ == "__main__":
    unittest.main()
