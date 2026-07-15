"""ledger.py — run 단위 append-only event 장부 + helper-generated receipt (이슈 #587).

발상:
    prose 파일 (`<run_dir>/<agent>[-MODE].md`) 은 계속 SSOT 다. ledger 는 그 위에
    얹는 *색인 / 상태 / audit 장부* — 긴 prose 를 매번 대화 context 에 재주입하지
    않고도 resume / handoff / audit 에 필요한 상태를 durable 하게 남긴다.

    🔴 핵심 제약: agent 에게 JSON 출력 형식을 강제하지 않는다. helper (본 모듈) 가
    저장된 prose + known state 에서 receipt 를 *생성* 한다. prose 가 변형 SSOT 이고
    ledger 는 그것을 가리키는 장부일 뿐이다.

단일 SSOT (이슈 #587 옵션 B):
    모든 lifecycle 과 `step_completed` receipt 를 `ledger.jsonl` 에 기록한다.
    소비처 (finalize-run / strict-conveyor gate / Stop hook / run_review) 는
    `read_step_completed` 가 돌려주는 현재 receipt 만 읽는다.

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

receipt 필드명 ↔ 이슈 명세 매핑:
    prose_file ↔ prose_path / prose_excerpt ↔ short_summary / ts ↔ created_at.
    현재 ledger schema 의 canonical 필드명은 prose_file / prose_excerpt / ts 다.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "EVENT_TYPES",
    "LIFECYCLE_EVENT_TYPES",
    "MANUAL_EVENT_TYPES",
    "ledger_path",
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
    "render_status",
]

# Current event catalog consumed by the canonical session_state transition.
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

# helper-owned lifecycle events are never accepted by the manual checkpoint CLI.
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
    {"impl-validator", "architecture-validator", "product-acceptance"}
)

# phase 추론 — entry_point + 마지막 step agent 로 "지금 어느 단계인가" best-effort.
_PHASE_BY_AGENT = {
    "build-worker": "implement",
    "impl-validator": "validate",
    "system-architect": "design",
    "module-architect": "design",
    "architecture-validator": "design-review",
    "ux-architect": "ux",
    "designer": "ux",
    "product-acceptance": "acceptance",
    "tech-reviewer": "tech-review",
}


def ledger_path(sid: str, rid: str, *, base_dir: Optional[Path] = None) -> Path:
    """`<run_dir>/ledger.jsonl` 절대 경로."""
    from harness.session_state import run_dir

    return run_dir(sid, rid, base_dir=base_dir) / "ledger.jsonl"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read the only supported ledger schema; malformed current data is fatal."""
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise _format_error(path, f"malformed JSON at line {line_no}") from exc
            if not isinstance(rec, dict) or rec.get("event") not in EVENT_TYPES:
                raise _format_error(path, f"invalid event at line {line_no}")
            out.append(rec)
    except OSError as exc:
        raise _format_error(path, f"unreadable ledger: {exc}") from exc
    return out


def _format_error(path: Path, detail: str) -> ValueError:
    from harness.session_state import StateFormatError

    return StateFormatError(
        f"current run ledger is invalid at {path}: {detail}; "
        "remove that run state and rerun the workflow to recreate it"
    )


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
    """Reject an invalid current receipt instead of treating it as absent."""
    for e in events:
        if e.get("event") == "step_completed":
            reason = _validate_primary_step_receipt(e)
            if reason:
                raise _format_error(primary, f"invalid step_completed receipt: {reason}")
    return events


def _read_events_path(path: Path) -> List[Dict[str, Any]]:
    """현재 ledger.jsonl 을 읽고 receipt 가 손상된 step 을 제외한다."""
    events = _read_jsonl(path)
    return _drop_invalid_primary_steps(events, path) if events else []


def read_events(
    sid: str, rid: str, *, base_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """현재 ledger.jsonl 전체 읽기."""
    return _read_events_path(ledger_path(sid, rid, base_dir=base_dir))


def read_events_at(run_dir_path: Any) -> List[Dict[str, Any]]:
    """run_dir Path 로부터 직접 읽기 (run_review 사후 분석 — sid/rid 없이 디렉토리 스캔)."""
    p = Path(run_dir_path)
    return _read_events_path(p / "ledger.jsonl")


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
    """step_completed event 만 시간순 반환."""
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
    """(agent, mode) step_completed 수."""
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
_FAIL_RE = re.compile(r"\bFAIL\b")
_FAIL_NEGATION_RE = re.compile(
    r"(없|미발견|아님|아니|불필요|\bno\b|\bnot\b|\bzero\b|\b0\s*\b)",
    re.IGNORECASE,
)


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

    🔴 자유서술 방식 보존: 이건 *hint* 일 뿐 메인 Claude 의 분기 판단을
    대체하지 않는다. 확실하지 않으면 빈 문자열 → status 가 생략.
    """
    if agent not in _VALIDATOR_AGENTS:
        return ""
    if agent == "product-acceptance" and enum == "FAIL":
        return "acceptance gap 후속 분기(`/impl`/`/design`/`/spec`/`/ux`/`/to-issue`) 예상"
    if not must_fix:
        return ""
    if agent == "impl-validator":
        return "finding-class에 따라 build-worker rework 또는 메인 root-cause 수정 예상"
    if agent == "architecture-validator":
        return "finding 분류로 설계 agent 분기 예상 (build-worker 단계 아님)"
    return ""


def _product_acceptance_fail_from_prose(prose: str) -> bool:
    """product-acceptance 자유서술 방식 결론에서 FAIL hint 만 보수적으로 추출."""
    for line in reversed(prose.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        return bool(_FAIL_RE.search(stripped) and not _FAIL_NEGATION_RE.search(stripped))
    return False


def build_receipt(
    agent: str,
    mode: Optional[str],
    enum: str,
    prose: str,
    prose_path: Any,
    *,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """저장된 prose + known state 에서 receipt dict 생성 (helper-generated).

    현재 receipt 필드(prose_excerpt / prose_file / must_fix / sha256 /
    evidence_paths / next_action)를 helper가 생성한다. agent 출력 형식 강제 X.
    """
    from harness.session_state import _extract_prose_summary, _has_positive_must_fix

    must_fix = _has_positive_must_fix(prose)
    hint_enum = enum
    if agent == "product-acceptance" and enum == "PROSE_LOGGED":
        hint_enum = "FAIL" if _product_acceptance_fail_from_prose(prose) else enum
    receipt = {
        "agent": agent,
        "mode": mode,
        "enum": enum,
        "prose_excerpt": _extract_prose_summary(prose, max_lines=12),
        "must_fix": must_fix,
        "prose_file": str(prose_path),
        "sha256": sha256_text(prose),
        "evidence_paths": extract_evidence_paths(prose),
        "next_action": infer_next_action(agent, mode, must_fix=must_fix, enum=hint_enum),
    }
    if provider:
        receipt["provider"] = provider
    return receipt


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
        except Exception:  # nosec B110
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
