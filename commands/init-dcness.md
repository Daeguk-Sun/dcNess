---
name: init-dcness
description: 현재 프로젝트를 dcNess plugin 활성 대상으로 등록하는 부트스트랩 스킬. dcNess 는 디폴트로 모든 프로젝트에서 비활성 (hook pass-through). 본 스킬 호출 시 현재 cwd 의 main repo 를 plugin-scoped whitelist (`~/.claude/plugins/data/dcness-dcness/projects.json`) 에 추가해 SessionStart / PreToolUse Agent 훅이 발화하기 시작한다. 사용자가 "init-dcness", "dcness 활성화", "이 프로젝트에 dcness 켜", "dcness 시작", "/init-dcness" 등을 말할 때 사용. 비활성화는 `/disable-dcness` (또는 본 스킬에서 status 확인 후 안내).
---

# Init dcNess Skill - 프로젝트 활성화

> dcNess plugin 은 디폴트 disabled. 명시 활성화 필요. plugin install 만으로는 hook 발화 0 (pass-through).

## 언제 사용

- 사용자 발화: "init-dcness", "dcness 활성화", "/init-dcness", "이 프로젝트에 dcness 켜"
- 새 프로젝트에 dcness plugin 사용 시작 시
- 비활성 -> 활성 전환 시
- project-local bootstrap 파일이나 Codex 분기 opt-in 을 새로 설치/갱신할 때

## 실행 원칙

본 문서는 사용자가 지금 선택하거나 실행해야 하는 bootstrap 절차만 다룬다. hook 정책, TDD Guard skip 룰, workflow YAML 전문, 배경 히스토리는 reference 로 내린다.

- 상세 bootstrap inventory / YAML snippet: [`docs/plugin/init-dcness.md`](../docs/plugin/init-dcness.md)
- hook 정책 SSOT: [`docs/plugin/hooks.md`](../docs/plugin/hooks.md)
- git / PR naming SSOT: [`docs/plugin/git-spec.md`](../docs/plugin/git-spec.md)
- Project lifecycle SSOT: [`docs/plugin/github-project.md`](../docs/plugin/github-project.md)

멱등 기준:

- whitelist 활성화: 중복 제거.
- `~/.claude/settings.json` Read 권한: 없을 때만 추가.
- `.git/hooks/*`: thin shim always-overwrite.
- `.github/workflows/*.yml`: 사용자가 선택한 경우 always-overwrite.
- `docs/*`, `design-variants/*`: 부재 시만 seed.
- Codex validator skills: `$CODEX_HOME/skills/dcness-*` always-overwrite, provider routing 은 opt-in 값으로 갱신.
- CC hook / TDD Guard: 사용자 repo 파일 설치 없음. 활성화 후 plug-in hook 으로 자동 발화.

## 공통 변수

이후 절차에서 반복 사용한다.

```bash
PLUGIN_ROOT="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)"
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"
```

`PLUGIN_ROOT` 또는 `PROJECT_ROOT` 가 비면 중단하고 plugin 설치 상태와 git repo 여부를 먼저 확인한다.

## 절차

### Step 1 - 현재 상태 확인

```bash
"$HELPER" status
```

이미 활성(`active: YES`)이면 Step 2 는 skip 하고 나머지 bootstrap 갱신 여부만 확인한다.

### Step 2 - 활성화

```bash
"$HELPER" enable
```

결과:

- 현재 cwd 의 main repo root 를 whitelist 에 추가.
- whitelist: `~/.claude/plugins/data/dcness-dcness/projects.json`
- 다음 Claude Code 세션부터 SessionStart / PreToolUse hook 이 활성 프로젝트로 인식.

### Step 3 - Read 권한 부여

SessionStart 훅이 plugin cache 안 SSOT 문서를 inject 하려면 `~/.claude/settings.json` 에 Read allow 가 필요하다.

