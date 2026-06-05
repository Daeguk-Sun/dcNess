"""Smoke tests for the Codex validator wrapper."""
from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from harness.session_state import start_run


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "dcness-codex-validator"


class CodexValidatorWrapperTests(unittest.TestCase):
    def test_embeds_installed_skill_and_mode_before_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review this implementation.\n", encoding="utf-8")

            codex_home = tmp / "codex-home"
            skill_dir = codex_home / "skills" / "dcness-architecture-validator"
            skill_dir.mkdir(parents=True)
            skill_dir.joinpath("SKILL.md").write_text(
                "# Test Skill\n\nSPECIAL_SKILL_CHECKLIST\n",
                encoding="utf-8",
            )

            prompt_capture = tmp / "captured-prompt.md"
            prose_capture = tmp / "captured-prose.md"
            helper_args = tmp / "helper-args.txt"
            codex_env_capture = tmp / "codex-env.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "exec" ] && [ "${2:-}" = "--help" ]; then
                      echo "Usage: codex exec"
                      exit 0
                    fi
                    out=""
                    while [ "$#" -gt 0 ]; do
                      case "$1" in
                        --output-last-message)
                          out="$2"
                          shift 2
                          ;;
                        *)
                          shift
                          ;;
                      esac
                    done
                    cat > "$PROMPT_CAPTURE"
                    printf '%s\\n%s\\n' "$DCNESS_SESSION_ID" "$DCNESS_RUN_ID" > "$CODEX_ENV_CAPTURE"
                    printf 'Codex prose\\n\\nPASS\\n' > "$out"
                    """
                ),
                encoding="utf-8",
            )
            codex.chmod(0o755)

            helper = tmp / "dcness-helper"
            helper.write_text(
                textwrap.dedent(
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
                    """
                ),
                encoding="utf-8",
            )
            helper.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "CODEX_HOME": str(codex_home),
                    "CODEX_ENV_CAPTURE": str(codex_env_capture),
                    "DCNESS_RUN_ID": "run-1234abcd",
                    "DCNESS_SESSION_ID": "sid-test",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "PROMPT_CAPTURE": str(prompt_capture),
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(WRAPPER),
                    "architecture-validator",
                    "SECOND",
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
            prompt = prompt_capture.read_text(encoding="utf-8")
            self.assertIn("dcNess validation agent: architecture-validator", prompt)
            self.assertIn("dcNess validation mode: SECOND", prompt)
            self.assertIn("SPECIAL_SKILL_CHECKLIST", prompt)
            self.assertIn("Review this implementation.", prompt)
            self.assertTrue(
                helper_args.read_text(encoding="utf-8")
                .strip()
                .startswith("end-step architecture-validator SECOND --prose-file "),
            )
            self.assertEqual(
                prose_capture.read_text(encoding="utf-8"),
                "Codex prose\n\nPASS\n",
            )
            self.assertEqual(
                codex_env_capture.read_text(encoding="utf-8"),
                "sid-test\nrun-1234abcd\n",
            )

    def test_resolves_sid_rid_without_caller_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            state_base = project / ".claude" / "harness-state"
            start_run("sid-auto", "run-a1b2c3d4", "impl", base_dir=state_base)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review this implementation.\n", encoding="utf-8")

            codex_env_capture = tmp / "codex-env.txt"
            prose_capture = tmp / "captured-prose.md"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "exec" ] && [ "${2:-}" = "--help" ]; then
                      echo "Usage: codex exec"
                      exit 0
                    fi
                    out=""
                    while [ "$#" -gt 0 ]; do
                      case "$1" in
                        --output-last-message)
                          out="$2"
                          shift 2
                          ;;
                        *)
                          shift
                          ;;
                      esac
                    done
                    cat >/dev/null
                    printf '%s\\n%s\\n' "$DCNESS_SESSION_ID" "$DCNESS_RUN_ID" > "$CODEX_ENV_CAPTURE"
                    printf 'Codex prose\\n\\nPASS\\n' > "$out"
                    """
                ),
                encoding="utf-8",
            )
            codex.chmod(0o755)

            helper = tmp / "dcness-helper"
            helper.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
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
                    """
                ),
                encoding="utf-8",
            )
            helper.chmod(0o755)

            env = os.environ.copy()
            env.pop("DCNESS_SESSION_ID", None)
            env.pop("DCNESS_RUN_ID", None)
            env.update(
                {
                    "CODEX_ENV_CAPTURE": str(codex_env_capture),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(WRAPPER),
                    "code-validator",
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
            self.assertEqual(
                codex_env_capture.read_text(encoding="utf-8"),
                "sid-auto\nrun-a1b2c3d4\n",
            )

    def test_timeout_retries_once_and_logs_escalate_prose(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review this implementation.\n", encoding="utf-8")

            attempts_file = tmp / "attempts.txt"
            prose_capture = tmp / "timeout-prose.md"
            helper_args = tmp / "helper-args.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "exec" ] && [ "${2:-}" = "--help" ]; then
                      echo "Usage: codex exec"
                      exit 0
                    fi
                    n=0
                    if [ -f "$ATTEMPTS_FILE" ]; then
                      n=$(cat "$ATTEMPTS_FILE")
                    fi
                    n=$((n + 1))
                    printf '%s' "$n" > "$ATTEMPTS_FILE"
                    sleep 30
                    """
                ),
                encoding="utf-8",
            )
            codex.chmod(0o755)

            helper = tmp / "dcness-helper"
            helper.write_text(
                textwrap.dedent(
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
                    """
                ),
                encoding="utf-8",
            )
            helper.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "ATTEMPTS_FILE": str(attempts_file),
                    "DCNESS_CODEX_TIMEOUT": "1",
                    "DCNESS_RUN_ID": "run-deadbeef",
                    "DCNESS_SESSION_ID": "sid-timeout",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(WRAPPER),
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
                timeout=10,
            )

            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertEqual(attempts_file.read_text(encoding="utf-8"), "2")
            self.assertIn("timed out after 1s (attempt 1/2)", result.stderr)
            self.assertIn("timed out after 1s (attempt 2/2)", result.stderr)
            self.assertTrue(
                helper_args.read_text(encoding="utf-8")
                .strip()
                .startswith("end-step pr-reviewer --prose-file "),
            )
            prose = prose_capture.read_text(encoding="utf-8")
            self.assertIn("did not finish within 1s", prose)
            self.assertTrue(prose.rstrip().endswith("ESCALATE"))


if __name__ == "__main__":
    unittest.main()
