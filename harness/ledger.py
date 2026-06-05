"""ledger.py — run 단위 append-only event 장부 + helper-generated receipt (이슈 #587).

발상:
    prose 파일 (`<run_dir>/<agent>[-MODE].md`) 은 계속 SSOT 다. ledger 는 그 위에
    얹는 *색인 / 상태 / audit 장부* — 긴 prose 를 매번 대화 context 에 재주입하지
    않고도 resume / handoff / audit 에 필요한 상태를 durable 하게 남긴다.

    🔴 핵심 제약: agent 에게 JSON 출력 형식을 강제하지 않는다. helper (본 모듈) 가
    저장된 prose + known state 에서 receipt 를 *생성* 한다. prose 가 변형 SSOT 이고
    ledger 는 그것을 가리키는 장부일 뿐이다.

단일 SSOT 재설계 (이슈 #587 옵션 B):
    옛 `.steps.jsonl` (step_completed 수준만 기록) 을 `ledger.jsonl` 로 흡수한다.
    `step_completed` event 가 옛 step row 의 *superset* — 옛 필드명 (prose_excerpt /
    prose_file / must_fix / enum) 을 그대로 유지하고 receipt 필드 (sha256 /
    evidence_paths / next_action) 를 더한다. 따라서 소비처 (finalize-run /
    strict-conveyor gate / Stop hook / run_review) 는 `read_step_completed` 가
    돌려주는 레코드를 옛 row 처럼 읽으면 된다.

    마이그레이션 셔틀: `ledger.jsonl` 이 없고 옛 `.steps.jsonl` 만 있으면 (plugin
    업데이트가 진행 중 run 에 걸친 경우) 옛 row 를 `step_completed` event 로
    normalize 해 폴백한다. 새 run 부터는 ledger.jsonl 단일 사용.

저장 위치: `<run_dir>/ledger.jsonl` (= `.sessions/<sid>/runs/<rid>/ledger.jsonl`).
    워크트리에서 호출해도 `session_state.run_dir` 의 base_dir 해석이 main repo
    harness-state 를 단일 source 로 잡으므로 (git --git-common-dir) 정합.

ledger event 카탈로그 (이슈 명세):
    run_started / step_started / step_completed (=receipt) /
    validator_passed / validator_failed / pr_created / pr_merged /
    task_completed / blocked / run_finished

    이 중 코드 경로가 *자동* 기록하는 것은 run_started (begin-run) /
    step_started (begin-step) / step_completed (end-step) / run_finished
    (end-run) 4종. 나머지는 메인/skill 이 `ledger-event` CLI 로 *선택* 기록하거나
    (pr_*, task_completed, blocked), step_completed event 에서 *파생 해석* 한다
    (validator_passed/failed = validator agent + must_fix). dcNess doctrine 의
    "강제는 catastrophic 만" 정신 — 형식/기록을 agent 에 강제하지 않는다.

receipt 필드명 ↔ 이슈 명세 매핑 (호환 우선):
    prose_file ↔ prose_path / prose_excerpt ↔ short_summary / ts ↔ created_at.
    옛 `.steps.jsonl` 소비처 회귀를 0 으로 만들기 위해 내부 필드명은 옛 이름을
    유지한다 (의미는 동일).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "EVENT_TYPES",
    "LIFECYCLE_EVENT_TYPES",
    "MANUAL_EVENT_TYPES",
    "ledger_path",
    "legacy_steps_path",
    "append_event",
    "read_events",
    "read_events_at",
    "read_step_completed",
    "read_step_completed_at",
    "count_step_completed",
    "sha256_text",
    "extract_evidence_paths",
    "infer_next_action",
    "infer_phase",
    "build_receipt",
    "append_step_completed",
    "render_status",
]

# 이슈 #587 event 카탈로그 — append_event 가 허용하는 event type 전체.
EVENT_TYPES = frozenset(
    {
        "run_started",
        "step_started",
        "step_completed",
        "validator_passed",
        "validator_failed",
        "pr_created",
        "pr_merged",
        "task_completed",
        "blocked",
        "run_finished",
    }
)

# helper-owned lifecycle event — begin-run/begin-step/end-step/end-run 코드 경로만
# 기록한다. step_completed 는 receipt 필드(sha256/prose_file/...)를 동반해야 하므로
# 반드시 append_step_completed 를 거친다.
LIFECYCLE_EVENT_TYPES = frozenset(
    {"run_started", "step_started", "step_completed", "run_finished"}
)

# `ledger-event` CLI 가 허용하는 *수동* checkpoint event (이슈 #587 codex review).
# lifecycle event 를 수동 CLI 로 위조하면 receipt 필드 없는 가짜 step_completed 가
# read_step_completed/list_runs/finalize-run 에서 진짜 step 으로 취급돼 prose-as-SSOT
# invariant 가 깨진다 — 따라서 수동 CLI 는 manual event 만.
MANUAL_EVENT_TYPES = EVENT_TYPES - LIFECYCLE_EVENT_TYPES

# step_completed 에서 validator pass/fail 을 *파생* 할 때 쓰는 validator agent 집합.
_VALIDATOR_AGENTS = frozenset(
    {"code-validator", "pr-reviewer", "architecture-validator"}
)

# phase 추론 — entry_point + 마지막 step agent 로 "지금 어느 단계인가" best-effort.
_PHASE_BY_AGENT = {
    "test-engineer": "test",
    "build-test": "test",
    "engineer": "implement",
    "build-impl": "implement",
    "build-worker": "implement",
    "code-validator": "validate",
    "build-validate": "validate",
    "pr-reviewer": "review",
    "system-architect": "design",
    "module-architect": "design",
    "architecture-validator": "design-review",
    "ux-architect": "ux",
    "designer": "ux",
    "qa": "triage",
    "product-planner": "plan",
    "tech-reviewer": "tech-review",
}


def _now_iso() -> str:
    """session_state._now_iso 와 동일 형식 — 지연 import 비용 회피용 동일 구현."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ledger_path(sid: str, rid: str, *, base_dir: Optional[Path] = None) -> Path:
    """`<run_dir>/ledger.jsonl` 절대 경로."""
    from harness.session_state import run_dir

    return run_dir(sid, rid, base_dir=base_dir) / "ledger.jsonl"