```bash
PERM='Read(~/.claude/plugins/cache/dcness/**)'
SETTINGS="$HOME/.claude/settings.json"
if [ ! -f "$SETTINGS" ]; then
  mkdir -p "$(dirname "$SETTINGS")"
  printf '{"permissions":{"allow":[]}}\n' > "$SETTINGS"
fi
if command -v jq >/dev/null 2>&1; then
  if jq -e --arg p "$PERM" '(.permissions.allow // []) | index($p)' "$SETTINGS" >/dev/null; then
    echo "[dcness] permission 이미 존재: $PERM"
  else
    tmp=$(mktemp)
    jq --arg p "$PERM" '.permissions = (.permissions // {}) | .permissions.allow = ((.permissions.allow // []) + [$p] | unique)' "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"
    echo "[dcness] permission 추가: $PERM -> $SETTINGS"
  fi
else
  echo "[dcness] WARN - jq 미설치. $SETTINGS .permissions.allow 에 '$PERM' 수동 추가 필요" >&2
fi
```

### Step 4 - local git hook 설치

브랜치명, 커밋 제목, main 직접 push 를 로컬에서 조기 차단한다. 본체 검증 로직은 사용자 repo 에 복사하지 않고 plug-in SSOT 를 직접 호출한다.

```bash
mkdir -p "$PROJECT_ROOT/.git/hooks"

cp "$PLUGIN_ROOT/scripts/hooks/commit-msg" "$PROJECT_ROOT/.git/hooks/commit-msg"
chmod +x "$PROJECT_ROOT/.git/hooks/commit-msg"
echo "[dcness] .git/hooks/commit-msg 갱신 (thin shim -> plugin SSOT 호출)"

cp "$PLUGIN_ROOT/scripts/hooks/post-checkout" "$PROJECT_ROOT/.git/hooks/post-checkout"
chmod +x "$PROJECT_ROOT/.git/hooks/post-checkout"
echo "[dcness] .git/hooks/post-checkout 갱신 (thin shim -> plugin SSOT 호출)"

cp "$PLUGIN_ROOT/scripts/hooks/pre-push" "$PROJECT_ROOT/.git/hooks/pre-push"
chmod +x "$PROJECT_ROOT/.git/hooks/pre-push"
echo "[dcness] .git/hooks/pre-push 갱신 (thin shim -> plugin SSOT 호출)"

if [ -f "$PROJECT_ROOT/scripts/check_git_naming.mjs" ]; then
  echo "[dcness] NOTE - scripts/check_git_naming.mjs 가 사용자 repo 에 잔존. 이제 plugin SSOT 에서 호출하므로 제거 권장:"
  echo "         git rm scripts/check_git_naming.mjs"
fi
if [ -f "$PROJECT_ROOT/docs/plugin/skill-guidelines.md" ]; then
  echo "[dcness] NOTE - docs/plugin/skill-guidelines.md 가 사용자 repo 에 잔존. session-start.sh 가 이제 plugin SSOT 에서 read. 제거 권장:"
  echo "         git rm docs/plugin/skill-guidelines.md"
fi
```

### Step 5 - 선택형 CI workflow

