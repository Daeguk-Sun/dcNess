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
                    "", "skills/design/design-routing.md", cwd=cwd
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
                        "skills/design/design-routing.md",
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
                "skills/design/design-routing.md",
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
            # write-zero agent (빈 ALLOW) — #696 이후 전용 차단 reason.
            self.assertIn("write-zero", reason)

    def test_architecture_validator_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("architecture-validator", "docs/architecture.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("write-zero", reason)

    def test_module_architect_new_docs_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for path in (
                "docs/epics/epic-01-foo/impl/01-foo.md",
                "docs/epics/epic-01-foo/architecture.md",
                "docs/epics/epic-01-foo/domain-model.md",
                "docs/decisions/0001-storage.md",
                "docs/conventions.md",
            ):
                self.assertIsNone(
                    check_write_allowed("module-architect", path, cwd=cwd),
                    f"{path} should be writable by module-architect",
                )

    def test_architect_family_root_flat_epic_outputs_blocked(self):
        # #810 — root-flat epic artifacts are no longer a legacy fallback.
        # Global docs/architecture.md and docs/tech-review.md remain allowed; only
        # root-level epic artifacts and removed ADR locations are denied before the broad docs/ allow.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent in ("architect", "module-architect", "system-architect"):
                for path in (
                    "docs/stories.md",
                    "docs/ux-flow.md",
                    "docs/domain-model.md",
                    "docs/impl/01-foo.md",
                    "docs/impl/",
                    "docs/adr.md",
                    "docs/epics/epic-01-foo/adr.md",
                ):
                    reason = check_write_allowed(agent, path, cwd=cwd)
                    self.assertIsNotNone(reason, f"{agent} should be blocked on {path}")
                    self.assertIn("root-flat", reason)

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

    def test_ux_architect_root_ux_flow_blocked(self):
        # #810 — root docs/ux-flow.md legacy fallback is removed.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("ux-architect", "docs/ux-flow.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

    def test_ux_architect_epic_scoped_ux_flow_allowed(self):
        # #810 — epic-scoped ux-flow canonical path no longer includes milestones/.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed(
                    "ux-architect",
                    "docs/epics/epic-01-foo/ux-flow.md",
                    cwd=cwd,
                )
            )

    def test_ux_architect_non_canonical_ux_flow_blocked(self):
        # Canonical = docs/epics/<epic>/ux-flow.md only.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for bad in (
                "docs/milestones/v01/ux-flow.md",                       # epics/<epic> 누락
                "docs/epics/epic-01-foo/impl/ux-flow.md",  # 한 단계 더 깊음
                "docs/epics/epic-01-foo/impl/ux-flow.md",
            ):
                reason = check_write_allowed("ux-architect", bad, cwd=cwd)
                self.assertIsNotNone(reason, f"{bad} 는 차단돼야 함")
                self.assertIn("ALLOW_MATRIX", reason)

    def test_ux_architect_design_md_allowed(self):
        # design system token (system-level 영역) — agents/ux-architect 권한 경계가 문서화한 책무.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("ux-architect", "docs/design.md", cwd=cwd)
            )

    def test_ux_architect_architecture_blocked(self):
        # 역할 격리 보존 — ux-architect 는 architecture.md 를 쓰지 않는다 (architect 전용).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("ux-architect", "docs/architecture.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)


