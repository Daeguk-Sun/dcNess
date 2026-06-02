#!/usr/bin/env bash
# dcNess file-guard 훅 — PreToolUse Edit/Write/Read/Bash/mcp__.* agent_boundary 강제 + trace
#
# 트리거: Claude Code PreToolUse event, tool=Edit|Write|NotebookEdit|Read|Bash|mcp__.*
# mcp__* 도구는 boundary 검사 skip (file_path 인자 부재) + trace pre append 만 — #255 W5 정합.
# stdin: CC payload (sessionId + tool_name + tool_input)
# 동작: harness/hooks.py 의 handle_pretooluse_file_op 호출
#
# 반환:
#   exit 0: allow (CC 가 tool 호출 진행)
#   exit 1: block (stderr 메시지 + CC 가 호출 거부)
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

# 활성화 게이트 — 미활성 프로젝트는 즉시 통과 + suppressOutput.
if ! python3 -m harness.session_state is-active >/dev/null 2>&1; then
  echo '{"suppressOutput": true, "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
  exit 0
fi

# bash 의 PPID = CC main process
CC_PID=$PPID

python3 -m harness.hooks pretooluse-file-op --cc-pid "$CC_PID"
RC=$?

# #404 — 정상 통과 시 suppressOutput: true 써서 transcript attachment 숨김 시도.
# CC 본체 알려진 버그 (anthropics/claude-code#34859) 회피 가설. 차단 path 는 기존 (stderr + exit 1) 유지.
if [ "$RC" = "0" ]; then
  echo '{"suppressOutput": true, "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
fi
exit $RC
