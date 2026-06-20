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
import shlex
# Fixed git argv probes in this module run without shell and with timeouts.
import subprocess  # nosec B404
from pathlib import Path
from typing import Iterable, Optional

from harness.session_state import _resolve_project_root


__all__ = [
    "DCNESS_INFRA_PATTERNS",
    "ALLOW_MATRIX",
    "READ_DENY_MATRIX",
    "is_infra_project",
    "is_opt_out",
    "load_project_boundary_overrides",
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
    # 프로젝트별 boundary override 설정 디렉토리 `.dcness/` 전체 (#696) — 위조 방지.
    # sub-agent 가 자기 write 경계를 셀프 확장/축소하지 못하도록 INFRA 로 보호한다.
    # 파일 단위(`boundary\.json$`)만 막으면, 프로젝트가 add 로 `.dcness/` 를 연 뒤
    # 디렉토리 타깃 Bash write(`cp x .dcness/`)로 boundary.json 을 *교체* 해 보호를 우회할
    # 수 있다 (codex P2). 디렉토리 자체(`.dcness`)·하위(`.dcness/...`) 를 모두 매칭해
    # 디렉토리 타깃 우회를 닫는다. `.dcness` 는 dcness 제어 영역이라 sub-agent write 가
    # 정당하지 않다 (메인 Claude 는 INFRA 통과로 boundary.json 작성). INFRA 검사는
    # ALLOW(코어+add) 검사보다 *먼저* 발화하므로 add 로 못 열고, remove 는 ALLOW 에서만
    # 빼는 DENY 오버레이라 INFRA 보호를 못 푼다 (가드 = 검사 순서로 자동 보장).
    r'(^|/)\.dcness(/|$)',
    # guard self-disable 마커 (#696 codex P1) — boundary override 의 broad add(예 `.*`)로
    # sub-agent 가 file guard 자체를 끄는 통제 파일을 쓰지 못하도록 INFRA 로 보호한다.
    #   - `.no-dcness-guard` — is_opt_out() 마커. 쓰면 다음 검사부터 file guard 전면 우회.
    #   - `.claude-plugin/` — plugin.json name=dcness 가 _is_dcness_self_repo() 신호라,
    #     쓰면 is_infra_project() True 로 모든 sub-agent 경계가 무력화된다. `(^|/)\.claude/`
    #     는 `.claude-plugin/`(≠`.claude/`)에 미매칭이라 별도 보호 필요. 디렉토리 타깃 우회
    #     방지로 디렉토리 자체·하위를 모두 매칭. (`~/.claude/.dcness-infra` 는 home 이라
    #     cwd-밖 가드가 이미 차단 — sub-agent 가 경계 밖 write 불가.)
    r'(^|/)\.no-dcness-guard(/|$)',
    r'(^|/)\.claude-plugin(/|$)',
)


# ── run_dir prose carve-out (#597 커밋4) ──────────────────────────────
# build-worker 의 `<run_dir>/build-{test,impl,validate,polish}.md` self-write 만 보존
# (`agents/build-worker.md` 권한 경계). run_dir 는 INFRA 패턴 `(^|/)\.claude/` 에
# 걸리고, build-worker 가 ALLOW_MATRIX 에 등재된 순간 ALLOW 미매칭으로도 막힌다.
# → INFRA / ALLOW_MATRIX 검사보다 *먼저*, build-worker + build-*.md 만 좁게 허용한다.
#
# 🔴 반드시 (agent == build-worker) AND (파일명 = build-{test,impl,validate,polish}.md)
#    둘 다 좁힌다.
#    넓게(임의 agent, 임의 .md) 열면 engineer 같은 agent 가 run_dir 에 module-architect.md /
#    code-validator.md / architecture-validator.md 를 `PASS` 로 *위조* → `_has_pass` 가 신뢰 →
#    catastrophic gate (pr-reviewer / engineer / module-architect 게이트) 우회 (codex review P1). build-* 파일명은 어떤
#    gate 도 신뢰하지 않으므로 forge 불가.
RUN_DIR_PROSE_ALLOW: tuple[str, ...] = (
    r'(^|/)\.claude/harness-state/\.sessions/[^/]+/runs/[^/]+/build-(test|impl|validate|polish)\.md$',
)