class LanguageNeutralAllowMatrixTests(unittest.TestCase):
    """#694 — ALLOW_MATRIX 언어 중립성.

    test-engineer / engineer 의 write 경계가 JS/TS 모노레포 컨벤션에 묶여 비-JS 외부
    프로젝트(Python·Go·Ruby·JVM·C#·PHP·Elixir·remotion 등)의 정상 산출물을 차단하던
    회귀 수정. 역할 격리(test-engineer=테스트만, engineer=소스)는 유지하면서 언어·레이아웃만
    중립화한다. 외부 프로젝트 시뮬레이션(DCNESS_INFRA="" + CLAUDE_PLUGIN_ROOT="").
    """

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @staticmethod
    def _write_boundary(root: Path, mapping: dict) -> None:
        cfg_dir = root / ".dcness"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "boundary.json").write_text(
            json.dumps(mapping), encoding="utf-8"
        )

    # ── test-engineer: 언어 중립 테스트 경로 허용 ──
    def test_test_engineer_python_tests_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in (
                "tests/core/domain/test_shorts.py",   # tests/ 디렉토리 + test_ 파일명
                "test_module.py",                      # 루트 test_*.py
                "pkg/utils_test.py",                   # *_test.py (디렉토리 밖)
            ):
                self.assertIsNone(
                    check_write_allowed("test-engineer", p, cwd=cwd),
                    f"Python 테스트 {p} 가 허용되어야 함",
                )

    def test_test_engineer_go_test_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # *_test.go (디렉토리 무관 파일명 컨벤션).
            self.assertIsNone(
                check_write_allowed("test-engineer", "internal/svc/handler_test.go", cwd=cwd)
            )

    def test_test_engineer_ruby_spec_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in ("spec/models/user_spec.rb", "lib/foo_test.rb"):
                self.assertIsNone(
                    check_write_allowed("test-engineer", p, cwd=cwd),
                    f"Ruby 테스트 {p} 허용",
                )

    def test_test_engineer_jvm_csharp_php_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in (
                "src/test/java/com/foo/UserServiceTest.java",  # src/test/ 디렉토리
                "src/test/kotlin/FooTests.kt",
                "MyApp.Tests/CalculatorTests.cs",              # 파일명 패턴 (디렉토리 밖)
                "app/Service/UserTest.php",
            ):
                self.assertIsNone(
                    check_write_allowed("test-engineer", p, cwd=cwd),
                    f"JVM/C#/PHP 테스트 {p} 허용",
                )

    def test_test_engineer_elixir_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("test-engineer", "test/foo_test.exs", cwd=cwd)
            )

    def test_test_engineer_js_ts_regression(self):
        # 기존 JS/TS 패턴이 광범위 패턴에 흡수돼도 여전히 허용 (회귀 방지).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in (
                "src/__tests__/a.test.ts",
                "src/components/Button.spec.tsx",
                "apps/web/tests/e2e.test.ts",
                "packages/core/src/__tests__/x.test.ts",
            ):
                self.assertIsNone(
                    check_write_allowed("test-engineer", p, cwd=cwd),
                    f"기존 JS/TS 테스트 {p} 회귀",
                )

    def test_test_engineer_still_cannot_write_impl(self):
        # 역할 격리 유지 — test-engineer 는 비-테스트 구현 코드를 쓰면 안 된다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in ("src/domain/shorts.py", "remotion/shorts-types.ts", "lib/core.go"):
                reason = check_write_allowed("test-engineer", p, cwd=cwd)
                self.assertIsNotNone(reason, f"test-engineer 가 구현 {p} 를 쓰면 안 됨")
                self.assertIn("ALLOW_MATRIX", reason)

    # ── engineer: 언어 중립 소스 레이아웃 허용 ──
    def test_engineer_remotion_requires_project_override(self):
        # #778 — 프로젝트 고유 디렉토리(remotion/)는 코어 기본값이 아니라 프로젝트 override.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed("engineer", "remotion/shorts-types.ts", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

            self._write_boundary(cwd, {"engineer": {"add": [r"^remotion/"]}})
            self.assertIsNone(
                check_write_allowed("engineer", "remotion/shorts-types.ts", cwd=cwd)
            )

    def test_engineer_common_source_layouts_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in (
                "lib/parser.rb",
                "app/models/user.rb",
                "cmd/server/main.go",
                "internal/svc/handler.go",
                "pkg/util/strings.go",
            ):
                self.assertIsNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"흔한 소스 레이아웃 {p} 허용",
                )

    def test_dot_slash_prefix_normalized(self):
        # #694 codex P2 (라운드3) — Edit/Write/Bash 가 ./ prefix 로 넘긴 경로도 정규화되어
        # 루트 앵커(^lib/ 등)가 빗나가지 않아야 하고, ./docs/ 우회는 여전히 차단돼야 한다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # ./ prefix 소스 — 허용
            for p in ("./lib/parser.rb", "./cmd/main.go"):
                self.assertIsNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"./ prefix 소스 {p} 허용",
                )
            reason = check_write_allowed("engineer", "./remotion/shorts-types.ts", cwd=cwd)
            self.assertIsNotNone(reason, "프로젝트 override 없는 remotion/ 은 차단되어야 함")
            self.assertIn("ALLOW_MATRIX", reason)
            # ./ prefix 테스트 — 허용
            self.assertIsNone(
                check_write_allowed("test-engineer", "./tests/test_x.py", cwd=cwd)
            )
            # ./ prefix docs 우회 — 차단 유지
            reason = check_write_allowed("engineer", "./docs/internal/x.md", cwd=cwd)
            self.assertIsNotNone(reason, "./docs/ 우회가 차단돼야 함")
            self.assertIn("docs", reason)

    def test_code_agents_can_write_docs_named_package(self):
        # #694 codex P2 — docs deny 는 루트 docs 트리(^docs/)만. monorepo 의 docs 이름
        # app/package(apps/docs/src·packages/docs/src)는 정상 소스라 허용돼야 한다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in ("apps/docs/src/App.tsx", "packages/docs/src/index.ts"):
                self.assertIsNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"docs 이름 패키지 소스 {p} 허용",
                )

    def test_dotdot_escape_via_allowed_dirname_blocked(self):
        # #694 codex P2 — 부모 경로가 허용 디렉토리명(tests/spec/lib)이어도 cwd 밖 탈출은
        # ALLOW 검사 전에 차단. `../tests/x` 가 (^|/)tests?/ 에 매칭되던 우회 봉쇄.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("test-engineer", "../tests/test_x.py"),
                ("test-engineer", "../spec/foo_spec.rb"),
                ("engineer", "../lib/x.rb"),
                ("build-worker", "../src/main.py"),
            ]:
                reason = check_write_allowed(agent, p, cwd=cwd)
                self.assertIsNotNone(reason, f"{agent} cwd 밖 {p} 차단")

    def test_nested_dotdot_escape_blocked(self):
        # #694 codex P1 — 초기 허용 세그먼트 뒤 중첩 .. 로 cwd 밖 탈출(lib/../../lib/x·
        # tests/../../tests/y)도 resolve 후 절대경로화되어 cwd-밖 가드로 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("engineer", "lib/../../lib/payload.rb"),
                ("test-engineer", "tests/../../tests/test_x.py"),
            ]:
                reason = check_write_allowed(agent, p, cwd=cwd)
                self.assertIsNotNone(reason, f"{agent} 중첩 .. 탈출 {p} 차단")

    def test_code_agents_cannot_write_dependency_trees(self):
        # #694 codex P2 — 의존성/vendored 트리는 test 패턴(tests?/·spec/)·src 패턴이 중첩
        # 매칭해도 코드 agent write 금지 (node_modules·vendor·third_party·venv).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            cases = [
                # 의존성/vendored — 안의 src/tests 가 중첩 매칭돼도 차단
                ("test-engineer", "node_modules/pkg/tests/x.py"),
                ("test-engineer", "vendor/foo/spec/bar_spec.rb"),
                ("build-worker", "third_party/lib/foo_test.go"),
                ("engineer", "node_modules/pkg/src/index.ts"),
                ("engineer", ".venv/lib/python3.11/site.py"),
                # 빌드 산출물 — 안의 src/tests 가 중첩 매칭돼도 차단
                ("engineer", "dist/bundle/src/app.js"),
                ("engineer", "build/gen/src/Main.java"),
                ("engineer", "target/debug/build/foo/src/lib.rs"),
                ("test-engineer", "out/tests/e2e.test.ts"),
                ("engineer", "src/__pycache__/mod.cpython-311.pyc"),
            ]
            for agent, p in cases:
                reason = check_write_allowed(agent, p, cwd=cwd)
                self.assertIsNotNone(reason, f"{agent} 가 의존성/산출물 트리 {p} 를 쓰면 안 됨")

    def test_source_dir_named_like_output_allowed(self):
        # #694 codex P2 — 빌드 산출물 deny 는 루트/패키지 루트 앵커. 허용된 src/ 트리 안의
        # 동명 디렉토리(src/build·src/dist·.../src/out)는 정당 소스라 허용돼야 한다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in ("src/build/index.ts", "src/dist/util.ts",
                      "packages/core/src/out/x.ts", "apps/web/src/build/m.ts"):
                self.assertIsNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"src 트리 안 동명 디렉토리 {p} 허용",
                )

    def test_output_dirs_root_and_package_blocked(self):
        # 루트(^build/) 및 monorepo 패키지 루트(apps/*/build·packages/*/dist) 산출물은 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in ("build/x.js", "dist/foo/src/a.js", "target/debug/x.rs",
                      "out/index.html", "apps/web/build/foo/src/m.ts",
                      "packages/core/dist/i.js"):
                self.assertIsNotNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"산출물 루트 {p} 차단",
                )

    def test_vendor_named_package_allowed(self):
        # #694 codex P2 round10 — vendor/third_party 는 패키지명과 겹칠 수 있어 루트/패키지 루트
        # 앵커. monorepo 의 `apps/vendor/src/` 같은 정당 패키지 소스는 허용돼야 한다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in ("apps/vendor/src/index.ts",
                      "packages/third_party/src/x.ts"):
                self.assertIsNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"vendor/third_party 이름의 정당 패키지 소스 {p} 허용",
                )

    def test_vendor_tree_root_and_package_blocked(self):
        # 루트(^vendor/·^third_party/) 및 monorepo 패키지 루트(apps/*/vendor·packages/*/third_party)
        # vendored 트리는 여전히 차단 — 동명 패키지 허용이 진짜 vendored 트리를 뚫으면 안 됨.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("engineer", "vendor/p/index.ts"),
                ("test-engineer", "third_party/lib/spec/x_spec.rb"),
                ("engineer", "apps/web/vendor/p/y.ts"),
                ("build-worker", "packages/core/third_party/foo_test.go"),
            ]:
                self.assertIsNotNone(
                    check_write_allowed(agent, p, cwd=cwd),
                    f"{agent} 가 vendored 트리 {p} 를 쓰면 안 됨",
                )

    def test_directory_target_write_allowed(self):
        # #694 codex P2 round10 — `cp x tests/`·`mv y apps/web/src/` 의 디렉토리 목적지 토큰은
        # resolve() 가 끝 `/`를 떼면 ALLOW 패턴(`tests?/`·`.../src/`)에 미매칭돼 정당 in-bound
        # write 가 오차단되던 결함. 끝 `/`를 보존해 디렉토리 루트 자체가 허용돼야 한다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("test-engineer", "tests/"),
                ("engineer", "src/"),
                ("engineer", "apps/web/src/"),
                ("engineer", "lib/"),
                ("engineer", "packages/core/src/"),
                # `/.`·`/./` 스펠링도 같은 디렉토리 타깃 (codex P2 r10).
                ("test-engineer", "tests/."),
                ("engineer", "apps/web/src/."),
                ("engineer", "src/./"),
            ]:
                self.assertIsNone(
                    check_write_allowed(agent, p, cwd=cwd, shell_context=True),
                    f"{agent} 의 허용 디렉토리 타깃 {p} 허용",
                )

    def test_directory_target_role_and_deny_preserved(self):
        # 디렉토리 타깃이라도 역할 격리(engineer 는 tests/ 못 씀)와 전용영역/인프라 deny 는 유지.
        # 끝 `/` 보존이 보호를 뚫으면 안 됨 — 오히려 `docs/`·`hooks/` 디렉토리 타깃이 정확히 매칭.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("engineer", "tests/"),         # 역할 격리 — engineer ALLOW 미매칭
                ("engineer", "docs/"),          # 전용영역 deny
                ("engineer", "node_modules/"),  # 의존성 deny
                ("engineer", "vendor/"),        # vendored deny (루트)
                ("engineer", "hooks/"),         # 인프라 deny
                # `/.` 스펠링도 동일하게 deny 매칭돼야 함 (보호 우회 방지).
                ("engineer", "docs/."),
                ("engineer", "node_modules/."),
                ("engineer", "hooks/."),
            ]:
                self.assertIsNotNone(
                    check_write_allowed(agent, p, cwd=cwd, shell_context=True),
                    f"{agent} 의 보호 디렉토리 타깃 {p} 차단",
                )

    def test_shell_expansion_collapsed_by_dotdot_blocked(self):
        # #694 codex P2 round10 — `$PWD/../tests/x` 는 _normalize 가 `$PWD/..` 를 상쇄해 norm 에서
        # `$` 가 사라지지만, 런타임엔 셸이 `$PWD` 를 확장해 프로젝트 밖에 write 한다. 셸확장 검사를
        # 정규화 *전* 원본에 적용해 차단해야 한다 (norm 기반 검사의 우회 봉쇄).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("test-engineer", "$PWD/../tests/x.py"),
                ("engineer", "$PWD/../../etc/src/x.py"),
                ("engineer", "`pwd`/../src/x.py"),
                ("engineer", "${PWD}/../app/x.rb"),
            ]:
                self.assertIsNotNone(
                    check_write_allowed(agent, p, cwd=cwd, shell_context=True),
                    f"{agent} 셸확장+상쇄 경로 {p} 차단",
                )

    def test_shell_expansion_path_blocked(self):
        # #694 codex P2 — Bash 출처(shell_context=True)의 $VAR/${}/$()/backtick 은 셸이 hook 후
        # 확장하므로 위치 미확정 → 차단. (literal Edit/Write 경로는 shell_context=False 라 허용.)
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("test-engineer", "$HOME/tests/test_x.py"),
                ("engineer", "${HOME}/lib/x.rb"),
                ("engineer", "$(pwd)/src/x.py"),
                ("engineer", "`echo /etc`/src/x.py"),
            ]:
                reason = check_write_allowed(agent, p, cwd=cwd, shell_context=True)
                self.assertIsNotNone(reason, f"{agent} Bash 셸 확장 경로 {p} 차단")

    def test_literal_dollar_filename_allowed_for_edit_write(self):
        # #694 codex P2 — Edit/Write 의 literal 파일명에 $ 가 있어도(Remix/React Router route
        # users.$id.tsx) 허용 (shell_context=False 기본). 셸확장 검사는 Bash 출처에만 적용.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in ("src/routes/users.$userId.tsx", "app/routes/$slug.tsx"):
                self.assertIsNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"literal $ 파일명 {p} 허용 (Edit/Write)",
                )
            # 동일 경로라도 Bash 출처(shell_context=True)면 셸 변수로 간주 차단
            self.assertIsNotNone(
                check_write_allowed("engineer", "src/routes/users.$userId.tsx",
                                    cwd=cwd, shell_context=True),
                "Bash 출처의 $ 경로는 차단",
            )

    def test_tilde_home_path_blocked(self):
        # #694 codex P2 — Bash 의 ~/... 는 셸이 hook 통과 후 home 으로 확장하므로 cwd 밖.
        # _normalize expanduser + cwd-밖 가드로 차단 (tests?/ 등 ALLOW 매칭 우회 방지).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, p in [
                ("test-engineer", "~/tests/test_x.py"),
                ("engineer", "~/lib/x.rb"),
                ("engineer", "~/src/main.py"),
            ]:
                reason = check_write_allowed(agent, p, cwd=cwd)
                self.assertIsNotNone(reason, f"{agent} tilde 경로 {p} 차단")

    def test_dotdot_escape_blocked(self):
        # #694 codex P1 — 상대 path 의 .. 세그먼트로 경계 밖(루트 문서·구현 코드)으로 탈출하는
        # 우회 차단. _normalize 가 cwd 기준 resolve 로 실제 write 위치를 매칭 대상으로 삼는다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # lib/../README.md → 실제 README.md(루트 문서) → engineer 차단
            self.assertIsNotNone(
                check_write_allowed("engineer", "lib/../README.md", cwd=cwd),
                "lib/../README.md (.. 우회) 차단",
            )
            # tests/../src/main.py → 실제 src/main.py(구현) → test-engineer 차단
            self.assertIsNotNone(
                check_write_allowed("test-engineer", "tests/../src/main.py", cwd=cwd),
                "tests/../src/main.py (.. 우회) 차단",
            )
            # ../ 상위 탈출 → 차단
            self.assertIsNotNone(
                check_write_allowed("engineer", "../outside/x.ts", cwd=cwd),
                "../ 상위 탈출 차단",
            )
            # 정상 .. 해소 후 유효 소스는 허용 (src/sub/../foo.ts → src/foo.ts)
            self.assertIsNone(
                check_write_allowed("engineer", "src/sub/../foo.ts", cwd=cwd),
                "src/sub/../foo.ts → src/foo.ts 허용",
            )

    def test_engineer_nested_layout_names_not_matched(self):
        # #694 codex P2 — 루트 소스 레이아웃(^lib/·^cmd/ 등)은 루트 앵커라, 의존성도 docs 도
        # 아닌 일반 중첩 동명 디렉토리(.github/*/lib·services/*/lib·a/b/cmd)는 소스 루트가
        # 아니므로 ALLOW 미매칭으로 차단된다 (의존성 트리는 별도 deny — 아래 테스트).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for p in (
                ".github/actions/foo/lib/action.yml",
                "services/foo/lib/util.rb",
                "a/b/cmd/run.go",
            ):
                reason = check_write_allowed("engineer", p, cwd=cwd)
                self.assertIsNotNone(reason, f"engineer 가 중첩 {p} 를 쓰면 안 됨")
                self.assertIn("ALLOW_MATRIX", reason)

    def test_engineer_invariant_still_blocks_docs_and_root(self):
        # 회귀 가드 — engineer 가 docs / 루트 비소스 문서를 쓰면 안 된다 (기존 invariant 유지).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # 루트 비소스 문서 — ALLOW_MATRIX 미매칭 차단.
            for p in ("README.md", "CHANGELOG.md"):
                reason = check_write_allowed("engineer", p, cwd=cwd)
                self.assertIsNotNone(reason, f"engineer 가 {p} 를 쓰면 안 됨")
                self.assertIn("ALLOW_MATRIX", reason)
            # docs/ — 전용영역 deny 로 차단 (#694 codex P2).
            reason = check_write_allowed("engineer", "docs/storage-layout.md", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("docs", reason)

    def test_code_agents_cannot_write_docs_subtree(self):
        # #694 codex P2 — 언어중립 패턴이 docs/ 하위 동명 디렉토리(docs/internal·docs/lib·
        # docs/spec·docs/tests)나 docs 안 테스트 파일명을 re.search 로 우회 허용하면 안 된다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            cases = [
                ("engineer", "docs/internal/release-notes.md"),  # internal/ 우회
                ("engineer", "docs/lib/guide.md"),               # lib/ 우회
                ("engineer", "docs/app/overview.md"),            # app/ 우회
                ("test-engineer", "docs/spec/api.md"),           # spec/ 우회
                ("test-engineer", "docs/tests/plan.md"),         # tests/ 우회
                ("test-engineer", "docs/test_examples.py"),      # test_*.py 파일명 우회
                ("build-worker", "docs/internal/x.md"),          # 합집합 상속
            ]
            for agent, p in cases:
                reason = check_write_allowed(agent, p, cwd=cwd)
                self.assertIsNotNone(reason, f"{agent} 가 docs 하위 {p} 를 쓰면 안 됨")
                self.assertIn("docs", reason)

    def test_code_agents_cannot_write_design_variants(self):
        # design-variants/ 는 designer 전용 — 코드 agent 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent in ("engineer", "test-engineer", "build-worker"):
                reason = check_write_allowed(agent, "design-variants/v1/index.html", cwd=cwd)
                self.assertIsNotNone(reason, f"{agent} 가 design-variants 를 쓰면 안 됨")

    # ── build-worker: 합집합으로 둘 다 허용 (youTubeGenerator 통합 시나리오) ──
    def test_build_worker_youtube_generator_scenario(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(cwd, {"engineer": {"add": [r"^remotion/"]}})
            # 테스트 산출 (test-engineer 영역) — task 01·02·03·07
            self.assertIsNone(
                check_write_allowed("build-worker", "tests/core/domain/test_shorts.py", cwd=cwd)
            )
            # 소스 산출 (engineer 영역) — task 04
            self.assertIsNone(
                check_write_allowed("build-worker", "remotion/shorts-types.ts", cwd=cwd)
            )
            # remotion 디렉토리 안 테스트 (test 디렉토리 패턴)
            self.assertIsNone(
                check_write_allowed("build-worker", "remotion/test/render_test.ts", cwd=cwd)
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
            for fname in ("build-test.md", "build-impl.md", "build-validate.md", "build-polish.md"):
                p = f".claude/harness-state/.sessions/SID123/runs/run-abcd1234/{fname}"
                self.assertIsNone(
                    check_write_allowed("build-worker", p, cwd=cwd),
                    f"run_dir prose {fname} self-write 가 허용되어야 함",
                )

    def test_build_worker_absolute_main_run_dir_allowed_from_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            main = Path(td) / "main"
            worktree = Path(td) / "wt"
            main.mkdir()
            worktree.mkdir()
            run_path = (
                main
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "SID123"
                / "runs"
                / "run-abcd1234"
                / "build-test.md"
            )

            with patch("harness.agent_boundary._resolve_project_root", return_value=main):
                self.assertIsNone(
                    check_write_allowed("build-worker", str(run_path), cwd=worktree),
                    "worktree cwd 에서 main repo run_dir 절대경로 phase prose self-write 가 허용되어야 함",
                )

    def test_build_worker_bash_redirect_to_absolute_run_dir_allowed_from_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            main = Path(td) / "main"
            worktree = Path(td) / "wt"
            main.mkdir()
            worktree.mkdir()
            run_path = (
                main
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "SID123"
                / "runs"
                / "run-abcd1234"
                / "build-validate.md"
            )

            command = f"printf '%s\\n' PASS > {run_path}"
            paths = extract_bash_paths(command)
            self.assertEqual(paths, [str(run_path)])
            with patch("harness.agent_boundary._resolve_project_root", return_value=main):
                self.assertIsNone(
                    check_write_allowed(
                        "build-worker",
                        paths[0],
                        cwd=worktree,
                        shell_context=True,
                    ),
                    "Bash redirect 로 쓰는 main run_dir phase prose 도 같은 carve-out 을 타야 함",
                )

    def test_absolute_run_dir_outside_project_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            main = Path(td) / "main"
            worktree = Path(td) / "wt"
            other = Path(td) / "other"
            main.mkdir()
            worktree.mkdir()
            other.mkdir()
            run_path = (
                other
                / ".claude"
                / "harness-state"
                / ".sessions"
                / "SID123"
                / "runs"
                / "run-abcd1234"
                / "build-test.md"
            )

            with patch("harness.agent_boundary._resolve_project_root", return_value=main):
                reason = check_write_allowed("build-worker", str(run_path), cwd=worktree)
            self.assertIsNotNone(reason)
            self.assertIn("경계 밖", reason)

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
            # docs/ 는 architect 전용 — 코드 agent 전용영역 deny 로 차단 (#694 codex P2).
            self.assertIn("docs", reason)

    def test_tech_reviewer_allowed_paths(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("tech-reviewer", "docs/tech-review.md", cwd=cwd)
            )
            self.assertIsNone(
                check_write_allowed(
                    "tech-reviewer",
                    "docs/epics/epic-01-demo/tech-review.md",
                    cwd=cwd,
                )
            )
            self.assertIsNone(
                check_write_allowed(
                    "tech-reviewer",
                    ".dcness-work/reviews/2026-06-21-demo.html",
                    cwd=cwd,
                )
            )

    def test_tech_reviewer_tracked_evidence_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            reason = check_write_allowed(
                "tech-reviewer", "docs/tech-review/report.html", cwd=cwd
            )
            self.assertIsNotNone(reason)
            self.assertIn("ALLOW_MATRIX", reason)

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
                "module-architect", "hooks/file-guard.sh", cwd=cwd
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

    def test_sed_clustered_in_place_extracts(self):
        for flag in ("-ni", "-ri", "-nri", "-Ei"):
            with self.subTest(flag=flag):
                paths = extract_bash_paths(f"sed {flag} 's/x/y/' hooks/gate.sh")
                self.assertIn("hooks/gate.sh", paths)

    def test_sed_attached_expr_is_not_in_place(self):
        self.assertEqual(
            extract_bash_paths("sed -es/i/o/ input.txt > docs/out.txt"),
            ["docs/out.txt"],
        )

    def test_redirect_extracts(self):
        paths = extract_bash_paths("echo hi > hooks/evil.sh")
        self.assertIn("hooks/evil.sh", paths)

    def test_cp_extracts(self):
        paths = extract_bash_paths("cp src/a.ts hooks/b.sh")
        self.assertIn("hooks/b.sh", paths)

    def test_read_operands_not_extracted_as_write_paths(self):
        # write boundary 는 실제 write target 만 검사한다. read operand 를 섞으면
        # `cat README.md > src/generated.ts` 같은 정상 생성이 README.md write 로 오차단된다.
        self.assertEqual(
            extract_bash_paths("cat README.md > src/generated.ts"),
            ["src/generated.ts"],
        )
        self.assertEqual(
            extract_bash_paths("cp README.md src/generated.ts"),
            ["src/generated.ts"],
        )
        self.assertEqual(
            extract_bash_paths("cat docs/prd.md | tee .dcness-work/reviews/x.json"),
            [".dcness-work/reviews/x.json"],
        )

    def test_perl_in_place(self):
        paths = extract_bash_paths("perl -i -pe 's/a/b/' docs/x.md")
        self.assertIn("docs/x.md", paths)

    def test_awk_in_place(self):
        paths = extract_bash_paths("awk -i inplace '{ print }' docs/x.md")
        self.assertIn("docs/x.md", paths)

    def test_url_not_extracted_as_write_path(self):
        # codex P2 (round9) — `curl URL > local.json` 의 URL 은 로컬 write 대상이 아님 → 후보 제외.
        # `/` 포함이라는 이유로 write path 로 오인돼 정상 명령이 차단되던 false positive 수정 검증.
        paths = extract_bash_paths(
            "curl -s https://example.com/api/v1 > .dcness-work/reviews/x.json"
        )
        self.assertNotIn("https://example.com/api/v1", paths)
        self.assertIn(".dcness-work/reviews/x.json", paths)

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
        # 파일 operand 위치가 확정된 뒤에는 확장자 없는 파일도 write target 으로 본다.
        self.assertIn("Makefile", extract_bash_paths("sed -i 's/a/b/' Makefile"))

    def test_quoted_shell_expansion_token_extracted(self):
        # codex P2 (round10) — 큰따옴표 안에 $/backtick 이 있는 토큰은 셸이 확장하므로 inner 를
        # 살려 후보로 반환해야 한다. 따옴표째 버리면 `echo x > "$HOME/tests/x"` 가
        # check_write_allowed 셸확장 가드에 도달 못 해 프로젝트 밖 write 우회가 된다.
        paths = extract_bash_paths('echo x > "$HOME/tests/x.py"')
        self.assertIn("$HOME/tests/x.py", paths)
        # backtick 명령치환도 동일.
        paths_bt = extract_bash_paths('echo x > "`pwd`/lib/y.rb"')
        self.assertIn("`pwd`/lib/y.rb", paths_bt)

    def test_quoted_literal_write_target_extracted(self):
        # sed script 는 quote 여부와 무관하게 command syntax 라 제외한다.
        self.assertNotIn(
            "s/foo/bar/", extract_bash_paths("sed -i 's/foo/bar/' src/main.ts")
        )
        # 하지만 실제 write target 이면 quote 된 literal path 도 검사 대상이다.
        self.assertIn(
            "docs/x.md", extract_bash_paths('sed -i "s/a/b/" "docs/x.md"')
        )
        self.assertIn(
            "hooks/evil.sh", extract_bash_paths('echo hi > "hooks/evil.sh"')
        )

    def test_quoted_sed_script_with_var_excluded(self):
        # codex P2 (round10) — `sed -i "s/$old/$new/" src/main.ts` 의 큰따옴표 치환 스크립트는
        # $ 가 있어 inner 가 살아나지만, 곧바로 sed 스크립트 제외 로직(^[sy]<delim>…)에 걸려
        # 후보에서 빠진다. 실제 대상 src/main.ts 만 남아 정상 편집이 안 막혀야 한다.
        paths = extract_bash_paths('sed -i "s/$old/$new/" src/main.ts')
        self.assertNotIn("s/$old/$new/", paths)
        self.assertIn("src/main.ts", paths)


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

    # ── #636 — leader-owned dcness helper 서브커맨드 (병렬 wave worker 금지) ──

    def test_helper_leader_subcommand_blocked_direct(self):
        # wrapper 직접 호출 (basename = dcness-helper)
        self.assertIsNotNone(
            check_bash_mutation("/x/scripts/dcness-helper end-run")
        )
        self.assertIsNotNone(
            check_bash_mutation("scripts/dcness-helper begin-run impl")
        )
        self.assertIsNotNone(check_bash_mutation("dcness-helper next-task"))
        self.assertIsNotNone(
            check_bash_mutation("dcness-helper ledger-event pr_merged --pr 5")
        )

    def test_helper_leader_subcommand_blocked_via_bash(self):
        # `bash <path>/dcness-helper end-run` — bash 가 toks[0] 여도 식별
        self.assertIsNotNone(
            check_bash_mutation("bash scripts/dcness-helper end-run")
        )
        self.assertIsNotNone(
            check_bash_mutation('bash "${CLAUDE_PLUGIN_ROOT}/scripts/dcness-helper" post-task-begin --reason x')
        )

    def test_helper_leader_subcommand_blocked_via_module(self):
        # python -m harness.session_state <subcommand>
        self.assertIsNotNone(
            check_bash_mutation("python3 -m harness.session_state finalize-run")
        )

    def test_helper_buildworker_subcommands_pass(self):
        # #636 회귀 가드 — serial build-worker(sub-agent)가 정상 호출하는 것은 통과.
        # begin-step/end-step: hybrid-A phase 직접 구동. prev-tasks-append: phase 3 누적.
        # (deny set 에 넣으면 기존 직렬 run 실행이 깨진다 — codex P2 F2.)
        self.assertIsNone(check_bash_mutation("dcness-helper begin-step build-worker"))
        self.assertIsNone(check_bash_mutation("dcness-helper end-step build-worker"))
        self.assertIsNone(
            check_bash_mutation("bash scripts/dcness-helper prev-tasks-append --slug 01-x --summary y")
        )

    def test_helper_prev_tasks_reset_blocked(self):
        # codex F16 — append(추가)는 build-worker 호출이라 허용하지만, reset(삭제)은
        # 메인 전담 + 파괴적(handoff FIFO 삭제)이라 차단. 비대칭.
        self.assertIsNotNone(check_bash_mutation("dcness-helper prev-tasks-reset"))
        self.assertIsNotNone(
            check_bash_mutation("bash scripts/dcness-helper prev-tasks-reset")
        )

    def test_helper_readonly_subcommand_passes(self):
        # read-only 서브커맨드는 통과 (worker 가 run_dir 등 조회는 무해)
        self.assertIsNone(check_bash_mutation("dcness-helper run-dir"))
        self.assertIsNone(check_bash_mutation("dcness-helper run-status"))
        self.assertIsNone(check_bash_mutation("dcness-helper is-active"))
        self.assertIsNone(check_bash_mutation("dcness-helper wave-status"))
        self.assertIsNone(
            check_bash_mutation("bash scripts/dcness-helper wave-plan docs/x/impl")
        )

    def test_helper_peer_state_mutation_blocked(self):
        # #641 peer mode board/merge mutations are main-owned. `wave-plan` is
        # read-only unless --register is present.
        self.assertIsNotNone(
            check_bash_mutation("dcness-helper wave-plan --register docs/x/impl")
        )
        self.assertIsNotNone(check_bash_mutation("dcness-helper wave-claim docs/x/impl/01-a.md"))
        self.assertIsNotNone(check_bash_mutation("dcness-helper wave-heartbeat abc"))
        self.assertIsNotNone(check_bash_mutation("dcness-helper wave-release abc --state failed"))
        self.assertIsNotNone(check_bash_mutation("dcness-helper wave-reclaim abc --reason stale"))
        self.assertIsNotNone(check_bash_mutation("dcness-helper merge-lock acquire --pr 1"))

    def test_pr_finalize_wrapper_blocked(self):
        # #641 review finding — sub-agents must not bypass merge-lock/gh mutation
        # guards by invoking the finalize wrapper script.
        self.assertIsNotNone(check_bash_mutation("bash scripts/pr-finalize.sh 123"))
        self.assertIsNotNone(check_bash_mutation("scripts/pr-finalize.sh 123"))

    def test_helper_unrelated_command_passes(self):
        # dcness-helper 아닌 명령은 무관 — end-run 같은 토큰이 있어도 false-positive 없음
        self.assertIsNone(check_bash_mutation("echo end-run"))
        self.assertIsNone(check_bash_mutation("ls scripts/dcness-helper"))

    def test_helper_token_in_data_position_passes(self):
        # codex F9 — helper 가 *명령 위치* 가 아니라 데이터일 땐 통과 (false-positive 제거).
        self.assertIsNone(check_bash_mutation("echo dcness-helper end-run"))
        self.assertIsNone(check_bash_mutation("echo 'run dcness-helper end-run later'"))
        self.assertIsNone(check_bash_mutation("grep next-task scripts/dcness-helper"))
        # 진짜 명령 위치는 여전히 차단 (회귀 아님 확인)
        self.assertIsNotNone(check_bash_mutation("dcness-helper end-run"))
        self.assertIsNotNone(check_bash_mutation("bash scripts/dcness-helper next-task"))


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
        # codex P1 (round4) — issue mutation 은 per-agent tools gate 예외 → 통과.
        for t in (
            "mcp__github__create_issue",
            "mcp__github__update_issue",
            "mcp__github__add_issue_comment",
        ):
            self.assertIsNone(
                check_github_mcp_mutation(t),
                f"{t} 는 per-agent issue tool 예외 — 통과해야 함",
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
        # codex P2 (round9) — tech-reviewer 의 `curl URL > .dcness-work/reviews/…` 가
        # URL 오인으로 차단되지 않아야 한다 (commit4 회귀 수정 검증).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            cmd = (
                "curl -s https://pypi.org/pypi/foo/json "
                "> .dcness-work/reviews/foo.json"
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

    def test_quoted_redirect_shell_expansion_blocked(self):
        # codex P2 (round10) — `echo x > "$HOME/tests/x.py"` 가 따옴표째 버려져 검사 미도달로
        # 프로젝트 밖 write 우회되던 결함 수정 검증. extract → shell_context 가드까지 도달해 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            paths = extract_bash_paths('echo x > "$HOME/tests/x.py"')
            self.assertIn("$HOME/tests/x.py", paths)
            blocked = [
                p for p in paths
                if check_write_allowed("test-engineer", p, cwd=cwd,
                                       shell_context=True) is not None
            ]
            self.assertTrue(
                any("$" in p for p in blocked),
                f"quoted 셸확장 redirect 가 차단되지 않음: {paths}",
            )

    def test_cp_mv_into_allowed_dir_not_blocked(self):
        # codex P2 (round10) — `cp src/foo.ts apps/web/src/`·`mv test_helper.py tests/` 의
        # 디렉토리 목적지가 끝 `/` 소실로 차단되던 false positive 수정 검증 (end-to-end).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            blocked_eng = [
                p for p in extract_bash_paths("cp src/foo.ts apps/web/src/")
                if check_write_allowed("engineer", p, cwd=cwd,
                                       shell_context=True) is not None
            ]
            self.assertEqual(blocked_eng, [],
                             f"engineer cp 디렉토리 타깃 차단됨: {blocked_eng}")
            blocked_te = [
                p for p in extract_bash_paths("mv test_helper.py tests/")
                if check_write_allowed("test-engineer", p, cwd=cwd,
                                       shell_context=True) is not None
            ]
            self.assertEqual(blocked_te, [],
                             f"test-engineer mv 디렉토리 타깃 차단됨: {blocked_te}")

    def test_quoted_redirect_dotdot_collapse_blocked(self):
        # codex P2 (round10) — `echo x > "$PWD/../tests/x.py"` 는 추출되어 norm 에서 `$PWD/..`
        # 가 상쇄(→ tests/x.py)되지만, 원본 셸확장 검사로 차단돼야 한다 (프로젝트 밖 write).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            paths = extract_bash_paths('echo x > "$PWD/../tests/x.py"')
            self.assertIn("$PWD/../tests/x.py", paths)
            blocked = [
                p for p in paths
                if check_write_allowed("test-engineer", p, cwd=cwd,
                                       shell_context=True) is not None
            ]
            self.assertTrue(
                any("$" in p for p in blocked),
                f"$PWD/.. 상쇄 escape 가 차단되지 않음: {paths}",
            )

    def test_quoted_sed_with_var_legit_edit_not_blocked(self):
        # codex P2 (round10) — engineer 의 `sed -i "s/$old/$new/" src/main.ts` 가 따옴표 안
        # 치환 스크립트 오인으로 차단되면 안 됨 (src/main.ts 만 후보, 정상 통과).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            blocked = [
                p for p in extract_bash_paths('sed -i "s/$old/$new/" src/main.ts')
                if check_write_allowed("engineer", p, cwd=cwd,
                                       shell_context=True) is not None
            ]
            self.assertEqual(blocked, [], f"engineer 정상 편집이 차단됨: {blocked}")


class FdRedirectAndDeviceSinkTests(unittest.TestCase):
    """#705 — fd 복제 redirect / device sink 가 write path 로 오추출되던 false positive.

    `cmd 2>&1` 의 `1`, `cmd > /dev/null` 의 `/dev/null` 은 프로젝트 파일 write 가 아니다.
    이들이 write target 으로 추출되면 ALLOW 미매칭(`1`) / 경계 밖(`/dev/null`) 차단이 발화해
    sub-agent 의 read-only 검증 명령(pytest/lint 게이트) 이 통째로 막힌다 — build-worker 가
    검증을 한 번도 실행 못 하고 정적 분석만으로 PASS 를 보고하는 false-clean 의 근본원인.
    """

    # ── fd 복제 (N>&M) / fd 닫기 (N>&-) — 파일 아님 ──────────────────

    def test_stderr_to_stdout_dup_not_extracted(self):
        self.assertEqual(extract_bash_paths("pytest tests/ 2>&1"), [])
        self.assertEqual(extract_bash_paths("pytest tests/ 2>&1 | tail -20"), [])

    def test_stdout_to_stderr_dup_not_extracted(self):
        self.assertEqual(extract_bash_paths("echo warn 1>&2"), [])
        self.assertEqual(extract_bash_paths("echo warn >&2"), [])

    def test_fd_close_not_extracted(self):
        self.assertEqual(extract_bash_paths("cmd 2>&-"), [])
        self.assertEqual(extract_bash_paths("cmd >&-"), [])

    def test_plain_redirect_to_digit_named_file_still_extracted(self):
        # `> 1` 은 fd 복제가 아니라 파일명 `1` write — 추출 유지 (경계 검사 대상).
        self.assertEqual(extract_bash_paths("echo x > 1"), ["1"])

    def test_csh_style_redirect_to_file_still_extracted(self):
        # `>& out.log` (stdout+stderr 를 파일로) — 대상이 fd 숫자가 아니면 파일 write.
        self.assertEqual(extract_bash_paths("cmd >& out.log"), ["out.log"])

    def test_fd_numbered_file_redirect_still_extracted(self):
        # `2> err.log` 는 stderr 를 *파일* 로 — write target 추출 유지.
        self.assertEqual(extract_bash_paths("cmd 2> err.log"), ["err.log"])

    # ── device sink — 어디에 써도 프로젝트 mutation 아님 ─────────────

    def test_dev_null_redirect_not_extracted(self):
        self.assertEqual(extract_bash_paths("pytest -q > /dev/null"), [])
        self.assertEqual(extract_bash_paths("ruff check src/ 2>/dev/null"), [])
        self.assertEqual(
            extract_bash_paths("bash scripts/gate.sh >/dev/null 2>&1"), []
        )

    def test_dev_stream_sinks_not_extracted(self):
        self.assertEqual(extract_bash_paths("cmd > /dev/stdout"), [])
        self.assertEqual(extract_bash_paths("cmd > /dev/stderr"), [])
        self.assertEqual(extract_bash_paths("cmd | tee /dev/null"), [])

    def test_dev_lookalike_paths_still_extracted(self):
        # device sink allowlist 는 정확한 경로만 — 하위/유사 경로는 일반 경계 검사 유지.
        self.assertEqual(extract_bash_paths("echo x > /dev/shm/evil"), ["/dev/shm/evil"])
        self.assertEqual(extract_bash_paths("echo x > dev/null"), ["dev/null"])

    def test_real_outside_write_still_extracted(self):
        # 회귀 가드 — repo 밖 실제 파일 write 는 계속 추출 (경계가 차단해야 함).
        self.assertEqual(
            extract_bash_paths("npm test 2>&1 | tee /tmp/test.log"), ["/tmp/test.log"]
        )

    def test_unicode_digit_fd_lookalike_still_extracted(self):
        # 리뷰 P3 — bash 는 `>&²` 를 파일 `²` write 로 본다 (ASCII 숫자만 fd).
        # str.isdigit() 단독 판정이면 유니코드 숫자가 fd 로 오인돼 추출 누락.
        self.assertIn("²", extract_bash_paths("echo x >&²"))

    def test_device_sink_equivalent_spellings_not_extracted(self):
        # 리뷰 P3 — `/dev/./null`·`//dev/null` 은 `/dev/null` 과 동일 대상.
        self.assertEqual(extract_bash_paths("pytest -q > /dev/./null"), [])
        self.assertEqual(extract_bash_paths("pytest -q > //dev/null"), [])

    def test_device_sink_case_and_traversal_still_extracted(self):
        # 대소문자(POSIX 구분)·경로 탈출은 동등 스펠링이 아님 — 추출 유지.
        self.assertEqual(extract_bash_paths("echo x > /dev/NULL"), ["/dev/NULL"])
        self.assertEqual(
            extract_bash_paths("echo x > /dev/null/../../etc/x"),
            ["/dev/null/../../etc/x"],
        )


class WorktreeValidationBoundaryTests(unittest.TestCase):
    """#705 통합 — worktree(.venv/node_modules 심볼릭) 의 read-only 검증 명령 비차단.

    git worktree 에는 .venv/node_modules 가 없어(gitignore) main repo 로 가는 심볼릭으로
    우회하는 게 정상 패턴이다. 그 경로로 게이트를 실행하는 Bash 가 agent-boundary 에
    차단되지 않아야 하고(AC), 동시에 repo 밖 write / 의존 트리 write 차단은 유지돼야 한다.
    """

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def _make_worktree(self, td: str) -> Path:
        root = Path(td)
        main = root / "mainrepo"
        (main / ".venv" / "bin").mkdir(parents=True)
        (main / "node_modules" / ".bin").mkdir(parents=True)
        wt = root / "worktrees" / "wt1"
        wt.mkdir(parents=True)
        (wt / ".venv").symlink_to(main / ".venv")
        (wt / "node_modules").symlink_to(main / "node_modules")
        (wt / "tests").mkdir()
        (wt / "scripts").mkdir()
        return wt

    def _blocked(self, agent: str, cmd: str, cwd: Path) -> list:
        return [
            p for p in extract_bash_paths(cmd)
            if check_write_allowed(agent, p, cwd=cwd, shell_context=True) is not None
        ]

    def test_venv_symlink_pytest_not_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            wt = self._make_worktree(td)
            for cmd in (
                ".venv/bin/python -m pytest tests/ 2>&1",
                ".venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -20",
                ".venv/bin/ruff check src/ 2>/dev/null",
            ):
                with self.subTest(cmd=cmd):
                    self.assertEqual(
                        self._blocked("build-worker", cmd, wt), [],
                        f"worktree 검증 명령이 차단됨: {cmd}",
                    )

    def test_node_modules_symlink_gate_not_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            wt = self._make_worktree(td)
            for cmd in (
                "node_modules/.bin/eslint src/ 2>&1",
                "bash scripts/check_quality.sh >/dev/null 2>&1",
                "npm test 2>&1",
            ):
                with self.subTest(cmd=cmd):
                    self.assertEqual(
                        self._blocked("build-worker", cmd, wt), [],
                        f"worktree 검증 명령이 차단됨: {cmd}",
                    )

    def test_dependency_tree_write_still_blocked(self):
        # 회귀 가드 — 심볼릭 *경유 실행* 허용이지 의존 트리 *write* 허용이 아니다.
        with tempfile.TemporaryDirectory() as td:
            wt = self._make_worktree(td)
            self.assertIsNotNone(
                check_write_allowed(
                    "build-worker", ".venv/lib/site.py", cwd=wt, shell_context=True
                )
            )
            self.assertIsNotNone(
                check_write_allowed(
                    "build-worker", "node_modules/pkg/index.js", cwd=wt,
                    shell_context=True,
                )
            )

    def test_outside_write_still_blocked(self):
        # 회귀 가드 — repo 밖 실제 write 는 worktree 에서도 계속 차단.
        with tempfile.TemporaryDirectory() as td:
            wt = self._make_worktree(td)
            blocked = self._blocked(
                "build-worker", "echo pwned | tee /tmp/evil.sh", wt
            )
            self.assertEqual(blocked, ["/tmp/evil.sh"])


class RootCodeFileAllowTests(unittest.TestCase):
    """#705 실측 보강 — repo 루트 직속 코드 파일(app.py 등) write 차단 friction.

    엔트리포인트가 루트 단일 파일인 레이아웃(Flask/FastAPI `app.py`, Django `manage.py`,
    Go `main.go`, Node `server.js`)에서 ALLOW_MATRIX 가 디렉토리 패턴만 갖고 있으면 code
    agent 가 그 파일을 못 고쳐 "prose 제시 -> 메인 대리 적용" 우회가 강제된다. 루트 직속
    *코드 확장자* 파일만 좁게 허용하고, 게이트 스크립트(.sh)/문서(.md)/매니페스트
    (toml·json·yaml)/비루트 경로는 기존 차단을 유지한다.
    """

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_root_entry_code_files_allowed_for_code_agents(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, fp in (
                ("engineer", "app.py"),
                ("engineer", "main.py"),
                ("engineer", "manage.py"),
                ("engineer", "server.js"),
                ("engineer", "main.go"),
                ("build-worker", "app.py"),
                ("build-worker", "main.go"),
            ):
                with self.subTest(agent=agent, fp=fp):
                    self.assertIsNone(check_write_allowed(agent, fp, cwd=cwd))

    def test_root_non_code_files_still_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent, fp in (
                ("engineer", "README.md"),       # 문서 — 역할 격리 유지
                ("engineer", "check.sh"),        # 게이트 스크립트 — agent 가 수정 금지
                ("engineer", "pyproject.toml"),  # 매니페스트
                ("engineer", "package.json"),
                ("engineer", "Makefile"),
                ("engineer", ".env"),
                ("build-worker", "release.yaml"),
            ):
                with self.subTest(agent=agent, fp=fp):
                    self.assertIsNotNone(check_write_allowed(agent, fp, cwd=cwd))

    def test_non_root_code_paths_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # 루트 전용 앵커 — 디렉토리 하위는 기존 패턴 영역 그대로.
            self.assertIsNotNone(
                check_write_allowed("engineer", "scripts/run.py", cwd=cwd)
            )
            # docs/ 하위 코드 파일명은 전용영역 deny 가 계속 우선.
            self.assertIsNotNone(
                check_write_allowed("engineer", "docs/app.py", cwd=cwd)
            )

    def test_root_validation_toolchain_files_blocked_for_engineer(self):
        # 리뷰 P2 — 루트 코드 파일 ALLOW 가 *검증 도구체인 설정* 까지 열면 안 된다.
        # conftest.py 한 줄(collect_ignore)로 테스트 전체 침묵 skip = false-clean 재유입.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for fp in (
                "conftest.py",        # pytest collection 제어 — engineer 금지
                "noxfile.py",         # 테스트 세션 러너
                "jest.config.js",
                "vitest.config.ts",
                "eslint.config.mjs",
                ".eslintrc.js",       # dotfile 설정
            ):
                with self.subTest(fp=fp):
                    self.assertIsNotNone(
                        check_write_allowed("engineer", fp, cwd=cwd)
                    )

    def test_build_worker_keeps_conftest_via_test_union(self):
        # build-worker 는 테스트도 쓰는 엔진 — test-engineer 합집합으로 conftest 유지.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("build-worker", "conftest.py", cwd=cwd)
            )

    def test_conftest_allowed_for_test_engineer(self):
        # pytest 관례 파일 — 같은 클래스 friction (디렉토리 패턴 밖 관례 파일).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("test-engineer", "conftest.py", cwd=cwd)
            )
            self.assertIsNone(
                check_write_allowed("test-engineer", "tests/conftest.py", cwd=cwd)
            )

    def test_test_engineer_still_blocked_from_impl_source(self):
        # 역할 격리 회귀 가드 — test-engineer 는 구현 엔트리 파일 write 금지 유지.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNotNone(
                check_write_allowed("test-engineer", "app.py", cwd=cwd)
            )


