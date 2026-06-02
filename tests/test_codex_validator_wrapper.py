"""Smoke tests for the Codex validator wrapper."""
from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
