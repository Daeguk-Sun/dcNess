#!/bin/bash
# dcness pr-finalize — PR 머지 + CI 대기 + origin/main ref 동기화 자동
#
# pr-finalize 호출 = 머지 확정. 이 스크립트는 별도 최종 승인 UI 없이 merge 를 시도한다.
#
# 한 명령으로 머지 절차 끝:
#   1. gh pr merge --auto --merge (auto-merge 토글 ON)
#   2. gh pr checks --watch (CI 결과 대기)
#   3. auto-merge 완료 대기 (GitHub 백그라운드 lag)
#   4. git fetch origin main (origin/main remote-tracking 만 갱신, refspec 없이)
#   5. (통합 브랜치 sub-PR 만) PR body 의 close 선언 기반 issue close 보정
#
# 통합 브랜치 sub-PR (base ≠ default branch) 인지:
#   - CI 체크 0개를 정상으로 처리 — 검증 워크플로는 default branch 대상 PR 만 발동.
#   - GitHub auto-close 는 default branch 머지만 인식 → PR body 의 Closes/Fixes/Resolves
#     선언을 근거로 머지 후 gh issue close 보정 (git-spec "통합 브랜치 케이스" 절).
#     임의 직접 close 가 아니라 PR body 선언의 기계 보정이다.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/dcness-helper"

PR="$1"
BRANCH=""
MERGE_LOCK_TOKEN=""
MERGE_CLAIM_KEY=""

json_field() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"
}

record_pr_merged() {
  local pr_number="$1"
  local pr_url="$2"
  if ! "$HELPER" ledger-event pr_merged --pr "$pr_number" --url "$pr_url" >/dev/null 2>&1; then
    echo "[pr-finalize] WARN: ledger pr_merged 기록 실패 — active dcNess run 밖이면 정상" >&2
  fi
}

