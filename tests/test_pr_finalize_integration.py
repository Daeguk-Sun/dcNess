"""pr-finalize 통합 브랜치 sub-PR 처리 테스트.

base ≠ default branch 인 sub-PR 에서 (1) CI 체크 0개를 정상으로 처리하고
(2) 머지 후 PR body 의 close 선언 기반 issue close 보정이 와이어링됐는지 확인한다.
(기존 test_pr_finalize_peer_lock.py 와 같은 content-assertion 패턴.)
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "pr-finalize.sh"


class PrFinalizeIntegrationBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_script_syntax_valid(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_detects_integration_base_via_default_branch_ref(self) -> None:
        self.assertIn("defaultBranchRef", self.script)
        self.assertIn("baseRefName", self.script)
        self.assertIn("INTEGRATION=true", self.script)

    def test_zero_checks_pass_only_in_integration_mode(self) -> None:
        # check-run 0개 재확인은 통합 브랜치 모드 분기 안에서만 일어난다.
        self.assertIn("check-runs", self.script)
        self.assertIn('CHECK_COUNT" = "0"', self.script)
        idx_integration_guard = self.script.index('[ "$INTEGRATION" = "true" ]')
        idx_check_runs = self.script.index("check-runs")
        self.assertLess(idx_integration_guard, idx_check_runs)

    def test_close_compensation_uses_pr_body_declarations(self) -> None:
        # close 보정은 PR body 의 Closes/Fixes/Resolves 선언만 근거로 한다 —
        # Part of 는 매치되지 않아야 한다 (선언 없는 issue 임의 close 금지).
        self.assertIn("extract_close_issue_numbers", self.script)
        self.assertIn("gh issue close", self.script)
        self.assertIn("close[sd]?", self.script)
        self.assertIn("resolve[sd]?", self.script)
        self.assertNotIn("Part of", self.script.split("gh issue close")[0].split("CLOSE_NUMS=")[-1])
        self.assertIn("issue close 보정 대상", self.script)

    def test_close_keyword_extraction_ignores_part_of(self) -> None:
        body = (
            "본문에서 `Closes #333` 라고 예시를 들었다.\n"
            "> Closes #444\n"
            "- Closes #555\n"
            "Closes #219\n"
            "task-index: 3/3\n"
            "Part of #220\n"
            "Fixes #11, #12\n"
            "Resolved #13\n"
        )
        pipeline = (
            "awk '{ line = $0; lower = tolower(line); "
            "if (lower ~ /^[[:space:]]*(close[sd]?|fix(e[sd])?|resolve[sd]?)[[:space:]]+#[0-9]+([,[:space:]]+#?[0-9]+)*[[:space:]]*$/) "
            "{ while (match(line, /#[0-9]+/)) { print substr(line, RSTART + 1, RLENGTH - 1); line = substr(line, RSTART + RLENGTH) } } }'"
            " | sort -un"
        )
        result = subprocess.run(
            ["bash", "-c", f"printf '%s' \"$1\" | {pipeline}", "_", body],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.split(), ["11", "12", "13", "219"])

    def test_pr_finalize_documents_invocation_as_merge_commitment(self) -> None:
        self.assertIn("pr-finalize 호출 = 머지 확정", self.script)
        git_spec = (REPO_ROOT / "docs" / "plugin" / "git-spec.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("pr-finalize 호출 = 머지 확정", git_spec)

    def test_close_only_when_issue_open(self) -> None:
        self.assertIn('ISSUE_STATE" = "OPEN"', self.script)

    def test_fetches_integration_base_after_merge(self) -> None:
        self.assertIn('git fetch origin "$BASE_REF"', self.script)
        self.assertIn('git fetch origin "$DEFAULT_REF"', self.script)

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
            REPO_ROOT / "skills" / "impl-loop" / "SKILL.md",
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
    def _write_fake_gh(self, bin_dir: Path) -> None:
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  'repo view --json defaultBranchRef -q .defaultBranchRef.name') echo main ;;\n"
            "  'pr view 123 --json baseRefName -q .baseRefName') echo main ;;\n"
            "  'pr view 123 --json headRefName -q .headRefName') echo feature/a ;;\n"
            "  'pr view 123 --json state -q .state') echo MERGED ;;\n"
            "  'pr view 123 --json url -q .url') echo https://example.test/pull/123 ;;\n"
            "  'pr merge 123 --auto --merge') exit 0 ;;\n"
            "  'pr checks 123 --watch') exit 0 ;;\n"
            "  'pr checks 123') exit 0 ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)

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
