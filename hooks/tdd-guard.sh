#!/usr/bin/env bash
# dcness TDD Guard Hook — PreToolUse[Edit|Write|NotebookEdit]
# agent 가 src 파일 작성/편집 시도 시 매칭 test 파일 존재 검사.
# 없으면 deny + 한국어 안내. 진짜 TDD 강제 (코드 작성 *전* 테스트 먼저).
#
# 영감: jha0313/codex-live-demo/.codex/hooks/tdd-guard.sh
# 차이: dcness 환경 (Claude Code plug-in hook) 매처 정합 + 한국어 메시지 보강
#
# 시점: agent Edit/Write tool_use 직전. tool_input.file_path 추출 + 검증.
# 차단 시 stderr 로 reason 출력 + exit 2.
#   — CC docs: PreToolUse 는 exit 2 라야 차단 + stderr 가 Claude 에 피드백.
#     (deny JSON + exit 0 은 CC 본체 버그 anthropics/claude-code#37210 영향 가변 →
#      catastrophic-gate / file-guard 와 동일하게 exit 2 로 통일.)

set -u

# #404 — 정상 통과 시 suppressOutput: true 써서 transcript attachment 숨김 시도.
allow() {
  echo '{"suppressOutput": true, "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
  exit 0
}

# plugin root 를 PYTHONPATH 에 prepend — cross-project 시나리오 대응 (다른 wrapper 정합).
export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

# 활성화 게이트 (#597 커밋3) — 미활성 프로젝트는 즉시 allow (no-op).
# 나머지 6 wrapper 는 이미 보유. tdd-guard 만 누락이라 비활성 프로젝트서도 deny 발동하던 결함 수정.
python3 -m harness.session_state is-active >/dev/null 2>&1 || allow

INPUT=$(cat)
[ -z "$INPUT" ] && allow

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

deny() {
  # reason 을 stderr 로 — exit 2 (호출부) 와 짝지어 CC 가 Claude 에 피드백.
  printf '%s\n' "$1" >&2
}

# tool_input.file_path 추출
FILE_PATH=$(python3 - "$INPUT" <<'PY'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
ti = payload.get("tool_input") or {}
for key in ("file_path", "path", "filename"):
    v = ti.get(key)
    if isinstance(v, str) and v:
        print(v)
        sys.exit(0)
PY
)

[ -z "$FILE_PATH" ] && allow

# 자동 skip — test/spec 파일 자체 + 표준 test 디렉터리 (#681)
# 주의: 단순 *test* / *spec* 광역 glob 은 contest.ts / spectrum.ts / latest.ts 같은
# 구현 파일을 test 파일로 오인 skip → TDD 강제를 우회시킨다 (false negative).
# 따라서 (1) basename 의 `.test.` / `.spec.` 접미 컨벤션, (2) 슬래시로 구분된 표준
# test 디렉터리 마디만 매치한다. basename 에 우연히 test/spec 이 든 구현 파일은 skip 안 함.
case "$(basename "$FILE_PATH")" in
  *.test.*|*.spec.*) allow ;;
esac
# 디렉터리 마디 매치는 **repo-relative 경로 기준** — PROJECT_ROOT 바깥 조상
# 디렉터리가 우연히 test 디렉터리명(e2e / __mocks__ 등)이어도 repo 내부 구현 파일을
# 오인 skip 하지 않게 한다 (codex P2 round2: `.../e2e/app/src/foo.ts` 가 e2e 조상으로
# TDD guard 가 무력화되던 결함). 절대/상대·심볼릭링크 경로 차이를 흡수하려 부모
# 디렉터리를 물리경로(`pwd -P`)로 정규화한 뒤 PROJECT_ROOT 접두를 제거한다. 부모 dir 이
# 아직 없으면(신규 중첩 경로) 원본을 그대로 쓴다. 선두 슬래시 1개로 정규화해 top-level
# 상대 경로 (`tests/helper.ts`) 도 `*/tests/*` 로 잡는다.
_tdd_pdir=$(cd "$(dirname "$FILE_PATH")" 2>/dev/null && pwd -P || true)
if [ -n "$_tdd_pdir" ]; then
  _tdd_abs="${_tdd_pdir}/$(basename "$FILE_PATH")"
