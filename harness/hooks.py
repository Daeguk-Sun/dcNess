"""hooks.py — Claude Code 훅 핸들러 (`docs/archive/conveyor-design.md` §7).

bash 훅 (`hooks/*.sh`) 이 stdin payload + cc_pid 를 본 모듈의 핸들러로 전달.
순수 Python 으로 catastrophic 검사 + by-pid 레지스트리 갱신을 처리.

핸들러:
    handle_session_start(stdin_data, cc_pid) -> exit_code
        SessionStart event. sid 추출 + by-pid 작성 + live.json 초기화.

    handle_pretooluse_agent(stdin_data, cc_pid) -> exit_code
        PreToolUse, tool=Agent. §2.1 룰 검사.
        exit 0 = allow, exit 1 = block (stderr 메시지 + CC 가 호출 거부).

§2.1.2 (LGTM 없이 merge — 자연어 폐기) / §2.1.4 (PRD 변경 후 plan-reviewer PASS) /
§2.1.6~§2.1.8 (impl-task-loop 3-commit) 는 *메인 영역* (skill 안 Pre-flight)
또는 다른 흐름 (`/architect-loop` 의 impl 미리 머지 등) 으로 이전 — 코드
강제 폐기. 본 hook 코드 강제는 §2.1.1 (pr-reviewer 직전 code-validator PASS)
/ §2.1.3 (engineer 직전 module-architect PASS) / §2.1.5 (architect-loop 안
module-architect 첫 호출 직전 architecture-validator PASS) 3 룰.

규약:
    - 모든 실패 케이스 silent (exit 0) — CC 동작 방해 최소화
    - 단, catastrophic 위반은 exit 1 + stderr 메시지 (CC 사용자에게 가시)
    - stdin payload 파싱 실패 / sid 없음 / 잘못된 sid 등은 exit 0 (skip)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from harness.session_state import (
    read_live,
    read_pid_current_run,
    run_dir,
    session_dir,
    update_live,
    valid_cc_pid,
    valid_session_id,
    write_pid_session,
)


__all__ = [
    "handle_session_start",
    "handle_pretooluse_agent",
    "handle_pretooluse_file_op",
    "handle_posttooluse_agent",
    "handle_posttooluse_file_op",
    "handle_stop",
]


# ── DCN-CHG-20260501-11 — agent-trace.jsonl 헬퍼 ──────────────────────


_TRACE_INPUT_MAX = 200  # entry size cap (POSIX append atomic = 4096 bytes 이내)


def _shorten_path(s: str) -> str:
    """absolute path → cwd 기준 relative path. cwd 외부 또는 absolute 아니면 그대로.

    #408 — PostToolUse:Agent histogram 본문 cache_read 감축.
    예: '/Users/foo/proj/src/x.ts' (cwd='/Users/foo/proj') → 'src/x.ts'
    """
    if not s or not s.startswith("/"):
        return s
    try:
        cwd_str = str(Path.cwd().resolve())
        if s.startswith(cwd_str + "/"):
            return s[len(cwd_str) + 1:]
    except (OSError, ValueError):
        pass
    return s


def _summarize_input(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """tool_input 핵심을 _TRACE_INPUT_MAX bytes 이하로 요약."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        s = str(tool_input.get("command", ""))
    elif tool_name in ("Edit", "Write", "NotebookEdit", "Read"):
        s = _shorten_path(str(tool_input.get("file_path", "") or tool_input.get("path", "")))
    elif tool_name in ("Glob", "Grep"):
        s = str(tool_input.get("pattern", ""))
    else:
        s = ""
    if len(s) > _TRACE_INPUT_MAX:
        s = s[:_TRACE_INPUT_MAX] + "..."
    return s


def _append_trace_safe(
    sid: str,
    rid: str,
    entry: Dict[str, Any],
    *,
    base_dir: Optional[Path] = None,
) -> None:
    """trace append — 어떤 실패도 hook 본 흐름 방해 X."""
    try:
        from harness.agent_trace import append as _trace_append
        _trace_append(sid, rid, entry, base_dir=base_dir)
    except Exception:  # noqa: BLE001 — silent
        pass


# #272 W2 — prose robust extraction (어떤 nested 형식이든 first non-empty text)
# CC PostToolUse Agent 의 tool_response 형식 이력:
#   - 2026-05-01 도입 시 dict {"text": ...} 가정 (실측 X — 항상 fail)
#   - 2026-05-07 issue-232 가 list[{"type":"text","text":...}] 1형식 추가
#   - jajang #272/#273: 그래도 fail → 또 다른 nested 변형 추정
# 본 헬퍼는 *모든 dict/list 변형* depth-first 탐색해 first non-empty text-like 값
# 추출. CC schema 변동/undocumented format 대응. 후보 키 우선순위는 Anthropic
# content block 관례 (text > content > value > output).
_PROSE_TEXT_KEYS = ("text", "content", "value", "output")


