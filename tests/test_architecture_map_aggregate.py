"""Regression tests for the architecture map aggregation tool (#811)."""
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


@unittest.skipUnless(NODE, "node not installed — architecture map tool is a node script")
class ArchitectureMapAggregateTests(unittest.TestCase):
    def test_generates_root_map_from_epic_architecture_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs/epics/epic-01-alpha/domain-model.md", "# Domain\n")
            _write(
                project / "docs/epics/epic-01-alpha/architecture.md",
                """
                # Epic Architecture

                ## 모듈 목록

                | 모듈 | 책임 | 의존 모듈 | 공개 API | 테스트 단위 |
                |---|---|---|---|---|
                | AuthCore | login orchestration | TokenStore | `authenticate()` | auth contract |
                | TokenStore | token persistence | - | `saveToken()` | token store |

                ## Contract Ledger

                | contract | owner | producer | consumer | invariant | ordering | error mode | config | forbidden alternative | refs |
                |---|---|---|---|---|---|---|---|---|---|
                | AuthSession | AuthCore | LoginForm | AuthCore | session id stable | login before refresh | reject | env | global mutable session | [ADR-0001](../../decisions/0001-auth.md) |

                ## Decisions

                | Decision | Scope | Reason |
                |---|---|---|
                | [ADR-0001](../../decisions/0001-auth.md) | global | auth decision |
                """,
            )

            proc = _run(project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            root_map = (project / "docs/architecture.md").read_text(encoding="utf-8")
            self.assertIn("## 에픽 간 지도", root_map)
            self.assertIn(
                "| [epic-01-alpha](epics/epic-01-alpha/architecture.md) | [domain-model.md](epics/epic-01-alpha/domain-model.md) | AuthCore, TokenStore | [ADR-0001](decisions/0001-auth.md) |",
                root_map,
            )
            self.assertIn(
                "| AuthCore | login orchestration | TokenStore | `authenticate()` | [epic-01-alpha](epics/epic-01-alpha/architecture.md) |",
                root_map,
            )
            self.assertIn("## 공유 계약 인덱스", root_map)
            self.assertIn(
                "| AuthSession | AuthCore | LoginForm | AuthCore | session id stable | [ADR-0001](decisions/0001-auth.md) | [epic-01-alpha](epics/epic-01-alpha/architecture.md) |",
                root_map,
            )

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_check_fails_when_root_map_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
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

            architecture = project / "docs/epics/epic-01-alpha/architecture.md"
            architecture.write_text(
                architecture.read_text(encoding="utf-8")
                + "| SessionCache | cache session | AuthCore | `getSession()` | cache test |\n",
                encoding="utf-8",
            )

            check = _run(project, "--check")
            self.assertEqual(check.returncode, 1)
            self.assertIn("stale", check.stderr)

    def test_preserves_manual_root_sections_while_updating_generated_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(
                project / "docs/architecture.md",
                """
                # 전역 아키텍처 지도

                ## 시스템 개요

                수동으로 작성한 개요.

                ## 에픽 간 지도

                old content

                ## 데이터 흐름

                수동 데이터 흐름.
                """,
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

            root_map = (project / "docs/architecture.md").read_text(encoding="utf-8")
            self.assertIn("수동으로 작성한 개요.", root_map)
            self.assertIn("수동 데이터 흐름.", root_map)
            self.assertIn("| AuthCore | login orchestration | - | `authenticate()` |", root_map)
            self.assertNotIn("old content", root_map)


if __name__ == "__main__":
    unittest.main()
