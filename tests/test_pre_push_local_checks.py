"""pre-push hook 의 로컬 lint-build-test 실행 계약.

비공개 저장소에서 `/init-dcness` 가 workflow 대신 `.dcness/lint-build-test.sh` 를
설치하면, pre-push hook 이 push 직전에 그 스크립트를 실행하고 실패 시 push 를 막는다.
"""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness.ci_workflows import LOCAL_SCRIPT
from harness.guard_telemetry import read_events

ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = ROOT / "scripts" / "hooks" / "pre-push"
ZERO = "0" * 40
UPDATE = "refs/heads/feature/local_checks abc refs/heads/feature/local_checks def\n"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
    env["DCNESS_FORCE_ENABLE"] = "1"
    return env


class PrePushLocalChecksTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _script(self, body: str) -> Path:
        path = self.root / LOCAL_SCRIPT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def _push(self, refs: str = UPDATE) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(PRE_PUSH), "origin", "git@github.com:example/private.git"],
            input=refs,
            cwd=str(self.root),
            env=_env(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_runs_local_script_and_allows_push_on_success(self) -> None:
        self._script('touch "$(git rev-parse --show-toplevel)/ran"\n')

        result = self._push()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "ran").exists())

    def test_blocks_push_and_records_hit_when_script_fails(self) -> None:
        self._script("exit 3\n")

        result = self._push()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("lint-build-test", result.stderr)
        events = read_events(cwd=self.root)
        self.assertTrue(
            any(
                e.get("guard") == "git-pre-push" and e.get("category") == "local_lint_build_test"
                for e in events
            ),
            events,
        )

    def test_script_does_not_consume_push_refs_stdin(self) -> None:
        self._script('cat > "$(git rev-parse --show-toplevel)/stdin"\n')

        result = self._push()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "stdin").read_text(encoding="utf-8"), "")

    def test_branch_delete_push_skips_script(self) -> None:
        self._script("exit 3\n")

        result = self._push(f"(delete) {ZERO} refs/heads/feature/old def\n")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_script_means_no_local_check(self) -> None:
        result = self._push()

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
