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

    def test_env_plugin_root(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self.assertTrue(
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


if __name__ == "__main__":
    unittest.main()
