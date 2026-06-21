"""pr-trailer.sh 행동 테스트 — impl frontmatter 기반 PR 트레일러 자동 생성.

git-spec "PR 트레일러 (Part of / Closes)" 적용 절차의 한 명령 구현이 분기표대로
동작하는지 fixture 저장소 + 가짜 gh 스텁으로 검증한다.
"""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pr-trailer.sh"

STORIES_BODY = """# Story Backlog

## Epic — demo epic

**GitHub Epic Issue:** [#10](https://github.com/x/y/issues/10)

### Story 1 — first story

**GitHub Issue:** [#11](https://github.com/x/y/issues/11)

### Story 2 — second story

**GitHub Issue:** [#12](https://github.com/x/y/issues/12)
"""


def _write_fake_gh(bin_dir: Path, open_story_count: str) -> None:
    """gh 스텁 — `gh issue list ... --jq length` 호출에 open story 수를 돌려준다."""
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "issue" ] && [ "$2" = "list" ]; then\n'
        f"  echo {open_story_count}\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "issue" ] && [ "$2" = "view" ]; then\n'
        "  echo epic-07-demo\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)


class PrTrailerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.epic_dir = self.root / "docs/epics/epic-07-demo"
        (self.epic_dir / "impl").mkdir(parents=True)
        (self.epic_dir / "stories.md").write_text(STORIES_BODY, encoding="utf-8")
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()

    def tearDown(self) -> None:
        self._td.cleanup()

    def _task(self, name: str, story: str, task_index: str) -> Path:
        p = self.epic_dir / "impl" / name
        p.write_text(
            f"---\nstory: {story}\ntask_index: {task_index}\ndepends_on: []\n---\n# task\n",
            encoding="utf-8",
        )
        return p

    def _run(self, *args: str, open_story_count: str = "2") -> subprocess.CompletedProcess:
        _write_fake_gh(self.bin_dir, open_story_count)
        env = dict(os.environ)
        env["PATH"] = f"{self.bin_dir}:{env['PATH']}"
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=self.root,
        )

    def test_middle_task_part_of_story(self) -> None:
        task = self._task("01-first.md", "1", "1/2")
        result = self._run(str(task))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Part of #11\ntask-index: 1/2")

    def test_last_task_closes_story_only_when_epic_has_open_stories(self) -> None:
        task = self._task("02-last.md", "1", "2/2")
        result = self._run(str(task), open_story_count="2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Closes #11\ntask-index: 2/2")

    def test_last_task_of_last_story_closes_epic_too(self) -> None:
        task = self._task("02-last.md", "2", "2/2")
        result = self._run(str(task), open_story_count="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), "Closes #12\nCloses #10\ntask-index: 2/2"
        )

    def test_common_task_part_of_epic_without_task_index(self) -> None:
        task = self._task("00-common.md", "공통", "—")
        result = self._run(str(task))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Part of #10")
        self.assertNotIn("task-index", result.stdout)

    def test_malformed_task_index_blocks(self) -> None:
        task = self._task("03-bad.md", "1", "—")
        result = self._run(str(task))
        self.assertEqual(result.returncode, 1)
        self.assertIn("malformed", result.stderr)

    def test_missing_story_issue_marker_blocks(self) -> None:
        (self.epic_dir / "stories.md").write_text(
            "# Story Backlog\n\n**GitHub Epic Issue:** [#10](u)\n\n### Story 1 — x\n\n본문만\n",
            encoding="utf-8",
        )
        task = self._task("01-first.md", "1", "1/2")
        result = self._run(str(task))
        self.assertEqual(result.returncode, 1)
        self.assertIn("GitHub Issue", result.stderr)

    def test_base_mode_reads_integration_branch_marker(self) -> None:
        (self.epic_dir / "stories.md").write_text(
            "**Base Branch:** feature/shorts-template\n\n" + STORIES_BODY,
            encoding="utf-8",
        )
        task = self._task("01-first.md", "1", "1/2")
        result = self._run("--base", str(task))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "feature/shorts-template")

    def test_base_mode_defaults_to_main(self) -> None:
        task = self._task("01-first.md", "1", "1/2")
        result = self._run("--base", str(task))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "main")

    def test_integration_base_warns_autoclose_not_firing(self) -> None:
        (self.epic_dir / "stories.md").write_text(
            "**Base Branch:** feature/shorts-template\n\n" + STORIES_BODY,
            encoding="utf-8",
        )
        task = self._task("01-first.md", "1", "1/2")
        result = self._run(str(task))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Part of #11\ntask-index: 1/2")
        self.assertIn("통합 브랜치", result.stderr)
        self.assertIn("pr-finalize", result.stderr)


if __name__ == "__main__":
    unittest.main()