각 질문에 사용자가 `Y` 를 선택한 경우에만 reference 의 YAML snippet 을 그대로 써서 해당 파일을 always-overwrite 한다. snippet 진본은 [`docs/plugin/init-dcness.md#ci-workflow-snippets`](../docs/plugin/init-dcness.md#ci-workflow-snippets) 이다.

#### git-naming-validation

```
[dcness] GitHub Actions CI 에서 git-naming 강제할까요?
  - PR open / sync / edit 시 브랜치명 + PR 제목 자동 검증
  - 본 thin yml 1개만 사용자 repo 에 깔리고, 검증 본체는 alruminum/dcNess composite action 호출
  - 로컬 git hook 만으로 충분하면 n
(Y/n)
```

Y 선택 시 `$PROJECT_ROOT/.github/workflows/git-naming-validation.yml` always-overwrite.

#### pr-body-validation

```
[dcness] GitHub Actions CI 에서 PR body close-keyword 강제할까요?
  - PR open / edit / sync 시 PR body issue trailer 검증
  - issue lifecycle 강제 안 하면 n
(Y/n)
```

Y 선택 시 `$PROJECT_ROOT/.github/workflows/pr-body-validation.yml` always-overwrite.

### Step 6 - 선택형 project seed

사용자 작업물을 보호하기 위해 모두 부재 시만 생성한다. 사용자가 `n` 을 선택하면 skip 하고, 다음 `/init-dcness` 재실행 때 다시 물을 수 있다.

#### design.md awareness

프로젝트가 UI 를 다루는지 묻는다.

```
[dcness] 이 프로젝트는 UI (화면 / 컴포넌트 / 시각 디자인) 를 다룹니까? (Y/n)
```

- `n`: `docs/design.md` 와 `design-variants/` seed skip.
- `Y`: `CLAUDE.md` lazy-read 매트릭스에 `docs/design.md` 행이 없으면 추가 여부를 묻고, `docs/design.md` 부재 시 minimal 템플릿 생성 여부를 묻는다. 템플릿 기준은 [`docs/plugin/design.md`](../docs/plugin/design.md).

#### 초기 docs 폼

```bash
mkdir -p "$PROJECT_ROOT/docs"
for FILE in prd.md architecture.md adr.md; do
  if [ -f "$PROJECT_ROOT/docs/$FILE" ]; then
    echo "[dcness] docs/$FILE 이미 존재 - skip"
  else
    # 사용자 동의 (Y/n) 받은 후에만 cp 실행. 동의 없이 silent cp 금지.
    cp "$PLUGIN_ROOT/templates/project-init/$FILE" "$PROJECT_ROOT/docs/$FILE"
    echo "[dcness] docs/$FILE 시드 완료 - 기획 논의 후 채워넣으세요"
  fi
done
```

#### design-variants

UI 프로젝트이고 `design-variants/` seed 를 원할 때만 진행한다.

```bash
mkdir -p "$PROJECT_ROOT/design-variants/_lib"
for FILE in _lib/show-ids.js _lib/canvas.js canvas.html; do
  TARGET="$PROJECT_ROOT/design-variants/$FILE"
  SOURCE="$PLUGIN_ROOT/templates/design-variants/$FILE"
  if [ -f "$TARGET" ]; then
    echo "[dcness] design-variants/$FILE 이미 존재 - skip"
  else
    cp "$SOURCE" "$TARGET"
    echo "[dcness] design-variants/$FILE 시드 완료"
  fi
done
```

### Step 7 - Codex validator opt-in

`code-validator` / `architecture-validator` / `pr-reviewer` 만 Codex read-only 실행으로 보낼 수 있다. 사용자 repo 에 provider config 를 만들지 않는다.

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME/skills"
for DIR in dcness-code-validator dcness-architecture-validator dcness-pr-reviewer; do
  mkdir -p "$CODEX_HOME/skills/$DIR"
  cp "$PLUGIN_ROOT/codex/skills/$DIR/SKILL.md" "$CODEX_HOME/skills/$DIR/SKILL.md"
  echo "[dcness] Codex skill 갱신: $CODEX_HOME/skills/$DIR/SKILL.md"
done
```

사용자에게 1회 묻는다.

```
[dcness] read-only validation 3종(code-validator / architecture-validator / pr-reviewer)을 Codex 로 보낼까요? (Y/n)
```

- `Y`:
  ```bash
  "$HELPER" routing enable-codex-validation
  "$HELPER" routing status
  ```
- `n`:
  ```bash
  "$HELPER" routing disable-codex-validation
  "$HELPER" routing status
  ```

### Step 8 - GitHub Project lifecycle bootstrap

GitHub Project v2 `Status / IssueType / Priority` 축과 repo label 6종을 점검할지 묻는다. 세부 계약은 [`docs/plugin/github-project.md`](../docs/plugin/github-project.md) 와 [`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) 가 SSOT 다.

