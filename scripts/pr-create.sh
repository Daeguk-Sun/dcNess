#!/bin/bash
# dcness pr-create — branch + add + commit + push + pr create 통합 (#446 Step 4 회수)
#
# build-worker prose 의 PR body + commit message 초안을 임시 파일로 받아
# git branch 생성 + add + commit + push + gh pr create 까지 한 명령으로 처리.
# 머지는 pr-reviewer LGTM 후 별 명령 (scripts/pr-finalize.sh) 호출.
#
# 사용:
#   scripts/pr-create.sh \
#     --branch <branch-name> \
#     --base <base-ref> \
#     --title "..." \
#     --body-file <path> \
#     --commit-msg-file <path>
#
# 동작:
#   1. git checkout -b <branch> <base>     (이미 branch 위면 skip)
#   2. git add -A
#   3. git commit -F <commit-msg-file>
#   4. git push -u origin <branch>
#   5. gh pr create --base <base> --title "..." --body-file <body-file>
#
# 출력: PR URL 마지막 줄
#
# 안전:
#   - 인자 누락 시 abort
#   - working tree clean (변경 없음) 시 abort
#   - branch 이미 존재 (다른 위치) 시 abort

set -e

BRANCH=""
BASE=""
TITLE=""
BODY_FILE=""
COMMIT_MSG_FILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --branch)          BRANCH="$2"; shift 2 ;;
    --base)            BASE="$2"; shift 2 ;;
    --title)           TITLE="$2"; shift 2 ;;
    --body-file)       BODY_FILE="$2"; shift 2 ;;
    --commit-msg-file) COMMIT_MSG_FILE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      echo "[pr-create] ERROR: 알 수 없는 인자: $1" >&2
      exit 2
      ;;
  esac
done

# 인자 검증
for var in BRANCH BASE TITLE BODY_FILE COMMIT_MSG_FILE; do
  if [ -z "${!var}" ]; then
    echo "[pr-create] ERROR: --${var,,} 인자 누락" >&2
    exit 2
  fi
done

if [ ! -f "$BODY_FILE" ]; then
  echo "[pr-create] ERROR: body-file 부재: $BODY_FILE" >&2
  exit 2
fi
if [ ! -f "$COMMIT_MSG_FILE" ]; then
  echo "[pr-create] ERROR: commit-msg-file 부재: $COMMIT_MSG_FILE" >&2
  exit 2
fi

# working tree 변경 확인
if [ -z "$(git status --porcelain)" ]; then
  echo "[pr-create] ERROR: working tree 에 변경 없음 — commit 할 게 없음" >&2
  exit 1
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Step 1: branch 처리 — origin/$BASE 기반으로 만들어 worktree 환경에서도 stale base 회피
if [ "$CURRENT_BRANCH" = "$BRANCH" ]; then
  echo "[pr-create] 이미 '$BRANCH' 위에 있음 — checkout skip" >&2
elif git rev-parse --verify --quiet "$BRANCH" >/dev/null; then
  echo "[pr-create] ERROR: '$BRANCH' branch 가 이미 존재 (다른 위치). 다른 이름 사용 또는 기존 branch 정리" >&2
  exit 1
else
  echo "[pr-create] git fetch origin $BASE + git checkout -b $BRANCH --no-track origin/$BASE" >&2
  if ! git fetch origin "$BASE" --quiet; then
    echo "[pr-create] WARN: git fetch origin $BASE 실패 — 로컬 origin/$BASE ref 사용 (stale 가능)" >&2
  fi
  # --no-track: 새 branch 가 origin/$BASE 를 upstream 으로 잡지 않도록 명시 차단
  #             (사용자가 우연히 git push 만 호출했을 때 base branch 로 push 시도 방지).
  #             이후 Step 4 의 `git push -u origin $BRANCH` 가 upstream 을 origin/$BRANCH 로 설정.
  git checkout -b "$BRANCH" --no-track "origin/$BASE"
fi

# Step 2~3: add + commit
echo "[pr-create] git add -A + commit" >&2
git add -A
git commit -F "$COMMIT_MSG_FILE" >&2

# Step 4: push
echo "[pr-create] git push -u origin $BRANCH" >&2
git push -u origin "$BRANCH" >&2

# Step 5: PR 생성
echo "[pr-create] gh pr create --base $BASE" >&2
PR_URL=$(gh pr create --base "$BASE" --title "$TITLE" --body-file "$BODY_FILE")

echo "[pr-create] 완료 — PR 생성: $PR_URL" >&2
echo "$PR_URL"