# ── ALLOW_MATRIX (agent 별 Write 허용) ─────────────────────────
# RWHarness agent-boundary.py:48~84 기반. engineer / test-engineer 는 #694 에서 언어·레이아웃
# 중립으로 확장 (JS/TS 전용 → Python·Go·Ruby·JVM·C#·PHP·Elixir 등 비-JS 외부 프로젝트).
ALLOW_MATRIX: dict[str, tuple[str, ...]] = {
    # engineer — 구현 소스. JS/TS·Python 모노레포(src/·apps/·packages/) + 언어 중립 소스 루트
    # (lib/·app/·cmd/·internal/·pkg/). docs/ · 루트 비소스 문서(README 등)는 미매칭으로
    # 차단 — 역할 격리 유지. remotion/ 같은 프로젝트 고유 디렉토리는 프로젝트별 override 영역.
    "engineer": (
        # JS/TS·Python 모노레포 관례
        r'(^|/)src/',
        r'(^|/)apps/[^/]+/src/',
        r'(^|/)apps/[^/]+/app/',
        r'(^|/)apps/[^/]+/alembic/',
        r'(^|/)packages/[^/]+/src/',
        r'(^|/)apps/[^/]+/[^/]+\.toml$',
        r'(^|/)apps/[^/]+/[^/]+\.cfg$',
        # 언어 중립 소스 루트 레이아웃 — 프로젝트 루트(^) 앵커. 위 src/ 는 monorepo 중첩
        # (services/x/src 등)도 소스라 (^|/) 유지하지만, lib/cmd/pkg/internal 등은 모듈 루트
        # 성격이라 중첩(node_modules/*/lib·.github/*/lib·vendor/*/pkg)을 소스로 오인하면 안 된다 (codex P2).
        r'^lib/',          # 다수 언어 라이브러리 소스
        r'^app/',          # Rails/Phoenix 등 루트 app/
        r'^cmd/',          # Go 엔트리포인트
        r'^internal/',     # Go 내부 패키지
        r'^pkg/',          # Go 공개 패키지
        # 루트 직속 단일 파일 엔트리포인트 — Flask/FastAPI `app.py`·`main.py`, Django
        # `manage.py`, Go 루트 `main.go`, Node `server.js`/`index.js` 등 (#705 실측: 디렉토리
        # 패턴만 있으면 worker 가 루트 엔트리 파일을 못 고쳐 "prose 제시 → 메인 대리 적용"
        # 우회가 강제됨). *코드 확장자만* — `.sh`(게이트 스크립트)·`.md`(문서)·toml/json/yaml
        # (매니페스트)·Makefile/Dockerfile 은 계속 미매칭 차단. 그 외 언어는 #696 override 영역.
        #
        # 단 *검증 도구체인 설정* 은 코드 확장자라도 제외 (#705 리뷰 P2) — 이들을 engineer 가
        # 고치면 자기 산출을 검증하는 게이트 자체를 침묵시킬 수 있다 (conftest.py 의
        # collect_ignore 한 줄 = 테스트 전체 skip → false-clean 재유입):
        #   - dotfile 설정 (.eslintrc.js 등) — `(?!\.)` 선두 제외
        #   - conftest.py (pytest collection 제어) / noxfile.py (테스트 세션 러너)
        #     — test-engineer 의 `conftest\.py$` ALLOW 는 별개라 build-worker(합집합)는 유지
        #   - *.config.{js,ts,mjs,cjs} (jest/vitest/eslint/playwright 류 설정)
        r'^(?!\.)(?!conftest\.py$)(?!noxfile\.py$)'
        r'(?![^/]+\.config\.(?:js|ts|mjs|cjs)$)'
        r'[^/]+\.(?:py|pyi|go|rs|rb|php|ex|exs|js|jsx|ts|tsx|mjs|cjs)$',
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
    # test-engineer — 테스트만 (역할 격리: 구현 소스 write 금지). 언어 중립 테스트 컨벤션을
    # 디렉토리(tests/·test/·spec/·__tests__/)와 파일명(test_*.py·*_test.{go,rb,..}·
    # *.test.{ts,..}·*Test(s).{java,kt,cs,php}·*_spec.rb 등)으로 포괄.
    # 기존 JS/TS 전용 패턴(src/__tests__/·apps/*/tests/ 등)은 아래 광범위 패턴에 흡수됨
    # (test_test_engineer_js_ts_regression 회귀 가드가 보존 검증).
    "test-engineer": (
        # 테스트 디렉토리 — 안의 모든 파일이 테스트 (언어 다수)
        r'(^|/)tests?/',           # tests/ · test/ — Python·Rust·PHP·JVM(src/test/)·JS·일반
        r'(^|/)spec/',             # Ruby RSpec, JS Jasmine
        r'(^|/)__tests__/',        # JS/TS jest — 어디든
        # 테스트 파일명 — 디렉토리 밖 테스트 (언어별 컨벤션)
        r'(^|/)test_[^/]+\.py$',                          # Python test_*.py
        r'(^|/)[^/]+_test\.(py|go|rb|dart|exs?)$',        # Python·Go·Ruby·Dart·Elixir *_test.*
        r'(^|/)[^/]+_spec\.rb$',                          # Ruby *_spec.rb
        r'(^|/)[^/]+\.test\.[jt]sx?$',                    # JS/TS *.test.*
        r'(^|/)[^/]+\.spec\.[jt]sx?$',                    # JS/TS *.spec.*
        r'(^|/)[^/]+Tests?\.(java|kt|kts|scala|cs|php)$', # JVM·C#·PHP *Test(s).*
        r'(^|/)conftest\.py$',                            # pytest 픽스처 관례 파일 (#705)
    ),
    # ux-architect — 화면 플로우/와이어프레임 + design system token (agents/ux-architect 권한 경계).
    # ux-flow 는 epic 단위가 canonical (docs/milestones/.../ux-flow.md — /design 흐름), root
    # docs/ux-flow.md 는 단일-epic legacy 폴백. design.md 는 system-level token 영역 (/ux 흐름).
    # 산출물 위치·계층 SSOT = docs/plugin/deliverables-map.md.
    "ux-architect": (
        r'(^|/)docs/ux-flow\.md$',                              # root (단일-epic legacy 폴백)
        r'(^|/)docs/milestones/[^/]+/epics/[^/]+/ux-flow\.md$',  # epic 폴더 한정 (canonical — /design)
        r'(^|/)docs/design\.md$',                               # design system token (system-level 영역)
    ),
    # tech-reviewer — PRD 기술 선행 검토 산출물만 (agents/tech-reviewer.md 권한 경계).
    "tech-reviewer": (
        r'(^|/)docs/tech-review\.md$',
        r'(^|/)docs/tech-review/',
    ),
    # 판정/검증 전용 agent — Write 0.
    "code-validator": (),
    "architecture-validator": (),
    "pr-reviewer": (),
    "product-acceptance": (),
    "plan-reviewer": (),
}

# build-worker — engineer ∪ test-engineer (agents/build-worker.md 권한 경계).
# 합집합으로 정의해 engineer / test-engineer 패턴 변경 시 자동 동기화 (drift 방지).
# 키 부재 시 "미정의 agent = 통과" fallback 으로 빠져 /impl-loop 핵심 mutation agent 의
# 경계가 무력화되던 결함(#597) 수정. (run_dir prose self-write 는 RUN_DIR_PROSE_ALLOW carve-out.)
ALLOW_MATRIX["build-worker"] = ALLOW_MATRIX["engineer"] + ALLOW_MATRIX["test-engineer"]

# build-worker 의 합집합 구성 역할 — 프로젝트 override(#696) 전파 대상. 코어 ALLOW 가
# engineer ∪ test-engineer 인 것과 동일 원리로, `.dcness/boundary.json` 의 engineer /
# test-engineer add·remove 도 build-worker 에 합쳐 전파해야 한다 (안 그러면 /impl-loop 의
# 실제 mutation agent 인 build-worker 가 engineer.remove 를 우회하고 engineer.add 를 무효화).
_BUILD_WORKER_UNION_ROLES: tuple[str, ...] = ("engineer", "test-engineer", "build-worker")


# ── 코드 agent 전용영역 deny (#694 codex P2) ───────────────────────
# engineer / test-engineer / build-worker 의 언어 중립 ALLOW 패턴(lib/·internal/·cmd/·
# tests?/·spec/·test_*.py 등)은 re.search 라 docs/ 하위 동명 디렉토리(docs/internal/·
# docs/spec/·docs/tests/)나 docs 안 테스트 파일명을 *우회 허용* 한다. docs/ 는 architect,
# design-variants/ 는 designer 전용이므로, 코드 agent 의 write 를 ALLOW 검사보다 *먼저*
# 차단해 역할 경계를 지킨다. (기존 src/ 패턴의 docs/src/ 우회도 함께 닫힌다.)
_CODE_AGENTS: frozenset = frozenset({"engineer", "test-engineer", "build-worker"})
# 루트(^) 앵커 — monorepo 의 동명 app/package(apps/docs/src·packages/docs/src)를 문서로
# 오인해 정상 소스를 막지 않도록 루트 docs 트리만 deny (#694 codex P2). _normalize 가
# ./·.. 를 해소하므로 ^ 앵커가 안전(우회 prefix 없음).
_CODE_AGENT_EXCLUSIVE_DENY: tuple[str, ...] = (
    # 다른 역할 전용 산출 영역 — 루트(^) 앵커 (monorepo 동명 패키지 apps/docs/src 는 소스라 허용).
    r'^docs/',            # architect / ux-architect / tech-reviewer 전용
    r'^design-variants/', # designer 전용
    # 의존성 / 빌드 산출 트리 — 누구도 직접 write 하지 않는다. engineer 의 (^|/)src/ 와
    # test-engineer 의 (^|/)tests?/·spec/ 가 이 트리 안 src/tests 를 *중첩* 매칭하던 우회를
    # 차단 (codex P1/P2). 언어 전반의 보편 집합 — 프로젝트 고유 추가는 #696 override.
    #
    # 두 그룹으로 나눈다 (codex P2 round10):
    #  A. 이름 충돌 없는 트리 — 디렉토리명이 소스 디렉토리·패키지명과 겹칠 일이 없어 어디서든
    #     (^|/) deny 가 안전.
    r'(^|/)node_modules/',   # JS/TS 의존성
    r'(^|/)\.venv/',          # Python 가상환경
    r'(^|/)venv/',
    r'(^|/)__pycache__/',     # Python 캐시 (항상 캐시 — 어디든)
    #  B. 이름 충돌 가능 트리 — vendor·third_party·dist·build·target·out 은 패키지명이나
    #     소스 디렉토리명과 겹칠 수 있다 (예 monorepo 의 `apps/vendor/src/` 정상 패키지,
    #     허용된 `src/build/`). 어디서든 (^|/) deny 하면 이런 정당 소스를 오차단하므로,
    #     루트 또는 monorepo 패키지 루트(apps/*·packages/*)에만 앵커한다 (codex P2 round10).
    r'^(?:vendor|third_party|dist|build|target|out)/',
    r'(^|/)(?:apps|packages)/[^/]+/(?:vendor|third_party|dist|build|target|out)/',
)


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


# ── 프로젝트별 boundary override (#696) ────────────────────────────────
_BOUNDARY_ROOT_CACHE: dict[str, Optional[str]] = {}


def _git_worktree_toplevel(cwd: Path) -> Optional[Path]:
    """현재 working tree 의 top-level (`git rev-parse --show-toplevel`) — boundary 탐색 상한.

    `_resolve_project_root` 는 state 공유 목적으로 git common-dir parent(= main repo
    루트)를 돌려주는데, linked worktree(메인 체크아웃 밖에 둔 worktree)에선 그 루트가
    worktree cwd 의 조상이 아니라 boundary.json 탐색 경계로 부적합하다 (#696 codex P2).
    boundary.json 은 worktree-local 체크아웃 파일이므로, 현재 working tree top-level 까지
    탐색해야 nested·linked worktree 양쪽에서 정확하고, 그 *위* 상위 워크스페이스·home 은
    무시된다. git 아님·실패 시 None (호출부가 cwd 폴백).
    """
    key = str(cwd)
    if key in _BOUNDARY_ROOT_CACHE:
        cached = _BOUNDARY_ROOT_CACHE[key]
        return Path(cached) if cached else None
    top: Optional[Path] = None
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(cwd),
            timeout=2,
        )
        out = result.stdout.strip()
        if out:
            top = Path(out).resolve()
    except (subprocess.SubprocessError, OSError, ValueError):
        top = None
    _BOUNDARY_ROOT_CACHE[key] = str(top) if top else None
    return top


