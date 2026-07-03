"""CLAUDE.md seed/migration helper tests."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dcness-context-docs"
COLD_START_TITLE = "## dcNess Cold Start"


class ContextDocsTests(unittest.TestCase):
    def test_missing_claude_md_is_seeded_with_official_structure(self) -> None:
        from harness.context_docs import ensure_claude_context

        with TemporaryDirectory() as td:
            root = Path(td)

            result = ensure_claude_context(root)

            claude = root / "CLAUDE.md"
            self.assertTrue(claude.exists())
            text = claude.read_text(encoding="utf-8")
            self.assertIn("## Commands", text)
            self.assertIn("## Architecture", text)
            self.assertIn("## Key Files", text)
            self.assertIn("## Code Style", text)
            self.assertIn("## Environment", text)
            self.assertIn("## Testing", text)
            self.assertIn("## Gotchas", text)
            self.assertIn("## Workflow", text)
            self.assertIn(COLD_START_TITLE, text)
            self.assertIn("`/next`", text)
            self.assertIn("gh variable get DCNESS_PROJECT_NUMBER", text)
            self.assertLess(len(text.splitlines()), 200)
            self.assertNotRegex(text, r"TODO|TBD|<TODO>|<TBD>")
            self.assertIn("created", result.actions)
            self.assertGreaterEqual(result.audit.total_score, 90)

    def test_existing_claude_md_gets_additive_idempotent_cold_start_anchor(self) -> None:
        from harness.context_docs import ensure_claude_context

        with TemporaryDirectory() as td:
            root = Path(td)
            claude = root / "CLAUDE.md"
            original = "# Existing Rules\n\n- Keep this exact content.\n"
            claude.write_text(original, encoding="utf-8")

            first = ensure_claude_context(root)
            second = ensure_claude_context(root)

            text = claude.read_text(encoding="utf-8")
            self.assertTrue(text.startswith(original))
            self.assertEqual(text.count(COLD_START_TITLE), 1)
            self.assertIn("appended-cold-start", first.actions)
            self.assertEqual(second.actions, ["noop"])

    def test_audit_reports_rubric_gaps_without_mutating_existing_doc(self) -> None:
        from harness.context_docs import audit_claude_md_file

        with TemporaryDirectory() as td:
            root = Path(td)
            claude = root / "CLAUDE.md"
            original = "# Project Notes\n\nGeneral prose only.\n"
            claude.write_text(original, encoding="utf-8")

            audit = audit_claude_md_file(root)

            self.assertLess(audit.total_score, 100)
            self.assertIn("Commands", audit.missing_sections)
            self.assertFalse(audit.has_cold_start_anchor)
            self.assertEqual(claude.read_text(encoding="utf-8"), original)

    def test_cli_ensure_prints_quality_report(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            proc = subprocess.run(
                [str(SCRIPT), "--ensure", "--repo", str(root)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("## CLAUDE.md seed/migration", proc.stdout)
            self.assertIn("score", proc.stdout)
            self.assertTrue((root / "CLAUDE.md").exists())


if __name__ == "__main__":
    sys.exit(unittest.main())
