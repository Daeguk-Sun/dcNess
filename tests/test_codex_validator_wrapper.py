"""Smoke tests for the Codex validator wrapper."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from harness.session_state import start_run


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "dcness-codex-validator"
WORKER = ROOT / "scripts" / "dcness-codex-worker"


class CodexValidatorWrapperTests(unittest.TestCase):
    def test_embeds_plugin_skill_and_mode_before_prompt_when_installed_copy_is_stale(self) -> None:
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
                "# Installed Skill\n\nSTALE_INSTALLED_CHECKLIST\n",
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
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      exit 0
                    fi
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
            self.assertIn("# dcness-architecture-validator", prompt)
            self.assertNotIn("STALE_INSTALLED_CHECKLIST", prompt)
            self.assertIn("Review this implementation.", prompt)
            self.assertIn("stale installed skill ignored", result.stderr)
            self.assertIn("/init-dcness Core Step 5", result.stderr)
            self.assertTrue(
                helper_args.read_text(encoding="utf-8")
                .strip()
                .startswith(
                    "end-step architecture-validator SECOND "
                    "--provider codex-headless --prose-file "
                ),
            )
            self.assertEqual(
                prose_capture.read_text(encoding="utf-8"),
                "Codex prose\n\nPASS\n",
            )
            self.assertEqual(
                codex_env_capture.read_text(encoding="utf-8"),
                "sid-test\nrun-1234abcd\n",
            )

    def test_passes_model_and_effort_overrides_when_env_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review this implementation.\n", encoding="utf-8")

            args_capture = tmp / "codex-args.txt"
            prose_capture = tmp / "captured-prose.md"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      echo "  -a, --ask-for-approval <APPROVAL_POLICY>"
                      exit 0
                    fi
                    printf '%s\\n' "$@" > "$ARGS_CAPTURE"
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
            env.update(
                {
                    "ARGS_CAPTURE": str(args_capture),
                    "DCNESS_CODEX_EFFORT": "xhigh",
                    "DCNESS_CODEX_MODEL": "gpt-test-model",
                    "DCNESS_RUN_ID": "run-abcdef01",
                    "DCNESS_SESSION_ID": "sid-model",
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
            args = args_capture.read_text(encoding="utf-8")
            self.assertIn("-m\ngpt-test-model\n", args)
            self.assertIn("-c\nmodel_reasoning_effort=xhigh\n", args)

    def test_inherits_model_and_effort_when_env_is_unset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review this implementation.\n", encoding="utf-8")

            args_capture = tmp / "codex-args.txt"
            prose_capture = tmp / "captured-prose.md"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      exit 0
                    fi
                    printf '%s\\n' "$@" > "$ARGS_CAPTURE"
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
            env.pop("DCNESS_CODEX_EFFORT", None)
            env.pop("DCNESS_CODEX_MODEL", None)
            env.update(
                {
                    "ARGS_CAPTURE": str(args_capture),
                    "DCNESS_RUN_ID": "run-abcdef02",
                    "DCNESS_SESSION_ID": "sid-inherit",
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
            args = args_capture.read_text(encoding="utf-8").splitlines()
            self.assertNotIn("-m", args)
            self.assertNotIn("model_reasoning_effort=xhigh", args)

    def test_resolves_sid_rid_without_caller_env(self) -> None:
        """issue #625 — Codex subprocess PPID/env 단절 전 wrapper 가 sid/rid 를 export."""
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
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      exit 0
                    fi
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
            wrapper_tmpdir = tmp / "wrapper-tmp"
            wrapper_tmpdir.mkdir()

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      exit 0
                    fi
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
                    "TMPDIR": str(wrapper_tmpdir),
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
                .startswith(
                    "end-step pr-reviewer --provider codex-headless --prose-file "
                ),
            )
            prose = prose_capture.read_text(encoding="utf-8")
            self.assertIn("did not finish within 1s", prose)
            self.assertTrue(prose.rstrip().endswith("ESCALATE"))
            # issue #723 — the timeout/retry path must clean up its temp files so
            # no residue pollutes the next run (the EXIT trap fires on exit 124).
            residue = sorted(p.name for p in wrapper_tmpdir.iterdir())
            self.assertEqual(
                residue, [], f"wrapper left temp residue after timeout: {residue}"
            )


