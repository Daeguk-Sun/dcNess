"""hooks.py — Claude Code 훅 핸들러 (`docs/archive/conveyor-design.md` §7).

bash 훅 (`hooks/*.sh`) 이 stdin payload + cc_pid 를 본 모듈의 핸들러로 전달.
순수 Python 으로 catastrophic 검사 + by-pid 레지스트리 갱신을 처리.

핸들러:
    handle_session_start(stdin_data, cc_pid) -> exit_code
        SessionStart event. sid 추출 + by-pid 작성 + live.json 초기화.

    handle_pretooluse_agent(stdin_data, cc_pid) -> exit_code
        PreToolUse, tool=Agent. catastrophic 룰 검사.
        exit 0 = allow, exit 1 = block (stderr 메시지 + CC 가 호출 거부).

옛 merge-gate (LGTM 없이 merge) / impl-task-loop 3-commit 룰은 *메인 영역*
(skill 안 Pre-flight) 또는 다른 흐름 (`/design` 의 impl 미리 머지 등)
으로 이전 — 코드 강제 폐기. 본 hook 코드 강제는 3 게이트:
pr-reviewer 게이트 (engineer 산출물 이후 code-validator PASS) / engineer 게이트 (직전
module-architect PASS) / module-architect 게이트 (design 안 첫 호출
직전 architecture-validator PASS).

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

from harness.agent_names import normalize_agent_type
from harness.session_state import (
    _read_steps_jsonl,
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
    "handle_subagent_stop",
    "handle_stop",
]


_STRICT_CONVEYOR_ENTRY_POINTS = frozenset({
    "design",
    "impl",
    "ux",
})


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


def _mode_or_none(mode: Any) -> Optional[str]:
    return str(mode) if isinstance(mode, str) and mode else None


def _agent_mode_label(agent: str, mode: Optional[str]) -> str:
    return f"{agent}:{mode}" if mode else agent


def _begin_step_cmd(agent: str, mode: Optional[str]) -> str:
    return f"dcness-helper begin-step {agent}{' ' + mode if mode else ''}"


def _end_step_cmd(agent: str, mode: Optional[str]) -> str:
    return f"dcness-helper end-step {agent}{' ' + mode if mode else ''}"


def _strict_conveyor_gate_message(
    *,
    sid: str,
    rid: str,
    base_dir: Optional[Path],
    slot: Dict[str, Any],
    subagent: str,
    mode: Optional[str],
) -> Optional[str]:
    """active conveyor run 안 Agent 직접 호출을 begin-step/current_step 기준으로 차단."""
    if not subagent:
        return None
    entry_point = slot.get("entry_point", "")
    if entry_point not in _STRICT_CONVEYOR_ENTRY_POINTS:
        return None
    if slot.get("completed_at") or slot.get("finalized_at"):
        return None

    requested = _agent_mode_label(subagent, mode)
    cur_step = slot.get("current_step")
    if not isinstance(cur_step, dict):
        return (
            "[strict-conveyor] begin-step 누락 — active conveyor run"
            f"(entry_point={entry_point}, rid={rid[:8]}...) 안에서 Agent({requested}) "
            "직접 호출을 차단했습니다. 먼저 "
            f"`{_begin_step_cmd(subagent, mode)}` 실행 후 Agent를 다시 호출하세요."
        )

    step_agent = cur_step.get("agent")
    if not isinstance(step_agent, str) or not step_agent:
        return (
            "[strict-conveyor] current_step.agent 공백 — active conveyor run"
            f"(entry_point={entry_point}, rid={rid[:8]}...) 의 step 상태가 불완전합니다. "
            f"`{_begin_step_cmd(subagent, mode)}` 로 올바른 step을 다시 설정한 뒤 "
            "Agent를 호출하세요."
        )
    step_mode = _mode_or_none(cur_step.get("mode"))
    current = _agent_mode_label(step_agent, step_mode)

    # #700 — 이름은 canonical 비교(namespaced/alias 무관, subagent 는 호출부에서 정규화 전달).
    # mode 는 Agent 도구가 실을 수 없어 항상 None 이므로, Agent 측 mode 가 *실제로 실린*
    # 경우(미래 호환)에만 불일치 차단 — moded step(engineer:IMPL)이 영구 차단되던 결함 해소.
    norm_step_agent = normalize_agent_type(step_agent) or step_agent
    if norm_step_agent != subagent or (mode is not None and step_mode != mode):
        return (
            "[strict-conveyor] begin-step/Agent 불일치 — current_step="
            f"{current}, requested Agent={requested}. 현재 step을 닫아야 하면 "
            f"`{_end_step_cmd(step_agent, step_mode)}` 를 먼저 호출하고, 다른 Agent를 "
            f"호출하려면 `{_begin_step_cmd(subagent, mode)}` 로 step을 재설정하세요."
        )

    prose_file = cur_step.get("prose_file")
    if isinstance(prose_file, str) and prose_file:
        return (
            "[strict-conveyor] 이전 Agent 결과가 이미 staged 상태입니다 — "
            f"current_step={current}, prose_file={Path(prose_file).name}. "
            f"같은 Agent를 다시 호출하기 전에 `{_end_step_cmd(step_agent, step_mode)}` 로 "
            "현재 step을 먼저 기록하세요."
        )

    records = [
        record
        for record in _read_steps_jsonl(sid, rid, base_dir=base_dir)
        if isinstance(record, dict)
    ]
    if records:
        last = records[-1]
        last_agent = last.get("agent")
        last_mode = _mode_or_none(last.get("mode"))
        if last_agent == step_agent and last_mode == step_mode:
            raw_count_at_begin = cur_step.get("steps_count_at_begin")
            try:
                count_at_begin = int(raw_count_at_begin)
            except (TypeError, ValueError):
                count_at_begin = None
            current_count = len(records)
            if (
                count_at_begin is not None
                and current_count > count_at_begin
            ):
                return (
                    "[strict-conveyor] 이전 step이 이미 ledger.jsonl 에 기록됐습니다 — "
                    f"logged_step={current}. 다음 Agent 호출 전 "
                    f"`{_begin_step_cmd(subagent, mode)}` 로 새 step을 먼저 시작하세요."
                )

    return None


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


def _resolve_acting_agent(
    stdin_data: Dict[str, Any], live: Dict[str, Any]
) -> str:
    """file-op 훅의 acting sub-agent 식별 — issue #598 self-attribution.

    공식 CC docs (code.claude.com/docs/en/hooks): PreToolUse/PostToolUse 가
    sub-agent 안에서 발화하면 payload 에 `agent_type` (+`agent_id`) 가 실린다.
    각 도구 호출이 *자기 payload* 로 agent 를 식별하면 동시 sub-agent 가 공유
    단일 슬롯(`live.active_agent`)을 서로 덮어써도 권한/trace 귀속이 안 섞인다.

    우선순위: payload `agent_type` (자기 식별, 동시 안전) → `live.active_agent`
    단일 슬롯 폴백 (구버전 CC / payload 미탑재 케이스). 둘 다 없으면 "" = 메인 Claude.

    issue #598 (codex P1) — 반환 전 `normalize_agent_type` 으로 정규화. namespaced
    payload(`dcness:code-validator`) 가 ALLOW_MATRIX 미정의 → check_*_allowed pass-through 로
    경계를 우회하던 결함 차단. 정규화 후 boundary + trace 가 canonical 이름 사용.
    """
    payload_agent = stdin_data.get("agent_type")
    if isinstance(payload_agent, str) and payload_agent:
        return normalize_agent_type(payload_agent) or ""
    return normalize_agent_type(live.get("active_agent") or "") or ""


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
    """PreToolUse Agent 훅 처리 — catastrophic 룰 검사 (hooks.md 의 catastrophic-gate.sh).

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
    # #700 — 게이트 비교는 canonical 이름으로 일관화. namespaced(`dcness:engineer`) / legacy
    # alias 가 raw 비교에서 strict-conveyor 불일치로 차단되던 것을 정규화로 해소(A). 그리고
    # strict-conveyor 가 namespaced 를 통과시키는 이상, 뒤따르는 catastrophic 게이트(engineer/
    # pr-reviewer/module-architect)도 norm 으로 비교해야 namespaced 우회를 막는다(codex P1).
    # active_agent / pending 기록은 raw subagent 유지(식별 원본 보존). 단 게이트의 *판정 로직*
    # (module-architect PASS 요구)은 main 그대로 — engineer 게이트의 lane-aware 면제 + effective
    # mode(POLISH) 판정은 #701(Finding C).
    norm_subagent = normalize_agent_type(subagent) or subagent

    rid = _resolve_rid(sid, cc_pid, base_dir=base_dir)

    if not rid:
        return 0  # 컨베이어 외부 — 그 외 agent 는 통과

    rd = run_dir(sid, rid, base_dir=base_dir)

    # issue #604 — active conveyor run 안에서는 begin-step 없이 Agent 직접 호출 금지.
    # PostToolUse staging 이후 같은 step 재호출, end-step 완료 후 stale current_step 도
    # PreToolUse 시점에서 차단해 `.steps.jsonl` 누락을 실행 전에 막는다.
    step_mode = None
    try:
        live = read_live(sid, base_dir=base_dir) or {}
        active = live.get("active_runs", {}) if isinstance(live, dict) else {}
        slot = active.get(rid, {}) if isinstance(active, dict) else {}
        if isinstance(slot, dict):
            # #709 — begin-step 이 기록한 current_step.mode 를 effective mode fallback 으로
            # 쓰기 위해 같은 slot read 에서 함께 추출(중복 read 회피). 단 fallback 의 신뢰
            # 근거가 "strict-conveyor 가 begin-step↔Agent 정합을 보장" 이므로, strict
            # entry_point 일 때만 step_mode 를 채운다 — 비-strict run 은 그 정합이 없어
            # 다른 step 의 mode 가 면제로 새는 것을 원천 차단(게이트 약화 방향 방어).
            if slot.get("entry_point", "") in _STRICT_CONVEYOR_ENTRY_POINTS:
                cur_step = slot.get("current_step")
                if isinstance(cur_step, dict):
                    step_mode = _mode_or_none(cur_step.get("mode"))
            strict_msg = _strict_conveyor_gate_message(
                sid=sid,
                rid=rid,
                base_dir=base_dir,
                slot=slot,
                subagent=norm_subagent,
                mode=_mode_or_none(mode),
            )
            if strict_msg:
                print(strict_msg, file=sys.stderr)
                return 1
    except (OSError, ValueError):
        pass  # state 읽기 실패는 fail-open — hook 버그발 과차단 회피.

    # engineer 게이트 — engineer 직전 설계 산출물 필수 (effective mode != POLISH).
    # #700 — namespaced 우회 차단을 위해 norm_subagent 비교(codex P1).
    # #701 — prerequisite = 같은-run module-architect PASS ∪ begin-run 에 기록된
    # 머지된 설계 문서(design_doc) 실존. impl-loop 풀 4-agent 는 설계가 별도 run
    # 에서 머지된 뒤 진입하므로 같은-run prose 단일 기준이면 구조적으로 차단된다.
    # #714 — /impl 2축 모델의 Lite lane(설계도 없음)에 sub-agent 엔진을 붙이는
    # 4번째 조합. lane="lite"(begin-run --lane lite 로 start_run 에 기록)는 정의상
    # 설계도가 없으므로 module-architect PASS / design_doc 둘 다 없다. 면제 경계는
    # *명시적으로 기록된* lane="lite" 한정 — lane 미기록(impl-loop 풀4 / 기본)과
    # lane="standard" 는 종전대로 설계 산출물을 요구한다(면제 누수 차단). lane 은
    # entry_point=impl 에서만 기록 가능(start_run 강제)하므로 design/architect-loop
    # run 의 module-architect PASS 강제는 영향받지 않는다. 이 면제는 engineer 게이트
    # *만* 푼다 — 뒤따르는 pr-reviewer←code-validator 잔존 보호는 lane 무관 불변.
    # #709 — effective mode = tool_input.mode ∪ current_step.mode. Agent 도구 스키마에
    # mode 파라미터가 없는 CC 빌드에선 tool_input.mode 가 안 실려, POLISH 면제가
    # tool_input.mode 단독이면 죽는다(impl-loop engine B 의 pr-reviewer→engineer:POLISH 가
    # design_doc·MA PASS 둘 다 없어 구조적 차단). begin-step 이 CLI 로 확실히 기록한
    # current_step.mode 를 fallback 으로 봐 환경 무관하게 면제를 복원한다. strict-conveyor 가
    # begin-step↔Agent(agent) 정합을 이미 보장하므로 current_step.mode=POLISH 는 신뢰 신호.
    effective_mode = _mode_or_none(mode) or step_mode
    if norm_subagent == "engineer" and effective_mode != "POLISH":
        lane_lite = _run_lane(sid, rid, base_dir=base_dir) == "lite"
        if (
            not lane_lite
            and not _has_module_architect_pass(rd)
            and not _run_design_doc_exists(sid, rid, base_dir=base_dir)
        ):
            print(
                "[catastrophic: engineer 게이트] engineer 호출은 설계 산출물 확보 후만 — "
                "같은 run 의 module-architect PASS prose (module-architect*.md 안 "
                "PASS 마커) 또는 begin-run --design-doc 으로 기록된 설계 문서 실존",
                file=sys.stderr,
            )
            return 1

    # pr-reviewer 게이트 — engineer sub-agent 산출물 이후 code-validator PASS 필수.
    # Lite lane 은 메인 직접 구현 경로라 engineer prose 가 없고, pr-reviewer 단독 허용.
    if norm_subagent == "pr-reviewer":
        if _has_engineer_write(rd) and not _has_pass(rd, "code-validator"):
            print(
                "[catastrophic: pr-reviewer 게이트] engineer 산출물 이후 "
                "pr-reviewer 호출은 code-validator PASS 후만",
                file=sys.stderr,
            )
            return 1

    # module-architect 게이트 — design 안 module-architect × K *첫 호출* 직전
    # architecture-validator PASS 필수. jajang Spike Gate 사단 회피.
    if (
        norm_subagent == "module-architect"
        and _is_design_loop(sid, rid, base_dir=base_dir)
        and _module_architect_first_call(rd)
    ):
        if not _has_pass(rd, "architecture-validator"):
            print(
                "[catastrophic: module-architect 게이트] module-architect × K 첫 호출은 "
                "architecture-validator PASS 후만 "
                "(architecture-validator.md 안 PASS 마커)",
                file=sys.stderr,
            )
            return 1

    # tech-reviewer 재호출 (design 진입 후) 은 *tech-reviewer 전용* 코드 강제로
    # 차단하지 않는다 (#609). tech-review 는 design 진입 *전* 단방향 선행 단계라
    # 재호출이 거의 필요 없지만, 재호출 자체는 docs/tech-review.md + 증거물만 쓰는 read-mostly
    # 작업 — 회복 비용 비대칭이 없어 catastrophic 이 아니다. 따라서 "재호출 비권장" 은 자연어
    # 관례 (skill/agent prose) 로 두고 재호출 여부는 메인/사용자 자율 판단 (forcing function 을
    # 코드 강제하지 않는 대원칙 — CLAUDE.md). design 도중 미검증 새 외부 의존 발견 =
    # NEW_DEP_ESCALATE 3안.
    #   ※ 자유 재호출은 active conveyor run *밖* (메인 루프 / 루프 finalize 후) 에서 일어난다 —
    #   그 경우 rid 부재 또는 strict-conveyor 의 finalize 분기로 게이트가 발화하지 않는다. active
    #   conveyor run *안* 에서는 위 strict-conveyor gate(#604) 가 *모든* off-sequence agent
    #   (tech-reviewer 포함) 에 begin-step 선언을 요구한다 — 이는 tech-reviewer 전용 차단이 아닌
    #   일반 conveyor 무결성 룰이라 #609 범위 밖이고, 루프 도중 의존 검증은 NEW_DEP_ESCALATE 로 간다.

    # 옛 merge-gate (LGTM 없이 merge) / impl-task-loop 3-commit 룰 (자연어 폐기) —
    # /design 이 impl/NN-*.md 미리 머지로 의미 소멸 또는 prerequisite
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
                # issue #598 — set 전 동시성 감지 (이미 미완 pending 있으면 경고).
                _warn_concurrent_subagent(
                    sid, rid, tuid, subagent, base_dir=base_dir
                )
                set_pending_agent(
                    sid, rid,
                    tool_use_id=tuid, sub_type=subagent, mode=(mode or None),
                    base_dir=base_dir,
                )
            except (OSError, ValueError):
                pass  # 실패해도 Agent 호출 통과 — histogram 폴백 의존.

    return 0


