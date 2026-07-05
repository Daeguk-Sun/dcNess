"""CLI handlers for step completion + run finalization (#469 / #520 / #587).

Split out of ``session_state_cli`` to keep the CLI dispatcher cohesive. The
public CLI surface is unchanged: ``session_state_cli`` re-exposes these names so
``python3 -m harness.session_state <end-step|finalize-run|auto-resolve>`` and the
``harness.session_state`` compatibility path keep working.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _parent_state_module():
    module = sys.modules.get("harness.session_state")
    if module is not None and hasattr(module, "read_live"):
        return module
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "read_live"):
        return main
    import harness.session_state as module

    return module


_state = _parent_state_module()
_now_iso = _state._now_iso
_read_steps_jsonl = _state._read_steps_jsonl
auto_detect_run_id = _state.auto_detect_run_id
auto_detect_session_id = _state.auto_detect_session_id
clear_current_step = _state.clear_current_step
diagnose_sid_rid_resolution = _state.diagnose_sid_rid_resolution
read_live = _state.read_live
record_fail_open_event = _state.record_fail_open_event
run_dir = _state.run_dir
session_dir = _state.session_dir
update_live = _state.update_live


_SUMMARY_LINE_LIMIT = 12      # prose 요약 최대 줄 수 (DCN-CHG-30-11: 8 → 12)
_SUMMARY_CHAR_LIMIT = 1200    # 요약 총 길이 cap (DCN-CHG-30-11: 600 → 1200)

# 결론/요약 섹션 헤더 후보 — case-insensitive 매칭 (한국어 + 영어 혼용).
# `\b` 는 한국어에 잘못 동작 (word boundary 가 ASCII 만) — 사용 X. 대신 끝에
# 공백/끝 또는 한국어 조사 후속 허용 패턴.
_CONCLUSION_HEADER_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*"
    r"(결론|결과|요약|변경\s*요약|변경\s*사항|변경\s*내용|"
    r"conclusion|summary|result|key\s*changes?|outcome|verdict)"
    r"(\s|$|:|—|-)",
    re.IGNORECASE,
)


def _extract_section_after_header(prose: str, max_lines: int, char_cap: int) -> str:
    """결론/요약 섹션 헤더를 찾아 그 다음 본문 추출.

    헤더 부재 시 빈 문자열 반환 (caller 가 fallback 사용).
    """
    lines = prose.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if _CONCLUSION_HEADER_RE.match(line):
            start = i + 1
            break
    if start < 0:
        return ""
    out: list = []
    total = 0
    for line in lines[start:]:
        rstripped = line.rstrip()
        stripped = rstripped.lstrip()
        # 다음 동급 이상 헤더 만나면 종료
        if stripped.startswith("#"):
            if out:  # 본문이 시작된 후 만나는 다음 헤더 = 섹션 종료
                break
            continue
        if not stripped and not out:
            continue  # 헤더 직후 빈 줄 skip
        out.append(rstripped)
        total += len(rstripped) + 1
        if len(out) >= max_lines or total >= char_cap:
            break
    # 끝 trailing 빈 줄 제거
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _extract_prose_summary(prose: str, *, max_lines: int = _SUMMARY_LINE_LIMIT) -> str:
    """prose 의 결론/요약 섹션 우선 추출, 없으면 첫 의미 있는 N 줄 fallback.

    의도: skill bash 에서 helper 호출 후 stderr 로 흘려 사용자 가시성 ↑. agent prose 가
    대개 마지막에 `## 결론` / `## Summary` / `## 변경 요약` 섹션 씀 — 그 섹션이 가장
    정보 밀도 높음. 첫 N 줄 무차별 추출보다 효과적.

    DCN-CHG-30-11 (이전 8 줄 / 600 char → 12 줄 / 1200 char) — 사용자 가시성 ↑ 위해 cap 확장.
    """
    char_cap = _SUMMARY_CHAR_LIMIT if max_lines == _SUMMARY_LINE_LIMIT else max_lines * 100
    # 1단계: 결론/요약 섹션 우선
    section = _extract_section_after_header(prose, max_lines, char_cap)
    if section:
        return section
    # 2단계: fallback — 첫 의미 있는 줄
    out_lines: list = []
    total_chars = 0
    for raw in prose.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped:
            continue
        # skip 첫 markdown 헤더만 (정보 부족)
        if stripped.startswith("#") and len(stripped) < 40 and len(out_lines) == 0:
            continue
        out_lines.append(line)
        total_chars += len(line) + 1
        if len(out_lines) >= max_lines or total_chars >= char_cap:
            break
    return "\n".join(out_lines)


def _find_prose_fallback(sid: str, rid: str, agent: str, mode: Optional[str]) -> Optional[str]:
    """hook staging 실패 시 run_dir 에서 prose 파일 패턴 탐색 fallback."""
    try:
        rd = run_dir(sid, rid)
        stem = f"{agent}-{mode}" if mode else agent
        base_path = rd / f"{stem}.md"
        if base_path.exists():
            return str(base_path)
        candidates = sorted(rd.glob(f"{stem}-*.md"), key=lambda p: p.stat().st_mtime)
        if candidates:
            return str(candidates[-1])
    except Exception:  # nosec B110
        pass
    return None


def _cli_end_step(args: Any) -> int:
    """sid+rid auto-detect → write_prose → prose-only (PROSE_LOGGED).

    부수 출력: stderr 로 `[agent:mode = PROSE_LOGGED]` 헤더 + prose 요약 ~5줄. 모든
    skill 자동 수혜 — skill prompt 안에 별도 요약 instruction 쓸 필요 0.
    """
    from harness.signal_io import write_prose

    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1

    mode = args.mode if args.mode else None
    # #700 — end-step 의 agent 도 canonical 정규화. namespaced 로 begin-step+Agent 한 뒤
    # end-step 을 namespaced 로 호출해도 write_prose 이름 검증(콜론 거부)에 안 걸리고,
    # begin-step 이 정규화 저장한 current_step.agent(bare)와 DRIFT 오탐 없이 일치한다.
    from harness.agent_names import normalize_agent_type
    agent = normalize_agent_type(args.agent) or args.agent

    # DCN-CHG-20260430-25: drift detector — current_step 와 end-step agent 불일치 시 WARN.
    # 메인 Claude 가 begin-step 안 부르고 end-step 호출하거나, 다른 agent 에 대한
    # begin-step 이후 다른 agent end-step 부르는 경우 잡음. 자동 보정 X (안전).
    try:
        live = read_live(sid)
        slot = live.get("active_runs", {}).get(rid, {}) if live else {}
        cur_step = slot.get("current_step") if slot else None
        if cur_step:
            cur_agent = cur_step.get("agent")
            cur_mode = cur_step.get("mode")
            if cur_agent and cur_agent != agent:
                print(
                    f"[session_state] DRIFT WARN — current_step={cur_agent}"
                    f"{':' + cur_mode if cur_mode else ''} but end-step={agent}"
                    f"{':' + mode if mode else ''}. begin-step 누락 의심.",
                    file=sys.stderr,
                )
            elif cur_mode and mode and cur_mode != mode:
                print(
                    f"[session_state] DRIFT WARN — current_step mode={cur_mode} "
                    f"but end-step mode={mode}. begin-step 누락 의심.",
                    file=sys.stderr,
                )
        else:
            # current_step 자체 부재 — begin-step 안 부른 경우 (engineer auto-PR 후 등).
            print(
                f"[session_state] DRIFT WARN — current_step 부재. "
                f"end-step={agent}{':' + mode if mode else ''}. "
                f"begin-step 안 호출하고 end-step 호출. ledger.jsonl 에 기록은 됨.",
                file=sys.stderr,
            )
    except Exception:  # nosec B110
        # drift detector 자체 실패는 silent — end-step 동작 우선
        pass

    # DCN-CHG-20260501-15: prose 로딩 — --prose-file 제공 시 legacy 경로, 없으면 hook auto-stage.
    if args.prose_file:
        prose = Path(args.prose_file).read_text(encoding="utf-8")
        if not prose.strip():
            print("[session_state] empty prose", file=sys.stderr)
            return 1
        base = session_dir(sid) / "runs"
        occ = _count_step_occurrences(sid, rid, agent, mode)
        prose_path = write_prose(agent, rid, prose, mode=mode, base_dir=base, occurrence=occ)
    else:
        # hook auto-staged prose — live.json.current_step.prose_file 에서 경로 읽기
        try:
            _live = read_live(sid)
            _slot = _live.get("active_runs", {}).get(rid, {}) if _live else {}
            _cur = _slot.get("current_step") if isinstance(_slot, dict) else None
            _staged = _cur.get("prose_file") if isinstance(_cur, dict) else None
        except Exception:
            _staged = None
        if not _staged:
            _staged = _find_prose_fallback(sid, rid, agent, mode)
            if _staged:
                print(
                    f"[session_state] hook staging fallback → {Path(_staged).name}",
                    file=sys.stderr,
                )
        if not _staged:
            print("[session_state] --prose-file 미제공 + hook staging 없음", file=sys.stderr)
            return 1
        prose_path = Path(_staged)
        if not prose_path.exists():
            print(f"[session_state] hook staged prose_file 없음: {prose_path}", file=sys.stderr)
            return 1
        prose = prose_path.read_text(encoding="utf-8")
        if not prose.strip():
            print("[session_state] empty prose (hook staged)", file=sys.stderr)
            return 1

    # 자유서술 방식 (이슈 #280/#284) — 메인 Claude 가 prose 자체를 직접 읽고 분기 결정.
    # stdout 은 sentinel "PROSE_LOGGED" 로 통일. 옛 enum 기계 추출은 폐기.
    agent_label = agent if not mode else f"{agent}:{mode}"

    print("PROSE_LOGGED")
    print(f"[{agent_label} = PROSE_LOGGED]", file=sys.stderr)
    summary = _extract_prose_summary(prose)
    if summary:
        print(summary, file=sys.stderr)
    # step status append — finalize-run / 회고용
    _append_step_status(
        sid,
        rid,
        agent,
        mode,
        "PROSE_LOGGED",
        prose,
        prose_path,
        provider=getattr(args, "provider", None),
    )
    clear_current_step(sid, rid, agent=agent, mode=mode)
    return 0


# ── step status log + finalize-run + auto-resolve ────────────────────


_MUST_FIX_RE = re.compile(r"\bMUST[\s_-]?FIX\b", re.IGNORECASE)

# 같은 줄 부정 패턴 — "MUST FIX 0" / "MUST FIX 없음" / "no must fix"
# DCN-CHG-20260523 (#484 Case 2): between 영역 `[\s:=]*` → `[^\n]{0,30}?` 로 일반화.
# jajang `**MUST FIX 항목**: 없음` 패턴 (한국어 라벨 + markdown bold + 콜론 끼임)
# 회귀 차단. 30자 한도 = `MUST FIX` 직후 같은 라인 안 짧은 라벨 + 부정 어휘만 흡수.
_MUST_FIX_NEGATION_RE = re.compile(
    r"\bMUST[\s_-]?FIX\b[^\n]{0,30}?"
    r"(?:\b0(?!\s*\d)|없[음다]|해당\s*없[음다])"
    r"|\bno\s+MUST[\s_-]?FIX\b",
    re.IGNORECASE,
)
# Markdown 헤더 단독 줄 — "## MUST FIX" 처럼 내용 없이 헤더만
_MUST_FIX_HEADER_ONLY_RE = re.compile(r'^\s*#{1,6}\s*MUST[\s_-]?FIX\s*$', re.IGNORECASE)
# 헤더 다음 줄 부정 패턴 — "없음." / "0건" / "해당 없음" 등
_NEXT_LINE_NEGATION_RE = re.compile(
    r'^(?:없[음다]\.?|0건|0개|해당\s*없[음다]\.?|없습니다\.?)\s*$',
    re.IGNORECASE,
)


def _has_positive_must_fix(prose: str) -> bool:
    """prose 안 MUST FIX 가 *positive* (실제 fix 요청) 의미로 등장했는지.

    검사 절차:
      1. MUST FIX 매칭 0개 → False
      2. 라인 단위 — 같은 줄 부정 컨텍스트 → skip
      3. Markdown 헤더 단독 줄 (## MUST FIX) → 다음 비어있지 않은 줄이 부정이면 skip
      4. 위 조건 모두 통과 → True (실제 fix 항목 존재)
    """
    if not _MUST_FIX_RE.search(prose):
        return False
    lines = prose.splitlines()
    for i, line in enumerate(lines):
        if not _MUST_FIX_RE.search(line):
            continue
        if _MUST_FIX_NEGATION_RE.search(line):
            continue  # 같은 줄 부정
        if _MUST_FIX_HEADER_ONLY_RE.match(line):
            # 헤더 단독 줄 — 다음 의미있는 줄 확인
            next_content = next(
                (line.strip() for line in lines[i + 1:] if line.strip()), ""
            )
            if not next_content or _NEXT_LINE_NEGATION_RE.match(next_content):
                continue  # 다음 줄이 없거나 부정 → false positive
        return True
    return False


def _count_step_occurrences(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """(agent, mode) step_completed 수 반환 (write_prose occurrence 계산용 — 이슈 #587).

    `ledger.count_step_completed` 위임 (ledger.jsonl 우선, 옛 .steps.jsonl 폴백).
    """
    from harness import ledger

    return ledger.count_step_completed(sid, rid, agent, mode, base_dir=base_dir)


def _append_step_status(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    enum: str,
    prose: str,
    prose_path: "Path",
    *,
    provider: Optional[str] = None,
) -> None:
    """end-step 호출마다 ledger.jsonl 에 step_completed event append (이슈 #587).

    옛 단일 .steps.jsonl row → `ledger.append_step_completed` 위임. receipt
    (sha256 / evidence_paths / next_action) 가 옛 필드 (prose_excerpt / must_fix /
    prose_file) 의 superset 으로 기록된다. prose 가 SSOT, ledger 는 색인 장부.
    """
    from harness import ledger

    ledger.append_step_completed(
        sid, rid, agent, mode, enum, prose, prose_path, provider=provider
    )
    try:
        if agent == "build-worker" and provider in {"codex-headless", "claude-headless"}:
            from harness.run_review import _extract_conclusion_enum

            if _extract_conclusion_enum(prose) == "VALIDATION_BLOCKED":
                ledger.append_event(
                    sid,
                    rid,
                    "blocked",
                    agent=agent,
                    mode=mode,
                    provider=provider,
                    category="headless_validation_blocked",
                    prose_file=str(prose_path),
                    detail=(
                        "headless build-worker reported VALIDATION_BLOCKED; "
                        "main must run the validation command fallback"
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        record_fail_open_event(
            hook="headless-validation-blocked-ledger",
            category="metric_write_error",
            detail=f"{type(exc).__name__}: {exc}",
        )


def _record_design_run_if_applicable(sid: str, rid: str) -> None:
    """Write durable design-run index when the active run is entry_point=design."""
    try:
        from harness import design_run_records

        record = design_run_records.write_design_record(
            run_dir(sid, rid), repo_path=Path.cwd()
        )
        if record is not None:
            path = design_run_records.design_record_path(
                design_run_records.resolve_repo_root(Path.cwd())
            )
            print(
                f"[design-record] {path} updated for {rid}",
                file=sys.stderr,
            )
    except Exception as exc:  # nosec B110
        print(
            f"[design-record] WARN — durable design run record skipped: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def _latest_step_per_role(steps: list) -> list:
    """`steps` 의 같은 (agent, mode) 쌍 중 *마지막* entry 만 골라 반환 (#272 W4).

    POLISH/retry 사이클 완료 후 PASS 으로 해소된 must_fix 가 has_must_fix 에 sticky
    되는 문제 해결용. 최신 step 만 봄으로써 step #N 이 FAIL → step #M
    이 PASS 이면 latest = PASS (must_fix=False) 로 평가.

    입력 순서 (시간 순) 유지 — 같은 키 마지막 발생.
    """
    out: dict = {}
    for s in steps:
        if not isinstance(s, dict):
            continue
        key = (s.get("agent"), s.get("mode"))
        out[key] = s
    return list(out.values())


def _cli_finalize_run(args: Any) -> int:
    """현재 run 의 step status JSON 출력 (skill 이 clean 판정용으로 소비).

    출력 (stdout, JSON 한 줄):
        {
          "run_id": "...",
          "session_id": "...",
          "steps": [{agent, mode, enum, must_fix, prose_excerpt}, ...],
          "has_ambiguous": bool,
          "has_must_fix": bool,
          "step_count": N
        }

    skill 이 expected enum 매트릭스와 비교해 clean/caveat 결정.
    """
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(json.dumps({"error": "sid/rid 미해결"}), file=sys.stderr)
        return 1
    steps = _read_steps_jsonl(sid, rid)
    # #272 W4 — has_must_fix sticky on PASS 수정. POLISH/retry 로 해소된 must_fix 가
    # sticky 로 남아 PASS final step 임에도 caveat 진입했음. 같은 (agent, mode) 의
    # *마지막* 발생만 평가해서 후속 step 에서 해소된 신호를 정합 처리.
    latest_steps = _latest_step_per_role(steps)
    has_ambiguous = any(s.get("enum") == "AMBIGUOUS" for s in latest_steps)
    has_must_fix = any(s.get("must_fix") for s in latest_steps)

    # DCN-CHG-20260430-25: --expected-steps 검증 — skill 이 정상 시퀀스 step 수
    # 명시 시 ledger.jsonl step_completed 수 미만이면 stderr WARN. /impl-loop 자기검증.
    expected = getattr(args, "expected_steps", None)
    if expected is not None and len(steps) < expected:
        print(
            f"[session_state] STEP COUNT WARN — ledger.jsonl step_completed={len(steps)} < "
            f"expected={expected}. inner step 누락 의심 — Agent 호출 후 end-step "
            f"안 부른 케이스 (drift). /run-review 로 진단 권고.",
            file=sys.stderr,
        )

    payload = {
        "run_id": rid,
        "session_id": sid,
        "steps": steps,
        "has_ambiguous": has_ambiguous,
        "has_must_fix": has_must_fix,
        "step_count": len(steps),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # finalized_at 플래그 — end-run 이 미호출 감지용.
    try:
        _live = read_live(sid)
        _active = _live.get("active_runs", {}) if _live else {}
        if isinstance(_active, dict) and rid in _active:
            _slot = dict(_active[rid])
            _slot["finalized_at"] = _now_iso()
            _active[rid] = _slot
            update_live(sid, active_runs=_active)
    except Exception:  # nosec B110
        pass

    # DCN-CHG-20260430-29: --auto-review flag — in-process /run-review chained.
    # 메인 Claude 가 finalize-run 호출만 하면 review 자동 piggy-back. 의도적 skip 불가.
    # SessionEnd 훅 reject (cross-session run false positive 우려).
    if getattr(args, "auto_review", False):
        print()
        print("--- /run-review (auto) ---")
        try:
            import io
            from harness import run_review as _rv  # lazy import (test mock 용이)
            _buf = io.StringIO()
            _old_stdout = sys.stdout
            sys.stdout = _buf
            try:
                _rv.main(["--run-id", rid, "--repo", str(Path.cwd())])
            except SystemExit:
                pass
            finally:
                sys.stdout = _old_stdout
            review_text = _buf.getvalue()
            if review_text:
                print(review_text)
                try:
                    review_path = run_dir(sid, rid) / "review.md"
                    review_path.write_text(review_text, encoding="utf-8")
                    print(
                        f"[REVIEW_READY] {review_path} — 위 리뷰를 세션에 그대로 출력할 것 (loop-procedure.md 의 Step 8 review 결과 인지)",
                        file=sys.stderr,
                    )
                except Exception:  # nosec B110
                    pass
        except Exception as exc:
            print(
                f"[session_state] AUTO_REVIEW_FAIL — {type(exc).__name__}: {exc}. "
                f"수동 `dcness-review --run-id {rid}` 1회 재시도 권장.",
                file=sys.stderr,
            )

    # issue #392 — auto accumulate 매커니즘 폐기. 자동 redo/wastes/goods 누적이
    # jajang 실측 100% baseline 노이즈 (PROSE_ECHO_OK) 만 만들어냄. 메인 자율
    # 평가는 PR3 의 `insight` CLI 로 대체.

    _record_design_run_if_applicable(sid, rid)

    return 0


# yolo 모드 폴백 매트릭스 — agent + ESCALATE/CLARITY 시 권장 행동
_YOLO_FALLBACKS: Dict[str, Dict[str, Optional[str]]] = {
    "ux-architect:UX_FLOW_ESCALATE": {
        "action": "re-invoke",
        "hint": (
            "NoUI 프로젝트 케이스 — minimal UX_FLOW_PATCHED prose 작성 (UI 없음 1줄 ack) "
            "후 advance"
        ),
        "next_enum": "UX_FLOW_PATCHED",
    },
    "product-planner:CLARITY_INSUFFICIENT": {
        "action": "re-invoke",
        "hint": "agent 권고 그대로 채택 — 모든 항목 default 채택 + 재호출",
        "next_enum": "PRODUCT_PLAN_READY",
    },
    "architect:SPEC_GAP_FOUND": {
        "action": "escalate-or-architect-spec-gap",
        "hint": "SPEC_GAP cycle 진입 (architect SPEC_GAP) 또는 사용자 위임",
        "next_enum": "SPEC_GAP_RESOLVED",
    },
    "code-validator:FAIL": {
        "action": "re-invoke-prev",
        "hint": "engineer 재호출 (FAIL 본문 보고) — attempt < 3",
        "next_enum": None,
    },
    "code-validator:ESCALATE": {
        "action": "escalate-or-architect-spec-gap",
        "hint": "본문 사유 prose 확인: spec 부재면 architect SPEC_GAP, 그 외면 사용자 위임",
        "next_enum": None,
    },
    "architecture-validator:FAIL": {
        # 분류 의존 분기 — 단일 정적 action 으로 target 을 못 정한다.
        # re-invoke(현재=read-only validator 재호출, 같은 FAIL 반복) X.
        # re-invoke-prev(직전 step 고정) X — Step 5 SYSTEM_BOUNDARY 는 직전이 module-architect
        # 라도 target 이 system-architect. 실제 target 은 finding 분류(hint)가 진본 —
        # 메인이 분류를 읽고 분기, 분류 모호하면 사용자 위임 (mechanical 재호출 금지).
        "action": "route-by-classification",
        "hint": (
            "validator 재호출 X — finding 분류로 architect 분기 (design-routing): "
            "SYSTEM_BOUNDARY → system-architect 재진입 / "
            "CONTRACT_PROPAGATION → module-architect mode=contract_sweep / "
            "TASK_LOCAL → module-architect 보강(해당 task). 분류 모호 시 사용자 위임 (cycle ≤ 2)"
        ),
        "next_enum": None,
    },
    "*:AMBIGUOUS": {
        "action": "user-delegate",
        "hint": "재호출 1회 시도. 그래도 모호 → 사용자 위임 (yolo 도 hard safety 보존)",
        "next_enum": None,
    },
}


def _cli_auto_resolve(args: Any) -> int:
    """yolo 모드 — enum + agent[:mode] 받아 권장 액션 JSON 반환.

    skill 이 yolo keyword 검출 시 호출. 권장 액션 = {action, hint, next_enum}.
    매핑 없으면 `unmapped` 반환 — skill 이 사용자 위임 fallback.

    catastrophic 룰 우회 X — yolo 는 skill-level 확인 prompt 자동화만.
    """
    key = args.agent_mode  # 예: "ux-architect:UX_FLOW_ESCALATE" 또는 "code-validator:FAIL"
    fallback = _YOLO_FALLBACKS.get(key)
    if fallback is None:
        # AMBIGUOUS 통합 케이스 — 어떤 agent 든 동일 권장
        if key.endswith(":AMBIGUOUS"):
            fallback = _YOLO_FALLBACKS["*:AMBIGUOUS"]
    if fallback is None:
        print(json.dumps({"action": "unmapped", "key": key}, ensure_ascii=False))
        return 1
    print(json.dumps({"key": key, **fallback}, ensure_ascii=False))
    return 0
