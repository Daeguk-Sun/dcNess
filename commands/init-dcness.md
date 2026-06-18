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
- Codex validator skills: `$CODEX_HOME/skills/dcness-*` always-overwrite.
- Codex provider routing: core 에서는 상태만 확인하고, 선택형 확장에서 opt-in 값으로 갱신.
- CC hook / TDD Guard: 사용자 repo 파일 설치 없음. 활성화 후 plug-in hook 으로 자동 발화.

## 공통 변수

이후 절차에서 반복 사용한다.

```bash
PLUGIN_ROOT="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)"
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"
```

`PLUGIN_ROOT` 또는 `PROJECT_ROOT` 가 비면 중단하고 plugin 설치 상태와 git repo 여부를 먼저 확인한다.

## Core Activation

core activation 의 성공 기준은 다음 항목까지다.

- whitelist 활성화
- `~/.claude/settings.json` Read 권한
- git hook shim 3종 설치
- Codex validator skill 배포
- Codex validation routing 상태 확인
- `dcness-helper status` 기준 FAIL 0

선택형 확장은 core activation 성공 조건이 아니다. CI workflow, project docs seed, design seed, GitHub Project lifecycle, workflow 변경 PR 은 INFO/WARN 으로 남아도 core 성공 메시지를 흐리지 않는다.

### Core Step 1 - 상태 진단

```bash
"$HELPER" status
```

`status` 는 현재 설치 상태를 PASS / WARN / FAIL / INFO / NA 진단표로 출력한다. 각 FAIL 항목은 해결 명령을 함께 보여주므로, 별도 doctor 명령 없이 셋업과 점검을 겸한다. self repo(dcNess 본체)에서는 외부 활성 항목이 `NA` 로 표기되어 self 작업 규칙과 섞이지 않는다.

진단표 기준 분기:

- `whitelist 활성` 이 PASS 면 Core Step 2 skip. FAIL 이면 Core Step 2.
- `Read 권한` FAIL → Core Step 3.
- `git hook shim 3종` FAIL → Core Step 4.
- `Codex validator skills` FAIL → Core Step 5 재실행.
- `Codex validation routing` 은 INFO 로 상태만 확인한다. 이미 enabled 면 다시 쓰지 않는다.
- `선택형 CI workflow` 는 INFO 다. core activation 성공/실패 판정에 넣지 않는다.

### Core Step 2 - 활성화

```bash
"$HELPER" enable
```

결과:

- 현재 cwd 의 main repo root 를 whitelist 에 추가.
- whitelist: `~/.claude/plugins/data/dcness-dcness/projects.json`
- 다음 Claude Code 세션부터 SessionStart / PreToolUse hook 이 활성 프로젝트로 인식.

### Core Step 3 - Read 권한 부여

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

### Core Step 4 - local git hook 설치

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

### Core Step 5 - Codex validator skill 배포와 routing 상태 확인

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

이미 Codex validation routing 이 enabled 면 질문하지 않고 현재 값을 유지한다. disabled/미설정이면 core completion 뒤 선택형 확장 추천 bundle 또는 custom 경로에서 다룬다.

```bash
"$HELPER" routing status
```

### Core Step 6 - 완료 선언

core 작업 뒤 `status` 를 재실행한다. FAIL 이 0 이면 INFO·NA 행과 선택 WARN 이 남아도 즉시 완료를 먼저 출력한다.

```bash
"$HELPER" status
```