def load_project_boundary_overrides(
    cwd: Optional[Path] = None,
) -> dict[str, dict[str, tuple[str, ...]]]:
    """cwd 조상에서 `.dcness/boundary.json` 을 찾아 agent별 add/remove 패턴을 반환한다.

    #696 — 외부 활성 프로젝트가 자기 레이아웃·정책을 직접 선언해 sub-agent write 경계를
    양방향으로 커스텀하는 메커니즘. 코어 ALLOW_MATRIX 는 합리적 기본값만 잡고, 무한한
    프로젝트별 예외는 프로젝트가 SSOT (reactive cycle 을 코어 밖으로 이관).

    형식: `{"<agent>": {"add": [regex...], "remove": [regex...]}}`.
    - add  — 코어 ALLOW 에 없는 경로 허용 (비표준 레이아웃 / 의도적 기본 제외 완화).
    - remove — 코어 기본 허용 경로를 이 프로젝트에서 제거 (DENY 오버레이).

    되돌릴 수 없는 경계(INFRA / boundary.json 자기보호)는 호출부(check_write_allowed)가
    ALLOW 검사보다 *먼저* 강제하므로 여기서 거르지 않는다 — add 로 INFRA 를 못 열고,
    remove 는 ALLOW 에서만 빼므로 INFRA 보호를 못 푼다 (가드 = 검사 순서로 자동 보장).

    안전 degrade: 파일 부재·파싱 실패·형식 위반·컴파일 불가 정규식은 조용히 무시하고
    해당 부분만 제외한다 (잘못된 설정이 코어 기본값을 깨뜨리지 않는다).
    """
    if cwd is None:
        cwd = Path.cwd()
    try:
        cur = cwd.resolve()
    except (OSError, RuntimeError):
        return {}
    # 탐색 범위를 현재 working tree top-level 까지로 제한 (#696 codex P2). 무한정 상위로
    # 올라가면 현재 프로젝트 밖(상위 워크스페이스 / home)의 boundary.json 이 무관한 하위
    # 프로젝트의 sub-agent write 경계를 silently 확장/축소해 file guard 를 약화한다.
    # top-level 은 nested·linked worktree 양쪽에서 worktree-local 루트로 해소되므로, 하위
    # 디렉토리에서도 worktree 루트 boundary.json 을 찾되 그 위는 무시한다. top-level 이
    # cwd 조상이 아니면(git 아님·폴백·예외) cwd 자신만 검사한다.
    root = _git_worktree_toplevel(cur)
    if root is None:
        root = cur
    search_dirs: list[Path] = []
    for d in (cur, *cur.parents):
        search_dirs.append(d)
        if d == root:
            break
    else:
        search_dirs = [cur]
    cfg_path: Optional[Path] = None
    for d in search_dirs:
        candidate = d / ".dcness" / "boundary.json"
        if candidate.is_file():
            cfg_path = candidate
            break
    if cfg_path is None:
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for agent, spec in data.items():
        if not isinstance(agent, str) or not isinstance(spec, dict):
            continue
        entry: dict[str, tuple[str, ...]] = {}
        for key in ("add", "remove"):
            raw = spec.get(key, [])
            if not isinstance(raw, list):
                continue
            valid: list[str] = []
            for pat in raw:
                if not isinstance(pat, str):
                    continue
                try:
                    re.compile(pat)
                except re.error:
                    continue
                valid.append(pat)
            if valid:
                entry[key] = tuple(valid)
        if entry:
            result[agent] = entry
    return result


