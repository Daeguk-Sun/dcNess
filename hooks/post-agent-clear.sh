#!/usr/bin/env bash
# dcNess post-agent-clear 훅 — PostToolUse Agent
#
# 동작:
#   1. live.json.active_agent / active_mode clear (메인 복귀)
#   2. prose staging 결과를 additionalContext stdout JSON 으로 inject
#      → 메인 다음 turn 의 Agent tool result 옆에 system reminder 로 보임
#
# 트리거: Claude Code PostToolUse event, tool=Agent
# stdin: CC payload (sessionId, agent_id, tool_input.subagent_type 등)
#
# 반환:
#   exit 0: 항상 (PostToolUse 는 차단 권한 X)
#   stdout: JSON (hookSpecificOutput) — Claude Code 가 인식해서 메인 컨텍스트 inject

set -uo pipefail

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

# 활성화 게이트.
python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0

CC_PID=$PPID

# stdout (JSON) 그대로 통과시킴 — stderr 는 /tmp 에 보존 (디버그용).
python3 -m harness.hooks posttooluse-agent --cc-pid "$CC_PID" 2>>/tmp/dcness-hook-stderr.log || true
exit 0
