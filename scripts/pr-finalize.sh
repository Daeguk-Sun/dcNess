#!/bin/bash
# dcness pr-finalize — PR 머지 + CI 대기 + origin/main ref 동기화 자동
#
# 한 명령으로 머지 절차 끝:
#   1. gh pr merge --auto --merge (auto-merge 토글 ON)
#   2. gh pr checks --watch (CI 결과 대기)
#   3. auto-merge 완료 대기 (GitHub 백그라운드 lag)
#   4. git fetch origin main (origin/main remote-tracking 만 갱신, refspec 없이)
#
# 사용:
#   pr-finalize.sh                # current branch 의 open PR 자동 검출
#   pr-finalize.sh <PR_NUMBER>    # 명시 PR 번호
#
# 안전:
#   - 현재 working tree dirty 면 sync skip 옵션 (Y/n 물음)
#   - CI FAIL 시 sync skip + 에러 코드
#   - 머지 안 됐으면 sync skip + 사용자 안내
#
# 멀티 worktree 호환:
#   - Step 4 는 `git fetch origin main` (refspec 없이) — 다른 worktree 가 main checkout 중이어도
#     origin/main remote-tracking ref 만 갱신, 어느 worktree HEAD 와도 충돌 X.
#   - 새 branch 생성은 `scripts/pr-create.sh` 가 `origin/$BASE` 기반으로 처리하므로 base 항상 최신.
#
# stdout / stderr 분리:
#   - stdout = 최종 1줄 (PR URL + merged) — 메인 Claude / 사용자에게 필요한 정보.
#   - stderr = 진행 표시 / WARN / ERROR — 사용자가 보고 싶으면 보면 됨, 메인 컨텍스트엔 안 들어감.

set -e

PR="$1"

# PR 번호 자동 검출 — current branch
if [ -z "$PR" ]; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  if [ "$BRANCH" = "main" ]; then
    echo "[pr-finalize] ERROR: current branch = main. PR 번호 인자 박거나 feature branch 에서 호출" >&2
    exit 1
  fi
  PR=$(gh pr list --head "$BRANCH" --json number -q '.[0].number' 2>/dev/null)
  if [ -z "$PR" ] || [ "$PR" = "null" ]; then
    echo "[pr-finalize] ERROR: '$BRANCH' branch 의 open PR 없음. PR 먼저 생성 (gh pr create)" >&2
    exit 1
  fi
  echo "[pr-finalize] current branch '$BRANCH' → PR #$PR 자동 검출" >&2
fi

# working tree dirty check
if [ -n "$(git status --porcelain)" ]; then
  echo "[pr-finalize] WARN: working tree dirty — fetch sync 영향은 없지만 다음 작업 시 충돌 위험" >&2
  git status --short >&2
  echo "[pr-finalize] 계속 진행 (auto-merge 만, sync skip) Y/n? " >&2
  read -r reply
  if [ "$reply" != "Y" ] && [ "$reply" != "y" ]; then
    exit 1
  fi
  SKIP_SYNC=true
fi

# Step 1: auto-merge 토글
echo "[pr-finalize] PR #$PR — auto-merge 토글 ON" >&2
gh pr merge "$PR" --auto --merge >&2

# Step 2: CI 결과 대기
echo "[pr-finalize] CI 결과 대기 (gh pr checks --watch)" >&2
if ! gh pr checks "$PR" --watch >&2; then
  echo "[pr-finalize] ERROR: CI FAIL — 머지 안 됨. sync skip" >&2
  exit 1
fi

# Step 3: auto-merge 완료 대기 (GitHub 백그라운드)
echo "[pr-finalize] auto-merge 완료 대기" >&2
STATE=""
for i in 1 2 3 4 5 6 7 8; do
  STATE=$(gh pr view "$PR" --json state -q .state 2>/dev/null)
  if [ "$STATE" = "MERGED" ]; then
    break
  fi
  sleep 3
done

if [ "$STATE" != "MERGED" ]; then
  echo "[pr-finalize] WARN: PR #$PR 머지 안 됐음 (state=$STATE). branch protection 미충족 또는 review 필요 가능. 수동 확인:" >&2
  echo "  gh pr view $PR" >&2
  exit 1
fi

# Step 4: origin/main ref 동기화 (refspec 없이 fetch — worktree 호환)
PR_URL=$(gh pr view "$PR" --json url -q .url 2>/dev/null)

if [ "${SKIP_SYNC:-}" = "true" ]; then
  echo "[pr-finalize] origin/main 동기화 skip (working tree dirty)" >&2
  echo "[pr-finalize] PR #$PR merged · $PR_URL"
  exit 0
fi

echo "[pr-finalize] origin/main ref 동기화" >&2
if ! git fetch origin main --quiet; then
  echo "[pr-finalize] ERROR: git fetch origin main 실패 (네트워크 / 권한)" >&2
  exit 1
fi

echo "[pr-finalize] PR #$PR merged · $PR_URL"
