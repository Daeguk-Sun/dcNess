#!/bin/bash
# dcness create-epic-story-issues — PRD + stories.md 보고 GitHub epic + story 이슈 + sub-issue 연결 일괄 등록
#
# 한 명령으로:
#   1. stories.md parse — epic + Story N 추출
#   2. milestone number 조회 (Epics / Story)
#   3. epic 이슈 1 생성 → stories.md 에 번호 씀
#   4. story 이슈 N 순차 생성 → stories.md 에 번호 + 하단 표 씀
#   5. sub-issue API 호출 (epic ↔ story N 연결, GitHub native sub-issue API)
#   6. 결과 prose 출력
#
# SSOT: docs/plugin/issue-lifecycle.md 의 이슈 계층
#
# 사용:
#   create_epic_story_issues.sh docs/milestones/vNN/epics/epic-NN-<slug>/stories.md   # epic 단위 (표준)
#   create_epic_story_issues.sh path/to/stories.md                                    # 명시 경로
#
# 표준 위치 (이슈 #511): epic 단위 폴더 안 stories.md. 옛 root 단위 docs/stories.md 도
# 인자로 명시하면 동작 (호환 영역).
#
# 의존: gh CLI, jq, bash. dcness plug-in 활성 프로젝트 안에서 호출.

set -e

STORIES="${1:-docs/stories.md}"

if [ ! -f "$STORIES" ]; then
  echo "[issue-create] ERROR: $STORIES 부재. PRD/stories.md 먼저 작성 후 호출하세요." >&2
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null)
if [ -z "$REPO" ]; then
  echo "[issue-create] ERROR: gh CLI 또는 repo 인식 실패. 'gh auth login' + git remote 확인." >&2
  exit 1
fi

# 멱등성 — 이미 epic 번호 적혀있으면 skip
if grep -qE '^\*\*GitHub Epic Issue:\*\* \[#[0-9]+\]' "$STORIES"; then
  echo "[issue-create] $STORIES 이미 epic 번호 있음 — skip"
  echo "  멱등성 재실행 필요 시 stories.md 상단 'GitHub Epic Issue' 라인 제거 후 재호출"
  exit 0
fi

# 마일스톤 title 조회 (issue-lifecycle.md 의 마일스톤 파라미터)
# 주의: gh CLI 의 `--milestone` 옵션은 *name* 만 받음 (number 거부). gh issue create --help → `-m, --milestone name`.
# 따라서 milestone title 그대로 추출 + `--milestone "$EPICS_MS"` 에 전달 (line 127, 174).
EPICS_MS=$(gh api "repos/$REPO/milestones" --jq '.[] | select(.title=="Epics") | .title' 2>/dev/null)
STORY_MS=$(gh api "repos/$REPO/milestones" --jq '.[] | select(.title=="Story") | .title' 2>/dev/null)

if [ -z "$EPICS_MS" ] || [ -z "$STORY_MS" ]; then
  echo "[issue-create] ERROR: 'Epics' 또는 'Story' 마일스톤 부재. GitHub repo 에 두 마일스톤 생성 후 재시도." >&2
  echo "  gh api repos/$REPO/milestones -X POST -f title=Epics" >&2
  echo "  gh api repos/$REPO/milestones -X POST -f title=Story" >&2
  exit 1
fi

# stories.md parse — 헤더 양식 auto-detect
# 두 양식 지원:
#   format1 (product-plan 신양식): "## Epic — <title>"  + "### Story N — <title>"  (h2 + h3)
#   format2 (jajang 등 기존 양식): "# Epic NN — <title>" + "## Story N — <title>"   (h1 + h2)
EPIC_HEADER_LINE=$(grep -m1 -E '^#+[[:space:]]+Epic([[:space:]]|—)' "$STORIES" || true)
if [ -z "$EPIC_HEADER_LINE" ]; then
  echo "[issue-create] ERROR: stories.md 에 Epic 헤더 부재 ('## Epic — ...' 또는 '# Epic NN — ...' 형식 필요)." >&2
  exit 1
fi

case "$EPIC_HEADER_LINE" in
  "## Epic —"*)
    EPIC_RE='^## Epic —'
    STORY_RE='^### Story [0-9]+ —'
    STORY_PREFIX='### Story'
    EPIC_TITLE=$(awk '/^## Epic —/{ sub(/^## Epic —[[:space:]]*/, ""); print; exit }' "$STORIES")
    ;;
  "# Epic "*)
    EPIC_RE='^# Epic [0-9]+ —'
    STORY_RE='^## Story [0-9]+ —'
    STORY_PREFIX='## Story'
    EPIC_TITLE=$(awk '/^# Epic [0-9]+ —/{ sub(/^# Epic [0-9]+ —[[:space:]]*/, ""); print; exit }' "$STORIES")
    ;;
  *)
    echo "[issue-create] ERROR: 알 수 없는 Epic 헤더 형식: $EPIC_HEADER_LINE" >&2
    echo "  지원 양식: '## Epic — <title>' (h2) 또는 '# Epic NN — <title>' (h1)" >&2
    exit 1
    ;;
