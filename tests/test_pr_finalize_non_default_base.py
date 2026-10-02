"""pr-finalize default-branch merge guard와 post-merge worktree 회귀 테스트."""
from __future__ import annotations

import json
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

    def test_check_verdict_precedes_every_merge_command(self) -> None:
        """머지 명령은 모두 검사 판정 뒤에 있다 — 필수 검사 지정에 기대지 않는다 (#1248)."""
        verdict = self.script.index("CHECK_VERDICT=$(check_verdict)")
        merge_calls = [
            i for i in range(len(self.script))
            if self.script.startswith('gh pr merge "$PR"', i)
        ]
        self.assertTrue(merge_calls)
        for index in merge_calls:
            self.assertLess(verdict, index)

        git_spec = (REPO_ROOT / "docs" / "plugin" / "git-spec.md").read_text(
            encoding="utf-8"
        )
        procedure = git_spec[git_spec.index("`pr-finalize.sh` 내부:"):]
        self.assertLess(
            procedure.index("gh pr checks --watch"), procedure.index("gh pr merge --auto --merge")
        )

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
        buckets: list[str] | None = ("pass",),
        rollup_len: int = 1,
    ) -> Path:
        """`gh` 대역. buckets 로 PR 검사 결과를 바꾸고, 호출 인자를 gh.log 에 남긴다.

        buckets=None 은 `gh pr checks --json` 이 검사 목록을 돌려주지 못하는 경우다.
        실제 gh 는 검사가 0개일 때 이렇게 실패하므로, rollup_len=0 과 함께 쓰면
        「검사 없음」 저장소를 재현한다 (#1228).
        """
        checks_json = bin_dir / "checks.json"
        if buckets is None:
            checks_branch = (
                "  'pr checks 123 --json bucket')"
                " echo \"no checks reported on the 'feature/a' branch\" >&2; exit 1 ;;\n"
            )
            watch_exit = 1
        else:
            checks_json.write_text(
                json.dumps([{"bucket": b, "name": f"check-{i}"} for i, b in enumerate(buckets)]),
                encoding="utf-8",
            )
            checks_branch = f"  'pr checks 123 --json bucket') cat '{checks_json}' ;;\n"
            watch_exit = 0 if all(b in ("pass", "skipping") for b in buckets) else 1
        gh_log = bin_dir / "gh.log"
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            f"echo \"$*\" >> '{gh_log}'\n"
            "case \"$*\" in\n"
            "  'repo view --json defaultBranchRef -q .defaultBranchRef.name') echo main ;;\n"
            "  'pr view 123 --json baseRefName -q .baseRefName') echo main ;;\n"
            "  'pr view 123 --json headRefName -q .headRefName') echo feature/a ;;\n"
            "  'pr view 123 --json headRefOid -q .headRefOid') echo abc123 ;;\n"
            "  'pr view 123 --json state -q .state') echo MERGED ;;\n"
            "  'pr view 123 --json url -q .url') echo https://example.test/pull/123 ;;\n"
            "  'pr view 123 --json statusCheckRollup -q .statusCheckRollup|length')"
            f" echo {rollup_len} ;;\n"
            "  'pr merge 123 '*) exit 0 ;;\n"
            + checks_branch +
            f"  'pr checks 123 --watch') exit {watch_exit} ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return gh_log

    def _run_finalize(self, cwd: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        return subprocess.run(
            [str(SCRIPT_PATH), "123"],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=90,
        )

    def test_no_reported_checks_does_not_block_sync_and_cleanup(self) -> None:
        """검사가 0개면 `gh pr checks` 가 실패해도 머지와 동기화를 진행한다 (#1228)."""
        with tempfile.TemporaryDirectory() as td:
            root, feature, _origin, origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            gh_log = self._write_fake_gh(bin_dir, buckets=None, rollup_len=0)

            result = self._run_finalize(feature, bin_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("pr merge 123", gh_log.read_text(encoding="utf-8"))
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

    def test_passing_checks_merge_the_checked_head_commit(self) -> None:
        """검사 결과를 먼저 확인하고, 확인한 head commit 에 고정해 머지한다."""
        with tempfile.TemporaryDirectory() as td:
            _root, feature, _origin, _origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            gh_log = self._write_fake_gh(bin_dir, buckets=["pass", "skipping"], rollup_len=2)

            result = self._run_finalize(feature, bin_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = gh_log.read_text(encoding="utf-8").splitlines()
            merge_calls = [c for c in calls if c.startswith("pr merge 123")]
            self.assertTrue(merge_calls)
            for call in merge_calls:
                self.assertIn("--match-head-commit abc123", call)
            first_merge = calls.index(merge_calls[0])
            self.assertIn("pr checks 123 --json bucket", calls[:first_merge])

    def test_failed_or_cancelled_checks_never_reach_merge_command(self) -> None:
        """필수 검사 지정이 없어도 검사가 실패·취소면 머지 명령을 부르지 않는다 (#1248)."""
        for buckets in (["pass", "fail"], ["pass", "cancel"], ["pass", "unexpected"]):
            with self.subTest(buckets=buckets), tempfile.TemporaryDirectory() as td:
                root, feature, _origin, origin_head = self._init_repo_with_remote_ahead(td)
                before = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, text=True
                ).strip()
                bin_dir = Path(td) / "bin"
                bin_dir.mkdir()
                gh_log = self._write_fake_gh(bin_dir, buckets=buckets, rollup_len=len(buckets))

                result = self._run_finalize(feature, bin_dir)

                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("pr merge", gh_log.read_text(encoding="utf-8"))
                self.assertIn("머지하지 않았습니다", result.stderr)
                self.assertTrue(feature.exists())
                self.assertEqual(
                    subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                    before,
                )
                self.assertNotEqual(before, origin_head)

    def test_base_changed_during_check_wait_blocks_merge(self) -> None:
        """검사 대기 중 base 가 바뀌면 head 가 같아도 머지하지 않는다."""
        with tempfile.TemporaryDirectory() as td:
            _root, feature, _origin, _origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            gh_log = self._write_fake_gh(bin_dir)
            gh = bin_dir / "gh"
            # 검사 판정 전에는 main, 검사 판정 뒤에는 다른 브랜치를 base 로 보고한다.
            gh.write_text(
                gh.read_text(encoding="utf-8").replace(
                    "'pr view 123 --json baseRefName -q .baseRefName') echo main ;;",
                    "'pr view 123 --json baseRefName -q .baseRefName')\n"
                    f"    if grep -q 'pr checks 123 --json bucket' '{gh_log}'; then"
                    " echo feature/parent; else echo main; fi ;;",
                ),
                encoding="utf-8",
            )

            result = self._run_finalize(feature, bin_dir)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("feature/parent", result.stderr)
            self.assertNotIn("pr merge", gh_log.read_text(encoding="utf-8"))

    def test_unreadable_check_result_fails_closed_before_merge(self) -> None:
        """검사가 있다고 보고되는데 결과 목록을 읽지 못하면 머지하지 않는다."""
        with tempfile.TemporaryDirectory() as td:
            _root, feature, _origin, _origin_head = self._init_repo_with_remote_ahead(td)
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            gh_log = self._write_fake_gh(bin_dir, buckets=None, rollup_len=2)

            result = self._run_finalize(feature, bin_dir)

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("pr merge", gh_log.read_text(encoding="utf-8"))
            self.assertIn("머지하지 않았습니다", result.stderr)

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
