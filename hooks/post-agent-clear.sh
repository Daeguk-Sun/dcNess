#!/usr/bin/env bash
# dcNess post-agent-clear 훅 — PostToolUse Agent
#
# 동작:
#   1. status=completed foreground prose만 저장 + step_completed receipt 기록
#   2. async/빈 prose/identity mismatch는 false completion 없이 복구 진단
#   3. matching live.json.active_agent / pending identity clear
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
