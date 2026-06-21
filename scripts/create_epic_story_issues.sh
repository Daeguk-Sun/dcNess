#!/bin/bash
# dcness create-epic-story-issues — PRD + stories.md 보고 GitHub epic + story 이슈 + sub-issue 연결 일괄 등록
#
# 한 명령으로:
#   1. stories.md parse — epic + Story N 추출
#   2. milestone number 조회 (Epics / Story)
#   3. epic 이슈 1 생성 → stories.md 에 번호 씀
#   4. story 이슈 N 순차 생성 → stories.md 에 번호 + 하단 표 씀
#   5. sub-issue API 호출 (epic ↔ story N 연결, GitHub native sub-issue API)
#   6. GitHub Project 보드 등록 (Status=Todo, IssueType=epic/story, Priority=major) — 좌표 있을 때
#   7. 결과 prose 출력
#
# 보드 등록은 비대화형 best-effort: 좌표(--project/--owner, DCNESS_PROJECT_* env,
# gh variable) 를 못 구하면 보드 등록만 skip 하고 이슈는 항상 생성한다. 대화형 보드
# 셋업(없으면 만들지 물어보기)은 메인 Claude 가 이 스크립트 호출 전에 담당한다.
#
# SSOT: docs/plugin/issue-lifecycle.md 의 이슈 계층 + GitHub Project lifecycle
#
# 사용:
#   create_epic_story_issues.sh docs/epics/epic-NN-<slug>/stories.md   # epic 단위 (표준)
#   create_epic_story_issues.sh /abs/path/docs/epics/epic-NN-<slug>/stories.md
#
# 표준 위치: epic 단위 폴더 안 stories.md. root docs/stories.md 기본값은 없다.
#
# 의존: gh CLI, jq, bash. dcness plug-in 활성 프로젝트 안에서 호출.

set -e

# 인자 파싱 — positional stories.md + 선택 --project/--owner (보드 좌표 명시).
STORIES=""
PROJECT_NUMBER=""
PROJECT_OWNER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT_NUMBER="$2"; shift 2 ;;
    --owner) PROJECT_OWNER="$2"; shift 2 ;;
    *) STORIES="$1"; shift ;;
  esac
done

if [ -z "$STORIES" ]; then
  echo "[issue-create] ERROR: stories.md 경로 인자 필요 — 예: docs/epics/epic-NN-<slug>/stories.md" >&2
  exit 2
fi
if ! printf '%s\n' "$STORIES" | grep -Eq '(^|/)docs/epics/[^/]+/stories\.md$'; then
  echo "[issue-create] ERROR: 비정식 stories 경로 — docs/epics/epic-NN-<slug>/stories.md 필요: $STORIES" >&2
  exit 2
fi
EPIC_SLUG=$(basename "$(dirname "$STORIES")")
if ! printf '%s\n' "$EPIC_SLUG" | grep -Eq '^epic-[0-9][0-9]-[a-z0-9-]+$'; then
  echo "[issue-create] ERROR: epic 디렉토리명은 epic-NN-<slug> 여야 함: $EPIC_SLUG" >&2
  exit 2
fi
if [ ! -f "$STORIES" ]; then
  echo "[issue-create] ERROR: $STORIES 부재. PRD/stories.md 먼저 작성 후 호출하세요." >&2
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null)
if [ -z "$REPO" ]; then
  echo "[issue-create] ERROR: gh CLI 또는 repo 인식 실패. 'gh auth login' + git remote 확인." >&2
  exit 1
fi

# 보드 좌표 조회 — 플래그 → env → gh variable (= CI vars 와 단일 SSOT) → owner fallback = repo owner.
# 전부 non-fatal: 좌표를 못 구해도 이슈 생성은 막지 않는다 (보드 등록만 skip).
if [ -z "$PROJECT_NUMBER" ]; then PROJECT_NUMBER="${DCNESS_PROJECT_NUMBER:-}"; fi
if [ -z "$PROJECT_NUMBER" ]; then PROJECT_NUMBER="$(gh variable get DCNESS_PROJECT_NUMBER 2>/dev/null || true)"; fi
if [ -z "$PROJECT_OWNER" ]; then PROJECT_OWNER="${DCNESS_PROJECT_OWNER:-}"; fi
if [ -z "$PROJECT_OWNER" ]; then PROJECT_OWNER="$(gh variable get DCNESS_PROJECT_OWNER 2>/dev/null || true)"; fi
if [ -z "$PROJECT_OWNER" ]; then PROJECT_OWNER="${REPO%%/*}"; fi

LIFECYCLE_MJS="$(dirname "$0")/github_project_lifecycle.mjs"