```
[dcness] GitHub Project lifecycle bootstrap 을 수행할까요?
  - Project v2 field: Status / IssueType / Priority
  - repo label 6종: epic / feature / story / task / subTask / bug
  - /to-issue 등록, workflow 시작, PR merge 후처리가 같은 축을 사용
(Y/n)
```

- `n`: 보드 연결 없이 진행. `/to-issue` 는 issue 생성만 하고 보드 등록을 건너뛸 수 있다.
- `Y`: Project owner/number 를 확인하고 bootstrap script 를 실행한다.

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
OWNER="${REPO%%/*}"
gh project list --owner "$OWNER"

node "$PLUGIN_ROOT/scripts/github_project_lifecycle.mjs" bootstrap \
  --repo "$REPO" \
  --owner "$OWNER" \
  --project "$PROJECT_NUMBER"

gh variable set DCNESS_PROJECT_NUMBER --body "$PROJECT_NUMBER"
gh variable set DCNESS_PROJECT_OWNER --body "$OWNER"
```

필드나 label 이 부족하면 사용자의 명시 동의를 받은 뒤 `--apply` 로 생성/갱신한다.

```bash
node "$PLUGIN_ROOT/scripts/github_project_lifecycle.mjs" bootstrap \
  --repo "$REPO" \
  --owner "$OWNER" \
  --project "$PROJECT_NUMBER" \
  --apply
```

선택형 lifecycle workflow 를 물어본다.

```
[dcness] GitHub Actions CI/CD 에서 Project lifecycle guard 를 활성화할까요?
  - issue label/type drift 검출
  - PR closed+merged 시 close keyword 대상 issue 의 Project Status=Done 보정
  - Project v2 쓰기에는 secrets.DCNESS_PROJECT_TOKEN 과 vars.DCNESS_PROJECT_* 권장
(Y/n)
```

Y 선택 시 `$PROJECT_ROOT/.github/workflows/github-project-lifecycle.yml` always-overwrite. snippet 진본은 [`docs/plugin/init-dcness.md#ci-workflow-snippets`](../docs/plugin/init-dcness.md#ci-workflow-snippets) 이다.

### Step 9 - 선택형 workflow 변경 PR

자동 PR 대상은 `/init-dcness` 가 배포한 `.github/workflows/*.yml` 변경만이다. TDD Guard 는 자동 hook 이라 사용자 repo 파일 변경이 없고, docs/design seed 는 사용자 콘텐츠라 자동 infra PR 에 섞지 않는다.

```bash
cd "$PROJECT_ROOT"
CHANGES="$(git status --short .github/workflows/ 2>/dev/null | awk '{print $2}' | tr '\n' ' ')"
CHANGES_TRIM="$(echo "$CHANGES" | tr -s ' ')"

if [ -z "$CHANGES_TRIM" ]; then
  echo "[dcness] working tree 안 dcness workflow 변경 없음 - Step 9 skip"
fi
```

현재 branch 가 `main` 이고 변경이 있을 때만 사용자에게 묻는다.

```
[dcness] dcness workflow 변경 자동 commit + PR 만들까요?
  변경 파일:
    <.github/workflows/*.yml>
  자동 진행 시:
    1. branch 생성: docs/dcness_init_{timestamp}
    2. 위 workflow 파일만 stage + commit
    3. push + PR 생성
  n 시 수동 처리
(Y/n)
```

Y 선택 시:

