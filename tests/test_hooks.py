"""test_hooks — Claude Code 훅 핸들러 검증 (`harness/hooks.py`).

Coverage matrix:
    handle_session_start:
        - 정상 sid 추출 + by-pid 작성 + live.json 초기화
        - 잘못된 sid → silent skip (return 0)
        - cc_pid invalid → silent skip
        - 빈 stdin → silent skip
        - 기존 live.json 보존 (재호출 안전)

    handle_pretooluse_agent:
        - pr-reviewer 게이트 — engineer 산출물 이후 CODE_VALIDATION 없으면 차단
        - pr-reviewer 게이트 — engineer 변경 후 CODE_VALIDATION PASS 있으면 통과
        - pr-reviewer 게이트 — Lite 직접 구현처럼 engineer 산출물이 없으면 통과
        - engineer 게이트 — engineer 직전 module-architect PASS 없으면 차단
        - engineer 게이트 — module-architect.md 안 PASS 있으면 통과
        - engineer 게이트 — module-architect-N.md (occurrence) 안 PASS 도 인정
        - engineer 게이트 — engineer POLISH 모드는 plan 검사 skip
        - engineer 게이트 — run 에 기록된 design_doc 실존 시 module-architect 없이 통과
        - engineer 게이트 — design_doc 기록됐지만 디스크 부재면 차단 (fail-strict)
        - engineer 게이트 — 상대경로 기록 후 cwd 가 달라도 통과 (기록 시점 resolve)
        - engineer 게이트 — mode-suffixed prose(module-architect-COMPACT_PLAN.md) PASS 인정
        - 그 외 agent (architect MODULE_PLAN, code-validator 등) — run 외부에서도 통과
        - sid 없음 → silent allow
        - tool_input 비정상 → silent allow

    rid 결정:
        - by-pid-current-run 우선
        - 폴백: live.json 의 가장 최근 미완료 슬롯
        - 둘 다 없음 → ""
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Optional

from harness.hooks import (
    handle_posttooluse_agent,
    handle_posttooluse_file_op,
    handle_pretooluse_agent,
    handle_pretooluse_file_op,
    handle_session_start,
    handle_stop,
)
from harness.agent_trace import append as trace_append
from harness.agent_trace import read_all as read_trace
# issue #392 — redo_log 폐기
from harness.session_state import (
    read_live,
    read_pid_session,
    run_dir,
    session_dir,
    start_run,
    update_current_step,
    update_live,
    write_pid_current_run,
    write_pid_session,
)


# ---------------------------------------------------------------------------
# handle_session_start
# ---------------------------------------------------------------------------


class HandleSessionStartTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_happy_creates_by_pid_and_live(self) -> None:
        rc = handle_session_start(
            stdin_data={"sessionId": "abc-sid"},
            cc_pid=12345,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(read_pid_session(12345, base_dir=self.base), "abc-sid")
        live = read_live("abc-sid", base_dir=self.base)
        self.assertEqual(live["session_id"], "abc-sid")
        self.assertEqual(live["active_runs"], {})

    def test_session_id_3_variants(self) -> None:
        for key in ("session_id", "sessionId", "sessionid"):
            with TemporaryDirectory() as td:
                base = Path(td)
                rc = handle_session_start(
                    stdin_data={key: "test-sid"},
                    cc_pid=12345,
                    base_dir=base,
                )
                self.assertEqual(rc, 0)
                self.assertEqual(read_pid_session(12345, base_dir=base), "test-sid")

    def test_invalid_sid_silent(self) -> None:
        rc = handle_session_start(
            stdin_data={"sessionId": "../bad"},
            cc_pid=12345,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        # 아무것도 안 만들어짐
        self.assertFalse((self.base / ".by-pid" / "12345").exists())

    def test_missing_cc_pid_silent(self) -> None:
        rc = handle_session_start(
            stdin_data={"sessionId": "abc-sid"},
            cc_pid=None,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        self.assertFalse((self.base / ".by-pid").exists())

    def test_invalid_cc_pid_silent(self) -> None:
        rc = handle_session_start(
            stdin_data={"sessionId": "abc-sid"},
            cc_pid=0,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_empty_payload_silent(self) -> None:
        rc = handle_session_start(stdin_data={}, cc_pid=12345, base_dir=self.base)
        self.assertEqual(rc, 0)

    def test_idempotent_preserves_live(self) -> None:
        # 1차 호출 + start_run
        handle_session_start(
            stdin_data={"sessionId": "abc-sid"},
            cc_pid=12345,
            base_dir=self.base,
        )
        start_run("abc-sid", "run-aaaaaaaa", "test", base_dir=self.base)
        # 2차 호출 — 기존 active_runs 보존되어야 함
        handle_session_start(
            stdin_data={"sessionId": "abc-sid"},
            cc_pid=12345,
            base_dir=self.base,
        )
        live = read_live("abc-sid", base_dir=self.base)
        self.assertIn("run-aaaaaaaa", live.get("active_runs", {}))


# ---------------------------------------------------------------------------
# handle_pretooluse_agent — base setup
# ---------------------------------------------------------------------------


class _PreToolBase(unittest.TestCase):
    sid = "test-sid"
    rid = "run-12345678"
    cc_pid = 99999

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        # 기본 setup — session + run 활성
        write_pid_session(self.cc_pid, self.sid, base_dir=self.base)
        update_live(self.sid, base_dir=self.base)
        start_run(self.sid, self.rid, "test", base_dir=self.base)
        write_pid_current_run(self.cc_pid, self.rid, base_dir=self.base)
        self.run_path = run_dir(self.sid, self.rid, base_dir=self.base)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _payload(self, subagent: str, mode: str = "") -> dict:
        return {
            "sessionId": self.sid,
            "tool_input": {
                "subagent_type": subagent,
                "mode": mode,
            },
        }

    def _begin_step(self, agent: str, mode: str = "") -> None:
        update_current_step(
            self.sid, self.rid, agent, mode or None, base_dir=self.base,
        )


# ---------------------------------------------------------------------------
# engineer 게이트 — engineer 직전 plan READY 검사
# ---------------------------------------------------------------------------


class CatastrophicEngineerTests(_PreToolBase):
    def test_blocked_without_plan(self) -> None:
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_allowed_with_module_architect_pass(self) -> None:
        (self.run_path / "module-architect.md").write_text(
            "## 계획\n...\n## 결론\nPASS\n", encoding="utf-8",
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_polish_mode_skips_plan_check(self) -> None:
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "POLISH"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    # -- #709 — POLISH 면제의 effective mode 는 tool_input.mode ∪ current_step.mode --

    def _strict_impl_run(self, rid: str = "run-87650001") -> Path:
        # effective-mode fallback 은 strict entry_point(impl) 에서만 신뢰되므로
        # current_step.mode 의존 테스트는 strict impl run 으로 세팅한다.
        start_run(self.sid, rid, "impl", base_dir=self.base)
        write_pid_current_run(self.cc_pid, rid, base_dir=self.base)
        return run_dir(self.sid, rid, base_dir=self.base)

    def test_polish_via_current_step_when_toolinput_mode_absent(self) -> None:
        # impl-loop engine B 실전 — Agent 도구 스키마에 mode 파라미터가 없는 CC 빌드에선
        # tool_input.mode 가 안 실린다. begin-step 이 기록한 current_step.mode=POLISH 를
        # effective mode 로 봐야 POLISH 면제가 환경 무관하게 작동한다.
        rd = self._strict_impl_run()
        (rd / "build-worker.md").write_text("PASS\n", encoding="utf-8")
        update_current_step(
            self.sid, "run-87650001", "engineer", "POLISH", base_dir=self.base,
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer"),  # tool_input.mode 빈값 (실전 payload)
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_impl_still_blocked_when_current_step_mode_impl_and_no_artifact(self) -> None:
        # 회귀 가드 — current_step.mode=IMPL 이고 설계 산출물 없으면 여전히 차단.
        # effective-mode fallback 이 IMPL 까지 면제로 새지 않는다.
        self._strict_impl_run()
        update_current_step(
            self.sid, "run-87650001", "engineer", "IMPL", base_dir=self.base,
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer"),  # tool_input.mode 빈값
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_blocked_when_no_mode_anywhere_and_no_artifact(self) -> None:
        # 회귀 가드 — tool_input.mode 도 current_step.mode(부재) 도 POLISH 가 아니고
        # 설계 산출물도 없으면 차단. begin-step engineer(mode 없음) → current_step.mode=None.
        self._strict_impl_run()
        update_current_step(
            self.sid, "run-87650001", "engineer", None, base_dir=self.base,
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_polish_step_mode_ignored_in_nonstrict_run(self) -> None:
        # 게이트 약화 방향 방어 — 비-strict entry_point 에서는 current_step.mode 정합이
        # strict-conveyor 로 보장되지 않으므로 step_mode fallback 을 쓰지 않는다.
        # setUp 의 run 은 entry_point="test"(비-strict). current_step.mode=POLISH 여도
        # 산출물 없으면 차단(POLISH 누수 차단).
        self._begin_step("engineer", "POLISH")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer"),  # tool_input.mode 빈값
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_allowed_with_module_architect_occurrence(self) -> None:
        # module-architect-2.md (occurrence 카운터) 안 PASS 도 인정
        (self.run_path / "module-architect-2.md").write_text(
            "## 결론\nPASS\n", encoding="utf-8",
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_namespaced_engineer_does_not_bypass_gate(self) -> None:
        # #700 (codex P1) — strict-conveyor 가 namespaced 를 통과시키므로 engineer 게이트도
        # 정규화 비교한다. dcness:engineer 가 module-architect PASS 게이트를 우회하면 안 된다.
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("dcness:engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    # -- #701 — design_doc 실존 = module-architect PASS 의 등가 prerequisite --

    def _record_run_with_design_doc(self, rid: str, design_doc: str) -> None:
        """design_doc 검증은 cwd(repo root) 기준 — begin-run cwd 를 base 로 모사."""
        old_cwd = os.getcwd()
        os.chdir(self.base)
        try:
            start_run(
                self.sid, rid, "impl",
                base_dir=self.base, design_doc=design_doc,
            )
        finally:
            os.chdir(old_cwd)

    def _start_run_with_design_doc(self, design_doc: str) -> None:
        """begin-run --design-doc + begin-step engineer 경로 모사.

        entry_point=impl run 은 strict-conveyor 가 begin-step 을 강제하므로
        실제 풀 4-agent 시퀀스대로 current_step 까지 세팅 — 차단/통과가
        engineer 게이트에서 판정되도록 한다.
        """
        rid2 = "run-87654321"
        self._record_run_with_design_doc(rid2, design_doc)
        write_pid_current_run(self.cc_pid, rid2, base_dir=self.base)
        update_current_step(
            self.sid, rid2, "engineer", "IMPL", base_dir=self.base,
        )

    def _write_design_doc(self) -> Path:
        doc = (
            self.base / "docs" / "milestones" / "v01" / "epics"
            / "epic-01-x" / "impl" / "03-foo.md"
        )
        doc.parent.mkdir(parents=True)
        doc.write_text("# impl task\n", encoding="utf-8")
        return doc

    def test_allowed_with_merged_design_doc(self) -> None:
        # #701 — impl-loop 풀 4-agent: 설계(impl 문서)는 별도 run 에서 머지된 뒤
        # 진입하므로, run 에 기록된 design_doc 실존이 같은-run module-architect
        # PASS 없이도 engineer(IMPL) prerequisite 를 충족해야 한다.
        doc = self._write_design_doc()
        self._start_run_with_design_doc(str(doc))
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_blocked_when_design_doc_gone_from_disk(self) -> None:
        # 기록 시점엔 실존했지만 게이트 시점에 삭제된 design_doc → fail-strict 차단.
        # 차단 주체가 strict-conveyor 가 아닌 engineer 게이트임을 stderr 로 확정.
        from io import StringIO
        from contextlib import redirect_stderr

        doc = self._write_design_doc()
        self._start_run_with_design_doc(str(doc))
        doc.unlink()
        err = StringIO()
        with redirect_stderr(err):
            rc = handle_pretooluse_agent(
                stdin_data=self._payload("engineer", "IMPL"),
                cc_pid=self.cc_pid,
                base_dir=self.base,
            )
        self.assertEqual(rc, 1)
        self.assertIn("[catastrophic: engineer 게이트]", err.getvalue())

    def test_other_run_design_doc_does_not_unlock_current_run(self) -> None:
        # design_doc 은 *자기 run* 의 prerequisite 만 충족 — design_doc 없는 기존
        # run(setUp 의 self.rid)은 종전대로 차단 유지 (회귀 가드).
        doc = self._write_design_doc()
        self._record_run_with_design_doc("run-87654321", str(doc))
        # current run 은 여전히 setUp 의 design_doc 없는 run
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_design_doc_recorded_relative_survives_cwd_change(self) -> None:
        # 기록은 worktree cwd 에서 상대경로로, 게이트는 다른 cwd(hook 프로세스)
        # 에서 실행 — 기록 시점 resolve 절대화가 없으면 false-block 하는 회귀 가드.
        doc = self._write_design_doc()
        rel = doc.relative_to(self.base)
        self._start_run_with_design_doc(str(rel))
        # 게이트는 테스트 프로세스 cwd(레포 루트, self.base 아님)에서 실행된다.
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_allowed_with_mode_suffixed_module_architect_pass(self) -> None:
        # /impl Standard — module-architect:COMPACT_PLAN 의 prose 는
        # module-architect-COMPACT_PLAN.md 에 기록된다. 같은-run PASS 로 인정
        # 해야 engineer(IMPL) 가 진입 가능 (mode-suffixed 파일명 인식).
        (self.run_path / "module-architect-COMPACT_PLAN.md").write_text(
            "## 결론\nPASS\n", encoding="utf-8",
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# #714 — engineer 게이트 lane-aware 면제 (Lite lane + sub-agent 엔진)
# ---------------------------------------------------------------------------


class CatastrophicEngineerLiteLaneTests(_PreToolBase):
    """기록된 lane=lite 가 engineer 게이트의 설계 산출물 prerequisite 를 면제한다.

    Lite lane 은 정의상 설계도가 없어 module-architect PASS / design_doc 둘 다
    없다. 면제 경계는 *명시적으로 기록된* lane=lite 한정 — lane 미기록(impl-loop
    풀4 / 기본) 과 lane=standard 는 종전 차단 유지(면제 누수 차단). pr-reviewer ←
    code-validator 잔존 보호는 lane 무관 불변.
    """

    def setUp(self) -> None:
        super().setUp()
        self._set_slot(entry_point="impl")  # Lite lane = impl 구현 run (strict)

    def _set_slot(self, **fields) -> None:
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        active[self.rid].update(fields)
        update_live(self.sid, base_dir=self.base, active_runs=active)

    def test_lite_lane_allows_engineer_without_design_artifact(self) -> None:
        # 핵심 — lane=lite 면 설계 산출물 없이도 sub-agent engineer:IMPL 가 통과.
        self._set_slot(lane="lite")
        self._begin_step("engineer", "IMPL")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_lane_standard_still_requires_design_artifact(self) -> None:
        # 회귀 — lane=standard 는 설계 산출물 없으면 종전대로 차단(면제는 lite 한정).
        self._set_slot(lane="standard")
        self._begin_step("engineer", "IMPL")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_lane_none_still_requires_design_artifact(self) -> None:
        # 회귀 — lane 미기록(impl-loop 풀4 / 기본) impl run 은 설계 산출물 요구 유지.
        self._begin_step("engineer", "IMPL")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_lite_lane_does_not_weaken_pr_reviewer_gate(self) -> None:
        # 면제가 catastrophic 보호를 약화하지 않음 — Lite + 풀4 라도 engineer 산출물
        # 이후 pr-reviewer 는 code-validator PASS 없이는 여전히 차단(잔존 보호 불변).
        self._set_slot(lane="lite")
        (self.run_path / "engineer-IMPL.md").write_text("IMPL_DONE", encoding="utf-8")
        self._begin_step("pr-reviewer")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# pr-reviewer 게이트 — pr-reviewer 직전 validator PASS 검사
# ---------------------------------------------------------------------------


class CatastrophicPrReviewerTests(_PreToolBase):
    def test_no_engineer_write_allows(self) -> None:
        # engineer 호출 흔적 없으면 통과
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_engineer_write_without_validator_blocks(self) -> None:
        (self.run_path / "engineer-IMPL.md").write_text("IMPL_DONE", encoding="utf-8")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_namespaced_pr_reviewer_does_not_bypass_gate(self) -> None:
        # #700 (codex P1) — namespaced pr-reviewer 도 정규화 후 게이트 발동(우회 차단).
        (self.run_path / "engineer-IMPL.md").write_text("IMPL_DONE", encoding="utf-8")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("dcness:pr-reviewer", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_engineer_write_with_code_validator_pass_allows(self) -> None:
        (self.run_path / "engineer-IMPL.md").write_text("IMPL_DONE", encoding="utf-8")
        (self.run_path / "code-validator.md").write_text(
            "## 결론\nPASS\n", encoding="utf-8",
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_engineer_write_with_code_validator_occurrence_pass_allows(self) -> None:
        # occurrence (재호출) 도 인정
        (self.run_path / "engineer-IMPL.md").write_text("IMPL_DONE", encoding="utf-8")
        (self.run_path / "code-validator-2.md").write_text(
            "## 결론\nPASS\n", encoding="utf-8",
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# module-architect 게이트 — design 안 module-architect × N 첫 호출 직전
# architecture-validator PASS 필수 (PR B-4 부활, β-strong)
# ---------------------------------------------------------------------------


class _DesignLoopBase(unittest.TestCase):
    """design entry_point 컨텍스트 — module-architect 게이트 발동 조건."""

    sid = "test-sid-arch"
    rid = "run-archloop"
    cc_pid = 55555

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        write_pid_session(self.cc_pid, self.sid, base_dir=self.base)
        update_live(self.sid, base_dir=self.base)
        start_run(self.sid, self.rid, "design", base_dir=self.base)
        write_pid_current_run(self.cc_pid, self.rid, base_dir=self.base)
        self.run_path = run_dir(self.sid, self.rid, base_dir=self.base)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _payload(self, subagent: str, mode: str = "") -> dict:
        return {
            "sessionId": self.sid,
            "tool_input": {"subagent_type": subagent, "mode": mode},
        }

    def _begin_step(self, agent: str, mode: str = "") -> None:
        update_current_step(
            self.sid, self.rid, agent, mode or None, base_dir=self.base,
        )

    def _set_entry_point(self, entry_point: str) -> None:
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        active[self.rid]["entry_point"] = entry_point
        update_live(self.sid, base_dir=self.base, active_runs=active)


class CatastrophicArchitectureValidatorTests(_DesignLoopBase):
    def test_module_architect_first_call_blocked_without_arch_validator(self) -> None:
        self._begin_step("module-architect")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_module_architect_first_call_allowed_with_arch_validator_pass(self) -> None:
        self._begin_step("module-architect")
        (self.run_path / "architecture-validator.md").write_text(
            "## 결론\nPASS\n", encoding="utf-8",
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_module_architect_subsequent_call_skips_arch_validator_check(self) -> None:
        # 첫 호출 prose 이미 있음 → 후속 호출. gate 미발동.
        self._begin_step("module-architect")
        (self.run_path / "module-architect.md").write_text(
            "## 결론\nPASS\n", encoding="utf-8",
        )
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_gate_skipped_for_non_design_loop(self) -> None:
        """impl-task-loop 등 다른 entry_point 는 module-architect 게이트 미적용."""
        with TemporaryDirectory() as td:
            base = Path(td)
            sid, rid, cc_pid = "sid-impl", "run-impl1234", 44444
            write_pid_session(cc_pid, sid, base_dir=base)
            update_live(sid, base_dir=base)
            start_run(sid, rid, "impl", base_dir=base)
            write_pid_current_run(cc_pid, rid, base_dir=base)
            update_current_step(
                sid, rid, "module-architect", None, base_dir=base,
            )
            rc = handle_pretooluse_agent(
                stdin_data={"sessionId": sid, "tool_input": {"subagent_type": "module-architect", "mode": ""}},
                cc_pid=cc_pid,
                base_dir=base,
            )
            self.assertEqual(rc, 0)

    def test_design_entry_point_enforces_arch_validator_gate(self) -> None:
        self._begin_step("module-architect")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)


class TechReviewerRecallNotBlockedTests(_DesignLoopBase):
    """#609 — design 중 tech-reviewer 재호출은 코드 강제 차단하지 않는다.

    옛 #597 커밋7 의 부분 코드강제 (재호출 시 exit) 를 제거했다 (forcing function 은
    catastrophic 이 아님 — CLAUDE.md 대원칙). 재호출 비권장은 자연어 관례로만 남는다.
    in/out 양쪽 모두 통과(rc=0) — 차단 부활 회귀 방지.
    """

    def test_tech_reviewer_allowed_in_design_loop(self) -> None:
        # strict-conveyor gate(#604) 통과 위해 begin-step 으로 current_step 설정.
        self._begin_step("tech-reviewer")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("tech-reviewer"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_tech_reviewer_allowed_outside_design_loop(self) -> None:
        # 비-design run (entry_point=impl) 에서도 tech-reviewer 통과.
        with TemporaryDirectory() as td:
            base = Path(td)
            sid, rid, cc_pid = "sid-impl2", "run-impl5678", 33333
            write_pid_session(cc_pid, sid, base_dir=base)
            update_live(sid, base_dir=base)
            start_run(sid, rid, "impl", base_dir=base)
            write_pid_current_run(cc_pid, rid, base_dir=base)
            update_current_step(
                sid, rid, "tech-reviewer", None, base_dir=base,
            )
            rc = handle_pretooluse_agent(
                stdin_data={
                    "sessionId": sid,
                    "tool_input": {"subagent_type": "tech-reviewer", "mode": ""},
                },
                cc_pid=cc_pid,
                base_dir=base,
            )
            self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# issue #604 — active conveyor run strict begin-step gate
# ---------------------------------------------------------------------------


class StrictConveyorGateTests(_PreToolBase):
    def setUp(self) -> None:
        super().setUp()
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        active[self.rid]["entry_point"] = "impl"
        update_live(self.sid, base_dir=self.base, active_runs=active)

    def test_blocks_agent_without_begin_step(self) -> None:
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_impl_entry_point_is_strict(self) -> None:
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        active[self.rid]["entry_point"] = "impl"
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_impl_lite_pr_reviewer_allows_without_code_validator_when_no_engineer_step(self) -> None:
        self._begin_step("pr-reviewer")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_design_entry_point_is_strict_alias(self) -> None:
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        active[self.rid]["entry_point"] = "design"
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("pr-reviewer"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_allows_matching_begin_step(self) -> None:
        self._begin_step("module-architect")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_blocks_agent_mismatch(self) -> None:
        self._begin_step("system-architect")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_blocks_agent_mode_mismatch(self) -> None:
        # mode 가 *실제로 실린* 경우(인위적)엔 여전히 불일치 차단 — 방어 유지.
        self._begin_step("engineer", "IMPL")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("engineer", "POLISH"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_allows_moded_step_when_agent_omits_mode(self) -> None:
        # #700 Finding B — Agent 도구는 mode 를 실을 수 없어 항상 None. begin-step
        # code-validator VERIFY_ONLY 후 Agent(code-validator, mode 미지정)가 통과해야 한다.
        # (engineer 대신 catastrophic 게이트 없는 code-validator 로 strict-conveyor 순수 검증.)
        self._begin_step("code-validator", "VERIFY_ONLY")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("code-validator", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_allows_namespaced_agent_against_bare_begin_step(self) -> None:
        # #700 Finding A — begin-step bare + Agent namespaced → 정규화 후 일치.
        self._begin_step("module-architect")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("dcness:module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_allows_bare_agent_against_namespaced_begin_step(self) -> None:
        # #700 Finding A — begin-step namespaced 는 current_step.agent 가 bare 로
        # 정규화 저장돼야 하고(staging/end-step ValueError 회피), Agent bare 와 일치.
        self._begin_step("dcness:module-architect")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_allows_namespaced_moded_agent_full_cycle(self) -> None:
        # #700 AC3 (strict-conveyor 부분) — namespaced + moded step + mode 미지정 Agent 가
        # strict-conveyor 를 추가 우회 없이 통과해야 한다. engineer catastrophic 게이트의
        # lane-aware 화(풀4 engineer:IMPL)는 별개 작업 — Finding C follow-up.
        self._begin_step("code-validator", "VERIFY_ONLY")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("dcness:code-validator", ""),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_namespaced_agent_passing_strict_does_not_bypass_catastrophic_gate(self) -> None:
        # #700 (codex P1) — active impl run 에서 begin-step engineer 후 dcness:engineer 가
        # strict-conveyor 를 통과해도 engineer catastrophic 게이트(module-architect PASS)를
        # 우회하면 안 된다 (strict norm 과 게이트 norm 의 연계 검증).
        self._begin_step("engineer", "IMPL")
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("dcness:engineer", "IMPL"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_blocks_blank_current_step_agent(self) -> None:
        self._begin_step("module-architect")
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        slot = dict(active[self.rid])
        cur_step = dict(slot["current_step"])
        cur_step["agent"] = ""
        slot["current_step"] = cur_step
        active[self.rid] = slot
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_blocks_staged_previous_agent_result(self) -> None:
        self._begin_step("module-architect")
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        slot = dict(active[self.rid])
        cur_step = dict(slot["current_step"])
        cur_step["prose_file"] = str(self.run_path / "module-architect.md")
        slot["current_step"] = cur_step
        active[self.rid] = slot
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_blocks_logged_stale_current_step(self) -> None:
        self._begin_step("module-architect")
        steps_path = self.run_path / ".steps.jsonl"
        steps_path.write_text(
            json.dumps({"agent": "module-architect", "mode": None}) + "\n",
            encoding="utf-8",
        )

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_allows_same_agent_after_new_begin_step(self) -> None:
        steps_path = self.run_path / ".steps.jsonl"
        steps_path.write_text(
            json.dumps({"agent": "module-architect", "mode": None}) + "\n",
            encoding="utf-8",
        )
        self._begin_step("module-architect")

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_allows_same_agent_with_missing_count_and_same_second_timestamp(self) -> None:
        same_second = "2026-06-04T12:00:00+00:00"
        steps_path = self.run_path / ".steps.jsonl"
        steps_path.write_text(
            json.dumps({
                "agent": "module-architect",
                "mode": None,
                "ts": same_second,
            }) + "\n",
            encoding="utf-8",
        )
        self._begin_step("module-architect")
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        slot = dict(active[self.rid])
        cur_step = dict(slot["current_step"])
        cur_step.pop("steps_count_at_begin", None)
        cur_step["started_at"] = same_second
        slot["current_step"] = cur_step
        active[self.rid] = slot
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_skips_strict_gate_after_completed_run(self) -> None:
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        slot = dict(active[self.rid])
        slot["completed_at"] = "2026-06-04T12:00:00+00:00"
        active[self.rid] = slot
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_skips_strict_gate_after_finalized_run(self) -> None:
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        slot = dict(active[self.rid])
        slot["finalized_at"] = "2026-06-04T12:00:00+00:00"
        active[self.rid] = slot
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rc = handle_pretooluse_agent(
            stdin_data=self._payload("module-architect"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# rid 폴백 (by-pid-current-run 없을 때 live.json 에서 추정)
# ---------------------------------------------------------------------------


class RidResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        self.sid = "test-sid"
        update_live(self.sid, base_dir=self.base)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_falls_back_to_most_recent_uncompleted(self) -> None:
        # 두 run 존재. by-pid-current-run 없음.
        start_run(self.sid, "run-aaaaaaaa", "older", base_dir=self.base)
        # 약간 기다리지 않아도 ISO 같은 sec 단위 — 둘 다 같은 ts 가능
        # 강제로 서로 다른 ts 박기
        from harness.session_state import read_live as _rl
        live = _rl(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        if "run-aaaaaaaa" in active:
            active["run-aaaaaaaa"]["started_at"] = "2026-04-29T11:00:00+00:00"
        update_live(self.sid, base_dir=self.base, active_runs=active)
        start_run(self.sid, "run-bbbbbbbb", "newer", base_dir=self.base)
        live = _rl(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        active["run-bbbbbbbb"]["started_at"] = "2026-04-29T12:00:00+00:00"
        update_live(self.sid, base_dir=self.base, active_runs=active)

        rd_b = run_dir(self.sid, "run-bbbbbbbb", base_dir=self.base)
        # newer 의 run_dir 에 module-architect PASS 박음
        rd_b.mkdir(parents=True, exist_ok=True)
        (rd_b / "module-architect.md").write_text(
            "PASS", encoding="utf-8",
        )

        # by-pid 없이 호출 → live.json 의 newer 슬롯 선택 → READY 있어 통과
        rc = handle_pretooluse_agent(
            stdin_data={
                "sessionId": self.sid,
                "tool_input": {"subagent_type": "engineer", "mode": "IMPL"},
            },
            cc_pid=None,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# 비정상 입력 — silent allow
# ---------------------------------------------------------------------------


class SilentAllowTests(_PreToolBase):
    def test_no_session_id_silent(self) -> None:
        rc = handle_pretooluse_agent(
            stdin_data={"tool_input": {"subagent_type": "engineer", "mode": "IMPL"}},
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# 입력 비정상 — silent allow
# ---------------------------------------------------------------------------


class SilentAllowTests(_PreToolBase):
    def test_no_tool_input_silent(self) -> None:
        rc = handle_pretooluse_agent(
            stdin_data={"sessionId": self.sid},
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_non_dict_stdin_silent(self) -> None:
        rc = handle_pretooluse_agent(
            stdin_data="invalid",  # type: ignore[arg-type]
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# DCN-CHG-20260501-01 — handle_pretooluse_file_op + handle_posttooluse_agent
# ---------------------------------------------------------------------------


class FileOpAgentRecordTests(_PreToolBase):
    """PreToolUse Agent 통과 시 live.json.active_agent 기록 확인."""

    def test_active_agent_recorded_on_pass(self) -> None:
        # code-validator = HARNESS_ONLY 외 + run 컨텍스트 있음 → 통과
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("code-validator"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertEqual(live.get("active_agent"), "code-validator")

    def test_active_agent_with_mode(self) -> None:
        # validator + DESIGN_VALIDATION = HARNESS_ONLY 아님 (DESIGN_VALIDATION 미포함)
        rc = handle_pretooluse_agent(
            stdin_data=self._payload("validator", mode="DESIGN_VALIDATION"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertEqual(live.get("active_agent"), "validator")
        self.assertEqual(live.get("active_mode"), "DESIGN_VALIDATION")


class FileOpHookTests(_PreToolBase):
    """PreToolUse Edit/Write/Read/Bash agent_boundary 강제."""

    def setUp(self) -> None:
        super().setUp()
        # 모든 infra 신호 해제 — user 프로젝트 시뮬레이션.
        self._old_env = {}
        for k in ("DCNESS_INFRA", "CLAUDE_PLUGIN_ROOT"):
            self._old_env[k] = os.environ.get(k)
            os.environ.pop(k, None)
        # cwd 도 whitelist 외로 임시 이동.
        self._old_cwd = os.getcwd()
        os.chdir(str(self.base))

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        for k, v in self._old_env.items():
            if v is not None:
                os.environ[k] = v
        super().tearDown()

    def _file_op_payload(self, tool_name: str, **tool_input) -> dict:
        return {
            "sessionId": self.sid,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }

    def test_main_claude_passes(self) -> None:
        # active_agent 미설정 → 통과.
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Edit", file_path="hooks/x.sh"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_engineer_blocked_on_infra_edit(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload(
                "Edit", file_path="hooks/catastrophic-gate.sh"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_engineer_allowed_on_src_edit(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Edit", file_path="src/foo.ts"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_engineer_blocked_on_random_path(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Write", file_path="README.md"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_engineer_bash_sed_blocks_infra(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload(
                "Bash", command="sed -i 's/x/y/' hooks/foo.sh"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_bash_no_indicator_passes(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Bash", command="ls -la docs/"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_bash_git_push_blocked(self) -> None:
        # #597 커밋5 — sub-agent 의 git push 차단.
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Bash", command="git push -u origin x"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_bash_gh_issue_create_blocked(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload(
                "Bash", command="gh issue create --title x --body y"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_bash_gh_readonly_passes(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload(
                "Bash", command="gh issue list --state open"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_mcp_github_pr_mutation_blocked(self) -> None:
        # #597 커밋5 — sub-agent 의 GitHub MCP PR/repo mutation 차단.
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "mcp__github__merge_pull_request",
                "tool_input": {"pullNumber": 1},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)

    def test_mcp_github_issue_mutation_exempt(self) -> None:
        # codex P1 (round4) — issue mutation 은 per-agent tools gate 예외 → 통과.
        update_live(self.sid, base_dir=self.base, active_agent="code-validator")
        rc = handle_pretooluse_file_op(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "mcp__github__create_issue",
                "tool_input": {"title": "x"},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_mcp_github_read_passes(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "mcp__github__get_issue",
                "tool_input": {"issue_number": 5},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_opt_out_marker_bypasses_bash_mutation(self) -> None:
        # codex P2 (round6) — .no-dcness-guard 면 git push 도 통과 (opt-out 일관성).
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        (self.base / ".no-dcness-guard").write_text("")
        try:
            rc = handle_pretooluse_file_op(
                stdin_data=self._file_op_payload("Bash", command="git push origin main"),
                cc_pid=self.cc_pid,
                base_dir=self.base,
            )
            self.assertEqual(rc, 0)
        finally:
            (self.base / ".no-dcness-guard").unlink()

    def test_opt_out_marker_bypasses_mcp_mutation(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        (self.base / ".no-dcness-guard").write_text("")
        try:
            rc = handle_pretooluse_file_op(
                stdin_data={
                    "sessionId": self.sid,
                    "tool_name": "mcp__github__merge_pull_request",
                    "tool_input": {"pullNumber": 1},
                },
                cc_pid=self.cc_pid,
                base_dir=self.base,
            )
            self.assertEqual(rc, 0)
        finally:
            (self.base / ".no-dcness-guard").unlink()

    def test_main_claude_mutation_passes(self) -> None:
        # active_agent 미설정 (메인) → git push / MCP mutation 모두 통과.
        rc_push = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Bash", command="git push origin main"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        rc_mcp = handle_pretooluse_file_op(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "mcp__github__merge_pull_request",
                "tool_input": {"pullNumber": 1},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc_push, 0)
        self.assertEqual(rc_mcp, 0)

    def test_mcp_tool_passes_boundary_and_records_trace(self) -> None:
        # #255 W5 — mcp__* 도구는 boundary 검사 skip + trace pre append.
        # designer / code-validator false positive (prose-only 의심) 차단 의도.
        from harness.session_state import (
            start_run, generate_run_id, write_pid_current_run, write_pid_session,
        )
        from harness.agent_trace import histogram as _hist
        update_live(self.sid, base_dir=self.base, active_agent="designer")
        rid = generate_run_id()
        start_run(self.sid, rid, "designer", base_dir=self.base)
        write_pid_session(self.cc_pid, self.sid, base_dir=self.base)
        write_pid_current_run(self.cc_pid, rid, base_dir=self.base)
        rc = handle_pretooluse_file_op(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "mcp__pencil__batch_design",
                "tool_input": {"operations": "..."},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0, "mcp__* 도구는 boundary 차단 X — trace 만 기록")
        hist = _hist(self.sid, rid, base_dir=self.base)
        self.assertEqual(
            hist.get("mcp__pencil__batch_design", 0), 1,
            "mcp__* 도구가 histogram 에 1 카운트되어야 함",
        )


class PostToolUseAgentClearTests(_PreToolBase):
    def test_clears_active_agent(self) -> None:
        update_live(
            self.sid, base_dir=self.base,
            active_agent="engineer", active_mode="IMPL",
        )
        rc = handle_posttooluse_agent(
            stdin_data={"sessionId": self.sid},
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertNotIn("active_agent", live)
        self.assertNotIn("active_mode", live)

    def test_invalid_sid_silent(self) -> None:
        rc = handle_posttooluse_agent(
            stdin_data={"sessionId": "!"},
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# DCN-CHG-20260501-11 — sub 행동 trace append (Pre + Post)
# ---------------------------------------------------------------------------


class FileOpTraceTests(_PreToolBase):
    """handle_pretooluse_file_op 통과 시 agent-trace.jsonl pre append."""

    def setUp(self) -> None:
        super().setUp()
        self._old_env = {}
        for k in ("DCNESS_INFRA", "CLAUDE_PLUGIN_ROOT"):
            self._old_env[k] = os.environ.get(k)
            os.environ.pop(k, None)
        self._old_cwd = os.getcwd()
        os.chdir(str(self.base))

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        for k, v in self._old_env.items():
            if v is not None:
                os.environ[k] = v
        super().tearDown()

    def _payload_file(self, tool_name: str, **tool_input) -> dict:
        return {
            "sessionId": self.sid,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }

    def test_pre_trace_appended_on_pass(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_file("Edit", file_path="src/foo.py"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["phase"], "pre")
        self.assertEqual(entries[0]["agent"], "engineer")
        self.assertEqual(entries[0]["tool"], "Edit")
        self.assertEqual(entries[0]["input"], "src/foo.py")

    def test_no_trace_on_block(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_file("Edit", file_path="hooks/foo.sh"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(entries, [])

    def test_no_trace_when_main_claude(self) -> None:
        # active_agent 미설정 → trace 미기록.
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_file("Edit", file_path="src/foo.py"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(entries, [])

    def test_bash_input_in_trace(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_file("Bash", command="ls -la docs/"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["input"], "ls -la docs/")

    def test_long_input_truncated(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        long_cmd = "echo " + "x" * 500
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_file("Bash", command=long_cmd),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        # 200 cap + "..." suffix
        self.assertTrue(entries[0]["input"].endswith("..."))
        self.assertLessEqual(len(entries[0]["input"]), 210)


class PostToolUseFileOpTests(_PreToolBase):
    """handle_posttooluse_file_op — sub 행동 post trace append."""

    def _post_payload(
        self, tool_name: str, tool_response: dict, **tool_input
    ) -> dict:
        return {
            "sessionId": self.sid,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_response": tool_response,
        }

    def test_post_trace_appended(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_posttooluse_file_op(
            stdin_data=self._post_payload(
                "Bash",
                {"exit_code": 0, "stdout": "hello"},
                command="echo hello",
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["phase"], "post")
        self.assertEqual(entries[0]["tool"], "Bash")
        self.assertEqual(entries[0]["exit"], 0)
        self.assertEqual(entries[0]["stdout_size"], 5)

    def test_post_noop_when_main(self) -> None:
        # active_agent 미설정 → noop.
        rc = handle_posttooluse_file_op(
            stdin_data=self._post_payload("Edit", {}, file_path="src/x.py"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(entries, [])

    def test_post_records_is_error(self) -> None:
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_posttooluse_file_op(
            stdin_data=self._post_payload(
                "Bash",
                {"exit_code": 1, "is_error": True},
                command="false",
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(entries[0]["exit"], 1)
        self.assertTrue(entries[0]["is_error"])

    def test_post_invalid_sid_silent(self) -> None:
        rc = handle_posttooluse_file_op(
            stdin_data={"sessionId": "!"},
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# issue #598 — file-op self-attribution (payload agent_type/agent_id 우선)
# ---------------------------------------------------------------------------


class FileOpSelfAttributionTests(FileOpHookTests):
    """payload 의 agent_type 로 acting agent self-attribution — 동시 sub-agent 안전.

    공식 CC docs (code.claude.com/docs/en/hooks): PreToolUse/PostToolUse 가
    sub-agent 안에서 발화하면 payload 에 `agent_id` + `agent_type` 가 실린다.
    file-guard 가 공유 단일 슬롯(`live.active_agent`) 대신 *각 호출의 payload* 로
    acting agent 를 귀속하면, 두 번째 sub 가 active_agent 를 덮어써도 권한 판정이
    서로 안 섞인다 (issue #598 근본원인 해결).
    """

    def _payload_with_agent(self, tool_name, agent_type, **tool_input):
        d = self._file_op_payload(tool_name, **tool_input)
        d["agent_type"] = agent_type
        return d

    def test_payload_agent_type_overrides_active_agent_allow(self):
        # active_agent 가 다른 sub(code-validator: write 전면 불가)로 덮어써져 있어도
        # payload agent_type=engineer → engineer 매트릭스로 판정 → src 허용.
        update_live(self.sid, base_dir=self.base, active_agent="code-validator")
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_with_agent(
                "Edit", "engineer", file_path="src/foo.ts"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)  # code-validator 로 판정됐다면 차단(rc 1)됐을 것

    def test_payload_agent_type_overrides_active_agent_block(self):
        # active_agent=engineer(src 허용) 인데 payload agent_type=code-validator → code-validator 로 판정 → src 차단.
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_with_agent(
                "Edit", "code-validator", file_path="src/foo.ts"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)  # engineer 로 판정됐다면 통과(rc 0)됐을 것

    def test_payload_agent_type_enforced_without_active_agent(self):
        # active_agent 미설정(다른 sub 의 SubagentStop 으로 clear됨)이라도 payload
        # agent_type 있으면 sub 로 인지 → 경계 강제. 단일 슬롯 의존 시 BUG: 메인으로 오인 통과.
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_with_agent(
                "Write", "engineer", file_path="README.md"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)  # engineer 는 README write 불가

    def test_no_agent_type_falls_back_to_active_agent(self):
        # payload 에 agent_type 없으면 (구버전 CC) 기존 active_agent 폴백 유지.
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Write", file_path="README.md"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)  # 폴백: engineer README 차단 (기존 동작)

    def test_no_agent_type_no_active_agent_passes(self):
        # payload agent_type 없음 + active_agent 없음 → 메인 Claude → 통과.
        rc = handle_pretooluse_file_op(
            stdin_data=self._file_op_payload("Write", file_path="README.md"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_pre_trace_uses_payload_agent_type(self):
        # 통과한 file-op 의 pre-trace agent 도 payload agent_type 로 귀속.
        update_live(self.sid, base_dir=self.base, active_agent="code-validator")
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_with_agent(
                "Read", "engineer", file_path="src/foo.ts"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        pre = [e for e in entries if e.get("phase") == "pre"]
        self.assertTrue(pre)
        self.assertEqual(pre[-1]["agent"], "engineer")

    def test_namespaced_payload_agent_type_enforced(self):
        # issue #598 codex P1 — namespaced agent_type(dcness:code-validator)도 정규화되어 경계 강제.
        # 정규화 없으면 ALLOW_MATRIX 미정의 → pass-through bypass (code-validator 가 src write).
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_with_agent(
                "Edit", "dcness:code-validator", file_path="src/foo.ts"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 1)  # dcness:code-validator → code-validator → src write 불가

    def test_namespaced_payload_agent_type_allow(self):
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_with_agent(
                "Edit", "dcness:engineer", file_path="src/foo.ts"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)  # dcness:engineer → engineer → src 허용

    def test_namespaced_trace_agent_normalized(self):
        # namespaced payload 의 trace agent 도 canonical 로 기록.
        rc = handle_pretooluse_file_op(
            stdin_data=self._payload_with_agent(
                "Read", "dcness:engineer", file_path="src/foo.ts"
            ),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        pre = [e for e in entries if e.get("phase") == "pre"]
        self.assertTrue(pre)
        self.assertEqual(pre[-1]["agent"], "engineer")  # dcness: prefix 제거


class PostFileOpSelfAttributionTests(PostToolUseFileOpTests):
    """post trace 의 agent 귀속도 payload agent_type 우선 (issue #598)."""

    def test_post_trace_uses_payload_agent_type(self):
        update_live(self.sid, base_dir=self.base, active_agent="code-validator")
        d = self._post_payload(
            "Bash", {"exit_code": 0, "stdout": "x"}, command="echo x"
        )
        d["agent_type"] = "engineer"
        d["agent_id"] = "sub-eng-1"
        rc = handle_posttooluse_file_op(
            stdin_data=d, cc_pid=self.cc_pid, base_dir=self.base
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(entries[-1]["agent"], "engineer")  # active_agent(code-validator) 아님

    def test_post_trace_records_with_payload_only(self):
        # active_agent 미설정이라도 payload agent_type 있으면 trace 기록.
        d = self._post_payload("Bash", {"exit_code": 0}, command="ls")
        d["agent_type"] = "engineer"
        rc = handle_posttooluse_file_op(
            stdin_data=d, cc_pid=self.cc_pid, base_dir=self.base
        )
        self.assertEqual(rc, 0)
        entries = read_trace(self.sid, self.rid, base_dir=self.base)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["agent"], "engineer")


# ---------------------------------------------------------------------------
# DCN-CHG-20260501-13 — PostToolUse Agent histogram inject + auto redo_log
# ---------------------------------------------------------------------------


class PostToolUseAgentHistogramTests(_PreToolBase):
    """sub 종료 후 trace 집계 → redo_log 자동 append + stdout 메시지.

    #272 W3 진짜 fix — agent_id 폴백 제거. PreToolUse Agent 의 set_pending_agent
    + 시각 범위 매칭 (tool_use_id 검증) 으로 정확한 sub 식별.
    """

    def _simulate_pre(
        self, sub_type: str, *, tool_use_id: str = "toolu_test_default",
        mode=None,
    ) -> None:
        """PreToolUse Agent 시점 시뮬레이션 — set_pending_agent 박음."""
        from harness.session_state import set_pending_agent
        set_pending_agent(
            self.sid, self.rid,
            tool_use_id=tool_use_id, sub_type=sub_type, mode=mode,
            base_dir=self.base,
        )

    def _seed_trace(self, sub_type: str, tools: list) -> None:
        """sub 내부 file-op trace — set_pending_agent *후* 호출돼야 시각 범위 매칭."""
        for tool in tools:
            trace_append(self.sid, self.rid, {
                "phase": "pre", "agent": sub_type, "tool": tool,
            }, base_dir=self.base)
            trace_append(self.sid, self.rid, {
                "phase": "post", "agent": sub_type, "tool": tool,
            }, base_dir=self.base)

    def _post_payload(
        self, sub_type: str, *, tool_use_id: str = "toolu_test_default",
        prompt: str = "",
    ) -> dict:
        return {
            "sessionId": self.sid,
            "tool_use_id": tool_use_id,
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": sub_type,
                "prompt": prompt,
            },
        }

    # issue #392 — redo_log auto append 폐기. 관련 3 tests 삭제:
    #   - test_redo_log_records_measurement_only
    #   - test_low_call_no_anomaly_inject
    #   - test_high_repeat_no_decision_inject

    def test_clears_active_agent_still_works(self):
        update_live(
            self.sid, base_dir=self.base,
            active_agent="engineer", active_mode="IMPL",
        )
        self._simulate_pre("engineer", mode="IMPL")
        self._seed_trace("engineer", ["Read", "Bash"])
        rc = handle_posttooluse_agent(
            stdin_data=self._post_payload("engineer"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertNotIn("active_agent", live)
        self.assertNotIn("active_mode", live)

    def test_no_trace_no_event(self):
        # PreToolUse 안 박혔고 trace 비어있으면 → since_ts="" → hist={} → eval 발화 안 함.
        # issue #392 — redo_log auto append 폐기 후 검증 단순화 (read_redos 사용 X).
        rc = handle_posttooluse_agent(
            stdin_data={"sessionId": self.sid, "tool_name": "Agent"},
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)

    def test_prior_step_trace_excluded(self):
        """#272 W3 진짜 회귀 — 직전 step (engineer) 의 trace 가 *다음* sub 의
        histogram 에 새지 않음. 시각 범위 매칭의 핵심."""
        # 직전 engineer 가 file-op 다수 했음 (이미 끝남)
        self._seed_trace("engineer", ["Read", "Edit", "Edit", "Bash"])
        # 시각 진행 보장 — _now_iso 1초 단위라 sleep 1.1s 면 충분
        import time
        time.sleep(1.1)
        # 이제 메인이 pr-reviewer (prose-only) 호출 — PreToolUse Agent 박음
        self._simulate_pre("pr-reviewer", tool_use_id="toolu_pr1")
        # pr-reviewer 가 file-op 안 함 (prose-only)
        rc = handle_posttooluse_agent(
            stdin_data=self._post_payload("pr-reviewer", tool_use_id="toolu_pr1"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        # issue #392 — redo_log auto append 폐기로 측정 결과 검증 단순화.
        # pending_agents 가 정상 clear 되는지만 검증 (#272 W3 핵심, #598 multi-slot).
        from harness.session_state import read_live as _rl
        live = _rl(self.sid, base_dir=self.base)
        slot = live.get("active_runs", {}).get(self.rid, {})
        self.assertNotIn("pending_agents", slot)

    def test_histogram_filters_by_matched_agent(self):
        # issue #598 finding1 — 동시 sub 환경: since_ts 이후 다른 agent(code-validator)의 trace 가
        # 끝난 agent(engineer)의 histogram 에 섞이지 않음 (시각 범위 + agent 필터).
        import io
        import contextlib
        self._simulate_pre("engineer", tool_use_id="toolu_eng")
        for tool in ["Read", "Edit"]:
            trace_append(
                self.sid, self.rid,
                {"phase": "pre", "agent": "engineer", "tool": tool},
                base_dir=self.base,
            )
        for tool in ["Bash", "Bash", "Grep"]:
            trace_append(
                self.sid, self.rid,
                {"phase": "pre", "agent": "code-validator", "tool": tool},
                base_dir=self.base,
            )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = handle_posttooluse_agent(
                stdin_data=self._post_payload("engineer", tool_use_id="toolu_eng"),
                cc_pid=self.cc_pid, base_dir=self.base,
            )
        self.assertEqual(rc, 0)
        ctx = out.getvalue()
        self.assertIn("Read:1", ctx)
        self.assertIn("Edit:1", ctx)
        # 동시 code-validator 행동(Bash/Grep)은 engineer histogram 에 누설 안 됨.
        self.assertNotIn("Grep", ctx)
        self.assertNotIn("Bash", ctx)

    def test_tool_use_id_drift_logged(self):
        """tool_use_id 가 PreToolUse 와 PostToolUse 사이 다르면 stderr WARN."""
        import io
        import contextlib
        self._simulate_pre("engineer", tool_use_id="toolu_pre")
        self._seed_trace("engineer", ["Read", "Edit"])
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = handle_posttooluse_agent(
                stdin_data=self._post_payload(
                    "engineer", tool_use_id="toolu_post_DIFFERENT",
                ),
                cc_pid=self.cc_pid,
                base_dir=self.base,
            )
        self.assertEqual(rc, 0)
        stderr = buf.getvalue()
        self.assertIn("[hook agent-id]", stderr)
        self.assertIn("tool_use_id 불일치", stderr)
        # issue #392 — redo_log auto append 폐기. drift 신호는 stderr WARN 으로만 확인.

    def test_pending_agent_cleared_after_post(self):
        """PostToolUse Agent 후 live.json.active_runs[rid].pending_agents 제거."""
        from harness.session_state import read_live as _rl
        self._simulate_pre("engineer", tool_use_id="toolu_x")
        live = _rl(self.sid, base_dir=self.base)
        slot = live.get("active_runs", {}).get(self.rid, {})
        self.assertIn("pending_agents", slot)
        self.assertIn("toolu_x", slot["pending_agents"])
        self._seed_trace("engineer", ["Read"])
        handle_posttooluse_agent(
            stdin_data=self._post_payload("engineer", tool_use_id="toolu_x"),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        live2 = _rl(self.sid, base_dir=self.base)
        slot2 = live2.get("active_runs", {}).get(self.rid, {})
        self.assertNotIn("pending_agents", slot2)

    # issue #392 — test_prose_only_subtype_no_decision_inject 폐기.
    # redo_log auto append 매커니즘 자체 폐기되어 본 테스트 의미 없음.


# ---------------------------------------------------------------------------
# issue #598 — pending_agents multi-slot (tool_use_id 키) + 동시성 경고
# ---------------------------------------------------------------------------


class PendingAgentsMultiSlotTests(_PreToolBase):
    """set_pending_agent / clear_pending_agent 를 tool_use_id 키 multi-slot 으로 확장.

    동시 Agent 호출 시 각 tool_use_id 별 독립 추적 — 단일 슬롯이면 둘째가 첫째를
    덮어써 prose-staging 시각 범위/trace 귀속이 섞인다 (issue #598).
    """

    def test_set_two_tool_use_ids_both_present(self):
        from harness.session_state import set_pending_agent
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t1", sub_type="engineer",
            base_dir=self.base,
        )
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t2", sub_type="code-validator",
            base_dir=self.base,
        )
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.rid]
        self.assertIn("pending_agents", slot)
        self.assertEqual(set(slot["pending_agents"]), {"t1", "t2"})
        self.assertEqual(slot["pending_agents"]["t1"]["sub_type"], "engineer")
        self.assertEqual(slot["pending_agents"]["t2"]["sub_type"], "code-validator")

    def test_clear_by_tool_use_id_pops_only_match(self):
        from harness.session_state import set_pending_agent, clear_pending_agent
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t1", sub_type="engineer",
            base_dir=self.base,
        )
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t2", sub_type="code-validator",
            base_dir=self.base,
        )
        popped = clear_pending_agent(
            self.sid, self.rid, tool_use_id="t1", base_dir=self.base
        )
        self.assertEqual(popped["tool_use_id"], "t1")
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.rid]
        self.assertEqual(set(slot["pending_agents"]), {"t2"})

    def test_clear_last_removes_key(self):
        from harness.session_state import set_pending_agent, clear_pending_agent
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t1", sub_type="engineer",
            base_dir=self.base,
        )
        clear_pending_agent(
            self.sid, self.rid, tool_use_id="t1", base_dir=self.base
        )
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.rid]
        self.assertNotIn("pending_agents", slot)

    def test_clear_none_single_fallback_pops(self):
        # tool_use_id 미지정인데 슬롯 1개 → 폴백 pop (drift 시각 범위 보존).
        from harness.session_state import set_pending_agent, clear_pending_agent
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t1", sub_type="engineer",
            base_dir=self.base,
        )
        popped = clear_pending_agent(self.sid, self.rid, base_dir=self.base)
        self.assertIsNotNone(popped)
        self.assertEqual(popped["tool_use_id"], "t1")

    def test_clear_none_multiple_ambiguous_noop(self):
        # tool_use_id 미지정 + 여러 개 → 모호 → pop 안 함 (잘못된 슬롯 제거 방지).
        from harness.session_state import set_pending_agent, clear_pending_agent
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t1", sub_type="engineer",
            base_dir=self.base,
        )
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t2", sub_type="code-validator",
            base_dir=self.base,
        )
        popped = clear_pending_agent(self.sid, self.rid, base_dir=self.base)
        self.assertIsNone(popped)
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.rid]
        self.assertEqual(set(slot["pending_agents"]), {"t1", "t2"})

    def test_clear_unmatched_tuid_multiple_noop(self):
        # tool_use_id 매칭 없음 + 여러 개 → pop 안 함 (drift 폴백은 단일일 때만).
        from harness.session_state import set_pending_agent, clear_pending_agent
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t1", sub_type="engineer",
            base_dir=self.base,
        )
        set_pending_agent(
            self.sid, self.rid, tool_use_id="t2", sub_type="code-validator",
            base_dir=self.base,
        )
        popped = clear_pending_agent(
            self.sid, self.rid, tool_use_id="tX", base_dir=self.base
        )
        self.assertIsNone(popped)

    def test_clear_legacy_singular_absorbed(self):
        # 구버전 단일 슬롯(pending_agent) 잔존분 흡수 (in-flight 업그레이드 호환).
        from harness.session_state import clear_pending_agent
        live = read_live(self.sid, base_dir=self.base)
        active = live["active_runs"]
        active[self.rid]["pending_agent"] = {
            "tool_use_id": "old", "sub_type": "engineer",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        update_live(self.sid, base_dir=self.base, active_runs=active)
        popped = clear_pending_agent(
            self.sid, self.rid, tool_use_id="old", base_dir=self.base
        )
        self.assertIsNotNone(popped)
        self.assertEqual(popped["tool_use_id"], "old")
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.rid]
        self.assertNotIn("pending_agent", slot)


