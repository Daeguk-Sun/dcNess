from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness.impl_preview import build_preview, validate_design_doc


class ImplPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.impl_dir = self.root / "docs" / "epics" / "epic-01-demo" / "impl"
        self.impl_dir.mkdir(parents=True)
        self.impl_doc = self.impl_dir / "01-task.md"
        self.impl_doc.write_text("# Task\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_design_doc_selects_standard(self) -> None:
        preview = build_preview(design_doc=str(self.impl_doc), cwd=self.root)

        self.assertEqual(preview.route, "standard")
        self.assertEqual(preview.lane, "standard")
        self.assertEqual(
            preview.begin_run_args,
            [
                "begin-run",
                "impl",
                "--design-doc",
                "docs/epics/epic-01-demo/impl/01-task.md",
            ],
        )

    def test_concrete_without_design_doc_selects_lite(self) -> None:
        preview = build_preview(concrete=True, cwd=self.root)

        self.assertEqual(preview.route, "lite")
        self.assertEqual(preview.begin_run_args, ["begin-run", "impl", "--lane", "lite"])

    def test_needs_design_stays_outside_impl(self) -> None:
        preview = build_preview(needs_design=True, concrete=True, cwd=self.root)

        self.assertEqual(preview.route, "outside-design")
        self.assertEqual(preview.begin_run_args, [])
        self.assertIn("/design", preview.next_action)

    def test_natural_language_only_selects_issue_intake(self) -> None:
        preview = build_preview(natural_language_only=True, cwd=self.root)

        self.assertEqual(preview.route, "issue-intake")
        self.assertEqual(preview.begin_run_args, [])
        self.assertIn("/to-issue", preview.next_action)

    def test_no_concrete_signal_defaults_to_issue_intake(self) -> None:
        preview = build_preview(cwd=self.root)

        self.assertEqual(preview.route, "issue-intake")
        self.assertIn("no concrete signal", " ".join(preview.reasons))

    def test_user_skip_design_overrides_missing_design_doc(self) -> None:
        preview = build_preview(needs_design=True, skip_design=True, cwd=self.root)

        self.assertEqual(preview.route, "lite")
        self.assertIn("skip-design", " ".join(preview.reasons))

    def test_high_risk_beats_skip_design_override(self) -> None:
        preview = build_preview(workflow_risk="high", skip_design=True, cwd=self.root)

        self.assertEqual(preview.route, "outside-design")
        self.assertEqual(preview.begin_run_args, [])
        self.assertIn("workflow risk=high", " ".join(preview.reasons))

    def test_impl_always_uses_main_implementation_owner(self) -> None:
        preview = build_preview(concrete=True, cwd=self.root, review_provider="codex")

        self.assertEqual(preview.implementation_owner, "main")
        self.assertEqual(preview.review_provider, "codex")

    def test_validate_design_doc_rejects_removed_surface(self) -> None:
        removed = self.root / "docs" / "compact-plans" / "demo.md"
        removed.parent.mkdir(parents=True)
        removed.write_text("# Removed\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            validate_design_doc(str(removed), cwd=self.root)

    def test_cli_json(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "harness.session_state",
                "impl-preview",
                "--design-doc",
                str(self.impl_doc),
                "--cwd",
                str(self.root),
                "--json",
            ],
            cwd=repo,
            env={**os.environ, "PYTHONPATH": str(repo)},
            text=True,
            capture_output=True,
            check=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["route"], "standard")
        self.assertEqual(payload["implementation_owner"], "main")
        self.assertIn(payload["review_provider"], {"claude", "codex"})


if __name__ == "__main__":
    unittest.main()