def legacy_steps_path(
    sid: str, rid: str, *, base_dir: Optional[Path] = None
) -> Path:
    """옛 `<run_dir>/.steps.jsonl` 절대 경로 (마이그레이션 폴백 전용)."""
    from harness.session_state import run_dir

    return run_dir(sid, rid, base_dir=base_dir) / ".steps.jsonl"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """jsonl 전체 읽기 — 깨진 줄 skip, 파일 없으면 빈 리스트.

    손상 가시화 (이슈 #587 codex review): truncated lifecycle event (crash /
    partial write) 가 "없던 event" 와 구분 안 되면 resume/finalize 가 stale
    state 로 silent 폴백한다. malformed 줄이 있으면 stderr 1회 WARN — 정상 시엔
    0건이라 노이즈 없음.
    """
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    malformed = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(rec, dict):
                out.append(rec)
    except OSError:
        return []
    if malformed:
        print(
            f"[ledger] {malformed} malformed line(s) skipped in {path} — "
            f"손상 가능 (truncated write?). run-status / run-review 로 상태 확인 권장.",
            file=sys.stderr,
        )
    return out


def _normalize_legacy_rows(legacy: Path) -> List[Dict[str, Any]]:
    """옛 .steps.jsonl row 를 step_completed event 로 normalize."""
    out: List[Dict[str, Any]] = []
    for row in _read_jsonl(legacy):
        if "event" not in row:
            row = {"event": "step_completed", **row}
        out.append(row)
    return out