extract_close_issue_numbers() {
  awk '
    {
      line = $0
      lower = tolower(line)
      if (lower ~ /^[[:space:]]*(close[sd]?|fix(e[sd])?|resolve[sd]?)[[:space:]]+#[0-9]+([,[:space:]]+#?[0-9]+)*[[:space:]]*$/) {
        while (match(line, /#[0-9]+/)) {
          print substr(line, RSTART + 1, RLENGTH - 1)
          line = substr(line, RSTART + RLENGTH)
        }
      }
    }
  ' | sort -un
}

cleanup_merge_lock() {
  rc=$?
  if [ -n "$MERGE_LOCK_TOKEN" ]; then
    if [ -n "$MERGE_CLAIM_KEY" ]; then
      "$HELPER" merge-lock release \
        --token "$MERGE_LOCK_TOKEN" \
        --claim-key "$MERGE_CLAIM_KEY" \
        --state failed \
        --reason "pr-finalize exit $rc" >/dev/null 2>&1 || true
    else
      "$HELPER" merge-lock release \
        --token "$MERGE_LOCK_TOKEN" \
        --state failed \
        --reason "pr-finalize exit $rc" >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup_merge_lock EXIT

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

if [ -z "$BRANCH" ]; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
fi

# 통합 브랜치 sub-PR 판정 — base ≠ default branch
DEFAULT_REF=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)
if [ -z "$DEFAULT_REF" ]; then
  DEFAULT_REF=main
fi
BASE_REF=$(gh pr view "$PR" --json baseRefName -q .baseRefName 2>/dev/null || true)
if [ -z "$BASE_REF" ]; then
  BASE_REF="$DEFAULT_REF"
fi
INTEGRATION=false
if [ "$BASE_REF" != "$DEFAULT_REF" ]; then
  INTEGRATION=true
  echo "[pr-finalize] base=$BASE_REF ≠ default=$DEFAULT_REF — 통합 브랜치 sub-PR 모드" >&2
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

# Peer mode guard (#641): unregistered branches return mode=serial and keep the
# existing finalize path unchanged. Registered peer claims acquire a repo-level
# mutex and check same-story task_index order before any merge attempt.
echo "[pr-finalize] peer merge guard 확인" >&2
MERGE_LOCK_JSON=$("$HELPER" merge-lock acquire --branch "$BRANCH" --pr "$PR") || {
  echo "[pr-finalize] ERROR: peer merge guard 실패" >&2
  printf '%s\n' "$MERGE_LOCK_JSON" >&2
  exit 1
}
MERGE_LOCK_MODE=$(printf '%s\n' "$MERGE_LOCK_JSON" | json_field mode)
if [ "$MERGE_LOCK_MODE" = "peer" ]; then
  MERGE_LOCK_TOKEN=$(printf '%s\n' "$MERGE_LOCK_JSON" | json_field token)
  MERGE_CLAIM_KEY=$(printf '%s\n' "$MERGE_LOCK_JSON" | json_field claim_key)
  echo "[pr-finalize] peer merge lock 획득 — claim $MERGE_CLAIM_KEY" >&2
  echo "[pr-finalize] lock 이후 base/PR 상태 재확인" >&2
  git fetch origin main --quiet
  if ! gh pr update-branch "$PR" >&2; then
    echo "[pr-finalize] WARN: gh pr update-branch 실패 또는 불필요 — merge/check 단계에서 재검증" >&2
  fi
  if ! gh pr checks "$PR" >&2; then
    echo "[pr-finalize] WARN: 현재 CI 상태가 clean 이 아님 — --watch 단계에서 최종 판정" >&2
  fi
fi

# Step 1: auto-merge 토글
# PR 이 이미 clean status (CI 통과 + mergeable) 면 enablePullRequestAutoMerge mutation
# 이 "Pull request is in clean status" 로 거부 → 즉시 머지 fallback.
echo "[pr-finalize] PR #$PR — auto-merge 토글 ON" >&2
MERGE_ERR=$(gh pr merge "$PR" --auto --merge 2>&1 >/dev/null) || {
  if echo "$MERGE_ERR" | grep -q "clean status"; then
    echo "[pr-finalize] PR 이미 clean status — auto-merge enable 의미 없음, 즉시 머지 fallback" >&2
    gh pr merge "$PR" --merge >&2 || {
      echo "[pr-finalize] ERROR: 즉시 머지 fallback 실패" >&2
      exit 1
    }
  else
    echo "[pr-finalize] ERROR: auto-merge 토글 실패: $MERGE_ERR" >&2
    exit 1
  fi
}

# Step 2: CI 결과 대기
# 통합 브랜치 sub-PR 은 CI 체크 0개가 정상 (검증 워크플로는 default branch 대상 PR 만
# 발동) — watch 가 "no checks reported" 로 실패하면 check-run 수를 재확인해 0개면 통과.
echo "[pr-finalize] CI 결과 대기 (gh pr checks --watch)" >&2
if ! gh pr checks "$PR" --watch >&2; then
  CHECKS_OK=false
  if [ "$INTEGRATION" = "true" ]; then
    HEAD_OID=$(gh pr view "$PR" --json headRefOid -q .headRefOid 2>/dev/null || true)
    CHECK_COUNT=$(gh api "repos/{owner}/{repo}/commits/${HEAD_OID}/check-runs" -q '.total_count' 2>/dev/null || true)
    if [ "$CHECK_COUNT" = "0" ]; then
      echo "[pr-finalize] 통합 브랜치 sub-PR 에 CI 체크 없음 — 정상, 계속 진행" >&2
      CHECKS_OK=true
    fi
  fi
  if [ "$CHECKS_OK" != "true" ]; then
    echo "[pr-finalize] ERROR: CI FAIL — 머지 안 됨. sync skip" >&2
    exit 1
  fi
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
record_pr_merged "$PR" "$PR_URL"

if [ -n "$MERGE_LOCK_TOKEN" ]; then
  "$HELPER" merge-lock complete \
    --token "$MERGE_LOCK_TOKEN" \
    --claim-key "$MERGE_CLAIM_KEY" \
    --pr "$PR" \
    --url "$PR_URL" >/dev/null
  MERGE_LOCK_TOKEN=""
  MERGE_CLAIM_KEY=""
fi

# Step 5: 통합 브랜치 sub-PR issue close 보정
# GitHub auto-close 는 base = default branch 인 PR 머지만 인식 — base ≠ default 인
# sub-PR 의 PR body close 선언(Closes/Fixes/Resolves #N)은 머지돼도 발동하지 않는다.
# PR body 의 독립 trailer 줄에 선언이 있는 OPEN issue 를 PR 링크 코멘트와 함께 close 보정한다
# (선언 없는 issue, 산문 인용, blockquote/list 예시는 건드리지 않음). epic→main 일괄 머지 PR 의
# 중복 Closes 는 이미 closed issue 에 무해.
if [ "$INTEGRATION" = "true" ]; then
  CLOSE_NUMS=$(gh pr view "$PR" --json body -q .body 2>/dev/null \
    | extract_close_issue_numbers || true)
  if [ -n "$CLOSE_NUMS" ]; then
    echo "[pr-finalize] issue close 보정 대상: $(printf '%s' "$CLOSE_NUMS" | tr '\n' ' ')" >&2
  else
    echo "[pr-finalize] issue close 보정 대상 없음" >&2
  fi
  for N in $CLOSE_NUMS; do
    ISSUE_STATE=$(gh issue view "$N" --json state -q .state 2>/dev/null || true)
    if [ "$ISSUE_STATE" = "OPEN" ]; then
      if gh issue close "$N" --comment "[pr-finalize] PR #${PR} 가 통합 브랜치 '${BASE_REF}' 에 머지됨 — base 가 default branch 가 아니어서 GitHub auto-close 미발동. PR body 의 close 선언을 근거로 보정 close. $PR_URL" >&2; then
        echo "[pr-finalize] issue #$N close 보정 (통합 브랜치 — auto-close 미발동)" >&2
      else
        echo "[pr-finalize] WARN: issue #$N close 실패 — 수동 확인 필요: gh issue view $N" >&2
      fi
    fi
  done
fi

if [ "${SKIP_SYNC:-}" = "true" ]; then
  echo "[pr-finalize] origin/$DEFAULT_REF 동기화 skip (working tree dirty)" >&2
  echo "[pr-finalize] PR #$PR merged · $PR_URL"
  exit 0
fi

echo "[pr-finalize] origin/$DEFAULT_REF ref 동기화" >&2
if ! git fetch origin "$DEFAULT_REF" --quiet; then
  echo "[pr-finalize] ERROR: git fetch origin $DEFAULT_REF 실패 (네트워크 / 권한)" >&2
  exit 1
fi
if [ "$INTEGRATION" = "true" ]; then
  if ! git fetch origin "$BASE_REF" --quiet; then
    echo "[pr-finalize] WARN: git fetch origin $BASE_REF 실패 — 다음 sub-PR branch 생성 전 수동 fetch 권장" >&2
  fi
fi

echo "[pr-finalize] PR #$PR merged · $PR_URL"
