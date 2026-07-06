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
    FETCHED=$(gh api repos/Daeguk-Sun/dcNess/contents/.claude-plugin/plugin.json --jq '.content' 2>/dev/null \
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

PROJECT_ROOT_FOR_DOCS=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
DOCS_INDEX="$PROJECT_ROOT_FOR_DOCS/docs/index.md"
# 구조 소스(cold) 절 — docs/index.md 유무·`## 진행 상태 · 다음 작업` 섹션 유무로 분기.
# 오케스트레이션 래퍼(트리거 어휘 + 단정 + focused preload)는 세 경우 공통이라 아래서
# 한 번만 조립한다. 'warm 인계' 로 지칭 — no-handoff 세션에서도 항상 주입되는 포인터라
# handoff 블록 헤더('대기 핸드오프')와 같은 문자열을 쓰면 그 부재를 검증하는 소비/부재
# 테스트를 회귀시키므로 다른 표현을 쓴다.
if [[ -f "$DOCS_INDEX" ]]; then
  if grep -Eq '^## 진행 상태 · 다음 작업[[:space:]]*$' "$DOCS_INDEX" 2>/dev/null; then
    DCNESS_NEXT_INDEX_CLAUSE='없으면 구조 소스(cold)로 `docs/index.md` 의 `## 진행 상태 · 다음 작업` 포인터와 `/next-work`(issue/label + phase 판정)를 화해시켜 phase 를 도출한다.'
  else
    DCNESS_NEXT_INDEX_CLAUSE='없으면 구조 소스(cold)로, 현재 `docs/index.md` 에 `## 진행 상태 · 다음 작업` 섹션이 없으므로 `/next-work`(issue/label + phase 판정)로 phase 를 도출한다. 필요하면 `/init-dcness` 재실행으로 섹션을 보강한다.'
  fi
else
  DCNESS_NEXT_INDEX_CLAUSE='없으면 구조 소스(cold)로, `docs/index.md` 가 없으므로 `/next-work`(issue/label + phase 판정)로 phase 를 도출한다. 필요하면 `/init-dcness` 로 project docs seed 를 설치한다.'
fi
DCNESS_NEXT_POINTER_MSG='"뭐하지 / 다음 일 / 남은 일 알려줘 / 이제 뭐해야하지 / 남은 일 브리핑 / 이어서" 처럼 다음·남은 일을 물으면: (1) 위에 warm 인계(이전 세션 /handoff)가 주입돼 있으면 그 다음 액션부터 이어간다. (2) '"$DCNESS_NEXT_INDEX_CLAUSE"' (3) 소스를 종합해 다음 액션 1개를 단정한다 — 메뉴 나열이 아니라 `/design <epic-path>` · `/impl` · 특정 story 중 하나 + 근거. 남은 일 전체를 물으면 `/next-work` 계층(L1>L2>L3)으로 함께 브리핑한다. (4) 그 액션이 가리키는 문서(해당 epic stories / prd 관련 절 / 설계 산출물 유무 / 리팩터 base 브랜치)만 focused preload 해 바로 착수한다. SessionStart 통독 금지 — preload 는 이 질의(또는 skill 진입) 시점에만.'
export DCNESS_NEXT_POINTER_MSG

# === 대기 핸드오프 (warm 레이어) ===
# 이전 세션이 /handoff 로 남긴 인계 문서가 있으면 archive 로 먼저 옮겨 원자적으로
# 소비(claim)한 뒤 그 내용을 additionalContext 최상단에 주입한다. mv(rename)를 read
# 보다 선행하므로 병렬 peer 세션 중 rename 에 성공한 first-consumer 만 내용을 얻어
# 단일 소비자 계약을 만족한다. 소비된 파일은 archive 에 보존(무손실)돼 다음다음 세션에
# stale 재주입되지 않는다. 파일 부재 시 아무 동작도 하지 않아 훅은 기존 동작 그대로다.
# 쓰기 경로(commands/handoff.md)도 같은 repo 루트를 써 서브디렉토리 실행에도 정합한다.
# `.dcness-work/` 는 untracked·writable 이므로 심어진 심링크를 따라가 임의 로컬 파일(.env
# 등)을 컨텍스트로 유출하지 않도록, 심링크가 아닌 정규 파일일 때만 claim/read 한다.
DCNESS_HANDOFF_MSG=""
HANDOFF_ACTIVE="$PROJECT_ROOT_FOR_DOCS/.dcness-work/handoffs/next-session.md"
if [[ -f "$HANDOFF_ACTIVE" && ! -L "$HANDOFF_ACTIVE" && -s "$HANDOFF_ACTIVE" ]]; then
  HANDOFF_ARCHIVE_DIR="$PROJECT_ROOT_FOR_DOCS/.dcness-work/handoffs/archive"
  mkdir -p "$HANDOFF_ARCHIVE_DIR" 2>/dev/null
  # 파일명에 프로세스 PID 를 붙여 같은 초에 소비되는 서로 다른 handoff 끼리 archive
  # 파일명이 충돌해 덮어써지는(무손실 위반) 것을 막는다. 세션마다 별 프로세스라 PID 는
  # 서로 다르고, 동일 src 를 노리는 병렬 mv 는 rename 원자성으로 하나만 성공한다.
  HANDOFF_CLAIMED="$HANDOFF_ARCHIVE_DIR/$(date +%Y%m%d-%H%M%S)-$$.md"
  # mv(rename)는 심링크를 따라가지 않으므로 check 이후 심링크로 교체되는 TOCTOU 도
  # archived 사본을 read 전 재확인해 차단한다.
  if mv "$HANDOFF_ACTIVE" "$HANDOFF_CLAIMED" 2>/dev/null \
     && [[ -f "$HANDOFF_CLAIMED" && ! -L "$HANDOFF_CLAIMED" ]]; then
    # slim-inject 보호 + exec env 한도 회피 — 상한 초과 시 전문을 주입하지 않고
    # archive 전문을 가리키는 포인터만 넣는다(무손실: 전문은 archive 사본에 보존).
    HANDOFF_MAX_BYTES=16384
    HANDOFF_BYTES=$(wc -c < "$HANDOFF_CLAIMED" 2>/dev/null | tr -d '[:space:]')
    HANDOFF_BYTES=${HANDOFF_BYTES:-0}
    if [[ "$HANDOFF_BYTES" -gt "$HANDOFF_MAX_BYTES" ]]; then
      DCNESS_HANDOFF_MSG="대기 핸드오프가 너무 큼(${HANDOFF_BYTES}B > ${HANDOFF_MAX_BYTES}B) — slim-inject 보호를 위해 전문 주입 생략. 다음 파일을 직접 읽고 시작할 것: ${HANDOFF_CLAIMED}"
    else
      DCNESS_HANDOFF_MSG=$(cat "$HANDOFF_CLAIMED" 2>/dev/null || echo "")
    fi
  fi
fi
export DCNESS_HANDOFF_MSG

# 슬림 inject (#596) — SessionStart 는 *초기화 + 최소 활성 안내* 만 담당.
# 문서 진입 매트릭스 / 안티패턴 / soft 필수 / cost-aware 항목은 제거: 하네스 모델은
# "문서 선독 기반 compliance" 가 아니라 "hook 이 차단하고 그 자리에서 복구". 절차·분기는
# skill 진입 시 해당 skill 이 안내하고, 위반 복구 정보는 각 blocking hook 메시지가 제공한다.
python3 -c "
import json, os
update_msg = os.environ.get('DCNESS_UPDATE_MSG', '').strip()
next_pointer_msg = os.environ.get('DCNESS_NEXT_POINTER_MSG', '').strip()
handoff_msg = os.environ.get('DCNESS_HANDOFF_MSG', '').strip()
handoff_block = ''
if handoff_msg:
    handoff_block = (
        '## ⚠️ 대기 핸드오프 — 이것부터 읽고 시작\n\n'
        '이전 세션이 /handoff 로 남긴 인계다. 다음 액션부터 확인하고, 상세는 포인터를 질의 시점에 lazy 로드한다.\n\n'
        + handoff_msg + '\n\n---\n\n'
    )
header = (update_msg + '\n\n---\n\n') if update_msg else ''
msg = handoff_block + header + f'''## [dcness 활성 환경]

첫 응답 첫 줄에 \`[dcness 활성 확인]\` 토큰 출력 (활성 신호 — 부재 시 사용자가 룰 미적용을 즉시 인지).

코드 hook 이 강제 영역만 차단한다. 위반하면 해당 hook 메시지가 그 자리에서 무엇을 고칠지 안내한다:
- 시퀀스 (sub-agent 호출 순서): 순서 차단 훅(catastrophic-gate)
- 파일 경계 + 외부 상태 변경: file-guard
- 테스트 선행 (구현 전 테스트 먼저): tdd-guard
- run 종료 자동화: stop-end-run

{next_pointer_msg}

hook 이 차단할 때만 그 메시지가 가리키는 doc/path 를 읽어 복구한다. SessionStart 에서 dcness 문서를 미리 통독하지 말 것 — 절차·분기는 skill 진입 시 해당 skill 이 안내한다.
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
