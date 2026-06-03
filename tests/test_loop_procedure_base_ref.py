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


def resolve_stories_path(task_file: str) -> str:
    """§3.4 의 epic 단위 stories.md 경로 유도 (impl task 경로 조부모 + stories.md)."""
    cmd = f'printf %s "$(dirname "$(dirname "{task_file}")")/stories.md"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def resolve_stories_section(epic_dir: str = "", task_file: str = "") -> str:
    """§1.1.1 의 self-contained STORIES 유도 (EPIC_DIR / TASK_FILE / root 폴백) — 존재검사 전 derived 값.

    F1-c: 수동 env 의존 없이 입력만으로 epic 단위 경로를 산출하는지 검증 (파일 존재 폴백은 별도).
    """
    cmd = f'''
EPIC_DIR="{epic_dir}"; TASK_FILE="{task_file}"
if [ -n "${{EPIC_DIR:-}}" ]; then STORIES="$EPIC_DIR/stories.md"
elif [ -n "${{TASK_FILE:-}}" ]; then STORIES="$(dirname "$(dirname "$TASK_FILE")")/stories.md"
else STORIES="docs/stories.md"; fi
printf %s "$STORIES"
'''
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True).stdout.strip()


class TestStoriesPathResolution(unittest.TestCase):
    """F1-b/F1-c: base 분기용 stories.md 는 root 가 아니라 epic 단위 (입력에서 직접 유도) 여야 함."""

    def test_epic_level_stories_from_task_path(self):
        task = "docs/milestones/v0.2/epics/epic-07-foo/impl/03-bar.md"
        self.assertEqual(
            resolve_stories_path(task),
            "docs/milestones/v0.2/epics/epic-07-foo/stories.md",
        )

    def test_not_root_docs_stories(self):
        # 회귀 차단: epic 단위 task 인데 root docs/stories.md 로 떨어지면 통합 브랜치 base 누락
        task = "docs/milestones/v01/epics/epic-11-monkey/impl/01-theme.md"
        resolved = resolve_stories_path(task)
        self.assertNotEqual(resolved, "docs/stories.md")
        self.assertTrue(resolved.endswith("/epic-11-monkey/stories.md"), resolved)

    def test_section_self_contained_from_epic_dir(self):
        # architect-loop: EPIC_DIR 입력 → epic 단위 stories.md
        epic_dir = "docs/milestones/v01/epics/epic-11-monkey"
        self.assertEqual(
            resolve_stories_section(epic_dir=epic_dir),
            "docs/milestones/v01/epics/epic-11-monkey/stories.md",
        )

    def test_section_self_contained_from_task_file(self):
        # impl-loop: TASK_FILE 입력 (EPIC_DIR 없음) → task 경로 조부모 stories.md
        task = "docs/milestones/v0.2/epics/epic-07-foo/impl/03-bar.md"
        self.assertEqual(
            resolve_stories_section(task_file=task),
            "docs/milestones/v0.2/epics/epic-07-foo/stories.md",
        )

    def test_section_fallback_when_no_input(self):
        # 둘 다 부재 → root docs/stories.md legacy 폴백
        self.assertEqual(resolve_stories_section(), "docs/stories.md")

    def test_section_docs_impl_fallback_path(self):
        # 비정식 위치(docs/impl/) task — 조부모 = docs → root stories.md (안전 폴백, 통합 브랜치 비대상)
        task = "docs/impl/05-foo.md"
        self.assertEqual(resolve_stories_section(task_file=task), "docs/stories.md")


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