esac

if [ -z "$EPIC_TITLE" ]; then
  echo "[issue-create] ERROR: Epic 제목 추출 실패 (헤더: $EPIC_HEADER_LINE)" >&2
  exit 1
fi

# epic slug 추정 (kebab-case, 한글 → kebab 어려우니 사용자 직접 박는 거 권장)
# stories.md frontmatter 또는 별도 marker 에서 epic_slug 추출 시도. 부재면 사용자에게 prose 명시.
EPIC_SLUG=$(grep -m1 -oE 'epic-NN-[a-z0-9-]+' "$STORIES" 2>/dev/null | head -1 || echo "")
if [ -z "$EPIC_SLUG" ]; then
  echo "[issue-create] WARN: stories.md 에 'epic-NN-<slug>' 라벨 마커 부재. 라벨 'epic-NN-...' 자동 생성 skip."
  echo "  사용자가 GitHub repo 라벨 'epic-NN-<slug>' 수동 생성 후 stories.md 갱신 권장."
fi

VNN=$(grep -m1 -oE 'v0[0-9]' "$STORIES" 2>/dev/null | head -1 || echo "v01")

# epic 이슈 생성
echo "[issue-create] epic 이슈 생성 — '$EPIC_TITLE'"
# 헤더 양식 분기 — epic 본문 = epic 헤더 ~ 첫 Story 헤더 사이
case "$EPIC_HEADER_LINE" in
  "## Epic —"*)
    EPIC_BODY=$(awk '/^## Epic —/{flag=1; next} /^### Story 1 —/{flag=0} flag' "$STORIES")
    ;;
  "# Epic "*)
    EPIC_BODY=$(awk '/^# Epic [0-9]+ —/{flag=1; next} /^## Story 1 —/{flag=0} flag' "$STORIES")
    ;;
esac

# **Base Branch:** 마커 read — stories.md 상단에 있으면 epic issue body 첫 줄로 미러링
BASE_BRANCH_LINE=$(grep -m1 -E '^\*\*Base Branch:\*\*[[:space:]]+' "$STORIES" || true)
if [ -n "$BASE_BRANCH_LINE" ]; then
  EPIC_BODY="${BASE_BRANCH_LINE}

${EPIC_BODY}"
  echo "[issue-create] Base Branch 마커 감지 — epic body 미러링: $BASE_BRANCH_LINE"
fi

LABELS_ARGS=( -l epic -l "$VNN" )
if [ -n "$EPIC_SLUG" ]; then
  LABELS_ARGS+=( -l "$EPIC_SLUG" )
fi

EPIC_OUT=$(gh issue create \
  --title "[epic] $EPIC_TITLE" \
  --body "$EPIC_BODY" \
  --milestone "$EPICS_MS" \
  "${LABELS_ARGS[@]}" 2>&1)
EPIC_NUM=$(echo "$EPIC_OUT" | grep -oE 'https://github.com/[^/]+/[^/]+/issues/[0-9]+' | tail -1 | grep -oE '[0-9]+$')
if [ -z "$EPIC_NUM" ]; then
  echo "[issue-create] ERROR: epic 이슈 생성 실패: $EPIC_OUT" >&2
  exit 1
fi
EPIC_URL="https://github.com/$REPO/issues/$EPIC_NUM"
echo "[issue-create] epic #$EPIC_NUM 생성 완료 — $EPIC_URL"

# stories.md 상단에 epic 번호 씀
sed -i.bak "s|^\*\*GitHub Epic Issue:\*\*.*\$|**GitHub Epic Issue:** [#$EPIC_NUM]($EPIC_URL)|" "$STORIES" 2>/dev/null
if ! grep -qE '^\*\*GitHub Epic Issue:\*\* \[' "$STORIES"; then
  # 라인 부재 시 Epic 헤더 직전에 씀 (양식 분기)
  awk -v line="**GitHub Epic Issue:** [#$EPIC_NUM]($EPIC_URL)" -v epic_re="$EPIC_RE" '
    $0 ~ epic_re && !done { print line; print ""; done=1 }
    { print }
  ' "$STORIES" > "$STORIES.tmp" && mv "$STORIES.tmp" "$STORIES"
fi
rm -f "$STORIES.bak"

# story 이슈 N 순차 생성
STORY_IDS=()
STORY_NUMS=()
STORY_TITLES=()

