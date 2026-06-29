#!/bin/sh
# dcNess pytest pre-commit gate (paths 분기)
# 규칙 정의: docs/internal/governance.md §2.7
#
# 동작:
#   1. staged 파일 목록 추출 (git diff --cached --name-only)
#   2. harness/ | tests/ | agents/ | skills/ | commands/ | templates/github-workflows/ | doc-path action/script | .github/workflows/python-tests.yml 매칭 시만 실행
#   3. python3.11/python3 -m unittest discover -s tests
#
# 종료 코드:
#   0 — 통과 (or 매칭 0)
#   1 — 테스트 실패
#
# 우회: git commit --no-verify (룰 위반).

set -u

# CI 환경 (GITHUB_ACTIONS) 에선 skip — workflow 가 별도 실행
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  exit 0
fi

# staged 파일 매칭 검사 (추가/수정만 — 삭제는 테스트 실행 불필요)
CHANGED=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)
if [ -z "$CHANGED" ]; then
  exit 0
fi

if ! printf '%s\n' "$CHANGED" | grep -qE '^(harness/|tests/|agents/|skills/|commands/|templates/github-workflows/|evals/|\.github/actions/doc-path-integrity/|scripts/check_git_naming\.mjs$|scripts/check_doc_path_integrity\.mjs$|docs/plugin/git-spec\.md$|docs/plugin/loop-procedure\.md$|\.github/workflows/python-tests\.yml$)'; then
  # 미매칭 — skip
  exit 0
fi

echo "[pytest-gate] 관련 staged 파일 감지 — 단위 테스트 실행"
# DCN-CHG-20260501-09: pre-commit 안에서 git env vars (GIT_INDEX_FILE / GIT_DIR /
# GIT_WORK_TREE) 가 inherited 되어 자식 git worktree add 호출이 fail. unset 후 실행.
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  # Tests use Python 3.10+ syntax (for example PEP 604 unions). Prefer 3.11
  # when present so the local hook matches CI instead of macOS system python3.
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  else
    PYTHON_BIN="python3"
  fi
fi

if ! env -u GIT_INDEX_FILE -u GIT_DIR -u GIT_WORK_TREE -u GIT_PREFIX -u GIT_EXEC_PATH "$PYTHON_BIN" -m unittest discover -s tests >&2; then
  echo "[pytest-gate] FAIL — 단위 테스트 회귀. fix 후 재커밋. (우회: --no-verify, 룰 위반)" >&2
  exit 1
fi
echo "[pytest-gate] PASS"
exit 0
