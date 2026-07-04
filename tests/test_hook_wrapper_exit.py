"""test_hook_wrapper_exit — PreToolUse wrapper 의 blocking exit-code 검증 (#597 커밋1).

핸들러(`harness/hooks.py`)는 위반 시 `return 1` 을 유지한다. 그러나 CC 는 PreToolUse
hook 의 **exit 1 을 non-blocking error 로 취급해 도구를 그대로 진행**시킨다 (차단 안 됨).
따라서 wrapper 가 `RC=1` 을 `exit 2` 로 번역해야 실제 차단 + stderr 피드백이 발생한다.

본 모듈은 **실제 bash wrapper** 를 PPID 기반으로 실행해 그 번역을 검증한다
(핸들러 직접 호출은 `test_hooks.py` / e2e 는 `test_multisession_smoke.py`).

메커니즘: wrapper 는 `CC_PID=$PPID` 를 쓴다. subprocess.run(["bash", ...]) 의
bash 부모 = 본 테스트 프로세스이므로 cc_pid = os.getpid(). 세션 state 를 그 PID 로 박는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness.guard_telemetry import read_events

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_wrapper(
    script_name: str, stdin_payload: dict, *, cwd: Path
) -> subprocess.CompletedProcess:
    """hooks/<script_name> 를 실제 bash 로 실행 — CC_PID=$PPID=본 프로세스."""
    env = {
        k: v
        for k, v in os.environ.items()
        # infra 신호 해제 — 외부 활성 프로젝트 시뮬레이션 (file-guard 차단 성립 조건)
        if k not in ("CLAUDE_PLUGIN_ROOT", "DCNESS_INFRA")
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["DCNESS_FORCE_ENABLE"] = "1"  # temp cwd whitelist 미등록 → is-active 게이트 우회
    return subprocess.run(
        ["bash", str(REPO_ROOT / "hooks" / script_name)],
        input=json.dumps(stdin_payload),
        text=True,
        capture_output=True,
        cwd=str(cwd),
        env=env,
        timeout=15,
    )


class CatastrophicGateWrapperExitTests(unittest.TestCase):
    """catastrophic-gate.sh — 게이트 위반 시 exit 2 + stderr."""

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.cwd = Path(self._td.name)
        self.base = self.cwd / ".claude" / "harness-state"
        self.sid = "wrap-cata-sid"
        self.rid = "run-cata1234"
        self.cc_pid = os.getpid()  # bash wrapper 의 $PPID

        from harness.session_state import (
            start_run, update_live, write_pid_current_run, write_pid_session,
            _clear_default_base_cache,
        )
        _clear_default_base_cache()
        write_pid_session(self.cc_pid, self.sid, base_dir=self.base)
        update_live(self.sid, base_dir=self.base)
        start_run(self.sid, self.rid, "test", base_dir=self.base)
        write_pid_current_run(self.cc_pid, self.rid, base_dir=self.base)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _agent_payload(self, subagent: str, mode: str = "") -> dict:
        return {
            "sessionId": self.sid,
            "tool_input": {"subagent_type": subagent, "mode": mode},
        }

    def test_violation_exits_2_with_stderr(self) -> None:
        # engineer 직전 module-architect PASS 부재 → engineer 게이트 위반 → handler return 1.
        result = _run_wrapper(
            "catastrophic-gate.sh",
            self._agent_payload("engineer", "IMPL"),
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 2,
            f"위반은 exit 2 여야 차단됨. stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        self.assertIn("순서 차단 훅: engineer", result.stderr)
        events = read_events(base_dir=self.base)
        self.assertTrue(
            any(
                e.get("kind") == "guard_hit"
                and e.get("guard") == "catastrophic-gate"
                and e.get("category") == "order_gate"
                for e in events
            ),
            events,
        )

    def test_allow_exits_0(self) -> None:
        from harness.session_state import run_dir
        run_path = run_dir(self.sid, self.rid, base_dir=self.base)
        (run_path / "module-architect.md").write_text(
            "## 결론\nPASS\n", encoding="utf-8",
        )
        result = _run_wrapper(
            "catastrophic-gate.sh",
            self._agent_payload("engineer", "IMPL"),
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 0,
            f"통과는 exit 0. stderr={result.stderr!r}",
        )


class FileGuardWrapperExitTests(unittest.TestCase):
    """file-guard.sh — agent_boundary 위반 시 exit 2 + stderr."""

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.cwd = Path(self._td.name)
        self.base = self.cwd / ".claude" / "harness-state"
        self.sid = "wrap-fg-sid"
        self.cc_pid = os.getpid()

        from harness.session_state import (
            update_live, write_pid_session, _clear_default_base_cache,
        )
        _clear_default_base_cache()
        write_pid_session(self.cc_pid, self.sid, base_dir=self.base)
        # 활성 sub-agent = engineer (file-guard 가 active_agent 로 boundary 판정).
        update_live(self.sid, base_dir=self.base, active_agent="engineer")

    def tearDown(self) -> None:
        self._td.cleanup()

    def _file_payload(self, tool_name: str, **tool_input) -> dict:
        return {
            "sessionId": self.sid,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }

    def test_infra_write_exits_2(self) -> None:
        # engineer 가 인프라 path (hooks/) Write → DCNESS_INFRA_PATTERNS 차단 → return 1.
        result = _run_wrapper(
            "file-guard.sh",
            self._file_payload("Write", file_path="hooks/evil.sh"),
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 2,
            f"인프라 write 는 exit 2 여야 차단됨. stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        self.assertIn("agent-boundary", result.stderr)
        events = read_events(base_dir=self.base)
        self.assertTrue(
            any(
                e.get("kind") == "guard_hit"
                and e.get("guard") == "file-guard"
                and e.get("category") == "write_boundary"
                for e in events
            ),
            events,
        )

    def test_src_write_exits_0(self) -> None:
        # engineer 의 src/ Write 는 허용 → exit 0.
        result = _run_wrapper(
            "file-guard.sh",
            self._file_payload("Edit", file_path="src/foo.ts"),
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 0,
            f"src 편집은 exit 0. stderr={result.stderr!r}",
        )


if __name__ == "__main__":
    unittest.main()
