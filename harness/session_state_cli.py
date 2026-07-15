"""CLI handlers for ``python3 -m harness.session_state``."""
from __future__ import annotations

import importlib
import json
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
_PPID_LOOKUP_TIMEOUT_SEC = _state._PPID_LOOKUP_TIMEOUT_SEC
_VALID_DESIGN_STAGES = _state._VALID_DESIGN_STAGES
_VALID_LANES = _state._VALID_LANES
_active_worktree_root_for_prompt = _state._active_worktree_root_for_prompt
_clear_default_base_cache = _state._clear_default_base_cache
_default_base = _state._default_base
_ledger_run_started = _state._ledger_run_started
_now_iso = _state._now_iso
_prompt_slot_check_text = _state._prompt_slot_check_text
_read_steps_jsonl = _state._read_steps_jsonl
_resolve_state_root_for_cwd = _state._resolve_state_root_for_cwd
_scan_recent_active_run_slot = _state._scan_recent_active_run_slot
_validate_design_doc = _state._validate_design_doc
auto_detect_run_id = _state.auto_detect_run_id
auto_detect_session_id = _state.auto_detect_session_id
clear_current_step = _state.clear_current_step
clear_pid_current_run = _state.clear_pid_current_run
complete_run = _state.complete_run
current_session_id = _state.current_session_id
diagnose_sid_rid_resolution = _state.diagnose_sid_rid_resolution
evaluate_order_gate_for_step = _state.evaluate_order_gate_for_step
generate_run_id = _state.generate_run_id
get_cc_pid_via_ppid_chain = _state.get_cc_pid_via_ppid_chain
read_live = _state.read_live
record_fail_open_event = _state.record_fail_open_event
run_dir = _state.run_dir
session_dir = _state.session_dir
start_run = _state.start_run
update_current_step = _state.update_current_step
update_live = _state.update_live
valid_cc_pid = _state.valid_cc_pid
valid_session_id = _state.valid_session_id
write_pid_current_run = _state.write_pid_current_run
write_pid_session = _state.write_pid_session
_activation = importlib.import_module("harness.session_state_activation")
disable_project = _activation.disable_project
enable_project = _activation.enable_project
is_project_active = _activation.is_project_active
_resolve_project_root = _activation._resolve_project_root
whitelist_path = _activation.whitelist_path

_fail_open = importlib.import_module("harness.session_state_fail_open")
collect_fail_open_summary = _fail_open.collect_fail_open_summary
format_fail_open_warning = _fail_open.format_fail_open_warning

_status = importlib.import_module("harness.session_state_status")
collect_status_diagnostics = _status.collect_status_diagnostics
format_status_report = _status.format_status_report
_is_self_repo = _status._is_self_repo

# peer parallelism (wave board + merge lock) handlers live in a cohesive
# sibling module; import them here because this dispatcher owns the CLI parser.
from harness.session_state_cli_wave import (  # noqa: E402
    _cli_merge_lock as _cli_merge_lock,
    _cli_normalize_scope as _cli_normalize_scope,
    _cli_wave_claim as _cli_wave_claim,
    _cli_wave_heartbeat as _cli_wave_heartbeat,
    _cli_wave_plan as _cli_wave_plan,
    _cli_wave_reclaim as _cli_wave_reclaim,
    _cli_wave_release as _cli_wave_release,
    _cli_wave_status as _cli_wave_status,
    _current_branch_fallback as _current_branch_fallback,
    _current_merge_lock as _current_merge_lock,
    _current_wave_board as _current_wave_board,
    _json_stdout as _json_stdout,
    _merge_order_base_ref as _merge_order_base_ref,
    _repo_root_from_state_root as _repo_root_from_state_root,
)

# step completion + run finalization handlers live in a cohesive sibling
# module; import them here because _cli_end_run and the parser dispatch to them.
from harness.session_state_cli_finalize import (  # noqa: E402
    _CONCLUSION_HEADER_RE as _CONCLUSION_HEADER_RE,
    _MUST_FIX_HEADER_ONLY_RE as _MUST_FIX_HEADER_ONLY_RE,
    _MUST_FIX_NEGATION_RE as _MUST_FIX_NEGATION_RE,
    _MUST_FIX_RE as _MUST_FIX_RE,
    _NEXT_LINE_NEGATION_RE as _NEXT_LINE_NEGATION_RE,
    _YOLO_FALLBACKS as _YOLO_FALLBACKS,
    _append_step_status as _append_step_status,
    _cli_auto_resolve as _cli_auto_resolve,
    _cli_end_step as _cli_end_step,
    _cli_finalize_run as _cli_finalize_run,
    _count_step_occurrences as _count_step_occurrences,
    _extract_prose_summary as _extract_prose_summary,
    _extract_section_after_header as _extract_section_after_header,
    _find_prose_fallback as _find_prose_fallback,
    _has_positive_must_fix as _has_positive_must_fix,
    _latest_step_per_role as _latest_step_per_role,
    _record_design_run_if_applicable as _record_design_run_if_applicable,
)

# ── CLI (python3 -m harness.session_state <subcommand>) ─────────────

def _cli_init_session(args: Any) -> int:
    """SessionStart 훅이 호출. by-pid 작성 + live.json 초기화."""
    if not valid_session_id(args.sid):
        print(f"[session_state] invalid sid: {args.sid!r}", file=sys.stderr)
        return 1
    if not valid_cc_pid(args.cc_pid):
        print(f"[session_state] invalid cc_pid: {args.cc_pid!r}", file=sys.stderr)
        return 1
    write_pid_session(args.cc_pid, args.sid)
    if not read_live(args.sid):
        update_live(args.sid)  # 빈 active_runs 로 초기화
    return 0


def _cli_begin_run(args: Any) -> int:
    """sid auto-detect → rid 생성 → start_run + by-pid-current-run."""
    sid = auto_detect_session_id()
    if not sid:
        print(diagnose_sid_rid_resolution(mode="sid"), file=sys.stderr)
        return 1
    rid = generate_run_id()
    issue_num = args.issue_num if args.issue_num is not None else None
    design_doc = getattr(args, "design_doc", None)
    lane = getattr(args, "lane", None)
    stage = getattr(args, "stage", None)
    acceptance_required = bool(getattr(args, "acceptance_required", False))
    try:
        start_run(
            sid, rid, args.entry_point,
            issue_num=issue_num, design_doc=design_doc, lane=lane, stage=stage,
            acceptance_required=acceptance_required,
        )
    except ValueError as exc:
        print(f"[begin-run] FAIL — {exc}", file=sys.stderr)
        return 1
    _ledger_run_started(
        sid, rid, args.entry_point,
        issue_num=issue_num, design_doc=design_doc, lane=lane, stage=stage,
        acceptance_required=acceptance_required,
    )
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        write_pid_current_run(cc_pid, rid)
    print(rid)
    return 0


