#!/usr/bin/env bash
# migrate_stories_to_new_format.sh
#
# 옛 stories.md 양식 (대상 화면·컴포넌트 / 동작 명세 / 수용 기준 + task [ ]/[x] 행)
# 을 새 양식 (As a / I want / So that + "**완료 시 확인 가능한 동작**:" 한 줄, user story 중심)
# 으로 변환 검사·report.
#
# 본 스크립트 = *report only* (자동 변환 X). 사용자가 직접 patch 결정.
# 옛 양식 잔재 = 그대로 허용 (skills/spec/spec-stories-reference.md 구버전 호환성 정합).
# 새 양식 변환 원하는 사용자만 본 스크립트로 *변환 대상 line* 식별 후 수동 patch.
#
# Usage:
#   bash scripts/migrate_stories_to_new_format.sh <stories.md 경로>
#   bash scripts/migrate_stories_to_new_format.sh docs/epics/epic-01-*/stories.md

set -euo pipefail

STORIES_FILE="${1:-}"

if [ -z "$STORIES_FILE" ]; then
  echo "Usage: $0 <stories.md 경로>" >&2
  exit 2
fi

if [ ! -f "$STORIES_FILE" ]; then
  echo "[migrate] 파일 부재: $STORIES_FILE" >&2
  exit 2
fi

echo "[migrate] 분석 대상: $STORIES_FILE"
echo

# 1. 옛 섹션 마커 식별 — 새 양식에 없는 표현
OLD_MARKERS=(
  '대상 화면·컴포넌트'
  '대상 화면'
  '동작 명세'
  '수용 기준 \(Story 단위\)'
  '수용 기준:'
)

FOUND_OLD=0
for marker in "${OLD_MARKERS[@]}"; do
  count=$(grep -c -E "\\*\\*$marker" "$STORIES_FILE" 2>/dev/null || echo 0)
  if [ "$count" -gt 0 ]; then
    echo "  [옛 양식] '$marker' 매치 $count 건:"
    grep -n -E "\\*\\*$marker" "$STORIES_FILE" | head -10
    echo
    FOUND_OLD=$((FOUND_OLD + count))
  fi
done

# 2. task 체크박스 행 식별 — 새 양식엔 쓰지 않음
TASK_LINES=$(grep -c -E '^\s*-\s*\[[ x]\]\s+[0-9]+' "$STORIES_FILE" 2>/dev/null || echo 0)
if [ "$TASK_LINES" -gt 0 ]; then
  echo "  [옛 양식] task 체크박스 행 $TASK_LINES 건:"
  grep -n -E '^\s*-\s*\[[ x]\]\s+[0-9]+' "$STORIES_FILE" | head -10
  echo
fi

# 3. 결과 안내
if [ "$FOUND_OLD" = "0" ] && [ "$TASK_LINES" = "0" ]; then
  echo "[migrate] $STORIES_FILE = 이미 새 양식 (옛 잔재 0 건). 변환 불필요."
  exit 0
fi

echo "[migrate] 발견: 옛 양식 마커 $FOUND_OLD 건 + task 체크박스 $TASK_LINES 건"
echo
echo "변환 가이드:"
echo "  1. 위 line 번호의 옛 섹션 (\\*\\*대상 화면·컴포넌트\\*\\* / \\*\\*동작 명세\\*\\* / \\*\\*수용 기준\\*\\*) 제거"
echo "  2. task 체크박스 행 (- [ ] / - [x] NN-*.md) 제거 — 새 양식엔 쓰지 않음"
echo "  3. Story 본문은 \"As a / I want / So that\" + \"**완료 시 확인 가능한 동작**:\" 한 줄만 남김"
echo "  4. Epic 헤더에는 \"완료 기준\" (검증 가능한 조건) 추가 — skills/spec/spec-stories-reference.md 의 stories.md 산출물 참조"
echo
echo "자동 변환 X — 사용자가 직접 patch (Edit / sed). 변환 후 /tech-review 권고 (기술 의존 검증)."
echo
echo "참조: skills/spec/spec-stories-reference.md 의 stories.md 산출물 (새 양식 정의)"

exit 0
