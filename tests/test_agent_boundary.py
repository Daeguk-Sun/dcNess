"""tests/test_agent_boundary.py — DCN-CHG-20260501-01 path 보호 단위 테스트.

agent_boundary.py 권한 경계 (ALLOW_MATRIX / READ_DENY / INFRA / infra-project)
spec 의 코드 강제 검증.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness.agent_boundary import (  # noqa: E402
    ALLOW_MATRIX,
    DCNESS_INFRA_PATTERNS,
    READ_DENY_MATRIX,
    check_bash_mutation,
    check_github_mcp_mutation,
    check_read_allowed,
    check_write_allowed,
    extract_bash_paths,
    is_infra_project,
    is_opt_out,
)


class IsInfraProjectTests(unittest.TestCase):
    def test_env_dcness_infra(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertTrue(is_infra_project(cwd, env={"DCNESS_INFRA": "1"}, home=Path(td)))

    def test_env_plugin_root_NOT_infra(self):
        # #597 P0-2 — CLAUDE_PLUGIN_ROOT 는 더 이상 infra 신호가 아니다.
        # 이 env 는 모든 plugin hook 실행 시 CC 가 자동 set 하므로 (외부 활성 프로젝트
        # sub-agent 포함), infra 신호로 쓰면 file-guard 가 전면 무력화된다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)  # dcness self repo 마커 없음 = 외부 프로젝트
            self.assertFalse(
                is_infra_project(cwd, env={"CLAUDE_PLUGIN_ROOT": "/x"}, home=Path(td))
            )

    def test_marker_file(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / ".claude").mkdir()
            (home / ".claude" / ".dcness-infra").write_text("")
            self.assertTrue(is_infra_project(home, env={}, home=home))

    def test_self_repo_marker(self):
        # cwd 조상에 .claude-plugin/plugin.json (name=dcness) 실재 → infra.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "dcness", "version": "0.3.0"})
            )
            self.assertTrue(is_infra_project(root, env={}, home=Path("/tmp")))
            # 중첩 하위 디렉토리에서도 walk-up 으로 마커 발견.
            nested = root / "harness" / "deep"
            nested.mkdir(parents=True)
            self.assertTrue(is_infra_project(nested, env={}, home=Path("/tmp")))

    def test_self_repo_marker_wrong_name(self):
        # name != dcness 매니페스트 → 오탐 방지 (외부 plugin 저장소).
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "some-other-plugin"})
            )
            self.assertFalse(is_infra_project(root, env={}, home=Path("/tmp")))

    def test_user_project_not_infra(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)  # 마커 없음 — 외부 사용자 프로젝트
            self.assertFalse(is_infra_project(cwd, env={}, home=Path(td)))

    def test_no_personal_path_hardcoded(self):
        # 회귀 가드 (#523): 배포되는 agent_boundary.py 소스에 개인 절대경로 0건.
        src = (REPO_ROOT / "harness" / "agent_boundary.py").read_text(encoding="utf-8")
        self.assertNotIn("/Users/", src)


class PluginRootDoesNotBypassTests(unittest.TestCase):
    """#597 P0-2 회귀 — CLAUDE_PLUGIN_ROOT set 이어도 외부 프로젝트 boundary 는 강제된다.

    실제 외부 활성 프로젝트 sub-agent 환경: CC 가 CLAUDE_PLUGIN_ROOT 를 자동 set 한다.
    이 신호로 infra 우회되던 버그(P0-2)를 제거했으므로, infra path edit 가 차단되어야 한다.
    """

    def test_external_project_engineer_blocked_on_infra_despite_plugin_root(self):
        with patch.dict(os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": "/x"}):
            with tempfile.TemporaryDirectory() as td:
                cwd = Path(td)  # dcness self repo 마커 없음 = 외부 프로젝트
                reason = check_write_allowed("engineer", "hooks/x.sh", cwd=cwd)
                self.assertIsNotNone(
                    reason, "CLAUDE_PLUGIN_ROOT 가 set 이어도 외부 프로젝트는 차단되어야 함"
                )
                self.assertIn("인프라", reason)

    def test_dcness_self_repo_still_bypasses(self):
        # dcness self 저장소(신호 3 = self repo 마커 조상)는 CLAUDE_PLUGIN_ROOT 없이도 infra 유지.
        with patch.dict(os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / ".claude-plugin").mkdir()
                (root / ".claude-plugin" / "plugin.json").write_text(
                    json.dumps({"name": "dcness", "version": "0.3.0"})
                )
                self.assertIsNone(
                    check_write_allowed("engineer", "hooks/x.sh", cwd=root)
                )


class WriteAllowedMainBypassTests(unittest.TestCase):
    """메인 Claude (active_agent 없음) = 통과."""

    def test_main_bypass(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(check_write_allowed(None, "hooks/x.sh", cwd=cwd))
            self.assertIsNone(
                check_write_allowed(
                    "", "skills/architect-loop/architect-loop-routing.md", cwd=cwd
                )
            )


class WriteAllowedInfraProjectBypassTests(unittest.TestCase):
    """is_infra_project=True 인 cwd = 통과 (dcness 자체 SSOT 편집)."""

    def test_infra_project_bypass(self):
        with patch.dict(os.environ, {"DCNESS_INFRA": "1"}):
            with tempfile.TemporaryDirectory() as td:
                cwd = Path(td)
                self.assertIsNone(
                    check_write_allowed("engineer", "hooks/x.sh", cwd=cwd)
                )
                self.assertIsNone(
                    check_write_allowed(
                        "engineer",
                        "skills/architect-loop/architect-loop-routing.md",
                        cwd=cwd,
                    )
                )


class WriteAllowedInfraPatternBlockTests(unittest.TestCase):
    """user 프로젝트 (infra=False) — INFRA_PATTERN 매칭 시 차단."""

    def setUp(self):
        # 모든 infra 신호 해제.
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_engineer_blocked_on_hooks(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("engineer", "hooks/foo.sh", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_architect_blocked_on_skill_routing(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed(
                "architect",
                "skills/architect-loop/architect-loop-routing.md",
                cwd=cwd,
            )
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_engineer_blocked_on_governance(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed(
                "engineer", "docs/internal/governance.md", cwd=cwd
            )
            self.assertIsNotNone(reason)

    def test_module_architect_blocked_on_claude_md(self):
        # #463 회귀 — module-architect 가 외부 활성 프로젝트의 CLAUDE.md 직접 수정.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed(
                "module-architect", "CLAUDE.md", cwd=cwd
            )
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_engineer_blocked_on_claude_md(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed(
                "engineer", "CLAUDE.md", cwd=cwd
            )
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_subdir_claude_md_not_matched(self):
        # repo root CLAUDE.md 만 차단. subdir 의 동명 파일은 매치 X.
        # (단 ALLOW_MATRIX 미매칭으로 다른 차단은 가능 — 본 테스트는 INFRA 패턴 한정.)
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed(
                "engineer", "node_modules/foo/CLAUDE.md", cwd=cwd
            )
            # INFRA 매칭은 아니어야 함 (root 직속만 매치).
            if reason is not None:
                self.assertNotIn("인프라", reason)


class WriteAllowedAllowMatrixTests(unittest.TestCase):
    """user 프로젝트 — ALLOW_MATRIX 매칭/미매칭."""

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_engineer_src_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("engineer", "src/foo.ts", cwd=cwd)
            )

    def test_engineer_blocked_on_random(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("engineer", "README.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

    def test_architect_docs_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("architect", "docs/architecture.md", cwd=cwd)
            )

    def test_code_validator_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("code-validator", "src/foo.ts", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

    def test_architecture_validator_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("architecture-validator", "docs/architecture.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

    def test_module_architect_docs_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("module-architect", "docs/impl/01-foo.md", cwd=cwd)
            )

    def test_module_architect_random_blocked(self):
        # #463 — module-architect 키 명시 후 ALLOW 외 path 는 차단되어야 (silent pass 회귀 방지).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("module-architect", "src/foo.ts", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

    def test_system_architect_docs_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("system-architect", "docs/architecture.md", cwd=cwd)
            )

    def test_unknown_agent_passes(self):
        # 미정의 agent → false positive 회피로 통과.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("custom-agent", "anywhere/x.ts", cwd=cwd)
            )


class AllowMatrixCoverageTests(unittest.TestCase):
    """#597 커밋4 — agents/*.md 전 agent 가 ALLOW_MATRIX key 로 등재 (누락 재발 차단).

    미정의 agent 는 false-positive 회피로 통과한다. 즉 새 mutation agent 가 ALLOW_MATRIX
    에 빠지면 경계가 *조용히* 무력화된다 (build-worker / tech-reviewer 가 그랬던 결함).
    본 테스트는 agents 디렉토리의 모든 frontmatter name 을 ALLOW_MATRIX key 와 대조한다.
    """

    def _agent_names(self):
        import re
        names = []
        for md in (REPO_ROOT / "agents").glob("*.md"):
            text = md.read_text(encoding="utf-8")
            m = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
            if m:
                names.append(m.group(1).strip().strip("'\""))
        return names

    def test_all_agents_have_allow_matrix_key(self):
        names = self._agent_names()
        self.assertGreaterEqual(len(names), 12, "agents/*.md 파싱 실패 의심")
        missing = [n for n in names if n not in ALLOW_MATRIX]
        self.assertEqual(
            missing, [],
            f"ALLOW_MATRIX 누락 agent: {missing} — 미정의 agent 는 경계가 무력화됨",
        )

    def test_build_worker_is_engineer_test_engineer_union(self):
        self.assertEqual(
            set(ALLOW_MATRIX["build-worker"]),
            set(ALLOW_MATRIX["engineer"]) | set(ALLOW_MATRIX["test-engineer"]),
        )


class RunDirProseCarveOutTests(unittest.TestCase):
    """#597 커밋4 — build-worker run_dir prose self-write 허용 + 임의 .claude/ 차단."""

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_build_worker_run_dir_prose_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for fname in ("build-test.md", "build-impl.md", "build-validate.md"):
                p = f".claude/harness-state/.sessions/SID123/runs/run-abcd1234/{fname}"
                self.assertIsNone(
                    check_write_allowed("build-worker", p, cwd=cwd),
                    f"run_dir prose {fname} self-write 가 허용되어야 함",
                )

    def test_build_worker_arbitrary_claude_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # run_dir 밖의 임의 .claude/ write 는 여전히 차단 (carve-out 은 run_dir prose 한정).
            reason = check_write_allowed(
                "build-worker", ".claude/settings.json", cwd=cwd
            )
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_run_dir_non_md_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # run_dir 안이라도 .md 아닌 파일은 carve-out 밖 → INFRA 차단.
            reason = check_write_allowed(
                "build-worker",
                ".claude/harness-state/.sessions/SID/runs/run-x/live.json",
                cwd=cwd,
            )
            self.assertIsNotNone(reason)

    def test_non_build_worker_cannot_forge_validator_pass(self):
        # codex P1 — engineer 등 임의 agent 가 run_dir 에 validator PASS 마커 위조 시도 → 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for marker in (
                "module-architect.md",
                "code-validator.md",
                "architecture-validator.md",
            ):
                p = f".claude/harness-state/.sessions/SID/runs/run-x/{marker}"
                reason = check_write_allowed("engineer", p, cwd=cwd)
                self.assertIsNotNone(
                    reason, f"engineer 가 {marker} 위조 → 차단되어야 함 (catastrophic gate 우회 방지)"
                )

    def test_build_worker_cannot_forge_validator_pass(self):
        # build-worker 라도 build-*.md 외 run_dir 파일(validator 마커)은 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            p = ".claude/harness-state/.sessions/SID/runs/run-x/code-validator.md"
            reason = check_write_allowed("build-worker", p, cwd=cwd)
            self.assertIsNotNone(reason)

    def test_build_worker_src_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(check_write_allowed("build-worker", "src/a.ts", cwd=cwd))
            self.assertIsNone(
                check_write_allowed("build-worker", "src/__tests__/a.test.ts", cwd=cwd)
            )

    def test_build_worker_docs_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("build-worker", "docs/impl/01-x.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

    def test_tech_reviewer_allowed_paths(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("tech-reviewer", "docs/tech-review.md", cwd=cwd)
            )
            self.assertIsNone(
                check_write_allowed(
                    "tech-reviewer", "docs/tech-review/report.html", cwd=cwd
                )
            )

    def test_tech_reviewer_prd_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("tech-reviewer", "docs/prd.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)


class OptOutMarkerTests(unittest.TestCase):
    """`.no-dcness-guard` 마커 — 사용자 임시 우회."""

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_marker_bypasses(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            (cwd / ".no-dcness-guard").write_text("")
            self.assertTrue(is_opt_out(cwd))
            # 우회 — INFRA_PATTERN 매칭이지만 통과.
            self.assertIsNone(
                check_write_allowed("engineer", "hooks/x.sh", cwd=cwd)
            )
            # CLAUDE.md 도 우회 (사용자 임시 우회 정합).
            self.assertIsNone(
                check_write_allowed("module-architect", "CLAUDE.md", cwd=cwd)
            )

    def test_no_marker_no_bypass(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertFalse(is_opt_out(cwd))


class ReadAllowedTests(unittest.TestCase):
    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_main_bypass(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(check_read_allowed(None, "hooks/x.sh", cwd=cwd))

    def test_infra_pattern_blocks_read(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_read_allowed(
                "product-planner", "hooks/file-guard.sh", cwd=cwd
            )
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_engineer_read_src_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_read_allowed("engineer", "src/main.ts", cwd=cwd)
            )


class BashHeuristicTests(unittest.TestCase):
    def test_no_indicator_returns_empty(self):
        self.assertEqual(extract_bash_paths("ls -la docs/"), [])
        self.assertEqual(extract_bash_paths("cat README.md"), [])

    def test_sed_in_place_extracts(self):
        paths = extract_bash_paths("sed -i 's/x/y/' docs/foo.md")
        self.assertIn("docs/foo.md", paths)

    def test_redirect_extracts(self):
        paths = extract_bash_paths("echo hi > hooks/evil.sh")
        self.assertIn("hooks/evil.sh", paths)

    def test_cp_extracts(self):
        paths = extract_bash_paths("cp src/a.ts hooks/b.sh")
        self.assertIn("hooks/b.sh", paths)

    def test_perl_in_place(self):
        paths = extract_bash_paths("perl -i -pe 's/a/b/' docs/x.md")
        self.assertIn("docs/x.md", paths)

    def test_url_not_extracted_as_write_path(self):
        # codex P2 (round9) — `curl URL > local.json` 의 URL 은 로컬 write 대상이 아님 → 후보 제외.
        # `/` 포함이라는 이유로 write path 로 오인돼 정상 명령이 차단되던 false positive 수정 검증.
        paths = extract_bash_paths(
            "curl -s https://example.com/api/v1 > docs/tech-review/evidence/x.json"
        )
        self.assertNotIn("https://example.com/api/v1", paths)
        self.assertIn("docs/tech-review/evidence/x.json", paths)

    def test_sed_script_not_extracted_as_path(self):
        # codex P2 (round10) — `sed -i 's/foo/bar/' src/main.ts` 의 치환 스크립트는
        # 명령 syntax → path 후보 아님. 실제 대상(src/main.ts)만 남아야 정상 편집이 안 막힘.
        paths = extract_bash_paths("sed -i 's/foo/bar/' src/main.ts")
        self.assertNotIn("s/foo/bar/", paths)
        self.assertIn("src/main.ts", paths)
        # 따옴표 없이 쓴 치환 스크립트도 제외.
        paths2 = extract_bash_paths("sed -i s/foo/bar/ src/main.ts")
        self.assertNotIn("s/foo/bar/", paths2)
        self.assertIn("src/main.ts", paths2)


class BashMutationTests(unittest.TestCase):
    """#597 커밋5 — check_bash_mutation: git push / gh mutation 차단, read-only 통과."""

    def test_git_push_blocked(self):
        self.assertIsNotNone(check_bash_mutation("git push -u origin feature/x"))
        self.assertIsNotNone(check_bash_mutation("git add . && git push"))

    def test_git_non_push_passes(self):
        self.assertIsNone(check_bash_mutation("git add ."))
        self.assertIsNone(check_bash_mutation("git status"))
        self.assertIsNone(check_bash_mutation("git commit -m 'x'"))

    def test_gh_pr_mutation_blocked(self):
        self.assertIsNotNone(check_bash_mutation("gh pr create --title x --body y"))
        self.assertIsNotNone(check_bash_mutation("gh pr merge 123 --merge"))

    def test_gh_pr_review_blocked(self):
        # codex P2 (round3) — gh pr review 는 PR 리뷰 제출 = mutation.
        self.assertIsNotNone(check_bash_mutation("gh pr review 123 --approve"))
        self.assertIsNotNone(
            check_bash_mutation("gh pr review 5 --request-changes --body x")
        )

    def test_heredoc_opener_suffix_still_scanned(self):
        # codex P2 (round3) — opener 라인의 `&& git push` 는 실행 syntax → 보존·차단.
        cmd = "cat > f <<'EOF' && git push origin main\nbody line\nEOF\n"
        self.assertIsNotNone(check_bash_mutation(cmd))

    def test_gh_issue_mutation_blocked(self):
        self.assertIsNotNone(check_bash_mutation("gh issue create --title x"))
        self.assertIsNotNone(check_bash_mutation("gh issue edit 5 --body y"))
        self.assertIsNotNone(check_bash_mutation("gh issue close 5"))
        self.assertIsNotNone(check_bash_mutation("gh issue comment 5 --body hi"))

    def test_gh_readonly_passes(self):
        self.assertIsNone(check_bash_mutation("gh pr view 123"))
        self.assertIsNone(check_bash_mutation("gh issue list --state open"))
        self.assertIsNone(check_bash_mutation("gh pr checks --watch"))
        self.assertIsNone(check_bash_mutation("gh api repos/o/r/issues"))

    def test_gh_api_mutation_method_blocked(self):
        self.assertIsNotNone(check_bash_mutation("gh api -X POST repos/o/r/issues"))
        self.assertIsNotNone(
            check_bash_mutation("gh api --method PATCH repos/o/r/issues/1")
        )
        self.assertIsNotNone(
            check_bash_mutation("gh api --method=DELETE repos/o/r/x")
        )

    def test_gh_api_field_flag_blocked(self):
        # codex P1 — field flag 는 method 미지정 시 POST 기본 → 차단.
        self.assertIsNotNone(check_bash_mutation("gh api repos/o/r/issues -f title=x"))
        self.assertIsNotNone(
            check_bash_mutation("gh api repos/o/r/issues -F labels[]=bug")
        )
        self.assertIsNotNone(
            check_bash_mutation("gh api --field title=x repos/o/r/issues")
        )

    def test_gh_api_explicit_get_with_field_passes(self):
        # 명시적 GET 이면 field 있어도 read.
        self.assertIsNone(
            check_bash_mutation("gh api -X GET repos/o/r/issues -f per_page=5")
        )

    def test_global_flags_before_subcommand_blocked(self):
        # codex P2 — global flag 가 noun/verb 앞에 와도 정확히 식별.
        self.assertIsNotNone(check_bash_mutation("git -C /repo push"))
        self.assertIsNotNone(check_bash_mutation("gh -R owner/repo issue create --title x"))
        self.assertIsNotNone(
            check_bash_mutation("gh --repo owner/repo pr merge 5 --merge")
        )

    def test_global_flags_readonly_still_passes(self):
        self.assertIsNone(check_bash_mutation("git -C /repo status"))
        self.assertIsNone(check_bash_mutation("gh -R owner/repo issue list"))

    def test_absolute_executable_path_blocked(self):
        # #601 — absolute path 로 실행해도 basename 정규화 후 git/gh mutation 식별.
        self.assertIsNotNone(check_bash_mutation("/usr/bin/git push origin main"))
        self.assertIsNotNone(
            check_bash_mutation("/opt/homebrew/bin/gh pr create --title x")
        )

    def test_absolute_executable_path_readonly_passes(self):
        self.assertIsNone(check_bash_mutation("/usr/bin/git status"))
        self.assertIsNone(check_bash_mutation("/opt/homebrew/bin/gh issue list"))

    def test_env_prefix_stripped(self):
        # `FOO=bar git push` 도 토큰 프리픽스 제거 후 git push 로 인식.
        self.assertIsNotNone(check_bash_mutation("GIT_TRACE=1 git push"))

    def test_empty_and_plain_pass(self):
        self.assertIsNone(check_bash_mutation(""))
        self.assertIsNone(check_bash_mutation("ls -la && cat README.md"))

    def test_quoted_mutation_not_false_positive(self):
        # codex P2 (round8) — 따옴표 안 `&&`/git push 는 데이터 → over-block 안 함.
        self.assertIsNone(
            check_bash_mutation("echo 'npm test && git push' > docs/x.md")
        )
        self.assertIsNone(check_bash_mutation('echo "run: git push" >> notes.md'))

    def test_quoted_args_preserve_real_mutation(self):
        # 인자만 따옴표인 진짜 mutation 은 여전히 차단 (명령부 보존).
        self.assertIsNotNone(check_bash_mutation("git push 'origin' main"))
        self.assertIsNotNone(check_bash_mutation("gh pr create --title 'my title'"))

    def test_value_flag_with_quoted_value_still_blocks(self):
        # codex P2 (round9) — value-flag(`-C`/`-R`) *직후* 따옴표 값이 와도 mutation 식별.
        # round8 의 따옴표 통째 삭제가 `-C` 의 값으로 push 를 소비시켜 미탐되던 자가 회귀 수정 검증.
        self.assertIsNotNone(check_bash_mutation("git -C '/repo' push"))
        self.assertIsNotNone(
            check_bash_mutation('git -C "/path/to/repo" push origin main')
        )
        self.assertIsNotNone(
            check_bash_mutation("gh -R 'owner/repo' issue create --title x")
        )

    def test_value_flag_with_quoted_value_readonly_passes(self):
        # 같은 따옴표-값 형태라도 read-only 는 통과 (over-block 회피).
        self.assertIsNone(check_bash_mutation("git -C '/repo' status"))
        self.assertIsNone(check_bash_mutation("gh -R 'owner/repo' issue list"))

    def test_quoted_verb_and_method_still_blocks(self):
        # codex P2 (round10) — 따옴표 친 verb/method 도 식별 (normal shell quoting).
        # placeholder 치환이 verb/method 를 안 보이게 만들던 회귀 수정 검증.
        self.assertIsNotNone(check_bash_mutation("git 'push' origin main"))
        self.assertIsNotNone(check_bash_mutation("gh 'pr' 'create' --title x"))
        self.assertIsNotNone(check_bash_mutation("gh api -X 'POST' repos/o/r/issues"))
        self.assertIsNotNone(check_bash_mutation('gh api --method "PATCH" repos/o/r/x'))

    def test_quoted_separator_still_no_false_positive(self):
        # round10 따옴표-인지 분리 — 따옴표 안 `&&` 는 여전히 가짜 segment 안 만듦.
        self.assertIsNone(
            check_bash_mutation("echo 'npm test && git push' > docs/x.md")
        )
        self.assertIsNone(check_bash_mutation('git commit -m "fix; gh pr create"'))

    def test_single_ampersand_separator_blocked(self):
        # codex P2 (round8) — 단일 `&`(백그라운드) 뒤 mutation 도 식별.
        self.assertIsNotNone(check_bash_mutation("sleep 1 & git push origin main"))
        self.assertIsNotNone(check_bash_mutation("gh pr create --title x &"))

    def test_heredoc_body_not_treated_as_command(self):
        # codex P2 — heredoc 데이터 안 git/gh 텍스트는 실행 명령 아님 → 차단 X.
        cmd = "cat > deploy.md <<'EOF'\ngit push origin main\ngh issue create --title x\nEOF\n"
        self.assertIsNone(check_bash_mutation(cmd))

    def test_real_push_after_heredoc_still_blocked(self):
        # heredoc 본문만 제거 — heredoc 뒤의 진짜 git push 는 여전히 차단.
        cmd = "cat > f.md <<'EOF'\nhello\nEOF\ngit push origin main\n"
        self.assertIsNotNone(check_bash_mutation(cmd))

    def test_nested_shell_c_mutation_blocked(self):
        # #601 — 흔한 nested shell payload 는 재귀 검사.
        self.assertIsNotNone(
            check_bash_mutation("bash -c 'git push origin main'")
        )
        self.assertIsNotNone(
            check_bash_mutation('sh -c "gh pr create --title x"')
        )
        self.assertIsNotNone(
            check_bash_mutation('zsh -lc "gh api -X POST repos/o/r/issues"')
        )
        self.assertIsNotNone(
            check_bash_mutation('/bin/bash -c "git push origin main"')
        )

    def test_nested_shell_c_readonly_passes(self):
        self.assertIsNone(check_bash_mutation("bash -c 'git status'"))
        self.assertIsNone(check_bash_mutation("bash -c \"echo 'git push'\""))

    def test_eval_mutation_blocked(self):
        self.assertIsNotNone(check_bash_mutation("eval 'git push origin main'"))
        self.assertIsNotNone(
            check_bash_mutation('eval "gh issue create --title x"')
        )
        self.assertIsNotNone(check_bash_mutation("eval git push origin main"))

    def test_eval_readonly_or_data_passes(self):
        self.assertIsNone(check_bash_mutation("eval 'git status'"))
        self.assertIsNone(check_bash_mutation("eval 'echo git push'"))


class GithubMcpMutationTests(unittest.TestCase):
    """#597 커밋5 — check_github_mcp_mutation: PR/repo mutation 차단, read·issue mutation 통과."""

    def test_pr_repo_mutation_blocked(self):
        for t in (
            "mcp__github__merge_pull_request",
            "mcp__github__push_files",
            "mcp__github__create_pull_request",
            "mcp__github__create_or_update_file",
        ):
            self.assertIsNotNone(check_github_mcp_mutation(t), f"{t} 는 차단되어야 함")

    def test_issue_mutation_exempt(self):
        # codex P1 (round4) — issue mutation 은 qa/designer 설계 권한 → 통과.
        for t in (
            "mcp__github__create_issue",
            "mcp__github__update_issue",
            "mcp__github__add_issue_comment",
        ):
            self.assertIsNone(
                check_github_mcp_mutation(t),
                f"{t} 는 qa/designer 설계 권한 — 통과해야 함",
            )

    def test_read_tools_pass(self):
        for t in (
            "mcp__github__get_issue",
            "mcp__github__list_issues",
            "mcp__github__search_code",
            "mcp__github__get_pull_request",
        ):
            self.assertIsNone(check_github_mcp_mutation(t), f"{t} 는 통과해야 함")

    def test_non_github_mcp_passes(self):
        self.assertIsNone(check_github_mcp_mutation("mcp__pencil__batch_design"))
        self.assertIsNone(check_github_mcp_mutation("Edit"))


class BashWrapperBypassTests(unittest.TestCase):
    """#597 codex P2 (round4) — 흔한 래퍼로 감싼 git/gh mutation 도 식별."""

    def test_sudo_wrapped_blocked(self):
        self.assertIsNotNone(check_bash_mutation("sudo git push origin main"))

    def test_env_command_wrapped_blocked(self):
        self.assertIsNotNone(check_bash_mutation("env GH_TOKEN=x gh issue create --title x"))

    def test_subshell_wrapped_blocked(self):
        self.assertIsNotNone(check_bash_mutation("(git push origin main)"))

    def test_if_then_wrapped_blocked(self):
        self.assertIsNotNone(
            check_bash_mutation("if true; then git push origin main; fi")
        )

    def test_nohup_wrapped_blocked(self):
        self.assertIsNotNone(check_bash_mutation("nohup gh pr create --title x"))

    def test_wrapped_readonly_passes(self):
        self.assertIsNone(check_bash_mutation("sudo git status"))
        self.assertIsNone(check_bash_mutation("(gh issue list)"))

    def test_wrapper_options_skipped(self):
        # codex P2 (round5) — 래퍼 자체 옵션(-E/-i/--)이 명령으로 오인되지 않게.
        self.assertIsNotNone(check_bash_mutation("sudo -E git push origin main"))
        self.assertIsNotNone(check_bash_mutation("env -i GH_TOKEN=x gh pr create --title x"))
        self.assertIsNotNone(check_bash_mutation("command -- gh pr create --title x"))

    def test_gh_api_attached_method_blocked(self):
        # codex P2 (round5) — `-XPOST` 붙임 / `-X=DELETE` 형태.
        self.assertIsNotNone(check_bash_mutation("gh api -XPOST repos/o/r/issues"))
        self.assertIsNotNone(check_bash_mutation("gh api -X=DELETE repos/o/r/x"))

    def test_gh_api_attached_field_blocked(self):
        # codex P2 (round7) — `-Ftitle=x` / `-fbody=x` 붙임 short field (POST 기본).
        self.assertIsNotNone(check_bash_mutation("gh api repos/o/r/issues -Ftitle=x"))
        self.assertIsNotNone(check_bash_mutation("gh api repos/o/r/issues -fbody=hi"))


class BashIntegrationTests(unittest.TestCase):
    """Bash heuristic + check_write_allowed 합."""

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_engineer_sed_blocks_infra(self):
        # heuristic 은 보수적 — quoted sed pattern 도 path 후보 포함 (`/` 있음).
        # 어떤 후보든 INFRA 매칭 되면 reason 발화 = OK.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            paths = extract_bash_paths(
                "sed -i 's/x/y/' hooks/catastrophic-gate.sh"
            )
            self.assertIn("hooks/catastrophic-gate.sh", paths)
            blocked = [
                p for p in paths
                if check_write_allowed("engineer", p, cwd=cwd) is not None
            ]
            self.assertTrue(any("hooks/" in p for p in blocked))

    def test_tech_reviewer_curl_evidence_not_blocked(self):
        # codex P2 (round9) — tech-reviewer 의 `curl URL > docs/tech-review/evidence/…` 가
        # URL 오인으로 차단되지 않아야 한다 (commit4 회귀 수정 검증).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            cmd = (
                "curl -s https://pypi.org/pypi/foo/json "
                "> docs/tech-review/evidence/foo.json"
            )
            blocked = [
                p for p in extract_bash_paths(cmd)
                if check_write_allowed("tech-reviewer", p, cwd=cwd) is not None
            ]
            self.assertEqual(
                blocked, [], f"tech-reviewer evidence 수집이 차단됨: {blocked}"
            )

    def test_engineer_sed_legit_edit_not_blocked(self):
        # codex P2 (round10) — engineer 의 정상 `sed -i 's/x/y/' src/…` 가
        # sed 스크립트 오인으로 차단되면 안 됨.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            blocked = [
                p for p in extract_bash_paths("sed -i 's/foo/bar/' src/main.ts")
                if check_write_allowed("engineer", p, cwd=cwd) is not None
            ]
            self.assertEqual(blocked, [], f"engineer 정상 편집이 차단됨: {blocked}")


if __name__ == "__main__":
    unittest.main()
