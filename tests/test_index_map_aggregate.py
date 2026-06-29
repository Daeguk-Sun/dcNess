"""Regression tests for the docs/index.md epic table aggregation tool (#823)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aggregate_index_map.mjs"
NODE = shutil.which("node")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE, str(SCRIPT), "--root", str(root), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


@unittest.skipUnless(NODE, "node not installed — index map tool is a node script")
class IndexMapAggregateTests(unittest.TestCase):
    def test_workflow_template_calls_doc_sync_action(self) -> None:
        workflow = (
            ROOT / "templates" / "github-workflows" / "doc-sync.yml"
        ).read_text(encoding="utf-8")
        action = (ROOT / ".github" / "actions" / "doc-sync" / "action.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: doc-sync", workflow)
        self.assertIn("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5", workflow)
        self.assertIn("alruminum/dcNess/.github/actions/doc-sync@main", workflow)
        self.assertNotIn("paths:", workflow)
        self.assertIn("scripts/aggregate_index_map.mjs", action)
        self.assertIn("scripts/aggregate_architecture_map.mjs", action)
        self.assertIn("--check", action)

    def test_generates_epic_table_from_epic_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(
                project / "docs/index.md",
                """
                # 프로젝트 문서 인덱스

                ## 개요

                수동 개요.

                ## 에픽

                old content

                ## 작업 영역

                수동 작업 영역.
                """,
            )
            _write(
                project / "docs/epics/epic-01-alpha/stories.md",
                """
                ---
                epic: epic-01-alpha
                milestone: v01
                ---

                # Story Backlog
                """,
            )
            _write(project / "docs/epics/epic-01-alpha/architecture.md", "# Architecture\n")
            _write(project / "docs/epics/epic-01-alpha/domain-model.md", "# Domain\n")
            _write(project / "docs/epics/epic-02-beta/stories.md", "# Story Backlog\n")
            _write(project / "docs/epics/epic-02-beta/tech-review.md", "# Tech Review\n")

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            index = (project / "docs/index.md").read_text(encoding="utf-8")
            self.assertIn("수동 개요.", index)
            self.assertIn("수동 작업 영역.", index)
            self.assertIn("<!-- dcness-index-map:generated -->", index)
            self.assertNotIn("old content", index)
            self.assertIn(
                "| [epic-01-alpha](epics/epic-01-alpha/) | v01 | [stories.md](epics/epic-01-alpha/stories.md) | [architecture.md](epics/epic-01-alpha/architecture.md) | [domain-model.md](epics/epic-01-alpha/domain-model.md) | — | — |",
                index,
            )
            self.assertIn(
                "| [epic-02-beta](epics/epic-02-beta/) | — | [stories.md](epics/epic-02-beta/stories.md) | — | — | — | [tech-review.md](epics/epic-02-beta/tech-review.md) |",
                index,
            )

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_check_fails_when_index_table_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/index.md", "# Index\n\n## 에픽\n\n")
            _write(project / "docs/epics/epic-01-alpha/stories.md", "# Story Backlog\n")
            self.assertEqual(_run(project).returncode, 0)

            _write(project / "docs/epics/epic-02-beta/stories.md", "# Story Backlog\n")

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 1)
            self.assertIn("stale", check.stderr)

    def test_no_epics_or_missing_index_is_noop_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/index.md", "# Index\n\n## 에픽\n\nmanual\n")

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("no-op", check.stdout)
            self.assertEqual(
                (project / "docs/index.md").read_text(encoding="utf-8"),
                "# Index\n\n## 에픽\n\nmanual\n",
            )

            missing_index = project / "missing-index"
            missing_index.mkdir()
            _write(missing_index / "docs/epics/epic-01-alpha/stories.md", "# Story Backlog\n")
            missing_check = _run(missing_index, "--check")
            self.assertEqual(missing_check.returncode, 0, missing_check.stderr)
            self.assertIn("no-op", missing_check.stdout)


if __name__ == "__main__":
    unittest.main()