class ProjectBoundaryOverrideTests(unittest.TestCase):
    """#696 — 프로젝트별 ALLOW_MATRIX override (`.dcness/boundary.json`).

    외부 활성 프로젝트가 자기 사정을 직접 선언해 sub-agent write 경계를 양방향으로
    커스텀한다 (add = 허용 확장, remove = 코어 기본값 제거). 코어는 합리적 기본값만,
    예외는 프로젝트가 SSOT. 외부 프로젝트 시뮬레이션(DCNESS_INFRA="" + tempdir).
    """

    def setUp(self):
        self._patcher = patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @staticmethod
    def _write_boundary(root: Path, mapping: dict) -> None:
        cfg_dir = root / ".dcness"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "boundary.json").write_text(
            json.dumps(mapping), encoding="utf-8"
        )

    @staticmethod
    def _git_init(root: Path) -> None:
        # 외부 활성 프로젝트는 git repo — project-root 경계(#696 P2)가 git common-dir
        # 기준으로 동작하므로, 조상 탐색 테스트는 실제 repo 로 시뮬레이션한다.
        import subprocess

        subprocess.run(
            ["git", "init", "-q"], cwd=str(root), check=True,
            capture_output=True,
        )

    # ── add: 허용 확장 ──
    def test_add_extends_allow_for_nonstandard_layout(self):
        # 코어에 없는 비표준 소스 레이아웃을 add 로 허용.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # add 전 — 차단 확인.
            self.assertIsNotNone(
                check_write_allowed("engineer", "custom-pkg/widget.go", cwd=cwd)
            )
            self._write_boundary(cwd, {"engineer": {"add": [r"(^|/)custom-pkg/"]}})
            self.assertIsNone(
                check_write_allowed("engineer", "custom-pkg/widget.go", cwd=cwd)
            )

    def test_add_opens_default_excluded_tests_for_engineer(self):
        # engineer 의 tests/ 기본 제외(self-grading 방어)를 프로젝트가 add 로 완화.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNotNone(
                check_write_allowed("engineer", "tests/test_widget.py", cwd=cwd)
            )
            self._write_boundary(cwd, {"engineer": {"add": [r"(^|/)tests?/"]}})
            self.assertIsNone(
                check_write_allowed("engineer", "tests/test_widget.py", cwd=cwd)
            )

    # ── remove: 코어 기본값 제거 ──
    def test_remove_blocks_core_default(self):
        # 코어 기본 허용 경로(^app/)를 프로젝트가 remove 로 제거.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("engineer", "app/models.rb", cwd=cwd)
            )
            self._write_boundary(cwd, {"engineer": {"remove": [r"^app/"]}})
            reason = check_write_allowed("engineer", "app/models.rb", cwd=cwd)
            self.assertIsNotNone(reason)

    def test_remove_overrides_add_on_conflict(self):
        # 같은 경로에 add+remove 동시 → remove 우선(보수적 차단).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(
                cwd,
                {"engineer": {"add": [r"(^|/)zone/"], "remove": [r"(^|/)zone/"]}},
            )
            self.assertIsNotNone(
                check_write_allowed("engineer", "zone/x.go", cwd=cwd)
            )

    # ── 가드: 되돌릴 수 없는 경계는 override 가 못 뚫는다 ──
    def test_add_cannot_open_infra_path(self):
        # add 로 INFRA 경로(hooks/)를 열려 해도 INFRA 검사가 먼저라 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(cwd, {"engineer": {"add": [r"(^|/)hooks/"]}})
            reason = check_write_allowed("engineer", "hooks/evil.py", cwd=cwd)
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_boundary_file_itself_blocked_for_subagent(self):
        # 위조 방지 — 설정 파일 자신은 어떤 sub-agent 도 write 못 함 (self 확장/축소 금지).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            for agent in ("engineer", "test-engineer", "build-worker", "architect"):
                reason = check_write_allowed(
                    agent, ".dcness/boundary.json", cwd=cwd
                )
                self.assertIsNotNone(reason, f"{agent} 가 boundary.json 쓰면 안 됨")
                self.assertIn("인프라", reason)

    def test_add_cannot_open_boundary_file(self):
        # add 로 .dcness/ 를 열려 해도 boundary.json 은 INFRA 라 차단.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(cwd, {"engineer": {"add": [r"(^|/)\.dcness/"]}})
            reason = check_write_allowed(
                "engineer", ".dcness/boundary.json", cwd=cwd
            )
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    def test_add_dcness_dir_target_write_still_blocked(self):
        # #696 codex P2 — add 로 .dcness/ 를 열어도 디렉토리 타깃 write(cp x .dcness/)로
        # boundary.json 을 교체하는 우회를 차단. .dcness 디렉토리 자체·하위 모두 INFRA.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(cwd, {"engineer": {"add": [r"(^|/)\.dcness/"]}})
            for target in (".dcness/", ".dcness", ".dcness/other.json"):
                reason = check_write_allowed(
                    "engineer", target, cwd=cwd, shell_context=True
                )
                self.assertIsNotNone(reason, f"{target} 우회 가능하면 안 됨")
                self.assertIn("인프라", reason)

    def test_remove_cannot_unprotect_boundary_file(self):
        # remove 로 boundary.json INFRA 보호를 풀 수 없다.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(
                cwd, {"engineer": {"remove": [r"(^|/)\.dcness/boundary\.json$"]}}
            )
            reason = check_write_allowed(
                "engineer", ".dcness/boundary.json", cwd=cwd
            )
            self.assertIsNotNone(reason)
            self.assertIn("인프라", reason)

    # ── 회귀/안전 ──
    def test_no_boundary_file_core_defaults_intact(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            # 코어 기본값 그대로 — src 허용, random 차단.
            self.assertIsNone(check_write_allowed("engineer", "src/x.ts", cwd=cwd))
            self.assertIsNotNone(
                check_write_allowed("engineer", "README.md", cwd=cwd)
            )

    def test_malformed_boundary_ignored(self):
        # 깨진 JSON → 무시하고 코어 기본값 유지 (안전 degrade).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            cfg_dir = cwd / ".dcness"
            cfg_dir.mkdir()
            (cfg_dir / "boundary.json").write_text("{not json", encoding="utf-8")
            self.assertIsNone(check_write_allowed("engineer", "src/x.ts", cwd=cwd))
            self.assertIsNotNone(
                check_write_allowed("engineer", "custom-pkg/x.go", cwd=cwd)
            )

    def test_invalid_regex_pattern_skipped(self):
        # 컴파일 불가 정규식은 그 패턴만 skip — 나머지 add 는 유효.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(
                cwd, {"engineer": {"add": [r"(unclosed", r"(^|/)okdir/"]}}
            )
            self.assertIsNone(
                check_write_allowed("engineer", "okdir/x.go", cwd=cwd)
            )

    def test_boundary_found_in_ancestor(self):
        # cwd 가 하위 디렉토리여도 *프로젝트 루트* 의 boundary.json 적용.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self._git_init(root)
            self._write_boundary(root, {"engineer": {"add": [r"(^|/)custom-pkg/"]}})
            sub = root / "services" / "api"
            sub.mkdir(parents=True)
            self.assertIsNone(
                check_write_allowed("engineer", "custom-pkg/x.go", cwd=sub)
            )

    def test_boundary_in_linked_worktree_from_subdir(self):
        # #696 codex P2 — 메인 체크아웃 밖에 둔 linked worktree 의 하위 디렉토리에서도
        # worktree 루트 boundary.json 이 적용된다 (top-level 기준 탐색).
        import subprocess

        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
            main = Path(ta).resolve()
            subprocess.run(["git", "init", "-q"], cwd=str(main), check=True,
                           capture_output=True)
            subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", "init"],
                           cwd=str(main), check=True, capture_output=True, env=env)
            wt = Path(tb).resolve() / "linked-wt"  # 메인 밖 경로
            subprocess.run(["git", "worktree", "add", "-q", str(wt)],
                           cwd=str(main), check=True, capture_output=True, env=env)
            self._write_boundary(wt, {"engineer": {"add": [r"(^|/)custom-pkg/"]}})
            sub = wt / "services" / "api"
            sub.mkdir(parents=True)
            self.assertIsNone(
                check_write_allowed("engineer", "custom-pkg/x.go", cwd=sub)
            )

    def test_boundary_outside_project_root_ignored(self):
        # #696 codex P2 — 프로젝트 루트 밖(상위 워크스페이스)의 boundary.json 은 무시.
        # 상위 디렉토리의 override 가 무관한 하위 프로젝트의 경계를 약화하면 안 된다.
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td).resolve()
            # 상위 워크스페이스에 boundary (engineer 에 custom-pkg 허용).
            self._write_boundary(outer, {"engineer": {"add": [r"(^|/)custom-pkg/"]}})
            # 하위에 독립 프로젝트(git repo) — 자기 boundary 없음.
            proj = outer / "child-project"
            proj.mkdir()
            self._git_init(proj)
            # 상위 boundary 가 새지 않아 여전히 차단되어야 한다.
            self.assertIsNotNone(
                check_write_allowed("engineer", "custom-pkg/x.go", cwd=proj)
            )

    # ── build-worker 합집합 전파 (codex P1) ──
    def test_build_worker_inherits_engineer_add(self):
        # build-worker = engineer ∪ test-engineer — engineer.add 가 build-worker 에 전파.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNotNone(
                check_write_allowed("build-worker", "custom-pkg/x.go", cwd=cwd)
            )
            self._write_boundary(cwd, {"engineer": {"add": [r"(^|/)custom-pkg/"]}})
            self.assertIsNone(
                check_write_allowed("build-worker", "custom-pkg/x.go", cwd=cwd)
            )

    def test_build_worker_inherits_engineer_remove(self):
        # engineer.remove 가 build-worker 에 전파 — remove 우회 방지.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNone(
                check_write_allowed("build-worker", "app/models.rb", cwd=cwd)
            )
            self._write_boundary(cwd, {"engineer": {"remove": [r"^app/"]}})
            self.assertIsNotNone(
                check_write_allowed("build-worker", "app/models.rb", cwd=cwd)
            )

    def test_build_worker_inherits_test_engineer_add(self):
        # test-engineer.add 도 build-worker 에 전파 (합집합 구성 역할).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertIsNotNone(
                check_write_allowed("build-worker", "custom-e2e/run.yml", cwd=cwd)
            )
            self._write_boundary(
                cwd, {"test-engineer": {"add": [r"(^|/)custom-e2e/.*"]}}
            )
            self.assertIsNone(
                check_write_allowed("build-worker", "custom-e2e/run.go", cwd=cwd)
            )

    def test_build_worker_own_key_still_applies(self):
        # build-worker 자체 키 override 도 유효 (union 에 build-worker 포함).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(
                cwd, {"build-worker": {"add": [r"(^|/)bw-only/"]}}
            )
            self.assertIsNone(
                check_write_allowed("build-worker", "bw-only/x.go", cwd=cwd)
            )
            # engineer 단독은 build-worker 키 add 를 받지 않는다 (역방향 전파 없음).
            self.assertIsNotNone(
                check_write_allowed("engineer", "bw-only/x.go", cwd=cwd)
            )

    def test_add_cannot_grant_write_to_readonly_agent(self):
        # #696 codex P2 — 판정/검증 전용 agent(빈 ALLOW)는 add 로도 write 못 연다.
        # 검증자 역할 격리는 catastrophic gate 신뢰의 근간 (되돌릴 수 없는 경계).
        readonly = (
            "code-validator", "pr-reviewer", "architecture-validator",
            "product-acceptance", "plan-reviewer",
        )
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(
                cwd, {a: {"add": [r"(^|/)src/"]} for a in readonly}
            )
            for agent in readonly:
                reason = check_write_allowed(agent, "src/x.ts", cwd=cwd)
                self.assertIsNotNone(reason, f"{agent} 가 add 로 write 열리면 안 됨")
                self.assertIn("write-zero", reason)

    def test_add_cannot_write_guard_disable_markers(self):
        # #696 codex P1 — broad add(.*)로도 file guard self-disable 마커는 못 쓴다.
        # .no-dcness-guard(is_opt_out) / .claude-plugin/plugin.json(is_infra_project).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._write_boundary(cwd, {"engineer": {"add": [r".*"]}})
            for target in (
                ".no-dcness-guard", ".no-dcness-guard/",
                ".claude-plugin/plugin.json", ".claude-plugin/", ".claude-plugin",
            ):
                reason = check_write_allowed(
                    "engineer", target, cwd=cwd, shell_context=True
                )
                self.assertIsNotNone(reason, f"{target} self-disable 가능하면 안 됨")
                self.assertIn("인프라", reason)

    def test_override_ignored_in_infra_project(self):
        # dcness self / infra project 는 어차피 통과 — override 무관, 메인 SSOT 편집 보존.
        with patch.dict(os.environ, {"DCNESS_INFRA": "1"}, clear=False):
            with tempfile.TemporaryDirectory() as td:
                cwd = Path(td)
                self._write_boundary(cwd, {"engineer": {"remove": [r"(^|/)src/"]}})
                # remove 했어도 infra project 는 통과.
                self.assertIsNone(
                    check_write_allowed("engineer", "src/x.ts", cwd=cwd)
                )


if __name__ == "__main__":
    unittest.main()
