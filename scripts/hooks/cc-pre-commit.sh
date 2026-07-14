#!/bin/sh
# dcNess Claude Code PreToolUse hook (Bash matcher)
# 규칙 정의: docs/internal/governance.md §2.7
#
# 입력: stdin JSON ({"tool_name":"Bash","tool_input":{"command":"..."}})
# 동작:
#   - git commit     → main 직접 commit 차단 + pytest 게이트
#   - git checkout -b / git switch -c → 브랜치명 git-spec 룰 검증
#   - gh pr create   → PR 제목 git-spec 룰 검증
# 종료 코드:
#   0 — 통과 (또는 대상 명령 미포함)
#   2 — 게이트 실패 (Claude Code PreToolUse 차단)

set -u

INPUT=$(cat)

# command 추출 (python3 가 없으면 grep fallback)
if command -v python3 >/dev/null 2>&1; then
  COMMAND=$(printf '%s' "$INPUT" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))
except Exception:
  pass' 2>/dev/null || echo "")
else
  COMMAND=$(printf '%s' "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"command"[[:space:]]*:[[:space:]]*"//; s/"$//')
fi

resolve_naming_script() {
  # 우선순위 (이슈 #419):
  # 1. git toplevel 의 scripts — 본 저장소 안 작업 시 항상 본 저장소의 최신 룰 우선.
  #    cc-pre-commit.sh 는 .claude/settings.json 통해 dcness self 작업용으로 등록되므로
  #    plug-in cache 의 구 룰이 자기 저장소를 검증하던 회귀 차단.
  # 2. CLAUDE_PLUGIN_ROOT — 외부 활성 프로젝트가 본 hook 를 별도로 등록한 경우 대비 (현재 미사용).
  # 3. plug-in cache — 위 둘 다 부재 시 최후 fallback.
  self_script="$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-}")/scripts/check_git_naming.mjs"
  [ -f "$self_script" ] && echo "$self_script" && return 0
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/check_git_naming.mjs" ]; then
    echo "${CLAUDE_PLUGIN_ROOT}/scripts/check_git_naming.mjs"; return 0
  fi
  cache_dir="${HOME}/.claude/plugins/cache/dcness/dcness"
  if [ -d "$cache_dir" ]; then
    latest=$(ls -1 "$cache_dir" 2>/dev/null | sort -V | tail -1)
    if [ -n "$latest" ] && [ -f "$cache_dir/$latest/scripts/check_git_naming.mjs" ]; then
      echo "$cache_dir/$latest/scripts/check_git_naming.mjs"; return 0
    fi
  fi
  return 1
}

CMD_FIRST_LINE=$(printf '%s' "$COMMAND" | head -1)

case "$CMD_FIRST_LINE" in
  *"git commit"*)
    # cwd 의 git toplevel 우선 — 워크트리 안에서는 워크트리 top, 메인이면 메인 top (#268).
    # CLAUDE_PROJECT_DIR 우선 시 워크트리 안 commit 이 메인 main 브랜치로 오인 차단됨.
    TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null)
    [ -z "$TOPLEVEL" ] && TOPLEVEL="${CLAUDE_PROJECT_DIR:-}"
    cd "$TOPLEVEL" 2>/dev/null || exit 0
    current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [ "$current_branch" = "main" ]; then
      echo "ERROR: main 직접 commit 금지. branch 만든 후 commit + PR." >&2
      echo "  git checkout -b feature/<name>" >&2
      exit 2
    fi
    if [ -f scripts/check_python_tests.sh ]; then
      if ! sh scripts/check_python_tests.sh; then
        exit 2
      fi
    fi
    ;;

  *"git checkout -b"* | *"git switch -c"*)
    BRANCH_NAME=$(printf '%s' "$COMMAND" | python3 -c '
import sys, re
cmd = sys.stdin.read()
m = re.search(r"git (?:checkout -b|switch -c)\s+([^\s]+)", cmd)
print(m.group(1) if m else "")
' 2>/dev/null || echo "")
    if [ -n "$BRANCH_NAME" ]; then
      NAMING_SCRIPT=$(resolve_naming_script)
      if [ -n "$NAMING_SCRIPT" ]; then
        if ! node "$NAMING_SCRIPT" --branch "$BRANCH_NAME" 2>&1; then
          echo "브랜치 생성 취소. 올바른 형식으로 다시 시도하세요." >&2
          exit 2
        fi
      fi
    fi
    ;;

  *"gh pr create"*)
    TITLE=$(printf '%s' "$COMMAND" | python3 -c '
import sys, re
cmd = sys.stdin.read()
m = re.search(r"--title\s+['\''\"](.*?)['\''\"]\s", cmd, re.DOTALL)
if not m:
    m = re.search(r"--title\s+['\''\"](.*?)['\''\"]\s*$", cmd, re.DOTALL)
if not m:
    m = re.search(r"--title\s+(\S+)", cmd)
print(m.group(1) if m else "")
' 2>/dev/null || echo "")
    if [ -n "$TITLE" ]; then
      NAMING_SCRIPT=$(resolve_naming_script)
      if [ -n "$NAMING_SCRIPT" ]; then
        if ! node "$NAMING_SCRIPT" --title "$TITLE" 2>&1; then
          echo "PR 생성 취소. 올바른 제목 형식으로 다시 시도하세요." >&2
          exit 2
        fi
      fi
    fi
    ;;
esac
exit 0
