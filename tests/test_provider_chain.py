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
from harness.prev_tasks import append as append_previous_task
from harness.session_state import transition


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
            self.assertRegex(
                raw_log,
                r"PROCESS_FORK: pid=[1-9][0-9]* started_at=.+\+00:00",
            )
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
            prompt_capture = tmp / "codex-prompt.md"
            helper_args = tmp / "helper-args.txt"
            helper = tmp / "dcness-helper"
            _write_failing_helper(helper)
            append_previous_task("01-foundation", "foundation ready", cwd=project)
            subprocess.run(["git", "add", ".claude/loop-insights/.prev-tasks.md"], cwd=project, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=dcNess Test", "-c",
                    "user.email=dcness-test@example.invalid", "commit", "-qm", "fixture",
                ],
                cwd=project,
                check=True,
            )

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
                cat > "$PROMPT_CAPTURE"
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
                    "PROMPT_CAPTURE": str(prompt_capture),
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
            prompt = prompt_capture.read_text(encoding="utf-8")
            self.assertIn(f"project/worktree root: {project}", prompt)
            self.assertIn("[PREVIOUS_TASKS]\n- 01-foundation: foundation ready", prompt)
            self.assertTrue(helper_args.exists())
            logs = list(
                (
                    project / ".dcness-work" / "headless-logs" / "unattributed"
                ).glob("codex-headless-build-worker-*.log")
            )
            self.assertEqual(len(logs), 1)
            raw_log = logs[0].read_text(encoding="utf-8")
            self.assertIn("UNATTRIBUTED", raw_log)
            self.assertRegex(
                raw_log,
                r"PROCESS_FORK: pid=[1-9][0-9]* started_at=.+\+00:00",
            )
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
            transition(sid, "run_started", run_id=rid, base_dir=state_base, entry_point="impl", lane="lite")
            transition(sid, "step_started", run_id=rid, base_dir=state_base, agent="build-worker", mode=None)

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
                and event.get("category") == "worker_boundary"
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
            self.assertEqual(marker.get("category"), "worker_boundary")
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
            append_previous_task("01-foundation", "foundation ready", cwd=project)
            subprocess.run(["git", "add", ".claude/loop-insights/.prev-tasks.md"], cwd=project, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=dcNess Test", "-c",
                    "user.email=dcness-test@example.invalid", "commit", "-qm", "fixture",
                ],
                cwd=project,
                check=True,
            )

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
            self.assertIn(f"project/worktree root: {project}", prompt)
            self.assertIn("[PREVIOUS_TASKS]\n- 01-foundation: foundation ready", prompt)
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
            transition(sid, "run_started", run_id=rid, base_dir=state_base, entry_point="impl", lane="lite")
            transition(sid, "step_started", run_id=rid, base_dir=state_base, agent="build-worker", mode=None)

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
            transition(sid, "run_started", run_id=rid, base_dir=state_base, entry_point="impl", lane="lite")
            transition(sid, "step_started", run_id=rid, base_dir=state_base, agent="build-worker", mode=None)

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
            transition(sid, "run_started", run_id=rid, base_dir=state_base, entry_point="impl", lane="lite")
            transition(sid, "step_started", run_id=rid, base_dir=state_base, agent="build-worker", mode=None)

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
            transition(sid, "run_started", run_id=rid, base_dir=state_base, entry_point="impl", lane="lite")
            transition(sid, "step_started", run_id=rid, base_dir=state_base, agent="build-worker", mode=None)

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

            for version in (1, 2):
                with self.subTest(unsupported_routing_version=version):
                    routing = tmp / f"routing-v{version}.json"
                    routing.write_text(
                        '{"version": %d, "routes": {}, "implementation_routes": {}}\n'
                        % version,
                        encoding="utf-8",
                    )
                    rejected = subprocess.run(
                        [
                            str(CHAIN),
                            "build-worker",
                            "--prompt-file",
                            str(prompt_file),
                            "--project-root",
                            str(project),
                            "--helper",
                            str(helper),
                        ],
                        capture_output=True,
                        env={**env, "DCNESS_ROUTING_PATH": str(routing)},
                        text=True,
                    )

                    self.assertEqual(rejected.returncode, 2)
                    self.assertIn(
                        "[dcness-implementation-chain] routing config rejected",
                        rejected.stderr,
                    )
                    self.assertIn(f"routing-v{version}.json", rejected.stderr)
                    self.assertIn("rerun /init-dcness", rejected.stderr)
                    self.assertNotIn("Traceback", rejected.stderr)

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

    def test_timeout_after_mutation_continues_same_provider_and_preserves_diff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            call_count = tmp / "codex-count.txt"
            retry_prompt = tmp / "retry-prompt.md"

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
                prompt="$(cat)"
                count="$(cat "$CALL_COUNT" 2>/dev/null || printf 0)"
                count=$((count + 1))
                printf '%s' "$count" > "$CALL_COUNT"
                mkdir -p src
                if [ "$count" -eq 1 ]; then
                  printf 'partial\\n' > src/partial.py
                  exit 124
                fi
                printf '%s' "$prompt" > "$RETRY_PROMPT"
                printf 'finished\\n' >> src/partial.py
                printf 'Recovered worker prose\\n\\nPASS\\n' > "$out"
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CALL_COUNT": str(call_count),
                    "DCNESS_IMPLEMENTATION_RECOVERY_LIMIT": "1",
                    "DCNESS_RUN_ID": "run-90909090",
                    "DCNESS_SESSION_ID": "sid-chain",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                    "PROSE_CAPTURE": str(prose_capture),
                    "RETRY_PROMPT": str(retry_prompt),
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
            self.assertEqual(call_count.read_text(encoding="utf-8"), "2")
            self.assertEqual(
                (project / "src" / "partial.py").read_text(encoding="utf-8"),
                "partial\nfinished\n",
            )
            self.assertIn("AUTOMATIC RECOVERY", retry_prompt.read_text(encoding="utf-8"))
            self.assertIn("RECOVERY", result.stderr)

    def test_empty_prose_after_mutation_continues_same_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            call_count = tmp / "codex-count.txt"

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
                cat >/dev/null
                count="$(cat "$CALL_COUNT" 2>/dev/null || printf 0)"
                count=$((count + 1))
                printf '%s' "$count" > "$CALL_COUNT"
                mkdir -p src
                if [ "$count" -eq 1 ]; then
                  printf 'partial\\n' > src/empty-recovery.py
                  : > "$out"
                  exit 0
                fi
                printf 'finished\\n' >> src/empty-recovery.py
                printf 'Recovered worker prose\\n\\nPASS\\n' > "$out"
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CALL_COUNT": str(call_count),
                    "DCNESS_IMPLEMENTATION_RECOVERY_LIMIT": "1",
                    "DCNESS_RUN_ID": "run-92929292",
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
            self.assertEqual(call_count.read_text(encoding="utf-8"), "2")
            self.assertEqual(
                (project / "src" / "empty-recovery.py").read_text(encoding="utf-8"),
                "partial\nfinished\n",
            )
            self.assertIn("category=empty_output", result.stderr)

    def test_boundary_recovery_exhaustion_blocks_run_durably(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            sid = "sid-chain-exhausted"
            rid = "run-baddc0de"
            state_base = project / ".claude" / "harness-state"
            transition(
                sid,
                "run_started",
                run_id=rid,
                base_dir=state_base,
                entry_point="impl",
                lane="lite",
            )
            transition(
                sid,
                "step_started",
                run_id=rid,
                base_dir=state_base,
                agent="build-worker",
                mode=None,
            )

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            call_count = tmp / "codex-count.txt"

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
                cat >/dev/null
                count="$(cat "$CALL_COUNT" 2>/dev/null || printf 0)"
                count=$((count + 1))
                printf '%s' "$count" > "$CALL_COUNT"
                mkdir -p hooks src
                printf 'attempt %s\\n' "$count" > hooks/catastrophic-gate.sh
                printf 'partial %s\\n' "$count" > src/generated.py
                printf 'Worker prose\\n\\nPASS\\n' > "$out"
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CALL_COUNT": str(call_count),
                    "DCNESS_IMPLEMENTATION_RECOVERY_LIMIT": "1",
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
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
            self.assertEqual(call_count.read_text(encoding="utf-8"), "2")
            self.assertIn("category=boundary_violation", result.stderr)
            self.assertIn("attempts=1/1", result.stderr)
            self.assertFalse(helper_args.exists())

            events = ledger.read_events(sid, rid, base_dir=state_base)
            blocked_events = [
                event
                for event in events
                if event.get("event") == "blocked"
                and event.get("category") == "worker_boundary"
            ]
            self.assertEqual(len(blocked_events), 1)
            self.assertEqual(blocked_events[0].get("agent"), "build-worker")
            self.assertEqual(blocked_events[0].get("provider"), "codex-headless")
            self.assertEqual(
                blocked_events[0].get("reason"),
                "mutation-time boundary recovery exhausted",
            )

            from harness.session_state import read_live

            live = read_live(sid, base_dir=state_base)
            marker = live["active_runs"][rid].get("blocked")
            self.assertIsInstance(marker, dict)
            self.assertEqual(marker.get("category"), "worker_boundary")

    def test_permission_required_boundary_stops_without_blind_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            sid = "sid-chain-permission"
            rid = "run-c0de1180"
            state_base = project / ".claude" / "harness-state"
            transition(
                sid,
                "run_started",
                run_id=rid,
                base_dir=state_base,
                entry_point="impl",
                lane="lite",
            )
            transition(
                sid,
                "step_started",
                run_id=rid,
                base_dir=state_base,
                agent="build-worker",
                mode=None,
            )

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            call_count = tmp / "codex-count.txt"

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
                cat >/dev/null
                count="$(cat "$CALL_COUNT" 2>/dev/null || printf 0)"
                count=$((count + 1))
                printf '%s' "$count" > "$CALL_COUNT"
                mkdir -p hooks
                printf 'attempt %s\\n' "$count" > hooks/catastrophic-gate.sh
                printf 'java.net.SocketException: Operation not permitted\\n' >&2
                printf 'Validation could not run.\\n\\nVALIDATION_BLOCKED\\n' > "$out"
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CALL_COUNT": str(call_count),
                    "DCNESS_IMPLEMENTATION_RECOVERY_LIMIT": "2",
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "HELPER_ARGS": str(helper_args),
                    "PATH": (
                        f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin"
                    ),
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
            self.assertEqual(call_count.read_text(encoding="utf-8"), "1")
            self.assertIn("category=boundary_violation", result.stderr)
            self.assertIn("permission_required", result.stderr)
            self.assertNotIn("RECOVERY provider=", result.stderr)
            self.assertFalse(helper_args.exists())

            receipts = list(
                (
                    state_base
                    / ".sessions"
                    / sid
                    / "runs"
                    / rid
                ).glob("codex-sandbox-permission-build-worker-*.json")
            )
            self.assertEqual(len(receipts), 1)
            events = ledger.read_events(sid, rid, base_dir=state_base)
            permission_events = [
                event
                for event in events
                if event.get("event") == "blocked"
                and event.get("category")
                == "codex_sandbox_permission_required"
            ]
            boundary_events = [
                event
                for event in events
                if event.get("event") == "blocked"
                and event.get("category") == "worker_boundary"
            ]
            self.assertEqual(len(permission_events), 1)
            self.assertEqual(len(boundary_events), 1)

    def test_post_run_tdd_guard_failure_retries_and_rechecks_guard(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement TypeScript through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            call_count = tmp / "codex-count.txt"

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
                cat >/dev/null
                count="$(cat "$CALL_COUNT" 2>/dev/null || printf 0)"
                count=$((count + 1))
                printf '%s' "$count" > "$CALL_COUNT"
                mkdir -p src
                printf 'export const value = 1;\\n' > src/feature.ts
                if [ "$count" -gt 1 ]; then
                  printf \"test('value', () => {});\\n\" > src/feature.test.ts
                fi
                printf 'Worker prose\\n\\nPASS\\n' > "$out"
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CALL_COUNT": str(call_count),
                    "DCNESS_FORCE_ENABLE": "1",
                    "DCNESS_IMPLEMENTATION_RECOVERY_LIMIT": "1",
                    "DCNESS_RUN_ID": "run-91919191",
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
            self.assertEqual(call_count.read_text(encoding="utf-8"), "2")
            self.assertTrue((project / "src" / "feature.test.ts").is_file())
            self.assertIn("category=tdd_guard", result.stderr)

    def test_committed_timeout_diff_stays_in_guard_scope_during_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=project,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=project,
                check=True,
            )
            (project / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "fixture"],
                cwd=project,
                check=True,
            )

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement TypeScript through chain.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"
            prose_capture = tmp / "prose.md"
            call_count = tmp / "codex-count.txt"

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
                cat >/dev/null
                count="$(cat "$CALL_COUNT" 2>/dev/null || printf 0)"
                count=$((count + 1))
                printf '%s' "$count" > "$CALL_COUNT"
                mkdir -p src
                if [ "$count" -eq 1 ]; then
                  printf 'export const value = 1;\\n' > src/committed.ts
                  git add src/committed.ts
                  git commit -qm 'partial implementation'
                  exit 124
                fi
                if [ "$count" -eq 3 ]; then
                  printf "test('value', () => {});\\n" > src/committed.test.ts
                fi
                printf 'Worker prose\\n\\nPASS\\n' > "$out"
                """,
            )
            helper = tmp / "dcness-helper"
            _write_helper(helper, helper_args, prose_capture)

            env = os.environ.copy()
            env.update(
                {
                    "CALL_COUNT": str(call_count),
                    "DCNESS_FORCE_ENABLE": "1",
                    "DCNESS_IMPLEMENTATION_RECOVERY_LIMIT": "2",
                    "DCNESS_RUN_ID": "run-93939393",
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
            self.assertEqual(call_count.read_text(encoding="utf-8"), "3")
            self.assertTrue((project / "src" / "committed.test.ts").is_file())
            self.assertIn("category=timeout", result.stderr)
            self.assertIn("category=tdd_guard", result.stderr)

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


class ChainWorkerConclusionTests(unittest.TestCase):
    """Issue #1217 — a worker that exits 0 with a non-PASS conclusion is not done."""

    def _run_chain_with_claude_prose(
        self, tmp: Path, prose: str, *, provider: str = "claude-headless"
    ) -> subprocess.CompletedProcess:
        project = tmp / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)

        prompt_file = tmp / "prompt.md"
        prompt_file.write_text("Implement through chain.\n", encoding="utf-8")
        helper_args = tmp / "helper-args.txt"
        prose_capture = tmp / "prose.md"
        helper = tmp / "dcness-helper"
        _write_helper(helper, helper_args, prose_capture)

        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        _write_executable(
            bin_dir / "claude",
            f"""\
            #!/bin/sh
            cat >/dev/null
            printf '{prose}'
            """,
        )

        env = os.environ.copy()
        env.update(
            {
                "DCNESS_RUN_ID": "run-17171717",
                "DCNESS_SESSION_ID": "sid-chain",
                "HELPER_ARGS": str(helper_args),
                "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                "PROSE_CAPTURE": str(prose_capture),
            }
        )

        return subprocess.run(
            [
                str(CHAIN),
                "build-worker",
                "--provider",
                provider,
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

    def test_non_pass_conclusion_is_not_reported_as_completed(self) -> None:
        for conclusion in (
            "IMPLEMENTATION_ESCALATE",
            "SPEC_GAP_FOUND",
            "TESTS_FAIL",
            "VALIDATION_BLOCKED",
        ):
            with self.subTest(conclusion=conclusion), tempfile.TemporaryDirectory() as td:
                result = self._run_chain_with_claude_prose(
                    Path(td), f"worker stopped early\\n\\n{conclusion}\\n"
                )

                self.assertEqual(result.returncode, 76, result.stderr)
                self.assertIn("IMPLEMENTATION_NOT_COMPLETED", result.stderr)
                self.assertIn(conclusion, result.stderr)
                self.assertNotIn("IMPLEMENTATION_COMPLETED", result.stderr)

    def test_pass_conclusion_still_reports_completion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self._run_chain_with_claude_prose(
                Path(td), "worker finished the task\\n\\nPASS\\n"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("IMPLEMENTATION_COMPLETED", result.stderr)

    def test_rework_pass_narrating_a_fixed_failure_is_not_blocked(self) -> None:
        """A PASS that describes the previously fixed TESTS_FAIL is still a PASS."""
        with tempfile.TemporaryDirectory() as td:
            result = self._run_chain_with_claude_prose(
                Path(td),
                "round 1 의 TESTS_FAIL 은 모두 근본 원인으로 닫혔습니다.\\n"
                "lint/build/unit test 전부 green 입니다.\\n\\nPASS\\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("IMPLEMENTATION_COMPLETED", result.stderr)
            self.assertNotIn("IMPLEMENTATION_NOT_COMPLETED", result.stderr)

    def test_unreadable_conclusion_completes_with_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self._run_chain_with_claude_prose(
                Path(td), "worker wrote prose without any conclusion label\\n"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("IMPLEMENTATION_COMPLETED", result.stderr)
            self.assertIn("conclusion could not be read", result.stderr)

    def test_non_pass_conclusion_does_not_fall_back_to_the_next_provider(self) -> None:
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
                printf 'env probe failed before any source edit\\n\\nIMPLEMENTATION_ESCALATE\\n' > "$out"
                """,
            )
            _write_executable(
                bin_dir / "claude",
                """\
                #!/bin/sh
                printf called > "$CLAUDE_CALLED"
                cat >/dev/null
                printf 'should not run\\n\\nPASS\\n'
                """,
            )

            env = os.environ.copy()
            env.update(
                {
                    "CLAUDE_CALLED": str(claude_called),
                    "DCNESS_RUN_ID": "run-12171217",
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

            self.assertEqual(result.returncode, 76, result.stderr)
            self.assertIn("IMPLEMENTATION_ESCALATE", result.stderr)
            self.assertNotIn("IMPLEMENTATION_COMPLETED", result.stderr)
            self.assertFalse(claude_called.exists())


if __name__ == "__main__":
    unittest.main()