def _cli_end_run(args: Any) -> int:
    """sid+rid auto-detect → complete_run + clear by-pid-current-run."""
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1

    # finalize-run 미호출 시 자동 실행 — 모델이 Step 7 건너뛴 경우 안전망.
    try:
        import argparse as _ap
        _live = read_live(sid)
        _active = _live.get("active_runs", {}) if _live else {}
        _slot = _active.get(rid, {}) if isinstance(_active, dict) else {}
        if not _slot.get("finalized_at"):
            print(
                "[session_state] finalize-run 미호출 감지 — auto-running finalize-run --auto-review",
                file=sys.stderr,
            )
            _fake = _ap.Namespace(
                expected_steps=None,
                auto_review=True,
            )
            _cli_finalize_run(_fake)
    except Exception as exc:
        print(f"[session_state] end-run finalize guard FAIL — {exc}", file=sys.stderr)

    complete_run(sid, rid)
    # 이슈 #587 — ledger run_finished checkpoint (complete_run 후 = run 종료 기록).
    try:
        from harness import ledger
        ledger.append_event(sid, rid, "run_finished")
    except Exception:  # nosec B110
        pass
    try:
        from harness.loop_lessons import sync_from_run

        changed = sync_from_run(run_dir(sid, rid), repo_path=Path.cwd())
        if changed:
            changed_list = ", ".join(str(path) for path in changed)
            print(f"[lessons] updated: {changed_list}", file=sys.stderr)
    except Exception as exc:  # nosec B110
        print(
            f"[lessons] WARN — recurrent lesson sync skipped: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    _record_design_run_if_applicable(sid, rid)
    try:
        warning = format_fail_open_warning(collect_fail_open_summary(cwd=Path.cwd()))
        if warning:
            print(warning, file=sys.stderr)
    except Exception:  # nosec B110
        pass
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        clear_pid_current_run(cc_pid)
    return 0


def _cli_post_task_begin(args: Any) -> int:
    """issue #472 — `/impl-loop` 종료 후 메인 자율 작업 영역 진입 marker.

    /impl-loop task 영역 (begin-run → build-worker → impl-validator → end-run) *외*
    자율 작업 (이슈 등록 / cleanup / 분석) 의 turn 을 task ROI 측정과 분리하기
    위한 marker. 본 호출 후 JSONL parser / run_review 가 marker timestamp 이후
    turn 을 *post-task 영역* 으로 분리 측정 → task당 평균 turn 왜곡 (jajang #446
    2차 측정 task3 사례 99 vs 81 = 18 turn 차이) 해소.

    동작:
    1. sid auto-detect (없으면 silent 0 — /impl-loop 외 호출 가능)
    2. live.json 에 `post_task_markers` list append (timestamp + reason)
    3. stdout = 메인이 자율 진입 self-aware 메시지

    Usage:
        dcness-helper post-task-begin [--reason "이슈 등록 / cleanup / 분석"]

    Exit codes:
        0 — 정상 (marker 있음) 또는 sid 미해결 (silent skip)
    """
    sid = auto_detect_session_id()
    if not sid:
        print(
            "[post-task-begin] sid 미해결 — marker skip "
            "(SessionStart 훅 미실행 또는 비활성 프로젝트)",
            file=sys.stderr,
        )
        return 0

    reason = (getattr(args, "reason", "") or "").strip()
    now = _now_iso()

    try:
        live = read_live(sid) or {}
    except Exception:
        live = {}
    markers = live.get("post_task_markers") if isinstance(live, dict) else None
    if not isinstance(markers, list):
        markers = []
    markers.append({"at": now, "reason": reason})
    # FIFO cap 20 (오래된 marker 자동 trim)
    if len(markers) > 20:
        markers = markers[-20:]

    try:
        update_live(sid, post_task_markers=markers)
    except Exception as exc:
        print(f"[post-task-begin] live.json update FAIL — {exc}", file=sys.stderr)
        return 0

    print("=== post-task area begin (issue #472) ===")
    print(f"timestamp: {now}")
    print(f"session_id: {sid}")
    print(f"marker count: {len(markers)}")
    if reason:
        print(f"reason: {reason}")
    print(
        "본 marker 후 turn 영역 = /impl-loop task 영역 외 (자율 이슈 등록 / "
        "cleanup / 분석 등). 측정 도구가 marker timestamp 이후 turn 분리."
    )
    print("=== /post-task area begin ===")
    return 0


def _cli_next_task(args: Any) -> int:
    """issue #471 — multi-task 사이 영역 (review echo + 다음 task 진입) 자동화.

    이전 run end-run + 새 run begin-run + previous review.md 본문 stdout 통합 →
    /impl-loop driver 의 task 경계 ~27 turn 영역을 1 helper 호출로 압축.

    동작:
    1. 현재 sid 해결 (없으면 exit 1)
    2. 이전 run (있으면) end-run 자동 호출 (finalize-run guard + complete_run + clear)
    3. 이전 run 의 review.md 본문 stdout (메인이 echo 만, 본문은 디스크 보존)
    4. 새 run begin-run + by-pid-current-run 갱신
    5. stdout = previous review + 새 run_id + 새 run_dir

    Usage:
        dcness-helper next-task [--entry-point impl] [--design-doc <path>]

    Exit codes:
        0 — 정상 (이전 run finalize + 새 run 발급)
        1 — sid 미해결 / design_doc 검증 실패
    """
    sid = auto_detect_session_id()
    if not sid:
        print(diagnose_sid_rid_resolution(mode="sid"), file=sys.stderr)
        return 1

    entry_point = getattr(args, "entry_point", "impl") or "impl"
    design_doc = getattr(args, "design_doc", None)
    acceptance_required = bool(getattr(args, "acceptance_required", False))
    if acceptance_required and entry_point != "impl":
        print(
            "[next-task] begin-run FAIL — acceptance_required is only valid "
            f"for entry_point=impl (got {entry_point!r})",
            file=sys.stderr,
        )
        return 1
    if design_doc is not None:
        # 이전 run end-run(비가역) *전* 선검증 — 경로 오타로 이전 run 만 닫히고
        # 새 run 발급이 실패하는 어긋남(prev review echo 영구 소실) 방지.
        try:
            design_doc = _validate_design_doc(design_doc)
        except ValueError as exc:
            print(f"[next-task] begin-run FAIL — {exc}", file=sys.stderr)
            return 1

    prev_rid = auto_detect_run_id()
    prev_review_path: Optional[Path] = None
    if prev_rid:
        try:
            prev_run_dir = run_dir(sid, prev_rid)
            prev_review_path = prev_run_dir / "review.md"
        except (ValueError, OSError):
            prev_review_path = None
        # end-run 자동 호출 (in-process, _cli_end_run 의 finalize guard 가 알아서 처리)
        try:
            import argparse as _ap
            _cli_end_run(_ap.Namespace())
        except Exception as exc:
            print(f"[next-task] end-run FAIL — {exc}", file=sys.stderr)

    new_rid = generate_run_id()
    try:
        start_run(
            sid, new_rid, entry_point, issue_num=None, design_doc=design_doc,
            acceptance_required=acceptance_required,
        )
    except Exception as exc:
        print(f"[next-task] begin-run FAIL — {exc}", file=sys.stderr)
        return 1
    # 이슈 #587 (codex review) — chain task run 도 run_started checkpoint 남김.
    _ledger_run_started(
        sid, new_rid, entry_point, design_doc=design_doc,
        acceptance_required=acceptance_required,
    )
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        write_pid_current_run(cc_pid, new_rid)
    try:
        new_run_dir_path = run_dir(sid, new_rid, create=True)
    except (ValueError, OSError):
        new_run_dir_path = Path("(unknown)")

    print("=== next-task transition ===")
    print(f"[previous] run_id: {prev_rid or '(없음)'}")
    if prev_review_path and prev_review_path.is_file():
        try:
            content = prev_review_path.read_text(encoding="utf-8", errors="ignore")
            print(f"\n[previous review.md ({prev_review_path.name})]")
            print(content)
        except OSError as exc:
            print(f"[next-task] previous review.md read FAIL — {exc}", file=sys.stderr)
    elif prev_rid:
        print(
            "[previous review.md 부재 — finalize-run --auto-review 가 review 생성 "
            "안 했거나 run-dir 누락]"
        )

    print(f"\n[new] run_id: {new_rid}")
    print(f"[new] run_dir: {new_run_dir_path}")
    print(f"[new] entry_point: {entry_point}")
    if design_doc:
        print(f"[new] design_doc: {design_doc}")
    if acceptance_required:
        print("[new] acceptance_required: true")
    print("=== next-task transition ===")
    return 0


def _cli_insight(args: Any) -> int:
    """issue #396 — 메인 자율 인사이트 1줄 append.

    Usage: dcness-helper insight <agent>[-<mode>] "<자연어 한 줄>"

    예시:
        dcness-helper insight build-worker "🚨 stub 파일로 TDD guard 우회 시도 — 절대 반복 X"
        dcness-helper insight impl-validator "PR 후 prose 결론 enum 누락 — 다음엔 PASS/FAIL 명시"
    """
    from harness.loop_insights import append_insight

    raw = (args.agent_mode or "").strip()
    if not raw:
        print("[session_state] agent_mode 미지정", file=sys.stderr)
        return 1

    # "agent-mode" 또는 "agent" 분리
    if "-" in raw:
        # 정식 agent 이름에 - 있을 수 있음 (impl-validator / module-architect 등).
        # 매트릭스 매칭: 정식 이름 prefix 시도.
        from harness.run_review import DCNESS_AGENT_NAMES
        agent = None
        mode = None
        for known in sorted(DCNESS_AGENT_NAMES, key=len, reverse=True):
            if raw == known:
                agent, mode = known, None
                break
            if raw.startswith(known + "-"):
                agent = known
                mode = raw[len(known) + 1:]
                break
        if not agent:
            # fallback: 첫 - 분리
            parts = raw.split("-", 1)
            agent, mode = parts[0], parts[1] if len(parts) > 1 else None
    else:
        agent, mode = raw, None

    path = append_insight(agent, mode, args.text, cwd=Path.cwd())
    print(f"[insight] appended → {path}", file=sys.stderr)
    return 0


def _cli_prev_tasks_append(args: Any) -> int:
    """#525 — build-worker 가 phase 3 종료 시 자기 task 산출 요약 한 줄 append.

    Usage: dcness-helper prev-tasks-append <slug> "<산출 요약 한 줄>"

    다음 task 진입 시 메인의 `begin-step build-worker` 가 [PREVIOUS_TASKS] 로
    emit → 메인이 build-worker prompt 에 포함. task 간 인터페이스 misalign 완화.
    """
    from harness.prev_tasks import append

    path = append(args.slug, args.summary, cwd=Path.cwd())
    print(f"[prev-tasks] appended → {path}", file=sys.stderr)
    return 0


def _cli_prev_tasks_reset(args: Any) -> int:
    """#525 — impl-loop chain 시작 시 누적 초기화 (skill 진입 1회 권장).

    Usage: dcness-helper prev-tasks-reset
    """
    from harness.prev_tasks import reset

    reset(cwd=Path.cwd())
    print("[prev-tasks] reset", file=sys.stderr)
    return 0


def _cli_begin_step(args: Any) -> int:
    """sid+rid auto-detect → update_current_step."""
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    mode = args.mode if args.mode else None
    try:
        from harness.signal_io import validate_mode_name

        validate_mode_name(mode)
    except ValueError as exc:
        print(f"[begin-step] FAIL — {exc}", file=sys.stderr)
        return 1
    # #700 — agent 이름 canonical 정규화. update_current_step 도 내부 정규화하지만
    # ledger checkpoint까지 같은 표기로 일관시킨다.
    from harness.agent_names import normalize_agent_type
    agent = normalize_agent_type(args.agent) or args.agent
    try:
        gate_message = evaluate_order_gate_for_step(sid, rid, agent, mode)
    except Exception as exc:  # noqa: BLE001
        record_fail_open_event(
            hook="begin-step-order-gate",
            category="gate_exception",
            detail=f"{type(exc).__name__}: {exc}",
        )
        gate_message = None
    if gate_message:
        print(gate_message, file=sys.stderr)
        return 1
    update_current_step(sid, rid, agent, mode)
    # 이슈 #587 — ledger step_started checkpoint. 기록 실패가 begin-step 막지 않게 silent.
    try:
        from harness import ledger
        ledger.append_event(sid, rid, "step_started", agent=agent, mode=mode)
    except Exception:  # nosec B110
        pass

    print("ok")

    prompt_slot_check = _prompt_slot_check_text(sid, rid, agent=agent)
    if prompt_slot_check:
        print(f"\n{prompt_slot_check}")

    # DCN-CHG-20260502-02: 해당 agent/mode 의 loop insights 있으면 stdout 주입.
    # 메인 Claude 가 Bash 결과로 읽고 Agent prompt 에 포함시킨다.
    try:
        from harness.loop_insights import read as _li_read
        _insights = _li_read(args.agent, mode or None)
        if _insights:
            label = f"{args.agent}/{mode}" if mode else args.agent
            print(f"\n[INSIGHTS: {label}]\n{_insights}")
    except Exception:  # nosec B110
        pass  # insights 주입 실패는 silent — 본 step 차단 X

    # #917: recurrent waste lessons. loop-insights 와 동렬의 advisory 주입이며,
    # 실패해도 begin-step 자체를 차단하지 않는다.
    try:
        from harness.loop_lessons import read as _ll_read

        _lessons = _ll_read(agent, mode or None)
        if _lessons:
            label = f"{agent}/{mode}" if mode else agent
            print(f"\n[LESSONS: {label}]\n{_lessons}")
    except Exception:  # nosec B110
        pass

    # #525: build-worker 진입 시 직전 task 산출 요약 stdout 주입. 메인 Claude 가
    # Bash 결과로 읽고 build-worker prompt 에 포함시킨다 (loop_insights 와 동일
    # 경로). 자기 task 는 phase 3 종료 시 append 되므로 여기선 직전까지만 보인다.
    if args.agent == "build-worker":
        try:
            from harness.prev_tasks import read as _pt_read
            _prev = _pt_read()
            if _prev:
                print(f"\n[PREVIOUS_TASKS]\n{_prev}")
        except Exception:  # nosec B110
            pass  # 주입 실패 silent — 본 step 차단 X

    return 0


def _cli_run_dir(args: Any) -> int:
    """현재 active run 의 run_dir 절대 경로 stdout (DCN-CHG-20260430-21).

    skill prompt 가 prose-file path 를 /tmp 대신 run-dir 안에 쓸 때 사용.
    멀티세션 격리 + stale prose 회피.
    """
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    rd = run_dir(sid, rid)
    print(str(rd))
    return 0


def _cli_sanity_receipt_dir(args: Any) -> int:
    """Print the primary-worktree receipt dir for a repo or linked worktree."""
    project_root = Path(args.project_root).expanduser().resolve()
    state_root = _resolve_state_root_for_cwd(str(project_root))
    persistent_project_root = state_root.parent.parent
    print(persistent_project_root / ".dcness-work" / "codebase-sanity")
    return 0


def _cli_run_status(args: Any) -> int:
    """현재 (또는 --run-id) run 의 ledger 기반 진행 상태 요약 (이슈 #587).

    compaction/resume 후 메인 Claude 가 긴 prose 재주입 없이 ledger 만 보고
    task / phase / last event / next action / evidence pointer 를 복원한다.
    """
    sid = auto_detect_session_id()
    rid = getattr(args, "run_id", None) or auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    from harness import ledger

    print(ledger.render_status(sid, rid))
    return 0


def _cli_design_records(args: Any) -> int:
    """Durable `docs/metrics/design-runs.jsonl` 조회 (#833)."""
    from harness import design_run_records

    argv: list[str] = ["--repo", args.repo]
    if getattr(args, "json", False):
        argv.append("--json")
    if getattr(args, "limit", None) is not None:
        argv.extend(["--limit", str(args.limit)])
    return design_run_records.main(argv)


def _cli_chain_view(args: Any) -> int:
    """impl-loop chain 진행 뷰 자동 렌더 → JSON stdout (#755).

    chain 모드에서 task 경계마다 메인이 진행 뷰를 손으로 다시 그리는 대신,
    task list + current index 를 입력받아 진행 뷰 표현 + Task operation
    시퀀스 + 비용 분기를 산출한다. 진행 뷰 규칙 SSOT = impl-loop SKILL 의
    "진행 뷰" 절 (본 helper 는 그 규칙을 코드로 옮길 뿐).

    **도구이지 게이트 아님** — run state 를 읽거나 쓰지 않는 순수 변환이라,
    미사용해도 chain 진행을 막지 않고 메인이 수동 rebuild 로 폴백할 수 있다.
    내부 helper (run-dir / run-status / wave-plan 류) — 새 공개 진입점 아님.
    """
    from harness import chain_view

    return chain_view.main(
        [
            "--tasks",
            args.tasks,
        ]
        + (["--current", str(args.current)] if args.current is not None else [])
        + (["--prev", str(args.prev)] if args.prev is not None else [])
        + (["--initial"] if getattr(args, "initial", False) else [])
    )


def _cli_mockup_node_check(args: Any) -> int:
    """Read-only design reference node-id checker (#989)."""
    from harness.mockup_node_check import check_mockup_nodes

    payload = check_mockup_nodes(args.impl_paths, mockup_dir=args.mockup_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def _cli_ledger_event(args: Any) -> int:
    """ledger 에 *수동* checkpoint event 한 줄 기록 (pr_created/pr_merged/task_completed/blocked 등 — 이슈 #587).

    강제 아님 — 메인/skill 이 PR 생성·머지·차단 같은 checkpoint 를 *선택적* 으로
    남기는 경로.

    🔴 helper-owned lifecycle event (run_started/step_started/step_completed/run_finished)
    는 거부한다 (codex review). 수동 CLI 로 receipt 필드 없는 가짜 step_completed 를
    넣으면 read_step_completed/list_runs/finalize-run 이 진짜 step 으로 취급해
    prose-as-SSOT invariant 가 깨진다 — lifecycle 은 begin-run/begin-step/end-step/
    end-run 코드 경로 전용.
    """
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    from harness import ledger

    if args.event_type not in ledger.MANUAL_EVENT_TYPES:
        print(
            f"[session_state] ledger-event 는 수동 checkpoint 만 허용: "
            f"{sorted(ledger.MANUAL_EVENT_TYPES)}. "
            f"lifecycle event(run_started/step_started/step_completed/run_finished)는 "
            f"begin-run/begin-step/end-step/end-run 코드 경로 전용 — 수동 위조 차단.",
            file=sys.stderr,
        )
        return 1

    fields: Dict[str, Any] = {}
    for key in ("agent", "mode", "pr_number", "url", "issue_num", "reason"):
        val = getattr(args, key, None)
        if val is not None:
            fields[key] = val
    try:
        rec = ledger.append_event(sid, rid, args.event_type, **fields)
    except ValueError as exc:
        print(f"[session_state] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(rec, ensure_ascii=False))
    return 0


def _cli_enable(args: Any) -> int:
    """현재 cwd 의 main repo 를 whitelist 에 추가."""
    root = enable_project()
    print(f"[dcness] enabled: {root}")
    print(f"[dcness] whitelist: {whitelist_path()}")
    return 0


def _cli_disable(args: Any) -> int:
    """현재 cwd 의 main repo 를 whitelist 에서 제거."""
    root = disable_project()
    print(f"[dcness] disabled: {root}")
    return 0


def _cli_is_active(args: Any) -> int:
    """현재 cwd 활성 여부 — 활성=exit 0, 비활성=exit 1 (silent, hook 게이트용)."""
    return 0 if is_project_active() else 1


def _cli_is_self(args: Any) -> int:
    """현재 cwd 가 dcNess plugin 본체 repo 인지 여부 — self=exit 0, 아니면 1."""
    try:
        project_root = _resolve_project_root().resolve()
    except OSError:
        return 1
    return 0 if _is_self_repo(project_root) else 1


def _cli_hook_fail_open(args: Any) -> int:
    """hook wrapper 내부용 fail-open 이벤트 기록."""
    record_fail_open_event(
        hook=args.hook,
        category=args.category,
        detail=args.detail or "",
        severity=args.severity,
    )
    return 0


# ── status 진단표 (#520) ────────────────────────────────────────────
#
# `dcness-helper status` 를 PASS/WARN/FAIL/INFO/NA 진단표로 확장한다. 별도 doctor
# 진입점을 추가하지 않고 (사용자가 외울 표면 최소화), init-dcness 가 셋업과 상태 점검을
# 겸하게 한다. 진단 수집은 deterministic 코드 (추측 누락 차단), 출력 종합/권유는
# init-dcness skill prose 가 담당. routing doctor 의 PASS/FAIL 관용구를 따른다.
#
# 배포 항목을 새로 추가할 때 (init-dcness 의 git hook / CI workflow / Read 권한 등)
# 아래 검사 항목도 함께 갱신해야 한다 (docs/plugin/init-dcness.md 의무 명시).

_READ_PERM = "Read(~/.claude/plugins/cache/dcness/**)"
_GIT_HOOK_SHIMS = ("commit-msg", "post-checkout", "pre-push")
# thin-shim 식별: 세 hook 모두 plugin cache 경로를 동적 resolve 한다.
_SHIM_MARKERS = ("plugins/cache/dcness", "CLAUDE_PLUGIN_ROOT")
_CI_WORKFLOWS = (
    "git-naming-validation.yml",
    "pr-body-validation.yml",
    "doc-path-integrity.yml",
    "doc-sync.yml",
    "github-project-lifecycle.yml",
)
_CODEX_VALIDATOR_SKILLS = (
    "dcness-impl-validator",
    "dcness-architecture-validator",
)



def _cli_status(args: Any) -> int:
    """whitelist + 현재 cwd 활성 상태를 진단표로 출력 (#520)."""
    diag = collect_status_diagnostics()
    print(format_status_report(diag))
    return 0


def _cli_boundary_suggestions(args: Any) -> int:
    """Read-only `.dcness/boundary.json` add override suggestion (#910)."""
    from harness.boundary_suggestions import (
        collect_boundary_suggestions,
        format_boundary_suggestions,
    )

    impl_plan = Path(args.impl_plan) if args.impl_plan else None
    report = collect_boundary_suggestions(
        Path(args.cwd) if args.cwd else None,
        impl_plan=impl_plan,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False))
    else:
        print(format_boundary_suggestions(report))
    return 0


def _cli_impl_preview(args: Any) -> int:
    """Deterministic `/impl` lane/review preview (#1019)."""
    from harness import agent_routing
    from harness import impl_preview

    argv: list[str] = []
    try:
        review_provider = args.review_provider or agent_routing.resolve_provider(
            "impl-validator"
        )
    except ValueError as exc:
        print(
            f"[dcness impl-preview] routing config rejected: {exc}",
            file=sys.stderr,
        )
        return 1
    for opt, value in (
        ("--design-doc", args.design_doc),
        ("--cwd", args.cwd),
        ("--workflow-risk", args.workflow_risk),
        ("--review-provider", review_provider),
    ):
        if value:
            argv.extend([opt, value])
    for opt, enabled in (
        ("--concrete", args.concrete),
        ("--natural-language-only", args.natural_language_only),
        ("--ambiguous", args.ambiguous),
        ("--needs-design", args.needs_design),
        ("--skip-design", args.skip_design),
        ("--json", args.json),
    ):
        if enabled:
            argv.append(opt)
    return impl_preview.main(argv)


def _cli_guard_telemetry(args: Any) -> int:
    """Guard hit / eval saturation summary (#875)."""
    from harness.guard_telemetry import (
        collect_eval_summary,
        collect_guard_summary,
        format_telemetry_report,
    )

    since_days = args.since_days if args.since_days and args.since_days > 0 else None
    guard_summary = collect_guard_summary(
        cwd=Path(args.cwd) if args.cwd else None,
        base_dir=Path(args.base_dir) if args.base_dir else None,
        idle_days=args.idle_days,
        since_days=since_days,
    )
    eval_summary = collect_eval_summary(
        cwd=Path(args.cwd) if args.cwd else None,
        base_dir=Path(args.base_dir) if args.base_dir else None,
        saturation_days=args.saturation_days,
        saturation_min_runs=args.saturation_min_runs,
    )
    if args.json:
        print(json.dumps({"guards": guard_summary, "evals": eval_summary}, ensure_ascii=False))
    else:
        print(format_telemetry_report(guard_summary, eval_summary))
    return 0


def _cli_routing(args: Any) -> int:
    """Local provider 분기 CLI.

    Provider 분기 state 는 plugin-scoped local config 다. Repository 는 의도적으로
    provider 분기 config 를 들고 있지 않다.
    """
    from harness import agent_routing

    action = args.routing_cmd
    if action == "status":
        print(agent_routing.format_status())
        return 0
    if action == "doctor":
        print(agent_routing.format_status())
        problems = agent_routing.doctor()
        if problems:
            return 1
        print("[dcness routing] doctor: PASS")
        return 0
    if action == "enable-codex-validation":
        path = agent_routing.enable_codex_validation()
        print(f"[dcness routing] enabled Codex validation: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "enable-role-split-routing":
        path = agent_routing.enable_role_split_routing()
        print(f"[dcness routing] enabled role-split routing: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "disable-codex-validation":
        path = agent_routing.disable_codex_validation()
        print(f"[dcness routing] disabled Codex validation: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "enable-headless-implementation":
        path = agent_routing.enable_headless_implementation()
        print(f"[dcness routing] enabled headless implementation chain: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "enable-claude-headless-implementation":
        path = agent_routing.enable_claude_headless_implementation()
        print(f"[dcness routing] enabled Claude headless implementation: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "set":
        try:
            path = agent_routing.set_provider(args.agent, args.provider)
        except ValueError as exc:
            print(f"[dcness routing] {exc}", file=sys.stderr)
            return 1
        print(f"[dcness routing] set {args.agent}={args.provider}: {path}")
        return 0
    if action == "set-implementation":
        try:
            path = agent_routing.set_implementation_provider(args.agent, args.provider)
        except ValueError as exc:
            print(f"[dcness routing] {exc}", file=sys.stderr)
            return 1
        print(
            f"[dcness routing] set implementation {args.agent}={args.provider}: {path}"
        )
        return 0
    if action == "resolve":
        try:
            provider = agent_routing.resolve_provider(
                args.agent,
                implementation_provider=getattr(args, "implementation_provider", None),
                main_provider=getattr(args, "main_provider", "claude") or "claude",
            )
        except ValueError as exc:
            print(f"[dcness routing] {exc}", file=sys.stderr)
            return 1
        print(provider)
        return 0
    print(f"[dcness routing] unknown command: {action}", file=sys.stderr)
    return 1


def _build_arg_parser() -> Any:
    import argparse

    from harness import parallel_wave

    parser = argparse.ArgumentParser(
        prog="python3 -m harness.session_state",
        description="dcNess 세션/run 격리 helper CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-session", help="SessionStart 훅 보조")
    p_init.add_argument("sid")
    p_init.add_argument("cc_pid", type=int)
    p_init.set_defaults(func=_cli_init_session)

    p_br = sub.add_parser("begin-run", help="run_id 발급 + start_run")
    p_br.add_argument("entry_point")
    p_br.add_argument("--issue-num", type=int, default=None)
    p_br.add_argument(
        "--design-doc", default=None, dest="design_doc",
        help="이 run 이 참조하는 머지된 설계 문서 경로 — implementation gate 가 "
             "같은-run module-architect PASS 의 등가 사전 조건으로 인정",
    )
    p_br.add_argument(
        "--lane", default=None, choices=_VALID_LANES,
        help="/impl 구현 경로(설계도 유무: lite / standard, #714) — lane=lite 는 "
             "설계도 없는 direct 구현 경로로 implementation gate 설계 산출물 사전 조건 "
             "면제 신호. entry_point=impl 에서만 수용",
    )
    p_br.add_argument(
        "--stage", default=None, choices=_VALID_DESIGN_STAGES,
        help="/design 내부 stage 기록(#958) — design-ux 또는 design-system. "
             "entry_point=design 에서만 수용",
    )
    p_br.add_argument(
        "--acceptance-required", action="store_true",
        help="story/epic 마감 task run marker (#722) — impl-validator PASS 뒤 "
             "product-acceptance 전 Stop hook auto end-run 방지. entry_point=impl 전용",
    )
    p_br.set_defaults(func=_cli_begin_run)

    p_er = sub.add_parser("end-run", help="complete_run + clear by-pid-current-run")
    p_er.set_defaults(func=_cli_end_run)

    p_nt = sub.add_parser(
        "next-task",
        help="이전 run end-run + 새 run begin-run + previous review.md stdout (issue #471)",
    )
    p_nt.add_argument(
        "--entry-point", default="impl",
        help="새 run 의 entry_point (default: impl)",
    )
    p_nt.add_argument(
        "--design-doc", default=None, dest="design_doc",
        help="다음 task 가 참조하는 머지된 설계 문서 경로 (begin-run --design-doc 동일)",
    )
    p_nt.add_argument(
        "--acceptance-required", action="store_true",
        help="다음 task 가 story/epic 마감 acceptance 대상임을 기록 (#722)",
    )
    p_nt.set_defaults(func=_cli_next_task)

    p_ptb = sub.add_parser(
        "post-task-begin",
        help="/impl-loop 종료 후 메인 자율 작업 영역 진입 marker (issue #472)",
    )
    p_ptb.add_argument(
        "--reason", default="",
        help='자율 진입 사유 ("이슈 등록 / cleanup / 분석" 등)',
    )
    p_ptb.set_defaults(func=_cli_post_task_begin)

    # issue #396 — insight CLI (메인 자율 평가 매커니즘)
    p_in = sub.add_parser(
        "insight",
        help="agent+mode 별 인사이트 한 줄 append (FIFO 10 cap, 메인 자율 평가)",
    )
    p_in.add_argument("agent_mode", help='agent 또는 "agent-mode" (예: build-worker)')
    p_in.add_argument("text", help="자연어 한 줄 (예: \"🚨 stub 파일로 TDD guard 우회 시도 — 절대 반복 X\")")
    p_in.set_defaults(func=_cli_insight)

    # #525 — /impl-loop 직전 task 산출 요약 누적 (build-worker append → 다음 진입 emit)
    p_pta = sub.add_parser(
        "prev-tasks-append",
        help="#525 — build-worker task 산출 요약 append (다음 task [PREVIOUS_TASKS] emit)",
    )
    p_pta.add_argument("slug", help="task slug (예: 05-revival-button)")
    p_pta.add_argument("summary", help="산출 요약 한 줄")
    p_pta.set_defaults(func=_cli_prev_tasks_append)

    p_ptr = sub.add_parser(
        "prev-tasks-reset",
        help="#525 — impl-loop chain 시작 시 누적 초기화 (skill 진입 1회)",
    )
    p_ptr.set_defaults(func=_cli_prev_tasks_reset)

    p_bs = sub.add_parser("begin-step", help="current_step + heartbeat 갱신")
    p_bs.add_argument("agent")
    p_bs.add_argument("mode", nargs="?", default="")
    p_bs.set_defaults(func=_cli_begin_step)

    p_es = sub.add_parser(
        "end-step",
        help="prose 저장 (자유서술 방식 — stdout=PROSE_LOGGED, 이슈 #280/#284)",
    )
    p_es.add_argument("agent")
    p_es.add_argument("mode", nargs="?", default="")
    p_es.add_argument(
        "--prose-file", required=False, default=None,
        help="prose 본문 파일 경로 (미제공 시 hook auto-stage 경로 사용)",
    )
    p_es.add_argument(
        "--provider", required=False, default=None,
        help="실제 실행 provider 기록 (예: codex-headless / claude-headless / claude-main)",
    )
    p_es.set_defaults(func=_cli_end_step)

    p_rd = sub.add_parser("run-dir", help="현재 active run 의 run_dir 절대 경로 (DCN-30-21)")
    p_rd.set_defaults(func=_cli_run_dir)

    p_srd = sub.add_parser(
        "sanity-receipt-dir",
        help="linked worktree 정리 후에도 남는 primary-worktree Sanity receipt 경로",
    )
    p_srd.add_argument(
        "--project-root",
        default=".",
        help="활성 project/worktree root (기본 cwd)",
    )
    p_srd.set_defaults(func=_cli_sanity_receipt_dir)

    p_rs = sub.add_parser(
        "run-status",
        help="현재 run 의 phase/task/last event/next action/evidence 요약 (resume 복원 — 이슈 #587)",
    )
    p_rs.add_argument("--run-id", default=None, dest="run_id")
    p_rs.set_defaults(func=_cli_run_status)

    p_dr = sub.add_parser(
        "design-records",
        help="docs/metrics/design-runs.jsonl durable design run records 조회 (#833)",
    )
    p_dr.add_argument("--repo", default=".", help="활성 프로젝트 root (기본 cwd)")
    p_dr.add_argument("--json", action="store_true")
    p_dr.add_argument("--limit", type=int, default=None)
    p_dr.set_defaults(func=_cli_design_records)

    p_cv = sub.add_parser(
        "chain-view",
        help="impl-loop chain 진행 뷰 자동 렌더 JSON (task list + current → view/operations/strategy — #755)",
    )
    p_cv.add_argument(
        "--tasks",
        required=True,
        help="task list JSON 경로 ('-' = stdin). {tasks:[{name,engine,closes?}], current?}",
    )
    p_cv.add_argument(
        "--current",
        type=int,
        default=None,
        help="현재(in_progress) task 0-based index. 미지정 시 입력 JSON 의 current.",
    )
    p_cv.add_argument(
        "--prev",
        type=int,
        default=None,
        help="직전 완료 task 0-based index (transition, 반드시 current-1 인접). 미지정 시 current-1. 임의 점프는 --initial.",
    )
    p_cv.add_argument(
        "--initial",
        action="store_true",
        help="전체 task list 최초 생성 operation 산출 (transition 대신).",
    )
    p_cv.set_defaults(func=_cli_chain_view)

    p_wp = sub.add_parser(
        "wave-plan",
        help="impl task 들의 opt-in 병렬 wave 계획 JSON (chain dry preview — #636)",
    )
    p_wp.add_argument("paths", nargs="+", help="impl 파일 / 디렉토리 / glob")
    p_wp.add_argument(
        "--max-parallel",
        type=int,
        default=parallel_wave.DEFAULT_MAX_PARALLEL_WORKERS,
        dest="max_parallel",
        help=f"동시성 상한 (default {parallel_wave.DEFAULT_MAX_PARALLEL_WORKERS})",
    )
    p_wp.add_argument(
        "--high-risk",
        default="",
        dest="high_risk",
        help="메인 dry-preview 고위험 판정 slug (콤마 구분) → 직렬 강제",
    )
    p_wp.add_argument(
        "--register",
        action="store_true",
        help="#641 peer mode opt-in: wave 후보 impl path 를 claim board 에 등록",
    )
    p_wp.add_argument(
        "--plan-id",
        default=None,
        dest="plan_id",
        help="claim board 등록 묶음 식별자 (선택)",
    )
    p_wp.set_defaults(func=_cli_wave_plan)

    p_ns = sub.add_parser(
        "normalize-scope",
        help="impl 문서 `### 수정 허용` bullet 형식 기계 교정 (#833)",
    )
    p_ns.add_argument("paths", nargs="+", help="impl 파일 / 디렉토리 / glob")
    p_ns.set_defaults(func=_cli_normalize_scope)

    p_mnc = sub.add_parser(
        "mockup-node-check",
        help="impl 디자인 참조의 data-node-id 가 확정 목업에 실존하는지 read-only 검증 (#989)",
    )
    p_mnc.add_argument("impl_paths", nargs="+", help="impl 파일 / 디렉토리 / glob")
    p_mnc.add_argument(
        "--mockup-dir",
        default="docs/design-variants",
        help="확정 목업 디렉토리 (default: docs/design-variants)",
    )
    p_mnc.set_defaults(func=_cli_mockup_node_check)

    p_wc = sub.add_parser(
        "wave-claim",
        help="#641 peer mode: canonical impl path claim (unregistered면 serial flow)",
    )
    p_wc.add_argument("impl_path")
    p_wc.add_argument("--session-id", default=None, dest="session_id")
    p_wc.add_argument("--run-id", default=None, dest="run_id")
    p_wc.add_argument("--worktree", default=None)
    p_wc.add_argument("--branch", default=None)
    p_wc.add_argument(
        "--stale-after",
        type=int,
        default=2 * 60 * 60,
        dest="stale_after",
        help="stale 판정 초 (default 7200). 자동 reclaim 은 하지 않음.",
    )
    p_wc.set_defaults(func=_cli_wave_claim)

    p_wh = sub.add_parser("wave-heartbeat", help="#641 peer claim heartbeat 갱신")
    p_wh.add_argument("key_or_path")
    p_wh.add_argument("--session-id", default=None, dest="session_id")
    p_wh.add_argument("--run-id", default=None, dest="run_id")
    p_wh.set_defaults(func=_cli_wave_heartbeat)

    p_wrel = sub.add_parser("wave-release", help="#641 peer claim 상태 기록")
    p_wrel.add_argument("key_or_path")
    p_wrel.add_argument(
        "--state",
        choices=("completed", "failed", "released"),
        default="released",
    )
    p_wrel.add_argument("--pr", type=int, default=None)
    p_wrel.add_argument("--url", default=None)
    p_wrel.add_argument("--reason", default="")
    p_wrel.set_defaults(func=_cli_wave_release)

    p_wre = sub.add_parser("wave-reclaim", help="#641 stale claim 명시 reclaim")
    p_wre.add_argument("key_or_path")
    p_wre.add_argument("--reason", required=True)
    p_wre.set_defaults(func=_cli_wave_reclaim)

    p_ws = sub.add_parser("wave-status", help="#641 peer claim board 현황")
    p_ws.add_argument("--json", action="store_true")
    p_ws.set_defaults(func=_cli_wave_status)

    p_ml = sub.add_parser("merge-lock", help="#641 peer PR finalize mutex")
    ml_sub = p_ml.add_subparsers(dest="merge_lock_cmd", required=True)
    p_mla = ml_sub.add_parser("acquire", help="peer claim 이 있으면 merge lock 획득")
    p_mla.add_argument("--branch", default=None)
    p_mla.add_argument("--pr", type=int, default=None)
    p_mla.add_argument("--owner", default=None)
    p_mla.set_defaults(func=_cli_merge_lock)
    p_mlr = ml_sub.add_parser("release", help="merge lock 해제")
    p_mlr.add_argument("--token", required=True)
    p_mlr.add_argument("--claim-key", default=None, dest="claim_key")
    p_mlr.add_argument("--state", choices=("released", "failed"), default="released")
    p_mlr.add_argument("--reason", default="")
    p_mlr.set_defaults(func=_cli_merge_lock)
    p_mlc = ml_sub.add_parser("complete", help="PR merged 후 claim completed + lock release")
    p_mlc.add_argument("--token", required=True)
    p_mlc.add_argument("--claim-key", required=True, dest="claim_key")
    p_mlc.add_argument("--pr", type=int, default=None)
    p_mlc.add_argument("--url", default=None)
    p_mlc.set_defaults(func=_cli_merge_lock)
    p_mlb = ml_sub.add_parser(
        "break",
        help="#641 peer merge lock stale 복구 (tokenless, stale 확인 후)",
    )
    p_mlb.add_argument(
        "--stale-after",
        type=int,
        default=2 * 60 * 60,
        dest="stale_after",
        help="stale 판정 초 (default 7200). fresh lock 은 해제하지 않음.",
    )
    p_mlb.add_argument("--owner", default=None)
    p_mlb.add_argument("--reason", default="")
    p_mlb.set_defaults(func=_cli_merge_lock)

    p_le = sub.add_parser(
        "ledger-event",
        help="ledger 에 임의 event 기록 (pr_created/pr_merged/task_completed/blocked 등 — 이슈 #587)",
    )
    p_le.add_argument("event_type")
    p_le.add_argument("--agent", default=None)
    p_le.add_argument("--mode", default=None)
    p_le.add_argument("--pr", type=int, default=None, dest="pr_number")
    p_le.add_argument("--url", default=None)
    p_le.add_argument("--issue", type=int, default=None, dest="issue_num")
    p_le.add_argument("--reason", default=None)
    p_le.set_defaults(func=_cli_ledger_event)

    p_en = sub.add_parser("enable", help="현재 cwd 의 main repo 활성화 (whitelist 추가)")
    p_en.set_defaults(func=_cli_enable)

    p_di = sub.add_parser("disable", help="현재 cwd 비활성화 (whitelist 제거)")
    p_di.set_defaults(func=_cli_disable)

    p_ia = sub.add_parser("is-active", help="활성 여부 (silent, exit 0/1) — hook 게이트용")
    p_ia.set_defaults(func=_cli_is_active)

    p_is = sub.add_parser("is-self", help="dcNess self repo 여부 (silent, exit 0/1)")
    p_is.set_defaults(func=_cli_is_self)

    p_hfo = sub.add_parser(
        "hook-fail-open",
        help="internal: enforcement hook fail-open diagnostic append",
    )
    p_hfo.add_argument("--hook", required=True)
    p_hfo.add_argument("--category", required=True)
    p_hfo.add_argument("--detail", default="")
    p_hfo.add_argument("--severity", default="WARN")
    p_hfo.set_defaults(func=_cli_hook_fail_open)

    p_st = sub.add_parser("status", help="whitelist + 현재 cwd 상태")
    p_st.set_defaults(func=_cli_status)

    p_bsug = sub.add_parser(
        "boundary-suggestions",
        help="#910 read-only: 비표준 소스 디렉터리 boundary override 후보 출력",
    )
    p_bsug.add_argument("--cwd", default="", help="검사할 프로젝트 cwd (기본 현재 cwd)")
    p_bsug.add_argument(
        "--impl-plan",
        default="",
        help="impl 문서의 `### 수정 허용` 경로를 ALLOW_MATRIX 와 대조",
    )
    p_bsug.add_argument("--json", action="store_true")
    p_bsug.set_defaults(func=_cli_boundary_suggestions)

    p_ip = sub.add_parser(
        "impl-preview",
        help="/impl route/engine/begin-run 후보를 결정론적으로 출력",
    )
    p_ip.add_argument("--design-doc", default="")
    p_ip.add_argument("--cwd", default="")
    p_ip.add_argument("--concrete", action="store_true")
    p_ip.add_argument("--natural-language-only", action="store_true")
    p_ip.add_argument("--ambiguous", action="store_true")
    p_ip.add_argument("--needs-design", action="store_true")
    p_ip.add_argument("--workflow-risk", choices=["normal", "high"], default="normal")
    p_ip.add_argument("--skip-design", action="store_true")
    p_ip.add_argument("--review-provider", choices=["claude", "codex"], default="")
    p_ip.add_argument("--json", action="store_true")
    p_ip.set_defaults(func=_cli_impl_preview)

    p_gt = sub.add_parser(
        "guard-telemetry",
        help="#875 guard hit / eval saturation telemetry summary",
    )
    p_gt.add_argument("--idle-days", type=int, default=30)
    p_gt.add_argument("--since-days", type=int, default=90)
    p_gt.add_argument("--saturation-days", type=int, default=30)
    p_gt.add_argument("--saturation-min-runs", type=int, default=3)
    p_gt.add_argument("--cwd", default="")
    p_gt.add_argument("--base-dir", default="")
    p_gt.add_argument("--json", action="store_true")
    p_gt.set_defaults(func=_cli_guard_telemetry)

    p_rt = sub.add_parser(
        "routing",
        help="provider 분기 상태/설정 (local plugin data only)",
    )
    rt_sub = p_rt.add_subparsers(dest="routing_cmd", required=True)

    rt_status = rt_sub.add_parser("status", help="분기 config 출력")
    rt_status.set_defaults(func=_cli_routing)

    rt_doctor = rt_sub.add_parser("doctor", help="분기 config 검증")
    rt_doctor.set_defaults(func=_cli_routing)

    rt_enable = rt_sub.add_parser(
        "enable-codex-validation",
        help="impl-validator / architecture-validator 를 Codex 로 보냄",
    )
    rt_enable.set_defaults(func=_cli_routing)

    rt_role_split = rt_sub.add_parser(
        "enable-role-split-routing",
        help=(
            "추천 role split: build-worker=headless-chain, "
            "impl-validator=codex, "
            "architecture-validator=codex"
        ),
    )
    rt_role_split.set_defaults(func=_cli_routing)

    rt_disable = rt_sub.add_parser(
        "disable-codex-validation",
        help="validation agent 분기를 Claude 로 되돌림",
    )
    rt_disable.set_defaults(func=_cli_routing)

    rt_set = rt_sub.add_parser("set", help="특정 validation agent provider 설정")
    rt_set.add_argument("agent")
    rt_set.add_argument("provider", choices=("claude", "codex"))
    rt_set.set_defaults(func=_cli_routing)

    rt_enable_headless = rt_sub.add_parser(
        "enable-headless-implementation",
        help="implementation agent 를 Codex headless → Claude headless → Claude main 체인으로 보냄",
    )
    rt_enable_headless.set_defaults(func=_cli_routing)

    rt_enable_claude_headless = rt_sub.add_parser(
        "enable-claude-headless-implementation",
        help="implementation agent 를 Claude headless → Claude main 체인으로 보냄",
    )
    rt_enable_claude_headless.set_defaults(func=_cli_routing)

    rt_set_impl = rt_sub.add_parser(
        "set-implementation",
        help="특정 implementation agent provider 설정",
    )
    rt_set_impl.add_argument("agent")
    rt_set_impl.add_argument(
        "provider",
        choices=("claude", "claude-headless", "headless-chain"),
    )
    rt_set_impl.set_defaults(func=_cli_routing)

    rt_resolve = rt_sub.add_parser("resolve", help="agent provider resolve")
    rt_resolve.add_argument("agent")
    rt_resolve.add_argument(
        "--implementation-provider",
        choices=("claude", "claude-headless", "headless-chain"),
        default=None,
        help="impl-validator 기본값을 계산할 때 구현 provider camp 를 반영",
    )
    rt_resolve.add_argument(
        "--main-provider",
        choices=("claude", "codex"),
        default="claude",
        help="implementation provider 가 없을 때 main 구현 provider camp",
    )
    rt_resolve.set_defaults(func=_cli_routing)

    p_fr = sub.add_parser(
        "finalize-run",
        help="현재 run 의 step status JSON 출력 (clean 판정용)",
    )
    p_fr.add_argument(
        "--expected-steps",
        type=int,
        default=None,
        help="정상 시퀀스 step 수 (예: /impl 5). 미만이면 stderr WARN (DCN-30-25)",
    )
    p_fr.add_argument(
        "--auto-review",
        action="store_true",
        help="finalize 직후 in-process 로 /run-review 호출 — STATUS JSON 뒤에 chained (DCN-30-29)",
    )
    # issue #392 — --accumulate / --no-accumulate flag 폐기 (auto accumulate 폐기와 정합).
    p_fr.set_defaults(func=_cli_finalize_run)

    p_ar = sub.add_parser(
        "auto-resolve",
        help="yolo 모드 권장 액션 JSON 반환 (agent:mode_or_enum 매핑)",
    )
    p_ar.add_argument(
        "agent_mode",
        help='"ux-architect:UX_FLOW_ESCALATE", "impl-validator:FAIL", "*:AMBIGUOUS" 등',
    )
    p_ar.set_defaults(func=_cli_auto_resolve)

    return parser


def _main(argv: Optional[list] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(_main())
