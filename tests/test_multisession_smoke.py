"""test_multisession_smoke — bash 훅 + Python 파이프라인 e2e + 멀티세션 격리.

Coverage:
    1. bash 훅 파이프라인 (session-start.sh / catastrophic-gate.sh) 종료코드 + 부수효과
    2. 두 동시 세션 (cc_pid 다름) — by-pid / live.json / run_dir 모두 격리
    3. catastrophic 룰 e2e — bash → python → exit code 1 + stderr 메시지

호환:
    - bash 가 자기 PPID 캡처해 python 호출하는 파이프라인 자체는 동일 PID (pytest 의 PID)
      이라 두 bash 호출이 같은 PID. 따라서 *격리 검증* 은 python CLI 직접 호출 (--cc-pid 명시) 로.
    - bash 파이프라인 검증은 "동작 가능 + 부수효과 있음" 까지만.

한계:
    - 실 Claude Code 환경의 PPID 신뢰성 / stdin payload 형식은 검증 안 함
      (별도 manual smoke 필요).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_bash_hook(
    script_name: str,
    stdin_payload: dict,
    *,
    cwd: Path,
) -> subprocess.CompletedProcess:
    """bash 훅 스크립트 실행 — stdin 으로 payload 전달."""
    script_path = REPO_ROOT / "hooks" / script_name
    return subprocess.run(
        ["bash", str(script_path)],
        input=json.dumps(stdin_payload),
        text=True,
        capture_output=True,
        cwd=str(cwd),
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            # smoke 테스트는 임시 cwd 라 whitelist 미등록 → 게이트 우회 강제 활성화
            "DCNESS_FORCE_ENABLE": "1",
        },
        timeout=10,
    )


def _run_python_hook(
    subcommand: str,
    stdin_payload: dict,
    cc_pid: int,
    *,
    cwd: Path,
) -> subprocess.CompletedProcess:
    """python -m harness.hooks 를 직접 호출 — cc_pid 명시 가능."""
    return subprocess.run(
        [
            sys.executable, "-m", "harness.hooks", subcommand,
            "--cc-pid", str(cc_pid),
        ],
        input=json.dumps(stdin_payload),
        text=True,
        capture_output=True,
        cwd=str(cwd),
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            # smoke 테스트는 임시 cwd 라 whitelist 미등록 → 게이트 우회 강제 활성화
            "DCNESS_FORCE_ENABLE": "1",
        },
        timeout=10,
    )


def _run_python_cli(
    subcommand_args: list,
    *,
    cwd: Path,
) -> subprocess.CompletedProcess:
    """python -m harness.session_state CLI 직접 호출."""
    return subprocess.run(
        [sys.executable, "-m", "harness.session_state", *subcommand_args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            # smoke 테스트는 임시 cwd 라 whitelist 미등록 → 게이트 우회 강제 활성화
            "DCNESS_FORCE_ENABLE": "1",
        },
        timeout=10,
    )


# ---------------------------------------------------------------------------
# bash pipeline smoke
# ---------------------------------------------------------------------------


class BashPipelineSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.cwd = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_session_start_bash_runs_successfully(self) -> None:
        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-A"},
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 0,
            f"stderr: {result.stderr}\nstdout: {result.stdout}",
        )

    def test_session_start_creates_artifacts(self) -> None:
        _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-A"},
            cwd=self.cwd,
        )
        # bash 의 PPID = pytest. 그 PPID 로 by-pid 파일 작성됨.
        by_pid_dir = self.cwd / ".claude" / "harness-state" / ".by-pid"
        self.assertTrue(by_pid_dir.exists(), "by-pid 디렉토리 생성 안 됨")
        files = list(by_pid_dir.iterdir())
        self.assertEqual(len(files), 1, f"by-pid 파일 1개 기대, 실제: {files}")
        sid = files[0].read_text().strip()
        self.assertEqual(sid, "smoke-ses-A")

        # live.json 도 생성됨
        live_path = (
            self.cwd / ".claude" / "harness-state"
            / ".sessions" / "smoke-ses-A" / "live.json"
        )
        self.assertTrue(live_path.exists())

    def test_session_start_inject_is_slim(self) -> None:
        """#596 — additionalContext 는 최소 활성 안내 (활성 토큰 + 코드 강제 gate
        + hook-first recovery) 만 담고, 문서 진입 매트릭스 / docs preload 지시는
        담지 않는다.

        하네스 모델 = "문서 선독 기반 compliance" 가 아니라 "hook 차단 → 그 자리 복구".
        따라서 SessionStart 가 docs 통독을 지시하면 회귀 (본 테스트가 차단)."""
        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-slim"},
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 0,
            f"stderr: {result.stderr}\nstdout: {result.stdout}",
        )
        # 임시 cwd 라 plugin.json 부재 → update 헤더 없이 inject JSON 단독.
        payload = json.loads(result.stdout)
        out = payload["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        ctx = out["additionalContext"]

        # 유지: 활성 토큰 + 코드 강제 gate + hook-first recovery 원칙
        self.assertIn("[dcness 활성 확인]", ctx)
        self.assertIn("catastrophic-gate", ctx)
        self.assertIn("file-guard", ctx)
        self.assertIn("tdd-guard", ctx)
        self.assertIn("stop-end-run", ctx)

        # 제거: 문서 진입 매트릭스 / docs preload 지시 / soft 필수·안티패턴 본문
        for forbidden in (
            "진입 매트릭스",
            "workflow-router.md",
            "loop-procedure.md",
            "issue-lifecycle.md",
            "git-spec.md",
            "안티패턴",
            "cost-aware",
            "메인 Claude 필수",
        ):
            self.assertNotIn(
                forbidden, ctx,
                f"slim inject 에 '{forbidden}' 잔존 — 문서 선독 지시 회귀 (#596)",
            )

    def test_invalid_sid_silent_no_artifacts(self) -> None:
        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "../invalid"},
            cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        # 잘못된 sid → 아무 파일도 생성 안 됨
        state_dir = self.cwd / ".claude" / "harness-state"
        if state_dir.exists():
            self.assertFalse(any(state_dir.rglob("*")))

    def test_catastrophic_gate_silent_when_no_session(self) -> None:
        result = _run_bash_hook(
            "catastrophic-gate.sh",
            {},  # 빈 payload
            cwd=self.cwd,
        )
        # sid 없음 → silent allow
        self.assertEqual(result.returncode, 0)


# ---------------------------------------------------------------------------
# 멀티세션 격리 (python CLI 직접 호출, cc_pid 명시)
# ---------------------------------------------------------------------------


class MultiSessionIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.cwd = Path(self._td.name)
        self.cc_pid_a = 12345
        self.cc_pid_b = 23456
        self.sid_a = "ses-AAAAA"
        self.sid_b = "ses-BBBBB"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _init_session(self, sid: str, cc_pid: int) -> None:
        result = _run_python_hook(
            "session-start",
            {"sessionId": sid},
            cc_pid,
            cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0, f"init failed: {result.stderr}")

    def test_two_sessions_by_pid_isolated(self) -> None:
        self._init_session(self.sid_a, self.cc_pid_a)
        self._init_session(self.sid_b, self.cc_pid_b)

        by_pid = self.cwd / ".claude" / "harness-state" / ".by-pid"
        self.assertEqual(
            (by_pid / str(self.cc_pid_a)).read_text().strip(), self.sid_a
        )
        self.assertEqual(
            (by_pid / str(self.cc_pid_b)).read_text().strip(), self.sid_b
        )

    def test_two_sessions_live_json_isolated(self) -> None:
        self._init_session(self.sid_a, self.cc_pid_a)
        self._init_session(self.sid_b, self.cc_pid_b)

        sessions = self.cwd / ".claude" / "harness-state" / ".sessions"
        live_a = json.loads((sessions / self.sid_a / "live.json").read_text())
        live_b = json.loads((sessions / self.sid_b / "live.json").read_text())

        self.assertEqual(live_a["session_id"], self.sid_a)
        self.assertEqual(live_b["session_id"], self.sid_b)
        # _meta envelope 자기참조 검증
        self.assertEqual(live_a["_meta"]["sessionId"], self.sid_a)
        self.assertEqual(live_b["_meta"]["sessionId"], self.sid_b)

    def test_concurrent_session_start_no_cross_contamination(self) -> None:
        """두 init-session 을 *동시* 실행해도 격리."""
        # 동시 spawn (Popen 으로 background)
        p_a = subprocess.Popen(
            [
                sys.executable, "-m", "harness.hooks",
                "session-start", "--cc-pid", str(self.cc_pid_a),
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(self.cwd),
            env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            # smoke 테스트는 임시 cwd 라 whitelist 미등록 → 게이트 우회 강제 활성화
            "DCNESS_FORCE_ENABLE": "1",
        },
        )
        p_b = subprocess.Popen(
            [
                sys.executable, "-m", "harness.hooks",
                "session-start", "--cc-pid", str(self.cc_pid_b),
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(self.cwd),
            env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            # smoke 테스트는 임시 cwd 라 whitelist 미등록 → 게이트 우회 강제 활성화
            "DCNESS_FORCE_ENABLE": "1",
        },
        )

        out_a, _ = p_a.communicate(json.dumps({"sessionId": self.sid_a}).encode(), timeout=10)
        out_b, _ = p_b.communicate(json.dumps({"sessionId": self.sid_b}).encode(), timeout=10)
        self.assertEqual(p_a.returncode, 0)
        self.assertEqual(p_b.returncode, 0)

        # 두 세션 격리 검증
        by_pid = self.cwd / ".claude" / "harness-state" / ".by-pid"
        self.assertEqual(
            (by_pid / str(self.cc_pid_a)).read_text().strip(), self.sid_a
        )
        self.assertEqual(
            (by_pid / str(self.cc_pid_b)).read_text().strip(), self.sid_b
        )


# ---------------------------------------------------------------------------
# catastrophic 룰 e2e (bash → python → exit code)
# ---------------------------------------------------------------------------


class CatastrophicRuleE2eTests(unittest.TestCase):
    """실 bash 훅 → python 파이프라인으로 §2.1 룰 발화 검증."""

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.cwd = Path(self._td.name)
        self.sid = "e2e-ses"
        self.cc_pid = 99999
        self.rid = "run-deadbeef"

        # 1. session-start
        _run_python_hook(
            "session-start",
            {"sessionId": self.sid},
            self.cc_pid,
            cwd=self.cwd,
        )
        # 2. begin-run via direct CLI (cc_pid override 가 begin-run 에 없음 — 헬퍼 직접)
        # 대신 start_run + write_pid_current_run 직접 호출 (test harness 안에서)
        sys.path.insert(0, str(REPO_ROOT))
        from harness.session_state import (
            start_run, write_pid_current_run,
        )
        # cwd 컨텍스트에서 작업하기 위해 chdir
        self._prev_cwd = os.getcwd()
        os.chdir(self.cwd)
        try:
            start_run(self.sid, self.rid, "e2e-test")
            write_pid_current_run(self.cc_pid, self.rid)
        finally:
            os.chdir(self._prev_cwd)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_engineer_without_plan_blocks_e2e(self) -> None:
        result = _run_python_hook(
            "pretooluse-agent",
            {
                "sessionId": self.sid,
                "tool_input": {
                    "subagent_type": "engineer",
                    "mode": "IMPL",
                },
            },
            self.cc_pid,
            cwd=self.cwd,
        )
        # #597 round5 — 정책 위반은 CLI 가 exit 2 (crash exit 1 과 구분, wrapper 차단 신호).
        self.assertEqual(result.returncode, 2, f"stdout: {result.stdout}")
        self.assertIn("§2.1.3", result.stderr)

    def test_engineer_with_plan_passes_e2e(self) -> None:
        # module-architect.md 작성
        run_path = (
            self.cwd / ".claude" / "harness-state"
            / ".sessions" / self.sid / "runs" / self.rid
        )
        (run_path / "module-architect.md").write_text(
            "PASS", encoding="utf-8",
        )
        result = _run_python_hook(
            "pretooluse-agent",
            {
                "sessionId": self.sid,
                "tool_input": {
                    "subagent_type": "engineer",
                    "mode": "IMPL",
                },
            },
            self.cc_pid,
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 0,
            f"기대 통과, stderr: {result.stderr}",
        )

    def test_pr_reviewer_without_validator_blocks_e2e(self) -> None:
        run_path = (
            self.cwd / ".claude" / "harness-state"
            / ".sessions" / self.sid / "runs" / self.rid
        )
        # engineer 흔적은 있는데 validator 검증 없음
        (run_path / "engineer-IMPL.md").write_text("IMPL_DONE", encoding="utf-8")
        result = _run_python_hook(
            "pretooluse-agent",
            {
                "sessionId": self.sid,
                "tool_input": {"subagent_type": "pr-reviewer", "mode": ""},
            },
            self.cc_pid,
            cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("§2.1.1", result.stderr)

if __name__ == "__main__":
    unittest.main()
