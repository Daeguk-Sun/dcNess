#!/usr/bin/env bash
# dcNess SubagentStart lifecycle hook.
# Actual Agent spawn identity를 active run step에 bind하고 mode 없는 foreground
# Agent step만 자동 시작한다. Dynamic worktree/[PREVIOUS_TASKS] context도 subagent의
# 첫 prompt 처리 전에 additionalContext로 전달한다.

set -uo pipefail

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0

CC_PID=$PPID
python3 -m harness.hooks subagent-start --cc-pid "$CC_PID" \
  2>>/tmp/dcness-hook-stderr.log || true
exit 0
