"""Tests for implementation provider chain and Claude headless wrappers."""
from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_VALIDATOR = ROOT / "scripts" / "dcness-claude-validator"
CLAUDE_WORKER = ROOT / "scripts" / "dcness-claude-worker"
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


class ClaudeHeadlessWrapperTests(unittest.TestCase):
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
                    "pr-reviewer",
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
                    "engineer",
                    "IMPL",
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
