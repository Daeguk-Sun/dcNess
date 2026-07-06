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
        + hook-first recovery + next-work pointer) 만 담고, 문서 진입 매트릭스 /
        docs preload 지시는 담지 않는다.

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
        self.assertIn("docs/index.md", ctx)
        self.assertIn("docs/index.md` 가 없으므로", ctx)
        self.assertNotIn("의 `## 진행 상태 · 다음 작업` 포인터", ctx)
        self.assertIn("/next-work", ctx)

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

    def test_session_start_uses_index_pointer_when_section_exists(self) -> None:
        docs = self.cwd / "docs"
        docs.mkdir()
        (docs / "index.md").write_text(
            "# 프로젝트 문서 인덱스\n\n## 진행 상태 · 다음 작업\n",
            encoding="utf-8",
        )

        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-index-section"},
            cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        self.assertIn("docs/index.md` 의 `## 진행 상태 · 다음 작업` 포인터", ctx)
        self.assertIn("/next-work", ctx)
        self.assertNotIn("섹션이 없으므로", ctx)

    def test_session_start_falls_back_when_index_section_missing(self) -> None:
        docs = self.cwd / "docs"
        docs.mkdir()
        (docs / "index.md").write_text("# 기존 인덱스\n", encoding="utf-8")

        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-index-no-section"},
            cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        self.assertIn("현재 `docs/index.md` 에 `## 진행 상태 · 다음 작업` 섹션이 없으므로", ctx)
        self.assertIn("/init-dcness` 재실행으로 섹션을 보강", ctx)
        self.assertNotIn("docs/index.md` 의 `## 진행 상태 · 다음 작업` 포인터", ctx)

    def test_session_start_pointer_orchestrates_next_and_remaining(self) -> None:
        """#954 — next 포인터가 "뭐하지 / 남은 일 / 이제 뭐해야하지" 류 자연어 트리거에
        (1) warm 인계 우선, (2) 없으면 구조 소스로 phase 도출, (3) 다음 액션 1개 단정
        (메뉴 나열 금지) + 남은 일 브리핑, (4) 그 액션 컨텍스트만 focused preload 를
        지시하는지 검증한다. warm 인계 문구는 no-handoff 테스트가 막는 '대기 핸드오프'
        문자열을 쓰면 안 되므로 'warm 인계' 로 표현한다."""
        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-pointer-orch"},
            cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        # 넓어진 자연어 트리거 어휘. '프로젝트 상태' 는 hooks.md 계약(파일/섹션 유무별
        # 포인터·/next-work 안내)의 진입점이므로 어휘 확장 시 떨어뜨리면 회귀.
        for trigger in ("프로젝트 상태", "뭐하지", "남은 일", "이제 뭐해야하지", "남은 일 브리핑"):
            self.assertIn(trigger, ctx, f"트리거 어휘 '{trigger}' 누락")
        # warm 우선 (단, no-handoff 테스트가 막는 '대기 핸드오프' 문자열은 금지)
        self.assertIn("warm 인계", ctx)
        self.assertNotIn("대기 핸드오프", ctx)
        # 다음 액션 1개 단정 (메뉴 나열 아님) + 남은 일 브리핑 + focused preload
        self.assertIn("다음 액션 1개", ctx)
        self.assertIn("메뉴 나열", ctx)
        self.assertIn("focused preload", ctx)
        # /next-work 가 phase 를 증명 못해 '판정 보류' 하면 /design·/impl 를 지어내지
        # 않도록 단정을 확정 phase 조건부로 묶는다 (스크립트 보류 가드 우회 방지).
        self.assertIn("판정 보류", ctx)

    def test_session_start_injects_pending_handoff(self) -> None:
        """#953 — 이전 세션이 남긴 handoff 가 additionalContext 최상단에 주입되고
        주입 직후 archive 로 이동해 active 경로에서 사라진다 (무손실 clear)."""
        handoffs = self.cwd / ".dcness-work" / "handoffs"
        handoffs.mkdir(parents=True)
        (handoffs / "next-session.md").write_text(
            "# 다음 세션 핸드오프\n\n## 다음 액션\n- issue953 handoff 테스트 green 확인\n",
            encoding="utf-8",
        )

        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-handoff"},
            cwd=self.cwd,
        )
        self.assertEqual(
            result.returncode, 0,
            f"stderr: {result.stderr}\nstdout: {result.stdout}",
        )
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        # 핸드오프 내용이 최상단(활성 안내보다 위)에 주입
        self.assertIn("대기 핸드오프", ctx)
        self.assertIn("issue953 handoff 테스트 green 확인", ctx)
        self.assertLess(
            ctx.index("대기 핸드오프"), ctx.index("[dcness 활성 환경]"),
            "핸드오프가 활성 안내보다 위에 와야 한다",
        )

        # 소비 후 active 파일 제거 + archive 로 이동 (무손실)
        self.assertFalse(
            (handoffs / "next-session.md").exists(),
            "active 핸드오프가 archive 로 이동되지 않음 — 다음 세션 stale 재주입 위험",
        )
        archived = list((handoffs / "archive").glob("*.md"))
        self.assertEqual(len(archived), 1, f"archive 파일 1개 기대, 실제: {archived}")
        self.assertIn(
            "issue953 handoff 테스트 green 확인",
            archived[0].read_text(encoding="utf-8"),
        )

    def test_session_start_handoff_consumed_once(self) -> None:
        """#953 — claim-first: 한 번 소비된 handoff 는 다음 SessionStart 에 재주입되지
        않고 archive 사본도 늘지 않는다 (단일 소비자 계약, 순차 프록시)."""
        handoffs = self.cwd / ".dcness-work" / "handoffs"
        handoffs.mkdir(parents=True)
        (handoffs / "next-session.md").write_text(
            "# 핸드오프\n\n## 다음 액션\n- 단일 소비 검증\n",
            encoding="utf-8",
        )

        first = _run_bash_hook(
            "session-start.sh", {"sessionId": "smoke-ses-consume-1"}, cwd=self.cwd,
        )
        self.assertEqual(first.returncode, 0)
        ctx1 = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("단일 소비 검증", ctx1)

        second = _run_bash_hook(
            "session-start.sh", {"sessionId": "smoke-ses-consume-2"}, cwd=self.cwd,
        )
        self.assertEqual(second.returncode, 0)
        ctx2 = json.loads(second.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("대기 핸드오프", ctx2)
        self.assertNotIn("단일 소비 검증", ctx2)

        # archive 사본은 1개만 (두 번째 세션이 stale 재소비/재아카이브하지 않음)
        archived = list((handoffs / "archive").glob("*.md"))
        self.assertEqual(len(archived), 1, f"archive 1개 기대, 실제: {archived}")

    def test_session_start_two_handoffs_both_archived(self) -> None:
        """#953 — 같은 초에 소비되는 서로 다른 두 handoff 의 archive 사본이 파일명
        충돌 없이 둘 다 보존된다 (무손실 계약). ts-only 파일명이면 덮어써져 실패."""
        handoffs = self.cwd / ".dcness-work" / "handoffs"
        handoffs.mkdir(parents=True)

        (handoffs / "next-session.md").write_text(
            "# H1\n\n## 다음 액션\n- first-handoff\n", encoding="utf-8",
        )
        r1 = _run_bash_hook(
            "session-start.sh", {"sessionId": "smoke-ses-h1"}, cwd=self.cwd,
        )
        self.assertEqual(r1.returncode, 0)

        (handoffs / "next-session.md").write_text(
            "# H2\n\n## 다음 액션\n- second-handoff\n", encoding="utf-8",
        )
        r2 = _run_bash_hook(
            "session-start.sh", {"sessionId": "smoke-ses-h2"}, cwd=self.cwd,
        )
        self.assertEqual(r2.returncode, 0)

        archived = [
            p.read_text(encoding="utf-8")
            for p in (handoffs / "archive").glob("*.md")
        ]
        self.assertEqual(
            len(archived), 2,
            f"두 handoff 모두 보존돼야 함(무손실) — 실제 archive: {archived}",
        )
        joined = "\n".join(archived)
        self.assertIn("first-handoff", joined)
        self.assertIn("second-handoff", joined)

    def test_session_start_symlink_handoff_not_followed(self) -> None:
        """#953 — next-session.md 가 심링크면 따라가지 않는다. `.dcness-work/` 는
        writable 이라 심어진 심링크(→ .env 등)를 훅이 read 하면 로컬 시크릿이 모델
        컨텍스트로 유출되므로, 정규 파일이 아닐 때는 소비/주입하지 않는다 (codex P2)."""
        handoffs = self.cwd / ".dcness-work" / "handoffs"
        handoffs.mkdir(parents=True)
        secret = self.cwd / "secret.txt"
        secret.write_text("SECRET_CONTENT_LEAK\n", encoding="utf-8")
        (handoffs / "next-session.md").symlink_to(secret)

        result = _run_bash_hook(
            "session-start.sh", {"sessionId": "smoke-ses-symlink"}, cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("SECRET_CONTENT_LEAK", ctx, "심링크 타겟이 컨텍스트로 유출됨")
        self.assertNotIn("대기 핸드오프", ctx)
        # 심링크는 따라가 archive 로 옮기지도 않는다 (타겟 보존)
        self.assertTrue(secret.exists())

    def test_session_start_oversize_handoff_injects_pointer_not_dump(self) -> None:
        """#953 — 상한 초과 handoff 는 전문을 컨텍스트로 덤프하지 않고 archive 전문
        포인터만 주입한다 (slim-inject 보호 + exec 한도 회피, 전문은 무손실 보존)."""
        handoffs = self.cwd / ".dcness-work" / "handoffs"
        handoffs.mkdir(parents=True)
        bulk = "X" * 20000  # 16KB 상한 초과
        (handoffs / "next-session.md").write_text(
            f"# 대용량\n{bulk}\n", encoding="utf-8",
        )

        result = _run_bash_hook(
            "session-start.sh", {"sessionId": "smoke-ses-big"}, cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("XXXXXXXXXX", ctx, "대용량 handoff 전문이 컨텍스트로 덤프됨")
        self.assertIn("너무 큼", ctx, "상한 초과 포인터 메시지 부재")

        # 전문은 archive 사본에 보존 (무손실)
        archived = list((handoffs / "archive").glob("*.md"))
        self.assertEqual(len(archived), 1)
        self.assertIn("XXXXXXXXXX", archived[0].read_text(encoding="utf-8"))

    def test_session_start_no_handoff_is_noop(self) -> None:
        """#953 — handoff 파일 부재 시 훅은 기존 동작 그대로 (무해)."""
        result = _run_bash_hook(
            "session-start.sh",
            {"sessionId": "smoke-ses-no-handoff"},
            cwd=self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("대기 핸드오프", ctx)
        # 파일이 없으면 archive 디렉토리조차 만들지 않는다
        self.assertFalse((self.cwd / ".dcness-work" / "handoffs" / "archive").exists())

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
    """실 bash 훅 → python 파이프라인으로 catastrophic 게이트 발화 검증."""

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
        self.assertIn("순서 차단 훅: engineer", result.stderr)

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
        self.assertIn("순서 차단 훅: pr-reviewer", result.stderr)

if __name__ == "__main__":
    unittest.main()
