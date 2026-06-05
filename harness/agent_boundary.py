"""agent_boundary.py — sub-agent 경로 접근 강제 (권한 경계 코드 SSOT — 본 모듈이 진본).

본 모듈은 PreToolUse(Edit/Write/Read/Bash) 훅이 호출하여 활성 sub-agent 의 path
접근을 차단한다. 권한 경계 spec 을 코드로 강제 (DCN-CHG-20260501-01). 사람용 일람 =
각 skill 의 `<skill>-routing.md` (적용 모드) + 각 `agents/<agent>.md` `## 권한 경계`.

핵심 룰:
    ALLOW_MATRIX — agent 별 Write 허용 path
    READ_DENY_MATRIX — agent 별 Read 금지 path
    DCNESS_INFRA_PATTERNS — 전 agent 공통 차단 (인프라 보호)
    is_infra_project() — dcness 자체 작업 시 위 룰 전부 해제

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
    "check_bash_mutation",
    "check_github_mcp_mutation",
]


# ── 인프라 패턴 (전 agent 공통 차단) ──────────────────────────
# RWHarness HARNESS_INFRA_PATTERNS 계열 + dcness 정합 보강.
DCNESS_INFRA_PATTERNS: tuple[str, ...] = (
    r'(^|/)\.claude/',
    r'(^|/)hooks/',
    r'(^|/)harness/(signal_io|hooks|session_state|agent_boundary)\.py$',
    r'(^|/)skills/[^/]+/[^/]+-routing\.md$',
    r'(^|/)docs/plugin/loop-procedure\.md$',
    r'(^|/)docs/internal/governance\.md$',
    r'(^|/)scripts/(check_document_sync|check_task_id|setup_branch_protection)\.mjs$',
    r'^CLAUDE\.md$',
)


# ── run_dir prose carve-out (#597 커밋4) ──────────────────────────────
# build-worker 의 `<run_dir>/build-{test,impl,validate}.md` self-write 만 보존
# (`agents/build-worker.md` 권한 경계). run_dir 는 INFRA 패턴 `(^|/)\.claude/` 에
# 걸리고, build-worker 가 ALLOW_MATRIX 에 등재된 순간 ALLOW 미매칭으로도 막힌다.
# → INFRA / ALLOW_MATRIX 검사보다 *먼저*, build-worker + build-*.md 만 좁게 허용한다.
#
# 🔴 반드시 (agent == build-worker) AND (파일명 = build-{test,impl,validate}.md) 둘 다 좁힌다.
#    넓게(임의 agent, 임의 .md) 열면 engineer 같은 agent 가 run_dir 에 module-architect.md /
#    code-validator.md / architecture-validator.md 를 `PASS` 로 *위조* → `_has_pass` 가 신뢰 →
#    catastrophic gate (pr-reviewer / engineer / module-architect 게이트) 우회 (codex review P1). build-* 파일명은 어떤
#    gate 도 신뢰하지 않으므로 forge 불가.
RUN_DIR_PROSE_ALLOW: tuple[str, ...] = (
    r'(^|/)\.claude/harness-state/\.sessions/[^/]+/runs/[^/]+/build-(test|impl|validate)\.md$',
)


# ── ALLOW_MATRIX (agent 별 Write 허용) ─────────────────────────
# RWHarness agent-boundary.py:48~84 와 동일 패턴.
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
    # tech-reviewer — PRD 기술 선행 검토 산출물만 (agents/tech-reviewer.md 권한 경계).
    "tech-reviewer": (
        r'(^|/)docs/tech-review\.md$',
        r'(^|/)docs/tech-review/',
    ),
    # 판정 전용 agent — Write 0.
    "qa": (),
    "code-validator": (),
    "architecture-validator": (),
    "pr-reviewer": (),
    "plan-reviewer": (),
}

# build-worker — engineer ∪ test-engineer (agents/build-worker.md 권한 경계).
# 합집합으로 정의해 engineer / test-engineer 패턴 변경 시 자동 동기화 (drift 방지).
# 키 부재 시 "미정의 agent = 통과" fallback 으로 빠져 /impl-loop 핵심 mutation agent 의
# 경계가 무력화되던 결함(#597) 수정. (run_dir prose self-write 는 RUN_DIR_PROSE_ALLOW carve-out.)
ALLOW_MATRIX["build-worker"] = ALLOW_MATRIX["engineer"] + ALLOW_MATRIX["test-engineer"]


# ── READ_DENY_MATRIX (agent 별 Read 금지) ──────────────────────
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


# ── is_infra_project() 3 OR 신호 ──────────────────────────────
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
    """3 OR 신호 — 인프라 프로젝트 판정.

    1. DCNESS_INFRA=1 환경변수
    2. 마커 파일 ~/.claude/.dcness-infra 존재
    3. cwd 조상에 dcness self repo 마커 (.claude-plugin/plugin.json name=dcness) 실재

    ⚠️ CLAUDE_PLUGIN_ROOT 는 **신호에서 제외** (#597 P0-2). 이 env 는 *모든* plugin hook
    실행 시 CC 가 자동 set 하므로, 외부 활성 프로젝트의 sub-agent 도 항상 가지고 있다.
    이를 infra 신호로 쓰면 file-guard 가 외부 프로젝트서 전면 무력화된다. dcness self
    저장소는 신호 3(self repo 마커 조상 탐색)으로 충분히 식별된다.
    """
    e = env if env is not None else os.environ
    if e.get("DCNESS_INFRA") == "1":
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

    # 0. run_dir prose carve-out — build-worker 의 build-{test,impl,validate}.md self-write 한정.
    #    agent + 파일명 둘 다 좁혀 PASS 마커 위조를 차단 (codex P1). INFRA/ALLOW 검사보다 먼저.
    if agent == "build-worker" and _matches_any(norm, RUN_DIR_PROSE_ALLOW):
        return None

    # 1. INFRA pattern → 모든 agent 차단.
    matched = _matches_any(norm, DCNESS_INFRA_PATTERNS)
    if matched:
        return f"인프라 path 보호: matched `{matched}` (DCNESS_INFRA_PATTERNS)"

    # 2. ALLOW_MATRIX 미매칭 → 차단.
    allowed = ALLOW_MATRIX.get(agent)
    if allowed is None:
        # 미정의 agent — false positive 회피로 통과.
        return None
    if not _matches_any(norm, allowed):
        return (
            f"{agent} ALLOW_MATRIX 미매칭: `{norm}` "
            f"(ALLOW_MATRIX — 허용 = {list(allowed)})"
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
        return f"인프라 path 읽기 금지: matched `{matched}` (DCNESS_INFRA_PATTERNS)"

    deny = READ_DENY_MATRIX.get(agent, ())
    matched = _matches_any(norm, deny)
    if matched:
        return (
            f"{agent} READ_DENY_MATRIX 매칭: `{norm}` "
            f"(READ_DENY_MATRIX matched `{matched}`)"
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
    # 토큰화 — quote 보존 (따옴표 친 토큰을 식별해 통째로 제외하기 위함).
    tokens = re.findall(r"[\"'][^\"']*[\"']|\S+", command)
    paths: list[str] = []
    for t in tokens:
        # 따옴표로 감싼 토큰은 path 후보에서 제외 (codex P2 round10). sed/awk/perl 스크립트
        # (`'s/foo/bar/'`)가 `/` 를 포함한다는 이유로 write path 로 오인돼 정상 편집
        # (`sed -i 's/foo/bar/' src/main.ts`)이 차단되던 false positive 방지. 따옴표 친 write
        # 대상이 누락되는 것은 본 guard 의 "false negative 우선" 원칙 + nested-shell 한계와 정합.
        if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
            continue
        if not t or t.startswith("-"):
            continue
        # URL/원격 스킴 토큰(`https://…`, `ssh://…`, `git://…`)은 로컬 write 대상이 아님 → 제외
        # (codex P2 round9). `curl https://… > docs/…/x.json` 의 URL 이 `/` 를 포함한다는 이유로
        # write path 후보로 오인돼 tech-reviewer 의 정상 evidence 수집이 차단되던 false positive 방지.
        # shell `>` 리다이렉트 대상은 항상 로컬 path 이므로 URL 제외가 write 누락을 만들지 않는다.
        if "://" in t:
            continue
        # 따옴표 없이 쓴 sed/awk 치환 스크립트(`s/foo/bar/`, `y/abc/def/`)도 명령 syntax → 제외
        # (codex P2 round10). delimiter 가 2번 이상 등장하는 `[sy]<delim>…<delim>` 형태만 매칭해
        # `src/main.ts` 같은 정상 path(`s` 다음이 delimiter 아님)는 보존.
        if re.match(r"^[sy]([/|#@,!~]).+\1", t):
            continue
        # path 후보 — `/` 포함 또는 알려진 확장자.
        if "/" in t or re.search(r"\.(md|py|json|sh|mjs|ts|tsx|js|jsx)$", t):
            paths.append(t)
    return paths


# ── 외부 시스템 mutation 차단 (#597 커밋5) ─────────────────────────────
# 활성 sub-agent 의 외부 상태 mutation (git push / gh pr·issue mutation / GitHub MCP)
# 차단. push·이슈·PR 은 메인 영역 (git-spec 절차). read-only 는 통과.
# 토큰 단위 파싱 — 문자열 grep 아님 (`gh issue list` 같은 read 를 오차단하지 않기 위함).

# 따옴표-인지 segment 분리 — shell 연산자(`&&` `||` `;` `|` `&`(백그라운드) `\n`)로 나누되
# *따옴표 안* 의 연산자는 무시한다 (codex P2 round10). 옛 방식(따옴표를 placeholder/공백으로
# 먼저 치환 후 정규식 split)은 두 결함의 근원이었다:
#   - 공백 치환(round8): value-flag(`-C`) 직후 따옴표 값을 통째로 없애 짝 파괴 → push 미탐.
#   - placeholder 치환(round9): 따옴표 친 verb/method(`git 'push'`, `gh api -X 'POST'`)가
#     placeholder 로 바뀌어 mutation 미탐.
# 따옴표-인지 스캐너는 (a) 따옴표 안 `&&` 가 가짜 segment 를 안 만들고(round8 목적 유지),
# (b) 따옴표를 *벗긴 내용* 을 토큰으로 보존해 verb/method/value 짝을 모두 살린다.
def _split_segments_quote_aware(command: str) -> list[str]:
    segments: list[str] = []
    cur: list[str] = []
    quote: Optional[str] = None
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
            cur.append(c)
            i += 1
            continue
        if command[i:i + 2] in ("&&", "||"):
            segments.append("".join(cur)); cur = []; i += 2; continue
        if c in ";|&\n":
            segments.append("".join(cur)); cur = []; i += 1; continue
        cur.append(c); i += 1
    segments.append("".join(cur))
    return segments


def _tokenize_quote_aware(segment: str) -> list[str]:
    """공백으로 토큰 분리하되 따옴표 안 공백은 무시하고 따옴표는 *벗겨 내용 보존*.

    그룹 punctuation `(){}` 는 공백 처리 — `(git push)` 안 명령도 토큰 분리 (codex P2).
    따옴표 친 verb/method(`'push'`, `'POST'`)의 *내용* 이 토큰으로 남아 mutation 식별 가능.
    """
    segment = re.sub(r"[(){}]", " ", segment)
    tokens: list[str] = []
    cur: list[str] = []
    in_tok = False
    quote: Optional[str] = None
    for c in segment:
        if quote:
            if c == quote:
                quote = None
            else:
                cur.append(c)
            in_tok = True
        elif c in "'\"":
            quote = c
            in_tok = True
        elif c.isspace():
            if in_tok:
                tokens.append("".join(cur)); cur = []; in_tok = False
        else:
            cur.append(c); in_tok = True
    if in_tok:
        tokens.append("".join(cur))
    return tokens

# heredoc *본문(body)* 만 제거 — `cat > f <<'EOF' … git push … EOF` 처럼 heredoc 데이터
# 안의 git/gh 텍스트를 실행 명령으로 오인해 차단하는 false positive 방지 (codex P2).
# 단 opener 라인의 `<<MARKER` *뒤* 에 오는 부분(예 `&& git push`)은 실행 syntax 이므로 보존
# (codex P2 재지적) — body 는 opener 라인 다음 `\n` 부터 줄 단독 `MARKER` 까지.
_HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1(?P<rest>[^\n]*)\n.*?^\s*\2\s*$",
    re.DOTALL | re.MULTILINE,
)


def _strip_heredocs(command: str) -> str:
    # body 만 지우고 opener 라인 잔여(rest, 예 `&& git push`)는 살린다.
    return _HEREDOC_RE.sub(lambda m: " " + m.group("rest") + " ", command)

# gh <noun> <verb> mutation 조합.
_GH_MUTATION: dict[str, frozenset] = {
    "pr": frozenset({"create", "merge", "close", "edit", "comment", "ready", "reopen", "review"}),
    "issue": frozenset({"create", "edit", "close", "comment", "delete", "reopen", "transfer", "pin", "unpin", "lock", "unlock"}),
    "release": frozenset({"create", "edit", "delete", "upload"}),
    "repo": frozenset({"create", "delete", "fork", "archive", "rename", "edit"}),
}

# gh api 의 mutating method.
_HTTP_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# gh api 의 field/input flag — 존재 시 method 미지정이면 POST 기본 (codex P1).
_GH_API_FIELD_FLAGS = frozenset({"-f", "-F", "--field", "--raw-field", "--input"})

# 서브커맨드 *앞* 에 올 수 있는 값-소비 global flag (codex P2) — 값 토큰을 noun 으로 오인 방지.
_GIT_VALUE_FLAGS = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix", "--config-env",
})
_GH_VALUE_FLAGS = frozenset({"-R", "--repo"})

# 명령 래퍼 / 쉘 키워드 — segment 선두에 와서 실제 명령어를 가리는 흔한 형태 (codex P2).
# 이들을 벗겨낸 *뒤* 의 첫 토큰을 실제 명령으로 본다.
_CMD_WRAPPERS = frozenset({
    "sudo", "doas", "env", "command", "builtin", "exec", "nice", "nohup",
    "time", "stdbuf", "setsid", "ionice", "then", "else", "elif", "do",
})
_SHELL_KEYWORDS = frozenset({
    "if", "fi", "done", "while", "until", "for", "case", "esac", "!",
})
_SHELL_COMMANDS = frozenset({"bash", "sh", "zsh"})
_MUTATION_RECURSION_LIMIT = 3

# main-owned dcness helper 서브커맨드 — sub-agent 금지.
# run 시작/종료/경계/checkpoint + peer claim board / merge lock 은 메인/훅 전담이고
# 어떤 sub-agent 도 호출하지 않는다(전수 grep 확인). 따라서 차단해도 회귀 0.
#
# ⚠️ 의도적 제외 — serial build-worker(sub-agent)가 정상적으로 호출하는 것들은 넣지 않는다:
#   - `begin-step`/`end-step`: hybrid-A build-worker 가 phase(test/impl/validate)마다 직접
#     호출 (loop-procedure.md). 막으면 기존 직렬 conveyor 가 깨진다.
#   - `prev-tasks-append`: build-worker 가 phase 3 에서 자기 산출 누적 (#525). 막으면 다음
#     task 의 [PREVIOUS_TASKS] 정합이 깨진다.
#   이들은 agent_boundary 가 parallel-worker 와 serial-build-worker 를 구별할 신호가 없어
#   구조 차단이 불가능 → 병렬 worker 에 대해서는 prompt 경계(정책 §5 + agent 지침)로 닫는다.
# 단 `prev-tasks-reset` 은 **메인 전담 + 파괴적**(메인 repo 의 .prev-tasks.md FIFO 삭제)이고
# 어떤 sub-agent 도 호출 안 하므로 차단한다 — 병렬 worker 가 leader 의 handoff 컨텍스트를
# 지우지 못하게 (#636 F16). append(추가)는 허용, reset(삭제)은 차단으로 비대칭.
# read-only (run-dir/run-status/is-active/status/routing/wave-plan/wave-status) 는 통과.
# 단 `wave-plan --register` 는 claim board 를 mutate 하므로 차단한다.
# `pr-create.sh` / `pr-finalize.sh` 같은 main-owned wrapper 도 command position 에서 차단한다.
_HELPER_LEADER_SUBCOMMANDS = frozenset({
    "begin-run", "end-run", "next-task", "post-task-begin",
    "finalize-run", "ledger-event", "init-session", "prev-tasks-reset",
    "wave-claim", "wave-heartbeat", "wave-release", "wave-reclaim",
    "merge-lock",
})
# 호출 형태 식별 — script basename / `python -m` 모듈명.
_HELPER_SCRIPT_NAMES = frozenset({"dcness-helper"})
_HELPER_MODULE_NAMES = frozenset({"harness.session_state"})
_MAIN_OWNED_SCRIPT_NAMES = frozenset({"pr-finalize.sh", "pr-create.sh"})

# GitHub MCP — read-only prefix (통과) / mutation verb prefix (차단).
_MCP_GH_READ_PREFIXES = ("get_", "list_", "search_")
_MCP_GH_MUTATION_PREFIXES = (
    "create_", "update_", "delete_", "merge_", "push_", "add_",
    "fork_", "remove_", "edit_", "close_", "request_", "submit_", "dismiss_",
)


def _segment_tokens(segment: str) -> list[str]:
    """한 shell segment 를 따옴표-인지 토큰화 + 선행 `KEY=VAL` env 프리픽스 제거.

    따옴표는 벗겨 *내용* 을 토큰으로 보존 (`git 'push'` → `push`) — codex P2 round10.
    """
    toks = _tokenize_quote_aware(segment)
    i = 0
    while i < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i]):
        i += 1  # env 할당 프리픽스 (FOO=bar cmd ...) skip
    return toks[i:]


def _command_basename(token: str) -> str:
    """실행 파일 토큰을 명령명으로 정규화 (`/usr/bin/git` -> `git`)."""
    return Path(token).name


def _peel_wrappers(toks: list[str]) -> list[str]:
    """선두 명령 래퍼/쉘 키워드를 벗겨 실제 명령 토큰 list 반환 (codex P2).

    `sudo git push` / `env X=y gh issue create` / `then git push` / `(git push)` 처럼
    실제 git/gh 가 래퍼 뒤에 숨는 흔한 형태 대응. `env` 는 뒤따르는 `VAR=val` 인자도 skip.

    한계: nested shell (`bash -c "..."`, `eval`), command substitution (`$(...)`),
    문자열 조립 등은 본 휴리스틱으로 잡지 못한다 — 본 guard 는 *보안 경계* 가 아니라
    실수 방지용 best-effort denylist (sub-agent 는 Bash 가 있어 우회는 원천적으로 가능).
    """
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        cmd_name = _command_basename(t)
        # 선두의 래퍼/키워드/옵션/`VAR=val` 은 모두 건너뛴다 (codex P2 round5):
        #   `sudo -E git push` / `env -i GH_TOKEN=x gh pr create` / `command -- gh pr create`.
        if (
            cmd_name in _CMD_WRAPPERS
            or t in _SHELL_KEYWORDS
            or t.startswith("-")
            or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)
        ):
            i += 1
            continue
        return toks[i:]
    return []


def _positional_args(toks: list[str], value_flags: frozenset) -> list[str]:
    """option 토큰을 건너뛰고 positional (noun/verb) 만 추출.

    값-분리형 global flag (예 `git -C <dir>`, `gh -R <owner/repo>`) 의 *값* 을
    positional 로 오인하지 않도록 value_flags 의 다음 토큰을 함께 skip (codex P2).
    """
    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            base = t.split("=", 1)[0]
            if base in value_flags and "=" not in t:
                i += 2  # `-C dir` 분리형 — 값 토큰도 skip
            else:
                i += 1
        else:
            out.append(t)
            i += 1
    return out


def _nested_shell_payload(toks: list[str]) -> Optional[tuple[str, str]]:
    """`bash -c ...` / `eval ...` 의 실행 payload 추출 (best-effort)."""
    if not toks:
        return None
    cmd = _command_basename(toks[0])
    if cmd in _SHELL_COMMANDS:
        for idx, tok in enumerate(toks[1:], start=1):
            # POSIX shell 계열에서 `-c` 또는 `-lc` 처럼 묶인 short option 뒤 토큰은 실행 문자열.
            if tok == "-c" or (tok.startswith("-") and not tok.startswith("--") and "c" in tok[1:]):
                if idx + 1 < len(toks):
                    return (f"{cmd} -c", toks[idx + 1])
                return None
        return None
    if cmd == "eval" and len(toks) > 1:
        return ("eval", " ".join(toks[1:]))
    return None


def _gh_api_mutation(toks: list[str]) -> Optional[str]:
    """`gh api` segment 가 mutation 인지 — block reason / None.

    explicit `-X/--method <mutating>` → 차단. 명시적 GET → 통과.
    method 미지정 + field/input flag(`-f`/`-F`/`--field`/`--raw-field`/`--input`) → POST 기본 → 차단.
    """
    explicit_method: Optional[str] = None
    has_field = False
    for j, t in enumerate(toks):
        if t in ("-X", "--method") and j + 1 < len(toks):
            explicit_method = toks[j + 1].upper()          # `-X POST` / `--method POST`
        elif t.startswith("--method="):
            explicit_method = t.split("=", 1)[1].upper()    # `--method=POST`
        elif t.startswith("-X") and len(t) > 2:
            # `-XPOST` (붙임) / `-X=POST` (codex P2 round5)
            explicit_method = t[2:].lstrip("=").upper()
        elif (
            t in _GH_API_FIELD_FLAGS
            or t.split("=", 1)[0] in _GH_API_FIELD_FLAGS
            or (len(t) > 2 and t[:2] in ("-f", "-F"))  # `-Ftitle=x` / `-fbody=x` 붙임 (round7)
        ):
            has_field = True
    if explicit_method in _HTTP_MUTATION_METHODS:
        return f"gh api {explicit_method} 차단 — 외부 mutation 은 메인 영역 (git-spec 절차)."
    if explicit_method == "GET":
        return None  # 명시적 GET — field 있어도 GET
    if has_field:
        return "gh api field flag (method 미지정 = POST 기본) 차단 — 외부 mutation 은 메인 영역."
    return None


def _helper_leader_mutation(toks: list[str]) -> Optional[str]:
    """leader-owned dcness helper 서브커맨드 호출인지 — block reason / None (#636).

    식별 형태(셋 다) — helper 가 **실제 실행 명령 위치(command position)** 일 때만:
      - `<...>/dcness-helper <subcommand>`          (wrapper 직접 — toks[0] basename)
      - `bash <...>/dcness-helper <subcommand>`      (shell 의 첫 positional = 스크립트)
      - `python -m harness.session_state <subcommand>` (`-m` 모듈 직접)

    그 뒤 *첫 positional* 토큰이 main-owned 서브커맨드면 차단. read-only
    (run-dir/run-status/.../wave-plan/wave-status)는 deny 목록에 없어 통과.

    data 위치 helper 토큰(`echo dcness-helper end-run`)은 명령이 아니므로 통과
    (#636 codex F9 — false-positive 제거). `bash -c "..."` 의 payload 는 호출부
    `_check_bash_mutation` 의 nested 재귀가 따로 처리한다.

    한계(의도적): `"$HELPER" end-run` 처럼 변수 indirection 은 미탐 — 본 guard 는
    보안 경계가 아니라 best-effort denylist (check_bash_mutation 한계와 동일).
    """
    if not toks:
        return None
    cmd0 = _command_basename(toks[0])
    sub_start: Optional[int] = None
    if cmd0 in _HELPER_SCRIPT_NAMES:
        sub_start = 1  # <helper> <sub>
    elif cmd0 in _SHELL_COMMANDS:
        # `bash <helper> <sub>` — 첫 positional(스크립트)이 helper 인 경우만.
        for i in range(1, len(toks)):
            if toks[i].startswith("-"):
                continue
            if _command_basename(toks[i]) in _HELPER_SCRIPT_NAMES:
                sub_start = i + 1
            break  # 첫 positional 만 본다 (그게 스크립트)
    elif cmd0.startswith("python"):
        # `python -m harness.session_state <sub>`
        for i in range(1, len(toks) - 1):
            if toks[i] == "-m" and toks[i + 1] in _HELPER_MODULE_NAMES:
                sub_start = i + 2
                break
    if sub_start is None:
        return None
    remaining = toks[sub_start:]
    for t in remaining:
        if t.startswith("-"):
            continue  # 옵션/플래그 skip
        if t == "wave-plan" and "--register" in remaining:
            return (
                "dcness-helper wave-plan --register 차단 — peer claim board 등록은 "
                "메인 영역."
            )
        if t in _HELPER_LEADER_SUBCOMMANDS:
            return (
                f"dcness-helper {t} 차단 — run 시작/종료/경계/checkpoint 및 "
                f"peer claim/merge lock 은 메인 영역."
            )
        return None  # 첫 positional 이 main-owned 아님 (read-only 등) → 통과
    return None


def _main_owned_script_mutation(toks: list[str]) -> Optional[str]:
    """Main-owned wrapper scripts invoked from command position."""
    if not toks:
        return None
    cmd0 = _command_basename(toks[0])
    if cmd0 in _MAIN_OWNED_SCRIPT_NAMES:
        return f"{cmd0} 차단 — PR 생성/머지는 메인 영역."
    if cmd0 in _SHELL_COMMANDS:
        for i in range(1, len(toks)):
            if toks[i].startswith("-"):
                continue
            script = _command_basename(toks[i])
            if script in _MAIN_OWNED_SCRIPT_NAMES:
                return f"{script} 차단 — PR 생성/머지는 메인 영역."
            break
    return None


def _check_bash_mutation(command: str, *, depth: int = 0) -> Optional[str]:
    if depth > _MUTATION_RECURSION_LIMIT:
        return None
    if not command:
        return None
    command = _strip_heredocs(command)  # heredoc 데이터 안 git/gh 텍스트 오인 방지 (codex P2)
    for segment in _split_segments_quote_aware(command):  # 따옴표-인지 분리 (codex P2 round10)
        toks = _peel_wrappers(_segment_tokens(segment))  # sudo/env/subshell/키워드 래퍼 제거
        if not toks:
            continue
        nested = _nested_shell_payload(toks)
        if nested:
            nested_source, payload = nested
            reason = _check_bash_mutation(payload, depth=depth + 1)
            if reason:
                return f"{nested_source} nested command 차단 — {reason}"
            continue
        # leader-owned dcness helper 서브커맨드 (병렬 wave worker 금지 — #636).
        helper_reason = _helper_leader_mutation(toks)
        if helper_reason:
            return helper_reason
        script_reason = _main_owned_script_mutation(toks)
        if script_reason:
            return script_reason
        cmd = _command_basename(toks[0])
        if cmd == "git":
            pos = _positional_args(toks[1:], _GIT_VALUE_FLAGS)
            if pos and pos[0] == "push":
                return "git push 차단 — push 는 메인 영역 (git-spec 절차). sub-agent 는 src/문서 변경만."
            continue
        if cmd != "gh":
            continue
        pos = _positional_args(toks[1:], _GH_VALUE_FLAGS)
        if not pos:
            continue
        noun = pos[0]
        # `gh api` — mutating method / field flag 차단.
        if noun == "api":
            reason = _gh_api_mutation(toks)
            if reason:
                return reason
            continue
        # `gh <noun> <verb>`
        verbs = _GH_MUTATION.get(noun)
        if verbs and len(pos) >= 2 and pos[1] in verbs:
            return (
                f"gh {noun} {pos[1]} 차단 — 외부 시스템 mutation 은 메인 영역 "
                f"(git-spec 이슈/PR 절차). read-only (view/list) 는 허용."
            )
    return None


def check_bash_mutation(command: str) -> Optional[str]:
    """Bash command 안의 외부 시스템 mutation 차단 — block reason str / None=allow.

    차단: `git push`, `gh pr (create|merge|...)`, `gh issue (create|edit|close|comment|...)`,
          `gh api` (mutating method / field flag), main-owned `dcness-helper`
          서브커맨드 (begin-run/end-run/next-task/post-task-begin/finalize-run/ledger-event/
          init-session/prev-tasks-reset/wave-claim/merge-lock 등), main-owned wrapper
          scripts (`pr-create.sh` / `pr-finalize.sh`).
    통과: read-only (`gh pr view`, `gh issue list`, `gh api` GET, `dcness-helper run-dir`,
          `dcness-helper wave-plan`), `git commit`(transport), serial build-worker 가 쓰는
          `begin-step`/`end-step`/`prev-tasks-append`(회귀 방지), 그 외 모든 명령.
          (prev-tasks `append`(추가)=허용 / `reset`(삭제)=차단 비대칭.)
    절대 실행 경로(`/usr/bin/git`, `/opt/homebrew/bin/gh`)도 명령명으로 정규화해 식별한다.
    global flag (`git -C ...`, `gh -R ...`) 가 앞에 와도 noun/verb 를 정확히 식별 (codex P2).
    흔한 래퍼(`sudo`/`env`/subshell/쉘 키워드)도 벗겨 식별 (codex P2).
    단순 nested shell (`bash/sh/zsh -c "..."`) 과 `eval "..."` payload 는 재귀 검사한다 (#601).

    ⚠️ 한계 (의도적 — 본 guard 는 *보안 경계* 가 아니라 실수 방지용 best-effort denylist):
      - command substitution (`$(...)`), backtick, 문자열 조립 우회 가능.
      - 값-소비 래퍼 옵션 뒤 명령 (`sudo -u root git push`, `nice -n 10 git push`) 은 미탐 —
        같은 short flag 가 래퍼마다 값 유무가 달라(`-n`: nice=값 / sudo=bare) 정확한 arity
        판정이 충돌하기 때문. bare 옵션(`sudo -E`, `command --`, `env -i`)까지는 식별.
      sub-agent 는 Bash 도구를 가지므로 완전 차단은 원천 불가. 실제 경계는 "외부 mutation 은
      메인 영역" 시퀀스 규약 + 흔한 직접 호출 차단의 조합이다. 추가 강화는 별도 follow-up 영역.
    """
    return _check_bash_mutation(command)


def check_github_mcp_mutation(tool_name: str) -> Optional[str]:
    """GitHub MCP tool mutation 차단 — block reason str / None=allow.

    read (`get_*`, `list_*`, `search_*`) = 통과. mutation verb prefix = 차단.
    보수적 — 알려진 mutation prefix 만 차단, 그 외 unknown 은 통과 (false positive 회피).

    🔴 GitHub *issue* mutation (`create_issue`/`update_issue`/`add_issue_comment` 등 op 에
    'issue' 포함) 은 **예외 — 통과** (codex review P1). qa / designer 는 frontmatter `tools:` 로
    이 도구를 *부여받아* 이슈 등록·추적 코멘트를 수행하도록 설계됐고 (`agents/qa.md`,
    `agents/designer.md`), CC 가 MCP 도구를 per-agent `tools:` 로 이미 gate 한다 (미부여 agent 는
    호출 자체 불가). 따라서 본 hook 이 issue mutation 을 막으면 *설계된 흐름만* 깨고
    실질 방어 이득은 없다. PR/repo mutation (`merge_pull_request`/`push_files`/
    `create_pull_request`/`create_or_update_file` 등) 은 어떤 agent 도 부여받지 않으므로 계속 차단.
    """
    prefix = "mcp__github__"
    if not tool_name.startswith(prefix):
        return None
    op = tool_name[len(prefix):]
    if op.startswith(_MCP_GH_READ_PREFIXES):
        return None
    if "issue" in op:
        return None  # issue mutation = qa/designer 설계 권한 (CC per-agent gate) — 예외
    if op.startswith(_MCP_GH_MUTATION_PREFIXES):
        return (
            f"GitHub MCP mutation 차단: {tool_name} — 외부 시스템 mutation 은 메인 영역 "
            f"(git-spec PR/repo 절차)."
        )
    return None
