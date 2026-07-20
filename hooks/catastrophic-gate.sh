#!/usr/bin/env bash
# dcNess catastrophic-gate 훅 — PreToolUse Agent 직전 catastrophic 룰 검사
#
# 트리거: Claude Code PreToolUse event, tool=Agent
# stdin: CC payload (sessionId + tool_input.{subagent_type, mode})
# 동작: harness/hooks.py 의 handle_pretooluse_agent 호출
#
# 반환:
#   exit 0: allow (CC 가 Agent 호출 진행)
#   exit 2: block (stderr 메시지 + CC 가 호출 거부)
#          — CC docs: PreToolUse 는 exit 2 라야 차단 + stderr 가 Claude 에 피드백.
#            exit 1 = non-blocking error → 도구 그대로 진행 (차단 안 됨).
#
# 강제 룰:
#   - modeful/current-step 일치 — 명시 step과 Agent 호출 identity 확인
#   - mode 없는 foreground Agent는 correlation intent만 저장하고 actual spawn은
#     SubagentStart lifecycle hook이 기록
#   - build-worker 게이트 — 구현 직전 설계 산출물 확인 (같은 run 의 module-architect PASS
#     또는 begin-run --design-doc 으로 기록된 설계 문서 실존)
#   - impl entry pre-flight — design_doc 의 `### 수정 허용` boundary 대조 +
#     generated TDD hook 활성/커밋 확인
#   - module-architect 게이트 — /design 첫 module-architect 단위 호출 직전 architecture-validator 1차 PASS

set -uo pipefail

# plugin root 를 PYTHONPATH 에 prepend — cross-project 시나리오 대응.
export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

record_fail_open() {
  python3 -m harness.session_state hook-fail-open \
    --hook catastrophic-gate \
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

python3 -m harness.hooks pretooluse-agent --cc-pid "$CC_PID"
RC=$?

# 정책 위반만 차단: Python CLI 가 정책 위반을 exit 2 로 내보낸다 (#597 round5).
# RC=2 → CC 차단 (handler 가 stderr 로 reason 출력 완료). exit 2 라야 차단 + stderr 피드백.
if [ "$RC" = "2" ]; then
  exit 2
fi
# 그 외 전부 fail-open(allow): RC=0(정상 통과) / RC=1·기타(import·문법 오류 등 파이썬 크래시).
# 크래시를 exit 2 로 매핑하면 hook 버그가 *모든* Agent 호출을 과차단하므로 반드시 fail-open.
# (#404 — suppressOutput: true 로 transcript attachment 숨김 시도.)
if [ "$RC" != "0" ]; then
  record_fail_open "handler_nonzero" "harness.hooks pretooluse-agent exited ${RC}; allowed"
fi
echo '{"suppressOutput": true, "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
exit 0
