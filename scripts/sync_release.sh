#!/bin/bash
set -euo pipefail

# sync_release.sh — main → release 동기화
# positive allowlist artifact만 release 브랜치에 기록해 repo-only 신규 파일의 유입을 막는다.

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

ORIG_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
TEMP_ROOT=""

git_with_token() {
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        local auth_header
        auth_header=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')
        GIT_CONFIG_COUNT=1 \
        GIT_CONFIG_KEY_0=http.https://github.com/.extraheader \
        GIT_CONFIG_VALUE_0="AUTHORIZATION: basic ${auth_header}" \
            git "$@"
    else
        git "$@"
    fi
}

restore_branch() {
    local current
    current=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
    if [ -n "$ORIG_BRANCH" ] && [ "$current" != "$ORIG_BRANCH" ]; then
        git checkout "$ORIG_BRANCH" 2>/dev/null || true
    fi
}

cleanup() {
    restore_branch
    if [ -n "$TEMP_ROOT" ]; then
        rm -rf "$TEMP_ROOT"
    fi
}
trap cleanup EXIT

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
git_with_token fetch origin --quiet
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

echo "→ positive allowlist artifact 생성..."
ARTIFACT_BUILDER="$REPO_ROOT/scripts/release_artifact.py"
TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/dcness-release-sync.XXXXXX")
ARTIFACT_DIR="$TEMP_ROOT/artifact"
if ! python3 "$ARTIFACT_BUILDER" build \
    --repo-root "$REPO_ROOT" \
    --ref "$MAIN_SHA" \
    --output "$ARTIFACT_DIR"; then
    echo "ERROR: positive allowlist artifact 생성에 실패해 release sync를 중단합니다." >&2
    exit 1
fi

git rm -r --quiet -- .
cp -R "$ARTIFACT_DIR/." "$REPO_ROOT/"
git add -u
(cd "$ARTIFACT_DIR" && find . -type f -print0) \
    | git add --pathspec-from-file=- --pathspec-file-nul
echo "  allowlist artifact 반영 완료"

if git diff --cached --quiet; then
    echo "→ 변경 없음 — commit 생략."
else
    git commit -m "[docs] release sync from main@${SHORT_SHA}"
    echo "→ commit: [docs] release sync from main@${SHORT_SHA}"
fi

echo ""
if ! confirm "release 브랜치를 origin 에 force-with-lease push"; then
    echo "push 생략. 로컬 release 브랜치만 갱신됨."
    exit 0
fi

git_with_token push --force-with-lease origin release
echo "✓ release 브랜치 sync 완료 — main@${SHORT_SHA}"
