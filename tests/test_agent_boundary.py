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
    def test_engineer_remotion_allowed(self):
        # #694 핵심 — src/ 밖 소스 루트(remotion/) 허용 (youTubeGenerator task 04).
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
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
            for p in ("./lib/parser.rb", "./remotion/shorts-types.ts", "./cmd/main.go"):
                self.assertIsNone(
                    check_write_allowed("engineer", p, cwd=cwd),
                    f"./ prefix 소스 {p} 허용",
                )
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
        # (deny set 에 넣으면 기존 직렬 conveyor 가 깨진다 — codex P2 F2.)
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
