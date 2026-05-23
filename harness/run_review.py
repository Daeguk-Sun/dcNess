"""run_review.py — dcness conveyor run 사후 분석 (RWHarness review skill 의 dcness 변환).

데이터 소스:
  1. `.sessions/{sid}/runs/{rid}/.steps.jsonl` — step 시퀀스 (agent/mode/enum/must_fix/prose_excerpt/ts)
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
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Reuse existing pricing util.
try:
    from harness.efficiency.analyze_sessions import price_for
except Exception:
    def price_for(_model: str) -> dict:  # type: ignore
        return {"in": 15.0, "out": 75.0, "cw5": 18.75, "cw1h": 30.0, "cr": 1.50}

# DCN-CHG-20260501-10: must_fix retroactive recompute.
# .steps.jsonl 의 must_fix 는 *기록 시점* helper regex 산출물 — DCN-CHG-20260501-09
# 이전 데이터는 단순 단어경계 매칭의 false positive 포함. parser 가 prose_full 보유 시
# 신규 negation-aware regex 로 재계산. prose_full 부재 시 jsonl fallback.
try:
    from harness.session_state import _has_positive_must_fix
except Exception:
    def _has_positive_must_fix(_prose: str) -> bool:  # type: ignore
        return False

# ── 상수 ───────────────────────────────────────────────────────────────

EXPECTED_FINAL_ENUMS = {
    "system-architect": {None: "PASS"},
    "module-architect": {None: "PASS"},
    "test-engineer": {None: "PASS"},
    "engineer": {"IMPL": "IMPL_DONE", "POLISH": "POLISH_DONE"},
    "code-validator": {None: "PASS"},
    "architecture-validator": {None: "PASS"},
    "pr-reviewer": {None: "PASS"},
    "qa": {None: None},  # qa 다양 (FUNCTIONAL_BUG / CLEANUP / etc.)
    "plan-reviewer": {None: "PASS"},
    "designer": {None: "PASS"},
    "ux-architect": {None: "UX_FLOW_READY"},  # 통일 부적합 — variant 3개
}

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

READONLY_AGENTS = {"qa", "code-validator", "architecture-validator", "pr-reviewer",
                    "plan-reviewer"}

# DCN-CHG-20260430-20: Phase 2 — per-Agent budget for THINKING_LOOP detection.
# elapsed_s: 정상 sub-agent 한 번 호출 한도 (초).
# min_output_tokens: 정상 sub-agent 가 emit 할 최소 output token (이하 = stall 의심).
EXPECTED_AGENT_BUDGETS: dict[str, dict[str, int]] = {
    "architect":       {"elapsed_s": 600, "min_output_tokens": 1500},
    "module-architect": {"elapsed_s": 600, "min_output_tokens": 1500},
    "system-architect": {"elapsed_s": 600, "min_output_tokens": 1500},
    "engineer":        {"elapsed_s": 900, "min_output_tokens": 2000},
    "test-engineer":   {"elapsed_s": 600, "min_output_tokens": 1500},
    "code-validator":  {"elapsed_s": 300, "min_output_tokens": 800},
    "architecture-validator": {"elapsed_s": 300, "min_output_tokens": 800},
    "pr-reviewer":     {"elapsed_s": 180, "min_output_tokens": 600},
    "qa":              {"elapsed_s": 300, "min_output_tokens": 600},
    "plan-reviewer":   {"elapsed_s": 300, "min_output_tokens": 1000},
    "designer":        {"elapsed_s": 600, "min_output_tokens": 1000},
    "ux-architect":    {"elapsed_s": 600, "min_output_tokens": 1000},
}

DCNESS_AGENT_NAMES = set(EXPECTED_AGENT_BUDGETS.keys())

# issue #383 — 옛 통합형 agent 이름 alias. 0.2.16 loop-procedure.md 의 bare
# `validator` 표현 학습으로 메인 Claude 가 `dcness:validator` 호출한 잔재
# (jajang 21건 trace 확인). 0.2.17 docs cleanup 이후 미래 호출은 차단됐지만
# 옛 데이터 review 회복 + backward compat 위해 정식 이름으로 흡수.
LEGACY_AGENT_ALIASES: dict[str, str] = {
    "validator": "code-validator",
}

# issue #383 B1 — window padding. step.ts = end-step 호출 시각이므로
# sub-agent TUR ts (완료 시각) 는 first_ts 보다 약간 이전. padding 없으면
# 첫 step metric 매번 누락. ±60s 여유로 jajang 실측 8s off-by-N 흡수.
WINDOW_TS_PADDING = timedelta(seconds=60)

# DCN-CHG-20260430-38: engineer self-verify echo anchor 옵션 (DCN-30-34 강제 → DCN-30-38 자율화).
# prose 끝에 *어느 한 anchor* 라도 있으면 통과. 형식 자율 + substance 의무.
# heading 라인에 검증 / verification / self-verify 단어가 *포함* 되면 매칭 (issue #249 — `## 수용 기준 검증` 같은 변형 허용).
SELF_VERIFY_ANCHORS = [
    r"^\s*#{1,6}[^\n]*검증",
    r"^\s*#{1,6}[^\n]*verification",
    r"^\s*#{1,6}[^\n]*self[-\s]?verify",
]


def _has_self_verify_anchor(prose: str) -> bool:
    """engineer prose 에 self-verify anchor 중 하나라도 있는지 (DCN-30-38)."""
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
    # issue #383 B4 — prose 본문 끝 결론 enum (PASS/LGTM/FAIL/ESCALATE).
    # 옛 enum mode 는 helper stdout 에서 enum 직접 박음. prose-only mode
    # (이슈 #284) 이후 helper sentinel = `PROSE_LOGGED` 통일 → agent prose
    # 마지막 단락 결론 (agents/code-validator.md §6 "PASS / FAIL / ESCALATE")
    # 을 표시 단계에서 추출. 부재 시 빈 문자열 (= sentinel 그대로 표시 fallback).
    conclusion_enum: str = ""


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


# issue #392 — `GoodFinding` dataclass 폐기. `detect_goods` 폐기와 정합.


@dataclass
class RunReport:
    run_id: str
    session_id: str
    run_dir: Path
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


# ── Run discovery ─────────────────────────────────────────────────────

def list_runs(sessions_root: Path) -> list[Path]:
    """`.sessions/{sid}/runs/{rid}/` 디렉토리 list (mtime 내림차순)."""
    if not sessions_root.exists():
        return []
    runs = []
    for sid_dir in sessions_root.iterdir():
        runs_dir = sid_dir / "runs"
        if not runs_dir.is_dir():
            continue
        for rid_dir in runs_dir.iterdir():
            if (rid_dir / ".steps.jsonl").exists():
                runs.append(rid_dir)
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def find_run_dir(sessions_root: Path, run_id: Optional[str], use_latest: bool) -> Optional[Path]:
    if run_id:
        for rd in list_runs(sessions_root):
            if rd.name == run_id:
                return rd
        # .steps.jsonl 없는 run 도 직접 탐색 (prose staging 실패 등 부분 완료 run)
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


# ── Step 파싱 ─────────────────────────────────────────────────────────

def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# issue #383 B4 — prose 본문 결론 enum 추출.
# agents/code-validator.md §6 등: "prose 마지막 단락에 결론 (PASS / FAIL / ESCALATE)".
# pr-reviewer 는 LGTM 도 사용. 마지막 N줄에서 단어 단위 매칭 — 부정문 (예: "FAIL 없음",
# "0 FAIL") 회피 위해 같은 줄에 부정 마커 있으면 skip.
_CONCLUSION_ENUMS: tuple[tuple[str, str], ...] = (
    # issue #383 follow-up — agent 별 결론 enum 12개 매트릭스 (agents/*.md 실측):
    #   engineer (IMPL): IMPL_DONE / IMPL_PARTIAL / TESTS_FAIL
    #   engineer (POLISH): POLISH_DONE / IMPLEMENTATION_ESCALATE
    #   test-engineer: TESTS_WRITTEN
    #   code-validator / architecture-validator / module-architect / system-architect
    #     / plan-reviewer: PASS / FAIL / ESCALATE
    #   pr-reviewer: LGTM / FAIL / ESCALATE
    #   ux-architect: UX_FLOW_DONE / UX_FLOW_ESCALATE
    #   designer: PASS
    # 우선순위 — 구체적 enum 먼저 (TESTS_FAIL 이 FAIL 보다 먼저 매칭).
    # 일반 PASS/FAIL/ESCALATE 는 마지막 fallback.
    ("LGTM", re.compile(r"\bLGTM\b")),
    # engineer IMPL
    ("IMPL_DONE", re.compile(r"\bIMPL_DONE\b")),
    ("IMPL_PARTIAL", re.compile(r"\bIMPL_PARTIAL\b")),
    ("TESTS_FAIL", re.compile(r"\bTESTS_FAIL\b")),
    # engineer POLISH
    ("POLISH_DONE", re.compile(r"\bPOLISH_DONE\b")),
    ("IMPLEMENTATION_ESCALATE", re.compile(r"\bIMPLEMENTATION_ESCALATE\b")),
    # test-engineer
    ("TESTS_WRITTEN", re.compile(r"\bTESTS_WRITTEN\b")),
    # ux-architect
    ("UX_FLOW_DONE", re.compile(r"\bUX_FLOW_DONE\b")),
    ("UX_FLOW_ESCALATE", re.compile(r"\bUX_FLOW_ESCALATE\b")),
    # 일반 (PR #361 enum 통일 — code/architecture-validator / system/module-architect
    # / plan-reviewer / pr-reviewer / designer 공통)
    ("PASS", re.compile(r"\bPASS\b")),
    ("FAIL", re.compile(r"\bFAIL\b")),
    ("ESCALATE", re.compile(r"\bESCALATE\b")),
)
# 단독 결론 (negation 검사 skip 대상) — 단어 자체가 부정 형태 가질 수 없음.
_STANDALONE_CONCLUSIONS: frozenset[str] = frozenset({
    "LGTM",
    "IMPL_DONE", "IMPL_PARTIAL",
    "POLISH_DONE", "IMPLEMENTATION_ESCALATE",
    "TESTS_WRITTEN", "TESTS_FAIL",
    "UX_FLOW_DONE", "UX_FLOW_ESCALATE",
})
_NEGATION_RE = re.compile(
    r"(없|미발견|아님|아니|불필요|"           # 한글 부정
    r"\bno\b|\bnot\b|\bzero\b|\b0\s*\b|"     # 영어 부정
    r"없음)",
    re.IGNORECASE,
)


def _extract_conclusion_enum(prose: str) -> str:
    """prose 본문 끝 ~15줄에서 positive 결론 enum 추출.

    매칭 룰:
    - 끝 15줄 (마지막 단락 가정)
    - 결론 enum 단어 매칭 + 같은 줄 부정 마커 부재
    - LGTM > PASS > FAIL > ESCALATE 우선순위 (LGTM 단독, PASS/FAIL 부정 가능)
    - 다 매칭 실패 시 빈 문자열 반환 (= 호출자가 helper sentinel 그대로 표시)
    """
    if not prose:
        return ""
    lines = prose.splitlines()
    tail = lines[-15:] if len(lines) > 15 else lines
    for label, pattern in _CONCLUSION_ENUMS:
        for line in tail:
            if pattern.search(line):
                # 단독 결론 enum (TESTS_WRITTEN / IMPL_DONE 등) 은 negation 검사 skip.
                # 단어 자체가 부정 형태 가질 수 없음 — "TESTS_WRITTEN 없음" 어색.
                if label in _STANDALONE_CONCLUSIONS:
                    return label
                # 일반 PASS/FAIL/ESCALATE — 같은 줄에 부정 마커 있으면 skip
                if _NEGATION_RE.search(line):
                    continue
                return label
    return ""


def parse_steps(run_dir: Path) -> list[StepRecord]:
    steps: list[StepRecord] = []
    jsonl = run_dir / ".steps.jsonl"
    if not jsonl.exists():
        return steps
    raw = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    for idx, rec in enumerate(raw):
        agent = rec.get("agent", "?")
        # issue #383 B2 — step.agent 도 alias normalize. jajang `.steps.jsonl`
        # 의 `validator` (0.2.16 잔재) 를 `code-validator` 로 흡수해야
        # assign_invocations_to_steps 의 `inv.agent != step.agent` 비교가
        # 정합 일치 (invocation 측은 _normalize_agent_type 에서 이미 normalize).
        agent = LEGACY_AGENT_ALIASES.get(agent, agent)
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

        # legacy fallback: prose_file 없는 옛 records → outer <agent>[-mode].md
        if not prose_full:
            suffix = f"{agent}-{mode}.md" if mode else f"{agent}.md"
            legacy = run_dir / suffix
            if legacy.exists():
                try:
                    prose_full = legacy.read_text(encoding="utf-8")
                except OSError:
                    pass

        if prose_full:
            must_fix = _has_positive_must_fix(prose_full)
        else:
            must_fix = bool(rec.get("must_fix"))

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
    except Exception:
        pass
    return hits


def detect_wastes(
    steps: list[StepRecord],
    invocations: Optional[list[dict]] = None,
    repo_path: Optional[Path] = None,
    window: Optional[tuple] = None,
    run_dir: Optional[Path] = None,
) -> list[WasteFinding]:
    # run_dir 신규 (DCN-CHG-20260523, #484 Case 1) — agent-trace.jsonl 기반
    # TOOL_REPEAT_HIGH 검출용. None 이면 trace 검사 skip.
    findings: list[WasteFinding] = []

    # RETRY_SAME_FAIL — 연속 동일 FAIL enum
    # 이슈 #302 #1: prose-only mode (#284) 정착 후 PROSE_LOGGED 가 표준 advance enum.
    # 또한 같은 (agent, mode) 가 N task 순회 정상 호출 (예: architect MODULE_PLAN × 4)
    # 시 동일 enum 반복은 *retry 가 아닌 정상 호출* — prose 내용이 다르면 다른 step.
    ADVANCE_ENUMS = {
        "PASS",  # 8 agent enum 통일 (code-validator / architecture-validator /
                 # plan-reviewer / system-architect / module-architect /
                 # test-engineer / pr-reviewer / designer 공통)
        "IMPL_DONE", "POLISH_DONE",  # engineer 분기 enum (통일 부적합)
        "PRODUCT_PLAN_READY",  # product-planner workflow enum
        "UX_FLOW_READY", "UX_FLOW_PATCHED", "UX_REFINE_READY",  # ux-architect 분기
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

    # issue #387 — MISSING_CONCLUSION_ENUM. engineer prose 끝 결론 enum (IMPL_DONE
    # / IMPL_PARTIAL / SPEC_GAP_FOUND / TESTS_FAIL / IMPLEMENTATION_ESCALATE
    # / POLISH_DONE) 부재 검출. agents/engineer.md §21~32 명시 강제.
    # validator/architect 류는 PR #361 enum 통일로 자율 영역 — 본 패턴 미적용.
    for s in steps:
        if s.agent != "engineer":
            continue
        if not s.prose_full:
            continue  # prose 부재 시 검사 불가
        if s.conclusion_enum:
            continue  # 결론 enum 정상 박힘
        findings.append(WasteFinding(
            pattern="MISSING_CONCLUSION_ENUM",
            severity="MEDIUM",
            step_idx=s.idx,
            agent=s.agent,
            detail=(
                f"engineer step {s.idx} prose 끝 결론 enum 부재 — "
                "agents/engineer.md §21~32 명시 의무 위반 "
                "(IMPL_DONE / IMPL_PARTIAL / SPEC_GAP_FOUND / TESTS_FAIL / "
                "IMPLEMENTATION_ESCALATE / POLISH_DONE 중 1)"
            ),
            fix=(
                "engineer 재호출 시 prompt 에 결론 enum 강제 의무 명시 또는 "
                "메인 Claude 가 prose routing 결정 시 enum 부재 인지 + 재호출"
            ),
        ))

    # issue #392 — ECHO_VIOLATION / PLACEHOLDER_LEAK 폐기.
    # 사유: agent 자율 영역 침해. ECHO_VIOLATION (prose <5줄) = "agent 자율 침해",
    # PLACEHOLDER_LEAK = "약속-실측 검사" — sub_eval.py:6~10 정신 위반.

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

    # MUST_FIX_GHOST — must_fix=true 이후 다음 step 진행
    for i, s in enumerate(steps):
        if s.must_fix and i + 1 < len(steps):
            findings.append(WasteFinding(
                pattern="MUST_FIX_GHOST",
                severity="HIGH",
                step_idx=i,
                agent=s.agent,
                detail=f"step {i} ({s.agent}) MUST_FIX 발견됐는데 step {i+1} 진행 — 멈춤 위반",
                fix="commands/{skill}.md caveat 멈춤 룰 강화",
            ))

    # issue #383 B3 — MUST_FIX_LEAK. 마지막 step 의 must_fix=True (= caveat 신호)
    # 는 MUST_FIX_GHOST 룰이 *다음 step 없음* 으로 skip → wastes 비어있는
    # 회귀 발생 (jajang run-459cce99 pr-reviewer 케이스). 사용자에게 caveat
    # 통지 누락 회피 위해 wastes 1+ 박아 회귀 차단.
    last = steps[-1] if steps else None
    if last and last.must_fix:
        findings.append(WasteFinding(
            pattern="MUST_FIX_LEAK",
            severity="HIGH",
            step_idx=len(steps) - 1,
            agent=last.agent,
            detail=f"마지막 step ({last.agent}) must_fix=True — caveat 통지 의무",
            fix="loop-procedure.md §5.4 7b 분기 — 사용자 위임 + 메모리 candidate emit",
        ))

    # SPEC_GAP_LOOP — architect SPEC_GAP cycle 한도 초과
    spec_gap_count = sum(1 for s in steps if s.agent == "architect" and s.mode == "SPEC_GAP")
    if spec_gap_count > 2:
        findings.append(WasteFinding(
            pattern="SPEC_GAP_LOOP",
            severity="MEDIUM",
            step_idx=-1,
            agent="architect",
            detail=f"architect SPEC_GAP {spec_gap_count}회 — cycle 한도 2 초과",
            fix="impl batch 자체 보강 또는 product-planner escalate",
        ))

    # INFRA_READ — prose 안 인프라 경로 흔적
    for s in steps:
        for path in INFRA_PATH_PATTERNS:
            if path in s.prose_full:
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

    # END_STEP_SKIP (DCN-CHG-20260430-37) — sub-agent invocation > .steps.jsonl row.
    # 메인 distract → end-step 호출 skip → .steps.jsonl 누락. DCN-30-25 STEP COUNT WARN /
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

    # issue #484 Case 1 — agent-trace 기반 TOOL_REPEAT_HIGH (동일 input 반복).
    if run_dir is not None:
        findings.extend(_detect_tool_repeat_findings(steps, run_dir))

    return findings


def _detect_tool_repeat_findings(
    steps: list[StepRecord], run_dir: Path
) -> list[WasteFinding]:
    """agent-trace.jsonl 기반 동일 (tool, input) ≥ N 회 반복 finding.

    issue #484 Case 1 (DCN-CHG-20260523): jajang run-545513a1 build-worker 가
    같은 Bash command 6회 반복 호출 + Bash 40회 폭증한 안티패턴을 review heuristic
    이 못 잡아 "잘못한 점 — 없음 ✅" 통과시킨 회귀 차단. PostToolUse hook 의
    감시자 신호와 동일 영역 — review 와 hook 의 단일 SSOT 통합.

    임계:
    - Bash: 같은 input ≥ 5 회
    - Read: 같은 input ≥ 4 회 (정상 단순 재read 2~3 회 면제)
    - 기타 도구: ≥ 5 회

    step 별 윈도우 (전 step end ~ 현 step end) 적용. input 200자 초과 truncate.
    """
    from collections import Counter

    findings: list[WasteFinding] = []
    trace_path = run_dir / "agent-trace.jsonl"
    if not trace_path.exists():
        return findings

    entries: list[dict] = []
    try:
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return findings

    pre_entries = [e for e in entries if e.get("phase") == "pre"]
    if not pre_entries:
        return findings

    thresholds = {"Bash": 5, "Read": 4}
    default_threshold = 5

    for i, s in enumerate(steps):
        start_ts = steps[i - 1].ts if i > 0 else ""
        end_ts = s.ts
        window_entries = [
            e for e in pre_entries
            if (not start_ts or e.get("ts", "") > start_ts)
            and (not end_ts or e.get("ts", "") <= end_ts)
        ]
        if not window_entries:
            continue
        key_count: Counter = Counter()
        for e in window_entries:
            tool = e.get("tool", "?")
            inp = e.get("input", "")
            if not isinstance(inp, str) or not inp:
                continue
            key_count[(tool, inp[:200])] += 1
        for (tool, inp), cnt in sorted(
            key_count.items(), key=lambda kv: (-kv[1], kv[0][0])
        ):
            threshold = thresholds.get(tool, default_threshold)
            if cnt < threshold:
                continue
            inp_disp = inp[:80].replace("\n", " ") + ("…" if len(inp) > 80 else "")
            findings.append(WasteFinding(
                pattern="TOOL_REPEAT_HIGH",
                severity="MEDIUM",
                step_idx=i,
                agent=s.agent,
                detail=(
                    f"step {i} ({s.agent}) {tool} 동일 input {cnt}회 반복 "
                    f"(임계 {threshold}회): `{inp_disp}`"
                ),
                fix=(
                    f"sub-agent prompt 에 동일 {tool} 호출 반복 금지 가드 추가 "
                    f"또는 작업 분해 ({tool} 결과 활용 권장)"
                ),
            ))
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
                   f"jajang 실측 임계 — context overflow / IMPL_PARTIAL 위험)",
        ))

    return notes


# issue #392 — `detect_goods` 함수 + 5 good patterns 전체 폐기.
# 사유: dcness 정신 정합 X — orchestration.md §0 "임계값 hardcode 금지 + 자율 친화".
# jajang 실측: loop-insights 100% PROSE_ECHO_OK (baseline) = 학습 가치 0.
# 본 함수의 5 patterns (ENUM_CLEAN / PROSE_ECHO_OK / DDD_PHASE_A / DEPENDENCY_CAUSAL /
# EXTERNAL_VERIFIED_PRESENT) 모두 폐기. 잘한점 섹션은 review.md render 에서도 제거.
# 메인 자율 평가는 insight CLI (PR3) 로 대체.


# ── Per-Agent invocation extraction (DCN-CHG-20260430-20, Phase 2) ────


def _normalize_agent_type(agent_type: Optional[str]) -> Optional[str]:
    """`dcness:architect:system-design` → `architect`. None / 비-dcness → 원형 그대로.

    issue #383: LEGACY_AGENT_ALIASES 도 적용 — 옛 `dcness:validator` → `code-validator`.
    """
    if not agent_type:
        return None
    if agent_type.startswith("dcness:"):
        parts = agent_type.split(":")
        normalized = parts[1] if len(parts) > 1 else agent_type
    else:
        normalized = agent_type
    return LEGACY_AGENT_ALIASES.get(normalized, normalized)


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
    steps_file = run_dir / ".steps.jsonl"
    if not steps_file.exists():
        return (0.0, 0, 0)

    raw = []
    for line in steps_file.read_text(encoding="utf-8").splitlines():
        try:
            raw.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not raw:
        return (0.0, 0, 0)

    first_ts = _parse_iso(raw[0].get("ts", ""))
    last_ts = _parse_iso(raw[-1].get("ts", ""))
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

def _build_tool_histogram_table(report: RunReport) -> list[str]:
    """issue #394 — agent-trace.jsonl 집계 → step 별 도구 사용 분포 표.

    각 step 의 prose timestamp 윈도우 안 agent-trace 의 PreToolUse pre entry 만
    카운트. raw 데이터 — 임계 X. 메인이 보고 자율 판단.

    return: markdown table line 리스트. 빈 trace 시 빈 리스트.
    """
    if not report.steps:
        return []

    from harness.agent_trace import read_all as _trace_read

    try:
        trace = _trace_read(
            report.session_id, report.run_id,
            base_dir=report.run_dir.parent.parent.parent.parent,
        )
    except Exception:
        return []
    if not trace:
        return []

    # step 별 시작/종료 ts 윈도우
    pre_entries = [e for e in trace if e.get("phase") == "pre"]

    lines: list[str] = []
    lines.append("| step | agent | mode | Read | Write | Edit | Bash | Glob | Grep | 기타 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    for i, s in enumerate(report.steps):
        # #415 — step.ts = end-step 시각. sub-agent 도구 호출 ts < step.ts.
        # 윈도우 = 이전 step end ~ 현재 step end (i=0 은 빈 string = 모두 포함).
        start_ts = report.steps[i - 1].ts if i > 0 else ""
        end_ts = s.ts

        from collections import Counter
        hist: Counter = Counter()
        for e in pre_entries:
            e_ts = e.get("ts", "")
            if start_ts and e_ts <= start_ts:
                continue
            if e_ts > end_ts:
                continue
            tool = e.get("tool", "?")
            hist[tool] += 1

        # 표시 안 함 = 빈 step
        if not hist:
            continue

        def _g(k: str) -> str:
            return str(hist.get(k, 0)) if hist.get(k, 0) else "-"

        common = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
        other = sum(v for k, v in hist.items() if k not in common)
        other_str = str(other) if other else "-"

        lines.append(
            f"| {s.idx} | {s.agent} | {s.mode or '-'} | "
            f"{_g('Read')} | {_g('Write')} | {_g('Edit')} | "
            f"{_g('Bash')} | {_g('Glob')} | {_g('Grep')} | {other_str} |"
        )

    return lines if len(lines) > 2 else []


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

    # 호출 흐름 — issue #383 B4: prose 결론 enum 우선 표시.
    # helper sentinel `PROSE_LOGGED` 는 prose-only mode 신호일 뿐 사용자 가독성 0.
    # parse_steps 가 prose 본문 끝 결론 (PASS/LGTM/FAIL/ESCALATE) 추출 → 우선.
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
        line_count = len([l for l in (s.prose_full or s.prose_excerpt).splitlines() if l.strip()])
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

    # issue #394 — 도구 사용 분포 표 (agent-trace.jsonl 집계, raw)
    tool_table = _build_tool_histogram_table(report)
    if tool_table:
        lines.append("## 🔧 도구 사용 분포 (raw — 임계 X)")
        lines.extend(tool_table)
        lines.append("")

    # issue #394 — 측정 noted (TOOL_USE_OVERFLOW / THINKING_LOOP, severity 없음)
    if report.notes:
        lines.append("## ⚠️ 측정 noted (임계 도달 — 결정 X, 메인 자율 판단)")
        for n in report.notes:
            lines.append(f"- step {n.step_idx} {n.agent} `{n.pattern}` — {n.detail}")
        lines.append("")

    # issue #396 — 메인 인사이트 prompt (REVIEW_READY 시 메인 시야 진입)
    # 메인 Claude 가 review.md 본 후 자연어 한 줄 평가 박는 매커니즘 안내.
    # 미박음 = noop (자율 영역, 강제 X).

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

    # issue #396 — 메인 인사이트 prompt (review.md 끝 임베드)
    # 메인 Claude 가 보고 자율 평가 박음. agent+mode 선택 자율.
    lines.append("## 📝 메인 인사이트 (1줄 자율 평가)")
    lines.append("")
    lines.append("이번 run 의 *구체적 학습 1줄* (다음 run 같은 실수 회피용) — 박을지 메인 자율:")
    lines.append("")
    lines.append("```bash")
    lines.append("$HELPER insight <agent>[-<mode>] \"<자연어 한 줄>\"")
    lines.append("# 예: $HELPER insight engineer-IMPL \"🚨 stub 파일로 TDD guard 우회 시도 — 절대 반복 X\"")
    lines.append("```")
    lines.append("")
    lines.append("- agent+mode 별 `.claude/loop-insights/<agent>[-<mode>].md` 에 누적 (FIFO 10 cap)")
    lines.append("- 다음 run begin-step 시 자동 inject — 같은 agent 호출 시 sub-agent prompt 끝에 박힘")
    lines.append("- 미박음 = noop (자율, 강제 X)")
    lines.append("- **형식 가이드**: *실수 환기* 형태로만 (예: `🚨 X 실수 — 반복 X`). 잘 됐던 케이스 누적은 학습 가치 0 (issue #392 실측)")
    lines.append("")

    return "\n".join(lines)


# ── 실행 ──────────────────────────────────────────────────────────────

def build_report(run_dir: Path, repo_path: Path) -> RunReport:
    steps = parse_steps(run_dir)

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
            # jajang run-459cce99 실측 — test-engineer TUR 02:40:18 vs first_ts 02:40:26 (8s diff).
            window = (first_ts - WINDOW_TS_PADDING, last_ts + WINDOW_TS_PADDING)
            invocations = extract_agent_invocations(repo_path, window)
            assign_invocations_to_steps(steps, invocations)

    # DCN-CHG-20260430-37: detect_wastes 에 invocations + repo_path + window 전달
    # (END_STEP_SKIP / MAIN_SED_MISDIAGNOSIS run-level 패턴 검출 위해).
    # DCN-CHG-20260523 (#484 Case 1): run_dir 추가 — agent-trace 기반 TOOL_REPEAT_HIGH.
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
    final_clean = (final_enum and not has_must_fix and not has_ambiguous
                   and len([w for w in wastes if w.severity == "HIGH"]) == 0)

    sid = run_dir.parent.parent.name
    return RunReport(
        run_id=run_dir.name,
        session_id=sid,
        run_dir=run_dir,
        steps=steps,
        wastes=wastes,
        notes=notes,
        total_cost_usd=cost,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        elapsed_s=elapsed,
        final_enum=final_enum,
        final_clean=final_clean,
    )


def _detect_sessions_root(cwd: Path) -> Optional[Path]:
    """`.claude/harness-state/.sessions/` 위치 자동 탐지 (현재 dir + .git common parent)."""
    cur = cwd / ".claude" / "harness-state" / ".sessions"
    if cur.exists():
        return cur
    # worktree fallback — git common-dir
    try:
        import subprocess
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                            cwd=str(cwd), capture_output=True, text=True, check=False)
        if r.returncode == 0:
            common = Path(r.stdout.strip())
            cand = common.parent / ".claude" / "harness-state" / ".sessions"
            if cand.exists():
                return cand
    except Exception:
        pass
    return None


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="dcness-run-review", description="dcness run 사후 분석")
    p.add_argument("--run-id", help="명시 run_id")
    p.add_argument("--latest", action="store_true", help="최신 run 분석")
    p.add_argument("--list", action="store_true", help="run list 만 출력")
    p.add_argument("--repo", default=".", help="저장소 cwd (default: cwd)")
    p.add_argument("--limit", type=int, default=10, help="--list 시 최대 개수")
    args = p.parse_args(argv)

    repo_path = Path(args.repo).resolve()
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

    report = build_report(run_dir, repo_path)
    print(render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
