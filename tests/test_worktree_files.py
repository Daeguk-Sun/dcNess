"""로컬 전용 하네스 파일의 linked worktree 연결 계약.

하네스 파일을 `.git/info/exclude` 로 커밋하지 않는 프로젝트에서 새 linked worktree 가
main worktree 의 파일을 링크로 받아 생성형 TDD guard·경계 계약이 그대로 동작하는지,
커밋된 프로젝트에는 아무것도 하지 않는지 검증한다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import worktree_files

ROOT = Path(__file__).resolve().parents[1]
TDD_HOOKS = ROOT / "scripts" / "dcness-tdd-hooks"
HELPER = ROOT / "scripts" / "dcness-helper"
LOCAL_ONLY = (
    "/CLAUDE.md\n/AGENTS.md\n/.claude/\n/.codex/\n/.dcness/\n/docs/index.md\n"
    "/local.properties\n/app/.env\n"
)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=a", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _env() -> dict[str, str]:
    return {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "DCNESS_TDD_PLUGIN_ROOT": str(ROOT),
        "PYTHONPATH": str(ROOT),
    }


class _Repo:
    """main worktree 하나와 그 linked worktree 를 만드는 fixture."""

    def __init__(self, *, local_only: bool = True) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.main = base / "main"
        self.main.mkdir()
        _git(self.main, "init", "-q", "-b", "main")
        (self.main / "pyproject.toml").write_text("[project]\nname='demo'\n")
        (self.main / "src").mkdir()
        (self.main / "src" / "existing.py").write_text("def existing():\n    return 1\n")
        if local_only:
            with (self.main / ".git" / "info" / "exclude").open("a") as fh:
                fh.write(LOCAL_ONLY)
        (self.main / "CLAUDE.md").write_text("# rules\n")
        (self.main / "docs").mkdir()
        (self.main / "docs" / "index.md").write_text("# index\n")
        self.base = base

    def ensure_tdd_hooks(self) -> None:
        subprocess.run(
            [
                str(TDD_HOOKS), "ensure", "--platform", "python", "--source-roots", "src",
                "--project-root", str(self.main), "--targets", "cc",
                "--plugin-root", str(ROOT),
            ],
            check=True, capture_output=True, text=True, timeout=30, env=_env(),
        )

    def commit_all(self) -> None:
        _git(self.main, "add", "-A")
        _git(self.main, "commit", "-qm", "init")

    def add_worktree(self, name: str = "wt") -> Path:
        path = self.base / name
        _git(self.main, "worktree", "add", "-q", "-b", f"feature/{name}", str(path))
        return path

    def close(self) -> None:
        self._tmp.cleanup()


class SyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _Repo()
        self.repo.ensure_tdd_hooks()
        self.repo.commit_all()
        self.wt = self.repo.add_worktree()

    def tearDown(self) -> None:
        self.repo.close()

    def test_links_local_only_harness_files_to_main_worktree(self) -> None:
        result = worktree_files.sync(self.wt)

        for rel in (
            "CLAUDE.md",
            ".claude/settings.json",
            ".claude/hooks/dcness-tdd-guard.sh",
            ".dcness/tdd-hooks.json",
            "docs/index.md",
        ):
            with self.subTest(rel=rel):
                dst = self.wt / rel
                self.assertTrue(dst.is_symlink())
                self.assertEqual(dst.resolve(), (self.repo.main / rel).resolve())
        self.assertIn("CLAUDE.md", result.linked)
        self.assertNotIn("AGENTS.md", result.linked)  # 원본 없음

    def test_worktree_status_stays_clean_after_sync(self) -> None:
        worktree_files.sync(self.wt)

        status = _git(self.wt, "status", "--porcelain").stdout
        self.assertEqual(status, "")

    def test_generated_tdd_hook_runs_in_worktree_after_sync(self) -> None:
        settings = json.loads((self.repo.main / ".claude" / "settings.json").read_text())
        command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        target = self.wt / "src" / "price.py"
        target.write_text("def price():\n    return 1\n")
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(target)}})

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["bash", "-c", command], input=payload, cwd=self.wt,
                capture_output=True, text=True, timeout=20, env=_env(),
            )

        before = run()
        self.assertIn("No such file", before.stderr)

        worktree_files.sync(self.wt)
        after = run()
        self.assertEqual(after.returncode, 2, after.stderr)
        self.assertIn("TDD GUARD", after.stderr)
        self.assertNotIn("No such file", after.stderr)

    def test_sync_is_idempotent(self) -> None:
        worktree_files.sync(self.wt)
        snapshot = sorted(
            (str(p.relative_to(self.wt)), os.readlink(p) if p.is_symlink() else None)
            for p in self.wt.rglob("*") if ".git" not in p.parts
        )
        second = worktree_files.sync(self.wt)

        self.assertEqual(second.linked, [])
        self.assertEqual(
            snapshot,
            sorted(
                (str(p.relative_to(self.wt)), os.readlink(p) if p.is_symlink() else None)
                for p in self.wt.rglob("*") if ".git" not in p.parts
            ),
        )

    def test_keeps_existing_real_file(self) -> None:
        (self.wt / "CLAUDE.md").write_text("# worktree own\n")

        result = worktree_files.sync(self.wt)

        self.assertFalse((self.wt / "CLAUDE.md").is_symlink())
        self.assertIn("CLAUDE.md", result.preserved)

    def test_main_worktree_is_untouched(self) -> None:
        result = worktree_files.sync(self.repo.main)

        self.assertFalse(result.linked_worktree)
        self.assertEqual(result.linked, [])

    def test_project_config_adds_link_and_copy_entries(self) -> None:
        (self.repo.main / "app").mkdir()
        (self.repo.main / "app" / ".env").write_text("TOKEN=1\n")
        (self.repo.main / "local.properties").write_text("sdk.dir=/x\n")
        (self.repo.main / worktree_files.CONFIG_REL).write_text(
            json.dumps({"link": ["app/.env"], "copy": ["local.properties"]})
        )

        result = worktree_files.sync(self.wt)

        self.assertTrue((self.wt / "app" / ".env").is_symlink())
        copied = self.wt / "local.properties"
        self.assertTrue(copied.is_file())
        self.assertFalse(copied.is_symlink())
        self.assertIn("local.properties", result.copied)
        self.assertEqual(_git(self.wt, "status", "--porcelain").stdout, "")

    def test_sync_all_covers_every_linked_worktree(self) -> None:
        second = self.repo.add_worktree("wt2")

        results = worktree_files.sync_all(self.repo.main)

        self.assertEqual(sorted(r.worktree for r in results), sorted([self.wt, second]))
        self.assertTrue((second / "CLAUDE.md").is_symlink())


class NotIgnoredTests(unittest.TestCase):
    def test_untracked_file_that_is_not_ignored_is_not_linked(self) -> None:
        repo = _Repo(local_only=False)
        try:
            # CLAUDE.md 는 커밋하지 않았지만 무시 대상도 아니다 — 연결하면 미추적 파일이 된다.
            _git(repo.main, "add", "pyproject.toml", "src")
            _git(repo.main, "commit", "-qm", "init")
            wt = repo.add_worktree()

            result = worktree_files.sync(wt)

            self.assertFalse((wt / "CLAUDE.md").exists())
            self.assertIn("CLAUDE.md", result.not_ignored)
        finally:
            repo.close()


class CommittedHarnessTests(unittest.TestCase):
    def test_committed_harness_files_are_left_alone(self) -> None:
        repo = _Repo(local_only=False)
        try:
            repo.ensure_tdd_hooks()
            repo.commit_all()
            wt = repo.add_worktree()
            before = {p: p.read_bytes() for p in wt.rglob("*") if p.is_file() and ".git" not in p.parts}

            result = worktree_files.sync(wt)

            self.assertEqual(result.linked + result.copied, [])
            after = {p: p.read_bytes() for p in wt.rglob("*") if p.is_file() and ".git" not in p.parts}
            self.assertEqual(before, after)
            self.assertFalse(any(p.is_symlink() for p in wt.rglob("*")))
        finally:
            repo.close()


class EntryPointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _Repo()
        self.repo.ensure_tdd_hooks()
        self.repo.commit_all()

    def tearDown(self) -> None:
        self.repo.close()

    def test_post_checkout_shim_links_files_on_git_worktree_add(self) -> None:
        hook = self.repo.main / ".git" / "hooks" / "post-checkout"
        shutil.copyfile(ROOT / "scripts" / "hooks" / "post-checkout", hook)
        hook.chmod(0o755)
        path = self.repo.base / "wt-hook"
        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "feature/hook_check", str(path)],
            cwd=self.repo.main, check=True, capture_output=True, text=True, env=_env(),
        )

        self.assertTrue((path / ".claude" / "hooks" / "dcness-tdd-guard.sh").is_symlink())

    def test_init_sync_all_twice_gives_same_result(self) -> None:
        wt = self.repo.add_worktree()

        def run_init_step() -> list[tuple[str, str]]:
            subprocess.run(
                [str(HELPER), "worktree-files", "sync", "--all", "--worktree", str(self.repo.main)],
                check=True, capture_output=True, text=True, timeout=20, env=_env(),
            )
            return sorted(
                (str(p.relative_to(wt)), os.readlink(p) if p.is_symlink() else p.read_text())
                for p in wt.rglob("*") if p.is_file() and ".git" not in p.parts
            )

        first = run_init_step()
        self.assertEqual(run_init_step(), first)
        self.assertEqual(_git(wt, "status", "--porcelain").stdout, "")

    def test_post_tool_use_enter_worktree_payload_links_files(self) -> None:
        wt = self.repo.add_worktree()
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "EnterWorktree",
            "cwd": str(wt),
            "tool_response": {"worktreePath": str(wt)},
        }
        proc = subprocess.run(
            ["bash", str(ROOT / "hooks" / "worktree-files.sh")],
            input=json.dumps(payload), cwd=wt, capture_output=True, text=True,
            timeout=20, env={**_env(), "DCNESS_FORCE_ENABLE": "1"},
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((wt / "CLAUDE.md").is_symlink())

    def test_helper_sync_command_links_files(self) -> None:
        wt = self.repo.add_worktree()
        proc = subprocess.run(
            [str(HELPER), "worktree-files", "sync"],
            cwd=wt, capture_output=True, text=True, timeout=20, env=_env(),
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((wt / "CLAUDE.md").is_symlink())


class InspectTests(unittest.TestCase):
    def test_reports_missing_files_in_linked_worktree(self) -> None:
        repo = _Repo()
        try:
            repo.ensure_tdd_hooks()
            repo.commit_all()
            wt = repo.add_worktree()

            state = worktree_files.inspect(wt)
            self.assertTrue(state.linked_worktree)
            self.assertIn("CLAUDE.md", state.missing)

            worktree_files.sync(wt)
            self.assertEqual(worktree_files.inspect(wt).missing, [])
        finally:
            repo.close()


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _Repo()
        self.repo.ensure_tdd_hooks()
        self.repo.commit_all()

    def tearDown(self) -> None:
        self.repo.close()

    def _check(self, cwd: Path) -> dict:
        from harness.session_state_status import collect_status_diagnostics

        diag = collect_status_diagnostics(
            cwd, settings_path=self.repo.base / "settings.json", plugin_root=ROOT,
            codex_home=self.repo.base / "codex", check_gh=False, check_routing=False,
        )
        return next(c for c in diag["checks"] if c["key"] == "worktree_files")

    def test_linked_worktree_warns_with_fix_then_passes_after_sync(self) -> None:
        wt = self.repo.add_worktree()

        missing = self._check(wt)
        self.assertEqual(missing["status"], "WARN")
        self.assertIn("CLAUDE.md", missing["detail"])
        self.assertIn("worktree-files sync", missing["fix"])

        worktree_files.sync(wt)
        self.assertEqual(self._check(wt)["status"], "PASS")

    def test_main_worktree_warns_when_post_checkout_shim_is_old(self) -> None:
        self.assertEqual(self._check(self.repo.main)["status"], "WARN")

        hook = self.repo.main / ".git" / "hooks" / "post-checkout"
        shutil.copyfile(ROOT / "scripts" / "hooks" / "post-checkout", hook)
        hook.chmod(0o755)
        self.assertEqual(self._check(self.repo.main)["status"], "PASS")

    def test_generated_tdd_hooks_do_not_require_commit_when_linked(self) -> None:
        from harness.tdd_hooks import generated_files_git_state

        wt = self.repo.add_worktree()
        worktree_files.sync(wt)

        state = generated_files_git_state(wt)
        self.assertFalse(state["generated_files_commit_required"], state)


if __name__ == "__main__":
    unittest.main()
