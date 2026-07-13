#!/bin/bash
# dcness pr-finalize — PR 머지 + CI 대기 + default worktree 동기화 자동
#
# pr-finalize 호출 = 머지 확정. 이 스크립트는 별도 최종 승인 UI 없이 merge 를 시도한다.
#
# 한 명령으로 머지 절차 끝:
#   1. gh pr merge --auto --merge (auto-merge 토글 ON)
#   2. gh pr checks --watch (CI 결과 대기)
#   3. auto-merge 완료 대기 (GitHub 백그라운드 lag)
#   4. git fetch origin <default> + default branch worktree fast-forward
#   5. clean feature worktree / stale worktree admin entry 정리
#
# base ≠ default branch PR은 merge 전에 거부한다. story stack PR은 사용자의 merge
# 승인 뒤 default branch로 리타겟·리베이스한 다음 이 helper를 호출해야 한다.
#
# 사용:
#   pr-finalize.sh                # current branch 의 open PR 자동 검출
#   pr-finalize.sh <PR_NUMBER>    # 명시 PR 번호
#
# 안전:
#   - 현재/대상 working tree dirty 면 강제 reset/stash 없이 preserved 목록에 이유 출력
#   - CI FAIL 시 sync skip + 에러 코드
#   - 머지 안 됐으면 sync skip + 사용자 안내
#
# 멀티 worktree 호환:
#   - default branch 가 다른 worktree 에 checkout 되어 있으면 그 worktree 를 fast-forward.
#   - default branch worktree 가 없고 현재 worktree 가 clean 이면 현재 worktree 를 default 로 전환.
#   - clean linked feature worktree 만 `git worktree remove` 로 정리.
#
# stdout / stderr 분리:
#   - stdout = 최종 1줄 (PR URL + sync/cleanup summary) — 메인 Claude / 사용자에게 필요한 정보.
#   - stderr = 진행 표시 / WARN / ERROR — 사용자가 보고 싶으면 보면 됨, 메인 컨텍스트엔 안 들어감.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/dcness-helper"

PR="$1"
BRANCH=""
PR_HEAD_REF=""
MERGE_LOCK_TOKEN=""
MERGE_CLAIM_KEY=""
CURRENT_WORKTREE=""
SYNCED_DEFAULT_PATH=""
SYNCED_DEFAULT_HEAD=""
ORIGIN_DEFAULT_HEAD=""
CLEANED_ITEMS=""
PRESERVED_ITEMS=""

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

append_item() {
  local current="$1"
  local item="$2"
  if [ -z "$current" ]; then
    printf '%s' "$item"
  else
    printf '%s; %s' "$current" "$item"
  fi
}

add_cleaned() {
  CLEANED_ITEMS=$(append_item "$CLEANED_ITEMS" "$1")
}

add_preserved() {
  PRESERVED_ITEMS=$(append_item "$PRESERVED_ITEMS" "$1")
}

format_items() {
  if [ -z "$1" ]; then
    printf 'none'
  else
    printf '%s' "$1"
  fi
}

require_default_base() {
  local resolved_base
  if ! resolved_base=$(gh pr view "$PR" --json baseRefName -q .baseRefName 2>/dev/null); then
    echo "[pr-finalize] ERROR: PR #$PR base branch 조회 실패 — merge 안전 검증 불가" >&2
    return 1
  fi
  if [ -z "$resolved_base" ] || [ "$resolved_base" = "null" ]; then
    echo "[pr-finalize] ERROR: PR #$PR base branch 조회 실패 — 빈 응답, merge 안전 검증 불가" >&2
    return 1
  fi
  BASE_REF="$resolved_base"
  if [ "$BASE_REF" != "$DEFAULT_REF" ]; then
    echo "[pr-finalize] ERROR: base=$BASE_REF ≠ default=$DEFAULT_REF — merge 전에 PR을 ${DEFAULT_REF}으로 리타겟·리베이스할 것" >&2
    return 1
  fi
}

canonical_path() {
  (cd "$1" 2>/dev/null && pwd -P) || printf '%s\n' "$1"
}

