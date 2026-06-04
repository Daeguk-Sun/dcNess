#!/usr/bin/env bash
# dcNess SessionStart 훅 — sid 추출 + by-pid 작성 + live.json 초기화 + 슬림 inject
#
# 트리거: Claude Code SessionStart event
# stdin: CC payload (sessionId 포함)
# 동작: harness/hooks.py 의 handle_session_start 호출 + 슬림 본문 inject
#
# 실패 시 silent (exit 0) — CC 동작 방해 안 함.

set -uo pipefail

# plugin root 를 PYTHONPATH 에 prepend — cwd 에 harness/ 없는 cross-project 시나리오 대응.
# CLAUDE_PLUGIN_ROOT 는 CC 가 plugin hook 실행 시 자동 설정.
export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

# 활성화 게이트 — 현재 프로젝트가 dcness whitelist 에 없으면 즉시 pass-through.
# /init-dcness 로 활성화. 미활성 프로젝트에선 hook 자체가 no-op.
python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0

# bash 의 PPID = CC main process
CC_PID=$PPID

# Python 으로 stdin 처리 + 핸들러 호출 (silent — stdout 안 씀)
python3 -m harness.hooks session-start --cc-pid "$CC_PID"

# === plug-in update 알림 (1회 / 일 캐싱, #376) ===
# 외부 활성 프로젝트가 옛 dcness plug-in 버전 잔재로 운영 룰 drift 되는 문제 회피.
# main branch 의 plugin.json version 과 비교 → 다르면 알림 씀.
# gh CLI 부재 / API 실패 시 silent skip.
DCNESS_UPDATE_MSG=""
INSTALLED_VERSION=$(jq -r .version "${CLAUDE_PLUGIN_ROOT:-.}/.claude-plugin/plugin.json" 2>/dev/null || echo "")
if [[ -n "$INSTALLED_VERSION" && "$INSTALLED_VERSION" != "null" ]]; then
  CACHE_DIR="${HOME}/.claude/plugins/data/dcness-dcness"
  CACHE_FILE="${CACHE_DIR}/last-update-check.txt"
  CHECK_INTERVAL=86400  # 24h
  NOW=$(date +%s 2>/dev/null || echo 0)
  LAST_CHECK=0
  LATEST_VERSION=""

  if [[ -f "$CACHE_FILE" ]]; then
    LAST_CHECK=$(awk '{print $1}' "$CACHE_FILE" 2>/dev/null || echo 0)
    LATEST_VERSION=$(awk '{print $2}' "$CACHE_FILE" 2>/dev/null || echo "")
  fi

  # 캐시 stale (24h+) — gh api 로 main 의 plugin.json fetch
  if (( NOW > 0 && NOW - LAST_CHECK > CHECK_INTERVAL )); then
    FETCHED=$(gh api repos/alruminum/dcNess/contents/.claude-plugin/plugin.json --jq '.content' 2>/dev/null \
              | base64 -d 2>/dev/null \
              | jq -r '.version' 2>/dev/null \
              || echo "")
    if [[ -n "$FETCHED" && "$FETCHED" != "null" ]]; then
      mkdir -p "$CACHE_DIR" 2>/dev/null
      echo "$NOW $FETCHED" > "$CACHE_FILE" 2>/dev/null
      LATEST_VERSION="$FETCHED"
    fi
  fi

  # LATEST 가 INSTALLED 보다 semver 상 높을 때만 알림.
  # 단순 != 비교는 설치 버전이 더 높은 경우(update 직후 + stale 24h 캐시)에도
  # "0.4.0 → 0.3.0" 처럼 다운그레이드 권유로 오발화 → semver 대소로 방향 강제 (#593).
  if [[ -n "$LATEST_VERSION" && "$INSTALLED_VERSION" != "$LATEST_VERSION" ]]; then
    HIGHER=$(printf '%s\n%s\n' "$INSTALLED_VERSION" "$LATEST_VERSION" | sort -V | tail -1)
    if [[ "$HIGHER" == "$LATEST_VERSION" ]]; then
      DCNESS_UPDATE_MSG="[dcness update available: ${INSTALLED_VERSION} → ${LATEST_VERSION}. \`claude plugin update\` 권장 — 옛 운영 룰 잔재 회피]"
    fi
  fi
fi
export DCNESS_UPDATE_MSG

# 슬림 inject (#596) — SessionStart 는 *초기화 + 최소 활성 안내* 만 담당.
# 문서 진입 매트릭스 / 안티패턴 / soft 필수 / cost-aware 항목은 제거: 하네스 모델은
# "문서 선독 기반 compliance" 가 아니라 "hook 이 차단하고 그 자리에서 복구". 절차·라우팅은
# skill 진입 시 해당 skill 이 안내하고, 위반 복구 정보는 각 blocking hook 메시지가 제공한다.
python3 -c "
import json, os
update_msg = os.environ.get('DCNESS_UPDATE_MSG', '').strip()
header = (update_msg + '\n\n---\n\n') if update_msg else ''
msg = header + '''## [dcness 활성 환경]

첫 응답 첫 줄에 \`[dcness 활성 확인]\` 토큰 출력 (활성 신호 — 부재 시 사용자가 룰 미적용을 즉시 인지).

코드 hook 이 강제 영역만 차단한다. 위반하면 해당 hook 메시지가 그 자리에서 무엇을 고칠지 안내한다:
- 시퀀스 (sub-agent 호출 순서): catastrophic-gate
- 파일 경계 + 외부 mutation: file-guard
- 테스트 선행 (구현 전 테스트 먼저): tdd-guard
- run 종료 자동화: stop-end-run

hook 이 차단할 때만 그 메시지가 가리키는 doc/path 를 읽어 복구한다. SessionStart 에서 dcness 문서를 미리 통독하지 말 것 — 절차·라우팅은 skill 진입 시 해당 skill 이 안내한다.
'''
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': msg,
    }
}))
" 2>/dev/null

# 모든 실패는 silent
exit 0