def _warn_concurrent_subagent(
    sid: str,
    rid: str,
    new_tuid: str,
    subagent: str,
    *,
    base_dir: Optional[Path] = None,
) -> None:
    """issue #598 — PreToolUse Agent 가 *이미 미완 pending* 상태에서 새 Agent 를
    발사하면 동시 sub-agent (컨베이어 순차 전제 위반) 로 보고 stderr 진단 (비차단).

    self-attribution (file-op payload agent_type) 덕에 boundary/trace 는 이미
    안전하지만, dcness 컨베이어는 step 당 agent 1개 순차 전제라 동시 발사는 메인
    로직 버그 신호일 수 있어 가시화한다. 차단·inject 아님 (권고 — 측정+경고).
    """
    try:
        live = read_live(sid, base_dir=base_dir) or {}
        active = live.get("active_runs", {})
        slot = active.get(rid, {}) if isinstance(active, dict) else {}
        pending = slot.get("pending_agents") if isinstance(slot, dict) else None
        if not isinstance(pending, dict):
            return
        others = [tid for tid in pending if tid != new_tuid]
        if others:
            print(
                f"[hook concurrency] 동시 sub-agent 감지 — 이미 미완 Agent "
                f"{len(others)}개(pending) 상태에서 '{subagent}' 추가 발사. dcness "
                f"컨베이어는 step 당 agent 1개 순차 전제. self-attribution 으로 "
                f"권한/trace 는 안전하나 순차 전제 위반 여부 점검 권장.",
                file=sys.stderr,
            )
    except Exception:  # noqa: BLE001 — 진단 실패는 무시 (Agent 호출 통과)
        pass


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
        check_bash_mutation,
        check_github_mcp_mutation,
        check_read_allowed,
        check_write_allowed,
        extract_bash_paths,
        is_infra_project,
        is_opt_out,
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
    # issue #598 — acting agent 는 payload agent_type(자기 식별, 동시 sub 안전) 우선,
    # 없으면 live.active_agent 단일 슬롯 폴백 (_resolve_acting_agent).
    acting_agent = _resolve_acting_agent(stdin_data, live)
    if not acting_agent:
        return 0  # 메인 Claude — governance 가 보호.

    tool_name = stdin_data.get("tool_name", "") or ""
    tool_input = stdin_data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    cwd = Path.cwd()

    # #597 codex P2 (round6) — mutation 검사도 file-guard 우회(.no-dcness-guard / infra)를 존중.
    # path 검사(check_write_allowed/check_read_allowed)는 내부에서 opt-out/infra 를 이미 해제하지만,
    # check_bash_mutation/check_github_mcp_mutation 은 cwd 무관 순수 함수라 별도 가드 필요.
    mutation_guard_off = is_opt_out(cwd) or is_infra_project(cwd)

    # boundary 검사 — 차단 시 즉시 return (trace 미기록 — 차단된 행동은 file-guard 가 stderr 에 별도 기록)
    if tool_name == "Read":
        fp = tool_input.get("file_path", "") or ""
        if fp:
            reason = check_read_allowed(acting_agent, fp, cwd=cwd)
            if reason:
                print(f"[agent-boundary] {reason}", file=sys.stderr)
                return 1
    elif tool_name in ("Edit", "Write", "NotebookEdit"):
        fp = tool_input.get("file_path", "") or ""
        if fp:
            reason = check_write_allowed(acting_agent, fp, cwd=cwd)
            if reason:
                print(f"[agent-boundary] {reason}", file=sys.stderr)
                return 1
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        # 외부 시스템 mutation (git push / gh pr mutation) — sub-agent 차단 (#597 커밋5).
        # opt-out/infra 면 우회 (path 검사와 동일 우회 시맨틱).
        if not mutation_guard_off:
            reason = check_bash_mutation(cmd)
            if reason:
                print(f"[agent-boundary][Bash] {reason}", file=sys.stderr)
                return 1
        for fp in extract_bash_paths(cmd):
            # shell_context=True — Bash 추출 경로의 $VAR/$()/backtick 셸 확장 토큰 차단
            # (#694 codex P2). Edit/Write 의 literal 경로 검사(위)는 기본 False 라 영향 없음.
            reason = check_write_allowed(acting_agent, fp, cwd=cwd, shell_context=True)
            if reason:
                print(f"[agent-boundary][Bash] {reason}", file=sys.stderr)
                return 1
    elif tool_name.startswith("mcp__github__"):
        # GitHub MCP PR/repo mutation (merge_pull_request / push_files 등) — 차단 (#597 커밋5).
        # opt-out/infra 면 우회.
        reason = None if mutation_guard_off else check_github_mcp_mutation(tool_name)
        if reason:
            print(f"[agent-boundary][MCP] {reason}", file=sys.stderr)
            return 1

    # DCN-CHG-20260501-11 — sub 행동 trace append (rid 활성 시만)
    rid = _resolve_rid(sid, cc_pid, base_dir=base_dir)
    if rid:
        _append_trace_safe(
            sid,
            rid,
            {
                "phase": "pre",
                "agent": acting_agent,
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
    # issue #598 — payload agent_type(self-attribution) 우선, active_agent 폴백.
    acting_agent = _resolve_acting_agent(stdin_data, live)
    if not acting_agent:
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
        "agent": acting_agent,
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
        # issue #598 — sub_type 도 정규화 (histogram filter 가 정규화된 trace agent 와
        # 매칭하도록 + 라벨 canonical). namespaced(`dcness:engineer`) → `engineer`.
        sub_type = normalize_agent_type(
            str(tool_input.get("subagent_type", "") or "")
        ) or ""

    rid = _resolve_rid(sid, cc_pid, base_dir=base_dir)

    # #597 커밋6 — staging 실패 진단을 모델에도 노출 (기존엔 stderr→/tmp 로만 묻혀
    # histogram 있을 때만 additionalContext 출력 → prose 미staging 원인이 모델에 안 보임).
    diagnostics: list[str] = []

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
            diagnostics.append(
                f"prose 추출 예외 ({type(e).__name__}) — sub 결과 prose 가 run_dir 에 "
                f"미저장. 다음 step 전 직전 sub 의 결론을 메인이 직접 확인할 것."
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
            diagnostics.append(
                "sub 결과에서 prose 텍스트를 못 뽑아 run_dir staging skip "
                f"({_shape}) — 직전 sub 결론을 메인이 직접 확인 후 진행."
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
                    diagnostics.append(
                        "current_step 부재 — begin-step 호출 누락 의심. 이번 sub 결과가 "
                        "run_dir 에 미staging. 다음 step 은 begin-step 먼저 호출할 것."
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
                        diagnostics.append(
                            "current_step.agent 공백 — staging skip. begin-step 에 agent "
                            "인자가 빠졌는지 확인."
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
                diagnostics.append(
                    f"prose write 예외 ({type(e).__name__}) — run_dir staging 실패. "
                    f"직전 sub 결론을 메인이 직접 확인 후 진행."
                )

    # rid 활성 시만 측정 inject + redo_log auto append
    # #272 W1 자율 친화 재설계 — hook 은 *raw 측정 데이터* 만 inject.
    # "REDO_SUSPECT" 같은 결정 X. 임계값 X. prose-only 화이트리스트 X.
    # 메인 LLM 이 loop-procedure.md 의 표준 1 step 시퀀스 가이드 보고 자율 판단.
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
            # issue #598 multi-slot — 끝난 Agent 의 tool_use_id 로 그 슬롯만 정확 pop
            # (동시 Agent 시 다른 sub 의 pending 보존). tuid 없으면 단일 슬롯 폴백.
            pending = clear_pending_agent(
                sid, rid, tool_use_id=(tuid_now or None), base_dir=base_dir
            )
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

            # issue #598 finding1 — 시각 범위 + 끝난 sub 의 agent 로 필터해 동시
            # sub-agent 의 행동이 이 histogram 에 섞이지 않게 한다 (trace 가 payload
            # self-attribution 으로 정확한 agent 를 담으므로). sub_type 미상 시 시각만.
            #
            # ⚠️ 알려진 한계 (codex round3 P2 — 측정 신호 한정): *동일* subagent_type
            # 두 개가 시간대 겹쳐 동시 실행되면 둘의 trace agent 가 같아 시각+agent
            # 필터로도 분리 불가 → histogram/input-repeat 가 오귀속될 수 있다. invocation
            # 단위 분리는 trace 의 agent_id(=sub 식별) 로만 가능하나, 본 집계는 PostToolUse
            # Agent(메인 ctx, tool_use_id 키)에서 일어나고 CC hook payload 에 tool_use_id↔
            # agent_id join 이 없어(부모 Agent tool_use_id 는 sub trace 에 없음) 정확 매핑
            # 불가. 영향은 *측정 신호*(additionalContext) 뿐 — file-guard 경계는 per-call
            # self-attribution, prose staging 은 current_step 키라 무관. 동일-타입 동시
            # 실행은 순차 컨베이어에서 사실상 안 일어나는 엣지 → 측정 한정 수용 + follow-up.
            _agent_filter = sub_type or None
            hist = (
                _trace_hist_since(
                    sid, rid, since_ts, agent=_agent_filter, base_dir=base_dir
                )
                if since_ts else {}
            )
            # 같은 input 반복 — 메인 자율 판단용 raw 신호 (다중 파일 vs 동일 파일 구분)
            if since_ts:
                trace_subset = [
                    e for e in _trace_read(sid, rid, base_dir=base_dir)
                    if e.get("ts", "") >= since_ts
                    and (not _agent_filter or (e.get("agent", "") or "") == _agent_filter)
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
    # 메인 LLM 이 loop-procedure.md 의 표준 1 step 시퀀스 가이드 (REDO 판단 신호) 보고 자율 판단.
    # #597 커밋6 — histogram 없어도 staging 진단(diagnostics)이 있으면 모델에 노출.
    if histogram_str or diagnostics:
        lines = []
        if histogram_str:
            line = f"[감시자 hook] sub={sub_type or '?'} tool histogram: {histogram_str}"
            if input_repeats_str:
                line += f"\n같은 input 반복: {input_repeats_str}"
            lines.append(line)
        if diagnostics:
            lines.append("[staging 진단] " + " / ".join(diagnostics))
        ctx = "\n".join(lines)

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


def handle_subagent_stop(
    stdin_data: Optional[Dict[str, Any]] = None,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """SubagentStop 훅 — sub-agent 종료 시 live.json.active_agent 신뢰 clear (issue #598).

    PostToolUse Agent 매칭(취약 — 메인 ctx 에서 발화, agent_id 가 없을 수 있음)보다
    신뢰도 높은 SubagentStop(sub 종료 직발, agent_id+agent_type 동반)으로 단일 슬롯
    clear 를 승격한다. PostToolUse Agent 의 clear 는 그대로 유지 (이중 안전망, 멱등).

    match-guard: `live.active_agent == payload agent_type` 일 때만 clear — 동시
    sub-agent 환경에서 다른 agent 의 슬롯을 오클리어하지 않는다. agent_type 부재
    (구버전 CC) 시 best-effort 무조건 clear.

    차단 권한 사용 안 함 — 항상 `exit 0`. SubagentStop 에 `stop_hook_active` 가
    없고 본 핸들러는 block(decision) 도 안 쓰므로 무한 루프 무관.
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

    # issue #598 — namespaced(`dcness:engineer`) 정규화 후 match-guard 비교.
    agent_type = normalize_agent_type(stdin_data.get("agent_type", "") or "") or ""
    try:
        live = read_live(sid, base_dir=base_dir) or {}
        active_agent = live.get("active_agent") or ""
        if not active_agent:
            return 0  # 이미 clear됨 (PostToolUse Agent 선처리 / sub 아님) — noop
        # match-guard — agent_type 있으면 일치할 때만 clear. 부재 시 best-effort.
        # 양쪽 모두 정규화해 namespaced/legacy alias 불일치로 인한 미clear 방지.
        if agent_type and (normalize_agent_type(active_agent) or "") != agent_type:
            return 0
        update_live(sid, base_dir=base_dir, active_agent=None, active_mode=None)
    except (OSError, ValueError):
        pass  # clear 실패해도 sub 종료엔 영향 X (PostToolUse Agent 가 백업 clear)
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


def _has_module_architect_pass(rd: Path) -> bool:
    """module-architect prose PASS — 무모드 / occurrence / mode-suffixed 모두 인정 (#701).

    moded step 의 prose 파일명은 `<agent>-<MODE>.md` 라서, `/impl` Standard 의
    `module-architect:COMPACT_PLAN` PASS 는 `module-architect-COMPACT_PLAN.md`
    에 기록된다 — `_has_pass` 의 occurrence 카운터(-2..-9)만으로는 못 읽어
    engineer 게이트가 false-block 했다(#700 에서 #701 로 이연된 Finding C).

    engineer 게이트 전용 helper — pr-reviewer 게이트의 code-validator 는 mode
    별 의미가 달라(PLAN_VALIDATION ≠ CODE_VALIDATION) 일괄 glob 을 적용하면
    plan 단계 PASS 가 code 검증을 대신하는 새 구멍이 생긴다. `_has_pass` 는
    그대로 둔다.
    """
    if "PASS" in _read_or_empty(rd / "module-architect.md"):
        return True
    try:
        for prose in rd.glob("module-architect-*.md"):
            if "PASS" in _read_or_empty(prose):
                return True
    except OSError:
        pass
    return False


def _run_design_doc_exists(
    sid: str,
    rid: str,
    *,
    base_dir: Optional[Path] = None,
) -> bool:
    """현재 run 슬롯에 기록된 design_doc 이 디스크에 실존하는지 (#701).

    begin-run `--design-doc` 으로 기록된 머지된 설계 문서는 engineer 게이트의
    같은-run module-architect PASS 등가 prerequisite 증거다. 경로 규약 검증은
    기록 시점(start_run fail-fast)에 끝났고, 여기서는 실존만 재확인한다 (기록
    후 삭제 방어). 기록 부재 / state 읽기 실패는 종전과 동일하게 차단 측
    (fail-strict).
    """
    try:
        live = read_live(sid, base_dir=base_dir) or {}
        active = live.get("active_runs", {}) if isinstance(live, dict) else {}
        slot = active.get(rid, {}) if isinstance(active, dict) else {}
        doc = slot.get("design_doc") if isinstance(slot, dict) else None
        if not isinstance(doc, str) or not doc:
            return False
        return Path(doc).is_file()
    except (OSError, ValueError):
        return False


def _run_lane(
    sid: str,
    rid: str,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[str]:
    """현재 run 슬롯에 기록된 lane(설계도 유무) 반환 (#714).

    /impl 2축 모델의 lane 은 begin-run `--lane lite|standard` 로 start_run 슬롯에
    기록된다. engineer 게이트는 lane="lite"(설계도 없는 Lite lane) 를 설계 산출물
    prerequisite 면제 신호로 인정한다. 기록 부재 / state 읽기 실패는 None 반환 →
    종전 차단 경로(설계 산출물 요구)로 떨어진다 (면제 누수 차단, fail-strict).
    """
    try:
        live = read_live(sid, base_dir=base_dir) or {}
        active = live.get("active_runs", {}) if isinstance(live, dict) else {}
        slot = active.get(rid, {}) if isinstance(active, dict) else {}
        lane = slot.get("lane") if isinstance(slot, dict) else None
        return lane if isinstance(lane, str) else None
    except (OSError, ValueError):
        return None


def _is_design_loop(
    sid: str,
    rid: str,
    *,
    base_dir: Optional[Path] = None,
) -> bool:
    """현재 run 이 design 설계 루프인지 확인 (entry_point 기준).

    module-architect 게이트 발동 조건 — design 안 module-architect
    × K 첫 호출 직전 architecture-validator PASS 필수.
    """
    try:
        live = read_live(sid, base_dir=base_dir) or {}
        active = live.get("active_runs", {})
        if not isinstance(active, dict):
            return False
        slot = active.get(rid, {})
        entry = slot.get("entry_point", "") if isinstance(slot, dict) else ""
        return entry == "design"
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

    배경 (issue #382): /impl / /impl-loop / /design 등 컨베이어 루프
    종료 후 메인 Claude 가 `end-run` 까먹는 회귀 반복 발생. loop-procedure.md 의
    end-run 호출 prose 의무로는 본능 (PR merge 후 "작업 끝" 인지) 패배.

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

    review.md 본문 echo 는 *기존 prose 의무* (loop-procedure.md 의 Step 8 review 결과 인지 +
    run-review.md 의 Step 1 리포트 출력 + commands/impl.md 의 종료 조건) 에 의존.

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
        # 이슈 #587 — finalize-run 됐어도 end-run(run_finished) 미호출이면 run-review 의
        # list_runs(run_finished 요구)에서 안 보인다. ledger 에 run_finished 가 이미
        # 있으면 닫힌 것 → skip. 없으면 (finalize-only, end-run 까먹음) 아래 end-run 발사
        # 흐름으로 내려가 run_finished 를 보장한다.
        try:
            from harness import ledger as _ledger

            _ev = (
                _ledger.read_events(sid, rid, base_dir=base_dir)
                if base_dir
                else _ledger.read_events(sid, rid)
            )
            if any(e.get("event") == "run_finished" for e in _ev):
                return 0  # 이미 run_finished — 닫힘
        except Exception:
            return 0  # 판정 실패 시 보수적으로 skip (기존 동작 보존)
        # run_finished 부재 → 아래 end-run 발사로 finalize-only run 복구

    # end-step 완료 매칭 검사 (false positive 회피)
    # _read_steps_jsonl 마지막 row.(agent, mode) vs live.current_step.(agent, mode).
    # 일치 = end-step 호출됨 (step 종료 상태) / 불일치 = begin-step 후 end-step
    # 미호출 (sub-agent 진행 중 응답 종료 케이스 — end-run 발사 false positive).
    try:
        steps = _read_steps_jsonl(sid, rid, base_dir=base_dir)
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
    # build-worker 검증 실행 불가 — 메인 게이트 대행이 MUST 인 결론. 누락 시 메인 침묵
    # Stop 에서 auto end-run 으로 run 이 대행 없이 닫힌다 (#705 리뷰 — impl-loop-routing 짝).
    "VALIDATION_BLOCKED",
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

    next_hint = (
        "worker 가 남긴 검증 명령을 메인이 직접 실행(게이트 대행) 후 exit 0 이면 "
        "git/PR, FAIL 이면 engineer 재시도 라우팅. "
        if enum == "VALIDATION_BLOCKED"
        else "정의된 다음 agent 호출 또는 PR/review/merge 영역 "
        "(예: begin-step pr-reviewer + Agent pr-reviewer + end-step + PR 머지). "
    )
    reason = (
        f"[dcness Stop hook · issue #469 결함 A] sub-step "
        f"'{last_agent}{mode_suffix}' 결론 '{enum}' — 다음 sub-step 진입 turn "
        f"필요. {next_hint}"
        "사용자 의도로 정말 종료 "
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

    p_sas = sub.add_parser("subagent-stop",
                           help="SubagentStop 훅 — sub 종료 시 active_agent clear (issue #598)")
    p_sas.add_argument("--cc-pid", type=int, default=None)

    args = parser.parse_args(argv)

    # cc_pid 미명시 시 PPID 사용 (bash 훅 의 PPID = CC main)
    cc_pid = args.cc_pid if args.cc_pid is not None else os.getppid()

    # #597 codex P2 (round5) — fail-open 보장:
    # PreToolUse blocking hook 은 *정책 위반* 일 때만 process exit 2 (wrapper 차단 신호).
    # handler 가 return 1 (정책 위반) → exit 2. handler 내부 예외 (import 외 런타임) → exit 0 (fail-open).
    # 이로써 RC=2=정책차단 / RC=0=allow·fail-open / RC=1(파이썬 크래시·import 실패)=wrapper 가 fail-open.
    # (과거엔 정책위반·크래시 모두 RC=1 이라, wrapper 가 둘 다 exit 2 로 과차단했음 — hook 버그가 전 호출 차단.)
    blocking = args.cmd in ("pretooluse-agent", "pretooluse-file-op")
    try:
        if args.cmd == "session-start":
            rc = handle_session_start(cc_pid=cc_pid)
        elif args.cmd == "pretooluse-agent":
            rc = handle_pretooluse_agent(cc_pid=cc_pid)
        elif args.cmd == "pretooluse-file-op":
            rc = handle_pretooluse_file_op(cc_pid=cc_pid)
        elif args.cmd == "posttooluse-agent":
            rc = handle_posttooluse_agent(cc_pid=cc_pid)
        elif args.cmd == "posttooluse-file-op":
            rc = handle_posttooluse_file_op(cc_pid=cc_pid)
        elif args.cmd == "stop":
            rc = handle_stop()
        elif args.cmd == "subagent-stop":
            rc = handle_subagent_stop()
        else:
            rc = 0
    except Exception:  # noqa: BLE001 — hook 버그가 도구 호출을 과차단하지 않게 fail-open
        import traceback
        traceback.print_exc()
        return 0
    # 정책 위반(rc==1)은 blocking hook 에서만 exit 2. 그 외(비-blocking / allow) 는 0.
    if blocking and rc == 1:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
