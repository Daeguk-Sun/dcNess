"""pr-finalize default-branch merge guard와 post-merge worktree 회귀 테스트."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "pr-finalize.sh"


class PrFinalizeBaseGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_script_syntax_valid(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_non_default_base_before_any_merge_path(self) -> None:
        self.assertIn("defaultBranchRef", self.script)
        self.assertIn("baseRefName", self.script)
        self.assertIn("리타겟·리베이스", self.script)
        self.assertGreaterEqual(self.script.count("require_default_base"), 3)
        guard = self.script.index("require_default_base", self.script.index("CURRENT_WORKTREE="))
        dirty_check = self.script.index("# working tree dirty check")
        merge_call = self.script.index('gh pr merge "$PR" --auto --merge')
        self.assertLess(guard, dirty_check)
        self.assertLess(guard, merge_call)
        self.assertNotIn("extract_close_issue_numbers", self.script)
        self.assertNotIn("gh issue close", self.script)
        self.assertNotIn("check-runs", self.script)

        git_spec = (REPO_ROOT / "docs" / "plugin" / "git-spec.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("base가 default와 다르면 origin/<base>도 fetch", git_spec)

    def test_non_default_base_exits_before_merge_command(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            bin_dir = Path(td) / "bin"
            gh_log = Path(td) / "gh.log"
            root.mkdir()
            bin_dir.mkdir()
            subprocess.run(
                ["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=root, check=True
            )
            (root / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True
            )

            gh = bin_dir / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                "echo \"$*\" >> \"$GH_LOG\"\n"
                "case \"$*\" in\n"
                "  'repo view --json defaultBranchRef -q .defaultBranchRef.name') echo main ;;\n"
                "  'pr view 123 --json baseRefName -q .baseRefName') echo feature/parent ;;\n"
                "  'pr view 123 --json headRefName -q .headRefName') echo feature/child ;;\n"
                "esac\n"
                "exit 0\n",
                encoding="utf-8",
            )
            gh.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "GH_LOG": str(gh_log),
            }

            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("feature/parent", result.stderr)
            self.assertIn("main으로 리타겟", result.stderr)
            self.assertNotIn("pr merge", gh_log.read_text(encoding="utf-8"))

    def test_unresolved_base_fails_closed_before_merge_command(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            bin_dir = Path(td) / "bin"
            gh_log = Path(td) / "gh.log"
            root.mkdir()
            bin_dir.mkdir()
            subprocess.run(
                ["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True
            )
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True
            )

            gh = bin_dir / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                "echo \"$*\" >> \"$GH_LOG\"\n"
                "case \"$*\" in\n"
                "  'repo view --json defaultBranchRef -q .defaultBranchRef.name') echo main ;;\n"
                "  'pr view 123 --json headRefName -q .headRefName') echo feature/child ;;\n"
                "  'pr view 123 --json baseRefName -q .baseRefName') exit 1 ;;\n"
                "  'pr merge 123 --auto --merge') exit 0 ;;\n"
                "  'pr checks 123 --watch') exit 1 ;;\n"
                "esac\n"
                "exit 0\n",
                encoding="utf-8",
            )
            gh.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "GH_LOG": str(gh_log),
            }

            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("base branch 조회 실패", result.stderr)
            self.assertNotIn("pr merge", gh_log.read_text(encoding="utf-8"))

    def test_pr_finalize_documents_invocation_as_merge_commitment(self) -> None:
        self.assertIn("pr-finalize 호출 = 머지 확정", self.script)
        git_spec = (REPO_ROOT / "docs" / "plugin" / "git-spec.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("pr-finalize 호출 = 머지 확정", git_spec)

    def test_post_merge_sync_fast_forwards_existing_default_worktree(self) -> None:
        self.assertIn("sync_default_worktree", self.script)
        self.assertIn("git worktree list --porcelain", self.script)
        self.assertIn('merge --ff-only "origin/$DEFAULT_REF"', self.script)

    def test_post_merge_cleanup_preserves_unsafe_worktrees(self) -> None:
        self.assertIn("cleanup_merged_feature_worktree", self.script)
        self.assertIn("git worktree remove", self.script)
        self.assertIn("dirty default worktree", self.script)
        self.assertIn("non-fast-forward default sync", self.script)
        self.assertNotIn("reset --hard", self.script)
        self.assertNotIn("git stash", self.script)

    def test_user_facing_finalize_paths_use_plugin_root_for_active_projects(self) -> None:
        surfaces = [
            REPO_ROOT / "skills" / "impl-loop" / "impl-loop-finish.md",
            REPO_ROOT / "skills" / "design" / "SKILL.md",
            REPO_ROOT / "skills" / "spec" / "spec-delivery-reference.md",
            REPO_ROOT / "docs" / "plugin" / "git-spec.md",
            REPO_ROOT / "docs" / "plugin" / "loop-procedure.md",
            REPO_ROOT / "docs" / "plugin" / "benchmark.md",
        ]

        for path in surfaces:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                self.assertIn("$PLUGIN_ROOT/scripts/pr-finalize.sh", text)
                self.assertNotIn("bash scripts/pr-finalize.sh", text)


class PrFinalizePostMergeWorktreeTests(unittest.TestCase):
    def _write_fake_gh(
        self,
        bin_dir: Path,
        *,
        checks_exit: int = 0,
        rollup_len: int = 1,
        state: str | None = "MERGED",
    ) -> None:
        """`gh` 대역. checks_exit / rollup_len 으로 CI 상황을 바꾼다.

        `gh pr checks` 는 체크가 하나도 없을 때도 exit 1 이므로, 그 상황은
        checks_exit=1 + rollup_len=0 으로 재현한다 (#1228).
        state=None 은 PR 상태 조회 자체가 실패하는 경우다.
        """
        state_branch = (
            "  'pr view 123 --json state -q .state') exit 1 ;;\n"
            if state is None
            else f"  'pr view 123 --json state -q .state') echo {state} ;;\n"
        )
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  'repo view --json defaultBranchRef -q .defaultBranchRef.name') echo main ;;\n"
            "  'pr view 123 --json baseRefName -q .baseRefName') echo main ;;\n"
            "  'pr view 123 --json headRefName -q .headRefName') echo feature/a ;;\n"
            + state_branch +
            "  'pr view 123 --json url -q .url') echo https://example.test/pull/123 ;;\n"
            "  'pr view 123 --json statusCheckRollup -q .statusCheckRollup|length')"
            f" echo {rollup_len} ;;\n"
            "  'pr merge 123 --auto --merge') exit 0 ;;\n"
            "  'pr checks 123 --watch')\n"
            f"    [ {checks_exit} -eq 0 ] || echo \"no checks reported on the 'feature/a' branch\" >&2\n"
            f"    exit {checks_exit} ;;\n"
            "  'pr checks 123')\n"
            f"    exit {checks_exit} ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)

    def test_no_reported_checks_does_not_block_sync_and_cleanup(self) -> None:
        """체크가 0개면 `gh pr checks` 가 exit 1 이어도 CI 실패가 아니다 (#1228)."""
        with tempfile.TemporaryDirectory() as td:
            root, feature, _origin, origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir, checks_exit=1, rollup_len=0)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=feature,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                origin_head,
            )
            self.assertFalse(feature.exists(), result.stdout + result.stderr)
            self.assertNotIn("CI FAIL", result.stderr)

    def test_cleanup_keeps_the_merged_branch(self) -> None:
        """워크트리만 정리하고 브랜치는 남긴다 — git-spec 의 브랜치 보존 규칙."""
        with tempfile.TemporaryDirectory() as td:
            root, feature, _origin, _origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=feature,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(feature.exists())
            branches = subprocess.check_output(
                ["git", "branch", "--list", "feature/a"], cwd=root, text=True
            )
            self.assertIn("feature/a", branches)

    def test_failing_checks_still_block_sync(self) -> None:
        """체크가 있고 실패가 섞여 있으면 종전대로 중단한다."""
        with tempfile.TemporaryDirectory() as td:
            root, feature, _origin, origin_head = self._init_repo_with_remote_ahead(td)
            before = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir, checks_exit=1, rollup_len=3)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=feature,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CI FAIL", result.stderr)
            self.assertTrue(feature.exists())
            self.assertEqual(
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                before,
            )
            self.assertNotEqual(before, origin_head)

    def test_ci_failure_message_does_not_claim_unmerged_when_already_merged(self) -> None:
        """머지가 끝난 뒤 CI FAIL 로 중단하면 「머지 안 됨」이라고 말하지 않는다."""
        with tempfile.TemporaryDirectory() as td:
            _root, feature, _origin, _origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir, checks_exit=1, rollup_len=3, state="MERGED")

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=feature,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CI FAIL", result.stderr)
            ci_fail_line = next(
                line for line in result.stderr.splitlines() if "CI FAIL" in line
            )
            self.assertNotIn("머지 안 됨", ci_fail_line)
            self.assertIn("MERGED", ci_fail_line)

    def test_ci_failure_message_does_not_claim_unmerged_when_state_unknown(self) -> None:
        """PR 상태를 못 읽으면 머지 여부를 어느 쪽으로도 단정하지 않는다."""
        with tempfile.TemporaryDirectory() as td:
            _root, feature, _origin, _origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir, checks_exit=1, rollup_len=3, state=None)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=feature,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

            self.assertNotEqual(result.returncode, 0)
            ci_fail_line = next(
                line for line in result.stderr.splitlines() if "CI FAIL" in line
            )
            self.assertNotIn("머지 안 됨", ci_fail_line)
            self.assertIn("확인하지 못했습니다", ci_fail_line)

    def _init_repo_with_remote_ahead(self, td: str) -> tuple[Path, Path, Path, str]:
        root = Path(td) / "repo"
        origin = Path(td) / "origin.git"
        updater = Path(td) / "updater"
        feature = Path(td) / "feature-wt"

        root.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=root, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            cwd=origin,
            check=True,
            capture_output=True,
        )

        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "feature/a", str(feature), "main"],
            cwd=root,
            check=True,
        )
        subprocess.run(["git", "clone", "-q", str(origin), str(updater)], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=updater, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=updater, check=True)
        (updater / "README.md").write_text("base\nmerged\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "merged"], cwd=updater, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=updater, check=True, capture_output=True)
        origin_head = subprocess.check_output(
            ["git", "rev-parse", "origin/main"], cwd=updater, text=True
        ).strip()
        return root, feature, origin, origin_head

    def _init_single_feature_worktree_with_remote_ahead(self, td: str) -> tuple[Path, str]:
        root = Path(td) / "repo"
        origin = Path(td) / "origin.git"
        updater = Path(td) / "updater"

        root.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=root, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            cwd=origin,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "switch", "-c", "feature/a"], cwd=root, check=True, capture_output=True)

        subprocess.run(["git", "clone", "-q", str(origin), str(updater)], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=updater, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=updater, check=True)
        (updater / "README.md").write_text("base\nmerged\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "merged"], cwd=updater, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=updater, check=True, capture_output=True)
        origin_head = subprocess.check_output(
            ["git", "rev-parse", "origin/main"], cwd=updater, text=True
        ).strip()
        return root, origin_head

    def test_syncs_default_worktree_and_removes_clean_feature_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root, feature, _origin, origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=feature,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                origin_head,
            )
            self.assertFalse(feature.exists(), result.stdout + result.stderr)
            self.assertIn("default_path=", result.stdout)
            self.assertIn("cleaned=", result.stdout)

    def test_switches_clean_current_worktree_when_no_default_worktree_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root, origin_head = self._init_single_feature_worktree_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip(),
                "main",
            )
            self.assertEqual(
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                origin_head,
            )
            self.assertIn("default_path=", result.stdout)

    def test_explicit_pr_uses_head_ref_when_called_from_default_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root, feature, _origin, origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                origin_head,
            )
            self.assertFalse(feature.exists(), result.stdout + result.stderr)
            self.assertIn("feature-wt: removed merged feature worktree", result.stdout)

    def test_dirty_default_worktree_is_preserved_without_force_sync(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root, feature, _origin, origin_head = self._init_repo_with_remote_ahead(td)
            before_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            (root / "local-note.txt").write_text("do not overwrite\n", encoding="utf-8")
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            self._write_fake_gh(bin_dir)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(SCRIPT_PATH), "123"],
                cwd=feature,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                before_head,
            )
            self.assertNotEqual(before_head, origin_head)
            self.assertTrue((root / "local-note.txt").exists())
            self.assertIn("dirty default worktree", result.stdout + result.stderr)
            self.assertIn("preserved=", result.stdout)


if __name__ == "__main__":
    unittest.main()
