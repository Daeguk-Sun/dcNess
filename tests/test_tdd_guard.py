"""hooks/tdd-guard.sh 단위 테스트 — entry-file false-positive 회피 (#423).

검증 범위:
- 기존 skip 룰 (test/spec 파일 자체 / config / 타입 / Next.js 특수) — 회귀 방지
- entry-file path heuristic (#423): App.{ts,tsx,js,jsx} / _layout.* / apps/*/index.* / src/main.*
- 파일 내용 시그니처 grep (#423): registerRootComponent / AppRegistry.registerComponent
- 일반 src 파일 + 테스트 부재 → deny (기존 동작 보존)
- 매칭 테스트 파일 존재 → allow

호출 메커니즘: hook 은 bash. stdin 으로 JSON payload 받음.
  - allow → exit 0 + stdout 에 suppressOutput JSON
  - deny  → exit 2 + stderr 에 reason (CC docs: PreToolUse 차단은 exit 2)
따라서 결정은 **returncode 로 판정** (0=allow / 2=deny). stdout JSON 파싱 아님.

활성 게이트: tdd-guard.sh 는 `is-active` 게이트를 가진다 (#597 커밋3). temp cwd 는
whitelist 미등록이라 게이트가 즉시 allow 시키므로, deny 동작 검증을 위해
`DCNESS_FORCE_ENABLE=1` + `PYTHONPATH=<repo>` 를 env 로 주입한다 (multisession smoke 정합).
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = ROOT / "hooks" / "tdd-guard.sh"


def run_hook(
    file_path: str, cwd: str, tool_name: str = "Edit"
) -> subprocess.CompletedProcess:
    """tdd-guard.sh 호출 → CompletedProcess 반환 (returncode 로 결정 판정)."""
    payload = {
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    }
    return subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT),
            # temp cwd 는 whitelist 미등록 → is-active 게이트 우회 강제 활성화 (커밋3)
            "DCNESS_FORCE_ENABLE": "1",
        },
    )


def decision(result: subprocess.CompletedProcess) -> str:
    """allow / deny 를 returncode 로 판정 — exit 0=allow / exit 2=deny."""
    if result.returncode == 0:
        return "allow"
    if result.returncode == 2:
        return "deny"
    return "unknown"


class TestEntryFileHeuristic(unittest.TestCase):
    """#423 — entry-file path heuristic skip."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str, content: str = "// stub\n") -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_app_tsx_skipped(self):
        path = self._touch("apps/mobile/App.tsx")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_app_js_skipped(self):
        path = self._touch("apps/mobile/App.js")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_expo_router_layout_skipped(self):
        path = self._touch("apps/mobile/app/_layout.tsx")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_expo_router_group_layout_skipped(self):
        path = self._touch("apps/mobile/app/(tabs)/_layout.tsx")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_monorepo_apps_index_js_skipped(self):
        path = self._touch("apps/mobile/index.js")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_monorepo_apps_index_ts_skipped(self):
        path = self._touch("apps/web/index.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_vue_vite_main_skipped(self):
        path = self._touch("src/main.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")


class TestSignatureGrep(unittest.TestCase):
    """#423 — 파일 내용 시그니처 grep skip."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, rel: str, content: str) -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_registerRootComponent_skipped(self):
        """비-컨벤션 path 라도 registerRootComponent 시그니처 → allow."""
        path = self._write(
            "src/some-non-conventional-entry.tsx",
            "import { registerRootComponent } from 'expo';\nregisterRootComponent(App);\n",
        )
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_AppRegistry_registerComponent_skipped(self):
        """Bare RN AppRegistry.registerComponent → allow."""
        path = self._write(
            "src/rn-bare-entry.js",
            "import { AppRegistry } from 'react-native';\nAppRegistry.registerComponent('app', () => App);\n",
        )
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")


class TestRegressionPreserved(unittest.TestCase):
    """기존 skip 룰 + deny 동작 회귀 방지."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str, content: str = "// stub\n") -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_test_file_self_skipped(self):
        path = self._touch("src/foo.test.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_config_skipped(self):
        path = self._touch("babel.config.js")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_metro_config_skipped(self):
        path = self._touch("metro.config.js")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_app_config_ts_skipped(self):
        path = self._touch("app.config.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_types_skipped(self):
        path = self._touch("src/types/foo.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_non_ts_js_skipped(self):
        path = self._touch("src/foo.py")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_src_business_logic_without_test_denied(self):
        """일반 비즈니스 로직 + 테스트 부재 → deny (기존 동작 보존)."""
        path = self._touch(
            "src/business-logic.ts",
            "export function calculatePrice(qty, unit) { return qty * unit; }\n",
        )
        self.assertEqual(decision(run_hook(path, self._tmp)), "deny")

    def test_src_business_logic_with_test_allowed(self):
        """일반 비즈니스 로직 + 매칭 테스트 존재 → allow."""
        self._touch(
            "src/biz.ts",
            "export function calc() { return 1; }\n",
        )
        self._touch("src/biz.test.ts", "test('ok', () => {})\n")
        path = str(Path(self._tmp) / "src/biz.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")


class TestBasenameSubstringFalseNegative(unittest.TestCase):
    """issue #681 — basename 에 우연히 'test'/'spec' 이 든 구현 파일은 skip 아님.

    버그: 기존 skip 매처가 `*test*` / `*spec*` 광역 glob 이라 `contest.ts` / `spectrum.ts`
    같은 구현 파일을 test 파일로 오인 → TDD 강제 우회. 매칭은 (1) basename 의
    `.test.` / `.spec.` 접미 컨벤션, (2) 슬래시로 구분된 표준 test 디렉터리 마디만 해야 한다.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str, content: str = "// stub\n") -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_contest_impl_without_test_denied(self):
        """contest.ts — basename 에 'test' 포함하나 구현 파일 → 테스트 부재면 deny."""
        path = self._touch(
            "src/contest.ts",
            "export function joinContest(id) { return id; }\n",
        )
        self.assertEqual(decision(run_hook(path, self._tmp)), "deny")

    def test_spectrum_impl_without_test_denied(self):
        """spectrum.ts — basename 에 'spec' 포함하나 구현 파일 → 테스트 부재면 deny."""
        path = self._touch(
            "src/spectrum.ts",
            "export function analyzeSpectrum(buf) { return buf.length; }\n",
        )
        self.assertEqual(decision(run_hook(path, self._tmp)), "deny")

    def test_latest_impl_without_test_denied(self):
        """latest.ts — basename 에 'test' 포함하나 구현 파일 → 테스트 부재면 deny."""
        path = self._touch(
            "src/latest.ts",
            "export function latest(arr) { return arr[arr.length - 1]; }\n",
        )
        self.assertEqual(decision(run_hook(path, self._tmp)), "deny")

    def test_contest_with_matching_test_allowed(self):
        """contest.ts + 매칭 contest.test.ts 존재 → allow (정상 TDD)."""
        self._touch("src/contest.ts", "export const c = 1;\n")
        self._touch("src/contest.test.ts", "test('ok', () => {})\n")
        path = str(Path(self._tmp) / "src/contest.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_real_test_file_still_skipped(self):
        """진짜 test 파일 (.test. 접미) 은 계속 skip — 회귀 방지."""
        path = self._touch("src/spectrum.test.ts", "test('x', () => {})\n")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_real_spec_file_still_skipped(self):
        """진짜 spec 파일 (.spec. 접미) 은 계속 skip — 회귀 방지."""
        path = self._touch("src/contest.spec.tsx", "test('x', () => {})\n")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_file_inside_tests_dir_skipped(self):
        """표준 test 디렉터리(__tests__) 안 파일은 .test. 접미 없어도 skip."""
        path = self._touch("src/__tests__/helper.ts", "export const h = 1;\n")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_file_inside_test_dir_segment_skipped(self):
        """슬래시로 구분된 test/ 디렉터리 마디 안 파일은 skip."""
        path = self._touch("src/test/fixtures.ts", "export const f = 1;\n")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_contest_dir_segment_not_skipped(self):
        """디렉터리명이 'contest' (test 아님) 인 구현 파일은 skip 아님 → deny."""
        path = self._touch("src/contest/board.ts", "export const b = 1;\n")
        self.assertEqual(decision(run_hook(path, self._tmp)), "deny")

    def test_relative_top_level_tests_dir_skipped(self):
        """상대 경로 top-level `tests/` 디렉터리 파일도 skip — codex P2 (선두 슬래시 정규화)."""
        self._touch("tests/helper.ts", "export const h = 1;\n")
        # 절대 경로가 아니라 cwd(tmp) 기준 상대 경로를 직접 전달.
        self.assertEqual(decision(run_hook("tests/helper.ts", self._tmp)), "allow")

    def test_relative_top_level_tests_underscore_dir_skipped(self):
        """상대 경로 top-level `__tests__/` 디렉터리 파일도 skip — codex P2."""
        self._touch("__tests__/setup.ts", "export const s = 1;\n")
        self.assertEqual(decision(run_hook("__tests__/setup.ts", self._tmp)), "allow")

    def test_relative_top_level_impl_still_denied(self):
        """상대 경로라도 top-level 구현 파일(test 디렉터리 아님)은 여전히 deny — 정규화 오버매치 방지."""
        self._touch("contest.ts", "export const c = 1;\n")
        self.assertEqual(decision(run_hook("contest.ts", self._tmp)), "deny")

    def test_repo_under_e2e_parent_does_not_skip_impl(self):
        """repo 루트의 *조상* 디렉터리명이 test 디렉터리(e2e)여도 구현 파일은 skip 안 함 → deny.

        codex P2 round2 — 디렉터리 마디 매치는 PROJECT_ROOT 상대 경로 기준이어야 한다.
        체크아웃이 `.../e2e/app` 밑에 있으면 절대 경로의 `e2e` 조상 마디가 매치돼
        TDD guard 가 무력화되던 결함.
        """
        repo = Path(self._tmp) / "e2e" / "app"
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        src = repo / "src" / "foo.ts"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("export function foo() { return 1; }\n", encoding="utf-8")
        # cwd = repo (PROJECT_ROOT 가 .../e2e/app 로 잡힘), 절대 경로 전달.
        self.assertEqual(decision(run_hook(str(src), str(repo))), "deny")

    def test_repo_internal_e2e_dir_still_skips(self):
        """repo *내부* 의 e2e/ 디렉터리 파일은 계속 skip — 회귀 방지 (상대 경로 매치 보존)."""
        repo = Path(self._tmp) / "e2e" / "app"
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        f = repo / "src" / "e2e" / "flow.ts"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("export const flow = 1;\n", encoding="utf-8")
        self.assertEqual(decision(run_hook(str(f), str(repo))), "allow")


class TestPathMatcherTier4_Grandparent(unittest.TestCase):
    """issue #469 결함 C — Tier 4: <grandparent>/__tests__/<name>.{test,spec}.<ext>.

    src 파일 hierarchy 가 2-tier 깊은 경우 (예: src/audio/decoder/X.ts) 의
    `<grandparent>/__tests__/X.test.ts` (= src/__tests__/X.test.ts) 매치.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str, content: str = "// stub\n") -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_grandparent_tests_match(self):
        # src 파일 = src/audio/decoder/X.ts
        # grandparent = src
        # 매치 위치 = src/__tests__/X.test.ts
        self._touch("src/audio/decoder/X.ts", "export function go() { return 1; }\n")
        self._touch("src/__tests__/X.test.ts", "test('ok', () => {})\n")
        path = str(Path(self._tmp) / "src/audio/decoder/X.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_grandparent_spec_match(self):
        self._touch("src/audio/decoder/Y.ts", "export const Y = 1;\n")
        self._touch("src/__tests__/Y.spec.ts", "test('ok', () => {})\n")
        path = str(Path(self._tmp) / "src/audio/decoder/Y.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")


class TestPathMatcherTier5_MonorepoSrcRoot(unittest.TestCase):
    """issue #469 결함 C — Tier 5: <src_root>/__tests__/<name>.{test,spec}.<ext>.

    monorepo `apps/<X>/src/...` 구조 cover. src_root = `apps/<X>/src`.
    예: jajang `apps/mobile/src/audio/AudioEngine.ts` 의 `apps/mobile/src/__tests__/AudioEngine.test.ts`.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str, content: str = "// stub\n") -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_monorepo_apps_mobile_src_audio_match(self):
        # src 파일 = apps/mobile/src/audio/AudioEngine.ts
        # src_root = apps/mobile/src
        # 매치 위치 = apps/mobile/src/__tests__/AudioEngine.test.ts
        self._touch(
            "apps/mobile/src/audio/AudioEngine.ts",
            "export class AudioEngine { play() {} }\n",
        )
        self._touch(
            "apps/mobile/src/__tests__/AudioEngine.test.ts",
            "test('ok', () => {})\n",
        )
        path = str(Path(self._tmp) / "apps/mobile/src/audio/AudioEngine.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_monorepo_deep_hierarchy_match(self):
        # src 파일 = apps/web/src/components/forms/LoginForm.ts (3-level deep)
        # src_root = apps/web/src
        self._touch(
            "apps/web/src/components/forms/LoginForm.ts",
            "export const LoginForm = () => null;\n",
        )
        self._touch(
            "apps/web/src/__tests__/LoginForm.test.ts",
            "test('login', () => {})\n",
        )
        path = str(Path(self._tmp) / "apps/web/src/components/forms/LoginForm.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")

    def test_monorepo_no_test_denied(self):
        # src 파일은 있는데 src_root 매치 test 부재 → deny
        self._touch(
            "apps/mobile/src/audio/AudioMixer.ts",
            "export class AudioMixer {}\n",
        )
        path = str(Path(self._tmp) / "apps/mobile/src/audio/AudioMixer.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "deny")

    def test_packages_src_root_match(self):
        # monorepo `packages/<X>/src/...` 패턴도 cover (src/ 마디 기준)
        self._touch(
            "packages/core/src/utils/format.ts",
            "export const format = (s) => s;\n",
        )
        self._touch(
            "packages/core/src/__tests__/format.test.ts",
            "test('format', () => {})\n",
        )
        path = str(Path(self._tmp) / "packages/core/src/utils/format.ts")
        self.assertEqual(decision(run_hook(path, self._tmp)), "allow")


class TestIsActiveGate(unittest.TestCase):
    """#597 커밋3 — tdd-guard 는 미활성 프로젝트에서 no-op (allow).

    DCNESS_FORCE_ENABLE 미설정 + temp cwd(whitelist 미등록) → is-active 게이트가
    deny 로직 도달 전에 allow 시킨다. (다른 6 wrapper 와 동일 게이트.)
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str, content: str = "// stub\n") -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def _run_inactive(self, file_path: str) -> subprocess.CompletedProcess:
        # harness 는 import 가능(PYTHONPATH)하되 활성 신호는 주지 않음 → is-active=inactive.
        env = {k: v for k, v in os.environ.items() if k != "DCNESS_FORCE_ENABLE"}
        env["PYTHONPATH"] = str(ROOT)
        return subprocess.run(
            ["bash", str(HOOK_PATH)],
            input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}}),
            capture_output=True, text=True, cwd=self._tmp, timeout=10, env=env,
        )

    def test_inactive_project_allows_even_without_test(self):
        # 활성이면 deny 였을 src 파일이, 미활성에선 게이트로 즉시 allow.
        path = self._touch(
            "src/biz.ts",
            "export function calc(a, b) { return a + b; }\n",
        )
        result = self._run_inactive(path)
        self.assertEqual(
            result.returncode, 0,
            f"미활성 프로젝트는 allow(exit 0) 여야 함. stderr={result.stderr!r}",
        )

    def test_active_project_still_denies(self):
        # 대조군 — DCNESS_FORCE_ENABLE=1 (run_hook 기본) 이면 동일 파일이 deny.
        path = self._touch(
            "src/biz2.ts",
            "export function calc2(a, b) { return a + b; }\n",
        )
        self.assertEqual(decision(run_hook(path, self._tmp)), "deny")


class TestBlockingSemantics(unittest.TestCase):
    """#597 커밋1 — deny = exit 2 + stderr reason (exit 1/JSON 아님)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self._tmp, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str, content: str = "// stub\n") -> str:
        p = Path(self._tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_deny_exits_2_with_stderr_reason(self):
        """테스트 부재 src → exit 2 + stderr 에 TDD GUARD reason."""
        path = self._touch(
            "src/biz.ts",
            "export function calc(a, b) { return a + b; }\n",
        )
        result = run_hook(path, self._tmp)
        self.assertEqual(result.returncode, 2, f"stdout={result.stdout}")
        self.assertIn("TDD GUARD", result.stderr)
        # 차단 reason 은 stderr 로 — stdout 에 deny JSON 을 더는 쓰지 않는다.
        self.assertNotIn("permissionDecision", result.stdout)

    def test_allow_exits_0(self):
        """매칭 테스트 존재 → exit 0 (allow)."""
        self._touch("src/biz.ts", "export const x = 1;\n")
        self._touch("src/biz.test.ts", "test('ok', () => {})\n")
        path = str(Path(self._tmp) / "src/biz.ts")
        result = run_hook(path, self._tmp)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