same_path() {
  [ "$(canonical_path "$1")" = "$(canonical_path "$2")" ]
}

worktree_is_clean() {
  [ -z "$(git -C "$1" status --porcelain)" ]
}

find_worktree_by_branch() {
  local branch="$1"
  git worktree list --porcelain | awk -v ref="refs/heads/${branch}" '
    $1 == "worktree" { path = substr($0, 10) }
    $1 == "branch" && $2 == ref { print path; exit }
  '
}

is_linked_worktree() {
  local git_dir
  git_dir=$(git -C "$1" rev-parse --git-dir 2>/dev/null || true)
  case "$git_dir" in
    */.git/worktrees/*|*.git/worktrees/*) return 0 ;;
    *) return 1 ;;
  esac
}

sync_default_worktree() {
  local path="$1"
  if ! worktree_is_clean "$path"; then
    add_preserved "$path: dirty default worktree; run git -C '$path' status, then git -C '$path' merge --ff-only origin/$DEFAULT_REF"
    return 1
  fi

  echo "[pr-finalize] default worktree fast-forward: $path" >&2
  if ! git -C "$path" merge --ff-only "origin/$DEFAULT_REF" >&2; then
    add_preserved "$path: non-fast-forward default sync; inspect git -C '$path' status/log before manual resolution"
    return 1
  fi

  SYNCED_DEFAULT_PATH="$path"
  SYNCED_DEFAULT_HEAD=$(git -C "$path" rev-parse HEAD 2>/dev/null || true)
  return 0
}

switch_current_to_default_worktree() {
  local path="$1"
  if ! worktree_is_clean "$path"; then
    add_preserved "$path: dirty current worktree; no default branch worktree exists, so default sync requires manual cleanup first"
    return 1
  fi

  echo "[pr-finalize] default worktree 없음 — 현재 clean worktree 를 $DEFAULT_REF 로 전환" >&2
  if git -C "$path" show-ref --verify --quiet "refs/heads/$DEFAULT_REF"; then
    git -C "$path" switch "$DEFAULT_REF" >&2 || {
      add_preserved "$path: checkout conflict switching to $DEFAULT_REF"
      return 1
    }
  else
    git -C "$path" switch -c "$DEFAULT_REF" --track "origin/$DEFAULT_REF" >&2 || {
      add_preserved "$path: checkout conflict creating $DEFAULT_REF from origin/$DEFAULT_REF"
      return 1
    }
  fi

  sync_default_worktree "$path"
}

cleanup_merged_feature_worktree() {
  local feature_path
  local anchor
  feature_path=$(find_worktree_by_branch "$BRANCH")

  if [ "$STATE" != "MERGED" ] || [ -z "$feature_path" ] || [ "$BRANCH" = "$DEFAULT_REF" ]; then
    return 0
  fi
  if [ -n "$SYNCED_DEFAULT_PATH" ] && same_path "$feature_path" "$SYNCED_DEFAULT_PATH"; then
    return 0
  fi
  if ! is_linked_worktree "$feature_path"; then
    add_preserved "$feature_path: feature branch is not a linked worktree"
    return 0
  fi
  if ! worktree_is_clean "$feature_path"; then
    add_preserved "$feature_path: dirty merged feature worktree"
    return 0
  fi

  anchor="$SYNCED_DEFAULT_PATH"
  if [ -z "$anchor" ]; then
    anchor=$(find_worktree_by_branch "$DEFAULT_REF")
  fi
  if [ -z "$anchor" ]; then
    add_preserved "$feature_path: no default worktree anchor available for safe removal"
    return 0
  fi

  if [ -n "$CURRENT_WORKTREE" ] && same_path "$CURRENT_WORKTREE" "$feature_path"; then
    cd "$anchor"
  fi
  if git -C "$anchor" worktree remove "$feature_path" >&2; then
    add_cleaned "$feature_path: removed merged feature worktree"
  else
    add_preserved "$feature_path: git worktree remove failed"
  fi
}

prune_stale_worktrees() {
  local dry_run
  dry_run=$(git worktree prune --dry-run 2>&1 || true)
  if [ -z "$dry_run" ]; then
    return 0
  fi
  if git worktree prune >&2; then
    add_cleaned "stale worktree admin entries pruned: $(printf '%s' "$dry_run" | tr '\n' ' ')"
  else
    add_preserved "stale worktree admin entries: prune failed: $(printf '%s' "$dry_run" | tr '\n' ' ')"
  fi
}

post_merge_sync_and_cleanup() {
  local default_path

  echo "[pr-finalize] origin/$DEFAULT_REF ref 동기화" >&2
  if ! git fetch origin "$DEFAULT_REF" --quiet; then
    echo "[pr-finalize] ERROR: git fetch origin $DEFAULT_REF 실패 (네트워크 / 권한)" >&2
    exit 1
  fi
  ORIGIN_DEFAULT_HEAD=$(git rev-parse "origin/$DEFAULT_REF" 2>/dev/null || true)

  default_path=$(find_worktree_by_branch "$DEFAULT_REF")
  if [ -n "$default_path" ]; then
    sync_default_worktree "$default_path" || true
  else
    switch_current_to_default_worktree "$CURRENT_WORKTREE" || true
  fi

  cleanup_merged_feature_worktree
  prune_stale_worktrees
}

emit_final_summary() {
  if [ -z "$ORIGIN_DEFAULT_HEAD" ]; then
    ORIGIN_DEFAULT_HEAD=$(git rev-parse "origin/$DEFAULT_REF" 2>/dev/null || printf 'unknown')
  fi
  if [ -n "$SYNCED_DEFAULT_PATH" ] && [ -z "$SYNCED_DEFAULT_HEAD" ]; then
    SYNCED_DEFAULT_HEAD=$(git -C "$SYNCED_DEFAULT_PATH" rev-parse HEAD 2>/dev/null || true)
  fi
  echo "[pr-finalize] PR #$PR merged · $PR_URL · default_path=${SYNCED_DEFAULT_PATH:-none} · HEAD=${SYNCED_DEFAULT_HEAD:-none} · origin/$DEFAULT_REF=${ORIGIN_DEFAULT_HEAD:-unknown} · cleaned=$(format_items "$CLEANED_ITEMS") · preserved=$(format_items "$PRESERVED_ITEMS")"
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
  PR_HEAD_REF=$(gh pr view "$PR" --json headRefName -q .headRefName 2>/dev/null || true)
  if [ -n "$PR_HEAD_REF" ]; then
    BRANCH="$PR_HEAD_REF"
  else
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
  fi
fi
CURRENT_WORKTREE=$(git rev-parse --show-toplevel)

# default branch merge guard
DEFAULT_REF=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)
if [ -z "$DEFAULT_REF" ]; then
  DEFAULT_REF=main
fi
require_default_base

# working tree dirty check
if [ -n "$(git status --porcelain)" ]; then
  echo "[pr-finalize] WARN: working tree dirty — fetch sync 영향은 없지만 다음 작업 시 충돌 위험" >&2
  git status --short >&2
  echo "[pr-finalize] 계속 진행 (dirty worktree 는 sync/cleanup preserved 로 보고) Y/n? " >&2
  read -r reply
  if [ "$reply" != "Y" ] && [ "$reply" != "y" ]; then
    exit 1
  fi
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
  git fetch origin "$DEFAULT_REF" --quiet
  if ! gh pr update-branch "$PR" >&2; then
    echo "[pr-finalize] WARN: gh pr update-branch 실패 또는 불필요 — merge/check 단계에서 재검증" >&2
  fi
  if ! gh pr checks "$PR" >&2; then
    echo "[pr-finalize] WARN: 현재 CI 상태가 clean 이 아님 — --watch 단계에서 최종 판정" >&2
  fi
fi

# 승인 대기·dirty 확인·peer lock 사이에 PR base가 바뀌었을 수 있으므로 merge
# 명령 직전에 다시 fail-closed 검증한다.
echo "[pr-finalize] merge 직전 default branch base 재확인" >&2
require_default_base

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

# Step 4: post-merge ledger 기록
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

post_merge_sync_and_cleanup
emit_final_summary
