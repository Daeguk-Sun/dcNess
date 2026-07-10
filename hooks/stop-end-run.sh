#!/usr/bin/env bash
# dcNess Stop 훅 — 메인 응답 종료 시 자동 end-run (issue #382)
#
# 트리거: Claude Code Stop event (메인 Claude 응답 종료 시점)
# stdin: CC payload (sessionId, stop_hook_active 포함)
# 동작: harness/hooks.py 의 handle_stop 호출
#   - stop_hook_active=true 시 즉시 skip (무한 루프 가드, 공식 docs §"Stop hook runs forever")
#   - active_runs 슬롯 + begin/end-step 완료 매칭 시 dcness-helper end-run 자동 호출
#   - 부산물: <run_dir>/review.md 생성 + loop-insights 누적 + active_runs 정리
#
# 실패 시 silent (exit 0) — Stop hook 은 block 안 함 (정상 종료 허용).

set -uo pipefail

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

# 활성화 게이트 — 현재 프로젝트가 dcness whitelist 에 없으면 pass-through.
python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0

CC_PID=$PPID

# stderr 는 /tmp 보존 (디버그용). Stop hook 의 stderr 는 메인 시야에 직접 inject 안 됨.
python3 -m harness.hooks stop --cc-pid "$CC_PID" 2>>/tmp/dcness-hook-stderr.log || true
exit 0
