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

  # 버전 다르면 알림
  if [[ -n "$LATEST_VERSION" && "$INSTALLED_VERSION" != "$LATEST_VERSION" ]]; then
    DCNESS_UPDATE_MSG="[dcness update available: ${INSTALLED_VERSION} → ${LATEST_VERSION}. \`claude plugin update\` 권장 — 옛 운영 룰 잔재 회피]"
  fi
fi
export DCNESS_UPDATE_MSG

# 슬림 inject — dcness-rules.md 폐기 (PR-3). 매 세션 system-reminder 로 본문 자동 노출.
# 외부 plug-in 사용자가 매 세션 강제 영역 + 메인 Claude 필수 + 진입 매트릭스 인지.
python3 -c "
import json, os
update_msg = os.environ.get('DCNESS_UPDATE_MSG', '').strip()
header = (update_msg + '\n\n---\n\n') if update_msg else ''
msg = header + '''## [dcness 활성 환경]

첫 응답 첫 줄에 토큰 \`[dcness 활성 확인]\` 출력 의무.

### 강제 (코드 hook 차단)
- **시퀀스**: catastrophic 4 룰 = \`docs/plugin/hooks.md\` 의 catastrophic-gate.sh
- **접근 영역**: file 경계 + 인프라 차단 = \`harness/agent_boundary.py\` (권한 경계 코드 SSOT)
- 그 외 = agent 자율 (형식 / handoff / marker 강제 X)

### 메인 Claude 필수
- **채널 형식**: chat = 백틱 \`경로\` / 본문 = 마크다운 링크
- **md 300줄 cap** (loop-procedure.md 등 SSOT 일부 예외): \`agents/**\` / \`commands/*.md\` / \`docs/plugin/*.md\`
- **Step 7 회고 → 메모리 candidate emit** 의무 (없으면 \"없음\" 1줄)
- **cost-aware 행동** (#402): 큰 plan/docs 통째 read 회피 → grep + offset/limit. Bash output 길면 \`| head\` 잘라내기. sub-agent 위임 우선 (메인 직접 도구 ↓ → 메인 cache_read 누적 ↓)

### 안티패턴
- reactive cycle (신규 룰 전 기존 룰 검토)
- 강제 vs 권고 혼동 (catastrophic 만 block)
- agent 자율성 침해 (agent prompt 강제 형식 X)

### 작업 진입 매트릭스 (lazy — 통째 read 폐기, #400)
| 상황 | docs |
|---|---|
| catastrophic / loop 인덱스 | \`hooks.md\` 의 catastrophic-gate.sh + \`loop-procedure.md\` 의 한눈 인덱스 |
| Step 0~8 / echo / REDO | \`loop-procedure.md\` |
| agent 결론 → 다음 (라우팅) | 호출 skill 의 \`<skill>-routing.md\` |
| hook 시점 / 차단 | \`hooks.md\` |
| 이슈 lifecycle / PR | \`issue-lifecycle.md\` |
| 브랜치/커밋 네이밍 | \`git-spec.md\` |

skill 트리거 시 해당 skill 의 ## 사전 read 가 정확 경로 안내.
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
