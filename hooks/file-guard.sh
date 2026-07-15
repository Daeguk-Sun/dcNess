#!/usr/bin/env bash
# dcNess file-guard 훅 — PreToolUse Edit/Write/Read/Bash/mcp__.* agent_boundary 강제
#
# 트리거: Claude Code PreToolUse event, tool=Edit|Write|NotebookEdit|Read|Bash|mcp__.*
# GitHub MCP 도구는 알려진 외부 mutation만 검사하고 read/issue 도구는 통과한다.
# stdin: CC payload (sessionId + tool_name + tool_input)
# 동작: harness/hooks.py 의 handle_pretooluse_file_op 호출
#
# 반환:
#   exit 0: allow (CC 가 tool 호출 진행)
#   exit 2: block (stderr 메시지 + CC 가 호출 거부)
#          — CC docs: PreToolUse 는 exit 2 라야 차단 + stderr 가 Claude 에 피드백.
#            exit 1 = non-blocking error → 도구 그대로 진행 (차단 안 됨).
#
# 강제 룰 (harness/agent_boundary.py — 권한 경계 코드 SSOT):
#   §4.4 DCNESS_INFRA_PATTERNS — 인프라 path (모든 sub-agent 차단)
#   §4.2 ALLOW_MATRIX — agent 별 Write 허용 path
#   §4.3 READ_DENY_MATRIX — agent 별 Read 금지 path
#   §4.5 is_infra_project() — dcness 자체 작업 시 해제
#
# 활성 sub-agent 가 없으면 (메인 Claude) 통과 — governance Document Sync 가 별도 보호.

set -uo pipefail

# plugin root 를 PYTHONPATH 에 prepend — cross-project 시나리오 대응.
export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

record_fail_open() {
  python3 -m harness.session_state hook-fail-open \
    --hook file-guard \
    --category "$1" \
    --detail "$2" >/dev/null 2>&1 || true
}

# 활성화 게이트 — 미활성 프로젝트는 즉시 통과 + suppressOutput.
if ! python3 -m harness.session_state is-active >/dev/null 2>&1; then
  echo '{"suppressOutput": true, "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
  exit 0
fi

# bash 의 PPID = CC main process
CC_PID=$PPID

python3 -m harness.hooks pretooluse-file-op --cc-pid "$CC_PID"
RC=$?

# 정책 위반만 차단: Python CLI 가 정책 위반을 exit 2 로 내보낸다 (#597 round5).
# RC=2 → CC 차단 (handler 가 stderr 로 reason 출력 완료). exit 2 라야 차단 + stderr 피드백.
if [ "$RC" = "2" ]; then
  exit 2
fi
# 그 외 전부 fail-open(allow): RC=0(정상 통과) / RC=1·기타(import·문법 오류 등 파이썬 크래시).
# 크래시를 exit 2 로 매핑하면 hook 버그가 *모든* 도구 호출을 과차단하므로 반드시 fail-open.
# (#404 — suppressOutput: true 로 transcript attachment 숨김 시도. CC 버그 anthropics/claude-code#34859 회피 가설.)
if [ "$RC" != "0" ]; then
  record_fail_open "handler_nonzero" "harness.hooks pretooluse-file-op exited ${RC}; allowed"
fi
echo '{"suppressOutput": true, "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
exit 0