def _effective_overrides(
    overrides: dict[str, dict[str, tuple[str, ...]]], agent: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """agent 에 적용할 (add, remove) 패턴을 반환한다.

    build-worker 는 코어 ALLOW 가 engineer ∪ test-engineer 합집합이므로(#597), 프로젝트
    override 도 구성 역할(engineer / test-engineer)의 add·remove 를 합쳐 전파한다 (codex
    P1 #696). 안 그러면 /impl-loop 의 실제 mutation agent 인 build-worker 가 engineer.remove
    를 우회하고 engineer.add 를 무효화한다. 그 외 agent 는 자기 키만 본다.
    """
    roles = _BUILD_WORKER_UNION_ROLES if agent == "build-worker" else (agent,)
    add: list[str] = []
    remove: list[str] = []
    for role in roles:
        ov = overrides.get(role)
        if not ov:
            continue
        add.extend(ov.get("add", ()))
        remove.extend(ov.get("remove", ()))
    return tuple(add), tuple(remove)


# ── path 정규화 ───────────────────────────────────────────────────────


def _normalize(file_path: str, cwd: Optional[Path] = None) -> str:
    """path 를 cwd 기준으로 resolve(`.`/`..`/심볼릭 해소) 후 cwd 상대로 환원.

    절대/상대 동일 정규화. cwd 밖(상위 탈출·외부 절대)이면 *절대경로* 를 반환한다 —
    호출부(check_write/read_allowed)의 cwd-밖 가드(`/` 시작)가 차단하게 (#694 codex P1).
    원본 문자열을 돌려주면 `lib/../../lib/x` 같은 중첩 .. 탈출이 ALLOW 패턴에 매칭되는
    우회가 생긴다.
    """
    if cwd is None:
        cwd = Path.cwd()
    # 디렉토리 타깃(`cp x tests/`·`mv y apps/web/src/`)의 끝 구분자 보존 — resolve()가 끝 `/`를
    # 떼면 ALLOW 패턴(`tests?/`·`.../src/`)과 deny 패턴(`^docs/`·`(^|/)hooks/`)이 디렉토리 루트를
    # 미매칭해, 정당 in-bound write 가 오차단되고 보호 디렉토리 타깃이 누락된다 (#694 codex P2 r10).
    # 끝 `/` 외에 `/.`(예 `cp x tests/.`)·`/./` 도 같은 디렉토리를 가리키는 흔한 스펠링이므로
    # 동일하게 끝 `/`로 보존한다. resolve() 가 `/.` 를 떼어 `tests` 로 만드는 것을 보정 (codex P2 r10).
    trailing = (
        "/" if file_path.endswith(("/", os.sep, "/.", os.sep + ".")) else ""
    )
    try:
        # ~ / ~user 는 셸이 hook 통과 *후* home 으로 확장하므로 미리 모사 — home 은 cwd 밖이라
        # 아래 resolve 가 절대경로화 → 호출부 cwd-밖 가드가 차단 (#694 codex P2).
        p = Path(file_path).expanduser()
        base = p if p.is_absolute() else (cwd / p)
        resolved = base.resolve()
        try:
            rel = str(resolved.relative_to(cwd.resolve()))
            # cwd 자기 자신(rel == ".")엔 `/`를 붙이지 않는다 — 루트는 어떤 ALLOW 도 아니며
            # `./` 오매칭을 막는다. resolve() 결과는 끝 `/`가 없으므로 슬래시 중복 없음.
            return rel + trailing if rel != "." else rel
        except ValueError:
            # cwd 밖 — 절대경로 반환 (가드의 `/` 시작 체크가 차단). 끝 `/`는 무해(가드 우선).
            return str(resolved) + trailing
    except (OSError, ValueError, RuntimeError):
        # expanduser 가 home 미해결 시 RuntimeError — 원본 반환(`~` 시작은 가드가 차단).
        return file_path


def _normalize_to_project_root(file_path: str, cwd: Optional[Path] = None) -> Optional[str]:
    """path 를 main project root 기준 상대경로로 정규화한다.

    일반 write 경계는 worktree cwd 기준으로 검사해야 하지만, build-worker phase prose
    run_dir 는 worktree 안에서도 main repo 의 `.claude/harness-state` 가 정본이다. worker 가
    `dcness-helper run-dir` 의 절대경로를 그대로 Write 할 때 cwd 밖 경로로 오차단하지 않도록
    run_dir carve-out 판정에만 project-root 정규화를 쓴다.
    """
    if cwd is None:
        cwd = Path.cwd()
    try:
        p = Path(file_path).expanduser()
        base = p if p.is_absolute() else (cwd / p)
        resolved = base.resolve()
        project_root = _resolve_project_root(cwd).resolve()
        return str(resolved.relative_to(project_root))
    except (OSError, ValueError, RuntimeError):
        return None


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
    shell_context: bool = False,
) -> Optional[str]:
    """Write/Edit 검사 — block reason str / None=allow.

    메인 Claude (agent=None / 빈 문자열) = 통과. 메인 거버넌스는 Document Sync 가 강제.
    is_infra_project() True = 통과 — dcness 자체 SSOT 편집.
    `.no-dcness-guard` 마커 = 통과.

    shell_context=True (Bash 추출 경로) — `$VAR`/`$()`/backtick 셸 확장 토큰을 추가 차단한다
    (셸이 hook 후 확장 → 위치 미확정). Edit/Write 의 literal file_path 는 False(기본)라
    프레임워크 route 파일명(users.$id.tsx 등)의 literal `$` 를 막지 않는다 (#694 codex P2).
    """
    if not agent:
        return None
    if is_infra_project(cwd):
        return None
    if is_opt_out(cwd):
        return None

    # 셸 변수/명령치환 — Bash 출처(shell_context)만, *정규화 전 원본* 에 대해 검사한다.
    # `$PWD/../tests/x` 처럼 `..` 가 `$` 세그먼트를 상쇄하면 _normalize 후 norm 에서 `$` 가
    # 사라져(→ `tests/x`) 셸가드를 우회하지만, 런타임엔 셸이 `$PWD` 를 확장해 프로젝트 밖에
    # write 한다 (#694 codex P2 r10). 원본 file_path 에 `$`/backtick 이 있으면 위치 미확정으로
    # 즉시 차단. Edit/Write 의 literal `$` 파일명(users.$id.tsx)은 shell_context=False 라 통과.
    # Bash 는 shlex tokenization 뒤 quote 원형을 보존하지 않으므로, write target 에 `$`/backtick 이
    # 남아 있으면 보수적으로 expansion risk 로 본다.
    if shell_context and ("$" in file_path or "`" in file_path):
        return (
            f"{agent} 셸 확장 경로 차단: `{file_path}` — Bash 의 $VAR/$()/backtick 은 hook 후 "
            f"셸 확장돼 위치 미확정 (프로젝트 밖 write 우회 방지)."
        )

    # run_dir prose carve-out — worktree cwd 에서도 helper run-dir 는 main repo 아래 절대경로다.
    # cwd 기준으로 보면 "프로젝트 밖"이므로, 먼저 project-root 기준으로 좁게 허용 여부를 본다.
    project_norm = _normalize_to_project_root(file_path, cwd)
    if (
        agent == "build-worker"
        and project_norm is not None
        and _matches_any(project_norm, RUN_DIR_PROSE_ALLOW)
    ):
        return None

    norm = _normalize(file_path, cwd)

    # cwd 밖 경로 차단 (#694 codex P2) — _normalize 가 cwd 상대화에 성공하면 항상 cwd-내
    # 상대경로다. `/`(절대 외부) 또는 `../`(상위 탈출)로 시작하면 cwd 밖이며, 이때 원본을
    # ALLOW 패턴에 먹이면 `../tests/x` 가 `(^|/)tests?/` 에 매칭되는 등 경계 우회가 생긴다.
    # 절대외부·상위탈출·~home — 출처 무관 공통 차단. _normalize 가 cwd 상대화에 성공하면 항상
    # cwd-내 상대경로이므로, `/`(절대 외부)·`..`/`../`(상위 탈출)·`~`(home, expanduser 잔존)로
    # 시작하면 프로젝트 루트 밖이다 (#694 codex P1/P2). 원본을 ALLOW 패턴에 먹이면 `../tests/x`
    # 가 `(^|/)tests?/` 에 매칭되는 우회가 생긴다.
    if norm.startswith("/") or norm == ".." or norm.startswith("../") or norm.startswith("~"):
        return (
            f"{agent} 경계 밖 경로 차단: `{norm}` — 프로젝트 루트 밖 write 금지 "
            f"(.. 상위 탈출 / 절대 외부 / ~ home)."
        )

    # 1. INFRA pattern → 모든 agent 차단.
    matched = _matches_any(norm, DCNESS_INFRA_PATTERNS)
    if matched:
        return f"인프라 path 보호: matched `{matched}` (DCNESS_INFRA_PATTERNS)"

    # 2. 코드 agent 전용영역 deny → ALLOW 검사보다 먼저 (#694 codex P2).
    #    언어 중립 ALLOW 패턴이 docs/·design-variants/ 하위 동명 디렉토리/파일명을
    #    re.search 로 우회 허용하는 것을 차단 — docs/ 는 architect, design-variants/ 는 designer.
    if agent in _CODE_AGENTS:
        matched = _matches_any(norm, _CODE_AGENT_EXCLUSIVE_DENY)
        if matched:
            return (
                f"{agent} 전용영역 침범 차단: `{norm}` matched `{matched}` — "
                f"docs/ 는 architect, design-variants/ 는 designer 전용 (코드 agent write 금지)."
            )

    # 3. 프로젝트별 boundary override (#696) — 코어 ALLOW 검사 직전에 적용.
    #    INFRA(1)·코드 agent 전용 deny(2) 를 모두 통과한 뒤이므로, override 는 되돌릴 수
    #    없는 경계를 건드리지 못한다 (가드 = 검사 순서). remove 는 ALLOW 보다 우선하는
    #    DENY 오버레이, add 는 코어 ALLOW 확장.
    add_patterns, remove_patterns = _effective_overrides(
        load_project_boundary_overrides(cwd), agent
    )

    # 3a. remove 오버레이 — 코어 기본 허용 경로를 이 프로젝트에서 제거.
    if remove_patterns:
        matched = _matches_any(norm, remove_patterns)
        if matched:
            return (
                f"{agent} 프로젝트 boundary remove: `{norm}` matched `{matched}` "
                f"(.dcness/boundary.json — 코어 기본값에서 제거)"
            )

    # 3b. ALLOW_MATRIX (코어 + 프로젝트 add) 미매칭 → 차단.
    allowed = ALLOW_MATRIX.get(agent)
    if allowed is None:
        # 미정의 agent — false positive 회피로 통과.
        return None
    # write-zero agent (판정/검증 전용 — code-validator / pr-reviewer /
    # architecture-validator / product-acceptance / plan-reviewer 의 빈 ALLOW) 는
    # 프로젝트 add 로도 write 를 열 수 없다 (#696 codex P2). "검증자는 자기가 검증하는
    # 것을 못 고친다" 는 역할 격리는 catastrophic gate 신뢰의 근간이라 되돌릴 수 없는
    # 경계다 — add 로 mutation agent 로 승격시키면 gate forge 위험. 이슈가 "프로젝트
    # 감수" 로 연 것은 mutation agent 내부 경계(engineer 의 tests/)이지 검증자 승격이 아니다.
    if allowed == ():
        return (
            f"{agent} 는 write-zero(판정/검증 전용) — 프로젝트 boundary add 로도 "
            f"write 를 열 수 없다 (`{norm}`): 검증자 역할 격리는 되돌릴 수 없는 경계."
        )
    effective = allowed + add_patterns
    if not _matches_any(norm, effective):
        return (
            f"{agent} ALLOW_MATRIX 미매칭: `{norm}` "
            f"(ALLOW_MATRIX — 허용 = {list(effective)})"
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

# v1: 명시적 write 구문(sed/perl -i / cp / mv / rm / tee / 리다이렉션) 만 잡는다.
# Bash 전체를 보안 파서처럼 해석하지 않는다. 단, 후보를 잡을 때는 "path처럼 보이는 모든
# 토큰" 이 아니라 실제 write 대상만 추출해 read operand 오차단을 줄인다.
_BASH_WRITE_INDICATORS: tuple[str, ...] = (
    r'\bsed\b\s+(?:[-]\w*i\w*|--in-place)',
    r'\bawk\b\s+(?:[-]\w*i\w*|--in-place)',
    r'\bperl\b\s+[-]\w*i',
    r'\b(?:cp|mv|rm)\b\s+',
    r'>\s*\S',     # redirect (writing)
    r'>>\s*\S',    # append redirect
    r'\btee\b',
)
_WRITE_REDIRECT_OPS = frozenset({">", ">>", ">|", "&>", ">&", "<>"})
_READ_REDIRECT_OPS = frozenset({"<", "<<", "<<-"})
_SHELL_SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})
_CP_VALUE_FLAGS = frozenset({"-t", "--target-directory"})
_SED_EXPR_FLAGS = frozenset({"-e", "--expression", "-f", "--file"})

