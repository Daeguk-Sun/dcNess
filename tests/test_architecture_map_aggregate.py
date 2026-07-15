"""Regression tests for the on-demand architecture map report tool (#811/#969)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aggregate_architecture_map.mjs"
NODE = shutil.which("node")
CARTOGRAPHY_FIXTURE = ROOT / "tests" / "fixtures" / "architecture-cartography"


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


def _report(root: Path) -> Path:
    return root / ".dcness-work" / "reports" / "architecture-map.md"


def _section(content: str, heading: str) -> str:
    marker = f"## {heading}"
    start = content.index(marker) + len(marker)
    rest = content[start:]
    next_heading = rest.find("\n## ")
    return rest if next_heading == -1 else rest[:next_heading]


def _table_cell_counts(section: str) -> list[int]:
    counts: list[int] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = stripped.strip("|").split("|")
        if all(set(cell.strip()) <= {"-", ":"} for cell in cells):
            continue
        counts.append(len(cells))
    return counts


@unittest.skipUnless(NODE, "node not installed — architecture map tool is a node script")
class ArchitectureMapAggregateTests(unittest.TestCase):
    def test_latest_template_preserves_public_interface_decisions_and_epic_owner(self) -> None:
        proc = _run(CARTOGRAPHY_FIXTURE, "--stdout")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("`receiveSms(intent)`", proc.stdout)
        self.assertIn("`receiveMms(wapPush)`", proc.stdout)
        self.assertIn("[ADR-0001]", proc.stdout)
        self.assertIn("[ADR-0002]", proc.stdout)
        self.assertIn("[epic-01-sms]", proc.stdout)
        self.assertIn("[epic-02-mms]", proc.stdout)
        self.assertNotIn("| SmsIngress | SMS receive owner | - | - |", proc.stdout)
        self.assertIn(
            "| module | SMS receive owner | SmsIngress | `receiveSms(intent)` | MessageStore | receiver contract test | [ADR-0001](../../docs/decisions/0001-message-routing.md) | [epic-01-sms](../../docs/epics/epic-01-sms/architecture.md) |",
            proc.stdout,
        )
        epic_map = _section(proc.stdout, "에픽 간 지도")
        self.assertEqual(epic_map.count("[ADR-0002]"), 1)

    def test_rebases_module_doc_links_from_epic_module_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/architecture.md", "# 전역 아키텍처 지도\n")
            _write(project / "docs/modules/android/architecture.md", "# Android\n")
            _write(
                project / "docs/epics/epic-01-mobile/architecture.md",
                """
                # Epic Architecture

                ## 모듈 목록

                | 모듈 | 책임 | 의존 모듈 | 공개 API | 테스트 단위 |
                |---|---|---|---|---|
                | [android](../../modules/android/architecture.md) | mobile UI shell | - | `MainActivity` | android smoke |
                """,
            )

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            root_map = _report(project).read_text(encoding="utf-8")
            self.assertIn(
                "| [android](../../docs/modules/android/architecture.md) | mobile UI shell | - | `MainActivity` | [epic-01-mobile](../../docs/epics/epic-01-mobile/architecture.md) |",
                root_map,
            )

    def test_does_not_mutate_manual_root_anchor_while_generating_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            manual_root = textwrap.dedent(
                """
                # 전역 아키텍처 지도

                ## 시스템 개요

                수동으로 작성한 개요.

                ## 에픽 간 지도

                old content

                ## 데이터 흐름

                수동 데이터 흐름.
                """
            ).lstrip()
            _write(
                project / "docs/architecture.md",
                manual_root,
            )
            _write(
                project / "docs/epics/epic-01-alpha/architecture.md",
                """
                # Epic Architecture

                ## 모듈 목록

                | 모듈 | 책임 | 의존 모듈 | 공개 API | 테스트 단위 |
                |---|---|---|---|---|
                | AuthCore | login orchestration | - | `authenticate()` | auth contract |
                """,
            )

            self.assertEqual(_run(project).returncode, 0)

            self.assertEqual(
                (project / "docs/architecture.md").read_text(encoding="utf-8"),
                manual_root,
            )
            report = _report(project).read_text(encoding="utf-8")
            self.assertIn("| AuthCore | login orchestration | - | `authenticate()` |", report)
            self.assertNotIn("old content", report)

    def test_no_epic_architecture_is_noop_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/architecture.md", "# 전역 아키텍처 지도\n\nmanual\n")

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("no-op", proc.stdout)
            self.assertEqual(
                (project / "docs/architecture.md").read_text(encoding="utf-8"),
                "# 전역 아키텍처 지도\n\nmanual\n",
            )
            self.assertFalse(_report(project).exists())

    def test_missing_root_anchor_still_generates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_root_map = Path(tmp)
            _write(
                missing_root_map / "docs/epics/epic-01-alpha/architecture.md",
                """
                # Epic Architecture

                ## 모듈 목록

                | 모듈 | 책임 | 의존 모듈 | 공개 API |
                |---|---|---|---|
                | AuthCore | login orchestration | - | `authenticate()` |
                """,
            )
            proc = _run(missing_root_map)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse((missing_root_map / "docs/architecture.md").exists())
            self.assertIn("AuthCore", _report(missing_root_map).read_text(encoding="utf-8"))

    def test_stdout_mode_prints_report_without_writing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(
                project / "docs/epics/epic-01-alpha/architecture.md",
                """
                # Epic Architecture

                ## 모듈 목록

                | 모듈 | 책임 | 의존 모듈 | 공개 API |
                |---|---|---|---|
                | AuthCore | login orchestration | - | `authenticate()` |
                """,
            )

            proc = _run(project, "--stdout")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("# 전역 아키텍처 온디맨드 리포트", proc.stdout)
            self.assertIn("AuthCore", proc.stdout)
            self.assertFalse(_report(project).exists())

    def test_check_mode_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            proc = _run(project, "--check")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("unknown argument: --check", proc.stderr)


if __name__ == "__main__":
    unittest.main()