class PreAgentConcurrencyWarnTests(_PreToolBase):
    """PreToolUse Agent — 이미 미완 pending 상태에서 새 Agent 발사 시 동시성 경고 (issue #598)."""

    def _agent_payload(self, subagent, tool_use_id):
        return {
            "sessionId": self.sid,
            "tool_use_id": tool_use_id,
            "tool_input": {"subagent_type": subagent, "mode": ""},
        }

    def test_second_concurrent_agent_warns(self):
        import io
        import contextlib
        # 1st Agent — pending 박힘, 경고 없음.
        buf1 = io.StringIO()
        with contextlib.redirect_stderr(buf1):
            rc1 = handle_pretooluse_agent(
                stdin_data=self._agent_payload("code-validator", "toolu_a"),
                cc_pid=self.cc_pid, base_dir=self.base,
            )
        self.assertEqual(rc1, 0)
        self.assertNotIn("동시 sub-agent", buf1.getvalue())
        # 2nd Agent (1st 아직 미완) — stderr 동시성 경고.
        buf2 = io.StringIO()
        with contextlib.redirect_stderr(buf2):
            rc2 = handle_pretooluse_agent(
                stdin_data=self._agent_payload("code-validator", "toolu_b"),
                cc_pid=self.cc_pid, base_dir=self.base,
            )
        self.assertEqual(rc2, 0)
        self.assertIn("동시 sub-agent", buf2.getvalue())
        # 둘 다 pending_agents 에 존재 (multi-slot push).
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.rid]
        self.assertEqual(set(slot["pending_agents"]), {"toolu_a", "toolu_b"})

    def test_sequential_agents_no_warn(self):
        # 1st Agent → PostToolUse 로 clear → 2nd Agent: pending 비어있음 → 경고 없음.
        import io
        import contextlib
        handle_pretooluse_agent(
            stdin_data=self._agent_payload("code-validator", "toolu_a"),
            cc_pid=self.cc_pid, base_dir=self.base,
        )
        handle_posttooluse_agent(
            stdin_data={
                "sessionId": self.sid, "tool_use_id": "toolu_a",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "code-validator"},
            },
            cc_pid=self.cc_pid, base_dir=self.base,
        )
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            handle_pretooluse_agent(
                stdin_data=self._agent_payload("code-validator", "toolu_b"),
                cc_pid=self.cc_pid, base_dir=self.base,
            )
        self.assertNotIn("동시 sub-agent", buf.getvalue())