# ── write target 이 아닌 redirect 대상 (#705) ─────────────────────────
# `cmd 2>&1` 의 `1` (fd 복제) 과 `cmd > /dev/null` 의 `/dev/null` (device sink) 은
# 프로젝트 파일 write 가 아니다. 이들이 write target 으로 추출되면 ALLOW 미매칭(`1`) /
# 경계 밖(`/dev/null`) 차단이 발화하는데, `2>&1`·`>/dev/null` 은 테스트/lint 게이트 호출의
# 보편 스펠링이라 sub-agent (특히 worktree 기반 /impl-loop 의 build-worker) 의 read-only
# 검증 실행이 통째로 막히고, 검증 미실행이 정적 분석 PASS 로 흡수되는 false-clean 으로
# 이어졌다. device sink 는 *동등 스펠링 정규화 후 일치* 만 — `/dev/shm/...` 등 하위 경로,
# `..` 탈출(`/dev/null/../../etc/x`), 대소문자 변형(POSIX 는 case-sensitive)은 일반 경계 검사 유지.
_DEVICE_SINKS = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"})


def _is_device_sink(path: str) -> bool:
    """`/dev/./null`·`//dev/null` 같은 동등 스펠링을 정규화해 sink 판정 (#705 리뷰).

    os.path.normpath 는 선두 `//` 를 POSIX 규약상 보존하므로 중복 슬래시를 먼저 접는다.
    `..` 가 섞이면 normpath 결과가 sink 정확 일치에서 벗어나 일반 검사로 흘러간다.
    """
    return os.path.normpath(re.sub(r"/{2,}", "/", path)) in _DEVICE_SINKS