else
  _tdd_abs="$FILE_PATH"
fi
_tdd_root=$(cd "$PROJECT_ROOT" 2>/dev/null && pwd -P || printf '%s' "$PROJECT_ROOT")
case "$_tdd_abs" in
  "$_tdd_root"/*) _tdd_rel="${_tdd_abs#"$_tdd_root"/}" ;;
  *) _tdd_rel="$_tdd_abs" ;;
esac
case "/${_tdd_rel#/}" in
  */__tests__/*|*/__test__/*|*/__mocks__/*) allow ;;
  */test/*|*/tests/*|*/spec/*|*/specs/*|*/e2e/*) allow ;;
esac

# 자동 skip — 설정 / 비-코드 / 타입 / Next.js 특수
case "$FILE_PATH" in
  *.json|*.css|*.scss|*.md|*.yml|*.yaml|*.env*|*.config.*|*tailwind*|*postcss*|*next.config*|*tsconfig*) allow ;;
  */types/*|*/types.ts|*/types.d.ts|*.d.ts) allow ;;
  */layout.tsx|*/layout.ts|*/page.tsx|*/page.ts|*/loading.tsx|*/error.tsx|*/not-found.tsx|*/globals.css) allow ;;
esac

# 자동 skip — plug-in 시드 boilerplate / 디자인 시안 폴더
# templates/ = dcness self repo 의 사용자 프로젝트 배포용 시드 (cp 후 활성화)
# design-variants/ = 활성화 프로젝트의 디자인 시안 폴더 (UI prototype, production 테스트 의무 X)
case "$FILE_PATH" in
  */templates/*|*/design-variants/*) allow ;;
esac

# 자동 skip — entry-file path heuristic (#423)
# registerRootComponent / AppRegistry.registerComponent 같은 entry 정의 파일은
# 비즈니스 로직 없는 boilerplate. test 의무 X. 컨벤션 path 만 좁게 매치.
# - */App.{ts,tsx,js,jsx}      = RN / Expo entry shell
# - */_layout.{ts,tsx,js,jsx}  = expo-router layout (Next.js layout.tsx 는 라인 67에서 별도 cover)
# - */apps/*/index.{ts,tsx,js,jsx} = monorepo apps/<name>/ entry (일반 index.* 는 너무 광범위라 제외)
# - */src/main.{ts,tsx,js,jsx}     = Vue/Vite main entry
case "$FILE_PATH" in
  */App.ts|*/App.tsx|*/App.js|*/App.jsx) allow ;;
  */_layout.ts|*/_layout.tsx|*/_layout.js|*/_layout.jsx) allow ;;
  */apps/*/index.ts|*/apps/*/index.tsx|*/apps/*/index.js|*/apps/*/index.jsx) allow ;;
  */src/main.ts|*/src/main.tsx|*/src/main.js|*/src/main.jsx) allow ;;
esac

# TS/JS 한정 — 그 외 silent skip
case "$FILE_PATH" in
  *.ts|*.tsx|*.js|*.jsx) ;;
  *) allow ;;
esac

# 자동 skip — 파일 내용 시그니처 매치 (#423)
# entry-file 가 path heuristic 못 잡은 위치에 있어도 내용으로 detection.
# 단 Edit 케이스만 cover (파일 이미 존재). 최초 Write 시는 path heuristic 의존.
if [ -f "$FILE_PATH" ]; then
  if grep -qE 'registerRootComponent\(|AppRegistry\.registerComponent\(' "$FILE_PATH" 2>/dev/null; then
    allow
  fi
fi

