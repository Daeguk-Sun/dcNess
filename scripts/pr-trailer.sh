#!/bin/bash
# dcness pr-trailer — impl task 의 story key 기반 PR body 트레일러 자동 생성
#
# 룰 SSOT = docs/plugin/git-spec.md 의 "PR 트레일러 (Part of / Closes)" 절.
# 본 스크립트는 그 적용 절차(수동 bash recipe)의 한 명령 구현이다 — 메인이 PR body
# 작성 직전 frontmatter 와 stories.md 를 손으로 읽고 분기하던 수작업을 대체한다.
# task 파일은 story grouping key 를 찾는 입력이며 task_index 는 PR 경계가 아니다.
#
# 사용:
#   scripts/pr-trailer.sh <impl-task-file>          # 트레일러 블록을 stdout 출력
#
# stdout / stderr 분리:
#   - stdout = 트레일러 블록만 — PR body 에 그대로 붙임.
#   - stderr = 판정 근거 / WARN / ERROR.
#
# 분기 (git-spec 기본 룰):
#   - story: 공통 → Part of #<epic>
#   - story PR → Closes #<story> (+ epic 마지막 story 면 Closes #<epic>)
#   - malformed (숫자 story 인데 task_index 가 i/total 형식 아님) → exit 1
#
# story PR 생성 시 stack base 는 dcness-story-runner next-action 의 pr_base 가
# 소유한다. merge 직전 main retarget/rebase 뒤 이 Closes trailer 가 발동한다.

set -e

if [ "$1" = "--base" ]; then
  echo "[pr-trailer] ERROR: --base 는 폐기됨 — dcness-story-runner next-action 의 pr_base 를 사용할 것" >&2
  exit 2
fi

TASK_FILE="$1"
if [ -z "$TASK_FILE" ]; then
  echo "[pr-trailer] ERROR: impl task 파일 경로 인자 필요 — 사용법: pr-trailer.sh [--base] <impl-task-file>" >&2
  exit 2
fi
if [ ! -f "$TASK_FILE" ]; then
  echo "[pr-trailer] ERROR: impl task 파일 부재: $TASK_FILE" >&2
  exit 2
fi

# stories.md 위치 — epic 단위 (impl/ 의 상위 디렉토리)
STORIES="$(dirname "$(dirname "$TASK_FILE")")/stories.md"
if ! printf '%s\n' "$STORIES" | grep -Eq '(^|/)docs/epics/[^/]+/stories\.md$'; then
  echo "[pr-trailer] ERROR: 비정식 impl task 경로 — docs/epics/epic-NN-<slug>/impl/NN-*.md 필요: $TASK_FILE" >&2
  exit 1
fi
if [ ! -f "$STORIES" ]; then
  echo "[pr-trailer] ERROR: stories.md 미발견 — $(dirname "$(dirname "$TASK_FILE")")/stories.md 필요" >&2
  exit 1
fi

if grep -qE '^\*\*Base Branch:\*\*' "$STORIES" 2>/dev/null; then
  echo "[pr-trailer] ERROR: 폐기된 Base Branch 마커가 $STORIES 에 남아 있음 — 마커를 제거하고 story-runner stack topology 를 사용할 것" >&2
  exit 1
fi

STORY_NUM=$(awk '/^story:/ {gsub(/[",]/,""); print $2; exit}' "$TASK_FILE")
TASK_INDEX=$(awk '/^task_index:/ {gsub(/[",]/,""); print $2; exit}' "$TASK_FILE")

EPIC_ISSUE=$(grep -m1 -E '^\*\*GitHub Epic Issue:\*\*' "$STORIES" 2>/dev/null | grep -oE '#[0-9]+' | head -1 | tr -d '#' || true)

# story 이슈 번호 — `### Story <N>` 섹션 안의 첫 `**GitHub Issue:**` 마커
STORY_ISSUE=""
if [ "$STORY_NUM" != "공통" ] && [ -n "$STORY_NUM" ]; then
  STORY_ISSUE=$(awk -v n="$STORY_NUM" '
    $0 ~ ("^### Story " n "([^0-9]|$)") {insec=1; next}
    insec && /^### Story / {insec=0}
    insec && /^\*\*GitHub Issue:\*\*/ {
      if (match($0, /#[0-9]+/)) { print substr($0, RSTART+1, RLENGTH-1); exit }
    }
  ' "$STORIES")
fi

if [ "$STORY_NUM" = "공통" ]; then
  # 공통 task group — 별도 story issue 가 없으므로 epic 에 연결한다.
  if [ -z "$EPIC_ISSUE" ]; then
    echo "[pr-trailer] ERROR: 공통 task 인데 $STORIES 에 '**GitHub Epic Issue:** #N' 마커 미해결 — 빈 'Part of #' 방지 위해 정지" >&2
    exit 1
  fi
  TRAILER="Part of #${EPIC_ISSUE}"
  echo "[pr-trailer] 공통 task group → Part of #${EPIC_ISSUE}" >&2
elif printf '%s' "$TASK_INDEX" | grep -qE '^[0-9]+/[0-9]+$'; then
  if [ -z "$STORY_ISSUE" ]; then
    echo "[pr-trailer] ERROR: story $STORY_NUM 의 '**GitHub Issue:** #N' 마커를 $STORIES 에서 못 찾음 — 이슈 미등록이면 등록 후 재시도" >&2
    exit 1
  fi
  TRAILER="Closes #${STORY_ISSUE}"
  echo "[pr-trailer] story $STORY_NUM PR → Closes #${STORY_ISSUE}" >&2
  # epic 마지막 story 판정 — epic 라벨은 stories.md 디렉토리명(epic-NN-<slug>) 우선,
  # 없으면 epic 이슈의 라벨에서 조회. OPEN story 가 본 story 뿐이면 epic 도 동봉.
  EPIC_LABEL=$(basename "$(dirname "$STORIES")" | grep -E '^epic-[0-9]+-' || true)
  if [ -z "$EPIC_LABEL" ] && [ -n "$EPIC_ISSUE" ]; then
    EPIC_LABEL=$(gh issue view "$EPIC_ISSUE" --json labels -q '.labels[].name' 2>/dev/null | grep -E '^epic-[0-9]+-' | head -1 || true)
  fi
  if [ -n "$EPIC_LABEL" ] && [ -n "$EPIC_ISSUE" ]; then
    OPEN=$(gh issue list --label "$EPIC_LABEL" --milestone Story --state open --json number --jq 'length' 2>/dev/null || true)
    if [ "$OPEN" = "1" ]; then
      TRAILER="${TRAILER}
Closes #${EPIC_ISSUE}"
      echo "[pr-trailer] epic 마지막 story — Closes #${EPIC_ISSUE} 동봉" >&2
    elif [ -z "$OPEN" ]; then
      echo "[pr-trailer] WARN: epic 마지막 story 판정 불가 (gh issue list 실패) — Closes #${EPIC_ISSUE} 미동봉. 수동 확인: gh issue list --label $EPIC_LABEL --milestone Story --state open" >&2
    fi
  elif [ -n "$EPIC_ISSUE" ]; then
    echo "[pr-trailer] WARN: epic 라벨(epic-NN-<slug>) 미해결 — epic 마지막 story 판정 skip" >&2
  fi
else
  echo "[pr-trailer] ERROR: story=$STORY_NUM 인데 task_index='$TASK_INDEX' 가 i/total 도 공통(—)도 아님 — malformed/누락 가드, PR 생성 정지 (git-spec PR 트레일러 MUST)" >&2
  exit 1
fi

echo "$TRAILER"