def _is_fd_dup_target(op: str, target: str) -> bool:
    """`>&` 의 대상이 fd 숫자(`2>&1`) 또는 `-`(fd 닫기, `2>&-`) 면 파일 아님.

    bash 시맨틱 그대로 — `>&word` 는 word 가 숫자/`-` 면 fd 복제, 그 외면 파일 redirect
    (csh 스타일 `>& out.log` 는 계속 write target). `&>word` 는 항상 파일이라 비대상.
    fd 는 ASCII 숫자만 — 유니코드 숫자(`>&²`)는 bash 가 파일명으로 취급 (#705 리뷰).
    """
    return op == ">&" and ((target.isascii() and target.isdigit()) or target == "-")


def _shell_tokens_for_paths(command: str) -> list[str]:
    """Path 추출용 shell tokenization.

    `shlex` 로 quote 를 해석하고 punctuation 을 분리한다. unmatched quote 등으로 실패하면
    빈 list 를 반환한다. 이 hook 은 보안 경계가 아니라 실수 방지용 denylist 이므로
    parse 불능 command 에서 억지 추출로 false positive 를 만들지 않는다.
    """
    try:
        lexer = shlex.shlex(_strip_heredocs(command), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return []


def _split_shell_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    cur: list[str] = []
    for tok in tokens:
        if tok in _SHELL_SEPARATORS:
            if cur:
                segments.append(cur)
                cur = []
        else:
            cur.append(tok)
    if cur:
        segments.append(cur)
    return segments


def _strip_redirections_for_paths(tokens: list[str]) -> tuple[list[str], list[str]]:
    """segment 에서 redirection write target 을 수집하고 command argv 만 반환."""
    argv: list[str] = []
    paths: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # `2>err.log` 는 shlex 가 `2`, `>`, `err.log` 로 분리한다. fd 번호는 argv 에 넣지 않는다.
        if tok.isdigit() and i + 1 < len(tokens) and tokens[i + 1] in (
            _WRITE_REDIRECT_OPS | _READ_REDIRECT_OPS
        ):
            op = tokens[i + 1]
            if i + 2 < len(tokens) and op in _WRITE_REDIRECT_OPS:
                # fd 복제 (`2>&1`) / 닫기 (`2>&-`) 는 파일 write 아님 (#705).
                if not _is_fd_dup_target(op, tokens[i + 2]):
                    paths.append(tokens[i + 2])
            i += 3 if i + 2 < len(tokens) else 2
            continue
        if tok in (_WRITE_REDIRECT_OPS | _READ_REDIRECT_OPS):
            if i + 1 < len(tokens) and tok in _WRITE_REDIRECT_OPS:
                # fd 복제 (`>&2`) / 닫기 (`>&-`) 는 파일 write 아님 (#705).
                if not _is_fd_dup_target(tok, tokens[i + 1]):
                    paths.append(tokens[i + 1])
            i += 2 if i + 1 < len(tokens) else 1
            continue
        argv.append(tok)
        i += 1
    return argv, paths


def _command_positionals(args: list[str], value_flags: frozenset = frozenset()) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            out.extend(args[i + 1:])
            break
        if arg.startswith("-") and arg != "-":
            base = arg.split("=", 1)[0]
            if base in value_flags and "=" not in arg:
                i += 2
            else:
                i += 1
            continue
        out.append(arg)
        i += 1
    return out


def _target_directory_flag(args: list[str]) -> Optional[str]:
    for i, arg in enumerate(args):
        if arg.startswith("--target-directory="):
            return arg.split("=", 1)[1]
        if arg == "-t" and i + 1 < len(args):
            return args[i + 1]
        if arg == "--target-directory" and i + 1 < len(args):
            return args[i + 1]
    return None


def _sed_short_options_include_in_place(arg: str) -> bool:
    if not arg.startswith("-") or arg.startswith("--") or arg == "-":
        return False
    for opt in arg[1:]:
        if opt == "i":
            return True
        if opt in ("e", "f"):
            return False
    return False


def _sed_in_place_targets(args: list[str]) -> list[str]:
    in_place = False
    expression_supplied = False
    script_consumed = False
    targets: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            targets.extend(p for p in args[i + 1:] if p and "://" not in p)
            break
        if arg in ("-i", "--in-place"):
            in_place = True
            # BSD sed: `sed -i '' 's/x/y/' file`
            if i + 1 < len(args) and args[i + 1] == "":
                i += 2
            else:
                i += 1
            continue
        if _sed_short_options_include_in_place(arg):
            in_place = True
            i += 1
            continue
        if arg.startswith("--in-place"):
            in_place = True
            i += 1
            continue
        if arg in _SED_EXPR_FLAGS:
            expression_supplied = True
            i += 2
            continue
        if (
            arg.startswith("-e")
            or arg.startswith("--expression=")
            or arg.startswith("-f")
            or arg.startswith("--file=")
        ):
            expression_supplied = True
            i += 1
            continue
        if arg.startswith("-") and arg != "-":
            i += 1
            continue
        if not expression_supplied and not script_consumed:
            script_consumed = True
            i += 1
            continue
        if arg and "://" not in arg:
            targets.append(arg)
        i += 1
    return targets if in_place else []


def _perl_in_place_targets(args: list[str]) -> list[str]:
    in_place = False
    targets: list[str] = []
    skip_next_expr = False
    for arg in args:
        if skip_next_expr:
            skip_next_expr = False
            continue
        if arg == "--":
            continue
        if arg.startswith("-") and arg != "-":
            if "i" in arg.lstrip("-"):
                in_place = True
            # `-e 'script'`, `-pe 'script'`, `-E 'script'` 등은 다음 토큰이 program text.
            opt = arg.lstrip("-")
            if ("e" in opt or "E" in opt) and opt.lower().endswith(("e", "pe", "ne")):
                skip_next_expr = True
            continue
        if arg and "://" not in arg:
            targets.append(arg)
    return targets if in_place else []


def _awk_in_place_targets(args: list[str]) -> list[str]:
    in_place = False
    program_supplied = False
    program_consumed = False
    targets: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            targets.extend(p for p in args[i + 1:] if p and "://" not in p)
            break
        if arg == "-i":
            if i + 1 < len(args) and args[i + 1] == "inplace":
                in_place = True
            i += 2
            continue
        if arg in ("-iinplace", "--include=inplace"):
            in_place = True
            i += 1
            continue
        if arg in ("-f", "--file"):
            program_supplied = True
            i += 2
            continue
        if arg.startswith("-f") or arg.startswith("--file="):
            program_supplied = True
            i += 1
            continue
        if arg in ("-v", "-F") and i + 1 < len(args):
            i += 2
            continue
        if arg.startswith("-") and arg != "-":
            i += 1
            continue
        if not program_supplied and not program_consumed:
            program_consumed = True
            i += 1
            continue
        # awk variable assignment arguments are not file operands.
        if arg and "://" not in arg and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", arg):
            targets.append(arg)
        i += 1
    return targets if in_place else []


def _command_write_targets(argv: list[str]) -> list[str]:
    toks = _peel_wrappers(argv)
    if not toks:
        return []
    cmd = _command_basename(toks[0])
    args = toks[1:]
    if cmd == "cp":
        target_dir = _target_directory_flag(args)
        if target_dir is not None:
            return [target_dir]
        pos = _command_positionals(args, _CP_VALUE_FLAGS)
        return [pos[-1]] if len(pos) >= 2 else []
    if cmd == "mv":
        target_dir = _target_directory_flag(args)
        pos = _command_positionals(args, _CP_VALUE_FLAGS)
        return ([target_dir] if target_dir is not None else []) + pos
    if cmd == "rm":
        return _command_positionals(args)
    if cmd == "tee":
        return _command_positionals(args)
    if cmd == "sed":
        return _sed_in_place_targets(args)
    if cmd == "perl":
        return _perl_in_place_targets(args)
    if cmd in ("awk", "gawk"):
        return _awk_in_place_targets(args)
    return []


def extract_bash_paths(command: str) -> list[str]:
    """Bash command 안의 write target path 추출 (best-effort).

    이 함수는 file boundary 용이다. 따라서 `cat README.md > src/generated.ts` 에서
    `README.md` 같은 read operand 는 후보가 아니고, 실제 write target 인
    `src/generated.ts` 만 반환한다.
    """
    if not any(re.search(ind, command) for ind in _BASH_WRITE_INDICATORS):
        return []
    paths: list[str] = []
    for segment in _split_shell_segments(_shell_tokens_for_paths(command)):
        argv, redirect_paths = _strip_redirections_for_paths(segment)
        paths.extend(redirect_paths)
        paths.extend(_command_write_targets(argv))
    seen: set[str] = set()
    deduped: list[str] = []
    for path in paths:
        if _is_device_sink(path):
            continue  # `/dev/null` 등 무해 sink — 프로젝트 write 아님 (#705)
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


# ── 외부 상태 변경 차단 (#597 커밋5) ─────────────────────────────
# 활성 sub-agent 의 외부 상태 변경 (git push / gh pr·issue 변경 / GitHub MCP)
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
            segments.append("".join(cur))
            cur = []
            i += 2
            continue
        if c in ";|&\n":
            segments.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
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
                tokens.append("".join(cur))
                cur = []
                in_tok = False
        else:
            cur.append(c)
            in_tok = True
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
        return f"gh api {explicit_method} 차단 — 외부 상태 변경은 메인 영역 (git-spec 절차)."
    if explicit_method == "GET":
        return None  # 명시적 GET — field 있어도 GET
    if has_field:
        return "gh api field flag (method 미지정 = POST 기본) 차단 — 외부 상태 변경은 메인 영역."
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
                f"gh {noun} {pos[1]} 차단 — 외부 상태 변경은 메인 영역 "
                f"(git-spec 이슈/PR 절차). read-only (view/list) 는 허용."
            )
    return None