# register_board [mode] — 생성/backfill 한 epic+story 이슈를 GitHub Project 보드에 등록.
# epic → IssueType=epic / story → IssueType=story. 신규 등록 시 Status=Todo, Priority=major.
# mode="backfill" (멱등 재실행) → --preserve-existing: 이미 보드에 있는 item 의 triage 상태
#   (In progress/Done/바뀐 priority)를 Todo/major 로 되돌리지 않고 보존, 비어있는 필드만 채움 (#669).
# mode="fresh" (기본, 새 이슈) → strict 등록 (Todo/major 강제 + 검증).
# 좌표 없으면 skip (이슈는 이미 생성됨). register-issue 실패는 흡수 + partial 보고 (이슈를 막지 않는다).
register_board() {
  local mode="${1:-fresh}"
  if [ -z "$PROJECT_NUMBER" ]; then
    echo "[issue-create] Project 보드 미연결 (번호 없음) — 보드 등록 skip. 이슈는 생성됨."
    echo "  보드 연결 후 backfill: --project <N> --owner <O> 로 재실행 또는 'gh variable set DCNESS_PROJECT_NUMBER --body <N>'."
    return 0
  fi
  local reg_ok=0 reg_total out failed="" preserve_flag="" note="신규 Status=Todo, Priority=major"
  if [ "$mode" = "backfill" ]; then
    preserve_flag="--preserve-existing"
    note="기존 triage 상태 보존, 빈 필드만 채움"
  fi
  reg_total=$((1 + ${#STORY_NUMS[@]}))
  echo "[issue-create] 보드 등록 ($mode) — Project #$PROJECT_NUMBER (owner=$PROJECT_OWNER), 대상 ${reg_total}건"
  if out=$(node "$LIFECYCLE_MJS" register-issue --repo "$REPO" --owner "$PROJECT_OWNER" --project "$PROJECT_NUMBER" --issue "$EPIC_NUM" --issue-type epic $preserve_flag --apply 2>&1); then
    reg_ok=$((reg_ok+1))
  else
    failed="$failed epic#$EPIC_NUM"
    echo "  WARN: epic #$EPIC_NUM 보드 등록 실패 — $(echo "$out" | tail -1)"
  fi
  for sn in "${STORY_NUMS[@]}"; do
    if out=$(node "$LIFECYCLE_MJS" register-issue --repo "$REPO" --owner "$PROJECT_OWNER" --project "$PROJECT_NUMBER" --issue "$sn" --issue-type story $preserve_flag --apply 2>&1); then
      reg_ok=$((reg_ok+1))
    else
      failed="$failed story#$sn"
      echo "  WARN: story #$sn 보드 등록 실패 — $(echo "$out" | tail -1)"
    fi
  done
  echo "[issue-create] 보드 등록 완료 — ${reg_ok}/${reg_total} 성공 ($note)"
  if [ "$reg_ok" -lt "$reg_total" ]; then
    echo "[issue-create] WARN: partial state — 등록 실패:$failed. 이슈는 생성됨, 보드는 미반영."
    echo "  보드/field 셋업 확인 후 재실행으로 backfill (이슈 생성은 멱등 skip, 보드만 재시도)."
  fi
  return 0
}

# 멱등성 — 이미 epic 번호 있으면 이슈 생성은 skip 하되, 보드 등록은 재시도 (backfill).
# 이슈 생성과 보드 등록을 분리: 첫 실행에서 보드 미연결로 등록을 못 했어도, 나중에
# 보드 연결 후 재실행하면 보드만 채울 수 있다 (getProjectItem 멱등이라 중복 없음).
if grep -qE '^\*\*GitHub Epic Issue:\*\* \[#[0-9]+\]' "$STORIES"; then
  echo "[issue-create] $STORIES 이미 epic 번호 있음 — 이슈 생성 skip, 보드 등록만 재시도 (backfill)"
  EPIC_NUM=$(grep -m1 -E '^\*\*GitHub Epic Issue:\*\* \[#[0-9]+\]' "$STORIES" | grep -oE '#[0-9]+' | head -1 | tr -d '#')
  STORY_NUMS=()
  while IFS= read -r _ln; do
    _n=$(echo "$_ln" | grep -oE '#[0-9]+' | head -1 | tr -d '#')
    [ -n "$_n" ] && STORY_NUMS+=("$_n")
  done < <(grep -E '^\*\*GitHub Issue:\*\* \[#[0-9]+\]' "$STORIES")
  register_board backfill
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
#   format1 (spec 신양식): "## Epic — <title>"  + "### Story N — <title>"  (h2 + h3)
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

# epic slug / milestone 은 path + frontmatter 가 진본이다. milestone path segment fallback 금지.
if ! printf '%s\n' "$EPIC_SLUG" | grep -Eq '^epic-[0-9][0-9]-[a-z0-9-]+$'; then
  echo "[issue-create] ERROR: epic 디렉토리명은 epic-NN-<slug> 여야 함: $EPIC_SLUG" >&2
  exit 1
fi

VNN=$(awk '
  /^milestone:[[:space:]]*v[0-9][0-9][[:space:]]*$/ {
    sub(/^milestone:[[:space:]]*/, "")
    print
    exit
  }
' "$STORIES")
if [ -z "$VNN" ]; then
  echo "[issue-create] ERROR: stories.md frontmatter milestone: vNN 필요" >&2
  exit 1
fi

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

# 보드 등록 — 생성한 epic+story 이슈를 GitHub Project 보드에 등록 (좌표 있을 때)
register_board

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