def _append_event_raw(
    sid: str,
    rid: str,
    event: str,
    *,
    base_dir: Optional[Path] = None,
    ts: Optional[str] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """저수준 append — event ∈ EVENT_TYPES 만 검증. 작성된 record 반환.

    🔴 helper 내부 전용 (`_` prefix). 직접 호출 금지 — step_completed 는 receipt
    동반이 강제이므로 반드시 `append_step_completed` 를, 그 외 event 는
    `append_event` (public, step_completed 거부) 를 쓴다.

    Raises:
        ValueError: event 가 EVENT_TYPES 에 없음.
    """
    if event not in EVENT_TYPES:
        raise ValueError(
            f"unknown ledger event: {event!r} (allowed: {sorted(EVENT_TYPES)})"
        )
    record: Dict[str, Any] = {"event": event, "ts": ts or _now_iso()}
    for k, v in fields.items():
        if k in ("event", "ts"):
            continue  # event/ts 는 강제 — fields 가 덮어쓰지 못함
        record[k] = v

    target = ledger_path(sid, rid, base_dir=base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def append_event(
    sid: str,
    rid: str,
    event: str,
    *,
    base_dir: Optional[Path] = None,
    ts: Optional[str] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """ledger.jsonl 에 event 한 줄 append (append-only). 작성된 record 반환.

    🔴 step_completed 직접 생성 거부 (codex review): step_completed 는 prose 무결성
    receipt (sha256 / prose_file / evidence_paths) 를 동반해야 하고, 소비처
    (read_step_completed / list_runs / finalize-run) 가 이를 진짜 step 으로 신뢰한다.
    receipt 없는 위조 step_completed 가 prose-as-SSOT invariant 를 깨지 못하도록
    step_completed 는 오직 `append_step_completed` 만 생성한다. run_started /
    step_started / run_finished 같은 lifecycle marker 와 manual event 는 그대로 허용.

    Raises:
        ValueError: event 가 step_completed 이거나 EVENT_TYPES 에 없음.
    """
    if event == "step_completed":
        raise ValueError(
            "step_completed 는 append_step_completed (receipt 동반) 전용 — "
            "append_event 직접 생성 금지 (prose-as-SSOT invariant)."
        )
    return _append_event_raw(sid, rid, event, base_dir=base_dir, ts=ts, **fields)


def _validate_primary_step_receipt(event: Dict[str, Any]) -> str:
    """primary step_completed receipt 검증. 정상 = 빈 문자열, 비정상 = reason."""
    prose_file = event.get("prose_file")
    expected_sha = event.get("sha256")
    if not isinstance(prose_file, str) or not prose_file:
        return "missing_field"
    if not isinstance(expected_sha, str) or not expected_sha:
        return "missing_field"

    prose_path = Path(prose_file)
    if not prose_path.exists():
        return "missing_file"
    try:
        actual = prose_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "unreadable_file"
    if sha256_text(actual) != expected_sha:
        return "sha256_mismatch"
    return ""


def _drop_invalid_primary_steps(
    events: List[Dict[str, Any]], primary: Path
) -> List[Dict[str, Any]]:
    """primary ledger.jsonl 의 invalid receipt step_completed 를 drop + warn.

    정당한 step_completed 는 append_step_completed 가 생성한 prose_file + sha256 를
    동반하고, read 시점에 prose 파일이 실제 존재하며 digest 가 일치해야 한다.
    위조(append API 우회) 또는 손상된 durable event 를 소비처가 진짜 step 으로
    신뢰하지 않도록 제거한다. step_completed 외 event 는 보존.
    """
    kept: List[Dict[str, Any]] = []
    dropped_by_reason: Dict[str, int] = {}
    for e in events:
        if e.get("event") == "step_completed":
            reason = _validate_primary_step_receipt(e)
            if reason:
                dropped_by_reason[reason] = dropped_by_reason.get(reason, 0) + 1
                continue
        kept.append(e)
    if dropped_by_reason:
        total = sum(dropped_by_reason.values())
        detail = ", ".join(
            f"{reason}={count}" for reason, count in sorted(dropped_by_reason.items())
        )
        print(
            f"[ledger] {total} step_completed with invalid receipt dropped from {primary} "
            f"({detail}) — prose_file 실존 + sha256 digest match strict 검증 실패.",
            file=sys.stderr,
        )
    return kept


def _read_events_paths(
    primary: Path, legacy: Path
) -> List[Dict[str, Any]]:
    """ledger.jsonl + 옛 .steps.jsonl 통합 읽기 (마이그레이션 셔틀).

    저수준 — sid/rid 버전 (`read_events`) 과 run_dir Path 버전 (`read_events_at`)
    공통 본체. 마이그레이션 셔틀이 한 곳에만 살게 한다.

    🔴 mixed-version merge (이슈 #587 codex review high): plugin 업데이트가 진행 중
    run 에 걸치면 한 run 에 옛 .steps.jsonl row (업데이트 전) 와 새 ledger.jsonl
    event (업데이트 후) 가 *둘 다* 존재할 수 있다. ledger 만 읽으면 옛 step 이
    통째로 사라져 occurrence count 가 리셋되고 prose 파일이 덮어써지며
    finalize/strict-gate/run_review 가 step 수를 적게 본다. 옛 코드는 .steps.jsonl
    에만, 새 코드는 ledger.jsonl 에만 쓰므로 step 중복은 없다 — legacy (시간상
    먼저) 를 앞에 두고 concat 해 시간순을 보존한다.
    """
    primary_events = _read_jsonl(primary) if primary.exists() else []
    legacy_events = _normalize_legacy_rows(legacy) if legacy.exists() else []
    # primary ledger.jsonl 의 step_completed 는 strict receipt 검증 필수 (codex review).
    # append API 가 위조 append 를 막아도, durable ledger 에 stale/downgrade/손상으로
    # receipt 없는 step_completed 가 남으면 reader 가 진짜 step 으로 신뢰해버린다 —
    # invariant 가 writer path 가 아니라 *소비되는 데이터* 에 걸리도록 read 측에서도
    # 강제한다. legacy .steps.jsonl 은 별도 호환 경로(무검증) — prose_file 없는 옛 row 보존.
    if primary_events:
        primary_events = _drop_invalid_primary_steps(primary_events, primary)
    if not (primary_events and legacy_events):
        return primary_events or legacy_events
    # mixed — ts 기준 안정 정렬 merge (codex review). concat 만 하면 version skew /
    # downgrade / retry / stale helper 시 새 legacy row 가 옛 ledger row 앞에 강제될 수
    # 있다. ISO8601(UTC) ts 는 lexicographic = chronological. ts 동률이면 stable sort 로
    # 입력 순서 (legacy 먼저) 보존. step_completed 는 (agent,mode,ts,prose_file) identity
    # 로 dedup 해 stale/retry 중복을 흡수한다.
    combined = legacy_events + primary_events
    combined.sort(key=lambda e: e.get("ts") or "")
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for e in combined:
        if e.get("event") == "step_completed":
            ident = (
                e.get("agent"),
                e.get("mode"),
                e.get("ts"),
                e.get("prose_file"),
            )
            if ident in seen:
                continue
            seen.add(ident)
        out.append(e)
    return out


def read_events(
    sid: str, rid: str, *, base_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """ledger.jsonl 전체 읽기. 없으면 옛 .steps.jsonl 폴백 (step_completed 로 normalize)."""
    return _read_events_paths(
        ledger_path(sid, rid, base_dir=base_dir),
        legacy_steps_path(sid, rid, base_dir=base_dir),
    )


def read_events_at(run_dir_path: Any) -> List[Dict[str, Any]]:
    """run_dir Path 로부터 직접 읽기 (run_review 사후 분석 — sid/rid 없이 디렉토리 스캔)."""
    p = Path(run_dir_path)
    return _read_events_paths(p / "ledger.jsonl", p / ".steps.jsonl")


def read_step_completed_at(run_dir_path: Any) -> List[Dict[str, Any]]:
    """run_dir Path 로부터 step_completed event 만 시간순 반환."""
    return [
        e
        for e in read_events_at(run_dir_path)
        if e.get("event") == "step_completed"
    ]


def read_step_completed(
    sid: str, rid: str, *, base_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """step_completed event 만 시간순 반환 (옛 `_read_steps_jsonl` 대체).

    소비처 (finalize-run / strict-conveyor / Stop hook / run_review) 는 이 결과를
    옛 .steps.jsonl row 처럼 읽으면 된다 (필드명 호환).
    """
    return [
        e
        for e in read_events(sid, rid, base_dir=base_dir)
        if e.get("event") == "step_completed"
    ]


def count_step_completed(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """(agent, mode) step_completed 수 (옛 `_count_step_occurrences` 대체 — occurrence 계산)."""
    return sum(
        1
        for s in read_step_completed(sid, rid, base_dir=base_dir)
        if s.get("agent") == agent and s.get("mode") == mode
    )


def sha256_text(text: str) -> str:
    """prose 무결성 기록용 sha256 hex (full 64 char)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# 백틱 안 경로 후보: 공백 없는 path 형 토큰.
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_PATH_TOKEN_RE = re.compile(r"^[\w.][\w./\-]*$")
# PR / issue URL.
_PR_URL_RE = re.compile(r"https?://[^\s`)\]]+/pull/\d+")


def extract_evidence_paths(prose: str) -> List[str]:
    """prose 에서 evidence pointer (파일 경로 / PR URL) best-effort 추출.

    보수적 — 백틱으로 감싼 경로형 토큰 (슬래시 포함) + PR URL 만. 노이즈 회피.
    형식 강제가 아니므로 못 찾으면 빈 리스트.
    """
    out: List[str] = []
    seen: set = set()

    for cand in _BACKTICK_RE.findall(prose):
        cand = cand.strip()
        # 슬래시 포함 + 경로형 토큰만 (`x == y` 같은 코드 조각 배제).
        if "/" in cand and _PATH_TOKEN_RE.match(cand) and cand not in seen:
            seen.add(cand)
            out.append(cand)

    for url in _PR_URL_RE.findall(prose):
        if url not in seen:
            seen.add(url)
            out.append(url)

    return out


def infer_next_action(
    agent: str,
    mode: Optional[str],
    *,
    must_fix: bool,
    enum: str,
) -> str:
    """다음 액션 best-effort hint (없으면 빈 문자열).

    🔴 prose-only 철학 보존: 이건 *hint* 일 뿐 메인 Claude 의 routing 판단을
    대체하지 않는다. 확실하지 않으면 빈 문자열 → status 가 생략.
    """
    if agent not in _VALIDATOR_AGENTS or not must_fix:
        return ""
    if agent == "code-validator":
        return "engineer 재호출 (FAIL 본문 반영) 예상"
    if agent == "pr-reviewer":
        return "지적 근본원인 수정 후 재리뷰 예상 (engineer 경유)"
    if agent == "architecture-validator":
        return "finding 분류로 architect 라우팅 예상 (engineer 단계 아님)"
    return ""


def build_receipt(
    agent: str,
    mode: Optional[str],
    enum: str,
    prose: str,
    prose_path: Any,
) -> Dict[str, Any]:
    """저장된 prose + known state 에서 receipt dict 생성 (helper-generated).

    필드명은 옛 .steps.jsonl row 호환 (prose_excerpt / prose_file / must_fix) +
    receipt 신규 (sha256 / evidence_paths / next_action). agent 출력 형식 강제 X.
    """
    from harness.session_state import _extract_prose_summary, _has_positive_must_fix

    must_fix = _has_positive_must_fix(prose)
    return {
        "agent": agent,
        "mode": mode,
        "enum": enum,
        "prose_excerpt": _extract_prose_summary(prose, max_lines=12),
        "must_fix": must_fix,
        "prose_file": str(prose_path),
        "sha256": sha256_text(prose),
        "evidence_paths": extract_evidence_paths(prose),
        "next_action": infer_next_action(agent, mode, must_fix=must_fix, enum=enum),
    }


def append_step_completed(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    enum: str,
    prose: str,
    prose_path: Any,
    *,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """end-step 시점: prose 에서 receipt 생성 → step_completed event append.

    step_completed 의 *유일한* 정당 생성 경로 — receipt (sha256 / prose_file /
    evidence_paths) 를 동반해 _append_event_raw 로 기록한다. public append_event 는
    step_completed 를 거부하므로 위조 경로가 없다 (codex review).
    """
    receipt = build_receipt(agent, mode, enum, prose, prose_path)
    return _append_event_raw(
        sid, rid, "step_completed", base_dir=base_dir, **receipt
    )


def infer_phase(
    entry_point: Optional[str], agent: Optional[str], mode: Optional[str]
) -> str:
    """entry_point + 마지막 step agent 로 현재 phase best-effort 추론."""
    if agent and agent in _PHASE_BY_AGENT:
        return _PHASE_BY_AGENT[agent]
    return entry_point or "unknown"


def _summary_one_line(text: str, *, cap: int = 120) -> str:
    """multi-line 요약을 status 표시용 1줄로 압축."""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line:
            return line[:cap]
    return ""


def render_status(
    sid: str, rid: str, *, base_dir: Optional[Path] = None
) -> str:
    """현재 run 의 task / phase / last event / next action / evidence pointer 출력.

    compaction/resume 후 메인 Claude 가 ledger 만 보고 진행 상태를 복원하는 1줄
    요약 명령 (`run-status`) 의 본문.
    """
    events = read_events(sid, rid, base_dir=base_dir)
    steps = [e for e in events if e.get("event") == "step_completed"]

    # entry_point / issue_num — run_started event 우선, 없으면 live.json 슬롯 폴백.
    started = next((e for e in events if e.get("event") == "run_started"), None)
    entry = started.get("entry_point") if started else None
    issue = started.get("issue_num") if started else None
    if entry is None or issue is None:
        try:
            from harness.session_state import read_live

            live = read_live(sid, base_dir=base_dir) or {}
            slot = live.get("active_runs", {}).get(rid, {}) if live else {}
            if isinstance(slot, dict):
                entry = entry or slot.get("entry_point")
                issue = issue if issue is not None else slot.get("issue_num")
        except Exception:
            pass

    last_step = steps[-1] if steps else None
    last_event = events[-1] if events else None
    phase = infer_phase(
        entry,
        last_step.get("agent") if last_step else None,
        last_step.get("mode") if last_step else None,
    )

    lines: List[str] = [f"run_id: {rid}"]
    if entry:
        lines.append(f"entry_point: {entry}")
    if issue:
        lines.append(f"task: #{issue}")
    lines.append(f"phase: {phase}")
    lines.append(f"step_completed count: {len(steps)}")

    if last_event:
        lines.append(
            f"last_event: {last_event.get('event')} @ {last_event.get('ts', '?')}"
        )
    if last_step:
        agent = last_step.get("agent", "?")
        mode = last_step.get("mode")
        label = f"{agent}:{mode}" if mode else agent
        summary = _summary_one_line(last_step.get("prose_excerpt", ""))
        mf = " ⚠️MUST_FIX" if last_step.get("must_fix") else ""
        lines.append(f"last_step: {label}{mf} — {summary}")
        na = last_step.get("next_action")
        if na:
            lines.append(f"next_action(hint): {na}")
        ev = last_step.get("evidence_paths") or []
        if ev:
            lines.append("evidence: " + ", ".join(str(p) for p in ev))

    if steps:
        lines.append("prose files (resume pointers):")
        for s in steps:
            pf = s.get("prose_file")
            if pf:
                lines.append(f"  - {pf}")

    return "\n".join(lines)
