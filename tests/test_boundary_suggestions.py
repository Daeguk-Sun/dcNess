"""Boundary override suggestion tests for issue #910."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness.boundary_suggestions import (  # noqa: E402
    collect_boundary_suggestions,
    format_boundary_suggestions,
)


class BoundarySuggestionsTests(unittest.TestCase):
    @staticmethod
    def _write(path: Path, text: str = "") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    @staticmethod
    def _write_boundary(root: Path, mapping: dict) -> None:
        cfg = root / ".dcness" / "boundary.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps(mapping), encoding="utf-8")

    def test_empty_project_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            report = collect_boundary_suggestions(Path(td))
            self.assertEqual([], report.suggestions)
            self.assertEqual("empty", report.reason)

    def test_standard_layout_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root / "src" / "app.ts", "export const x = 1\n")
            self._write(root / "lib" / "core.py", "x = 1\n")
            self._write(root / "apps" / "web" / "src" / "App.tsx", "export {}\n")

            report = collect_boundary_suggestions(root)

            self.assertEqual([], report.suggestions)
            self.assertEqual("covered", report.reason)

    def test_nonstandard_source_directory_suggests_build_worker_add(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root / "remotion" / "shorts-types.ts", "export {}\n")
            self._write(root / "remotion" / "scene.tsx", "export {}\n")

            report = collect_boundary_suggestions(root)

            self.assertEqual(1, len(report.suggestions))
            suggestion = report.suggestions[0]
            self.assertEqual("remotion/", suggestion.directory)
            self.assertEqual(r"^remotion/", suggestion.pattern)
            self.assertEqual(2, suggestion.file_count)
            self.assertEqual(
                ["remotion/scene.tsx", "remotion/shorts-types.ts"],
                suggestion.examples,
            )

            formatted = format_boundary_suggestions(report)
            self.assertIn(".dcness/boundary.json", formatted)
            self.assertIn("사람 승인", formatted)
            self.assertIn('"build-worker"', formatted)
            self.assertIn(r'"^remotion/"', formatted)
            self.assertFalse((root / ".dcness" / "boundary.json").exists())

    def test_nonstandard_frontend_extension_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root / "components" / "Button.vue", "<template />\n")

            report = collect_boundary_suggestions(root)

            self.assertEqual(1, len(report.suggestions))
            self.assertEqual("components/", report.suggestions[0].directory)
            self.assertEqual(r"^components/", report.suggestions[0].pattern)

    def test_partial_standard_top_level_keeps_suggestions_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root / "apps" / "web" / "components" / "Button.tsx", "export {}\n")
            self._write(root / "apps" / "api" / "server" / "main.go", "package main\n")

            report = collect_boundary_suggestions(root)

            self.assertEqual(
                [r"^apps/api/server/", r"^apps/web/components/"],
                [item.pattern for item in report.suggestions],
            )
            self.assertNotIn(r"^apps/", [item.pattern for item in report.suggestions])

    def test_existing_boundary_override_suppresses_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root / "remotion" / "scene.tsx", "export {}\n")
            self._write_boundary(root, {"build-worker": {"add": [r"^remotion/"]}})

            report = collect_boundary_suggestions(root)

            self.assertEqual([], report.suggestions)
            self.assertEqual("covered", report.reason)

    def test_ignores_tests_docs_dependencies_and_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in (
                "tests/test_app.py",
                "docs/snippet.ts",
                "node_modules/pkg/src/index.ts",
                "dist/generated.js",
                ".venv/lib/python/site-packages/pkg.py",
            ):
                self._write(root / rel, "x = 1\n")

            report = collect_boundary_suggestions(root)

            self.assertEqual([], report.suggestions)
            self.assertEqual("empty", report.reason)

    def test_helper_cli_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root / "remotion" / "scene.tsx", "export {}\n")

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "harness.session_state",
                    "boundary-suggestions",
                    "--cwd",
                    str(root),
                    "--json",
                ],
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            payload = json.loads(proc.stdout)

            self.assertEqual("uncovered", payload["reason"])
            self.assertEqual(r"^remotion/", payload["suggestions"][0]["pattern"])

if __name__ == "__main__":
    unittest.main()