```
[dcness] 활성화 완료
- 프로젝트: <main repo root>
- whitelist: ~/.claude/plugins/data/dcness-dcness/projects.json

다음 세션부터 자동 적용:
- SessionStart / PreToolUse / PostToolUse / SubagentStop / Stop hook
- TDD Guard 는 사용자 설정 없이 plug-in hook 으로 자동 발화

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

## 선택형 확장

core activation 완료 뒤에만 진행한다. 기본 경로에서 선택형 항목별 질문을 연속으로 던지지 않는다. 추천 summary 를 먼저 출력하고 마지막 줄의 `Y/n/custom` 하나만 실제 prompt 로 사용한다.

- 엔터 = Y
- 빈 입력은 Y 로 처리한다.
- `Y`: 탐지된 추천값을 한 번에 적용한다.
- `n`: 선택형 확장을 모두 skip 하고 core guard 만 유지한다.
- `custom`: 세부 경로로 진입하되 이미 결정 가능한 항목은 질문하지 않는다.

### 추천 bundle 산출 기준

- GitHub remote 가 있고 `.github/workflows/` 설치가 가능하면 `git-naming-validation.yml`, `pr-body-validation.yml` 추천 ON.
- 루트 `architecture.md` 가 있고 `docs/architecture.md` 가 없으면 `docs/architecture.md` 는 추천 OFF. 메시지에 `root architecture.md 감지로 docs/architecture.md skip` 을 남긴다.
- `docs/prd.md`, `docs/adr.md` 는 부재 시 추천 ON. 이미 있으면 skip.
- 루트 `architecture.md` 가 없고 `docs/architecture.md` 도 없으면 `docs/architecture.md` 추천 ON.
- UI 흔적이 있어도 `design-variants/` 는 기본 skip. 특히 단일 `app/page.tsx` 정도만으로 design kit 를 설치하지 않는다.
- GitHub Project lifecycle 은 기본 skip. `gh` 인증, Project number, PAT/secrets, field/label 복구가 얽히므로 custom 에서만 진행한다.
- Codex validation routing 이 이미 enabled 면 skip. disabled/미설정이면 추천 bundle 에서 enable 대상으로 표시하고, custom 에서는 명시 선택으로 다룬다.
- workflow 변경 PR 은 GitHub remote 가 있고, `gh auth status` 가 통과하고, `.github/workflows/*.yml` 변경이 있고, 현재 branch 가 `main` 이면 추천 ON. Y 선택 시 별도 질문 없이 branch 생성, workflow 파일만 stage, commit, push, PR 생성까지 진행한다. `gh` 미설치/미인증이면 자동 PR 은 skip 하고 custom/manual 안내만 남긴다.

추천 출력 예시:

```
[dcness] 추천 적용 예정:
 - CI: git-naming + pr-body 설치
 - docs: prd.md + adr.md 시드
 - docs: root architecture.md 감지로 docs/architecture.md skip
 - design kit: skip
 - Project lifecycle: skip
 - Codex validation routing: enable
 - workflow PR: gh 인증 + main branch + workflow 변경 시 자동 생성
적용할까요? (Y/n/custom)
```

### 추천 bundle 적용

#### 선택형 CI workflow

추천 ON 이면 reference 의 YAML snippet 을 그대로 써서 해당 파일을 always-overwrite 한다. snippet 진본은 [`docs/plugin/init-dcness.md#ci-workflow-snippets`](../docs/plugin/init-dcness.md#ci-workflow-snippets) 이다.

- `$PROJECT_ROOT/.github/workflows/git-naming-validation.yml`
- `$PROJECT_ROOT/.github/workflows/pr-body-validation.yml`

workflow 파일을 실제로 쓴 직후 이번 run 이 쓴 파일만 추적한다. workflow PR 은 이 목록만 stage 하며, 기존 dirty workflow 파일은 자동으로 포함하지 않는다.

```bash
DCNESS_WORKFLOW_CHANGES="${DCNESS_WORKFLOW_CHANGES:-}"
record_dcness_workflow_change() {
  DCNESS_WORKFLOW_CHANGES="$DCNESS_WORKFLOW_CHANGES $1"
}
```

`record_dcness_workflow_change` 는 선택되어 실제로 overwritten 된 파일에 대해서만 호출한다. skip 된 workflow 나 기존 dirty workflow 파일은 기록하지 않는다.

- `git-naming-validation.yml` 을 쓴 경우: `record_dcness_workflow_change ".github/workflows/git-naming-validation.yml"`
- `pr-body-validation.yml` 을 쓴 경우: `record_dcness_workflow_change ".github/workflows/pr-body-validation.yml"`
- custom 에서 `github-project-lifecycle.yml` 을 쓴 경우: `record_dcness_workflow_change ".github/workflows/github-project-lifecycle.yml"`

#### project docs seed

```bash
mkdir -p "$PROJECT_ROOT/docs"
for FILE in prd.md architecture.md adr.md; do
  if [ -f "$PROJECT_ROOT/docs/$FILE" ]; then
    echo "[dcness] docs/$FILE 이미 존재 - skip"
  elif [ "$FILE" = "architecture.md" ] && [ -f "$PROJECT_ROOT/architecture.md" ]; then
    echo "[dcness] root architecture.md 감지로 docs/architecture.md skip"
  else
    cp "$PLUGIN_ROOT/templates/project-init/$FILE" "$PROJECT_ROOT/docs/$FILE"
    echo "[dcness] docs/$FILE 시드 완료 - 기획 논의 후 채워넣으세요"
  fi
done
```

#### Codex validation routing

추천 ON 이고 현재 enabled 가 아니면 한 번만 실행한다.

```bash
"$HELPER" routing enable-codex-validation
"$HELPER" routing status
```

#### workflow 변경 PR

자동 PR 대상은 `/init-dcness` 가 배포한 `.github/workflows/*.yml` 변경만이다. TDD Guard 는 자동 hook 이라 사용자 repo 파일 변경이 없고, docs/design seed 는 사용자 콘텐츠라 자동 infra PR 에 섞지 않는다.

```bash
cd "$PROJECT_ROOT"
CHANGES="$(printf '%s\n' ${DCNESS_WORKFLOW_CHANGES:-} | awk 'NF && !seen[$0]++')"
CHANGES_TRIM="$(printf '%s\n' $CHANGES | xargs)"
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null)"
ORIGIN_URL="$(git remote get-url origin 2>/dev/null || true)"
case "$ORIGIN_URL" in
  *github.com*) GIT_REMOTE_OK=1 ;;
  *) GIT_REMOTE_OK=0 ;;
esac
if gh auth status >/dev/null 2>&1; then
  GH_AUTH_OK=1
else
  GH_AUTH_OK=0
fi

if [ -z "$CHANGES_TRIM" ]; then
  echo "[dcness] 이번 /init-dcness run 이 쓴 workflow 없음 - 선택형 workflow PR skip"
elif [ "$CURRENT_BRANCH" != "main" ]; then
  echo "[dcness] 현재 branch 가 main 이 아님($CURRENT_BRANCH) - workflow PR 자동 생성 skip"
  echo "[dcness] workflow 변경은 현재 branch 의 일반 작업에 포함하거나 main 에서 /init-dcness 를 재실행하세요."
elif [ "$GIT_REMOTE_OK" != "1" ]; then
  echo "[dcness] GitHub origin remote 없음 - workflow PR 자동 생성 skip"
  echo "[dcness] GitHub remote 설정 뒤 custom 에서 workflow PR 을 선택하거나 수동 PR 을 만드세요."
elif [ "$GH_AUTH_OK" != "1" ]; then
  echo "[dcness] gh auth 미인증/미설치 - workflow PR 자동 생성 skip"
  echo "[dcness] gh auth login 후 custom 에서 workflow PR 을 선택하거나 수동 PR 을 만드세요."
else
  STAGED_CHANGES=""
  for f in $CHANGES; do
    if git status --short -- "$f" | grep -q .; then
      STAGED_CHANGES="$STAGED_CHANGES $f"
    fi
  done
  CHANGES="$(printf '%s\n' $STAGED_CHANGES | xargs)"

  if [ -z "$CHANGES" ]; then
    echo "[dcness] 이번 run 이 쓴 workflow 파일에 실제 diff 없음 - 선택형 workflow PR skip"
  else
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

$(for f in $CHANGES; do
  case "$f" in
    *git-naming-validation.yml) echo "- \`git-naming-validation\`" ;;
    *pr-body-validation.yml) echo "- \`pr-body-validation\`" ;;
    *github-project-lifecycle.yml) echo "- \`github-project-lifecycle\`" ;;
  esac
done)
EOF
)"
  fi
fi
```

추천 bundle 에서 workflow PR 이 ON 이면 `gh auth status` 가 통과하고 현재 branch 가 `main` 이고 변경이 있을 때 별도 질문 없이 실행한다. custom 경로에서는 이 항목을 따로 선택할 수 있다.

### custom 세부 경로

custom 은 기존 세부 기능을 유지하되 이미 결정 가능한 항목은 질문하지 않는다.

- CI workflow: GitHub remote 가 없거나 `.github/workflows/` 를 쓸 수 없으면 묻지 않고 skip 이유를 남긴다. 가능하면 `git-naming-validation.yml`, `pr-body-validation.yml`, `github-project-lifecycle.yml` 을 각각 선택할 수 있다.
- docs seed: 이미 존재하는 파일은 묻지 않는다. 루트 `architecture.md` 가 있으면 `docs/architecture.md` 생성 질문을 생략하고 `root architecture.md 감지로 docs/architecture.md skip` 을 남긴다.
- design seed: UI 프로젝트 여부가 불명확할 때만 묻는다. `docs/design.md` 는 부재 시 [`docs/plugin/design.md`](../docs/plugin/design.md) 기준 minimal template 생성 여부를 선택한다. `design-variants/` 는 사용자가 명시 선택한 경우에만 설치한다.
- Codex routing: 현재 enabled 면 묻지 않는다. disabled/미설정이면 enable/disable 중 하나를 명시 선택한다.
- GitHub Project lifecycle: custom 에서만 진행한다. 세부 계약은 [`docs/plugin/github-project.md`](../docs/plugin/github-project.md) 와 [`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) 가 SSOT 다.
- workflow 변경 PR: `.github/workflows/*.yml` 변경이 있고 현재 branch 가 `main` 이고 `gh auth status` 가 통과할 때만 선택한다. 선택 시 workflow 파일만 stage 한다.

design seed 를 명시 선택한 경우:

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

GitHub Project lifecycle bootstrap 을 명시 선택한 경우 `Status / IssueType / Priority` 축과 repo label 6종을 점검한다.

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

Project lifecycle workflow 를 명시 선택한 경우 `$PROJECT_ROOT/.github/workflows/github-project-lifecycle.yml` 을 always-overwrite 한다. snippet 진본은 [`docs/plugin/init-dcness.md#ci-workflow-snippets`](../docs/plugin/init-dcness.md#ci-workflow-snippets) 이다.

## 이미 자동 적용되는 것

활성화 후 새 Claude Code 세션에서 plug-in hook 이 자동 발화한다. 사용자 repo 에 별도 파일을 설치하지 않는다.

- SessionStart: sid/live state 초기화와 활성 안내 inject.
- 순서 차단 훅: Agent 호출 전 작업 순서 보호.
- file-guard: agent 별 파일 경계와 외부 상태 변경 차단.
- TDD Guard: `Edit` / `Write` / `NotebookEdit` / `Bash` write target 의 TS/JS 구현 파일 매칭 test 존재 확인. 세부 skip/한계는 [`docs/plugin/hooks.md#tdd-guardsh`](../docs/plugin/hooks.md#tdd-guardsh).
- Stop hook: run 종료와 continuation signal.

## 추가 안내

재실행이 필요한 경우:

- plugin uninstall/reinstall 로 whitelist 가 사라진 경우
- 선택형 CI workflow 를 새로 깔거나 갱신하는 경우
- Codex validation 분기를 새로 opt-in 하는 경우
- Project lifecycle bootstrap 또는 project-local seed 가 필요한 경우

마지막 점검 권장:

```bash
"$HELPER" status
```

FAIL 이 0 이면 core activation 은 완료 상태다. INFO·NA 행과 선택 WARN 은 정상이다.

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
