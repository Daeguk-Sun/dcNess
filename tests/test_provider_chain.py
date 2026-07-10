"""Tests for implementation provider chain and Claude headless wrappers."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from harness import ledger
from harness.session_state import start_run, update_current_step


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_VALIDATOR = ROOT / "scripts" / "dcness-claude-validator"
CODEX_VALIDATOR = ROOT / "scripts" / "dcness-codex-validator"
CLAUDE_WORKER = ROOT / "scripts" / "dcness-claude-worker"
CODEX_WORKER = ROOT / "scripts" / "dcness-codex-worker"
CHAIN = ROOT / "scripts" / "dcness-implementation-chain"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    path.chmod(0o755)


def _write_helper(path: Path, helper_args: Path, prose_capture: Path) -> None:
    _write_executable(
        path,
        """\
        #!/bin/sh
        printf '%s\\n' "$*" > "$HELPER_ARGS"
        while [ "$#" -gt 0 ]; do
          case "$1" in
            --prose-file)
              cp "$2" "$PROSE_CAPTURE"
              exit 0
              ;;
          esac
          shift
        done
        exit 1
        """,
    )
    os.environ["HELPER_ARGS"] = str(helper_args)
    os.environ["PROSE_CAPTURE"] = str(prose_capture)


def _write_failing_helper(path: Path) -> None:
    _write_executable(
        path,
        """\
        #!/bin/sh
        printf '%s\\n' "$*" > "$HELPER_ARGS"
        exit 1
        """,
    )


class ClaudeHeadlessWrapperTests(unittest.TestCase):
    def _degraded_base_env(self, bin_dir: Path, helper_args: Path) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("DCNESS_RUN_ID", None)
        env.pop("DCNESS_SESSION_ID", None)
        env.update(
            {
                "HELPER_ARGS": str(helper_args),
                "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
            }
        )
        return env

    def test_worker_context_resolution_ignores_python_stderr_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement with noisy Python stderr.\n", encoding="utf-8")
            env_capture = tmp / "claude-env.txt"
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "python3",
                """\
                #!/bin/sh
                if [ "${1:-}" = "-c" ]; then
                  printf 'RuntimeWarning: noisy Python startup\\n' >&2
                fi
                exec "$REAL_PYTHON" "$@"
                """,
            )
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                cat >/dev/null
                {
                  printf 'DCNESS_SESSION_ID=%s\\n' "${DCNESS_SESSION_ID-}"
                  printf 'DCNESS_RUN_ID=%s\\n' "${DCNESS_RUN_ID-}"
                } > "$ENV_CAPTURE"
                printf 'Claude worker noisy Python prose\\n\\nPASS\\n'
                """,
            )

            sid = "sid-python-warning"
            rid = "run-1a2b3c4d"
            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "ENV_CAPTURE": str(env_capture),
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                    "REAL_PYTHON": sys.executable,
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RuntimeWarning: noisy Python startup", result.stderr)
            self.assertNotIn("sid/rid unresolved", result.stderr)
            captured = env_capture.read_text(encoding="utf-8")
            self.assertIn(f"DCNESS_SESSION_ID={sid}\n", captured)
            self.assertIn(f"DCNESS_RUN_ID={rid}\n", captured)
            logs = list(
                (
                    project
                    / ".claude"
                    / "harness-state"
                    / ".sessions"
                    / sid
                    / "runs"
                    / rid
                    / "headless-logs"
                ).glob("claude-headless-build-worker-*.log")
            )
            self.assertEqual(len(logs), 1)
            self.assertFalse(
                (project / ".dcness-work" / "headless-logs" / "unattributed").exists()
            )

    def test_claude_worker_degraded_context_runs_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement without run context.\n", encoding="utf-8")
            provider_called = tmp / "claude-called.txt"
            env_capture = tmp / "claude-env.txt"
            helper_args = tmp / "helper-args.txt"
            helper = tmp / "dcness-helper"
            _write_failing_helper(helper)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                printf called > "$PROVIDER_CALLED"
                cat >/dev/null
                {
                  printf 'DCNESS_SESSION_ID=%s\\n' "${DCNESS_SESSION_ID-}"
                  printf 'DCNESS_RUN_ID=%s\\n' "${DCNESS_RUN_ID-}"
                } > "$ENV_CAPTURE"
                printf 'Claude worker degraded prose\\n\\nPASS\\n'
                """,
            )

            env = self._degraded_base_env(bin_dir, helper_args)
            env.update(
                {
                    "ENV_CAPTURE": str(env_capture),
                    "PROVIDER_CALLED": str(provider_called),
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(provider_called.exists())
            self.assertIn("sid/rid unresolved", result.stderr)
            self.assertIn("degraded", result.stderr)
            captured = env_capture.read_text(encoding="utf-8")
            self.assertIn("DCNESS_SESSION_ID=\n", captured)
            self.assertIn("DCNESS_RUN_ID=\n", captured)
            self.assertTrue(helper_args.exists())
            logs = list(
                (
                    project / ".dcness-work" / "headless-logs" / "unattributed"
                ).glob("claude-headless-build-worker-*.log")
            )
            self.assertEqual(len(logs), 1)
            raw_log = logs[0].read_text(encoding="utf-8")
            self.assertIn("UNATTRIBUTED", raw_log)
            self.assertIn("Claude worker degraded prose", raw_log)

    def test_codex_worker_degraded_context_runs_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement without run context.\n", encoding="utf-8")
            provider_called = tmp / "codex-called.txt"
            env_capture = tmp / "codex-env.txt"
            helper_args = tmp / "helper-args.txt"
            helper = tmp / "dcness-helper"
            _write_failing_helper(helper)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "codex",
                """\
                #!/bin/sh
                if [ "$1" = "--help" ]; then
                  echo "Usage: codex"
                  exit 0
                fi
                out=""
                while [ "$#" -gt 0 ]; do
                  if [ "$1" = "--output-last-message" ]; then
                    out="$2"
                    shift 2
                    continue
                  fi
                  shift
                done
                printf called > "$PROVIDER_CALLED"
                cat >/dev/null
                {
                  printf 'DCNESS_SESSION_ID=%s\\n' "${DCNESS_SESSION_ID-}"
                  printf 'DCNESS_RUN_ID=%s\\n' "${DCNESS_RUN_ID-}"
                } > "$ENV_CAPTURE"
                printf 'Codex worker degraded prose\\n\\nPASS\\n' > "$out"
                """,
            )

            env = self._degraded_base_env(bin_dir, helper_args)
            env.update(
                {
                    "ENV_CAPTURE": str(env_capture),
                    "PROVIDER_CALLED": str(provider_called),
                }
            )

            result = subprocess.run(
                [
                    str(CODEX_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(provider_called.exists())
            self.assertIn("sid/rid unresolved", result.stderr)
            self.assertIn("degraded", result.stderr)
            captured = env_capture.read_text(encoding="utf-8")
            self.assertIn("DCNESS_SESSION_ID=\n", captured)
            self.assertIn("DCNESS_RUN_ID=\n", captured)
            self.assertTrue(helper_args.exists())
            logs = list(
                (
                    project / ".dcness-work" / "headless-logs" / "unattributed"
                ).glob("codex-headless-build-worker-*.log")
            )
            self.assertEqual(len(logs), 1)
            raw_log = logs[0].read_text(encoding="utf-8")
            self.assertIn("UNATTRIBUTED", raw_log)
            self.assertIn("Codex worker degraded prose", raw_log)

    def test_claude_validator_degraded_context_runs_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Validate without run context.\n", encoding="utf-8")
            provider_called = tmp / "claude-validator-called.txt"
            helper_args = tmp / "helper-args.txt"
            helper = tmp / "dcness-helper"
            _write_failing_helper(helper)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                printf called > "$PROVIDER_CALLED"
                cat >/dev/null
                printf 'Claude validator degraded prose\\n\\nPASS\\n'
                """,
            )

            env = self._degraded_base_env(bin_dir, helper_args)
            env["PROVIDER_CALLED"] = str(provider_called)

            result = subprocess.run(
                [
                    str(CLAUDE_VALIDATOR),
                    "impl-validator",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(provider_called.exists())
            self.assertIn("sid/rid unresolved", result.stderr)
            self.assertTrue(helper_args.exists())
            logs = list(
                (
                    project / ".dcness-work" / "headless-logs" / "unattributed"
                ).glob("claude-headless-impl-validator-*.log")
            )
            self.assertEqual(len(logs), 1)
            raw_log = logs[0].read_text(encoding="utf-8")
            self.assertIn("UNATTRIBUTED", raw_log)
            self.assertIn("Claude validator degraded prose", raw_log)

    def test_codex_validator_degraded_context_runs_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Validate without run context.\n", encoding="utf-8")
            provider_called = tmp / "codex-validator-called.txt"
            helper_args = tmp / "helper-args.txt"
            helper = tmp / "dcness-helper"
            _write_failing_helper(helper)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "codex",
                """\
                #!/bin/sh
                if [ "$1" = "--help" ]; then
                  echo "Usage: codex"
                  exit 0
                fi
                out=""
                while [ "$#" -gt 0 ]; do
                  if [ "$1" = "--output-last-message" ]; then
                    out="$2"
                    shift 2
                    continue
                  fi
                  shift
                done
                printf called > "$PROVIDER_CALLED"
                cat >/dev/null
                printf 'Codex validator degraded prose\\n\\nPASS\\n' > "$out"
                """,
            )

            env = self._degraded_base_env(bin_dir, helper_args)
            env["PROVIDER_CALLED"] = str(provider_called)

            result = subprocess.run(
                [
                    str(CODEX_VALIDATOR),
                    "impl-validator",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(provider_called.exists())
            self.assertIn("sid/rid unresolved", result.stderr)
            self.assertTrue(helper_args.exists())
            logs = list(
                (
                    project / ".dcness-work" / "headless-logs" / "unattributed"
                ).glob("codex-headless-impl-validator-*.log")
            )
            self.assertEqual(len(logs), 1)
            raw_log = logs[0].read_text(encoding="utf-8")
            self.assertIn("UNATTRIBUTED", raw_log)
            self.assertIn("Codex validator degraded prose", raw_log)

    def _assert_worker_records_boundary_block(
        self,
        *,
        wrapper: Path,
        provider: str,
        binary_name: str,
        binary_script: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            sid = "sid-boundary-block"
            rid = "run-0badc0de"
            state_base = project / ".claude" / "harness-state"
            start_run(sid, rid, "impl", base_dir=state_base, lane="lite")
            update_current_step(sid, rid, "build-worker", None, base_dir=state_base)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement this task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(bin_dir / binary_name, binary_script)

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(wrapper),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("changed files outside build-worker boundary", result.stderr)
            self.assertFalse(helper_args.exists())

            events = ledger.read_events(sid, rid, base_dir=state_base)
            blocked_events = [
                event for event in events
                if event.get("event") == "blocked"
                and event.get("category") == "engineer_boundary"
            ]
            self.assertEqual(len(blocked_events), 1)
            self.assertEqual(blocked_events[0].get("agent"), "build-worker")
            self.assertIsNone(blocked_events[0].get("mode"))
            self.assertEqual(blocked_events[0].get("provider"), provider)
            self.assertIn("hooks/catastrophic-gate.sh", blocked_events[0].get("reason", ""))
            self.assertTrue(blocked_events[0].get("raw_log", "").endswith(".log"))

            from harness.session_state import read_live

            live = read_live(sid, base_dir=state_base)
            marker = live["active_runs"][rid].get("blocked")
            self.assertIsInstance(marker, dict)
            self.assertEqual(marker.get("category"), "engineer_boundary")
            self.assertEqual(marker.get("provider"), provider)

    def test_worker_uses_hook_loading_claude_print_mode_and_records_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement this task.\n", encoding="utf-8")
            args_capture = tmp / "claude-args.txt"
            prompt_capture = tmp / "prompt-capture.md"
            prose_capture = tmp / "prose.md"
            helper_args = tmp / "helper-args.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                printf '%s\\n' "$@" > "$ARGS_CAPTURE"
                cat > "$PROMPT_CAPTURE"
                mkdir -p src
                printf 'print("ok")\\n' > src/generated.py
                printf 'Claude worker prose\\n\\nPASS\\n'
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "ARGS_CAPTURE": str(args_capture),
                    "DCNESS_RUN_ID": "run-facefeed",
                    "DCNESS_SESSION_ID": "sid-claude-worker",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROMPT_CAPTURE": str(prompt_capture),
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            args = args_capture.read_text(encoding="utf-8")
            self.assertIn("-p", args)
            self.assertIn("acceptEdits", args)
            self.assertNotIn("--bare", args)
            self.assertNotIn("--safe-mode", args)
            prompt = prompt_capture.read_text(encoding="utf-8")
            self.assertIn("Claude headless", prompt)
            self.assertIn("hooks and plugins enabled", prompt)
            self.assertTrue((project / "src" / "generated.py").exists())
            self.assertTrue(
                helper_args.read_text(encoding="utf-8")
                .strip()
                .startswith("end-step build-worker --provider claude-headless "),
            )
            self.assertEqual(
                prose_capture.read_text(encoding="utf-8"),
                "Claude worker prose\n\nPASS\n",
            )
            logs = list(
                (
                    project
                    / ".claude"
                    / "harness-state"
                    / ".sessions"
                    / "sid-claude-worker"
                    / "runs"
                    / "run-facefeed"
                    / "headless-logs"
                ).glob("claude-headless-build-worker-*.log")
            )
            self.assertEqual(len(logs), 1)
            self.assertIn("Claude worker prose", logs[0].read_text(encoding="utf-8"))

    def test_worker_boundary_checks_committed_diff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=project, check=True)
            (project / "src").mkdir()
            (project / "src" / "base.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "src/base.py"], cwd=project, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=project, check=True)

            sid = "sid-committed-boundary"
            rid = "run-c0ffee00"
            state_base = project / ".claude" / "harness-state"
            start_run(sid, rid, "impl", base_dir=state_base, lane="lite")
            update_current_step(sid, rid, "build-worker", None, base_dir=state_base)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement and commit this task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                cat >/dev/null
                mkdir -p hooks
                printf 'outside boundary\\n' > hooks/catastrophic-gate.sh
                git add hooks/catastrophic-gate.sh
                git commit -q -m "[feature] committed boundary escape"
                printf 'Committed worker prose\\n\\nPASS\\n'
                """,
            )

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("hooks/catastrophic-gate.sh", result.stderr)
            self.assertFalse(helper_args.exists())

    def test_worker_cleans_nested_claude_session_env_but_keeps_dcness_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement this task.\n", encoding="utf-8")
            env_capture = tmp / "claude-env.txt"
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                cat >/dev/null
                {
                  printf 'CLAUDE_CODE_SESSION_ID=%s\\n' "${CLAUDE_CODE_SESSION_ID-}"
                  printf 'CLAUDE_CODE_ENTRYPOINT=%s\\n' "${CLAUDE_CODE_ENTRYPOINT-}"
                  printf 'CLAUDECODE=%s\\n' "${CLAUDECODE-}"
                  printf 'CLAUDE_PLUGIN_ROOT=%s\\n' "${CLAUDE_PLUGIN_ROOT-}"
                  printf 'DCNESS_SESSION_ID=%s\\n' "${DCNESS_SESSION_ID-}"
                  printf 'DCNESS_RUN_ID=%s\\n' "${DCNESS_RUN_ID-}"
                } > "$ENV_CAPTURE"
                printf 'Claude worker prose\\n\\nPASS\\n'
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CLAUDE_CODE_ENTRYPOINT": "parent-cli",
                    "CLAUDE_CODE_SESSION_ID": "parent-session",
                    "CLAUDE_PLUGIN_ROOT": "/tmp/plugin-root",
                    "CLAUDECODE": "1",
                    "DCNESS_RUN_ID": "run-0badcafe",
                    "DCNESS_SESSION_ID": "sid-claude-worker",
                    "ENV_CAPTURE": str(env_capture),
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            captured = env_capture.read_text(encoding="utf-8")
            self.assertIn("CLAUDE_CODE_SESSION_ID=\n", captured)
            self.assertIn("CLAUDE_CODE_ENTRYPOINT=\n", captured)
            self.assertIn("CLAUDECODE=\n", captured)
            self.assertIn("CLAUDE_PLUGIN_ROOT=/tmp/plugin-root\n", captured)
            self.assertIn("DCNESS_SESSION_ID=sid-claude-worker\n", captured)
            self.assertIn("DCNESS_RUN_ID=run-0badcafe\n", captured)

    def test_validator_cleans_nested_claude_session_env_but_keeps_dcness_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review this task.\n", encoding="utf-8")
            env_capture = tmp / "claude-env.txt"
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                cat >/dev/null
                {
                  printf 'CLAUDE_CODE_SESSION_ID=%s\\n' "${CLAUDE_CODE_SESSION_ID-}"
                  printf 'CLAUDE_CODE_ENTRYPOINT=%s\\n' "${CLAUDE_CODE_ENTRYPOINT-}"
                  printf 'CLAUDECODE=%s\\n' "${CLAUDECODE-}"
                  printf 'DCNESS_SESSION_ID=%s\\n' "${DCNESS_SESSION_ID-}"
                  printf 'DCNESS_RUN_ID=%s\\n' "${DCNESS_RUN_ID-}"
                } > "$ENV_CAPTURE"
                printf 'Claude validator prose\\n\\nPASS\\n'
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CLAUDE_CODE_ENTRYPOINT": "parent-cli",
                    "CLAUDE_CODE_SESSION_ID": "parent-session",
                    "CLAUDECODE": "1",
                    "DCNESS_RUN_ID": "run-f00dcafe",
                    "DCNESS_SESSION_ID": "sid-claude-validator",
                    "ENV_CAPTURE": str(env_capture),
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_VALIDATOR),
                    "impl-validator",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            captured = env_capture.read_text(encoding="utf-8")
            self.assertIn("CLAUDE_CODE_SESSION_ID=\n", captured)
            self.assertIn("CLAUDE_CODE_ENTRYPOINT=\n", captured)
            self.assertIn("CLAUDECODE=\n", captured)
            self.assertIn("DCNESS_SESSION_ID=sid-claude-validator\n", captured)
            self.assertIn("DCNESS_RUN_ID=run-f00dcafe\n", captured)

    def test_worker_records_headless_validation_blocked_in_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            sid = "sid-validation-blocked"
            rid = "run-00c0ffee"
            state_base = project / ".claude" / "harness-state"
            start_run(sid, rid, "impl", base_dir=state_base, lane="lite")
            update_current_step(sid, rid, "build-worker", None, base_dir=state_base)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement and validate this task.\n", encoding="utf-8")

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                cat >/dev/null
                printf '검증 명령을 권한 때문에 실행하지 못했습니다.\\n\\nVALIDATION_BLOCKED\\n'
                """,
            )

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(ROOT / "scripts" / "dcness-helper"),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            events = ledger.read_events(sid, rid, base_dir=state_base)
            blocked_events = [
                event for event in events
                if event.get("event") == "blocked"
                and event.get("category") == "headless_validation_blocked"
            ]
            self.assertEqual(len(blocked_events), 1)
            self.assertEqual(blocked_events[0].get("agent"), "build-worker")
            self.assertEqual(blocked_events[0].get("provider"), "claude-headless")
            self.assertIn("build-worker.md", blocked_events[0].get("prose_file", ""))

    def test_codex_worker_records_boundary_block_in_ledger_and_live_marker(self) -> None:
        self._assert_worker_records_boundary_block(
            wrapper=CODEX_WORKER,
            provider="codex-headless",
            binary_name="codex",
            binary_script="""\
            #!/bin/sh
            if [ "$1" = "--help" ]; then
              echo "Usage: codex"
              exit 0
            fi
            out=""
            while [ "$#" -gt 0 ]; do
              if [ "$1" = "--output-last-message" ]; then
                out="$2"
                shift 2
                continue
              fi
              shift
            done
            cat >/dev/null
            mkdir -p hooks src
            printf 'outside boundary\\n' > hooks/catastrophic-gate.sh
            printf 'inside boundary\\n' > src/generated.py
            printf 'Codex worker prose\\n\\nPASS\\n' > "$out"
            """,
        )

    def test_codex_worker_idle_timeout_kills_zero_progress_hang(self) -> None:
        """#1019 — zero-output Codex hangs are killed before the full timeout."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            sid = "sid-codex-idle"
            rid = "run-00badbad"
            state_base = project / ".claude" / "harness-state"
            start_run(sid, rid, "impl", base_dir=state_base, lane="lite")
            update_current_step(sid, rid, "build-worker", None, base_dir=state_base)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement this task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "codex",
                """\
                #!/bin/sh
                if [ "$1" = "--help" ]; then
                  echo "Usage: codex"
                  exit 0
                fi
                cat >/dev/null
                sleep 5
                """,
            )

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_CODEX_IDLE_TIMEOUT": "1",
                    "DCNESS_CODEX_TIMEOUT": "10",
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CODEX_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 124)
            self.assertIn("failed before workspace mutation (exit 124)", result.stderr)
            self.assertFalse(helper_args.exists())
            logs = list(
                (
                    project
                    / ".claude"
                    / "harness-state"
                    / ".sessions"
                    / sid
                    / "runs"
                    / rid
                    / "headless-logs"
                ).glob("codex-headless-build-worker-*.log")
            )
            self.assertEqual(len(logs), 1)
            self.assertIn("idle timeout after 1s", logs[0].read_text(encoding="utf-8"))

    def test_claude_worker_idle_timeout_kills_zero_progress_hang(self) -> None:
        """#1028 — zero-output Claude headless hangs are killed before the full timeout."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            sid = "sid-claude-idle"
            rid = "run-00badbad"
            state_base = project / ".claude" / "harness-state"
            start_run(sid, rid, "impl", base_dir=state_base, lane="lite")
            update_current_step(sid, rid, "build-worker", None, base_dir=state_base)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement this task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                if [ "$1" = "--help" ]; then
                  echo "Usage: claude"
                  exit 0
                fi
                cat >/dev/null
                sleep 5
                """,
            )

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_CLAUDE_IDLE_TIMEOUT": "1",
                    "DCNESS_CLAUDE_TIMEOUT": "10",
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_WORKER),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 124)
            self.assertIn("failed before workspace mutation (exit 124)", result.stderr)
            self.assertFalse(helper_args.exists())
            logs = list(
                (
                    project
                    / ".claude"
                    / "harness-state"
                    / ".sessions"
                    / sid
                    / "runs"
                    / rid
                    / "headless-logs"
                ).glob("claude-headless-build-worker-*.log")
            )
            self.assertEqual(len(logs), 1)
            self.assertIn("idle timeout after 1s", logs[0].read_text(encoding="utf-8"))

    def test_claude_worker_records_boundary_block_in_ledger_and_live_marker(self) -> None:
        self._assert_worker_records_boundary_block(
            wrapper=CLAUDE_WORKER,
            provider="claude-headless",
            binary_name="claude",
            binary_script="""\
            #!/bin/sh
            cat >/dev/null
            mkdir -p hooks src
            printf 'outside boundary\\n' > hooks/catastrophic-gate.sh
            printf 'inside boundary\\n' > src/generated.py
            printf 'Claude worker prose\\n\\nPASS\\n'
            """,
        )

    def test_validator_blocks_workspace_mutation_without_end_step(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review only.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                cat >/dev/null
                mkdir -p src
                printf 'bad\\n' > src/mutated.py
                printf 'Claude validator prose\\n\\nPASS\\n'
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": "run-abcddcba",
                    "DCNESS_SESSION_ID": "sid-claude-validator",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CLAUDE_VALIDATOR),
                    "impl-validator",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("changed git status", result.stderr)
            self.assertFalse(helper_args.exists())


class ImplementationChainTests(unittest.TestCase):
    def test_chain_degraded_context_runs_headless_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain without run context.\n", encoding="utf-8")
            provider_called = tmp / "claude-called.txt"
            helper_args = tmp / "helper-args.txt"
            helper = tmp / "dcness-helper"
            _write_failing_helper(helper)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                printf called > "$PROVIDER_CALLED"
                cat >/dev/null
                printf 'Claude chain degraded prose\\n\\nPASS\\n'
                """,
            )

            env = os.environ.copy()
            env.pop("DCNESS_RUN_ID", None)
            env.pop("DCNESS_SESSION_ID", None)
            env.update(
                {
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROVIDER_CALLED": str(provider_called),
                }
            )

            result = subprocess.run(
                [
                    str(CHAIN),
                    "build-worker",
                    "--provider",
                    "claude-headless",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(provider_called.exists())
            self.assertIn("sid/rid unresolved", result.stderr)
            self.assertTrue(helper_args.exists())
            log_dir = project / ".dcness-work" / "headless-logs" / "unattributed"
            self.assertTrue(list(log_dir.glob("chain-claude-headless-build-worker-*.log")))
            worker_logs = list(log_dir.glob("claude-headless-build-worker-*.log"))
            self.assertEqual(len(worker_logs), 1)
            raw_log = worker_logs[0].read_text(encoding="utf-8")
            self.assertIn("UNATTRIBUTED", raw_log)
            self.assertIn("Claude chain degraded prose", raw_log)

    def test_codex_missing_falls_back_to_claude_headless(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            claude_called = tmp / "claude-called.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                printf called > "$CLAUDE_CALLED"
                cat >/dev/null
                mkdir -p src
                printf 'ok\\n' > src/generated.py
                printf 'Claude fallback prose\\n\\nPASS\\n'
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CLAUDE_CALLED": str(claude_called),
                    "DCNESS_RUN_ID": "run-12344321",
                    "DCNESS_SESSION_ID": "sid-chain",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CHAIN),
                    "build-worker",
                    "--provider",
                    "headless-chain",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(claude_called.exists())
            self.assertIn("provider codex-headless failed before workspace mutation", result.stderr)
            self.assertEqual(
                prose_capture.read_text(encoding="utf-8"),
                "Claude fallback prose\n\nPASS\n",
            )
            log_dir = (
                project
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-chain"
                / "runs"
                / "run-12344321"
                / "headless-logs"
            )
            self.assertTrue(list(log_dir.glob("chain-codex-headless-build-worker-*.log")))
            self.assertTrue(list(log_dir.glob("claude-headless-build-worker-*.log")))

    def test_codex_failure_after_mutation_stops_chain(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            claude_called = tmp / "claude-called.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "codex",
                """\
                #!/bin/sh
                if [ "$1" = "--help" ]; then
                  echo "Usage: codex"
                  exit 0
                fi
                cat >/dev/null
                mkdir -p src
                printf 'partial\\n' > src/partial.py
                exit 42
                """,
            )
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                printf called > "$CLAUDE_CALLED"
                cat >/dev/null
                printf 'should not run\\n'
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CLAUDE_CALLED": str(claude_called),
                    "DCNESS_RUN_ID": "run-42424242",
                    "DCNESS_SESSION_ID": "sid-chain",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(CHAIN),
                    "build-worker",
                    "--provider",
                    "headless-chain",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("changed workspace", result.stderr)
            self.assertFalse(claude_called.exists())
            self.assertFalse(helper_args.exists())

    def test_claude_headless_pre_mutation_failure_hands_off_to_main_agent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
            helper = tmp / "dcness-helper"
            _write_executable(helper, "#!/bin/sh\nexit 0\n")

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                cat >/dev/null
                exit 43
                """,
            )

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": "run-56565656",
                    "DCNESS_SESSION_ID": "sid-chain",
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                }
            )

            result = subprocess.run(
                [
                    str(CHAIN),
                    "build-worker",
                    "--provider",
                    "claude-headless",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 75)
            self.assertIn("FALLBACK_TO_CLAUDE_MAIN", result.stderr)


if __name__ == "__main__":
    unittest.main()
