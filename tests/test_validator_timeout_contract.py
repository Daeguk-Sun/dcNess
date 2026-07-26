from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_VALIDATOR = ROOT / "scripts" / "dcness-claude-validator"
CODEX_VALIDATOR = ROOT / "scripts" / "dcness-codex-validator"


class ValidatorTimeoutContractTests(unittest.TestCase):
    def test_usage_documents_worker_aligned_timeout_defaults(self) -> None:
        for wrapper, hard_name, idle_name in (
            (
                CLAUDE_VALIDATOR,
                "DCNESS_CLAUDE_TIMEOUT",
                "DCNESS_CLAUDE_IDLE_TIMEOUT",
            ),
            (
                CODEX_VALIDATOR,
                "DCNESS_CODEX_TIMEOUT",
                "DCNESS_CODEX_IDLE_TIMEOUT",
            ),
        ):
            with self.subTest(wrapper=wrapper.name):
                result = subprocess.run(
                    [str(wrapper), "--help"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertIn(f"{hard_name}", result.stdout)
                self.assertIn("Default: 3000.", result.stdout)
                self.assertIn(f"{idle_name}", result.stdout)
                self.assertIn("Default: 900.", result.stdout)

    def test_progress_beyond_idle_window_completes_for_both_validators(self) -> None:
        for provider in ("claude", "codex"):
            with self.subTest(provider=provider):
                result = self._run_wrapper(
                    provider,
                    command_body=self._progressing_command(provider),
                    hard_timeout=5,
                    idle_timeout=1,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_zero_progress_process_stops_at_idle_timeout_with_distinct_reason(self) -> None:
        for provider in ("claude", "codex"):
            with self.subTest(provider=provider):
                result = self._run_wrapper(
                    provider,
                    command_body="sleep 30\n",
                    hard_timeout=10,
                    idle_timeout=1,
                )
                self.assertEqual(result.returncode, 124, result.stderr)
                self.assertIn("idle timeout after 1s", result.stderr)
                self.assertNotIn("total timeout after 10s", result.stderr)

    def test_hard_timeout_reports_total_timeout_reason(self) -> None:
        for provider in ("claude", "codex"):
            with self.subTest(provider=provider):
                result = self._run_wrapper(
                    provider,
                    command_body=self._progressing_forever_command(provider),
                    hard_timeout=1,
                    idle_timeout=10,
                )
                self.assertEqual(result.returncode, 124, result.stderr)
                self.assertIn("total timeout after 1s", result.stderr)
                self.assertNotIn("idle timeout after 10s", result.stderr)

    def _run_wrapper(
        self,
        provider: str,
        *,
        command_body: str,
        hard_timeout: int,
        idle_timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            prompt = tmp / "prompt.md"
            prompt.write_text("Review the candidate.\n", encoding="utf-8")

            helper = tmp / "dcness-helper"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(0o755)

            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            executable = bin_dir / provider
            executable.write_text(
                self._command_script(provider, command_body),
                encoding="utf-8",
            )
            executable.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    f"DCNESS_{provider.upper()}_TIMEOUT": str(hard_timeout),
                    f"DCNESS_{provider.upper()}_IDLE_TIMEOUT": str(idle_timeout),
                }
            )
            wrapper = CLAUDE_VALIDATOR if provider == "claude" else CODEX_VALIDATOR
            return subprocess.run(
                [
                    str(wrapper),
                    "impl-validator",
                    "--prompt-file",
                    str(prompt),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(helper),
                ],
                capture_output=True,
                env=env,
                text=True,
                timeout=12,
            )

    @staticmethod
    def _command_script(provider: str, command_body: str) -> str:
        codex_prelude = ""
        if provider == "codex":
            codex_prelude = textwrap.dedent(
                """\
                if [ "${1:-}" = "--help" ]; then
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
                """
            )
        return "#!/bin/sh\n" + codex_prelude + command_body

    @staticmethod
    def _progressing_command(provider: str) -> str:
        final_output = (
            "printf 'Validator prose\\n\\nPASS\\n' > \"$out\"\n"
            if provider == "codex"
            else "printf 'Validator prose\\n\\nPASS\\n'\n"
        )
        return (
            "i=0\n"
            "while [ \"$i\" -lt 6 ]; do\n"
            "  printf 'progress %s\\n' \"$i\"\n"
            "  sleep 0.25\n"
            "  i=$((i + 1))\n"
            "done\n"
            + final_output
        )

    @staticmethod
    def _progressing_forever_command(provider: str) -> str:
        del provider
        return (
            "while :; do\n"
            "  printf 'progress\\n'\n"
            "  sleep 0.2\n"
            "done\n"
        )


if __name__ == "__main__":
    unittest.main()