def check_bash_mutation(command: str) -> Optional[str]:
    """Bash command 안의 외부 상태 변경 차단 — block reason str / None=allow.

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
      sub-agent 는 Bash 도구를 가지므로 완전 차단은 원천 불가. 실제 경계는 "외부 상태 변경은
      메인 영역" 시퀀스 규약 + 흔한 직접 호출 차단의 조합이다. 추가 강화는 별도 follow-up 영역.
    """
    return _check_bash_mutation(command)


def check_github_mcp_mutation(tool_name: str) -> Optional[str]:
    """GitHub MCP tool 외부 상태 변경 차단 — block reason str / None=allow.

    read (`get_*`, `list_*`, `search_*`) = 통과. mutation verb prefix = 차단.
    보수적 — 알려진 mutation prefix 만 차단, 그 외 unknown 은 통과 (false positive 회피).

    🔴 GitHub *issue* mutation (`create_issue`/`update_issue`/`add_issue_comment` 등 op 에
    'issue' 포함) 은 **예외 — 통과** (codex review P1). designer 등 issue 도구를 가진 agent 는
    frontmatter `tools:` 로 이슈 등록·추적 코멘트를 수행하도록 설계됐고 (`agents/designer.md`),
    CC 가 MCP 도구를 per-agent `tools:` 로 이미 gate 한다 (미부여 agent 는
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
        return None  # issue mutation = per-agent tools gate 설계 권한 — 예외
    if op.startswith(_MCP_GH_MUTATION_PREFIXES):
        return (
            f"GitHub MCP 외부 상태 변경 차단: {tool_name} — 외부 상태 변경은 메인 영역 "
            f"(git-spec PR/repo 절차)."
        )
    return None
