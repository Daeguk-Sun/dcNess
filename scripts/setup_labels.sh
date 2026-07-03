#!/usr/bin/env bash
# setup_labels.sh — dcNess lifecycle GitHub label 생성
# IssueType repo label 6종과 작업 중 상태 label in-progress 를 생성/갱신한다.
#
# 사용:
#   bash scripts/setup_labels.sh [<owner/repo>]
#   (인자 없으면 gh repo view 로 자동 감지)
set -euo pipefail

REPO="${1:-}"
if [ -z "$REPO" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo '')"
fi
if [ -z "$REPO" ]; then
  echo "[setup_labels] REPO 미지정 — 인자로 전달 또는 gh 로그인 후 재실행" >&2
  exit 1
fi

echo "[setup_labels] target: $REPO"

_upsert_label() {
  local name="$1" color="$2" description="$3"
  if gh label create "$name" --color "$color" --description "$description" --repo "$REPO" 2>/dev/null; then
    echo "  created: $name"
  else
    gh label edit "$name" --color "$color" --description "$description" --repo "$REPO" 2>/dev/null && \
      echo "  updated: $name" || echo "  skip: $name (no change or error)"
  fi
}

_upsert_label "epic"    "7057ff" "epic-level GitHub issue"
_upsert_label "feature" "a2eeef" "feature-level GitHub issue"
_upsert_label "story"   "0e8a16" "story-level GitHub issue"
_upsert_label "task"    "c5def5" "task-level GitHub issue"
_upsert_label "subTask" "bfdadc" "subTask-level GitHub issue"
_upsert_label "bug"     "d73a4a" "bug-level GitHub issue"
_upsert_label "in-progress" "fbca04" "dcNess lifecycle status: work is currently in progress"

echo "[setup_labels] 완료 — lifecycle label 7종"