class CodexWorkerWrapperTests(unittest.TestCase):
    def test_worker_embeds_agent_docs_writes_workspace_and_stores_prose(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement the task from docs/impl.md.\n", encoding="utf-8")

            prompt_capture = tmp / "captured-prompt.md"
            args_capture = tmp / "codex-args.txt"
            prose_capture = tmp / "captured-prose.md"
            helper_args = tmp / "helper-args.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      echo "  -a, --ask-for-approval <APPROVAL_POLICY>"
                      exit 0
                    fi
                    printf '%s\\n' "$@" > "$ARGS_CAPTURE"
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
                    mkdir -p src
                    printf 'print("ok")\\n' > src/generated.py
                    printf 'Worker prose\\n\\nPASS\\n' > "$out"
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
                    "ARGS_CAPTURE": str(args_capture),
                    "DCNESS_RUN_ID": "run-feedface",
                    "DCNESS_SESSION_ID": "sid-worker",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "PROMPT_CAPTURE": str(prompt_capture),
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(WORKER),
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
            prompt = prompt_capture.read_text(encoding="utf-8")
            self.assertIn("dcNess implementation agent: build-worker", prompt)
            self.assertIn("build-worker 지침", prompt)
            self.assertIn("Implement the task from docs/impl.md.", prompt)
            self.assertIn("-a\nnever\nexec", args_capture.read_text(encoding="utf-8"))
            self.assertIn("workspace-write", args_capture.read_text(encoding="utf-8"))
            self.assertTrue((project / "src" / "generated.py").exists())
            self.assertTrue(
                helper_args.read_text(encoding="utf-8")
                .strip()
                .startswith(
                    "end-step build-worker --provider codex-headless --prose-file "
                ),
            )
            self.assertEqual(
                prose_capture.read_text(encoding="utf-8"),
                "Worker prose\n\nPASS\n",
            )

    def test_worker_passes_model_and_effort_overrides_when_env_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement the task.\n", encoding="utf-8")

            args_capture = tmp / "codex-args.txt"
            prose_capture = tmp / "captured-prose.md"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      echo "  -a, --ask-for-approval <APPROVAL_POLICY>"
                      exit 0
                    fi
                    printf '%s\\n' "$@" > "$ARGS_CAPTURE"
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
                    printf 'Worker prose\\n\\nPASS\\n' > "$out"
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
            env.update(
                {
                    "ARGS_CAPTURE": str(args_capture),
                    "DCNESS_CODEX_EFFORT": "high",
                    "DCNESS_CODEX_MODEL": "gpt-worker-model",
                    "DCNESS_RUN_ID": "run-abcdef03",
                    "DCNESS_SESSION_ID": "sid-worker-model",
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "PROSE_CAPTURE": str(prose_capture),
                }
            )

            result = subprocess.run(
                [
                    str(WORKER),
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
            self.assertIn("-m\ngpt-worker-model\n", args)
            self.assertIn("-c\nmodel_reasoning_effort=high\n", args)

    def test_worker_success_blocks_boundary_violation_without_end_step(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement the task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex"
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
                    mkdir -p docs
                    printf 'bad\\n' > docs/bad.md
                    printf 'Worker prose\\n\\nPASS\\n' > "$out"
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
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            helper.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": "run-badbad00",
                    "DCNESS_SESSION_ID": "sid-worker",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                }
            )

            result = subprocess.run(
                [
                    str(WORKER),
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
            self.assertIn("outside build-worker boundary", result.stderr)
            self.assertFalse(helper_args.exists())

    def test_worker_success_blocks_ts_impl_without_matching_test(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement the task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex"
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
                    mkdir -p src
                    printf 'export const price = 1;\\n' > src/price.ts
                    printf 'Worker prose\\n\\nPASS\\n' > "$out"
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
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            helper.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": "run-tddblock",
                    "DCNESS_SESSION_ID": "sid-worker",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                }
            )

            result = subprocess.run(
                [
                    str(WORKER),
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
            self.assertIn("TDD GUARD", result.stderr)
            self.assertIn("src/price.ts", result.stderr)
            self.assertFalse(helper_args.exists())

    def test_worker_success_allows_ts_impl_with_matching_test(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement the task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex"
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
                    mkdir -p src
                    printf 'export const price = 1;\\n' > src/price.ts
                    printf 'test("price", () => {});\\n' > src/price.test.ts
                    printf 'Worker prose\\n\\nPASS\\n' > "$out"
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
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            helper.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": "run-tddallow",
                    "DCNESS_SESSION_ID": "sid-worker",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                }
            )

            result = subprocess.run(
                [
                    str(WORKER),
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
            self.assertTrue(
                helper_args.read_text(encoding="utf-8")
                .strip()
                .startswith(
                    "end-step build-worker --provider codex-headless --prose-file "
                ),
            )

    def test_worker_failure_after_mutation_does_not_fallback_or_end_step(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement the task.\n", encoding="utf-8")
            helper_args = tmp / "helper-args.txt"

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
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
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            helper.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "DCNESS_RUN_ID": "run-partial1",
                    "DCNESS_SESSION_ID": "sid-worker",
                    "HELPER_ARGS": str(helper_args),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                }
            )

            result = subprocess.run(
                [
                    str(WORKER),
                    "engineer",
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
            self.assertIn("failed after changing workspace", result.stderr)
            self.assertFalse(helper_args.exists())


class CodexValidatorWrapperMktempTests(unittest.TestCase):
    def test_mktemp_templates_use_trailing_random_field(self) -> None:
        """issue #723 — BSD(macOS) mktemp only randomizes a trailing run of X's;
        a suffix after the X-field (e.g. '.md') makes literal, colliding temp
        files. GNU mktemp on Linux CI tolerates embedded X's, so only this static
        check catches reintroduction across platforms."""
        text = WRAPPER.read_text(encoding="utf-8")
        templates = re.findall(r'mktemp\s+(?:-\S+\s+)?"([^"]+)"', text)
        self.assertTrue(
            templates, "expected at least one mktemp template in the wrapper"
        )
        for tpl in templates:
            self.assertRegex(
                tpl,
                r"X{6,}$",
                f"mktemp template must end with the trailing random field: {tpl!r}",
            )

    def test_tempfiles_unique_and_cleaned_in_isolated_tmpdir(self) -> None:
        """issue #723 — temp file creation must succeed uniquely and leave no
        residue regardless of prior TMPDIR state (deterministic across runs)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            wrapper_tmpdir = tmp / "wrapper-tmp"
            wrapper_tmpdir.mkdir()
            # Residue a prior SIGKILLed run could leave under the broken
            # embedded-suffix template; the wrapper must not collide with it.
            seed = wrapper_tmpdir / "dcness-codex-pr-reviewer.XXXXXX"
            seed.write_text("stale", encoding="utf-8")

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Review this implementation.\n", encoding="utf-8")
            prose_capture = tmp / "prose.md"

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
            env.update(
                {
                    "DCNESS_RUN_ID": "run-13572468",
                    "DCNESS_SESSION_ID": "sid-iso",
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "PROSE_CAPTURE": str(prose_capture),
                    "TMPDIR": str(wrapper_tmpdir),
                }
            )

            # Two consecutive runs: the broken embedded-suffix template would make
            # the second mktemp fail with 'File exists'; trailing X's stay unique.
            for _ in range(2):
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
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            self.assertEqual(
                prose_capture.read_text(encoding="utf-8"), "Codex prose\n\nPASS\n"
            )
            # Only the pre-seeded residue remains; the wrapper cleaned its own files.
            leftovers = sorted(p.name for p in wrapper_tmpdir.iterdir())
            self.assertEqual(
                leftovers,
                ["dcness-codex-pr-reviewer.XXXXXX"],
                f"wrapper left unexpected temp residue: {leftovers}",
            )


if __name__ == "__main__":
    unittest.main()
