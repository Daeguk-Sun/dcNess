# Init dcNess Bootstrap Reference

> **Status**: ACTIVE
> **Scope**: `/init-dcness` 가 사용자 프로젝트에 무엇을 쓰는지, 어떤 항목이 자동 적용되는지, 재실행 시 어떤 기준으로 skip/overwrite 되는지 설명한다.
> **Public surface**: 새 command 나 skill 을 추가하지 않는다. 사용자-facing 진입점은 `/init-dcness` 하나다.

`/init-dcness` 본문은 실행 런북이고, 이 문서는 상세 reference 다. hook 정책 자체의 SSOT 는 [`hooks.md`](hooks.md) 이며, 본 문서는 hook skip 룰을 재정의하지 않는다.

## Bootstrap Inventory

| 대상 | 위치 | Source | 언제 | 멱등성 | 자동 PR 대상 |
|---|---|---|---|---|---|
| 활성 whitelist | `~/.claude/plugins/data/dcness-dcness/projects.json` | `harness/session_state.py` | 항상 | 중복 제거 | X |
| Read 권한 | `~/.claude/settings.json` | `/init-dcness` jq patch | 항상 | 없을 때만 추가 | X |
| local git hook | `.git/hooks/commit-msg` | `scripts/hooks/commit-msg` | 항상 | always-overwrite | X |
| local git hook | `.git/hooks/post-checkout` | `scripts/hooks/post-checkout` | 항상 | always-overwrite | X |
| local git hook | `.git/hooks/pre-push` | `scripts/hooks/pre-push` | 항상 | always-overwrite | X |
| git naming workflow | `.github/workflows/git-naming-validation.yml` | 아래 [CI Workflow Snippets](#ci-workflow-snippets) | 사용자 선택 | always-overwrite | O |
| PR body workflow | `.github/workflows/pr-body-validation.yml` | 아래 [CI Workflow Snippets](#ci-workflow-snippets) | 사용자 선택 | always-overwrite | O |
| Project lifecycle workflow | `.github/workflows/github-project-lifecycle.yml` | 아래 [CI Workflow Snippets](#ci-workflow-snippets) | 사용자 선택 | always-overwrite | O |
| project docs seed | `docs/prd.md`, `docs/architecture.md`, `docs/adr.md` | `templates/project-init/*.md` | 사용자 선택 | 부재 시만 생성 | X |
| design seed | `docs/design.md` | `docs/plugin/design.md` minimal 예시 | UI 프로젝트 + 사용자 선택 | 부재 시만 생성 | X |
| design preview seed | `design-variants/**` | `templates/design-variants/**` | UI 프로젝트 + 사용자 선택 | 부재 시만 생성 | X |
| Codex validator skills | `$CODEX_HOME/skills/dcness-*` | `codex/skills/dcness-*` | 항상 복사 후 opt-in 질문 | always-overwrite | X |
| Codex provider routing | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing ...` | 사용자 선택 | opt-in 값으로 갱신 | X |
| Project coordinates | repo variables `DCNESS_PROJECT_NUMBER`, `DCNESS_PROJECT_OWNER` | `gh variable set` | Project bootstrap 선택 | 값 갱신 | X |
| CC hooks | Claude Code plugin hook registry | `hooks/hooks.json` | 활성 프로젝트 새 세션 | 사용자 repo 쓰기 없음 | X |

## Already Automatic

`/init-dcness` 가 whitelist 를 활성화하면 새 Claude Code 세션부터 [`hooks/hooks.json`](../../hooks/hooks.json) 의 CC hooks 가 자동 등록된다. 사용자가 따로 설치할 파일은 없다.

- `session-start.sh`: 세션 상태 초기화와 활성 안내.
- `catastrophic-gate.sh`: Agent 호출 전 작업 순서 보호.
- `file-guard.sh`: file/bash/MCP 경계와 외부 상태 변경 차단.
- `tdd-guard.sh`: TS/JS 구현 파일 수정 직전 매칭 test 존재 확인. 상세 범위와 한계는 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 가 SSOT.
- `post-agent-clear.sh`, `post-file-op-trace.sh`, `subagent-stop-clear.sh`, `stop-end-run.sh`: run state 보존과 종료 처리.

과거 TDD 관련 CI/commit-msg 방식의 폐기 이력은 release note 기록이며, `/init-dcness` 실행 절차가 아니다. 현행 TDD Guard 계약은 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 만 따른다.

## CI Workflow Snippets

사용자가 `/init-dcness` 에서 선택한 workflow 만 사용자 repo 의 `.github/workflows/` 에 쓴다. 검증 본체는 사용자 repo 에 복사하지 않고 dcNess composite action 을 호출한다.

### git-naming-validation.yml

경로: `.github/workflows/git-naming-validation.yml`

```yaml
name: git-naming-validation
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, edited]
permissions:
  contents: read
  pull-requests: read
jobs:
  naming:
    name: git-naming-spec gate
    runs-on: ubuntu-latest
    steps:
      - uses: alruminum/dcNess/.github/actions/git-naming@main
        with:
          branch: ${{ github.head_ref }}
          title: ${{ github.event.pull_request.title }}
```

### pr-body-validation.yml

경로: `.github/workflows/pr-body-validation.yml`

```yaml
name: pr-body-validation
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, edited]
permissions:
  contents: read
  pull-requests: read
jobs:
  pr-body:
    name: PR body close-keyword gate
    runs-on: ubuntu-latest
    steps:
      - uses: alruminum/dcNess/.github/actions/pr-body@main
        with:
          body: ${{ github.event.pull_request.body }}
```

### github-project-lifecycle.yml

경로: `.github/workflows/github-project-lifecycle.yml`

```yaml
name: github-project-lifecycle
on:
  issues:
    types: [opened, edited, labeled, unlabeled]
  pull_request:
    types: [closed]
permissions:
  contents: read
  issues: read
  pull-requests: read
jobs:
  issue-drift:
    if: ${{ github.event_name == 'issues' && vars.DCNESS_PROJECT_NUMBER != '' }}
    runs-on: ubuntu-latest
    steps:
      - uses: alruminum/dcNess/.github/actions/github-project-lifecycle@main
        with:
          mode: validate-issue
          repo: ${{ github.repository }}
          project-owner: ${{ vars.DCNESS_PROJECT_OWNER || github.repository_owner }}
          project-number: ${{ vars.DCNESS_PROJECT_NUMBER }}
          issue-number: ${{ github.event.issue.number }}
          gh-token: ${{ secrets.DCNESS_PROJECT_TOKEN || github.token }}
  pr-merged:
    if: ${{ github.event_name == 'pull_request' && github.event.pull_request.merged == true && vars.DCNESS_PROJECT_NUMBER != '' }}
    runs-on: ubuntu-latest
    steps:
      - uses: alruminum/dcNess/.github/actions/github-project-lifecycle@main
        with:
          mode: pr-merged
          repo: ${{ github.repository }}
          project-owner: ${{ vars.DCNESS_PROJECT_OWNER || github.repository_owner }}
          project-number: ${{ vars.DCNESS_PROJECT_NUMBER }}
          pr-body: ${{ github.event.pull_request.body }}
          apply: "true"
          gh-token: ${{ secrets.DCNESS_PROJECT_TOKEN || github.token }}
```

Project v2 쓰기에는 `secrets.DCNESS_PROJECT_TOKEN` 에 classic PAT `project` + `read:org` scope 가 필요하다. token 이 없으면 drift 검출 중심으로 실패 메시지를 남기며, owner type 판별은 graceful degrade 한다.

## Project Bootstrap Commands

Project lifecycle 축은 [`github-project.md`](github-project.md) 가 SSOT 다. `/init-dcness` 는 좌표를 확인한 뒤 같은 script 를 호출한다.

명령 본체: `scripts/github_project_lifecycle.mjs bootstrap`. 활성 프로젝트에서는 `$PLUGIN_ROOT` 안의 script 를 호출하고, dcNess self repo 에서 직접 검증할 때는 repo-local script 를 호출해도 된다.

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

Project가 없거나 필드가 부족하면 생성 또는 복구 안내를 제공한다. repo label이 부족하면 `--apply` 로 생성/갱신할 수 있다. 기존 Project field 의 option 이 부족한 경우는 GitHub CLI 제한 때문에 script 가 복구 안내를 내고 멈춘다. 다른 repo 에 적용할 때도 `--repo`, `--owner`, `--project` 값을 바꿔 같은 bootstrap 경로를 사용한다.

```bash
node "$PLUGIN_ROOT/scripts/github_project_lifecycle.mjs" bootstrap \
  --repo "$REPO" \
  --owner "$OWNER" \
  --project "$PROJECT_NUMBER" \
  --apply
```

## Re-run Matrix

| 상황 | `/init-dcness` 재실행 필요 | 이유 |
|---|---:|---|
| plugin 본체 문서/skill/hook 만 갱신 | 아니오 | `claude plugin update dcness@dcness` 로 plug-in cache 가 갱신된다. |
| plugin uninstall/reinstall | 예 | plugin data 디렉토리가 정리되어 whitelist 가 사라진다. |
| `.git/hooks/*` thin shim 갱신 | 예 | 사용자 repo `.git/hooks/` 파일은 plugin update 만으로 바뀌지 않는다. |
| 선택형 `.github/workflows/*.yml` 갱신 | 예 | workflow 파일은 사용자 repo 에 배포된 사본이다. |
| Codex validator routing opt-in 변경 | 예 | local plugin data 와 `$CODEX_HOME/skills` 를 갱신해야 한다. |
| Project lifecycle 좌표 저장/변경 | 예 | repo variables 와 선택형 workflow 를 갱신해야 한다. |
| docs/design/project-init/design-variants seed 추가 | 예 | 부재 파일 seed 는 사용자 repo 에 직접 생성된다. |
| TDD Guard 정책 갱신 | 아니오 | 사용자 repo 파일이 아니라 plug-in hook 본체가 갱신된다. |

## Auto PR Scope

`/init-dcness` 의 자동 commit + PR 단계는 `.github/workflows/*.yml` 만 대상으로 한다.

- 포함: `git-naming-validation.yml`, `pr-body-validation.yml`, `github-project-lifecycle.yml`
- 제외: `.git/hooks/*` (git 내부 파일), `~/.claude/**`, `$CODEX_HOME/**`, `docs/*` seed, `design-variants/*` seed, 자동 CC hook 설명

seed 문서는 사용자 프로젝트 내용물이므로 사용자가 별도 작업 PR 에 포함할지 직접 판단한다.

## References

- [`hooks.md`](hooks.md) - CC hook / git hook / CI layer policy
- [`git-spec.md`](git-spec.md) - branch / commit / PR naming
- [`github-project.md`](github-project.md) - Project v2 fields and bootstrap
- [`issue-lifecycle.md`](issue-lifecycle.md) - issue hierarchy and Project lifecycle
- [`design.md`](design.md) - `docs/design.md` format
- [`hooks/hooks.json`](../../hooks/hooks.json) - CC hook registration
