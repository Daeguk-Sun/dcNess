"""Regression tests for active-project doc path integrity validation."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_doc_path_integrity.mjs"
NODE = shutil.which("node")


def _run(project_root: Path, docs: str | None = None) -> subprocess.CompletedProcess[str]:
    args = [NODE, str(SCRIPT), "--root", str(project_root)]
    if docs is not None:
        args.extend(["--docs", docs])
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


@unittest.skipUnless(NODE, "node not installed - doc-path gate is a node script")
class DocPathIntegrityTests(unittest.TestCase):
    def test_workflow_template_calls_doc_path_action(self) -> None:
        workflow = (
            ROOT / "templates" / "github-workflows" / "doc-path-integrity.yml"
        ).read_text(encoding="utf-8")
        action = (
            ROOT / ".github" / "actions" / "doc-path-integrity" / "action.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("name: doc-path-integrity", workflow)
        self.assertIn("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5", workflow)
        self.assertIn("alruminum/dcNess/.github/actions/doc-path-integrity@main", workflow)
        self.assertNotIn("paths:", workflow)
        self.assertIn("scripts/check_doc_path_integrity.mjs", action)

    def test_valid_inline_and_markdown_paths_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "decisions").mkdir(parents=True)
            (root / "CLAUDE.md").write_text(
                "Read `docs/index.md` and [ADR](docs/decisions/0001-record.md).\n",
                encoding="utf-8",
            )
            (root / "docs" / "index.md").write_text("# Index\n", encoding="utf-8")
            (root / "docs" / "decisions" / "0001-record.md").write_text(
                "# ADR\n", encoding="utf-8"
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_broken_inline_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text(
                "Stale SSOT lives at `docs/missing.md`.\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("docs/missing.md", proc.stderr)

    def test_required_index_missing_fails_without_self_repo_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text(
                "Read active project docs at `docs/index.md`.\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("docs/index.md", proc.stderr)

    def test_dcness_self_active_project_paths_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "plugin.json").write_text("{}\n", encoding="utf-8")
            (root / "docs" / "plugin").mkdir(parents=True)
            (root / "docs" / "plugin" / "deliverables-map.md").write_text(
                "# Deliverables\n", encoding="utf-8"
            )
            (root / "scripts").mkdir()
            (root / "scripts" / "check_cross_refs.mjs").write_text(
                "console.log('ok');\n", encoding="utf-8"
            )
            (root / "CLAUDE.md").write_text(
                "dcNess self references active-project `docs/index.md` and "
                "`docs/decisions/` as deployed contracts.\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_dcness_self_marker_does_not_ignore_other_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "plugin.json").write_text("{}\n", encoding="utf-8")
            (root / "docs" / "plugin").mkdir(parents=True)
            (root / "docs" / "plugin" / "deliverables-map.md").write_text(
                "# Deliverables\n", encoding="utf-8"
            )
            (root / "scripts").mkdir()
            (root / "scripts" / "check_cross_refs.mjs").write_text(
                "console.log('ok');\n", encoding="utf-8"
            )
            (root / "CLAUDE.md").write_text(
                "A real stale reference remains `docs/missing.md`.\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("docs/missing.md", proc.stderr)

    def test_broken_markdown_link_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "index.md").write_text(
                "See [missing](architecture.md).\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("architecture.md", proc.stderr)

    def test_repo_relative_markdown_link_in_nested_doc_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "decisions").mkdir(parents=True)
            (root / "docs" / "index.md").write_text(
                "See [ADR](docs/decisions/0001-record.md).\n",
                encoding="utf-8",
            )
            (root / "docs" / "decisions" / "0001-record.md").write_text(
                "# ADR\n", encoding="utf-8"
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_project_context_is_part_of_default_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "project-context.md").write_text(
                "Current implementation path: `src/removed.ts`.\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("src/removed.ts", proc.stderr)

    def test_root_architecture_is_part_of_default_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "architecture.md").write_text(
                "Current architecture points at `src/removed.ts`.\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("src/removed.ts", proc.stderr)

    def test_seeded_decision_placeholder_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "architecture.md").write_text(
                "Decision records use `docs/decisions/NNNN-slug.md`.\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_seeded_index_optional_paths_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "index.md").write_text(
                "Tech review: `docs/tech-review.md`\n"
                "Volatile evidence: `.dcness-work/`\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_docs_double_star_markdown_glob_input_scans_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "nested").mkdir(parents=True)
            (root / "docs" / "nested" / "context.md").write_text(
                "Removed source path: `src/removed.ts`.\n",
                encoding="utf-8",
            )

            proc = _run(root, "docs/**/*.md")

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("src/removed.ts", proc.stderr)

    def test_commands_issue_refs_and_external_urls_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text(
                "Use `/init-dcness`, run `gh issue view 815`, keep #815, "
                "and read [GitHub](https://github.com/).\n",
                encoding="utf-8",
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