# ---------------------------------------------------------------------------
# issue #598 — SubagentStop 훅 (active_agent 신뢰 clear)
# ---------------------------------------------------------------------------


class SubagentStopClearTests(_PreToolBase):
    """SubagentStop 훅 — sub 종료 시 live.json.active_agent 신뢰 clear (issue #598).

    PostToolUse Agent 매칭(취약 — 메인 ctx)보다 신뢰도 높은 SubagentStop(sub 종료
    직발, agent_id+agent_type 동반)으로 단일 슬롯 clear 승격. match-guard 로 동시
    sub 의 슬롯 오클리어 방지. 차단 권한 사용 안 함 — 항상 exit 0.
    """

    def _payload(self, agent_type="", agent_id="sub-1"):
        return {
            "sessionId": self.sid,
            "agent_type": agent_type,
            "agent_id": agent_id,
            "hook_event_name": "SubagentStop",
        }

    def test_clears_matching_active_agent(self):
        from harness.hooks import handle_subagent_stop
        update_live(
            self.sid, base_dir=self.base,
            active_agent="engineer", active_mode="IMPL",
        )
        rc = handle_subagent_stop(
            self._payload(agent_type="engineer"), base_dir=self.base
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertNotIn("active_agent", live)
        self.assertNotIn("active_mode", live)

    def test_clears_when_agent_type_absent(self):
        # 구버전 payload (agent_type 부재) → best-effort 무조건 clear.
        from harness.hooks import handle_subagent_stop
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_subagent_stop(self._payload(agent_type=""), base_dir=self.base)
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertNotIn("active_agent", live)

    def test_no_clobber_on_mismatch(self):
        # 동시 sub: active_agent=code-validator 인데 engineer 의 SubagentStop → code-validator 슬롯 보존.
        from harness.hooks import handle_subagent_stop
        update_live(self.sid, base_dir=self.base, active_agent="code-validator")
        rc = handle_subagent_stop(
            self._payload(agent_type="engineer"), base_dir=self.base
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertEqual(live.get("active_agent"), "code-validator")

    def test_noop_when_no_active_agent(self):
        from harness.hooks import handle_subagent_stop
        rc = handle_subagent_stop(
            self._payload(agent_type="engineer"), base_dir=self.base
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertNotIn("active_agent", live)

    def test_clears_namespaced_agent_type(self):
        # issue #598 codex P1 — namespaced agent_type(dcness:engineer)도 정규화 후 매칭 clear.
        from harness.hooks import handle_subagent_stop
        update_live(self.sid, base_dir=self.base, active_agent="engineer")
        rc = handle_subagent_stop(
            self._payload(agent_type="dcness:engineer"), base_dir=self.base
        )
        self.assertEqual(rc, 0)
        live = read_live(self.sid, base_dir=self.base)
        self.assertNotIn("active_agent", live)

    def test_invalid_sid_silent(self):
        from harness.hooks import handle_subagent_stop
        rc = handle_subagent_stop({"sessionId": "!"}, base_dir=self.base)
        self.assertEqual(rc, 0)

    def test_empty_payload_silent(self):
        from harness.hooks import handle_subagent_stop
        rc = handle_subagent_stop({}, base_dir=self.base)
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# DCN-CHG-20260501-15 — PostToolUse Agent prose auto-staging
# ---------------------------------------------------------------------------


class PostToolUseAgentProseAutoStageTests(_PreToolBase):
    """handle_posttooluse_agent — tool_response.text → run_dir prose 자동 저장."""

    def _payload_with_prose(
        self, sub_type: str, agent: str, mode: Optional[str], prose: str
    ) -> dict:
        return {
            "sessionId": self.sid,
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": sub_type,
            },
            "tool_response": [{"type": "text", "text": prose}],
        }

    def _set_current_step(self, agent: str, mode: Optional[str]) -> None:
        from harness.session_state import update_current_step
        update_current_step(self.sid, self.rid, agent, mode, base_dir=self.base)

    def test_prose_staged_to_run_dir(self) -> None:
        self._set_current_step("code-validator", None)
        prose = "## 결과\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data=self._payload_with_prose("code-validator", "code-validator", None, prose),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertTrue(expected.exists())
        self.assertEqual(expected.read_text(encoding="utf-8"), prose)

    def test_prose_staged_with_mode(self) -> None:
        # #700 — legacy alias `validator` 는 begin-step 정규화로 canonical `code-validator`
        # 가 돼 prose 도 canonical 파일명으로 staging 된다(게이트 _has_pass 와 일치). mode
        # suffix 는 그대로 유지.
        self._set_current_step("validator", "PLAN_VALIDATION")
        prose = "## 결론\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data=self._payload_with_prose("validator", "validator", "PLAN_VALIDATION", prose),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = (
            session_dir(self.sid, base_dir=self.base) / "runs" / self.rid
            / "code-validator-PLAN_VALIDATION.md"
        )
        self.assertTrue(expected.exists())

    def test_prose_file_stored_in_current_step(self) -> None:
        self._set_current_step("module-architect", None)
        prose = "## 결론\nPASS\n"
        handle_posttooluse_agent(
            stdin_data=self._payload_with_prose("module-architect", "module-architect", None, prose),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        live = read_live(self.sid, base_dir=self.base) or {}
        slot = live.get("active_runs", {}).get(self.rid, {})
        cur_step = slot.get("current_step") or {}
        self.assertIn("prose_file", cur_step)
        self.assertTrue(cur_step["prose_file"].endswith("module-architect.md"))

    def test_empty_prose_no_staging(self) -> None:
        self._set_current_step("code-validator", None)
        rc = handle_posttooluse_agent(
            stdin_data=self._payload_with_prose("code-validator", "code-validator", None, "   "),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertFalse(expected.exists())

    def test_tool_response_dict_format_fallback(self) -> None:
        """dict 포맷 ({\"text\": ...}) 하위호환 — CC 포맷 변경 전 방어."""
        self._set_current_step("code-validator", None)
        prose = "## 결론\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "code-validator"},
                "tool_response": {"type": "text", "text": prose},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertTrue(expected.exists())
        self.assertEqual(expected.read_text(encoding="utf-8"), prose)

    def test_tool_response_string_format_fallback(self) -> None:
        """string 포맷 하위호환."""
        self._set_current_step("code-validator", None)
        prose = "## 결론\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "code-validator"},
                "tool_response": prose,
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertTrue(expected.exists())

    def test_tool_response_empty_list_no_staging(self) -> None:
        """빈 list → prose 없음."""
        self._set_current_step("code-validator", None)
        rc = handle_posttooluse_agent(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "code-validator"},
                "tool_response": [],
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertFalse(expected.exists())

    def test_no_tool_response_no_staging(self) -> None:
        self._set_current_step("code-validator", None)
        rc = handle_posttooluse_agent(
            stdin_data={"sessionId": self.sid, "tool_name": "Agent"},
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertFalse(expected.exists())

    def test_no_current_step_no_staging(self) -> None:
        prose = "## 결론\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data=self._payload_with_prose("code-validator", "code-validator", None, prose),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertFalse(expected.exists())

    def test_no_current_step_emits_diagnostic_stderr(self) -> None:
        """#272 W2 / #273 W1 — silent fail 제거. current_step 부재 시 stderr 진단 로그.

        post-agent-clear.sh 가 stderr → /tmp/dcness-hook-stderr.log 보존이라
        다음 run 에서 외부 환경 (jajang) staging 미동작 원인 진단 가능.
        """
        import io
        import contextlib

        prose = "## 결론\nPASS\n"
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = handle_posttooluse_agent(
                stdin_data=self._payload_with_prose("code-validator", "code-validator", None, prose),
                cc_pid=self.cc_pid,
                base_dir=self.base,
            )
        self.assertEqual(rc, 0)
        stderr = buf.getvalue()
        self.assertIn("[hook prose stage]", stderr)
        self.assertIn("current_step 부재", stderr)

    def test_robust_extraction_alt_type_recovers(self) -> None:
        """#272 W2 진짜 fix — list of dict 인데 type 이 'text' 아닌 'tool_result'
        같은 변형도 robust 추출. issue-232 1차 fix 가 type=='text' 한 형식만 본
        한계 회복."""
        self._set_current_step("code-validator", None)
        prose = "## 결론\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "code-validator"},
                "tool_response": [{"type": "tool_result", "content": prose}],
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertTrue(expected.exists(), msg="content 키 변형도 추출돼야 함")
        self.assertEqual(expected.read_text(encoding="utf-8"), prose)

    def test_robust_extraction_nested_dict(self) -> None:
        """nested dict 구조 — `{"result": {"text": prose}}` 같은 wrapping 도 cover."""
        self._set_current_step("code-validator", None)
        prose = "## 결론\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "code-validator"},
                "tool_response": {"result": {"text": prose}, "meta": {"n": 1}},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertTrue(expected.exists(), msg="nested dict 도 추출돼야 함")
        self.assertEqual(expected.read_text(encoding="utf-8"), prose)

    def test_robust_extraction_value_key(self) -> None:
        """`value` 키 변형 — 일부 SDK 가 사용."""
        self._set_current_step("code-validator", None)
        prose = "## 결론\nPASS\n"
        rc = handle_posttooluse_agent(
            stdin_data={
                "sessionId": self.sid,
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "code-validator"},
                "tool_response": {"value": prose},
            },
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        self.assertEqual(rc, 0)
        expected = session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "code-validator.md"
        self.assertTrue(expected.exists())

    def test_unextractable_emits_diagnostic_stderr(self) -> None:
        """robust extraction 이 *진짜* 못 뽑는 경우 — 텍스트 키 전무한 metadata 만."""
        import io
        import contextlib

        self._set_current_step("code-validator", None)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = handle_posttooluse_agent(
                stdin_data={
                    "sessionId": self.sid,
                    "tool_name": "Agent",
                    "tool_input": {"subagent_type": "code-validator"},
                    # text-like 키 (text/content/value/output) 전무 + 모든 값이 비-문자열
                    "tool_response": [{"type": "tool_result", "exit_code": 0}],
                },
                cc_pid=self.cc_pid,
                base_dir=self.base,
            )
        self.assertEqual(rc, 0)
        stderr = buf.getvalue()
        self.assertIn("[hook prose stage]", stderr)
        self.assertIn("robust extraction 실패", stderr)
        # 형식 정보 포함 — 외부 환경 디버그용
        self.assertIn("item0_type=tool_result", stderr)

    def test_occurrence_increments_on_repeat(self) -> None:
        import json

        self._set_current_step("engineer", None)
        # 첫 번째 end-step 기록을 .steps.jsonl 에 직접 박기 (base_dir 정합)
        steps_path = run_dir(self.sid, self.rid, base_dir=self.base) / ".steps.jsonl"
        steps_path.parent.mkdir(parents=True, exist_ok=True)
        steps_path.write_text(
            json.dumps({"agent": "engineer", "mode": None, "enum": "PASS"}) + "\n",
            encoding="utf-8",
        )
        # 두 번째 sub 호출 → occurrence=1 → engineer-1.md
        prose = "## 결론\nPASS\n"
        handle_posttooluse_agent(
            stdin_data=self._payload_with_prose("engineer", "engineer", None, prose),
            cc_pid=self.cc_pid,
            base_dir=self.base,
        )
        expected = (
            session_dir(self.sid, base_dir=self.base) / "runs" / self.rid / "engineer-1.md"
        )
        self.assertTrue(expected.exists())


class ExtractProseTextTests(unittest.TestCase):
    """#272 W2 — _extract_prose_text robust 매트릭스."""

    def test_str(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text("hello"), "hello")

    def test_empty_str(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text(""), "")
        self.assertEqual(_extract_prose_text("   "), "")

    def test_dict_text_key(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text({"text": "hi"}), "hi")

    def test_dict_content_key(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text({"content": "hi"}), "hi")

    def test_dict_value_key(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text({"value": "hi"}), "hi")

    def test_dict_text_priority_over_content(self):
        from harness.hooks import _extract_prose_text
        # text 가 우선
        self.assertEqual(
            _extract_prose_text({"text": "primary", "content": "secondary"}),
            "primary",
        )

    def test_list_of_text_block(self):
        from harness.hooks import _extract_prose_text
        # CC 의 issue-232 시점 형식
        self.assertEqual(
            _extract_prose_text([{"type": "text", "text": "hi"}]), "hi",
        )

    def test_list_of_alt_block(self):
        from harness.hooks import _extract_prose_text
        # type 다른 변형도 cover
        self.assertEqual(
            _extract_prose_text([{"type": "tool_result", "content": "hi"}]), "hi",
        )

    def test_list_first_non_empty(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(
            _extract_prose_text([{}, {"text": ""}, {"content": "found"}]),
            "found",
        )

    def test_nested_dict(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(
            _extract_prose_text({"result": {"text": "deep"}}), "deep",
        )

    def test_nested_list_dict(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(
            _extract_prose_text({"data": [{"value": "x"}]}), "x",
        )

    def test_empty_dict(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text({}), "")

    def test_empty_list(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text([]), "")

    def test_none(self):
        from harness.hooks import _extract_prose_text
        self.assertEqual(_extract_prose_text(None), "")

    def test_metadata_only(self):
        from harness.hooks import _extract_prose_text
        # text-like 키 전무 + 값들이 모두 비-문자열
        self.assertEqual(
            _extract_prose_text([{"type": "tool_result", "exit_code": 0}]),
            "",
        )

    def test_depth_limit_no_crash(self):
        from harness.hooks import _extract_prose_text
        # 의도적으로 깊은 nesting — 무한 재귀 방어 검증
        deep = {"a": "x"}
        for _ in range(50):
            deep = {"a": deep}
        # depth 16 초과는 "" 반환 (crash X)
        result = _extract_prose_text(deep)
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# handle_stop — issue #382 Stop hook (가드 로직 단위 테스트)
# ---------------------------------------------------------------------------


class StopHookGuardTests(unittest.TestCase):
    """Stop hook 의 *조건 검사 가드* 만 단위 검증.

    실제 end-run 발사 (in-process _cli_end_run) 는 integration 영역 —
    jajang 같은 활성 프로젝트에서 round-trip 검증.
    """

    def test_stop_hook_active_skips_immediately(self):
        # 무한 루프 가드 — Claude Code 공식 docs §"Stop hook runs forever"
        rc = handle_stop(stdin_data={"stop_hook_active": True})
        self.assertEqual(rc, 0)

    def test_invalid_stdin_skips(self):
        rc = handle_stop(stdin_data=None)
        self.assertEqual(rc, 0)
        rc = handle_stop(stdin_data="not a dict")  # type: ignore[arg-type]
        self.assertEqual(rc, 0)

    def test_empty_dict_no_sid_skips(self):
        # sid/rid auto-detect 실패 → skip
        rc = handle_stop(stdin_data={})
        self.assertEqual(rc, 0)

    def test_current_step_none_after_end_step_still_allows_end_run_candidate(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from harness.session_state import run_dir, start_run, update_live

        sid = "sid-stop-current-step-none"
        rid = "run-feedbeef"
        with TemporaryDirectory() as td:
            base = Path(td)
            update_live(sid, base_dir=base)
            start_run(sid, rid, "impl", base_dir=base)
            steps_path = run_dir(sid, rid, base_dir=base) / ".steps.jsonl"
            steps_path.write_text(
                json.dumps({"agent": "pr-reviewer", "mode": None}) + "\n",
                encoding="utf-8",
            )

            env = {"DCNESS_SESSION_ID": sid, "DCNESS_RUN_ID": rid}
            with patch.dict(os.environ, env, clear=False), patch(
                "harness.session_state._cli_end_run", return_value=0
            ) as end_run:
                rc = handle_stop(stdin_data={}, base_dir=base)

        self.assertEqual(rc, 0)
        end_run.assert_called_once()

    def test_finalized_without_run_finished_is_end_run_candidate(self):
        """이슈 #587 (codex review) — finalize-run 후 end-run 까먹어 run_finished 없으면 Stop 이 복구."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from harness import ledger
        from harness.session_state import read_live, run_dir, start_run, update_live

        sid = "sid-finalize-only"
        rid = "run-cafe1234"
        with TemporaryDirectory() as td:
            base = Path(td)
            update_live(sid, base_dir=base)
            start_run(sid, rid, "impl", base_dir=base)
            prose_path = run_dir(sid, rid, base_dir=base) / "pr-reviewer.md"
            prose_path.write_text("ok", encoding="utf-8")
            ledger.append_step_completed(
                sid, rid, "pr-reviewer", None, "PROSE_LOGGED", "ok", prose_path, base_dir=base)
            # finalize-run 흉내 — finalized_at 세팅, run_finished 는 없음
            live = read_live(sid, base_dir=base)
            slot = dict(live["active_runs"][rid])
            slot["finalized_at"] = "2026-06-05T00:00:00+00:00"
            active = dict(live["active_runs"])
            active[rid] = slot
            update_live(sid, base_dir=base, active_runs=active)

            env = {"DCNESS_SESSION_ID": sid, "DCNESS_RUN_ID": rid}
            with patch.dict(os.environ, env, clear=False), patch(
                "harness.session_state._cli_end_run", return_value=0
            ) as end_run:
                rc = handle_stop(stdin_data={}, base_dir=base)
        self.assertEqual(rc, 0)
        end_run.assert_called_once()

    def test_finalized_with_run_finished_skips(self):
        """run_finished 가 이미 있으면 (run 닫힘) Stop 이 end-run 재발사 안 함."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from harness import ledger
        from harness.session_state import read_live, run_dir, start_run, update_live

        sid = "sid-already-finished"
        rid = "run-beef5678"
        with TemporaryDirectory() as td:
            base = Path(td)
            update_live(sid, base_dir=base)
            start_run(sid, rid, "impl", base_dir=base)
            prose_path = run_dir(sid, rid, base_dir=base) / "pr-reviewer.md"
            prose_path.write_text("ok", encoding="utf-8")
            ledger.append_step_completed(
                sid, rid, "pr-reviewer", None, "PROSE_LOGGED", "ok", prose_path, base_dir=base)
            ledger.append_event(sid, rid, "run_finished", base_dir=base)
            live = read_live(sid, base_dir=base)
            slot = dict(live["active_runs"][rid])
            slot["finalized_at"] = "2026-06-05T00:00:00+00:00"
            active = dict(live["active_runs"])
            active[rid] = slot
            update_live(sid, base_dir=base, active_runs=active)

            env = {"DCNESS_SESSION_ID": sid, "DCNESS_RUN_ID": rid}
            with patch.dict(os.environ, env, clear=False), patch(
                "harness.session_state._cli_end_run", return_value=0
            ) as end_run:
                rc = handle_stop(stdin_data={}, base_dir=base)
        self.assertEqual(rc, 0)
        end_run.assert_not_called()


# ---------------------------------------------------------------------------
# _maybe_emit_continuation_signal — issue #469 결함 A
# ---------------------------------------------------------------------------


class StopHookContinuationSignalTests(unittest.TestCase):
    """issue #469 결함 A — 중간 step PASS 후 메인 turn 자동 발화 신호.

    `_maybe_emit_continuation_signal` 단위 검증. handle_stop 의 신규 분기는
    본 helper 가 True 반환 시 즉시 return 0 + JSON 출력만 박음 — helper
    단위로 충분.
    """

    SID = "12345678-1234-4321-abcd-1234567890ab"
    RID = "run-deadbeef"

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self._tmp.name)
        self.run_dir_path = (
            self.base_dir / "sessions" / self.SID / "runs" / self.RID
        )
        self.run_dir_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_prose(self, agent: str, conclusion_line: str, mode: str = "") -> None:
        suffix = f"-{mode}" if mode else ""
        path = self.run_dir_path / f"{agent}{suffix}.md"
        # 끝 15줄 안 결론 enum 매칭 위해 마지막 줄에 박음
        path.write_text(
            "## Prose\n\n작업 요약 prose.\n\n" + conclusion_line + "\n",
            encoding="utf-8",
        )

    def _slot(self, *, run_dir: str = None, stop_block_count=None) -> Dict[str, Any]:
        slot: Dict[str, Any] = {
            "run_id": self.RID,
            "started_at": "2026-05-22T00:00:00+00:00",
            "run_dir": run_dir if run_dir is not None else str(self.run_dir_path),
        }
        if stop_block_count is not None:
            slot["stop_block_count"] = stop_block_count
        return slot

    def _invoke(self, *, slot, last_agent, last_mode=None):
        from harness.hooks import _maybe_emit_continuation_signal
        active = {self.RID: slot}
        # stdout capture
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = _maybe_emit_continuation_signal(
                sid=self.SID, rid=self.RID, slot=slot, active=active,
                last_agent=last_agent, last_mode=last_mode,
                base_dir=self.base_dir,
            )
        return result, buf.getvalue()

    def test_build_worker_pass_emits_block(self):
        # PASS + 중간 agent → block decision JSON 박음
        self._write_prose("build-worker", "[task1 · 01] PASS")
        slot = self._slot()
        result, stdout = self._invoke(slot=slot, last_agent="build-worker")
        self.assertTrue(result)
        payload = json.loads(stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("build-worker", payload["reason"])
        self.assertIn("PASS", payload["reason"])

    def test_pr_reviewer_terminal_skips(self):
        # pr-reviewer 는 종료 agent — PASS/LGTM 박혀있어도 block 안 박음
        self._write_prose("pr-reviewer", "LGTM — merge 권고")
        slot = self._slot()
        result, stdout = self._invoke(slot=slot, last_agent="pr-reviewer")
        self.assertFalse(result)
        self.assertEqual(stdout, "")

    def test_fail_enum_skips(self):
        # FAIL → 메인 사용자 위임 영역 — block 안 박음
        self._write_prose("code-validator", "전반적 FAIL — 4 항목 위반")
        slot = self._slot()
        result, stdout = self._invoke(slot=slot, last_agent="code-validator")
        self.assertFalse(result)
        self.assertEqual(stdout, "")

    def test_no_conclusion_enum_skips(self):
        # 결론 enum 부재 → block 안 박음
        self._write_prose("build-worker", "작업 요약만 박음 — 결론 표기 없음")
        slot = self._slot()
        result, stdout = self._invoke(slot=slot, last_agent="build-worker")
        self.assertFalse(result)
        self.assertEqual(stdout, "")

    def test_prose_file_missing_skips(self):
        # prose file 자체 없음 → block 안 박음 (run_dir 만 박힘)
        slot = self._slot()
        result, stdout = self._invoke(slot=slot, last_agent="build-worker")
        self.assertFalse(result)
        self.assertEqual(stdout, "")

    def test_block_count_max_skips(self):
        # block count ≥ _STOP_BLOCK_COUNT_MAX (2) → 진짜 종료 의도 인정, skip
        from harness.hooks import _STOP_BLOCK_COUNT_MAX
        self._write_prose("build-worker", "[task1] PASS")
        slot = self._slot(stop_block_count={"build-worker:": _STOP_BLOCK_COUNT_MAX})
        result, stdout = self._invoke(slot=slot, last_agent="build-worker")
        self.assertFalse(result)
        self.assertEqual(stdout, "")

    def test_block_count_increments_and_persists(self):
        # 1차 호출 후 stop_block_count 가 live.json 에 +1 박힘
        self._write_prose("engineer", "IMPL_DONE — 변경 완료", mode="IMPL")
        slot = self._slot()
        result, _ = self._invoke(slot=slot, last_agent="engineer", last_mode="IMPL")
        self.assertTrue(result)

        # live.json 에 persist 됐는지 확인
        from harness.session_state import read_live
        live = read_live(self.SID, base_dir=self.base_dir)
        self.assertIsNotNone(live)
        persisted_slot = live["active_runs"][self.RID]
        self.assertEqual(
            persisted_slot["stop_block_count"]["engineer:IMPL"], 1,
        )

    def test_engineer_impl_done_block(self):
        # engineer mode 박힘 케이스 — prose path = engineer-IMPL.md
        self._write_prose("engineer", "IMPL_DONE — 6 파일 변경", mode="IMPL")
        slot = self._slot()
        result, stdout = self._invoke(slot=slot, last_agent="engineer", last_mode="IMPL")
        self.assertTrue(result)
        payload = json.loads(stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("engineer-IMPL", payload["reason"])
        self.assertIn("IMPL_DONE", payload["reason"])

    def test_missing_run_dir_skips(self):
        # slot.run_dir 부재 → block 안 박음
        slot = self._slot(run_dir="")  # 빈 문자열
        result, stdout = self._invoke(slot=slot, last_agent="build-worker")
        self.assertFalse(result)
        self.assertEqual(stdout, "")


# ---------------------------------------------------------------------------
# _shorten_path / _summarize_input path 단축 — issue #408
# ---------------------------------------------------------------------------


class ShortenPathTests(unittest.TestCase):
    """#408 — absolute path → cwd 기준 relative 단축."""

    def test_cwd_path_shortened(self):
        from harness.hooks import _shorten_path
        cwd = str(Path.cwd().resolve())
        self.assertEqual(_shorten_path(cwd + "/src/foo.ts"), "src/foo.ts")

    def test_outside_cwd_preserved(self):
        from harness.hooks import _shorten_path
        self.assertEqual(_shorten_path("/tmp/outside.txt"), "/tmp/outside.txt")

    def test_relative_path_preserved(self):
        from harness.hooks import _shorten_path
        self.assertEqual(_shorten_path("relative.ts"), "relative.ts")

    def test_empty_preserved(self):
        from harness.hooks import _shorten_path
        self.assertEqual(_shorten_path(""), "")

    def test_summarize_input_read_uses_shortened(self):
        from harness.hooks import _summarize_input
        cwd = str(Path.cwd().resolve())
        result = _summarize_input("Read", {"file_path": cwd + "/harness/hooks.py"})
        self.assertEqual(result, "harness/hooks.py")

    def test_summarize_input_bash_not_shortened(self):
        # Bash command 안 path 는 command 전체 의미라 단축 X
        from harness.hooks import _summarize_input
        cwd = str(Path.cwd().resolve())
        result = _summarize_input("Bash", {"command": f"cat {cwd}/foo.ts"})
        # command 그대로 — Bash 는 _shorten_path 미적용
        self.assertIn(cwd, result)


class PostToolUseStagingDiagnosticsTests(_PreToolBase):
    """#597 커밋6 — staging 실패 진단이 histogram 없어도 additionalContext 로 노출."""

    def _capture(self, stdin_data: dict):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = handle_posttooluse_agent(
                stdin_data=stdin_data, cc_pid=self.cc_pid, base_dir=self.base
            )
        return rc, buf.getvalue()

    def test_diagnostics_surfaced_without_histogram(self) -> None:
        # current_step 미설정 + subagent_type 없음(histogram 빈) + prose 존재 → 진단만 노출.
        stdin = {
            "sessionId": self.sid,
            "tool_name": "Agent",
            "tool_input": {},  # subagent_type 없음 → sub_type 빈 → histogram_str 빈
            "tool_response": [{"type": "text", "text": "## 결론\nPASS\n"}],
        }
        rc, out = self._capture(stdin)
        self.assertEqual(rc, 0)
        self.assertIn("staging 진단", out)
        self.assertIn("current_step 부재", out)

    def test_no_output_when_staging_ok_and_no_histogram(self) -> None:
        # current_step 정상 + staging 성공 + histogram 없음 → additionalContext 미출력.
        from harness.session_state import update_current_step
        update_current_step(self.sid, self.rid, "code-validator", None, base_dir=self.base)
        stdin = {
            "sessionId": self.sid,
            "tool_name": "Agent",
            "tool_input": {},
            "tool_response": [{"type": "text", "text": "## 결론\nPASS\n"}],
        }
        rc, out = self._capture(stdin)
        self.assertEqual(rc, 0)
        self.assertNotIn("staging 진단", out)


class MainFailOpenTests(unittest.TestCase):
    """#597 codex P2 (round5) — CLI _main: 정책 위반 exit 2 / 핸들러 크래시 fail-open exit 0."""

    def test_policy_block_maps_to_exit_2(self) -> None:
        from unittest.mock import patch
        import harness.hooks as H
        with patch.object(H, "handle_pretooluse_agent", return_value=1):
            self.assertEqual(H._main(["pretooluse-agent", "--cc-pid", "1"]), 2)

    def test_file_op_policy_block_maps_to_exit_2(self) -> None:
        from unittest.mock import patch
        import harness.hooks as H
        with patch.object(H, "handle_pretooluse_file_op", return_value=1):
            self.assertEqual(H._main(["pretooluse-file-op", "--cc-pid", "1"]), 2)

    def test_handler_crash_fails_open(self) -> None:
        # 핸들러 내부 예외 → exit 0 (fail-open) — hook 버그가 전 호출을 과차단하지 않게.
        from unittest.mock import patch
        import harness.hooks as H

        def _boom(**kw):
            raise RuntimeError("simulated hook bug")

        with patch.object(H, "handle_pretooluse_agent", side_effect=_boom):
            self.assertEqual(H._main(["pretooluse-agent", "--cc-pid", "1"]), 0)

    def test_allow_returns_0(self) -> None:
        from unittest.mock import patch
        import harness.hooks as H
        with patch.object(H, "handle_pretooluse_agent", return_value=0):
            self.assertEqual(H._main(["pretooluse-agent", "--cc-pid", "1"]), 0)

    def test_non_blocking_hook_never_exit_2(self) -> None:
        # session-start 등 비-blocking hook 은 정책 차단 개념 없음 → 항상 0.
        from unittest.mock import patch
        import harness.hooks as H
        with patch.object(H, "handle_session_start", return_value=1):
            self.assertEqual(H._main(["session-start", "--cc-pid", "1"]), 0)


class ContinueEnumsValidationBlockedTests(unittest.TestCase):
    """리뷰 P2 — VALIDATION_BLOCKED 는 메인 행동(게이트 대행)이 필수인 결론.

    _CONTINUE_ENUMS 에 없으면 메인 침묵 Stop 시 continuation block 없이 auto end-run
    으로 run 이 대행 실행 없이 닫힌다 — "메인 게이트 대행 (MUST)" 계약의 코드 측 짝.
    """

    def test_validation_blocked_is_continue_enum(self):
        from harness.hooks import _CONTINUE_ENUMS
        self.assertIn("VALIDATION_BLOCKED", _CONTINUE_ENUMS)


if __name__ == "__main__":
    unittest.main()
