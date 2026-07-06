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
            self.assertIn("`/next-work`", text)
            self.assertIn("GitHub issue open/closed 상태", text)
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

    def test_seed_skips_python_test_command_without_python_markers(self) -> None:
        from harness.context_docs import build_claude_seed

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "tests").mkdir()
            (root / "package.json").write_text(
                '{"scripts": {"test": "vitest"}}', encoding="utf-8"
            )

            seed = build_claude_seed(root)

            self.assertNotIn("unittest", seed)
            self.assertNotIn("python3.11", seed)
            self.assertIn("npm run test", seed)

    def test_seed_uses_python3_for_python_project_tests(self) -> None:
        from harness.context_docs import build_claude_seed

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "tests").mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nname = "demo"\n', encoding="utf-8"
            )

            seed = build_claude_seed(root)

            self.assertIn("- `python3 -m unittest discover -s tests -v`", seed)
            self.assertNotIn("python3.11", seed)

    def test_seed_detects_requirements_only_python_project(self) -> None:
        # requirements.txt 만 있고 pyproject/setup 없는 python 프로젝트도 detect_platform
        # 이 python 으로 인식 — tests/ 존재 시 python 명령을 심어야 한다 (회귀 가드).
        from harness.context_docs import build_claude_seed

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "tests").mkdir()
            (root / "requirements.txt").write_text("pytest\n", encoding="utf-8")

            seed = build_claude_seed(root)

            self.assertIn("- `python3 -m unittest discover -s tests -v`", seed)
            self.assertNotIn("python3.11", seed)

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

    def test_audit_detects_common_monorepo_broken_paths(self) -> None:
        from harness.context_docs import audit_claude_md_file

        with TemporaryDirectory() as td:
            root = Path(td)
            existing = root / "packages" / "core" / "existing.ts"
            existing.parent.mkdir(parents=True)
            existing.write_text("export const ok = true;\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text(
                "\n".join([
                    "# Project Instructions",
                    "",
                    "## Commands",
                    "- `npm run test`",
                    "",
                    "## Architecture",
                    "- packages/core/existing.ts is the module boundary.",
                    "- packages/core/missing.ts is stale.",
                    "",
                    "## Gotchas",
                    "- Keep generated files out of source.",
                    "",
                    COLD_START_TITLE,
                    "- 다음 작업 후보 확인: `/next-work`",
                    "",
                ]),
                encoding="utf-8",
            )

            audit = audit_claude_md_file(root)

            self.assertIn("packages/core/missing.ts", audit.broken_references)
            self.assertNotIn("packages/core/existing.ts", audit.broken_references)

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
