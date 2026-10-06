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

    def test_decision_lines_are_included_once_in_pack_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(root, impl_body="# Auth task\n\n- decision: docs/decisions/0001-auth.md\n")
            architecture = root / "docs/epics/epic-01-alpha/architecture.md"
            architecture.write_text(architecture.read_text() + "\n[decision](../../decisions/0001-auth.md)\n")
            decision = root / "docs/decisions/0001-auth.md"
            _write(decision, "# Decision\n" + "contract\n" * 2100)
            _write(root / "docs/decisions/0002-unrelated.md", "unrelated\n" * 100)
            proc = _run(root, "--json")
            plain = _run(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        budget = payload["epics"][0]
        self.assertEqual(budget["decision_line_count"], 2101)
        self.assertGreaterEqual(budget["design_pack_line_count"], 2101)
        self.assertIn("2101", plain.stdout)
        self.assertTrue(payload["ok"], "budget excess must remain advisory")

    def test_scoped_and_transitive_decisions_use_physical_line_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(root, impl_body="# Auth task\n")
            before = json.loads(_run(root, "--json").stdout)["epics"][0]
            decisions = root / "docs/decisions"
            _write(decisions / "0001-owned.md", "---\nscope: epic-01\n---\n[shared](../../decisions/0002-shared.md)\n")
            _write(decisions / "0002-shared.md", "[cycle](docs/decisions/0001-owned.md)")
            _write(decisions / "0003-module.md", "---\nscope: 'module:auth/epic-01' # scoped\n---\n")
            _write(decisions / "0004-other.md", "---\nscope: epic-02\n---\n")
            _write(decisions / "0005-empty.md", "")
            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        budget = json.loads(proc.stdout)["epics"][0]
        self.assertEqual(budget["decision_line_count"], 8)
        self.assertEqual(budget["design_pack_line_count"], before["design_pack_line_count"] + 8)
        self.assertEqual(len(budget["decision_paths"]), 3)

    def test_non_contiguous_story_group_is_a_design_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="""
                ---
                story: 1
                task_index: 1/2
                depends_on: []
                ---
                # Story 1 first task
                """,
            )
            _write(
                root / "docs/epics/epic-01-alpha/impl/02-story-two.md",
                """
                ---
                story: 2
                task_index: 1/1
                depends_on: [01-auth]
                ---
                # Story 2 task
                """,
            )
            _write(
                root / "docs/epics/epic-01-alpha/impl/03-story-one.md",
                """
                ---
                story: 1
                task_index: 2/2
                depends_on: [02-story-two]
                ---
                # Story 1 second task
                """,
            )

            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 1, proc.stderr)
        payload = json.loads(proc.stdout)
        violation = next(
            item
            for item in payload["violations"]
            if item["code"] == "impl-story-non-contiguous"
        )
        self.assertEqual(
            violation["file"],
            "docs/epics/epic-01-alpha/impl",
        )
        self.assertIn("story=1", violation["message"])

    def test_dependency_after_dependent_is_a_design_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="""
                ---
                story: 1
                task_index: 1/2
                depends_on: [02-api]
                ---
                # Consumer before dependency
                """,
            )
            _write(
                root / "docs/epics/epic-01-alpha/impl/02-api.md",
                """
                ---
                story: 1
                task_index: 2/2
                depends_on: []
                ---
                # Dependency
                """,
            )

            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 1, proc.stderr)
        payload = json.loads(proc.stdout)
        violation = next(
            item
            for item in payload["violations"]
            if item["code"] == "impl-runner-plan-invalid"
        )
        self.assertIn(
            "dependency order violation after path sorting",
            violation["message"],
        )
        self.assertIn("depends_on=02-api", violation["message"])


if __name__ == "__main__":
    unittest.main()
