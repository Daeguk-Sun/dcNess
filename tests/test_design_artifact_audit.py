"""Regression tests for the /design artifact audit (#969)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_design_artifact_structure.mjs"
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


def _seed_project(
    root: Path,
    *,
    impl_body: str,
    architecture_body: str | None = None,
) -> None:
    _write(
        root / "docs/index.md",
        """
        # Project Index

        ## 에픽

        | 에픽 | 마일스톤 | Stories | Architecture | Domain Model | UX Flow | Tech Review |
        |---|---|---|---|---|---|---|
        | [epic-01-alpha](epics/epic-01-alpha/) | v01 | [stories.md](epics/epic-01-alpha/stories.md) | [architecture.md](epics/epic-01-alpha/architecture.md) | — | — | — |
        """,
    )
    _write(root / "docs/architecture.md", "# Root Architecture\n")
    _write(root / "docs/epics/epic-01-alpha/stories.md", "# Stories\n")
    _write(
        root / "docs/epics/epic-01-alpha/architecture.md",
        architecture_body
        or """
        # Epic Architecture

        ## 모듈 목록

        | 모듈 | 책임 | 공개 인터페이스 |
        |---|---|---|
        | AuthCore | session invariant owner; forbidden append: global mutable session | authenticate() |

        ## 의존 그래프

        ```mermaid
        flowchart LR
          AuthCore
        ```

        ## Story -> 모듈 매핑

        | Story | 영향 모듈 | 이유 |
        |---|---|---|
        | 1 | AuthCore | login behavior |
        """,
    )
    _write(root / "docs/epics/epic-01-alpha/impl/01-auth.md", impl_body)


@unittest.skipUnless(NODE, "node not installed - design artifact audit is a node script")
class DesignArtifactAuditTests(unittest.TestCase):
    def test_agent_first_minimal_artifacts_pass_without_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="""
                # Auth task

                ## 계약 / 결정 참조

                - module: AuthCore
                - decision: docs/decisions/0001-auth.md
                """,
            )

            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["violations"], [])
        self.assertEqual(payload["warnings"], [])

    def test_missing_core_agent_first_sections_are_warnings_not_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                architecture_body="# Epic Architecture\n\n## 모듈 목록\n\n-\n",
                impl_body="# Auth task\n",
            )

            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        warning_codes = {warning["code"] for warning in payload["warnings"]}
        self.assertIn("dependency-graph-missing", warning_codes)
        self.assertIn("story-module-map-missing", warning_codes)

    def test_budget_warning_reports_full_pack_over_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(root, impl_body="# Auth task\n")
            noisy_lines = "\n".join(f"- line {i}" for i in range(1510))
            _write(root / "docs/epics/epic-01-alpha/stories.md", f"# Stories\n{noisy_lines}\n")

            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(
            any(w["code"] == "design-pack-over-target" for w in payload["warnings"])
        )

if __name__ == "__main__":
    unittest.main()