```bash
TS=$(date +%Y%m%d_%H%M%S)
BR="docs/dcness_init_${TS}"
git checkout -b "$BR"

for f in $CHANGES; do
  git add "$f"
done

git commit -m "[docs] dcNess init workflow stage"
git push -u origin "$BR"

gh pr create --title "[docs] dcNess init workflow stage" --body "$(cat <<EOF
## 변경 요약

dcness plug-in 의 선택형 workflow 파일을 main 에 등록합니다.

## 포함

$(for f in $CHANGES; do echo "- \`$f\`"; done)

## 관련 이슈

Document-Exception-PR-Close: dcness init workflow bootstrap

## 머지 후 발화

- \`git-naming-validation\`
- \`pr-body-validation\`
- \`github-project-lifecycle\`
EOF
)"
```

## 이미 자동 적용되는 것

활성화 후 새 Claude Code 세션에서 plug-in hook 이 자동 발화한다. 사용자 repo 에 별도 파일을 설치하지 않는다.

- SessionStart: sid/live state 초기화와 활성 안내 inject.
- 순서 차단 훅: Agent 호출 전 작업 순서 보호.
- file-guard: agent 별 파일 경계와 외부 상태 변경 차단.
- TDD Guard: `Edit` / `Write` / `NotebookEdit` 직전 TS/JS 구현 파일의 매칭 test 존재 확인. 세부 skip/한계는 [`docs/plugin/hooks.md#tdd-guardsh`](../docs/plugin/hooks.md#tdd-guardsh).
- Stop hook: run 종료와 continuation signal.

## 완료 안내

```
[dcness] 활성화 완료
- 프로젝트: <main repo root>
- whitelist: ~/.claude/plugins/data/dcness-dcness/projects.json

다음 세션부터 자동 적용:
- SessionStart / PreToolUse / PostToolUse / SubagentStop / Stop hook
- TDD Guard 는 사용자 설정 없이 plug-in hook 으로 자동 발화

재실행이 필요한 경우:
- plugin uninstall/reinstall 로 whitelist 가 사라진 경우
- 선택형 CI workflow 를 새로 깔거나 갱신하는 경우
- Codex validation 분기를 새로 opt-in 하는 경우
- Project lifecycle bootstrap 또는 project-local seed 가 필요한 경우

기본 workflow:
- /spec — PRD / Epic / Story / AC 정의
- /design — product/technical design
- /impl — 구현 진입 통합 (구현 경로: 설계도 유무 — Lite / Standard + 엔진 내부 판정)
- /acceptance — story/epic 제품 검수 MVP

support:
- /to-issue — Issue Brief 초안 작성 + 승인 후 GitHub issue/Project 등록

고급 workflow:
- /tech-review — high-risk 설계 선행 기술 검증
- /impl-loop — deep impl task 파일용 advanced runner
- /ux — 화면 UX / 디자인 핸드오프

유틸리티:
- /smart-compact — 컨텍스트 압축 + resume prompt
- /run-review — run 사후 분석
- /efficiency — 세션 토큰/비용 분석

비활성화:
- "$HELPER" disable

Claude Code 세션 재시작 권장:
- SessionStart 훅은 현재 세션에는 소급 적용되지 않는다.
```

## 재설치 시 재실행 필수

`claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness` 시 `~/.claude/plugins/data/dcness-dcness/` 가 정리되어 whitelist 가 사라진다. 재설치 후 각 활성 프로젝트마다 `/init-dcness` 를 다시 실행한다.

`~/.claude/settings.json` 의 Read 권한은 재설치 후에도 보존된다. `/init-dcness` 재실행 시 이미 있으면 skip 한다.

## 참조

- [`docs/plugin/init-dcness.md`](../docs/plugin/init-dcness.md) - bootstrap inventory / workflow snippets / re-run matrix
- [`docs/plugin/hooks.md`](../docs/plugin/hooks.md) - hook 정책 SSOT
- [`docs/plugin/git-spec.md`](../docs/plugin/git-spec.md) - git / PR naming
- [`docs/plugin/github-project.md`](../docs/plugin/github-project.md) - Project v2 축과 bootstrap
- `harness/session_state.py` - 활성 프로젝트 판정과 helper CLI
- `hooks/hooks.json` - Claude Code hook 등록 manifest