# Story 헤더 + 번호 추출 — STORY_PREFIX = "### Story" (h3) 또는 "## Story" (h2)
while IFS= read -r STORY_LINE; do
  STORY_N=$(echo "$STORY_LINE" | grep -oE 'Story [0-9]+' | grep -oE '[0-9]+')
  STORY_TITLE=$(echo "$STORY_LINE" | sed -E "s|^${STORY_PREFIX} $STORY_N —[[:space:]]*||")

  # story 본문 추출 (현재 Story 헤더부터 다음 Story 헤더 또는 파일 끝까지)
  STORY_BODY=$(awk -v target="${STORY_PREFIX} $STORY_N —" -v next_re="$STORY_RE" '
    $0 ~ target { flag=1; next }
    $0 ~ next_re && flag { flag=0 }
    flag { print }
  ' "$STORIES")

  echo "[issue-create] story $STORY_N 생성 — '$STORY_TITLE'"
  STORY_LABELS=( -l story -l "$VNN" )
  if [ -n "$EPIC_SLUG" ]; then
    STORY_LABELS+=( -l "$EPIC_SLUG" )
  fi

  STORY_OUT=$(gh issue create \
    --title "[story] $STORY_TITLE" \
    --body "$STORY_BODY" \
    --milestone "$STORY_MS" \
    "${STORY_LABELS[@]}" 2>&1)
  STORY_NUM=$(echo "$STORY_OUT" | grep -oE 'https://github.com/[^/]+/[^/]+/issues/[0-9]+' | tail -1 | grep -oE '[0-9]+$')
  if [ -z "$STORY_NUM" ]; then
    echo "[issue-create] ERROR: story $STORY_N 생성 실패: $STORY_OUT" >&2
    exit 1
  fi

  # story database id (sub-issue API 용 — .number 아님)
  STORY_ID=$(gh api "repos/$REPO/issues/$STORY_NUM" --jq '.id')
  STORY_URL="https://github.com/$REPO/issues/$STORY_NUM"

  STORY_NUMS+=("$STORY_NUM")
  STORY_IDS+=("$STORY_ID")
  STORY_TITLES+=("$STORY_TITLE")
  echo "  → #$STORY_NUM (id=$STORY_ID)"

  # stories.md 의 해당 Story 헤더 직하에 마커 씀 (이미 있으면 update) — STORY_PREFIX 동적
  python3 - "$STORIES" "$STORY_N" "$STORY_NUM" "$STORY_URL" "$STORY_PREFIX" <<'PYEOF'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
sn, num, url, prefix = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
text = p.read_text()
escaped = re.escape(prefix)
pattern = re.compile(rf'(^{escaped} {sn} — .*$)(\n+\*\*GitHub Issue:\*\*[^\n]*)?', re.MULTILINE)
marker = f'\n\n**GitHub Issue:** [#{num}]({url})'
def repl(m):
    return m.group(1) + marker
new = pattern.sub(repl, text, count=1)
p.write_text(new)
PYEOF

done < <(grep -E "$STORY_RE" "$STORIES")

# 포맷 SSOT = docs/plugin/git-spec.md 의 Story 이슈 (stories.md 하단 `## 관련 이슈` 테이블)
# 하단 ## 관련 이슈 테이블 씀
{
  echo ""
  echo "## 관련 이슈"
  echo ""
  echo "| 스토리 | GitHub Issue |"
  echo "|---|---|"
  echo "| Epic | [#$EPIC_NUM]($EPIC_URL) |"
  for i in "${!STORY_NUMS[@]}"; do
    n="$((i+1))"
    echo "| Story $n | [#${STORY_NUMS[$i]}](https://github.com/$REPO/issues/${STORY_NUMS[$i]}) |"
  done
} >> "$STORIES"

# sub-issue 연결 (issue-lifecycle.md 의 Sub-issue 연결)
echo "[issue-create] sub-issue 연결 — epic #$EPIC_NUM ↔ story N=${#STORY_IDS[@]}"
LINKED=0
for SID in "${STORY_IDS[@]}"; do
  if gh api -X POST "repos/$REPO/issues/$EPIC_NUM/sub_issues" -F sub_issue_id="$SID" >/dev/null 2>&1; then
    LINKED=$((LINKED+1))
  else
    echo "  WARN: story id=$SID sub-issue 연결 실패 (이미 연결됐을 가능성)"
  fi
done
echo "[issue-create] sub-issue 연결 완료 — $LINKED / ${#STORY_IDS[@]}"

# 결과 prose
echo ""
echo "[issue-create] 완료 — epic #$EPIC_NUM + story ${#STORY_NUMS[@]}개"
echo "  epic: $EPIC_URL"
for i in "${!STORY_NUMS[@]}"; do
  n="$((i+1))"
  echo "  Story $n (#${STORY_NUMS[$i]}): ${STORY_TITLES[$i]}"
done
echo ""
echo "  stories.md 갱신 완료 — git diff $STORIES 로 확인 후 commit."
