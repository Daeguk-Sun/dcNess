#!/bin/bash
set -euo pipefail

# sync_release.sh — main → release 동기화
# dcness self 경로를 제거한 사본을 release 브랜치에 push.

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# dcness self 전용 경로 — release 브랜치에서 제거
EXCLUDE_PATHS=(
    "docs/internal"
    "docs/archive"
    "tests"
    "evals"
    "PROGRESS.md"
    "CLAUDE.md"
    "scripts/sync_release.sh"
    ".claude-plugin/marketplace.json"
    ".github/workflows/python-tests.yml"
    ".github/workflows/release-sync.yml"
    ".claude"
)

ORIG_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")

restore_branch() {
    local current
    current=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
    if [ -n "$ORIG_BRANCH" ] && [ "$current" != "$ORIG_BRANCH" ]; then
        git checkout "$ORIG_BRANCH" 2>/dev/null || true
    fi
}
trap restore_branch EXIT

YES_MODE=0
for arg in "$@"; do
    if [ "$arg" = "--yes" ] || [ "$arg" = "-y" ]; then
        YES_MODE=1
    fi
done

confirm() {
    local prompt="$1"
    if [ "$YES_MODE" -eq 1 ]; then
        return 0
    fi
    printf "%s (yes/N): " "$prompt"
    read -r ans
    [ "$ans" = "yes" ]
}

# 위험 경고: release 위 직접 commit 체크
git fetch origin --quiet
if git show-ref --verify --quiet refs/remotes/origin/release; then
    DIVERGED=$(git log origin/release ^origin/main --oneline 2>/dev/null | wc -l | tr -d ' ')
    if [ "$DIVERGED" -gt 0 ]; then
        echo "⚠ WARNING: origin/release 에 origin/main 에 없는 commit ${DIVERGED}개 발견."
        echo "  force-push 하면 이 commit 들이 사라집니다."
        if ! confirm "계속하려면 'yes' 입력"; then
            echo "중단."
            exit 1
        fi
    fi
fi

MAIN_SHA=$(git rev-parse origin/main)
SHORT_SHA=${MAIN_SHA:0:7}

echo "→ release 브랜치를 origin/main@${SHORT_SHA} 기반으로 reset..."
if git show-ref --verify --quiet refs/heads/release; then
    git checkout release 2>/dev/null
    git reset --hard origin/main
else
    git checkout -b release origin/main
fi

echo "→ dcness self 경로 제거..."
REMOVED=()
for p in "${EXCLUDE_PATHS[@]}"; do
    if [ -n "$(git ls-files "$p")" ]; then
        git rm -r --quiet "$p"
        REMOVED+=("$p")
    fi
done

if [ ${#REMOVED[@]} -eq 0 ]; then
    echo "  제거 대상 없음 (이미 동기화 상태)."
else
    echo "  제거됨: ${REMOVED[*]}"
fi

if git diff --cached --quiet; then
    echo "→ 변경 없음 — commit 생략."
else
    # --no-verify: sync commit 은 기계 생성 스냅샷 — pre-commit 훅(pytest 게이트) 비대상
    git commit --no-verify -m "release sync from main@${SHORT_SHA}"
    echo "→ commit: release sync from main@${SHORT_SHA}"
fi

echo ""
if ! confirm "release 브랜치를 origin 에 force-with-lease push"; then
    echo "push 생략. 로컬 release 브랜치만 갱신됨."
    exit 0
fi

git push --force-with-lease origin release
echo "✓ release 브랜치 sync 완료 — main@${SHORT_SHA}"
