#!/bin/bash
set -euo pipefail

# sync_release.sh — immutable version tag → release artifact publish
# positive allowlist artifact만 release 브랜치에 기록하고 같은 version의 재발행을 차단한다.

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
TAG=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes|-y)
            YES_MODE=1
            shift
            ;;
        --tag)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: --tag requires vMAJOR.MINOR.PATCH." >&2
                exit 2
            fi
            TAG="$2"
            shift 2
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [ -z "$TAG" ]; then
    echo "ERROR: release publish requires --tag vMAJOR.MINOR.PATCH." >&2
    exit 2
fi

confirm() {
    local prompt="$1"
    if [ "$YES_MODE" -eq 1 ]; then
        return 0
    fi
    printf "%s (yes/N): " "$prompt"
    read -r ans
    [ "$ans" = "yes" ]
}

git_with_token fetch origin --quiet --tags

TAG_REF="refs/tags/${TAG}"
if ! git show-ref --verify --quiet "$TAG_REF"; then
    echo "ERROR: immutable release tag not found: ${TAG}" >&2
    exit 1
fi

LOCAL_TAG_OBJECT=$(git rev-parse "$TAG_REF")
REMOTE_TAG_OBJECT=$(git_with_token ls-remote origin "$TAG_REF" | awk 'NR == 1 {print $1}')
if [ -z "$REMOTE_TAG_OBJECT" ] || [ "$LOCAL_TAG_OBJECT" != "$REMOTE_TAG_OBJECT" ]; then
    echo "ERROR: local and origin tag objects differ for ${TAG}." >&2
    exit 1
fi

SOURCE_SHA=$(git rev-parse "${TAG_REF}^{commit}")
SHORT_SHA=${SOURCE_SHA:0:7}
if ! git merge-base --is-ancestor "$SOURCE_SHA" origin/main; then
    echo "ERROR: ${TAG} source ${SHORT_SHA} is not a tested origin/main commit." >&2
    exit 1
fi

ARTIFACT_BUILDER="$REPO_ROOT/scripts/release_artifact.py"
TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/dcness-release-sync.XXXXXX")
ARTIFACT_DIR="$TEMP_ROOT/artifact"
echo "→ ${TAG}@${SHORT_SHA} positive allowlist artifact 생성..."
if ! python3 "$ARTIFACT_BUILDER" build \
    --repo-root "$REPO_ROOT" \
    --ref "$TAG_REF" \
    --output "$ARTIFACT_DIR"; then
    echo "ERROR: positive allowlist artifact 생성에 실패해 release publish를 중단합니다." >&2
    exit 1
fi

PUBLISHED_RELEASE_SHA=$(printf '0%.0s' {1..40})
VERIFY_ARGS=(
    verify-release
    --repo-root "$REPO_ROOT"
    --tag "$TAG"
    --candidate "$ARTIFACT_DIR"
)
if git show-ref --verify --quiet refs/remotes/origin/release; then
    PUBLISHED_RELEASE_SHA=$(git rev-parse origin/release)
    PUBLISHED_SOURCE_SHA=$(git rev-parse origin/release^)
    PUBLISHED_DIR="$TEMP_ROOT/published"
    mkdir -p "$PUBLISHED_DIR"
    git archive --format=tar origin/release | tar -xf - -C "$PUBLISHED_DIR"
    VERIFY_ARGS+=(
        --published "$PUBLISHED_DIR"
        --published-source-sha "$PUBLISHED_SOURCE_SHA"
    )
fi

if [ -n "${PUBLISHED_DIR:-}" ]; then
    SMOKE_ARGS=(
        smoke
        --repo-root "$REPO_ROOT"
        --ref "$TAG_REF"
        --previous-root "$PUBLISHED_DIR"
    )
    if ! python3 "$ARTIFACT_BUILDER" "${SMOKE_ARGS[@]}"; then
        echo "ERROR: clean install/update release smoke에 실패해 publish하지 않습니다." >&2
        exit 1
    fi
fi

if ! VERIFY_JSON=$(python3 "$ARTIFACT_BUILDER" "${VERIFY_ARGS[@]}"); then
    echo "ERROR: version/tag/source/bundle consistency 검증에 실패해 publish하지 않습니다." >&2
    exit 1
fi
printf '%s\n' "$VERIFY_JSON"
ACTION=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["action"])' "$VERIFY_JSON")
VERSION=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["version"])' "$VERIFY_JSON")
if [ "$ACTION" = "already_published" ]; then
    echo "→ ${TAG} artifact는 이미 동일 source SHA와 bundle digest로 배포됨 — 변경 없음."
    exit 0
fi

if ! confirm "${TAG}@${SHORT_SHA} artifact를 release 브랜치에 publish"; then
    echo "publish 생략."
    exit 0
fi

echo "→ release 브랜치를 ${TAG}@${SHORT_SHA} tested source 기반으로 작성..."
git checkout -B release "$SOURCE_SHA" 2>/dev/null
git rm -r --quiet -- .
cp -R "$ARTIFACT_DIR/." "$REPO_ROOT/"
git add -u
(cd "$ARTIFACT_DIR" && find . -type f -print0) \
    | git add --pathspec-from-file=- --pathspec-file-nul

if git diff --cached --quiet; then
    echo "ERROR: new version ${VERSION} did not create a release artifact commit." >&2
    exit 1
fi

git commit -m "[docs] release ${VERSION} from ${TAG}@${SHORT_SHA}"
git_with_token push \
    "--force-with-lease=refs/heads/release:${PUBLISHED_RELEASE_SHA}" \
    origin HEAD:refs/heads/release
echo "✓ release publish 완료 — ${TAG}@${SHORT_SHA}"
