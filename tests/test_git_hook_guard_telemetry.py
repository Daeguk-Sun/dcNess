"""git hook guard telemetry contracts (#875)."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness.guard_telemetry import read_events
from harness.guard_telemetry import TELEMETRY_NAME
from harness.session_state import generate_run_id, run_dir


ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def _env(*, active: bool = False, whitelist_path: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
    if whitelist_path is not None:
        env["DCNESS_WHITELIST_PATH"] = str(whitelist_path)
    if active:
        env["DCNESS_FORCE_ENABLE"] = "1"
    else:
        env.pop("DCNESS_FORCE_ENABLE", None)
    return env


class GitHookGuardTelemetryTests(unittest.TestCase):
    def test_pre_commit_main_block_records_guard_hit(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            _git(root, "init")
            _git(root, "checkout", "-b", "main")

            result = subprocess.run(
                ["sh", str(ROOT / "scripts" / "hooks" / "pre-commit")],
                cwd=str(root),
                env=_env(active=True),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            events = read_events(cwd=root)
            self.assertTrue(
                any(
                    e.get("kind") == "guard_hit"
                    and e.get("guard") == "git-pre-commit"
                    and e.get("category") == "main_block"
                    for e in events
                ),
                events,
            )

    def test_commit_msg_naming_block_records_guard_hit(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            _git(root, "init")
            msg = root / "COMMIT_EDITMSG"
            msg.write_text("bad subject\n", encoding="utf-8")

            result = subprocess.run(
                ["sh", str(ROOT / "scripts" / "hooks" / "commit-msg"), str(msg)],
                cwd=str(root),
                env=_env(active=True),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            events = read_events(cwd=root)
            self.assertTrue(
                any(
                    e.get("kind") == "guard_hit"
                    and e.get("guard") == "git-commit-msg"
                    and e.get("category") == "git_naming"
                    for e in events
                ),
                events,
            )

    def test_inactive_commit_msg_block_does_not_create_telemetry(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            root = base / "repo"
            root.mkdir()
            _git(root, "init")
            msg = root / "COMMIT_EDITMSG"
            msg.write_text("bad subject\n", encoding="utf-8")

            result = subprocess.run(
                ["sh", str(ROOT / "scripts" / "hooks" / "commit-msg"), str(msg)],
                cwd=str(root),
                env=_env(whitelist_path=base / "projects.json"),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertFalse(
                (root / ".claude" / "harness-state" / TELEMETRY_NAME).exists()
            )
            self.assertEqual(read_events(cwd=root), [])

    def test_self_repo_commit_msg_block_records_without_whitelist(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            root = base / "dcness"
            root.mkdir()
            _git(root, "init")
            manifest = root / ".claude-plugin" / "plugin.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"name": "dcness"}), encoding="utf-8")
            msg = root / "COMMIT_EDITMSG"
            msg.write_text("bad subject\n", encoding="utf-8")

            result = subprocess.run(
                ["sh", str(ROOT / "scripts" / "hooks" / "commit-msg"), str(msg)],
                cwd=str(root),
                env=_env(whitelist_path=base / "projects.json"),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            events = read_events(cwd=root)
            self.assertTrue(
                any(
                    e.get("kind") == "guard_hit"
                    and e.get("guard") == "git-commit-msg"
                    and e.get("category") == "git_naming"
                    for e in events
                ),
                events,
            )

    def test_pre_push_main_block_records_guard_hit_when_active(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            _git(root, "init")

            result = subprocess.run(
                ["sh", str(ROOT / "scripts" / "hooks" / "pre-push")],
                input="refs/heads/main abc refs/heads/main def\n",
                cwd=str(root),
                env=_env(active=True),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            events = read_events(cwd=root)
            self.assertTrue(
                any(
                    e.get("kind") == "guard_hit"
                    and e.get("guard") == "git-pre-push"
                    and e.get("category") == "main_push_block"
                    for e in events
                ),
                events,
            )

    def test_pre_push_branch_naming_records_run_context_when_available(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            _git(root, "init")
            run_id = generate_run_id()
            env = _env(active=True)
            env["DCNESS_SESSION_ID"] = "git-hook-telemetry-sid"
            env["DCNESS_RUN_ID"] = run_id

            result = subprocess.run(
                ["sh", str(ROOT / "scripts" / "hooks" / "pre-push")],
                input="refs/heads/BadBranch abc refs/heads/BadBranch def\n",
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            events = read_events(cwd=root)
            self.assertTrue(
                any(
                    e.get("kind") == "guard_hit"
                    and e.get("guard") == "git-pre-push"
                    and e.get("category") == "branch_naming"
                    and e.get("session_id") == "git-hook-telemetry-sid"
                    and e.get("run_id") == run_id
                    for e in events
                ),
                events,
            )
            self.assertTrue(
                (
                    run_dir("git-hook-telemetry-sid", run_id, base_dir=root / ".claude" / "harness-state")
                    / TELEMETRY_NAME
                ).is_file()
            )

    def test_inactive_pre_push_block_does_not_create_telemetry(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            root = base / "repo"
            root.mkdir()
            _git(root, "init")

            result = subprocess.run(
                ["sh", str(ROOT / "scripts" / "hooks" / "pre-push")],
                input="refs/heads/main abc refs/heads/main def\n",
                cwd=str(root),
                env=_env(whitelist_path=base / "projects.json"),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertFalse(
                (root / ".claude" / "harness-state" / TELEMETRY_NAME).exists()
            )
            self.assertEqual(read_events(cwd=root), [])


if __name__ == "__main__":
    unittest.main()
