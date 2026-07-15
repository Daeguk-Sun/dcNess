"""run_review.py — dcness conveyor run 사후 분석 (RWHarness review skill 의 dcness 변환).

데이터 소스:
  1. `.sessions/{sid}/runs/{rid}/ledger.jsonl` — event 장부의 step_completed
     (agent/mode/enum/must_fix/prose_excerpt/ts)
  2. `.sessions/{sid}/runs/{rid}/<agent>[-<MODE>].md` — 각 step 의 전체 prose
  3. CC session JSONL — run timeframe 내 cost/token (run-level coarse)

산출물:
  - markdown 리포트 (요약 / 호출 흐름 / 단계별 표 / 잘한 점 / 잘못한 점 / 수정 제안)

사용:
    python3 -m harness.run_review --run-id RID
    python3 -m harness.run_review --latest
    python3 -m harness.run_review --list

DCN-CHG-20260430-19.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from harness.context_docs import audit_claude_md_file
from harness.session_state import StateFormatError

# Reuse existing pricing util.
try:
    from harness.efficiency.analyze_sessions import price_for
except Exception:
    def price_for(_model: str) -> dict:  # type: ignore
        return {"in": 15.0, "out": 75.0, "cw5": 18.75, "cw1h": 30.0, "cr": 1.50}

# must_fix 는 저장 receipt가 아니라 prose SSOT에서 다시 계산한다.
try:
    from harness.session_state import _has_positive_must_fix
    from harness.session_state_fail_open import (
        collect_fail_open_summary,
        format_fail_open_warning,
    )
except Exception:
    def _has_positive_must_fix(_prose: str) -> bool:  # type: ignore
        return False

    def collect_fail_open_summary(*_args, **_kwargs) -> dict:  # type: ignore
        return {"total": 0}

    def format_fail_open_warning(_summary: dict) -> str:  # type: ignore
        return ""

# ── 상수 ───────────────────────────────────────────────────────────────

PLACEHOLDER_PATTERNS = [
    r"\[미기록\]", r"\[미결\]", r"M0\s*이후", r"M0\s*에서\s*검증",
    r"NotImplementedError", r"^\s*#\s*TODO\b", r"후보\s*\d+\s*개\s*비교",
]

# 이슈 #321 C STRAY_DIR_LEAK — known infra dir 와 fuzzy match (typo 의심)
# 예: `.claire` (실측 jajang run-dbd49faf task 1/2/3 사례) → `.claude` 의 typo
KNOWN_INFRA_DIR_NAMES = [".claude", ".git", ".github"]

INFRA_PATH_PATTERNS = [
    "/.claude/harness-state/", "/.claude/harness-logs/",
    "harness-memory.md", "harness.config.json", "/.claude/harness/",
]

READONLY_AGENTS = {
    "impl-validator",
    "architecture-validator",
}

# DCN-CHG-20260430-20: Phase 2 — per-Agent budget for THINKING_LOOP detection.
# elapsed_s: 정상 sub-agent 한 번 호출 한도 (초).
# min_output_tokens: 정상 sub-agent 가 emit 할 최소 output token (이하 = stall 의심).
EXPECTED_AGENT_BUDGETS: dict[str, dict[str, int]] = {
    "module-architect": {"elapsed_s": 600, "min_output_tokens": 1500},
    "system-architect": {"elapsed_s": 600, "min_output_tokens": 1500},
    "build-worker":    {"elapsed_s": 900, "min_output_tokens": 2000},
    "impl-validator":  {"elapsed_s": 420, "min_output_tokens": 1000},
    "architecture-validator": {"elapsed_s": 300, "min_output_tokens": 800},
    "product-acceptance": {"elapsed_s": 300, "min_output_tokens": 800},
    "tech-reviewer":   {"elapsed_s": 300, "min_output_tokens": 1000},
    "designer":        {"elapsed_s": 600, "min_output_tokens": 1000},
    "ux-architect":    {"elapsed_s": 600, "min_output_tokens": 1000},
}

DCNESS_AGENT_NAMES = set(EXPECTED_AGENT_BUDGETS.keys())

# issue #383 B1 — window padding. step.ts = end-step 호출 시각이므로
# sub-agent TUR ts (완료 시각) 는 first_ts 보다 약간 이전. padding 없으면
# 첫 step metric 매번 누락. ±60s 여유로 jajang 실측 8s off-by-N 흡수.
WINDOW_TS_PADDING = timedelta(seconds=60)

# issue #770/#771 — MUST_FIX_GHOST 는 *게이트* agent 가 advance 결론을 내면서 미해결
# MUST FIX 를 남긴 모순만 검출한다 (producer 의 must_fix·reviewer FAIL 은 정상 흐름).
# 게이트 = PASS/FAIL 결론으로 진행을 막는 read-only 검증/리뷰/검수 agent.
# hardcode 대신 권한 metadata 에서 *파생* — agent_boundary.ALLOW_MATRIX 의 *빈 허용*
# (Write 권한 0 = read-only) agent 가 곧 게이트다 (code/architecture-validator,
# impl-validator, architecture-validator, product-acceptance 자동 포함). tech-reviewer 는 자기
# 보고서를 쓰므로 빈 허용은 아니지만 PASS/FAIL/ESCALATE 게이트라 명시 추가.
# 이렇게 단일 SSOT 에서 파생하면 게이트가 늘어도 본 집합이 자동으로 따라간다 (#771
# whack-a-mole 종료 — 게이트 하나씩 누락되던 hardcode 회귀 차단).
def _derive_gate_agents() -> set[str]:
    try:
        from harness.agent_boundary import ALLOW_MATRIX
        read_only = {a for a, paths in ALLOW_MATRIX.items() if not paths}
    except Exception:
        read_only = {
            "impl-validator",
            "architecture-validator",
            "product-acceptance",
        }
    return read_only | {"tech-reviewer"}


MUST_FIX_GATE_AGENTS = _derive_gate_agents()
MUST_FIX_GHOST_PASS_ENUMS = {"PASS"}
def _resolved_verdict(step) -> str:
    """현재 prose SSOT에서 추출한 step verdict."""
    return step.conclusion_enum or ""

# DCN-CHG-20260430-38: 구현 결과 self-verify echo anchor 옵션 (DCN-30-34 강제 → DCN-30-38 자율화).
# prose 끝에 *어느 한 anchor* 라도 있으면 통과. 형식 자율 + substance 의무.
# heading 라인에 검증 / verification / self-verify 단어가 *포함* 되면 매칭 (issue #249 — `## 수용 기준 검증` 같은 변형 허용).
SELF_VERIFY_ANCHORS = [
    r"^\s*#{1,6}[^\n]*검증",
    r"^\s*#{1,6}[^\n]*verification",
    r"^\s*#{1,6}[^\n]*self[-\s]?verify",
]


def _has_self_verify_anchor(prose: str) -> bool:
    """구현 prose 에 self-verify anchor 중 하나라도 있는지 (DCN-30-38)."""
    if not prose:
        return False
    for pat in SELF_VERIFY_ANCHORS:
        if re.search(pat, prose, re.MULTILINE | re.IGNORECASE):
            return True
    return False


def _detect_stray_infra_dirs(prose: str) -> list[tuple[str, str, float]]:
    """이슈 #321 C STRAY_DIR_LEAK — `.claude` / `.git` / `.github` 와 typo 의심 디렉토리.

    prose 안 `.<word>(/|\\b)` 매치 + KNOWN_INFRA_DIR_NAMES 와 difflib similarity ≥ 0.78
    이지만 정확 매치 아닌 후보 → typo 의심.

    Returns list of (typo_name, intended_name, similarity_ratio).
    """
    if not prose:
        return []
    import difflib  # 표준 라이브러리. 모듈 top import 와 분리 (사용 시점 import 비용 무시).
    # 4~10 문자 word — `.claude` (7자) / `.git` (4자) / `.github` (7자) 모두 커버
    candidates = re.findall(r'(?<![./\w])\.([a-zA-Z][a-zA-Z0-9_-]{3,9})(?=[/\s\b]|$)', prose)
    leaks: list[tuple[str, str, float]] = []
    seen = set()
    for cand in candidates:
        full = "." + cand
        full_lower = full.lower()
        if full_lower in {n.lower() for n in KNOWN_INFRA_DIR_NAMES}:
            continue
        if full_lower in seen:
            continue
        seen.add(full_lower)
        for known in KNOWN_INFRA_DIR_NAMES:
            ratio = difflib.SequenceMatcher(None, full_lower, known).ratio()
            # 0.70 = .claire/.claude 케이스 (실측 0.714) 커버, .vscode/.cargo/.cache
            # 등 false positive 0건 (실측 모두 0.57 이하)
            if ratio >= 0.70:
                leaks.append((full, known, ratio))
                break
    return leaks


# ── 데이터 모델 ────────────────────────────────────────────────────────

@dataclass
class StepRecord:
    idx: int
    ts: str
    agent: str
    mode: Optional[str]
    enum: str
    must_fix: bool
    prose_excerpt: str
    prose_full: str = ""
    elapsed_s: int = 0  # ts diff to next step
    # DCN-CHG-20260430-20: per-Agent metrics from CC session JSONL toolUseResult.
    duration_ms: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    matched_invocation: bool = False
    # DCN-CHG-20260430-37: tool_use_count — TOOL_USE_OVERFLOW 검출 + DCN-30-36 hint 짝.
    tool_use_count: int = 0
    # issue #383 B4 — prose 본문 끝 결론 enum.
    # prose-only mode helper sentinel = `PROSE_LOGGED` → agent prose
    # 마지막 단락 결론 (agents/impl-validator.md 의 결론 + 권장 다음 단계 "PASS / FAIL / ESCALATE")
    # 을 표시 단계에서 추출. 부재 시 빈 문자열 (= sentinel 그대로 표시 fallback).
    conclusion_enum: str = ""
    # 같은 run finding의 재발 판정 근거로 ledger prose_file 경로를 보존한다.
    prose_file: str = ""


@dataclass
class WasteFinding:
    pattern: str
    severity: str  # HIGH / MEDIUM / LOW
    step_idx: int
    agent: str
    detail: str
    fix: str


# issue #394 — `NoteFinding` 신규. severity 없는 raw 알림 (결정 X).
# TOOL_USE_OVERFLOW / THINKING_LOOP 처럼 hardcoded 임계값 있지만 사용자 요청에 따라
# 보존된 패턴 — wastes 분리하고 "측정 noted" 섹션에 단순 알림 형식으로 표시.
@dataclass
class NoteFinding:
    pattern: str
    step_idx: int
    agent: str
    detail: str


@dataclass
class ContextAuditFinding:
    pattern: str
    severity: str  # WARN / CANDIDATE / INFO
    source: str
    detail: str
    suggestion: str


# issue #392 — `GoodFinding` dataclass 폐기. `detect_goods` 폐기와 정합.

DEFAULT_RECURRENCE_THRESHOLD = 3

_RECURRENCE_SUGGESTION = (
    "자동 박제 없음. 재발 원인을 확인한 뒤 룰 추가, skill 박제, 또는 기존 룰 제거 "
    "중 하나를 사용자 결정으로 분리합니다."
)


@dataclass
class RecurrenceCandidate:
    pattern: str
    count: int
    threshold: int
    source: str
    suggestion: str


@dataclass
class RunReport:
    run_id: str
    session_id: str
    run_dir: Path
    repo_path: Path = Path(".")
    steps: list[StepRecord] = field(default_factory=list)
    wastes: list[WasteFinding] = field(default_factory=list)
    # issue #394 — notes: raw 측정 알림 (severity 없음).
    notes: list[NoteFinding] = field(default_factory=list)
    # issue #392 — `goods` field 폐기. `detect_goods` / `GoodFinding` 폐기와 정합.
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    elapsed_s: int = 0
    final_enum: str = ""
    final_clean: bool = False
    recurrence_checked: bool = False
    recurrence_threshold: int = DEFAULT_RECURRENCE_THRESHOLD
    recurrence_candidates: list[RecurrenceCandidate] = field(default_factory=list)


def _read_context_doc(repo_path: Path, name: str) -> tuple[Path, str, bool]:
    path = repo_path / name
    try:
        return path, path.read_text(encoding="utf-8", errors="ignore"), path.is_file()
    except Exception:
        return path, "", False


def _doc_has_placeholder(text: str) -> bool:
    return bool(re.search(
        r"(?im)^\s*(?:[-*]\s*)?(?:TODO|TBD)\b|"
        r"\[(?:TODO|TBD|미기록|미결)\]|<TODO>|<TBD>|NotImplementedError",
        text,
    ))


def audit_context_docs(
    repo_path: Path,
    *,
    report: Optional["RunReport"] = None,
) -> list[ContextAuditFinding]:
    """Return read-only CLAUDE.md/AGENTS.md freshness candidates.

    This intentionally reports candidates only. It never edits project-owned
    context docs because CLAUDE.md/AGENTS.md are user-owned SSOT files.
    """
    repo_path = repo_path.resolve()
    findings: list[ContextAuditFinding] = []

    claude_path, claude_text, has_claude = _read_context_doc(repo_path, "CLAUDE.md")
    agents_path, agents_text, has_agents = _read_context_doc(repo_path, "AGENTS.md")

    if not has_claude:
        findings.append(ContextAuditFinding(
            pattern="CLAUDE_MISSING",
            severity="WARN",
            source=str(claude_path.relative_to(repo_path)),
            detail="프로젝트 루트에 CLAUDE.md 가 없어 세션 규칙 SSOT 를 찾을 수 없습니다.",
            suggestion="/init-dcness 가 공식 구조 기반 CLAUDE.md seed 를 생성할 수 있습니다.",
        ))
    elif _doc_has_placeholder(claude_text):
        findings.append(ContextAuditFinding(
            pattern="CLAUDE_PLACEHOLDER_PRESENT",
            severity="CANDIDATE",
            source="CLAUDE.md",
            detail="CLAUDE.md 안에 TODO/TBD/미기록 계열 placeholder 가 남아 있습니다.",
            suggestion="placeholder 가 현재 프로젝트 규칙 공백이면 사용자 승인 후 구체 규칙으로 바꾸는 docs PR 후보입니다.",
        ))
    if has_claude:
        claude_audit = audit_claude_md_file(repo_path)
        if claude_audit.missing_sections:
            findings.append(ContextAuditFinding(
                pattern="CLAUDE_STRUCTURE_GAP",
                severity="CANDIDATE",
                source="CLAUDE.md",
                detail="공식 권장 섹션 누락: " + ", ".join(claude_audit.missing_sections),
                suggestion="Commands / Architecture / Key Files / Code Style / Environment / Testing / Gotchas / Workflow 중 프로젝트에 필요한 섹션을 보강합니다.",
            ))
        if not claude_audit.has_cold_start_anchor:
            findings.append(ContextAuditFinding(
                pattern="CLAUDE_COLD_START_ANCHOR_MISSING",
                severity="CANDIDATE",
                source="CLAUDE.md",
                detail="dcNess Cold Start 앵커가 없어 다음 작업과 live issue/label 조회 경로가 세션 시작 문서에 없습니다.",
                suggestion="/init-dcness 는 기존 내용을 변경하지 않고 앵커만 append 할 수 있습니다.",
            ))
        if claude_audit.total_score < 90:
            axis_summary = ", ".join(
                f"{axis.name} {axis.score}/{axis.maximum}"
                for axis in claude_audit.axis_scores
                if axis.score < axis.maximum
            )
            findings.append(ContextAuditFinding(
                pattern="CLAUDE_QUALITY_GAP",
                severity="CANDIDATE",
                source="CLAUDE.md",
                detail=f"CLAUDE.md quality score {claude_audit.total_score}/100 ({claude_audit.grade}); {axis_summary}",
                suggestion="6축 rubric 결과를 보고 파괴적 재작성 없이 targeted addition 후보로 분리합니다.",
            ))
        if claude_audit.broken_references:
            findings.append(ContextAuditFinding(
                pattern="CLAUDE_STALE_REFERENCE",
                severity="CANDIDATE",
                source="CLAUDE.md",
                detail="존재하지 않는 path 참조: " + ", ".join(claude_audit.broken_references[:5]),
                suggestion="path 를 현재 파일 구조와 맞추거나 참조가 필요 없으면 사용자 승인 후 제거합니다.",
            ))

    if not has_agents:
        findings.append(ContextAuditFinding(
            pattern="AGENTS_MISSING",
            severity="INFO",
            source=str(agents_path.relative_to(repo_path)),
            detail="AGENTS.md 가 없어 외부 에이전트용 CLAUDE.md 참조 안내 경로가 없습니다.",
            suggestion="외부 에이전트 협업이 필요한 프로젝트라면 CLAUDE.md 를 참조하는 얇은 AGENTS.md 생성 후보입니다.",
        ))
    elif "CLAUDE.md" not in agents_text:
        findings.append(ContextAuditFinding(
            pattern="AGENTS_REFERENCES_CLAUDE_MISSING",
            severity="CANDIDATE",
            source="AGENTS.md",
            detail="AGENTS.md 가 CLAUDE.md 를 참조하지 않아 작업 규칙이 중복·분기될 수 있습니다.",
            suggestion="AGENTS.md 는 규칙 재기술 대신 CLAUDE.md 를 SSOT 로 가리키는 얇은 안내로 정리할지 검토합니다.",
        ))

    if report is not None:
        waste_count = 0
        for waste in report.wastes:
            if waste.severity not in {"HIGH", "MEDIUM"}:
                continue
            findings.append(ContextAuditFinding(
                pattern="RUN_REVIEW_WASTE_FEEDBACK",
                severity="CANDIDATE",
                source=f"run-review:{waste.agent}",
                detail=(
                    f"{waste.severity} {waste.pattern} at step {waste.step_idx}: "
                    f"{waste.detail}"
                ),
                suggestion=(
                    "반복될 운영 학습이면 CLAUDE.md/AGENTS.md 반영 후보입니다. "
                    "특정 agent 습관이면 agent prompt 수정이 우선입니다."
                ),
            ))
            waste_count += 1
            if waste_count >= 5:
                break
        note_count = 0
        for note in report.notes:
            if note.pattern not in {"THINKING_LOOP", "TOOL_USE_OVERFLOW"}:
                continue
            findings.append(ContextAuditFinding(
                pattern="RUN_REVIEW_NOTE_FEEDBACK",
                severity="INFO",
                source=f"run-review:{note.agent}",
                detail=f"{note.pattern} at step {note.step_idx}: {note.detail}",
                suggestion="비용·도구 사용 문제가 반복되면 CLAUDE.md 의 cost-aware 운영 규칙 후보로 검토합니다.",
            ))
            note_count += 1
            if note_count >= 5:
                break

    return findings


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_context_audit_section(
    repo_path: Path,
    *,
    report: Optional["RunReport"] = None,
) -> str:
    findings = audit_context_docs(repo_path, report=report)
    lines = [
        "## CLAUDE.md/AGENTS.md 현행화 후보",
        "",
        "이 섹션은 read-only context audit 입니다. CLAUDE.md/AGENTS.md 를 자동 수정하지 않습니다.",
        "",
    ]
    if not findings:
        lines.append("- 후보 없음 — 이번 run 에서 CLAUDE.md/AGENTS.md 반영 신호가 없습니다.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| severity | pattern | source | detail | suggestion |")
    lines.append("|---|---|---|---|---|")
    for finding in findings:
        lines.append(
            f"| {finding.severity} | `{finding.pattern}` | {_md_cell(finding.source)} | "
            f"{_md_cell(finding.detail)} | {_md_cell(finding.suggestion)} |"
        )
    lines.append("")
    lines.append("- 반영은 사용자 승인 후 별도 docs PR 로 진행합니다.")
    lines.append("- 프로젝트 공통 규칙이 아니면 CLAUDE.md/AGENTS.md 대신 agent prompt 수정을 우선합니다.")
    lines.append("")
    return "\n".join(lines)


# ── Run discovery ─────────────────────────────────────────────────────

def list_runs(sessions_root: Path) -> list[Path]:
    """`.sessions/{sid}/runs/{rid}/` 디렉토리 list (mtime 내림차순) — implicit --latest/--list 후보.

    이슈 #587 (codex review): run-review 는 *끝난* run 분석 도구다.
    - ledger-backed run(ledger.jsonl): `run_finished` event 와 유효 step_completed 가
      둘 다 있어야 포함한다. 신규 ledger 는 begin-run 부터 event 를 쓰므로, 첫
      step_completed 후 end-run 전의 partial active run 이 implicit --latest 로
      선택돼 미완 리포트가 나오는 것을 막고, step 없는 완료 run 도 제외한다.
      (명시 `--run-id` 는 find_run_dir 직접 탐색으로 partial 도 분석 가능.)
    """
    from harness import ledger

    if not sessions_root.exists():
        return []
    runs = []
    for sid_dir in sessions_root.iterdir():
        runs_dir = sid_dir / "runs"
        if not runs_dir.is_dir():
            continue
        for rid_dir in runs_dir.iterdir():
            try:
                events = ledger.read_events_at(rid_dir)
            except StateFormatError as exc:
                print(f"[run-review] invalid run skipped: {exc}", file=sys.stderr)
                continue
            if not events:
                continue
            has_step = any(e.get("event") == "step_completed" for e in events)
            if has_step and any(e.get("event") == "run_finished" for e in events):
                runs.append(rid_dir)
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def find_run_dir(sessions_root: Path, run_id: Optional[str], use_latest: bool) -> Optional[Path]:
    if run_id:
        for rd in list_runs(sessions_root):
            if rd.name == run_id:
                return rd
        # ledger에 아직 step이 없는 부분 완료 run도 명시 ID로는 탐색한다.
        for sid_dir in sessions_root.iterdir():
            runs_dir = sid_dir / "runs"
            if not runs_dir.is_dir():
                continue
            cand = runs_dir / run_id
            if cand.is_dir():
                return cand
        return None
    if use_latest:
        runs = list_runs(sessions_root)
        return runs[0] if runs else None
    return None


def _sessions_root_for_run(run_dir: Path) -> Optional[Path]:
    for parent in Path(run_dir).resolve().parents:
        if parent.name == ".sessions":
            return parent
    return None


def _build_recurrence_candidates(
    current_wastes: list[WasteFinding],
    run_dir: Path,
    *,
    threshold: int = DEFAULT_RECURRENCE_THRESHOLD,
) -> list[RecurrenceCandidate]:
    """Count current run waste patterns across finished runs in the same sessions root."""
    threshold = max(int(threshold), 1)
    target_patterns = {w.pattern for w in current_wastes}
    if not target_patterns:
        return []
    sessions_root = _sessions_root_for_run(run_dir)
    if sessions_root is None:
        return []

    counter: Counter = Counter()
    for candidate_run_dir in list_runs(sessions_root):
        steps = parse_steps(candidate_run_dir)
        for waste in detect_wastes(steps, run_dir=candidate_run_dir):
            if waste.pattern in target_patterns:
                counter[waste.pattern] += 1

    candidates: list[RecurrenceCandidate] = []
    for pattern, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < threshold:
            continue
        candidates.append(RecurrenceCandidate(
            pattern=pattern,
            count=count,
            threshold=threshold,
            source="run_review.waste",
            suggestion=_RECURRENCE_SUGGESTION,
        ))
    return candidates


# ── Step 파싱 ─────────────────────────────────────────────────────────

def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# issue #383 B4 — prose 본문 결론 enum 추출.
# agents/impl-validator.md 의 결론 + 권장 다음 단계 등: "prose 마지막 단락에 결론 (PASS / FAIL / ESCALATE)".
# 마지막 N줄에서 단어 단위 매칭 — 부정문 (예: "FAIL 없음", "0 FAIL") 회피를 위해
# 같은 줄에 부정 마커가 있으면 skip.
_CONCLUSION_ENUMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 현행 agents/*.md 결론 enum. 구체적 enum을 일반 enum보다 먼저 매칭한다.
    ("VALIDATION_BLOCKED", re.compile(r"\bVALIDATION_BLOCKED\b")),
    ("TESTS_FAIL", re.compile(r"\bTESTS_FAIL\b")),
    ("SPEC_GAP_FOUND", re.compile(r"\bSPEC_GAP_FOUND\b")),
    ("IMPLEMENTATION_ESCALATE", re.compile(r"\bIMPLEMENTATION_ESCALATE\b")),
    ("SYSTEM_CHECKPOINT_REQUIRED", re.compile(r"\bSYSTEM_CHECKPOINT_REQUIRED\b")),
    ("NEW_DEP_ESCALATE", re.compile(r"\bNEW_DEP_ESCALATE\b")),
    ("UX_FLOW_READY", re.compile(r"\bUX_FLOW_READY\b")),
    ("UX_FLOW_PATCHED", re.compile(r"\bUX_FLOW_PATCHED\b")),
    ("UX_REFINE_READY", re.compile(r"\bUX_REFINE_READY\b")),
    ("UX_FLOW_ESCALATE", re.compile(r"\bUX_FLOW_ESCALATE\b")),
    ("PASS", re.compile(r"\bPASS\b")),
    ("FAIL", re.compile(r"\bFAIL\b")),
    ("ESCALATE", re.compile(r"\bESCALATE\b")),
)
# 단독 결론 (negation 검사 skip 대상) — 단어 자체가 부정 형태 가질 수 없음.
_STANDALONE_CONCLUSIONS: frozenset[str] = frozenset({
    "SPEC_GAP_FOUND", "TESTS_FAIL", "VALIDATION_BLOCKED",
    "IMPLEMENTATION_ESCALATE", "SYSTEM_CHECKPOINT_REQUIRED", "NEW_DEP_ESCALATE",
    "UX_FLOW_READY", "UX_FLOW_PATCHED", "UX_REFINE_READY", "UX_FLOW_ESCALATE",
})
_NEGATION_RE = re.compile(
    r"(없|미발견|아님|아니|불필요|"           # 한글 부정
    r"\bno\b|\bnot\b|\bzero\b|\b0\s*\b|"     # 영어 부정
    r"없음)",
    re.IGNORECASE,
)


# issue #771 — GHOST 가드용. _extract_conclusion_enum 은 라벨 우선순위(PASS 먼저)
# 로 끝 15줄을 스캔해 "tests PASS" 같은 incidental pass 단어를 결론으로 잡을 수 있다.
# GHOST 는 게이트가 *진짜* 통과했을 때만 모순이므로, prose 의 *위치상 마지막* 결론이
# fail-class 면(= 실제 실패) pass 단어가 섞였어도 GHOST 에서 제외한다 (fail wins).
_FAIL_CLASS_VERDICTS = frozenset({
    "FAIL", "TESTS_FAIL", "ESCALATE",
    "SPEC_GAP_FOUND", "IMPLEMENTATION_ESCALATE", "SYSTEM_CHECKPOINT_REQUIRED",
    "NEW_DEP_ESCALATE", "UX_FLOW_ESCALATE", "VALIDATION_BLOCKED",
})
_PASS_CLASS_VERDICTS = frozenset({"PASS"})
_ANY_VERDICT_RE = re.compile(
    r"\b(PASS|TESTS_FAIL|SPEC_GAP_FOUND|IMPLEMENTATION_ESCALATE|"
    r"SYSTEM_CHECKPOINT_REQUIRED|NEW_DEP_ESCALATE|UX_FLOW_ESCALATE|"
    r"VALIDATION_BLOCKED|FAIL|ESCALATE)\b"
)


def _prose_final_verdict_is_fail(prose: str) -> bool:
    """prose 를 아래에서 위로 스캔해 *결론줄* 이 fail-class 결론인지.

    dcness agent 규약 = 마지막 단락에 결론. verdict 토큰을 가진 첫 줄(아래에서)이 결론줄.
    혼합줄("PASS / FAIL 중 FAIL", "PASS 아님 — FAIL")은 **fail 우선** — fail-class 토큰이
    하나라도 있으면 실패로 본다 (incidental pass 단어보다 fail 이 이김, issue #771).
    """
    for line in reversed([line for line in prose.splitlines() if line.strip()]):
        matches = list(_ANY_VERDICT_RE.finditer(line))
        if not matches:
            continue  # verdict 없는 줄 — 위로
        # 위치상 *마지막*(rightmost) 토큰이 결론. 혼합줄 "PASS / FAIL 중 FAIL" → FAIL,
        # "PASS / FAIL 중 PASS" → PASS (round4↔round5 진동 종결, issue #771).
        last = matches[-1].group(1)
        if last in _PASS_CLASS_VERDICTS and _NEGATION_RE.search(line):
            continue  # 마지막 토큰이 부정된 pass — 결론 불명, 위로
        return last in _FAIL_CLASS_VERDICTS
    return False


def _extract_conclusion_enum(prose: str) -> str:
    """prose 본문 끝 ~15줄에서 positive 결론 enum 추출.

    매칭 룰:
    - 끝 15줄 (마지막 단락 가정)
    - 결론 enum 단어 매칭 + 같은 줄 부정 마커 부재
    - 구체적 worker enum > PASS > FAIL > ESCALATE 우선순위
    - 다 매칭 실패 시 빈 문자열 반환 (= 호출자가 helper sentinel 그대로 표시)
    """
    if not prose:
        return ""
    lines = prose.splitlines()
    tail = lines[-15:] if len(lines) > 15 else lines
    for label, pattern in _CONCLUSION_ENUMS:
        for line in tail:
            if pattern.search(line):
                # routing enum 자체는 같은 줄의 부정 표현과 무관하게 명시 결론으로 본다.
                if label in _STANDALONE_CONCLUSIONS:
                    return label
                # 일반 PASS/FAIL/ESCALATE — 같은 줄에 부정 마커 있으면 skip
                if _NEGATION_RE.search(line):
                    continue
                return label
    return ""


def parse_steps(
    run_dir: Path,
    *,
    event_cutoff: Optional[datetime] = None,
) -> list[StepRecord]:
    # ledger.jsonl 의 현재 step_completed receipt를 읽는다.
    from harness import ledger

    steps: list[StepRecord] = []
    raw = ledger.read_step_completed_at(run_dir)
    if event_cutoff is not None:
        raw = [
            rec
            for rec in raw
            if (parsed := _parse_iso(rec.get("ts", ""))) is not None
            and parsed <= event_cutoff
        ]
    if not raw:
        return steps

    for idx, rec in enumerate(raw):
        agent = rec.get("agent", "?")
        mode = rec.get("mode")
        prose_full = ""

        # prose_file: end-step 이 기록한 절대 경로 → 직접 읽기
        prose_file = rec.get("prose_file")
        if prose_file:
            p = Path(prose_file)
            if p.exists():
                try:
                    prose_full = p.read_text(encoding="utf-8")
                except OSError:
                    pass

        must_fix = _has_positive_must_fix(prose_full)

        steps.append(StepRecord(
            idx=idx,
            ts=rec.get("ts", ""),
            agent=agent,
            mode=mode,
            enum=rec.get("enum", ""),
            must_fix=must_fix,
            prose_excerpt=rec.get("prose_excerpt", ""),
            prose_full=prose_full,
            conclusion_enum=_extract_conclusion_enum(prose_full),
            prose_file=str(prose_file or ""),
        ))

    # elapsed 계산 — 다음 step ts 와의 차이
    for i in range(len(steps) - 1):
        a = _parse_iso(steps[i].ts)
        b = _parse_iso(steps[i + 1].ts)
        if a and b:
            steps[i].elapsed_s = int((b - a).total_seconds())
    return steps


# ── Waste 탐지 ────────────────────────────────────────────────────────

def _scan_main_sed_misdiagnosis(
    repo_path: Optional[Path],
    window: Optional[tuple],
) -> list[str]:
    """CC session JSONL within run window 에서 메인 self-correction 패턴 검출
    (DCN-CHG-20260430-37). I5 회귀 추적 — "정정 — 변경 0" / "잘못 진단" 등.

    return: 매칭된 assistant text excerpt list (최대 3).
    """
    if not repo_path or not window:
        return []
    first_ts, last_ts = window
    keyword_filter = ["정정", "잘못 진단", "실측 시", "misdiagnosis", "변경사항 0"]
    patterns = [
        r"정정[^\n]{0,80}(0개|0\s*변경|실제\s*0|변경사항\s*0)",
        r"sed[^\n]{0,80}변경[^\n]{0,20}0",
        r"실측\s*시\s*0",
        r"잘못\s*진단",
        r"misdiagnosis",
    ]
    hits: list[str] = []
    try:
        for jsonl in find_session_jsonls(repo_path):
            try:
                lines = jsonl.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                if not any(kw in line for kw in keyword_filter):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                ts = _parse_iso(rec.get("timestamp", ""))
                if not ts:
                    continue
                ts_naive = ts.replace(tzinfo=None)
                if ts_naive < first_ts.replace(tzinfo=None) or ts_naive > last_ts.replace(tzinfo=None):
                    continue
                content = rec.get("message", {}).get("content", [])
                matched = False
                for blk in content:
                    if blk.get("type") != "text":
                        continue
                    text = blk.get("text", "")
                    for pat in patterns:
                        if re.search(pat, text):
                            hits.append(text[:300].replace("\n", " "))
                            matched = True
                            break
                    if matched:
                        break
                if len(hits) >= 3:
                    return hits
    except Exception:  # nosec B110
        pass
    return hits


def detect_wastes(
    steps: list[StepRecord],
    invocations: Optional[list[dict]] = None,
    repo_path: Optional[Path] = None,
    window: Optional[tuple] = None,
    run_dir: Optional[Path] = None,
) -> list[WasteFinding]:
    findings: list[WasteFinding] = []

    # RETRY_SAME_FAIL — 연속 동일 FAIL enum
    # 이슈 #302 #1: prose-only mode (#284) 정착 후 PROSE_LOGGED 가 표준 advance enum.
    # 또한 같은 (agent, mode) 가 N task 순회 정상 호출 (예: module-architect × 4)
    # 시 동일 enum 반복은 *retry 가 아닌 정상 호출* — prose 내용이 다르면 다른 step.
    ADVANCE_ENUMS = {
        "PASS",
        "UX_FLOW_READY", "UX_FLOW_PATCHED", "UX_REFINE_READY",
        "PROSE_LOGGED",  # #284 prose-only mode default sentinel
    }
    for i in range(1, len(steps)):
        prev, cur = steps[i - 1], steps[i]
        if prev.agent != cur.agent or prev.enum != cur.enum:
            continue
        if prev.enum in ADVANCE_ENUMS:
            continue
        # prose 내용이 *다르면* 같은 enum 이라도 다른 invocation (N task 순회 등)
        # — retry 아님. prose_excerpt 가 동일할 때만 진짜 retry 후보.
        prev_prose = prev.prose_full or prev.prose_excerpt
        cur_prose = cur.prose_full or cur.prose_excerpt
        if prev_prose and cur_prose and prev_prose != cur_prose:
            continue
        findings.append(WasteFinding(
            pattern="RETRY_SAME_FAIL",
            severity="MEDIUM",
            step_idx=i,
            agent=cur.agent,
            detail=f"step {i-1}→{i} 동일 enum 반복: {cur.enum}",
            fix=f"agents/{cur.agent}.md fail 전략 강화 또는 impl 보강",
        ))

    # build-worker prose는 구현 결과를 routing할 결론 enum이 필수다.
    for s in steps:
        if s.agent != "build-worker":
            continue
        if not s.prose_full:
            continue  # prose 부재 시 검사 불가
        if s.conclusion_enum:
            continue  # 결론 enum 정상 있음
        findings.append(WasteFinding(
            pattern="MISSING_CONCLUSION_ENUM",
            severity="MEDIUM",
            step_idx=s.idx,
            agent=s.agent,
            detail=(
                f"build-worker step {s.idx} prose 끝 결론 enum 부재 — "
                "agents/build-worker.md 결론 계약 위반 "
                "(PASS / SPEC_GAP_FOUND / TESTS_FAIL / VALIDATION_BLOCKED / "
                "IMPLEMENTATION_ESCALATE 중 1)"
            ),
            fix=(
                "build-worker 재호출 시 prompt 에 결론 enum 강제 의무 명시 또는 "
                "메인 Claude 가 prose routing 결정 시 enum 부재 인지 + 재호출"
            ),
        ))

    # issue #392 — ECHO_VIOLATION / PLACEHOLDER_LEAK 폐기.
    # 사유: agent 자율 영역 침해. ECHO_VIOLATION (prose <5줄) = "agent 자율 침해",
    # PLACEHOLDER_LEAK = "약속-실측 검사" — agent 자율 판정 경계 위반.

    # STRAY_DIR_LEAK — `.claude` 와 typo 의심 디렉토리 흔적 (#321 C)
    # 실측: jajang run-dbd49faf task 1/2/3 `.claire` 3 회 연속.
    for s in steps:
        if not s.prose_full:
            continue
        for typo, intended, ratio in _detect_stray_infra_dirs(s.prose_full):
            findings.append(WasteFinding(
                pattern="STRAY_DIR_LEAK",
                severity="MEDIUM",
                step_idx=s.idx,
                agent=s.agent,
                detail=f"{s.agent} prose 안 `{typo}/` 흔적 — `{intended}/` typo 의심 (similarity {ratio:.2f})",
                fix=f"agents/{s.agent}.md 디렉토리명 정확 인지 룰 보강 또는 사용자 환경 검증",
            ))

    # MUST_FIX_GHOST — 게이트(리뷰어/검증자)가 PASS 결론을 내면서 prose 에 미해결
    # MUST FIX 를 남긴 모순 (= 통과시키면 안 되는데 통과). issue #770: 옛 룰은
    # `must_fix and 다음 step 존재` 만으로 위반 판정 → conveyor 의 정상 흐름
    # (reviewer FAIL → build-worker fix → 재리뷰) + producer 의 고친-항목 재진술을
    # 전수 오탐했다.
    # 실측 41/41 false positive. 진짜 신호는 *게이트가 advance(PASS)하면서
    # blocker 를 남긴* 경우뿐 — producer(build-worker)의 must_fix
    # 와 reviewer 의 FAIL 은 정상. 마지막 step 미해결은 MUST_FIX_LEAK 담당이라 제외.
    for i, s in enumerate(steps):
        if not (s.must_fix and i + 1 < len(steps)):
            continue
        if s.agent not in MUST_FIX_GATE_AGENTS:
            continue
        verdict = _resolved_verdict(s)
        if verdict not in MUST_FIX_GHOST_PASS_ENUMS:
            continue
        # prose 의 위치상 마지막 결론이 fail-class 면 incidental pass 단어를
        # conclusion_enum이 잘못 집은 것이므로 정상 fail→fix 루프로 본다.
        if _prose_final_verdict_is_fail(s.prose_full or s.prose_excerpt):
            continue
        findings.append(WasteFinding(
            pattern="MUST_FIX_GHOST",
            severity="HIGH",
            step_idx=i,
            agent=s.agent,
            detail=f"step {i} ({s.agent}) {verdict} 결론인데 prose 에 미해결 MUST FIX — 게이트 통과 모순",
            fix=f"agents/{s.agent}.md 결론 일관성 — MUST FIX 가 있으면 PASS 가 아니라 FAIL",
        ))

    # issue #383 B3 — MUST_FIX_LEAK. 마지막 step 의 must_fix=True (= caveat 신호)
    # 는 MUST_FIX_GHOST 룰이 *다음 step 없음* 으로 skip → wastes 비어있는
    # 회귀 발생 (jajang run-459cce99 impl-validator 케이스). 사용자에게 caveat
    # 통지 누락 회피 위해 wastes 1+ 써서 회귀 차단.
    last = steps[-1] if steps else None
    if last and last.must_fix:
        findings.append(WasteFinding(
            pattern="MUST_FIX_LEAK",
            severity="HIGH",
            step_idx=len(steps) - 1,
            agent=last.agent,
            detail=f"마지막 step ({last.agent}) must_fix=True — caveat 통지 의무",
            fix="loop-procedure.md 의 7b — 주의사항 확인 분기 — 사용자 위임 + 메모리 candidate emit",
        ))

    # SPEC_GAP_LOOP — 현행 agent들의 SPEC_GAP_FOUND cycle 한도 초과
    spec_gap_steps = [s for s in steps if _resolved_verdict(s) == "SPEC_GAP_FOUND"]
    spec_gap_count = len(spec_gap_steps)
    if spec_gap_count > 2:
        gap_agent = spec_gap_steps[-1].agent
        findings.append(WasteFinding(
            pattern="SPEC_GAP_LOOP",
            severity="MEDIUM",
            step_idx=-1,
            agent=gap_agent,
            detail=f"SPEC_GAP_FOUND {spec_gap_count}회 — cycle 한도 2 초과",
            fix="module-architect 보강 또는 사용자 위임",
        ))

    # INFRA_READ — prose 안 인프라 경로 흔적
    # issue #543: build-worker 등 driver 는 계약상 prose 끝에 자기 run_dir 의
    # phase prose 경로 (runs/<run_id>/build-*.md) 를 메인 ls 검증용으로 나열한다.
    # 그 경로는 리뷰 중인 run 자기 자신의 run_dir 아래라 인프라 *탐색* 이 아닌
    # 자기-bookkeeping → 오탐. 매칭된 인프라 경로가 등장하는 line 단위로 보고,
    # 자기 run_dir (`runs/<run_id>/`) 자기-참조 line 은 제외한다. 다른 세션/run
    # 경로·harness-memory.md 등 진짜 leak 은 self marker 미포함 → 검출 유지.
    self_run_marker = f"runs/{run_dir.name}/" if run_dir is not None else None
    for s in steps:
        for path in INFRA_PATH_PATTERNS:
            hit_lines = [ln for ln in s.prose_full.splitlines() if path in ln]
            if self_run_marker is not None:
                hit_lines = [ln for ln in hit_lines if self_run_marker not in ln]
            if hit_lines:
                findings.append(WasteFinding(
                    pattern="INFRA_READ",
                    severity="HIGH",
                    step_idx=s.idx,
                    agent=s.agent,
                    detail=f"{s.agent} prose 안 인프라 경로 흔적: `{path}`",
                    fix=f"agents/{s.agent}.md 권한 경계 인프라 탐색 금지 강화",
                ))
                break

    # READONLY_BASH — read-only agent 가 Bash 호출 흔적
    for s in steps:
        if s.agent in READONLY_AGENTS and re.search(r"`bash`|Bash tool|```bash", s.prose_full):
            findings.append(WasteFinding(
                pattern="READONLY_BASH",
                severity="HIGH",
                step_idx=s.idx,
                agent=s.agent,
                detail=f"{s.agent} (read-only) prose 안 Bash 흔적",
                fix=f"agents/{s.agent}.md Bash 사용 금지 명시 강화",
            ))

    # issue #392 — EXTERNAL_VERIFIED_MISSING 폐기 (정신 위반 — 약속-실측 검사).

    # issue #394 — THINKING_LOOP / TOOL_USE_OVERFLOW 는 detect_notes 로 이동.
    # issue #392 — PARTIAL_LOOP 폐기 (hardcoded ≥3 임계값 = 정신 위반).

    # END_STEP_SKIP (DCN-CHG-20260430-37) — sub-agent invocation > ledger receipt.
    # 메인 distract → end-step 호출 skip → receipt 누락. DCN-30-25 STEP COUNT WARN /
    # DCN-30-33 STALE STEP WARN 의 사후 측정 보완.
    if invocations:
        from collections import Counter
        inv_count_per_agent = Counter(i["agent"] for i in invocations)
        step_count_per_agent = Counter(s.agent for s in steps)
        for agent_name, inv_n in inv_count_per_agent.items():
            step_n = step_count_per_agent.get(agent_name, 0)
            # margin 1 — sub-agent self-recurse 등 false positive 회피.
            if inv_n > step_n + 1:
                findings.append(WasteFinding(
                    pattern="END_STEP_SKIP",
                    severity="HIGH",
                    step_idx=-1,
                    agent=agent_name,
                    detail=f"{agent_name} invocations={inv_n} > steps={step_n} "
                           f"(diff={inv_n-step_n}) — end-step 호출 누락 의심.",
                    fix="commands/<skill>.md begin/end-step 1:1 의무 (DCN-30-25 / DCN-30-33). "
                        "메인 distract 회피 — Agent 직후 즉시 end-step.",
                ))

    # issue #392 — MISSING_SELF_VERIFY 폐기 (agent 자율 영역 침해).
    # issue #392 — MAIN_SED_MISDIAGNOSIS 폐기 (메인 자율 영역 + 검출 모호함).

    return findings


# ── Good 탐지 ─────────────────────────────────────────────────────────

def detect_notes(steps: list[StepRecord]) -> list[NoteFinding]:
    """issue #394 — "측정 noted" raw 알림 (severity 없음).

    사용자 요청: hardcoded 임계 유지하되 결정 X. 메인이 보고 자율 판단.

    포함 패턴:
    - THINKING_LOOP — duration > budget × 1.5 + output_tokens < budget × 0.3
    - TOOL_USE_OVERFLOW — tool_use_count ≥ 100
    """
    notes: list[NoteFinding] = []

    # THINKING_LOOP — sub-agent 가 오래 돌았는데 output token 적음
    for s in steps:
        if not s.matched_invocation:
            continue
        budget = EXPECTED_AGENT_BUDGETS.get(s.agent)
        if not budget:
            continue
        duration_s = s.duration_ms / 1000 if s.duration_ms else 0
        out_tok = s.output_tokens
        thinking_loop = False
        reason = ""
        if duration_s > budget["elapsed_s"] * 1.5 and out_tok < budget["min_output_tokens"] * 0.3:
            thinking_loop = True
            reason = (f"duration {duration_s:.0f}s > budget {budget['elapsed_s']}s × 1.5 + "
                      f"output {out_tok} < min {budget['min_output_tokens']} × 0.3")
        elif duration_s > 300 and out_tok < 1000:
            thinking_loop = True
            reason = f"duration {duration_s:.0f}s > 300s + output {out_tok} < 1000"
        if thinking_loop:
            notes.append(NoteFinding(
                pattern="THINKING_LOOP",
                step_idx=s.idx,
                agent=s.agent,
                detail=f"{s.agent} stall 의심 — {reason}",
            ))

    # TOOL_USE_OVERFLOW — step 의 tool_use_count ≥ 100
    for s in steps:
        if not s.matched_invocation or s.tool_use_count < 100:
            continue
        notes.append(NoteFinding(
            pattern="TOOL_USE_OVERFLOW",
            step_idx=s.idx,
            agent=s.agent,
            detail=f"{s.agent} step {s.idx} tool_use_count={s.tool_use_count} (≥ 100, "
                   "tool 사용 과다로 context overflow 위험)",
        ))

    return notes


# issue #392 — `detect_goods` 함수 + 5 good patterns 전체 폐기.
# 사유: dcness 정신 정합 X — CLAUDE.md 의 dcness 강제 원칙 "임계값 hardcode 금지 + 자율 친화".
# 본 함수의 5 patterns (ENUM_CLEAN / PROSE_ECHO_OK / DDD_PHASE_A / DEPENDENCY_CAUSAL /
# EXTERNAL_VERIFIED_PRESENT) 모두 폐기. 잘한점 섹션은 review.md render 에서도 제거.


# ── Per-Agent invocation extraction (DCN-CHG-20260430-20, Phase 2) ────


# agent 이름 정규화 SSOT.
from harness.agent_names import normalize_agent_type as _normalize_agent_type  # noqa: E402,F401


def _compute_invocation_cost(model: str, usage: dict) -> float:
    """toolUseResult.usage 의 token breakdown 으로 USD 계산. price_for util 재사용."""
    if not usage:
        return 0.0
    price = price_for(model)
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    cw_detail = usage.get("cache_creation", {}) or {}
    cw5 = cw_detail.get("ephemeral_5m_input_tokens", 0)
    cw1h = cw_detail.get("ephemeral_1h_input_tokens", 0)
    if cw5 + cw1h == 0 and cw > 0:
        cw5 = cw
    return (
        inp * price["in"] / 1e6
        + out * price["out"] / 1e6
        + cw5 * price["cw5"] / 1e6
        + cw1h * price["cw1h"] / 1e6
        + cr * price["cr"] / 1e6
    )


def extract_agent_invocations(repo_path: Path, run_window: tuple[datetime, datetime]) -> list[dict]:
    """CC session JSONL 의 toolUseResult 에서 dcness sub-agent 호출만 추출.

    return: [{ts, agent, duration_ms, output_tokens, total_tokens, cost_usd, ...}, ...] (ts 오름차순).
    """
    first_ts, last_ts = run_window
    invocations: list[dict] = []

    for jsonl in find_session_jsonls(repo_path):
        try:
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tur = rec.get("toolUseResult")
                if not isinstance(tur, dict):
                    continue
                # totalTokens 또는 totalDurationMs 가 있어야 sub-agent result.
                if "totalTokens" not in tur and "totalDurationMs" not in tur:
                    continue
                rec_ts = _parse_iso(rec.get("timestamp", ""))
                if not rec_ts:
                    continue
                # 날짜 비교를 위해 timezone 통일 — naive 만 비교.
                rec_ts_naive = rec_ts.replace(tzinfo=None)
                if rec_ts_naive < first_ts.replace(tzinfo=None) or rec_ts_naive > last_ts.replace(tzinfo=None):
                    continue
                agent_type = tur.get("agentType") or ""
                normalized = _normalize_agent_type(agent_type)
                if normalized not in DCNESS_AGENT_NAMES:
                    continue
                usage = tur.get("usage", {}) or {}
                # iterations[].* 의 model 정보가 있으면 우선. 없으면 default opus.
                model = ""
                iters = usage.get("iterations") or []
                if iters and isinstance(iters[0], dict):
                    model = iters[0].get("model", "") or ""
                cost = _compute_invocation_cost(model, usage)
                invocations.append({
                    "ts": rec_ts_naive,
                    "agent": normalized,
                    "agent_type_raw": agent_type,
                    "duration_ms": tur.get("totalDurationMs", 0),
                    "total_tokens": tur.get("totalTokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "input_tokens": usage.get("input_tokens", 0),
                    "cache_read": usage.get("cache_read_input_tokens", 0),
                    "cost_usd": cost,
                    "tool_use_count": tur.get("totalToolUseCount", 0),
                })
        except OSError:
            continue

    invocations.sort(key=lambda r: r["ts"])
    return invocations


def assign_invocations_to_steps(steps: list[StepRecord], invocations: list[dict]) -> None:
    """각 step 에 대응 invocation 매칭 — timestamp proximity 기반 (DCN-30-21 fix).

    이전 algo (단순 순서 + agent name) 결함: step 0 invocation 누락 시 (다른 세션
    호출 등) cascade 로 후속 step 매칭 모두 어긋남. jajang 실측에서 9 step 중
    2 만 매칭, 7 미매칭. fix — 각 step 의 ts 와 가장 가까운 invocation 을 매칭
    window 안에서 선택. 1 invocation = 1 step (used set).

    매칭 룰:
    - inv.ts < step.ts (sub-agent 가 end-step 직전에 끝남)
    - step.ts - inv.ts ≤ 600s (10 분 — sub-agent budget 한도)
    - inv.agent == step.agent
    - 같은 agent 후보 여럿이면 가장 최근 inv (closest before step.ts)
    """
    if not steps or not invocations:
        return
    used: set[int] = set()

    for step in steps:
        step_ts = _parse_iso(step.ts)
        if not step_ts:
            continue
        step_ts_naive = step_ts.replace(tzinfo=None)
        best_idx = -1
        best_diff_s = float("inf")
        for i, inv in enumerate(invocations):
            if i in used:
                continue
            if inv["agent"] != step.agent:
                continue
            inv_ts = inv["ts"]
            if isinstance(inv_ts, datetime):
                inv_ts_naive = inv_ts.replace(tzinfo=None) if inv_ts.tzinfo else inv_ts
            else:
                continue
            diff_s = (step_ts_naive - inv_ts_naive).total_seconds()
            if 0 <= diff_s <= 600 and diff_s < best_diff_s:
                best_idx = i
                best_diff_s = diff_s
        if best_idx >= 0:
            inv = invocations[best_idx]
            step.duration_ms = inv["duration_ms"]
            step.output_tokens = inv["output_tokens"]
            step.total_tokens = inv["total_tokens"]
            step.cost_usd = inv["cost_usd"]
            step.matched_invocation = True
            step.tool_use_count = inv.get("tool_use_count", 0)
            used.add(best_idx)


# ── Cost cross-correlation (run-level coarse) ────────────────────────

def encode_repo_path_dcness(repo_path: str) -> str:
    """CC project dir 인코딩 룰 — `/` 와 `.` 모두 `-` 로 (DCN-30-08 fix 정합)."""
    return repo_path.replace("/", "-").replace(".", "-")


def find_session_jsonls(repo_path: Path) -> list[Path]:
    encoded = encode_repo_path_dcness(str(repo_path))
    base = Path.home() / ".claude" / "projects" / encoded
    if not base.exists():
        return []
    return list(base.glob("*.jsonl"))


def compute_run_cost(run_dir: Path, repo_path: Path) -> tuple[float, int, int]:
    """Run timeframe 내 assistant turn 의 cost/input/output 합산. Coarse — Agent 별 분리 X."""
    # 이슈 #587 (codex review) — run window = run_started ~ run_finished lifecycle event.
    # lifecycle marker가 손상된 경우 유효 step receipt 범위로 제한한다.
    from harness import ledger

    events = ledger.read_events_at(run_dir)
    if not events:
        return (0.0, 0, 0)
    started = next((e for e in events if e.get("event") == "run_started"), None)
    finished = next(
        (e for e in reversed(events) if e.get("event") == "run_finished"), None
    )
    steps = [e for e in events if e.get("event") == "step_completed"]
    first_src = started or (steps[0] if steps else None)
    last_src = finished or (steps[-1] if steps else None)
    if not first_src or not last_src:
        return (0.0, 0, 0)

    first_ts = _parse_iso(first_src.get("ts", ""))
    last_ts = _parse_iso(last_src.get("ts", ""))
    if not first_ts or not last_ts:
        return (0.0, 0, 0)

    total_cost = 0.0
    total_in = 0
    total_out = 0

    for jsonl in find_session_jsonls(repo_path):
        try:
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("timestamp", "")
                rec_ts = _parse_iso(ts)
                if not rec_ts:
                    continue
                if rec_ts < first_ts or rec_ts > last_ts:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message", {})
                model = msg.get("model", "") or ""
                usage = msg.get("usage", {}) or {}
                price = price_for(model)
                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cw = usage.get("cache_creation_input_tokens", 0)
                cr = usage.get("cache_read_input_tokens", 0)
                total_cost += (
                    inp * price["in"] / 1e6 + out * price["out"] / 1e6
                    + cw * price["cw5"] / 1e6 + cr * price["cr"] / 1e6
                )
                total_in += inp + cw + cr
                total_out += out
        except OSError:
            continue

    return (total_cost, total_in, total_out)


# ── Report 생성 ───────────────────────────────────────────────────────

def render_report(report: RunReport) -> str:
    lines = []
    lines.append(f"# Run Review: {report.run_id}")
    lines.append("")
    lines.append("## 요약")
    lines.append("| 항목 | 값 |")
    lines.append("|---|---|")
    lines.append(f"| run_id | `{report.run_id}` |")
    lines.append(f"| session_id | `{report.session_id}` |")
    lines.append(f"| step 수 | {len(report.steps)} |")
    lines.append(f"| 소요 | {report.elapsed_s}s |")
    lines.append(f"| 비용 (run window 내) | ${report.total_cost_usd:.4f} |")
    lines.append(f"| input tokens | {report.total_input_tokens:,} |")
    lines.append(f"| output tokens | {report.total_output_tokens:,} |")
    lines.append(f"| 최종 enum | `{report.final_enum}` |")
    lines.append(f"| clean 판정 | {'✅' if report.final_clean else '❌'} |")
    lines.append("")

    fail_open_warning = format_fail_open_warning(
        collect_fail_open_summary(cwd=report.repo_path)
    )
    if fail_open_warning:
        lines.append(fail_open_warning)
        lines.append("")

    # 호출 흐름 — issue #383 B4: prose 결론 enum 우선 표시.
    # helper sentinel `PROSE_LOGGED` 는 prose-only mode 신호일 뿐 사용자 가독성 0.
    # parse_steps 가 prose 본문 끝 결론을 추출 → 우선.
    lines.append("## 호출 흐름")
    lines.append("```")
    for i, s in enumerate(report.steps):
        marker = "└─" if i == len(report.steps) - 1 else "├─"
        mode_str = f" [{s.mode}]" if s.mode else ""
        flag = " ⚠️" if s.must_fix else ""
        display_enum = s.conclusion_enum or s.enum
        lines.append(f"{marker} {s.agent}{mode_str} ({s.elapsed_s}s) → {display_enum}{flag}")
    lines.append("```")
    lines.append("")

    # 단계별 표 (DCN-30-20: per-Agent metrics + DCN-30-24: local time 시작 컬럼
    #            + DCN-CHG-20260430-39: tool_uses 컬럼 — TOOL_USE_OVERFLOW 가시성)
    lines.append("## 단계별 상세")
    lines.append("| # | 시작(local) | agent | mode | elapsed(s) | duration(s) | out_tok | total_tok | tool_uses | cost($) | enum | must_fix | prose줄 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in report.steps:
        line_count = len([
            line for line in (s.prose_full or s.prose_excerpt).splitlines()
            if line.strip()
        ])
        dur_s = f"{s.duration_ms / 1000:.0f}" if s.matched_invocation else "-"
        out_tok = f"{s.output_tokens:,}" if s.matched_invocation else "-"
        tot_tok = f"{s.total_tokens:,}" if s.matched_invocation else "-"
        cost = f"{s.cost_usd:.4f}" if s.matched_invocation else "-"
        if s.matched_invocation:
            # ≥ 100 시 **bold** — TOOL_USE_OVERFLOW 임계와 동일 (run_review.py:465)
            tu_str = f"**{s.tool_use_count}**" if s.tool_use_count >= 100 else str(s.tool_use_count)
        else:
            tu_str = "-"
        ts_local = "-"
        ts_dt = _parse_iso(s.ts)
        if ts_dt:
            # UTC ISO → system local time (Mac 기본: 한국 KST)
            ts_local = ts_dt.astimezone().strftime("%H:%M:%S")
        # issue #383 B4 — prose 결론 enum 우선 표시 (sentinel fallback).
        display_enum = s.conclusion_enum or s.enum
        lines.append(
            f"| {s.idx} | {ts_local} | {s.agent} | {s.mode or '-'} | {s.elapsed_s} | "
            f"{dur_s} | {out_tok} | {tot_tok} | {tu_str} | {cost} | "
            f"`{display_enum}` | {'⚠️' if s.must_fix else ''} | {line_count} |"
        )
    lines.append("")

    # issue #392 — "잘한 점" 섹션 폐기. detect_goods + GoodFinding 폐기와 정합.

    # issue #394 — 측정 noted (TOOL_USE_OVERFLOW / THINKING_LOOP, severity 없음)
    if report.notes:
        lines.append("## ⚠️ 측정 noted (임계 도달 — 결정 X, 메인 자율 판단)")
        for n in report.notes:
            lines.append(f"- step {n.step_idx} {n.agent} `{n.pattern}` — {n.detail}")
        lines.append("")

    # issue #396 — 메인 인사이트 prompt (REVIEW_READY 시 메인 시야 진입)
    # 메인 Claude 가 review.md 본 후 자연어 한 줄 평가 박는 매커니즘 안내.
    # 미씀 = noop (자율 영역, 강제 X).

    # 잘못한 점 (차단성 검출 — catastrophic / drift)
    if report.wastes:
        lines.append("## 잘못한 점 (Waste Findings)")
        lines.append("| # | 심각도 | 패턴 | step | agent | 상세 | 수정 |")
        lines.append("|---|---|---|---|---|---|---|")
        sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        for i, w in enumerate(sorted(report.wastes, key=lambda x: sev_order.get(x.severity, 9)), 1):
            lines.append(
                f"| {i} | {w.severity} | `{w.pattern}` | {w.step_idx} | {w.agent} "
                f"| {w.detail} | {w.fix} |"
            )
        lines.append("")
    else:
        lines.append("## 잘못한 점 — 없음 ✅")
        lines.append("")

    if report.recurrence_checked:
        lines.append(f"## 재발 기반 개선 후보 (threshold {report.recurrence_threshold})")
        lines.append("")
        if report.recurrence_candidates:
            lines.append("| pattern | count | suggestion |")
            lines.append("|---|---:|---|")
            for candidate in report.recurrence_candidates:
                lines.append(
                    f"| {candidate.pattern} | {candidate.count} | {candidate.suggestion} |"
                )
        else:
            lines.append("(임계 도달 후보 없음 — GOOD 사례는 집계 대상이 아닙니다.)")
        lines.append("")
        lines.append("자동 수정 없음 — 후보 표면화까지만 수행하고 박제 여부는 사용자가 결정합니다.")
        lines.append("")

    lines.append(render_context_audit_section(report.repo_path, report=report))

    return "\n".join(lines)


# ── 실행 ──────────────────────────────────────────────────────────────

def build_report(
    run_dir: Path,
    repo_path: Path,
    *,
    include_recurrence: bool = False,
    recurrence_threshold: int = DEFAULT_RECURRENCE_THRESHOLD,
    event_cutoff: Optional[datetime] = None,
) -> RunReport:
    steps = parse_steps(run_dir, event_cutoff=event_cutoff)

    # DCN-CHG-20260430-20: per-Agent invocation 매칭 — wastes 탐지 *전*에 enrichment.
    invocations: list[dict] = []
    window: Optional[tuple] = None
    if steps:
        first_ts = _parse_iso(steps[0].ts)
        last_ts = _parse_iso(steps[-1].ts)
        if first_ts and last_ts:
            # issue #383 B1 — window padding. step.ts = end-step 호출 시각.
            # sub-agent TUR ts 는 end-step 호출 직전 (= first_ts 보다 약간 이전).
            # padding 없이 [first_ts, last_ts] 로 잡으면 첫 step TUR 가 *항상*
            # window 밖으로 필터아웃되어 구조적으로 첫 step metric 누락.
            # 실측 run에서 sub-agent 완료 시각과 first step 시각이 8초 어긋난 사례.
            window = (first_ts - WINDOW_TS_PADDING, last_ts + WINDOW_TS_PADDING)
            invocations = extract_agent_invocations(repo_path, window)
            assign_invocations_to_steps(steps, invocations)

    # DCN-CHG-20260430-37: detect_wastes 에 invocations + repo_path + window 전달
    # (END_STEP_SKIP / MAIN_SED_MISDIAGNOSIS run-level 패턴 검출 위해).
    wastes = detect_wastes(
        steps, invocations=invocations, repo_path=repo_path,
        window=window, run_dir=run_dir,
    )
    notes = detect_notes(steps)  # issue #394 — TOOL_USE_OVERFLOW / THINKING_LOOP raw 알림
    # issue #392 — detect_goods 호출 폐기.
    cost, in_tok, out_tok = compute_run_cost(run_dir, repo_path)

    elapsed = 0
    if len(steps) >= 2:
        a = _parse_iso(steps[0].ts)
        b = _parse_iso(steps[-1].ts)
        if a and b:
            elapsed = int((b - a).total_seconds())

    # issue #383 B4 — final_enum 표시도 conclusion 우선. clean 판정 로직 자체는
    # has_must_fix / has_ambiguous (= helper sentinel 기반) 그대로 — 의미 변경 없음.
    final_enum = ""
    if steps:
        final_enum = steps[-1].conclusion_enum or steps[-1].enum
    has_must_fix = any(s.must_fix for s in steps)
    has_ambiguous = any(s.enum == "AMBIGUOUS" for s in steps)
    final_clean = bool(
        final_enum and not has_must_fix and not has_ambiguous
        and len([w for w in wastes if w.severity == "HIGH"]) == 0
    )
    recurrence_threshold = max(int(recurrence_threshold), 1)
    recurrence_candidates = (
        _build_recurrence_candidates(
            wastes,
            run_dir,
            threshold=recurrence_threshold,
        )
        if include_recurrence
        else []
    )

    sid = run_dir.parent.parent.name
    return RunReport(
        run_id=run_dir.name,
        session_id=sid,
        run_dir=run_dir,
        repo_path=repo_path,
        steps=steps,
        wastes=wastes,
        notes=notes,
        total_cost_usd=cost,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        elapsed_s=elapsed,
        final_enum=final_enum,
        final_clean=final_clean,
        recurrence_checked=include_recurrence,
        recurrence_threshold=recurrence_threshold,
        recurrence_candidates=recurrence_candidates,
    )


def _detect_sessions_root(cwd: Path) -> Optional[Path]:
    """`.claude/harness-state/.sessions/` 위치 자동 탐지 (현재 dir + .git common parent)."""
    cur = cwd / ".claude" / "harness-state" / ".sessions"
    if cur.exists():
        return cur
    # worktree fallback — git common-dir
    try:
        import subprocess  # nosec B404
        r = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            common = Path(r.stdout.strip())
            cand = common.parent / ".claude" / "harness-state" / ".sessions"
            if cand.exists():
                return cand
    except Exception:  # nosec B110
        pass
    return None


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="dcness-run-review", description="dcness run 사후 분석")
    p.add_argument("--run-id", help="명시 run_id")
    p.add_argument("--latest", action="store_true", help="최신 run 분석")
    p.add_argument("--list", action="store_true", help="run list 만 출력")
    p.add_argument("--repo", default=".", help="저장소 cwd (default: cwd)")
    p.add_argument("--limit", type=int, default=10, help="--list 시 최대 개수")
    p.add_argument(
        "--recurrence-threshold",
        type=int,
        default=DEFAULT_RECURRENCE_THRESHOLD,
        help="재발 개선 후보로 표면화할 동일 waste pattern 반복 임계값 (기본 3)",
    )
    p.add_argument(
        "--context-audit",
        action="store_true",
        help="run 없이 CLAUDE.md/AGENTS.md 현행화 후보만 read-only 출력",
    )
    args = p.parse_args(argv)

    repo_path = Path(args.repo).resolve()
    if args.context_audit:
        print(render_context_audit_section(repo_path))
        return 0

    sessions_root = _detect_sessions_root(repo_path)
    if not sessions_root:
        print("[run-review] sessions root 미탐지 — `.claude/harness-state/.sessions/` 부재", file=sys.stderr)
        return 2

    if args.list:
        runs = list_runs(sessions_root)[:args.limit]
        if not runs:
            print("[run-review] runs 없음")
            return 0
        for i, r in enumerate(runs, 1):
            mtime = datetime.fromtimestamp(r.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{i}. {r.name}  (sid={r.parent.parent.name}, mtime={mtime})")
        return 0

    run_dir = find_run_dir(sessions_root, args.run_id, args.latest or not args.run_id)
    if not run_dir:
        print(f"[run-review] run_dir 미탐지 (run_id={args.run_id})", file=sys.stderr)
        return 2

    report = build_report(
        run_dir,
        repo_path,
        include_recurrence=True,
        recurrence_threshold=args.recurrence_threshold,
    )
    print(render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
