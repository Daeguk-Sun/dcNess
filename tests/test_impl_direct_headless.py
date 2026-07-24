"""Direct /impl one-shot headless ownership and lifecycle contracts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHAIN = ROOT / "scripts" / "dcness-implementation-chain"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_executable(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class DirectHeadlessImplTests(unittest.TestCase):
    def _fixture(self, base: Path) -> tuple[Path, Path]:
        primary = base / "primary"
        worktree = base / "worktree"
        primary.mkdir()
        _git(primary, "init", "-q", "-b", "main")
        _git(primary, "config", "user.name", "dcNess Test")
        _git(primary, "config", "user.email", "dcness-test@example.invalid")
        (primary / "README.md").write_text("fixture\n", encoding="utf-8")
        (primary / "docs" / "epics").mkdir(parents=True)
        (primary / "docs" / "epics" / "issue-1192.md").write_text(
            "# fixture design\n",
            encoding="utf-8",
        )
        _git(primary, "add", ".")
        _git(primary, "commit", "-qm", "fixture")
        _git(
            primary,
            "worktree",
            "add",
            "-q",
            "-b",
            "fix/issue1192_fixture",
            str(worktree),
            "main",
        )
        return primary, worktree

    def _provider_bin(self, base: Path) -> Path:
        bin_dir = base / "bin"
        bin_dir.mkdir(exist_ok=True)
        _write_executable(
            bin_dir / "claude",
            """\
            #!/bin/sh
            count="$(cat "$PROVIDER_COUNT" 2>/dev/null || printf 0)"
            count=$((count + 1))
            printf '%s' "$count" > "$PROVIDER_COUNT"
            cat > "$PROMPT_CAPTURE"
            python3 - "$PROMPT_CAPTURE" <<'PY'
            import pathlib
            import re
            import sys

            prompt = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
            match = re.search(r"^canonical run directory: (.+)$", prompt, re.MULTILINE)
            if not match:
                raise SystemExit("canonical run directory missing")
            run_dir = pathlib.Path(match.group(1))
            for phase in ("build-test.md", "build-impl.md", "build-validate.md"):
                (run_dir / phase).write_text(f"{phase} direct evidence\\n", encoding="utf-8")
            PY
            printf 'Direct worker completed.\\n\\nPASS\\n'
            """,
        )
        _write_executable(
            bin_dir / "codex",
            """\
            #!/bin/sh
            if [ "${1:-}" = "--help" ]; then
              printf 'codex fixture\\n'
              exit 0
            fi
            if [ "${CODEX_EXIT_CODE:-0}" -ne 0 ]; then
              exit "$CODEX_EXIT_CODE"
            fi
            output=""
            previous=""
            for argument in "$@"; do
              if [ "$previous" = "--output-last-message" ]; then
                output="$argument"
                break
              fi
              previous="$argument"
            done
            [ -n "$output" ] || exit 2
            count="$(cat "$PROVIDER_COUNT" 2>/dev/null || printf 0)"
            count=$((count + 1))
            printf '%s' "$count" > "$PROVIDER_COUNT"
            cat > "$PROMPT_CAPTURE"
            python3 - "$PROMPT_CAPTURE" "$output" <<'PY'
            import pathlib
            import re
            import sys

            prompt = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
            match = re.search(r"^canonical run directory: (.+)$", prompt, re.MULTILINE)
            if not match:
                raise SystemExit("canonical run directory missing")
            run_dir = pathlib.Path(match.group(1))
            for phase in ("build-test.md", "build-impl.md", "build-validate.md"):
                (run_dir / phase).write_text(f"{phase} direct evidence\\n", encoding="utf-8")
            pathlib.Path(sys.argv[2]).write_text(
                "Direct Codex worker completed.\\n\\nPASS\\n",
                encoding="utf-8",
            )
            PY
            """,
        )
        return bin_dir

    def _launch(
        self,
        *,
        primary: Path,
        project: Path,
        base: Path,
        provider: str | None = "claude-headless",
        codex_exit_code: int = 0,
        extra_args: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        prompt = base / "prompt.md"
        prompt.write_text(
            "\n".join(
                [
                    "target: issue #1192 fixture",
                    "confirmed_choice: complex upfront-headless",
                    "scope: README.md",
                    "test: no product mutation in fixture",
                    "ssot_pointer: README.md",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        bin_dir = self._provider_bin(base)
        env = os.environ.copy()
        env.update(
            {
                "DCNESS_FORCE_ENABLE": "1",
                "DCNESS_SESSION_ID": "sid-direct-impl",
                "CODEX_EXIT_CODE": str(codex_exit_code),
                "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                "PROMPT_CAPTURE": str(base / "provider-prompt.md"),
                "PROVIDER_COUNT": str(base / "provider-count.txt"),
            }
        )
        command = [
            str(CHAIN),
            "build-worker",
            "--direct-run",
            "--prompt-file",
            str(prompt),
            "--issue-num",
            "1192",
            "--project-root",
            str(project),
            "--helper",
            str(ROOT / "scripts" / "dcness-helper"),
            *extra_args,
        ]
        if provider is not None:
            command[3:3] = [
                "--provider",
                provider,
                "--provider-provenance",
                "explicit",
            ]
        result = subprocess.run(
            command,
            cwd=project,
            capture_output=True,
            env=env,
            text=True,
            timeout=30,
        )
        self.provider_count = base / "provider-count.txt"
        self.prompt_capture = base / "provider-prompt.md"
        return result

    def test_direct_one_shot_creates_lite_run_and_opposite_review_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=worktree,
                base=base,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-direct-impl"
                / "runs"
            )
            run_dirs = list(run_root.glob("run-*"))
            self.assertEqual(len(run_dirs), 1)
            events = [
                json.loads(line)
                for line in (run_dirs[0] / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [event["event"] for event in events],
                ["run_started", "step_started", "step_completed"],
            )
            self.assertEqual(events[0]["lane"], "lite")
            self.assertEqual(events[0]["issue_num"], 1192)
            self.assertEqual(events[2]["provider"], "claude-headless")
            self.assertIn(
                "IMPLEMENTATION_COMPLETED provider=claude-headless "
                "review_provider=codex fallback=none",
                result.stderr,
            )
            prompt = self.prompt_capture.read_text(encoding="utf-8")
            self.assertIn("target: issue #1192 fixture", prompt)
            self.assertIn("canonical run directory:", prompt)
            for phase in ("build-test.md", "build-impl.md", "build-validate.md"):
                self.assertTrue((run_dirs[0] / phase).is_file())

            repeated = self._launch(
                primary=primary,
                project=worktree,
                base=base,
            )
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(self.provider_count.read_text(encoding="utf-8"), "1")

            unsafe_rework = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                extra_args=("--rework",),
            )
            self.assertEqual(unsafe_rework.returncode, 2)
            self.assertIn(
                "--rework requires --resume-provider",
                unsafe_rework.stderr,
            )
            self.assertEqual(self.provider_count.read_text(encoding="utf-8"), "1")

            rework = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                provider=None,
                extra_args=(
                    "--rework",
                    "--resume-provider",
                    "claude-headless",
                ),
            )
            self.assertEqual(rework.returncode, 0, rework.stderr)
            self.assertEqual(self.provider_count.read_text(encoding="utf-8"), "2")
            rework_events = [
                json.loads(line)
                for line in (run_dirs[0] / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [event["event"] for event in rework_events],
                [
                    "run_started",
                    "step_started",
                    "step_completed",
                    "step_started",
                    "step_completed",
                ],
            )
            self.assertEqual(rework_events[-1]["provider"], "claude-headless")

    def test_design_doc_rework_reuses_completed_run_without_repassing_doc(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                extra_args=("--design-doc", "docs/epics/issue-1192.md"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-direct-impl"
                / "runs"
            )
            run_dirs = list(run_root.glob("run-*"))
            self.assertEqual(len(run_dirs), 1)
            initial_events = [
                json.loads(line)
                for line in (run_dirs[0] / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                Path(initial_events[0]["design_doc"]).resolve(),
                (worktree / "docs" / "epics" / "issue-1192.md").resolve(),
            )
            self.assertNotIn("lane", initial_events[0])

            rework = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                provider=None,
                extra_args=(
                    "--rework",
                    "--resume-provider",
                    "claude-headless",
                ),
            )
            self.assertEqual(rework.returncode, 0, rework.stderr)
            self.assertEqual(len(list(run_root.glob("run-*"))), 1)
            events = [
                json.loads(line)
                for line in (run_dirs[0] / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [event["event"] for event in events],
                [
                    "run_started",
                    "step_started",
                    "step_completed",
                    "step_started",
                    "step_completed",
                ],
            )
            self.assertEqual(events[-1]["provider"], "claude-headless")

    def test_direct_pre_mutation_failure_falls_back_and_reports_actual_provider(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                provider="headless-chain",
                codex_exit_code=1,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "provider codex-headless failed before workspace mutation",
                result.stderr,
            )
            self.assertIn(
                "IMPLEMENTATION_COMPLETED provider=claude-headless "
                "review_provider=codex fallback=none",
                result.stderr,
            )
            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-direct-impl"
                / "runs"
            )
            run_dir = next(run_root.glob("run-*"))
            events = [
                json.loads(line)
                for line in (run_dir / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(events[-1]["provider"], "claude-headless")

    def test_direct_codex_success_routes_review_to_claude(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                provider="headless-chain",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "IMPLEMENTATION_COMPLETED provider=codex-headless "
                "review_provider=claude fallback=none",
                result.stderr,
            )
            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-direct-impl"
                / "runs"
            )
            run_dir = next(run_root.glob("run-*"))
            events = [
                json.loads(line)
                for line in (run_dir / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(events[-1]["provider"], "codex-headless")

    def test_direct_initial_launch_refuses_default_branch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, _ = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=primary,
                base=base,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("enter an isolated feature worktree first", result.stderr)
            self.assertFalse(
                (
                    primary
                    / ".claude"
                    / "harness-state"
                    / ".sessions"
                    / "sid-direct-impl"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
