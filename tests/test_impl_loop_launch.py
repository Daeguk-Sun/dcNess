"""One-shot /impl-loop launch ordering and lifecycle contracts."""
from __future__ import annotations

from datetime import datetime
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


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
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


class ImplLoopLaunchTests(unittest.TestCase):
    def _fixture(self, base: Path, *, task_count: int = 1) -> tuple[Path, Path]:
        primary = base / "primary"
        worktree = base / "worktree"
        primary.mkdir()
        _run_git(primary, "init", "-q", "-b", "main")
        _run_git(primary, "config", "user.name", "dcNess Test")
        _run_git(primary, "config", "user.email", "dcness-test@example.invalid")
        impl_dir = primary / "docs" / "epics" / "epic-1" / "impl"
        impl_dir.mkdir(parents=True)
        for index in range(1, task_count + 1):
            task = impl_dir / f"{index:02d}-fast.md"
            task.write_text(
                "---\n"
                "story: 1\n"
                f"task_index: {index}/{task_count}\n"
                f"title: Fast start {index}\n"
                "---\n\n"
                "## 수정 허용\n- src/**\n",
                encoding="utf-8",
            )
        tdd_config = primary / ".dcness" / "tdd-hooks.json"
        tdd_config.parent.mkdir(parents=True)
        tdd_config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "platform": "android",
                    "impl_exts": [".kt", ".java"],
                    "source_roots": ["app/src/main"],
                    "test_candidate_templates": [
                        "app/src/test/java/{stem}Test{ext}",
                    ],
                    "test_file_globs": ["**/*Test.kt", "**/*Test.java"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (primary / "README.md").write_text("fixture\n", encoding="utf-8")
        _run_git(primary, "add", ".")
        _run_git(primary, "commit", "-qm", "fixture")
        _run_git(
            primary,
            "worktree",
            "add",
            "-q",
            "-b",
            "fix/issue1190_fixture",
            str(worktree),
            "main",
        )
        return primary, worktree

    def _launch(
        self,
        *,
        primary: Path,
        project: Path,
        base: Path,
        omit_phase_first_attempt: bool = False,
        use_claude_session_env: bool = False,
        acceptance_required: bool = True,
        provider_conclusion: str = "PASS",
        init_paths: tuple[str, ...] = (
            "docs/epics/epic-1/impl/01-fast.md",
        ),
    ) -> subprocess.CompletedProcess[str]:
        prompt = base / "prompt.md"
        prompt.write_text(
            "Read the task pointer, write RED first, implement, and validate.\n",
            encoding="utf-8",
        )
        provider_started = base / "provider-started.json"
        prompt_capture = base / "provider-prompt.md"
        bin_dir = base / "bin"
        bin_dir.mkdir(exist_ok=True)
        _write_executable(
            bin_dir / "claude",
            """\
            #!/bin/sh
            count="$(cat "$PROVIDER_COUNT" 2>/dev/null || printf 0)"
            count=$((count + 1))
            printf '%s' "$count" > "$PROVIDER_COUNT"
            python3 - "$PROVIDER_STARTED" <<'PY'
            import datetime
            import json
            import pathlib
            import sys
            pathlib.Path(sys.argv[1]).write_text(
                json.dumps({"at": datetime.datetime.now(datetime.timezone.utc).isoformat()}),
                encoding="utf-8",
            )
            PY
            cat > "$PROMPT_CAPTURE"
            if [ "$PROVIDER_CONCLUSION" != "PASS" ]; then
              :
            elif [ "$OMIT_PHASE_FIRST" = "1" ] && [ "$count" -eq 1 ]; then
              mkdir -p src
              printf 'partial work preserved for recovery\\n' > src/phase-recovery.txt
            else
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
                (run_dir / phase).write_text(f"{phase} fixture evidence\\n", encoding="utf-8")
            PY
            fi
            printf 'Worker completed without fixture mutation.\\n\\n%s\\n' "$PROVIDER_CONCLUSION"
            """,
        )
        env = os.environ.copy()
        env.update(
            {
                "DCNESS_FORCE_ENABLE": "1",
                "OMIT_PHASE_FIRST": "1" if omit_phase_first_attempt else "0",
                "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                "PROVIDER_CONCLUSION": provider_conclusion,
                "PROMPT_CAPTURE": str(prompt_capture),
                "PROVIDER_COUNT": str(base / "provider-count.txt"),
                "PROVIDER_STARTED": str(provider_started),
            }
        )
        if use_claude_session_env:
            env.pop("DCNESS_SESSION_ID", None)
            env["CLAUDE_CODE_SESSION_ID"] = "sid-fast-launch"
        else:
            env["DCNESS_SESSION_ID"] = "sid-fast-launch"
        command = [
                str(CHAIN),
                "build-worker",
                "--provider",
                "claude-headless",
                "--provider-provenance",
                "explicit",
                "--chain-state",
                ".dcness-work/story-run.json",
                "--prompt-file",
                str(prompt),
                "--project-root",
                str(project),
                "--helper",
                str(ROOT / "scripts" / "dcness-helper"),
            ]
        if acceptance_required:
            command.append("--acceptance-required")
        for init_path in init_paths:
            command[8:8] = ["--init-path", init_path]
        result = subprocess.run(
            command,
            cwd=project,
            capture_output=True,
            env=env,
            text=True,
            timeout=30,
        )
        self.provider_started = provider_started
        self.prompt_capture = prompt_capture
        self.provider_count = base / "provider-count.txt"
        return result

    def test_one_call_initializes_in_worktree_and_starts_step_before_provider(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(primary=primary, project=worktree, base=base)

            self.assertEqual(result.returncode, 0, result.stderr)
            state_path = worktree / ".dcness-work" / "story-run.json"
            self.assertTrue(state_path.is_file())
            self.assertFalse((primary / ".dcness-work" / "story-run.json").exists())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["project_root"], str(worktree.resolve()))

            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-fast-launch"
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
            self.assertEqual(events[1]["agent"], "build-worker")
            self.assertIs(events[0]["acceptance_required"], True)
            self.assertTrue(
                events[0]["design_doc"].startswith(str(worktree.resolve()))
            )
            provider_at = datetime.fromisoformat(
                json.loads(self.provider_started.read_text(encoding="utf-8"))["at"]
            )
            step_at = datetime.fromisoformat(events[1]["ts"])
            self.assertLessEqual(step_at, provider_at)
            prompt = self.prompt_capture.read_text(encoding="utf-8")
            self.assertIn("----- BEGIN PROJECT TDD CONTRACT -----", prompt)
            self.assertIn("app/src/main", prompt)
            self.assertIn("matching test", prompt)
            self.assertIn(
                f"canonical run directory: {run_dirs[0].resolve()}",
                prompt,
            )
            for phase in ("build-test.md", "build-impl.md", "build-validate.md"):
                self.assertIn(str((run_dirs[0] / phase).resolve()), prompt)
                self.assertTrue((run_dirs[0] / phase).is_file())

    def test_background_claude_session_id_bootstraps_first_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                use_claude_session_env=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-fast-launch"
                / "runs"
            )
            run_dirs = list(run_root.glob("run-*"))
            self.assertEqual(len(run_dirs), 1)
            events = [
                json.loads(line)["event"]
                for line in (run_dirs[0] / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                events,
                ["run_started", "step_started", "step_completed"],
            )

    def test_completed_current_run_is_idempotent_without_second_provider_fork(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            first = self._launch(primary=primary, project=worktree, base=base)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self._launch(primary=primary, project=worktree, base=base)

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("ALREADY_COMPLETED", second.stderr)
            self.assertEqual(self.provider_count.read_text(encoding="utf-8"), "1")
            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-fast-launch"
                / "runs"
            )
            run_dirs = list(run_root.glob("run-*"))
            self.assertEqual(len(run_dirs), 1)
            events = [
                json.loads(line)["event"]
                for line in (run_dirs[0] / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                events,
                ["run_started", "step_started", "step_completed"],
            )

    def test_main_branch_rejection_happens_before_run_or_story_state_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, _ = self._fixture(base)

            result = self._launch(primary=primary, project=primary, base=base)

            self.assertEqual(result.returncode, 2)
            self.assertIn("refusing default branch", result.stderr)
            self.assertFalse((primary / ".dcness-work" / "story-run.json").exists())
            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-fast-launch"
                / "runs"
            )
            self.assertFalse(run_root.exists())

    def test_second_task_reuses_state_but_gets_one_new_run_and_step(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base, task_count=2)
            init_paths = (
                "docs/epics/epic-1/impl/01-fast.md",
                "docs/epics/epic-1/impl/02-fast.md",
            )

            first = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                init_paths=init_paths,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            state_path = worktree / ".dcness-work" / "story-run.json"
            head = _run_git(worktree, "rev-parse", "HEAD").stdout.strip()
            marked = subprocess.run(
                [
                    str(ROOT / "scripts" / "dcness-story-runner"),
                    "mark",
                    "--state",
                    str(state_path),
                    "--task",
                    "1",
                    "--status",
                    "completed",
                    "--commit",
                    head,
                ],
                cwd=worktree,
                capture_output=True,
                text=True,
            )
            self.assertEqual(marked.returncode, 0, marked.stderr)

            second = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                init_paths=(),
            )
            self.assertEqual(second.returncode, 0, second.stderr)

            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-fast-launch"
                / "runs"
            )
            run_dirs = sorted(run_root.glob("run-*"))
            self.assertEqual(len(run_dirs), 2)
            event_sets = [
                [
                    json.loads(line)
                    for line in (run_dir / "ledger.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                for run_dir in run_dirs
            ]
            ledgers = [
                [event["event"] for event in events]
                for events in event_sets
            ]
            self.assertCountEqual(
                ledgers,
                [
                    [
                        "run_started",
                        "step_started",
                        "step_completed",
                        "run_finished",
                    ],
                    ["run_started", "step_started", "step_completed"],
                ],
            )
            run_started = [
                events[0]
                for events in event_sets
                if events and events[0]["event"] == "run_started"
            ]
            self.assertCountEqual(
                [
                    event.get("acceptance_required", False)
                    for event in run_started
                ],
                [False, True],
            )

    def test_missing_canonical_phase_prose_recovers_without_duplicate_step(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                omit_phase_first_attempt=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.provider_count.read_text(encoding="utf-8"), "2")
            self.assertIn("category=phase_evidence", result.stderr)
            self.assertTrue((worktree / "src" / "phase-recovery.txt").is_file())

            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-fast-launch"
                / "runs"
            )
            run_dirs = list(run_root.glob("run-*"))
            self.assertEqual(len(run_dirs), 1)
            events = [
                json.loads(line)["event"]
                for line in (run_dirs[0] / "ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                events,
                ["run_started", "step_started", "step_completed"],
            )
            for phase in ("build-test.md", "build-impl.md", "build-validate.md"):
                self.assertTrue((run_dirs[0] / phase).is_file())

    def test_preflight_escalation_records_terminal_prose_without_phase_retry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            primary, worktree = self._fixture(base)

            result = self._launch(
                primary=primary,
                project=worktree,
                base=base,
                provider_conclusion="IMPLEMENTATION_ESCALATE",
            )

            # The escalation is a terminal receipt, not a completed
            # implementation: the chain must not report it as one (issue #1217).
            self.assertEqual(result.returncode, 76, result.stderr)
            self.assertIn("IMPLEMENTATION_NOT_COMPLETED", result.stderr)
            self.assertIn("IMPLEMENTATION_ESCALATE", result.stderr)
            self.assertNotIn("IMPLEMENTATION_COMPLETED", result.stderr)
            self.assertEqual(self.provider_count.read_text(encoding="utf-8"), "1")
            self.assertNotIn("category=phase_evidence", result.stderr)

            run_root = (
                primary
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "sid-fast-launch"
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
            terminal_prose = Path(events[-1]["prose_file"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("IMPLEMENTATION_ESCALATE", terminal_prose)
            for phase in ("build-test.md", "build-impl.md", "build-validate.md"):
                self.assertFalse((run_dirs[0] / phase).exists())


if __name__ == "__main__":
    unittest.main()
