"""Regression tests for the docs/index.md generated table aggregation tool."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aggregate_index_map.mjs"
INDEX_TEMPLATE = ROOT / "skills" / "spec" / "templates" / "index.md"
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
        self.assertIn("Daeguk-Sun/dcNess/.github/actions/doc-sync@main", workflow)
        self.assertNotIn("paths:", workflow)
        self.assertIn("scripts/aggregate_index_map.mjs", action)
        self.assertNotIn("scripts/aggregate_architecture_map.mjs", action)
        self.assertIn("scripts/check_design_artifact_structure.mjs", action)
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
                "| [epic-01-alpha](epics/epic-01-alpha/) | v01 | [stories.md](epics/epic-01-alpha/stories.md) | [architecture.md](epics/epic-01-alpha/architecture.md) | [domain-model.md](epics/epic-01-alpha/domain-model.md) | — | — | `/design` (설계 미완) |",
                index,
            )
            self.assertIn(
                "| [epic-02-beta](epics/epic-02-beta/) | — | [stories.md](epics/epic-02-beta/stories.md) | — | — | — | [tech-review.md](epics/epic-02-beta/tech-review.md) | `/design` (설계 미완) |",
                index,
            )

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_epic_table_derives_next_action_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/index.md", "# Index\n\n## 에픽\n\n")
            # 설계 미완: stories 만 존재
            _write(project / "docs/epics/epic-01-alpha/stories.md", "# Story Backlog\n")
            # 설계 완료: architecture + impl task 존재
            _write(project / "docs/epics/epic-02-beta/stories.md", "# Story Backlog\n")
            _write(project / "docs/epics/epic-02-beta/architecture.md", "# Architecture\n")
            _write(project / "docs/epics/epic-02-beta/impl/01-foo.md", "# Task\n")
            # 설계 미완: architecture 는 있으나 impl task 부재 (핵심 엣지)
            _write(project / "docs/epics/epic-03-gamma/stories.md", "# Story Backlog\n")
            _write(project / "docs/epics/epic-03-gamma/architecture.md", "# Architecture\n")
            # 스펙 미작성: stories.md 부재 (에픽 디렉토리만 존재)
            _write(project / "docs/epics/epic-04-delta/notes.md", "placeholder\n")

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            index = (project / "docs/index.md").read_text(encoding="utf-8")
            self.assertIn(
                "| 에픽 | 마일스톤 | Stories | Architecture | Domain Model | UX Flow | Tech Review | 다음 액션 |",
                index,
            )
            self.assertRegex(index, r"epic-01-alpha.*\| `/design` \(설계 미완\) \|")
            self.assertRegex(index, r"epic-02-beta.*\| `/impl` \(설계 완료\) \|")
            self.assertRegex(index, r"epic-03-gamma.*\| `/design` \(설계 미완\) \|")
            self.assertRegex(index, r"epic-04-delta.*\| `/spec` \(스펙 미작성\) \|")

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_epic_table_marks_ux_done_system_incomplete_for_ui_epic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/index.md", "# Index\n\n## 에픽\n\n")
            _write(project / "docs/epics/epic-01-alpha/stories.md", "# Story Backlog\n")
            _write(project / "docs/epics/epic-01-alpha/ux-flow.md", "# UX Flow\n")

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            index = (project / "docs/index.md").read_text(encoding="utf-8")
            self.assertRegex(index, r"epic-01-alpha.*\| `/design` \(ux 완료 · system 미완\) \|")

    def test_impl_task_must_match_nn_prefix_for_design_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/index.md", "# Index\n\n## 에픽\n\n")
            _write(project / "docs/epics/epic-01-alpha/stories.md", "# Story Backlog\n")
            _write(project / "docs/epics/epic-01-alpha/architecture.md", "# Architecture\n")
            # impl/ 에 NN- prefix 아닌 파일만 있으면 설계 완료로 보지 않는다
            _write(project / "docs/epics/epic-01-alpha/impl/README.md", "# Notes\n")

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            index = (project / "docs/index.md").read_text(encoding="utf-8")
            self.assertRegex(index, r"epic-01-alpha.*\| `/design` \(설계 미완\) \|")

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

    def test_seeded_index_template_is_fresh_without_epics_or_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "docs").mkdir()
            shutil.copyfile(INDEX_TEMPLATE, project / "docs" / "index.md")

            check = _run(project, "--check")

        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("PASS", check.stdout)

    def test_generates_module_table_from_module_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(
                project / "docs/index.md",
                """
                # 프로젝트 문서 인덱스

                ## 개요

                수동 개요.
                """,
            )
            _write(project / "docs/modules/android/architecture.md", "# Android Architecture\n")
            _write(project / "docs/modules/android/conventions.md", "# Android Conventions\n")
            _write(project / "docs/modules/backend/conventions.md", "# Backend Conventions\n")

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            index = (project / "docs/index.md").read_text(encoding="utf-8")
            self.assertIn("수동 개요.", index)
            self.assertIn("## 모듈", index)
            self.assertIn("<!-- dcness-module-map:generated -->", index)
            self.assertIn(
                "| [android](modules/android/) | [architecture.md](modules/android/architecture.md) | [conventions.md](modules/android/conventions.md) | — |",
                index,
            )
            self.assertIn(
                "| [backend](modules/backend/) | — | [conventions.md](modules/backend/conventions.md) | — |",
                index,
            )

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_ignores_module_directories_that_do_not_match_module_id_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/index.md", "# 프로젝트 문서 인덱스\n")
            _write(project / "docs/modules/android/architecture.md", "# Android\n")
            _write(project / "docs/modules/3d-engine/architecture.md", "# 3D Engine\n")

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            index = (project / "docs/index.md").read_text(encoding="utf-8")
            self.assertIn(
                "| [android](modules/android/) | [architecture.md](modules/android/architecture.md) | — | — |",
                index,
            )
            self.assertNotIn("3d-engine", index)

    def test_generated_module_table_becomes_stale_when_module_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/index.md", "# Index\n")
            _write(project / "docs/modules/android/architecture.md", "# Android\n")
            self.assertEqual(_run(project).returncode, 0)

            shutil.rmtree(project / "docs/modules/android")

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 1)
            self.assertIn("stale", check.stderr)

            self.assertEqual(_run(project).returncode, 0)
            index = (project / "docs/index.md").read_text(encoding="utf-8")
            self.assertIn("| — | — | — | — |", index)

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
