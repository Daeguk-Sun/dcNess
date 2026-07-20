#!/usr/bin/env bash
# dcNess PostToolUseFailure Agent lifecycle hook.
# Matching hook-owned step을 step_aborted로 닫고 false step_completed 없이 복구
# context를 메인 Claude에 전달한다.

set -uo pipefail

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0

CC_PID=$PPID
python3 -m harness.hooks posttooluse-failure-agent --cc-pid "$CC_PID" \
  2>>/tmp/dcness-hook-stderr.log || true
exit 0
