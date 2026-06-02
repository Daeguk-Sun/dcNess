"""agent_boundary.py — sub-agent 경로 접근 강제 (`docs/plugin/handoff-matrix.md` §4 SSOT).

본 모듈은 PreToolUse(Edit/Write/Read/Bash) 훅이 호출하여 활성 sub-agent 의 path
접근을 차단한다. handoff-matrix.md §4.1~§4.4 의 spec 을 코드로 강제 (DCN-CHG-20260501-01).

핵심 룰 (handoff-matrix.md §4 정합):
    §4.1 ALLOW_MATRIX — agent 별 Write 허용 path
    §4.2 READ_DENY_MATRIX — agent 별 Read 금지 path
    §4.3 DCNESS_INFRA_PATTERNS — 전 agent 공통 차단 (인프라 보호)
    §4.4 is_infra_project() — dcness 자체 작업 시 §4.1~§4.3 해제

활성 sub-agent 판정: live.json.active_agent (catastrophic-gate 가 PreToolUse Agent
훅에서 기록, post-agent-clear 가 PostToolUse Agent 훅에서 해제).

규약:
    - 메인 Claude (active_agent 미설정) = 통과 — governance Document Sync 가 별도 보호.
    - 미정의 agent_type = 통과 (false positive 회피).
    - is_infra_project() True = 모든 룰 해제 (dcness 자체 SSOT 편집 가능해야).
    - opt-out 마커 `.no-dcness-guard` (cwd) 존재 = 모든 룰 해제.

검사 결과:
    None = allow
    str  = block reason (stderr 메시지 + exit 1)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional


__all__ = [
    "DCNESS_INFRA_PATTERNS",
    "ALLOW_MATRIX",
    "READ_DENY_MATRIX",
    "is_infra_project",
    "is_opt_out",
    "check_write_allowed",
    "check_read_allowed",
    "extract_bash_paths",
]


# ── §4.3 — 인프라 패턴 (전 agent 공통 차단) ──────────────────────────
# handoff-matrix.md:223 spec 그대로 + dcness 정합 보강.
DCNESS_INFRA_PATTERNS: tuple[str, ...] = (
    r'(^|/)\.claude/',
    r'(^|/)hooks/',
    r'(^|/)harness/(signal_io|hooks|session_state|agent_boundary)\.py$',
    r'(^|/)docs/plugin/orchestration\.md$',
    r'(^|/)docs/plugin/handoff-matrix\.md$',
    r'(^|/)docs/plugin/loop-procedure\.md$',
    r'(^|/)docs/internal/governance\.md$',
    r'(^|/)scripts/(check_document_sync|check_task_id|setup_branch_protection|analyze_metrics)\.mjs$',
    r'^CLAUDE\.md$',
)


# ── §4.1 — ALLOW_MATRIX (agent 별 Write 허용) ─────────────────────────
# handoff-matrix.md:200~209 정합. RWHarness agent-boundary.py:48~84 와 동일 패턴.
ALLOW_MATRIX: dict[str, tuple[str, ...]] = {
    "engineer": (
        r'(^|/)src/',
        r'(^|/)apps/[^/]+/src/',
        r'(^|/)apps/[^/]+/app/',
        r'(^|/)apps/[^/]+/alembic/',
        r'(^|/)packages/[^/]+/src/',
        r'(^|/)apps/[^/]+/[^/]+\.toml$',
        r'(^|/)apps/[^/]+/[^/]+\.cfg$',
    ),
    "architect": (
        r'(^|/)docs/',
        r'(^|/)backlog\.md$',
        r'(^|/)trd\.md$',
    ),
    # module-architect / system-architect — architect 변종. 키 명시 필수.
    # 키 부재 시 "미정의 agent = 통과" fallback 으로 빠져 ALLOW 강제 자체가 무력화.
    "module-architect": (
        r'(^|/)docs/',
        r'(^|/)backlog\.md$',
        r'(^|/)trd\.md$',
    ),
    "system-architect": (
        r'(^|/)docs/',
        r'(^|/)backlog\.md$',
        r'(^|/)trd\.md$',
    ),
    "designer": (
        r'(^|/)design-variants/',
        r'(^|/)docs/ui-spec',
    ),
    "test-engineer": (
        r'(^|/)src/__tests__/',
        r'(^|/)src/.*\.test\.[jt]sx?$',
        r'(^|/)src/.*\.spec\.[jt]sx?$',
        r'(^|/)apps/[^/]+/tests/',
        r'(^|/)apps/[^/]+/src/__tests__/',
        r'(^|/)apps/[^/]+/src/.*\.test\.[jt]sx?$',
        r'(^|/)apps/[^/]+/src/.*\.spec\.[jt]sx?$',
        r'(^|/)packages/[^/]+/src/__tests__/',
    ),
    "ux-architect": (
        r'(^|/)docs/ux-flow\.md$',
    ),
    # 판정 전용 agent — Write 0.
    "qa": (),
    "code-validator": (),
    "architecture-validator": (),
    "pr-reviewer": (),
    "plan-reviewer": (),
}


# ── §4.2 — READ_DENY_MATRIX (agent 별 Read 금지) ──────────────────────
READ_DENY_MATRIX: dict[str, tuple[str, ...]] = {
    "designer": (
        r'(^|/)src/',
    ),
    "test-engineer": (
        # impl 외 src 읽기 금지 — domain 문서 격리. 실 적용은 후속 강화.
    ),
    "plan-reviewer": (
        r'(^|/)src/',
        r'(^|/)docs/impl/',
        r'(^|/)trd\.md$',
    ),
}


# ── §4.4 — is_infra_project() 4 OR 신호 ──────────────────────────────
def _is_dcness_self_repo(cwd: Path) -> bool:
    """cwd 또는 그 상위에 dcness self repo 마커가 실재하나.

    마커 = `.claude-plugin/plugin.json` 의 `name == "dcness"`.
    배포된 plugin 의 plugin.json 은 plugin cache 에만 있고 *사용자 repo 에는 없으므로*,
    이 마커가 cwd 조상에 실재한다는 것은 dcness self 저장소에서 작업 중이라는 뜻이다.
    (옛 개인 절대경로 하드코딩 whitelist 대체 — 이슈 #523)
    """
    try:
        cur = cwd.resolve()
    except (OSError, RuntimeError):
        return False
    for d in (cur, *cur.parents):
        manifest = d / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return False
            return data.get("name") == "dcness"
    return False


def is_infra_project(
    cwd: Optional[Path] = None,
    *,
    env: Optional[dict] = None,
    home: Optional[Path] = None,
) -> bool:
    """4 OR 신호 — handoff-matrix.md §4.4.

    1. DCNESS_INFRA=1 환경변수
    2. 마커 파일 ~/.claude/.dcness-infra 존재
    3. CLAUDE_PLUGIN_ROOT 환경변수 non-empty (dcness 개발 모드)
    4. cwd 조상에 dcness self repo 마커 (.claude-plugin/plugin.json name=dcness) 실재
    """
    e = env if env is not None else os.environ
    if e.get("DCNESS_INFRA") == "1":
        return True
    if e.get("CLAUDE_PLUGIN_ROOT"):
        return True
    h = home if home is not None else Path.home()
    if (h / ".claude" / ".dcness-infra").exists():
        return True
    if cwd is None:
        cwd = Path.cwd()
    return _is_dcness_self_repo(cwd)


def is_opt_out(cwd: Optional[Path] = None) -> bool:
    """`.no-dcness-guard` 마커 — 사용자 임시 우회 (RWHarness `.no-harness` 정합)."""
    if cwd is None:
        cwd = Path.cwd()
    return (cwd / ".no-dcness-guard").exists()


# ── path 정규화 ───────────────────────────────────────────────────────


def _normalize(file_path: str, cwd: Optional[Path] = None) -> str:
    """절대 path → cwd 상대 path. 외부 path 는 그대로 반환."""
    if cwd is None:
        cwd = Path.cwd()
    try:
        p = Path(file_path)
        if p.is_absolute():
            try:
                return str(p.resolve().relative_to(cwd.resolve()))
            except ValueError:
                # cwd 밖 — 그대로 반환 (외부 path 는 패턴 매칭에서 잡거나 통과)
                return str(p)
        return file_path
    except (OSError, ValueError):
        return file_path


def _matches_any(path: str, patterns: Iterable[str]) -> Optional[str]:
    for pat in patterns:
        if re.search(pat, path):
            return pat
    return None


# ── 검사 ─────────────────────────────────────────────────────────────


def check_write_allowed(
    agent: Optional[str],
    file_path: str,
    *,
    cwd: Optional[Path] = None,
) -> Optional[str]:
    """Write/Edit 검사 — block reason str / None=allow.

    메인 Claude (agent=None / 빈 문자열) = 통과. 메인 거버넌스는 Document Sync 가 강제.
    is_infra_project() True = 통과 — dcness 자체 SSOT 편집.
    `.no-dcness-guard` 마커 = 통과.
    """
    if not agent:
        return None
    if is_infra_project(cwd):
        return None
    if is_opt_out(cwd):
        return None

    norm = _normalize(file_path, cwd)

    # 1. INFRA pattern → 모든 agent 차단.
    matched = _matches_any(norm, DCNESS_INFRA_PATTERNS)
    if matched:
        return f"인프라 path 보호: matched `{matched}` (handoff-matrix.md §4.3)"

    # 2. ALLOW_MATRIX 미매칭 → 차단.
    allowed = ALLOW_MATRIX.get(agent)
    if allowed is None:
        # 미정의 agent — false positive 회피로 통과.
        return None
    if not _matches_any(norm, allowed):
        return (
            f"{agent} ALLOW_MATRIX 미매칭: `{norm}` "
            f"(handoff-matrix.md §4.1 — 허용 = {list(allowed)})"
        )
    return None


def check_read_allowed(
    agent: Optional[str],
    file_path: str,
    *,
    cwd: Optional[Path] = None,
) -> Optional[str]:
    """Read 검사 — block reason str / None=allow.

    메인 = 통과. is_infra_project = 통과. opt-out = 통과.
    INFRA pattern = 모든 sub-agent 차단 (인프라 누설 방지).
    READ_DENY_MATRIX = agent 별 추가 차단.
    """
    if not agent:
        return None
    if is_infra_project(cwd):
        return None
    if is_opt_out(cwd):
        return None

    norm = _normalize(file_path, cwd)

    matched = _matches_any(norm, DCNESS_INFRA_PATTERNS)
    if matched:
        return f"인프라 path 읽기 금지: matched `{matched}` (handoff-matrix.md §4.3)"

    deny = READ_DENY_MATRIX.get(agent, ())
    matched = _matches_any(norm, deny)
    if matched:
        return (
            f"{agent} READ_DENY_MATRIX 매칭: `{norm}` "
            f"(handoff-matrix.md §4.2 matched `{matched}`)"
        )
    return None


# ── Bash heuristic ────────────────────────────────────────────────────

# v1: 명시적 위반 패턴 (sed -i / awk -i / cp / mv / rm / 리다이렉션) 만 잡는다.
# 정밀 path 추출 X — false negative 우선 (false positive 회피).
_BASH_WRITE_INDICATORS: tuple[str, ...] = (
    r'\bsed\b\s+(?:[-]\w*i\w*|--in-place)',
    r'\bawk\b\s+(?:[-]\w*i\w*|--in-place)',
    r'\bperl\b\s+[-]\w*i',
    r'\b(?:cp|mv|rm)\b\s+',
    r'>\s*\S',     # redirect (writing)
    r'>>\s*\S',    # append redirect
    r'\btee\b',
)


def extract_bash_paths(command: str) -> list[str]:
    """Bash command 안의 의심 path 토큰 추출 (v1: 보수적).

    write 지표 (sed -i / cp / mv / rm / >) 가 보일 때만 토큰 분해 후
    `/` 또는 `.md`/`.py`/`.json`/`.sh` 확장자 포함 토큰을 path 후보로 반환.
    indicator 없으면 빈 list — false positive 회피.
    """
    if not any(re.search(ind, command) for ind in _BASH_WRITE_INDICATORS):
        return []
    # 토큰화 — quote 단순 처리.
    tokens = re.findall(r"[\"'][^\"']+[\"']|\S+", command)
    paths: list[str] = []
    for t in tokens:
        t = t.strip("\"'")
        if not t or t.startswith("-"):
            continue
        # path 후보 — `/` 포함 또는 알려진 확장자.
        if "/" in t or re.search(r"\.(md|py|json|sh|mjs|ts|tsx|js|jsx)$", t):
            paths.append(t)
    return paths