def _extract_prose_text(obj: Any, _depth: int = 0) -> str:
    """tool_response → prose text. dict/list/str/nested 모두 robust.

    탐색 정책:
      - str: 그대로 반환 (strip 비어있으면 "")
      - dict: 우선순위 키 (`_PROSE_TEXT_KEYS`) 의 string value 만 채택 →
        그 다음 *dict/list value* 만 재귀 (string value 는 metadata 가능성
        — type="tool_result" 같은 필드 prose 로 오인 차단)
      - list: 각 item 재귀, first non-empty 반환
      - 기타: ""

    depth limit (16) — 무한 재귀 방어 (정상 payload 는 1~3 depth).
    """
    if _depth > 16:
        return ""
    if isinstance(obj, str):
        return obj if obj.strip() else ""
    if isinstance(obj, dict):
        # 우선순위 키 — 직접 매칭 (string value 만 prose 로 채택)
        for key in _PROSE_TEXT_KEYS:
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                return v
        # 그 외 — nested 컨테이너만 재귀 (string 값 = metadata 가능성, skip)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                r = _extract_prose_text(v, _depth + 1)
                if r:
                    return r
        return ""
    if isinstance(obj, list):
        for item in obj:
            r = _extract_prose_text(item, _depth + 1)
            if r:
                return r
        return ""
    return ""


def _extract_sid(payload: Dict[str, Any]) -> str:
    """OMC 3 변형 fallback."""
    return (
        payload.get("session_id")
        or payload.get("sessionId")
        or payload.get("sessionid")
        or ""
    )


def _resolve_rid(
    sid: str,
    cc_pid: Optional[int],
    *,
    base_dir: Optional[Path] = None,
) -> str:
    """rid 결정 — by-pid-current-run 우선, live.json 의 가장 최근 미완료 슬롯 폴백."""
    if cc_pid is not None and valid_cc_pid(cc_pid):
        rid = read_pid_current_run(cc_pid, base_dir=base_dir)
        if rid:
            return rid

    live = read_live(sid, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict):
        return ""
    candidates = [
        (rid_, slot) for rid_, slot in active.items()
        if isinstance(slot, dict) and slot.get("completed_at") is None
    ]
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[1].get("started_at", ""), reverse=True)
    return candidates[0][0]