# 매칭 test 파일 존재 검사
# issue #469 결함 C — monorepo `apps/<X>/src/__tests__/<name>.test` 위치 cover.
# `<src_root>` = 파일 경로 안 `src/` 마디 직전까지 trim. trim 실패 (src/ 부재) 시
# `<PROJECT_ROOT>` fallback. 기존 4-tier (8 location) + grandparent 2 +
# monorepo src_root 2 = 6-tier (12 location).
has_test_for() {
  local fp="$1"
  local dir base parent grandparent src_root ext
  dir=$(dirname "$fp")
  base=$(basename "$fp" | sed -E 's/\.(ts|tsx|js|jsx)$//')
  parent=$(dirname "$dir")
  grandparent=$(dirname "$parent")
  case "$fp" in
    */src/*) src_root="${fp%%/src/*}/src" ;;
    *) src_root="${PROJECT_ROOT}/src" ;;
  esac
  for ext in ts tsx js jsx; do
    [ -f "${dir}/${base}.test.${ext}" ] && return 0
    [ -f "${dir}/${base}.spec.${ext}" ] && return 0
    [ -f "${dir}/__tests__/${base}.test.${ext}" ] && return 0
    [ -f "${dir}/__tests__/${base}.spec.${ext}" ] && return 0
    [ -f "${parent}/__tests__/${base}.test.${ext}" ] && return 0
    [ -f "${parent}/__tests__/${base}.spec.${ext}" ] && return 0
    # Tier 4: <grandparent>/__tests__/<name>.{test,spec}.<ext>  (issue #469 결함 C)
    [ -f "${grandparent}/__tests__/${base}.test.${ext}" ] && return 0
    [ -f "${grandparent}/__tests__/${base}.spec.${ext}" ] && return 0
    # Tier 5: <src_root>/__tests__/<name>.{test,spec}.<ext>  (monorepo, issue #469 결함 C)
    [ -f "${src_root}/__tests__/${base}.test.${ext}" ] && return 0
    [ -f "${src_root}/__tests__/${base}.spec.${ext}" ] && return 0
    # Tier 6: <PROJECT_ROOT>/src/__tests__/<name>.{test,spec}.<ext> (single-app fallback)
    [ -f "${PROJECT_ROOT}/src/__tests__/${base}.test.${ext}" ] && return 0
    [ -f "${PROJECT_ROOT}/src/__tests__/${base}.spec.${ext}" ] && return 0
  done
  return 1
}

if ! has_test_for "$FILE_PATH"; then
  BASE=$(basename "$FILE_PATH" | sed -E 's/\.(ts|tsx|js|jsx)$//')
  DIR=$(dirname "$FILE_PATH")
  PARENT=$(dirname "$DIR")
  GP=$(dirname "$PARENT")
  case "$FILE_PATH" in
    */src/*) SRC_ROOT="${FILE_PATH%%/src/*}/src" ;;
    *) SRC_ROOT="${PROJECT_ROOT}/src" ;;
  esac
  deny "TDD GUARD: '${BASE}' 에 대한 테스트 파일이 존재하지 않습니다. 구현 코드를 작성하기 *전*에 테스트를 먼저 작성하세요.

권장 위치 (먼저 시도):
  ${DIR}/${BASE}.test.ts                또는 ${DIR}/${BASE}.spec.ts
  ${DIR}/__tests__/${BASE}.test.ts
  ${PARENT}/__tests__/${BASE}.test.ts

이미 테스트 작성했는데 인식 안 됨 — dcness 가 검사하는 6-tier 12 location:
  Tier 1: <dir>/<name>.{test,spec}.{ts,tsx,js,jsx}
  Tier 2: <dir>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
  Tier 3: <parent>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
  Tier 4: <grandparent>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
  Tier 5: <src_root>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
  Tier 6: <PROJECT_ROOT>/src/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}

본 파일의 실측 위치:
  <dir>         = ${DIR}
  <parent>      = ${PARENT}
  <grandparent> = ${GP}
  <src_root>    = ${SRC_ROOT}
  <PROJECT_ROOT>= ${PROJECT_ROOT}

회피 안티패턴 금지: 위 location 외 다른 위치 (예: <parent>/__tests__/<subdir>/<name>.test.<ext>) 에 같은 본문 복사 쓰지 말 것. false negative 발견 시 본 hook 자체 fix (#469 결함 C 영역) 후속 PR 영역."
  exit 2
fi

allow
