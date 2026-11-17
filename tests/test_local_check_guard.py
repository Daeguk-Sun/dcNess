"""로컬 lint-build-test 우회 차단 계약.

`.dcness/lint-build-test.sh` 가 설치된 프로젝트에서 Claude 가 pre-push hook 을
건너뛰거나 끄는 명령을 실행하기 전에 file-guard 가 막는다.
"""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from harness import hooks, local_check_guard
from harness.ci_workflows import LOCAL_SCRIPT
from harness.hooks import handle_pretooluse_file_op, handle_session_start


class _Repo:
    def __init__(self, *, local: bool = True) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        if local:
            script = self.root / LOCAL_SCRIPT
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")

    def close(self) -> None:
        self._tmp.cleanup()


class BashCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _Repo()

    def tearDown(self) -> None:
        self.repo.close()

    def _bash(self, command: str):
        return local_check_guard.check_tool(
            "Bash", {"command": command}, cwd=self.repo.root
        )

    def test_blocks_push_no_verify_and_its_abbreviation(self) -> None:
        for command in (
            "git push --no-verify origin feature/x",
            "git push -u origin feature/x --no-verify",
            "git push --no-veri",
            "cd sub && git push --no-verify",
            "sudo git -C . push --no-verify",
            "bash -c 'git push --no-verify'",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self._bash(command))

    def test_allows_normal_push_and_dry_run(self) -> None:
        for command in (
            "git push -u origin feature/x",
            "git push -n origin feature/x",
            "git commit --no-verify -m x",
            "echo 'git push --no-verify'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self._bash(command))

    def test_blocks_hooks_path_override(self) -> None:
        for command in (
            "git -c core.hooksPath=/dev/null push",
            "git -c CORE.HOOKSPATH=x push",
            "git --config-env=core.hooksPath=X push",
            "git config core.hooksPath .nohooks",
            "git config --unset core.hooksPath",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self._bash(command))

    def test_allows_reading_hooks_path(self) -> None:
        self.assertIsNone(self._bash("git config --get core.hooksPath"))

    def test_blocks_writes_to_git_hooks(self) -> None:
        for command in (
            "rm .git/hooks/pre-push",
            "mv .git/hooks/pre-push /tmp/x",
            "echo exit 0 > .git/hooks/pre-push",
            f"rm {self.repo.root}/.git/hooks/pre-push",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self._bash(command))

    def test_allows_reading_git_hooks(self) -> None:
        self.assertIsNone(self._bash("cat .git/hooks/pre-push"))


class FileToolTests(unittest.TestCase):
    def test_blocks_edit_and_write_of_git_hooks(self) -> None:
        repo = _Repo()
        try:
            for tool in ("Edit", "Write"):
                with self.subTest(tool=tool):
                    reason = local_check_guard.check_tool(
                        tool,
                        {"file_path": str(repo.root / ".git" / "hooks" / "pre-push")},
                        cwd=repo.root,
                    )
                    self.assertIsNotNone(reason)
            self.assertIsNone(
                local_check_guard.check_tool(
                    "Write", {"file_path": str(repo.root / "src" / "a.kt")}, cwd=repo.root
                )
            )
        finally:
            repo.close()


class ScopeTests(unittest.TestCase):
    def test_project_without_local_script_is_not_checked(self) -> None:
        repo = _Repo(local=False)
        try:
            self.assertIsNone(
                local_check_guard.check_tool(
                    "Bash", {"command": "git push --no-verify"}, cwd=repo.root
                )
            )
        finally:
            repo.close()


class HookAdapterTests(unittest.TestCase):
    def _run(self, tool: dict, *, agent: str = "", opt_out: bool = False) -> tuple[int, list]:
        repo = _Repo()
        prev = os.getcwd()
        try:
            with TemporaryDirectory() as td:
                base = Path(td)
                handle_session_start({"session_id": "sid-local"}, 12345, base_dir=base)
                payload = {"session_id": "sid-local", **tool}
                if agent:
                    payload["agent_type"] = agent
                os.chdir(repo.root)
                with patch("harness.agent_boundary.is_infra_project", return_value=False), \
                        patch("harness.agent_boundary.is_opt_out", return_value=opt_out), \
                        patch.object(hooks, "_record_guard_hit_safe") as hit:
                    rc = handle_pretooluse_file_op(payload, 12345, base_dir=base)
                return rc, hit.call_args_list
        finally:
            os.chdir(prev)
            repo.close()

    def test_main_push_no_verify_is_blocked_and_recorded(self) -> None:
        rc, hits = self._run(
            {"tool_name": "Bash", "tool_input": {"command": "git push --no-verify"}}
        )
        self.assertEqual(rc, 1)
        self.assertEqual(hits[0].args[:2], ("file-guard", "local_check_bypass"))

    def test_sub_agent_hook_file_write_is_blocked(self) -> None:
        rc, hits = self._run(
            {"tool_name": "Write", "tool_input": {"file_path": ".git/hooks/pre-push"}},
            agent="build-worker",
        )
        self.assertEqual(rc, 1)
        self.assertEqual(hits[0].args[:2], ("file-guard", "local_check_bypass"))

    def test_opt_out_marker_skips_check(self) -> None:
        rc, _ = self._run(
            {"tool_name": "Bash", "tool_input": {"command": "git push --no-verify"}},
            opt_out=True,
        )
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