def handle_session_start(
    stdin_data: Optional[Dict[str, Any]] = None,
    cc_pid: Optional[int] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """SessionStart 훅 처리.

    1. stdin 의 sessionId 추출
    2. regex 검증
    3. `.by-pid/{cc_pid}` ← sid 작성
    4. `.sessions/{sid}/live.json` 초기화 (없으면)

    실패 시 silent (exit 0).
    """
    if stdin_data is None:
        try:
            raw = sys.stdin.read()
            stdin_data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            return 0

    if not isinstance(stdin_data, dict):
        return 0

    sid = _extract_sid(stdin_data)
    if not valid_session_id(sid):
        return 0

    if cc_pid is None or not valid_cc_pid(cc_pid):
        return 0

    try:
        write_pid_session(cc_pid, sid, base_dir=base_dir)
        if not read_live(sid, base_dir=base_dir):
            update_live(sid, base_dir=base_dir)
    except (OSError, ValueError):
        return 0
    return 0


def handle_pretooluse_agent(
    stdin_data: Optional[Dict[str, Any]] = None,
    cc_pid: Optional[int] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """PreToolUse Agent 훅 처리 — orchestration.md §2.1 룰 검사.

    Returns:
        0: allow
        1: block (stderr 메시지 동반 — CC 가 호출 거부)
    """
    if stdin_data is None:
        try:
            raw = sys.stdin.read()
            stdin_data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            return 0  # parse 실패 → silent allow

    if not isinstance(stdin_data, dict):
        return 0

    sid = _extract_sid(stdin_data)
    if not valid_session_id(sid):
        return 0  # sid 없음 → 검사 불가, allow

    tool_input = stdin_data.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    subagent = tool_input.get("subagent_type", "") or ""
    mode = tool_input.get("mode", "") or ""

    rid = _resolve_rid(sid, cc_pid, base_dir=base_dir)

    if not rid:
        return 0  # 컨베이어 외부 — 그 외 agent 는 통과

    rd = run_dir(sid, rid, base_dir=base_dir)

    # §2.1.3 — engineer 직전 module-architect PASS 필수 (mode != POLISH)
    if subagent == "engineer" and mode != "POLISH":
        if not _has_pass(rd, "module-architect"):
            print(
                "[catastrophic §2.1.3] engineer 호출은 module-architect PASS 후만 "
                "(module-architect.md 안 PASS 마커)",
                file=sys.stderr,
            )
            return 1

    # §2.1.1 — pr-reviewer 직전 code-validator PASS 필수
    if subagent == "pr-reviewer":
        if _has_engineer_write(rd) and not _has_pass(rd, "code-validator"):
            print(
                "[catastrophic §2.1.1] pr-reviewer 호출은 code-validator "
                "PASS 후만",
                file=sys.stderr,
            )
            return 1

    # §2.1.5 — architect-loop 안 module-architect × K *첫 호출* 직전
    # architecture-validator PASS 필수. jajang Spike Gate 사단 회피.
    if (
        subagent == "module-architect"
        and _is_architect_loop(sid, rid, base_dir=base_dir)
        and _module_architect_first_call(rd)
    ):
        if not _has_pass(rd, "architecture-validator"):
            print(
                "[catastrophic §2.1.5] module-architect × K 첫 호출은 "
                "architecture-validator PASS 후만 "
                "(architecture-validator.md 안 PASS 마커)",
                file=sys.stderr,
            )
            return 1

    # §2.1.2 (LGTM 없이 merge — 자연어 폐기) / §2.1.4 / §2.1.6~§2.1.8 (3-commit) —
    # /architect-loop 가 impl/NN-*.md 미리 머지로 의미 소멸 또는 prerequisite
    # 검증은 메인 영역 (skill 안에서 보장) 으로 이전. 코드 강제 폐기.

    # DCN-CHG-20260501-01: 통과 시 live.json.active_agent 기록 — sub-agent 내부
    # PreToolUse(Edit/Write/Read/Bash) 훅이 활성 agent 판정에 사용 (agent_boundary).
    if subagent:
        try:
            update_live(sid, base_dir=base_dir, active_agent=subagent, active_mode=(mode or None))
        except (OSError, ValueError):
            pass  # 실패해도 Agent 호출은 통과 — 식별만 누락.

    # #272 W3 진짜 fix — PreToolUse Agent 의 tool_use_id + 시작 시각을 써
    # PostToolUse Agent 가 *시각 범위* 로 sub 의 trace 정확히 식별 (agent_id 폴백
    # 위험 제거). CC docs: tool_use_id 가 PreToolUse↔PostToolUse 매칭 키.
    if rid and subagent:
        tuid = stdin_data.get("tool_use_id", "") or ""
        if tuid:
            try:
                from harness.session_state import set_pending_agent
                set_pending_agent(
                    sid, rid,
                    tool_use_id=tuid, sub_type=subagent, mode=(mode or None),
                    base_dir=base_dir,
                )
            except (OSError, ValueError):
                pass  # 실패해도 Agent 호출 통과 — histogram 폴백 의존.

    return 0


# ── DCN-CHG-20260501-01 — sub-agent path 강제 (agent_boundary.py 권한 경계) ─


def handle_pretooluse_file_op(
    stdin_data: Optional[Dict[str, Any]] = None,
    cc_pid: Optional[int] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """PreToolUse Edit/Write/Read/Bash — agent_boundary 강제.

    활성 sub-agent (live.json.active_agent) 가 있을 때만 검사. 메인 Claude 는
    governance Document Sync 게이트가 별도 보호하므로 본 훅 통과.
    """
    from harness.agent_boundary import (
        check_read_allowed,
        check_write_allowed,
        extract_bash_paths,
    )

    if stdin_data is None:
        try:
            raw = sys.stdin.read()
            stdin_data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            return 0

    if not isinstance(stdin_data, dict):
        return 0

    sid = _extract_sid(stdin_data)
    if not valid_session_id(sid):
        return 0

    live = read_live(sid, base_dir=base_dir) or {}
    active_agent = live.get("active_agent") or ""
    if not active_agent:
        return 0  # 메인 Claude — governance 가 보호.

    tool_name = stdin_data.get("tool_name", "") or ""
    tool_input = stdin_data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    cwd = Path.cwd()

    # boundary 검사 — 차단 시 즉시 return (trace 미기록 — 차단된 행동은 file-guard 가 stderr 에 별도 기록)
    if tool_name == "Read":
        fp = tool_input.get("file_path", "") or ""
        if fp:
            reason = check_read_allowed(active_agent, fp, cwd=cwd)
            if reason:
                print(f"[agent-boundary] {reason}", file=sys.stderr)
                return 1
    elif tool_name in ("Edit", "Write", "NotebookEdit"):
        fp = tool_input.get("file_path", "") or ""
        if fp:
            reason = check_write_allowed(active_agent, fp, cwd=cwd)
            if reason:
                print(f"[agent-boundary] {reason}", file=sys.stderr)
                return 1
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        for fp in extract_bash_paths(cmd):
            reason = check_write_allowed(active_agent, fp, cwd=cwd)
            if reason:
                print(f"[agent-boundary][Bash] {reason}", file=sys.stderr)
                return 1

    # DCN-CHG-20260501-11 — sub 행동 trace append (rid 활성 시만)
    rid = _resolve_rid(sid, cc_pid, base_dir=base_dir)
    if rid:
        _append_trace_safe(
            sid,
            rid,
            {
                "phase": "pre",
                "agent": active_agent,
                "agent_id": stdin_data.get("agent_id", "") or "",
                "tool": tool_name,
                "input": _summarize_input(tool_name, tool_input),
            },
            base_dir=base_dir,
        )
    return 0


def handle_posttooluse_file_op(
    stdin_data: Optional[Dict[str, Any]] = None,
    cc_pid: Optional[int] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """PostToolUse Edit/Write/Read/Bash — sub 행동 trace post append (DCN-CHG-20260501-11).

    활성 sub-agent 가 있을 때만 기록. 메인 Claude turn 은 noop.
    PostToolUse 는 차단 권한 X — 항상 exit 0.
    """
    if stdin_data is None:
        try:
            raw = sys.stdin.read()
            stdin_data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            return 0

    if not isinstance(stdin_data, dict):
        return 0

    sid = _extract_sid(stdin_data)
    if not valid_session_id(sid):
        return 0

    live = read_live(sid, base_dir=base_dir) or {}
    active_agent = live.get("active_agent") or ""
    if not active_agent:
        return 0

    rid = _resolve_rid(sid, cc_pid, base_dir=base_dir)
    if not rid:
        return 0

    tool_name = stdin_data.get("tool_name", "") or ""
    tool_response = stdin_data.get("tool_response") or {}
    if not isinstance(tool_response, dict):
        tool_response = {}

    entry: Dict[str, Any] = {
        "phase": "post",
        "agent": active_agent,
        "agent_id": stdin_data.get("agent_id", "") or "",
        "tool": tool_name,
    }

    # Bash — exit code + stdout size
    exit_code = tool_response.get("exit_code")
    if isinstance(exit_code, int):
        entry["exit"] = exit_code
    stdout = tool_response.get("stdout")
    if isinstance(stdout, str):
        entry["stdout_size"] = len(stdout)

    # 모든 도구 — error flag
    is_error = tool_response.get("is_error") or stdin_data.get("is_error")
    if is_error is True:
        entry["is_error"] = True

    _append_trace_safe(sid, rid, entry, base_dir=base_dir)
    return 0


def handle_posttooluse_agent(
    stdin_data: Optional[Dict[str, Any]] = None,
    cc_pid: Optional[int] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """PostToolUse Agent — live.json clear + tool histogram inject + redo_log 자동.

    DCN-CHG-20260501-13 — sub 종료 후 agent-trace 집계 → result 옆에 histogram +
    anomaly 메시지 inject (additionalContext) + redo_log 1줄 자동 append.

    stdout JSON output:
        {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                 "additionalContext": "..."}}
    """
    if stdin_data is None:
        try:
            raw = sys.stdin.read()
            stdin_data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            return 0

    if not isinstance(stdin_data, dict):
        return 0

    sid = _extract_sid(stdin_data)
    if not valid_session_id(sid):
        return 0

    # 직전 sub 식별 — payload agent_id 우선, fallback trace 마지막 entry
    sub_agent_id = stdin_data.get("agent_id", "") or ""
    sub_type = ""
    tool_input = stdin_data.get("tool_input") or {}
    if isinstance(tool_input, dict):
        sub_type = str(tool_input.get("subagent_type", "") or "")

    rid = _resolve_rid(sid, cc_pid, base_dir=base_dir)

    # prose auto-staging — tool_response → run_dir 에 저장, current_step.prose_file 기록
    # #272 W2 진짜 fix — robust extraction. 도입(2026-05-01) 시 dict 만 가정 → fail.
    # issue-232 가 list[{type:"text",text:...}] 한 형식만 추가 → jajang 보고에서 또 fail.
    # 이번엔 *어떤 nested 형식이든* first non-empty text 추출 (CC schema 변동·
    # undocumented 변형 robust). 추출 실패 시에만 stderr 진단.
    if rid:
        raw_response = stdin_data.get("tool_response")
        prose_text = ""
        try:
            prose_text = _extract_prose_text(raw_response)
        except Exception as e:  # noqa: BLE001
            print(
                f"[hook prose stage] tool_response 추출 예외: "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )

        if not prose_text.strip():
            # robust extraction 도 fail 한 진짜 예외 — 다음 진단용
            if isinstance(raw_response, dict):
                _shape = f"dict keys={list(raw_response.keys())[:5]}"
            elif isinstance(raw_response, list):
                _shape = f"list len={len(raw_response)}"
                if raw_response and isinstance(raw_response[0], dict):
                    _shape += f" item0_keys={list(raw_response[0].keys())[:5]}"
                    _shape += f" item0_type={raw_response[0].get('type', '?')}"
            elif isinstance(raw_response, str):
                _shape = f"str len={len(raw_response)}"
            else:
                _shape = f"type={type(raw_response).__name__}"
            print(
                f"[hook prose stage] robust extraction 실패 — staging skip. {_shape}",
                file=sys.stderr,
            )
        else:
            try:
                live_data = read_live(sid, base_dir=base_dir) or {}
                active = live_data.get("active_runs", {}) or {}
                slot = active.get(rid, {}) if isinstance(active, dict) else {}
                cur_step = (
                    slot.get("current_step") if isinstance(slot, dict) else None
                )

                if not isinstance(cur_step, dict):
                    print(
                        f"[hook prose stage] current_step 부재 (rid={rid[:8]}…) — "
                        f"begin-step 호출 누락 의심. staging skip.",
                        file=sys.stderr,
                    )
                else:
                    step_agent = cur_step.get("agent")
                    step_mode = cur_step.get("mode") or None
                    if not step_agent:
                        print(
                            "[hook prose stage] current_step.agent 비어있음 — "
                            "staging skip.",
                            file=sys.stderr,
                        )
                    else:
                        from harness.signal_io import write_prose as _write_prose
                        from harness.session_state import (
                            _count_step_occurrences as _count_occ,
                        )

                        base = session_dir(sid, base_dir=base_dir) / "runs"
                        occ = _count_occ(
                            sid, rid, step_agent, step_mode, base_dir=base_dir
                        )
                        prose_path = _write_prose(
                            step_agent, rid, prose_text,
                            mode=step_mode, base_dir=base, occurrence=occ,
                        )
                        cur_step = dict(cur_step)
                        cur_step["prose_file"] = str(prose_path)
                        slot = dict(slot)
                        slot["current_step"] = cur_step
                        active = dict(active)
                        active[rid] = slot
                        update_live(sid, base_dir=base_dir, active_runs=active)

                        # issue #392 — routing_telemetry.record_agent_call 폐기.
                        # #281 baseline 비교 끝남 + jajang 실측 record_cascade 0건.
            except Exception as e:  # noqa: BLE001
                print(
                    f"[hook prose stage] write 예외: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )

    # rid 활성 시만 측정 inject + redo_log auto append
    # #272 W1 자율 친화 재설계 — hook 은 *raw 측정 데이터* 만 inject.
    # "REDO_SUSPECT" 같은 결정 X. 임계값 X. prose-only 화이트리스트 X.
    # 메인 LLM 이 loop-procedure.md §3.1 가이드 보고 자율 판단.
    histogram_str = ""
    input_repeats_str = ""
    pending_match = ""
    hist: Dict[str, int] = {}
    trace_subset: list = []
    if rid:
        try:
            from harness.agent_trace import histogram_since as _trace_hist_since
            from harness.agent_trace import read_all as _trace_read
            from harness.session_state import clear_pending_agent
            from harness.sub_eval import (
                format_histogram, format_input_repeats, summarize_input_repeats,
            )

            # #272 W3 — pending_agent.started_at 이후 trace = 그 sub 의 행동.
            tuid_now = stdin_data.get("tool_use_id", "") or ""
            pending = clear_pending_agent(sid, rid, base_dir=base_dir)
            since_ts = ""
            if isinstance(pending, dict):
                since_ts = pending.get("started_at", "") or ""
                pending_tuid = pending.get("tool_use_id", "") or ""
                if tuid_now and pending_tuid and tuid_now != pending_tuid:
                    print(
                        f"[hook agent-id] tool_use_id 불일치: pending="
                        f"{pending_tuid[:12]}… post={tuid_now[:12]}… — "
                        f"PreToolUse Agent ↔ PostToolUse Agent 매칭 실패. "
                        f"trace 시각 범위 폴백 사용.",
                        file=sys.stderr,
                    )
                    pending_match = "drift"
                else:
                    pending_match = "ok"

            hist = (
                _trace_hist_since(sid, rid, since_ts, base_dir=base_dir)
                if since_ts else {}
            )
            # 같은 input 반복 — 메인 자율 판단용 raw 신호 (다중 파일 vs 동일 파일 구분)
            if since_ts:
                trace_subset = [
                    e for e in _trace_read(sid, rid, base_dir=base_dir)
                    if e.get("ts", "") >= since_ts
                ]
                input_repeats = summarize_input_repeats(trace_subset)
                input_repeats_str = format_input_repeats(input_repeats)

            if hist or sub_type:
                histogram_str = format_histogram(hist) if hist else "(none)"
                # issue #392 — redo_log auto append 폐기. 메커니즘 죽음 (jajang
                # 실측 "하지 말 것" 0건). 학습 환류는 insight CLI (PR3) 로 대체.
        except Exception:  # noqa: BLE001 — silent
            pass

    # active_agent 해제 (기존 동작)
    try:
        update_live(sid, base_dir=base_dir, active_agent=None, active_mode=None)
    except (OSError, ValueError):
        pass

    # additionalContext — *raw 측정 데이터* + 가이드 1줄. 결정 메시지 X.
    # 메인 LLM 이 loop-procedure.md §3.1 가이드 (REDO 판단 신호) 보고 자율 판단.
    if histogram_str:
        ctx = f"[감시자 hook] sub={sub_type or '?'} tool histogram: {histogram_str}"
        if input_repeats_str:
            ctx += f"\n같은 input 반복: {input_repeats_str}"

        try:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": ctx,
                }
            }
            print(json.dumps(output, ensure_ascii=False))
        except Exception:  # noqa: BLE001 — silent
            pass

    return 0


def _read_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def _has_pass(rd: Path, agent: str) -> bool:
    """`<agent>.md` 또는 `<agent>-N.md` (occurrence) 안 PASS 마커 확인.

    8 agent enum 통일 (PR B-3) 후 모든 catastrophic 검사가 PASS 단일 마커.
    occurrence 카운터 — `<agent>-2.md` / `-3.md` ... 까지 가장 최근 호출.
    """
    if "PASS" in _read_or_empty(rd / f"{agent}.md"):
        return True
    for n in range(2, 10):
        if "PASS" in _read_or_empty(rd / f"{agent}-{n}.md"):
            return True
    return False


def _has_engineer_write(rd: Path) -> bool:
    return (rd / "engineer-IMPL.md").exists() or (rd / "engineer-POLISH.md").exists()


def _is_architect_loop(
    sid: str,
    rid: str,
    *,
    base_dir: Optional[Path] = None,
) -> bool:
    """현재 run 이 architect-loop 인지 확인 (entry_point 기준).

    §2.1.5 catastrophic gate 발동 조건 — architect-loop 안 module-architect
    × K 첫 호출 직전 architecture-validator PASS 필수.
    """
    try:
        live = read_live(sid, base_dir=base_dir) or {}
        active = live.get("active_runs", {})
        if not isinstance(active, dict):
            return False
        slot = active.get(rid, {})
        entry = slot.get("entry_point", "") if isinstance(slot, dict) else ""
        return entry == "architect-loop"
    except Exception:  # noqa: BLE001 — safe default
        return False


def _module_architect_first_call(rd: Path) -> bool:
    """module-architect 첫 호출인지 — 기존 prose 파일 부재 검사."""
    return not (rd / "module-architect.md").exists()


# ── Stop hook (issue #382) ────────────────────────────────────────────


def handle_stop(
    stdin_data: Optional[Dict[str, Any]] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """Stop hook — 메인 응답 종료 시 자동 end-run.

    배경 (issue #382): /impl / /impl-loop / /architect-loop 등 컨베이어 루프
    종료 후 메인 Claude 가 `end-run` 까먹는 회귀 반복 발생. loop-procedure.md §5.1
    의 prose 의무로는 본능 (PR merge 후 "작업 끝" 인지) 패배.

    Stop hook 으로 *코드 강제 승격*:
    1. stop_hook_active=true → 무한 루프 방지, skip
    2. active_runs[rid] 슬롯 부재 / finalized_at 있음 → skip (이미 종료)
    3. `.steps.jsonl` 마지막 row 의 (agent, mode) 가 live.json.current_step.
       (agent, mode) 와 일치 → end-step 완료 상태 = 종료 후보 / 불일치 →
       begin-step 후 end-step 미호출 진행 중 → skip (false positive 회피)
    4. 위 모두 통과 → in-process `_cli_end_run` 호출.
       session_state.py:1001 안전망 → finalize-run --auto-review 자동 →
       `<run_dir>/review.md` 생성 + stderr `[REVIEW_READY]` 신호

    issue #469 결함 A fix (DCN-CHG-20260522): 중간 step PASS 후 다음 step 미진입
    상태로 Stop 받으면 `decision:"block"` JSON stdout 으로 메인 turn 자동 발화
    강제 (build-worker PASS → 9시간 침묵 회귀 차단). `_maybe_emit_continuation_signal`
    helper 가 `_CONTINUE_ENUMS` + `_TERMINAL_AGENTS` + `stop_block_count` 가드로
    분기.

    review.md 본문 echo 는 *기존 prose 의무* (loop-procedure.md §6 +
    run-review.md §51 + commands/impl.md §종료 조건) 에 의존.

    return: 항상 0 (block 쓴 경우에도 0 — CC 가 stdout JSON 으로 block 분기 인식).
    """
    if stdin_data is None:
        try:
            raw = sys.stdin.read()
            stdin_data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            return 0

    if not isinstance(stdin_data, dict):
        return 0

    # 무한 루프 가드 (Claude Code 공식 docs §"Stop hook runs forever")
    if stdin_data.get("stop_hook_active"):
        return 0

    # 지연 import — session_state 가 무거움
    try:
        from harness.session_state import (
            auto_detect_session_id,
            auto_detect_run_id,
            read_live,
            _read_steps_jsonl,
            _cli_end_run,
        )
    except Exception:
        return 0

    try:
        sid = auto_detect_session_id(base_dir=base_dir) if base_dir else auto_detect_session_id()
        rid = auto_detect_run_id(base_dir=base_dir) if base_dir else auto_detect_run_id()
    except Exception:
        return 0

    if not (sid and rid):
        return 0

    # active_runs 슬롯 검사
    try:
        live = read_live(sid, base_dir=base_dir) if base_dir else read_live(sid)
    except Exception:
        return 0
    if not live:
        return 0
    active = live.get("active_runs", {}) if isinstance(live, dict) else {}
    slot = active.get(rid) if isinstance(active, dict) else None
    if not isinstance(slot, dict):
        return 0  # begin-run 미호출 — skip
    if slot.get("finalized_at"):
        return 0  # 이미 finalize-run 호출됨 — skip

    # end-step 완료 매칭 검사 (false positive 회피)
    # _read_steps_jsonl 마지막 row.(agent, mode) vs live.current_step.(agent, mode).
    # 일치 = end-step 호출됨 (step 종료 상태) / 불일치 = begin-step 후 end-step
    # 미호출 (sub-agent 진행 중 응답 종료 케이스 — end-run 발사 false positive).
    try:
        steps = _read_steps_jsonl(sid, rid)
    except Exception:
        return 0
    if not steps:
        return 0  # step 0개 — begin-step 안 부른 상태

    last = steps[-1]
    last_agent = last.get("agent")
    last_mode = last.get("mode")
    cur_step = slot.get("current_step") if isinstance(slot, dict) else None
    if isinstance(cur_step, dict):
        cur_agent = cur_step.get("agent")
        cur_mode = cur_step.get("mode")
        # 정확 일치 검사 (mode None 도 비교)
        if cur_agent != last_agent or cur_mode != last_mode:
            return 0  # begin-step 후 end-step 미호출 — 진행 중

    # === issue #469 결함 A — 중간 step PASS 후 메인 turn 자동 발화 부재 fix ===
    # build-worker / engineer / code-validator 같은 중간 step 종료 후 메인이
    # 다음 step 진입 안 한 상태로 Stop 받으면 decision:block 으로 메인 turn
    # 재 발화 강제. pr-reviewer 는 종료 agent (run 끝 = 정상 침묵).
    if _maybe_emit_continuation_signal(
        sid=sid, rid=rid, slot=slot, active=active,
        last_agent=last_agent, last_mode=last_mode,
        base_dir=base_dir,
    ):
        return 0
    # === /issue #469 결함 A ============================================

    # 모든 조건 충족 — end-run in-process 호출
    try:
        import argparse as _ap
        _fake = _ap.Namespace()
        _cli_end_run(_fake)
        print("[stop-hook] end-run 자동 호출 — issue #382", file=sys.stderr)
    except Exception as exc:
        print(f"[stop-hook] end-run FAIL — {exc}", file=sys.stderr)

    return 0


# issue #469 결함 A — Stop hook continuation signal helper
# 다음 step 진입 가능 결론 enum (단독 결론 + 일반 PASS).
_CONTINUE_ENUMS: frozenset[str] = frozenset({
    "PASS", "IMPL_DONE", "POLISH_DONE",
    "TESTS_WRITTEN", "UX_FLOW_DONE",
})
# 종료 agent — 본 agent 의 PASS/LGTM 은 run 끝 = block 안 함.
_TERMINAL_AGENTS: frozenset[str] = frozenset({"pr-reviewer"})
# 무한 루프 가드 — 같은 step 에서 block 쓴 횟수 상한.
_STOP_BLOCK_COUNT_MAX = 2


def _maybe_emit_continuation_signal(
    *,
    sid: str,
    rid: str,
    slot: Dict[str, Any],
    active: Dict[str, Any],
    last_agent: Optional[str],
    last_mode: Optional[str],
    base_dir: Optional[Path],
) -> bool:
    """issue #469 결함 A — 중간 step PASS 후 메인 turn 발화 강제 신호 박기.

    조건:
    1. 마지막 step agent 가 종료 agent (pr-reviewer) 아님
    2. 마지막 step prose 파일 존재 + 결론 enum 이 다음 step 진입 가능 enum
    3. stop_block_count[step_key] < _STOP_BLOCK_COUNT_MAX (무한 루프 가드)

    반환:
        True  — decision:block JSON stdout 씀 + 호출자는 return 0 해야 함
        False — 조건 미충족, 호출자는 기존 분기 (end-run 자동 호출) 진행
    """
    if not last_agent or last_agent in _TERMINAL_AGENTS:
        return False
    rdir = slot.get("run_dir")
    if not isinstance(rdir, str) or not rdir:
        return False

    mode_suffix = f"-{last_mode}" if last_mode else ""
    prose_path = Path(rdir) / f"{last_agent}{mode_suffix}.md"
    if not prose_path.is_file():
        return False

    # 결론 enum 추출 (run_review 의 패턴 재사용 — handle_stop 안 lazy import).
    try:
        from harness.run_review import _extract_conclusion_enum
    except Exception:
        return False
    try:
        prose = prose_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    enum = _extract_conclusion_enum(prose)
    if enum not in _CONTINUE_ENUMS:
        return False

    # 무한 루프 가드 — 같은 step 에서 block 쓴 횟수 상한 검사.
    step_key = f"{last_agent}:{last_mode or ''}"
    block_counts = slot.get("stop_block_count")
    if not isinstance(block_counts, dict):
        block_counts = {}
    try:
        cur_count = int(block_counts.get(step_key, 0) or 0)
    except (TypeError, ValueError):
        cur_count = 0
    if cur_count >= _STOP_BLOCK_COUNT_MAX:
        return False  # 메인이 reason 받고도 발화 안 함 = 진짜 종료 — 기존 분기로

    # count +1 persist
    block_counts[step_key] = cur_count + 1
    slot["stop_block_count"] = block_counts
    active[rid] = slot
    try:
        update_live(sid, base_dir=base_dir, active_runs=active)
    except Exception:
        pass  # persist 실패해도 block 자체는 씀 (다음 호출 시 cur_count 만 미증가)

    reason = (
        f"[dcness Stop hook · issue #469 결함 A] sub-step "
        f"'{last_agent}{mode_suffix}' 결론 '{enum}' — 다음 sub-step 진입 turn "
        "필요. /impl-loop Hybrid A = build-worker PASS → pr-reviewer 영역 "
        "(begin-step pr-reviewer + Agent pr-reviewer + end-step + PR 머지). "
        "4-agent /impl 이면 정의된 다음 agent 호출. 사용자 의도로 정말 종료 "
        f"하려면 메인 발화 → 다시 Stop trigger 시 본 가드가 {_STOP_BLOCK_COUNT_MAX}회 후 "
        "skip 처리됨."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return True


# ── CLI 진입점 (bash 훅 → python -m harness.hooks <subcommand>) ─────


def _main(argv: Optional[list] = None) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(
        prog="python3 -m harness.hooks",
        description="dcNess Claude Code 훅 진입점",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ss = sub.add_parser("session-start", help="SessionStart 훅 처리")
    p_ss.add_argument("--cc-pid", type=int, default=None)

    p_ag = sub.add_parser("pretooluse-agent", help="PreToolUse Agent 훅 처리")
    p_ag.add_argument("--cc-pid", type=int, default=None)

    p_fo = sub.add_parser("pretooluse-file-op",
                          help="PreToolUse Edit/Write/Read/Bash agent_boundary 강제")
    p_fo.add_argument("--cc-pid", type=int, default=None)

    p_pa = sub.add_parser("posttooluse-agent",
                          help="PostToolUse Agent — live.json.active_agent 해제")
    p_pa.add_argument("--cc-pid", type=int, default=None)

    p_pf = sub.add_parser("posttooluse-file-op",
                          help="PostToolUse Edit/Write/Read/Bash — agent-trace post append")
    p_pf.add_argument("--cc-pid", type=int, default=None)

    p_st = sub.add_parser("stop",
                          help="Stop 훅 — 메인 응답 종료 시 자동 end-run (issue #382)")
    p_st.add_argument("--cc-pid", type=int, default=None)

    args = parser.parse_args(argv)

    # cc_pid 미명시 시 PPID 사용 (bash 훅 의 PPID = CC main)
    cc_pid = args.cc_pid if args.cc_pid is not None else os.getppid()

    if args.cmd == "session-start":
        return handle_session_start(cc_pid=cc_pid)
    elif args.cmd == "pretooluse-agent":
        return handle_pretooluse_agent(cc_pid=cc_pid)
    elif args.cmd == "pretooluse-file-op":
        return handle_pretooluse_file_op(cc_pid=cc_pid)
    elif args.cmd == "posttooluse-agent":
        return handle_posttooluse_agent(cc_pid=cc_pid)
    elif args.cmd == "posttooluse-file-op":
        return handle_posttooluse_file_op(cc_pid=cc_pid)
    elif args.cmd == "stop":
        return handle_stop()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
