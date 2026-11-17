#!/usr/bin/env bash
# dcNess worktree-files 훅 — EnterWorktree 직후 로컬 전용 하네스 파일을 새 worktree 에 연결
#
# 트리거: Claude Code PostToolUse event, tool=EnterWorktree
# stdin: CC payload (tool_response.worktreePath, cwd)
# 동작: harness/worktree_files.py sync — main worktree 원본으로 심볼릭 링크
#
# EnterWorktree 는 git post-checkout hook 을 실행하지 않으므로 이 훅이 대신한다.
# 실패해도 작업을 막지 않는다 (exit 0). 빠진 파일은 dcness-helper status 가 보여 준다.

set -uo pipefail

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0

python3 -m harness.worktree_files sync --hook-stdin >&2 || true
exit 0
