# Init dcNess Bootstrap Reference

> **Status**: ACTIVE
> **Scope**: `/init-dcness` 가 사용자 프로젝트에 무엇을 쓰는지, 어떤 항목이 자동 적용되는지, 재실행 시 어떤 기준으로 skip/overwrite 되는지 설명한다.
> **Public surface**: 새 command 나 skill 을 추가하지 않는다. 사용자-facing 진입점은 `/init-dcness` 하나다.

`/init-dcness` 본문은 실행 런북이고, 이 문서는 상세 reference 다. hook 정책 자체의 SSOT 는 [`hooks.md`](hooks.md) 이며, 본 문서는 hook skip 룰을 재정의하지 않는다.

## Bootstrap Inventory

### Core

core activation 완료 기준이다. 아래 항목이 끝나고 `dcness-helper status` 기준 FAIL 이 0 이면 `/init-dcness` 는 즉시 `활성화 완료`를 출력한다. Optional 항목의 INFO/WARN 은 core 성공 조건이 아니다.

| 대상 | 위치 | Source | 언제 | 멱등성 | 자동 PR 대상 |
|---|---|---|---|---|---|
| 활성 whitelist | `~/.claude/plugins/data/dcness-dcness/projects.json` | `harness/session_state.py` | 항상 | 중복 제거 | X |
| Read 권한 | `~/.claude/settings.json` | `/init-dcness` jq patch | 항상 | 없을 때만 추가 | X |
| local git hook | `.git/hooks/commit-msg` | `scripts/hooks/commit-msg` | 항상 | always-overwrite | X |
| local git hook | `.git/hooks/post-checkout` | `scripts/hooks/post-checkout` | 항상 | always-overwrite | X |
| local git hook | `.git/hooks/pre-push` | `scripts/hooks/pre-push` | 항상 | always-overwrite | X |
| Codex validator skills | `$CODEX_HOME/skills/dcness-*` | `codex/skills/dcness-*` | 항상 | always-overwrite | X |
| Codex provider routing 상태 확인 | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing status` | 항상 확인 | read-only | X |
| CC hooks | Claude Code plugin hook registry | `hooks/hooks.json` | 활성 프로젝트 새 세션 | 사용자 repo 쓰기 없음 | X |

### Optional

core activation 완료 뒤 추천 bundle 1질문(`Y/n/custom`, 엔터 = Y) 또는 custom 경로에서만 적용한다. 기본 `n` 또는 skip 은 core guard 를 끄지 않는다.

| 대상 | 위치 | Source | 언제 | 멱등성 | 자동 PR 대상 |
|---|---|---|---|---|---|
| git naming workflow | `.github/workflows/git-naming-validation.yml` | [`templates/github-workflows/git-naming-validation.yml`](../../templates/github-workflows/git-naming-validation.yml) | GitHub remote 감지 시 추천 ON | always-overwrite | O |
| PR body workflow | `.github/workflows/pr-body-validation.yml` | [`templates/github-workflows/pr-body-validation.yml`](../../templates/github-workflows/pr-body-validation.yml) | GitHub remote 감지 시 추천 ON | always-overwrite | O |
| Project lifecycle workflow | `.github/workflows/github-project-lifecycle.yml` | [`templates/github-workflows/github-project-lifecycle.yml`](../../templates/github-workflows/github-project-lifecycle.yml) | custom 선택 | always-overwrite | O |
| project docs seed | `docs/prd.md`, `docs/architecture.md`, `docs/adr.md` | `templates/project-init/*.md` | 추천 bundle 또는 custom | 부재 시만 생성 | X |
| design seed | `docs/design.md` | `docs/plugin/design.md` minimal 예시 | custom 선택 | 부재 시만 생성 | X |
| design preview seed | `design-variants/**` | `templates/design-variants/**` | custom 선택 | 부재 시만 생성 | X |
| Codex provider routing 변경 | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing ...` | disabled/미설정일 때 추천 bundle 또는 custom | opt-in 값으로 갱신 | X |
| Project coordinates | repo variables `DCNESS_PROJECT_NUMBER`, `DCNESS_PROJECT_OWNER` | `gh variable set` | Project bootstrap 선택 | 값 갱신 | X |

> 🔴 **진단 동기화 의무**: 위 inventory 에 새 복사/배포 대상(git hook · CI workflow · 권한 등)을 추가하면, `dcness-helper status` 진단표(`harness/session_state.py` 의 `collect_status_diagnostics`)에도 해당 검사 항목을 함께 추가한다. 그렇지 않으면 사용자가 설치 누락을 한눈에 확인할 수 없다.

`dcness-helper status` 는 설치 상태뿐 아니라 최근 hook fail-open 활동도 `hook fail-open 진단` 항목으로 보여준다. 정상 inactive no-op 은 기록하지 않고, 활성 프로젝트에서 enforcement hook 이 검사를 평가하지 못하고 allow 한 경우만 최근 reason category 를 WARN 으로 노출한다. 자세한 정책은 [`hooks.md`](hooks.md) 가 SSOT 다.

## Recommended Bundle Defaults

`/init-dcness` 기본 경로는 core activation 완료 뒤 `Y/n/custom` 1질문만 사용한다. 엔터 = Y 다.

- GitHub remote 가 있고 `.github/workflows/` 설치가 가능하면 `git-naming-validation.yml`, `pr-body-validation.yml` 추천 ON.
- 루트 `architecture.md` 가 있고 `docs/architecture.md` 가 없으면 `docs/architecture.md` 는 추천 OFF. 메시지에 `root architecture.md 감지로 docs/architecture.md skip` 을 남긴다.
- `docs/prd.md`, `docs/adr.md` 는 부재 시 추천 ON. 이미 있으면 skip.
- 루트 `architecture.md` 가 없고 `docs/architecture.md` 도 없으면 `docs/architecture.md` 추천 ON.
- `design-variants/` 는 기본 skip. 단일 `app/page.tsx` 정도의 UI 흔적만으로 design kit 를 설치하지 않는다.
- GitHub Project lifecycle 은 기본 skip. `gh` 인증, Project number, PAT/secrets, field/label 복구가 얽히므로 custom 에서만 진행한다.
- Codex validation routing 이 이미 enabled 면 skip. disabled/미설정이면 추천 bundle 또는 custom 에서 명시적으로 다룬다.
- workflow 변경 PR 은 GitHub remote 가 있고, `gh auth status` 가 통과하고, 이번 `/init-dcness` run 이 쓴 `.github/workflows/*.yml` 변경이 있고, 현재 branch 가 `main` 이면 추천 ON. Y 선택 시 별도 질문 없이 해당 파일만 stage 해서 branch/commit/push/PR 을 진행한다. `gh` 미설치/미인증이면 자동 PR 은 skip 하고 custom/manual 안내만 남긴다. 기존 dirty workflow 파일은 자동 포함하지 않는다.

## Already Automatic

`/init-dcness` 가 whitelist 를 활성화하면 새 Claude Code 세션부터 [`hooks/hooks.json`](../../hooks/hooks.json) 의 CC hooks 가 자동 등록된다. 사용자가 따로 설치할 파일은 없다.

- `session-start.sh`: 세션 상태 초기화와 활성 안내.
- `catastrophic-gate.sh`: Agent 호출 전 작업 순서 보호.
- `file-guard.sh`: file/bash/MCP 경계와 외부 상태 변경 차단.
- `tdd-guard.sh`: TS/JS 구현 파일 및 Bash write target 수정 직전 매칭 test 존재 확인. 상세 범위와 한계는 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 가 SSOT.
- `post-agent-clear.sh`, `post-file-op-trace.sh`, `subagent-stop-clear.sh`, `stop-end-run.sh`: run state 보존과 종료 처리.

과거 TDD 관련 CI/commit-msg 방식의 폐기 이력은 release note 기록이며, `/init-dcness` 실행 절차가 아니다. 현행 TDD Guard 계약은 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 만 따른다.

## CI Workflow Snippets

기존 `#ci-workflow-snippets` anchor 호환을 위해 heading 은 유지한다. 이 섹션은 더 이상 YAML 전문을 소유하지 않고, `/init-dcness` 가 사용자 repo 의 `.github/workflows/` 로 복사하는 workflow template inventory 만 제공한다. 검증 본체는 사용자 repo 에 복사하지 않고 dcNess composite action 을 호출한다.

### git-naming-validation.yml

- 대상 경로: `.github/workflows/git-naming-validation.yml`
- 템플릿: [`templates/github-workflows/git-naming-validation.yml`](../../templates/github-workflows/git-naming-validation.yml)
- 역할: `alruminum/dcNess/.github/actions/git-naming@main` 을 호출해 `github.head_ref` 와 PR title 을 검증한다.

### pr-body-validation.yml

- 대상 경로: `.github/workflows/pr-body-validation.yml`
- 템플릿: [`templates/github-workflows/pr-body-validation.yml`](../../templates/github-workflows/pr-body-validation.yml)
- 역할: `alruminum/dcNess/.github/actions/pr-body@main` 을 호출해 PR body 에 issue trailer 가 있는지 확인한다.

### github-project-lifecycle.yml

- 대상 경로: `.github/workflows/github-project-lifecycle.yml`
- 템플릿: [`templates/github-workflows/github-project-lifecycle.yml`](../../templates/github-workflows/github-project-lifecycle.yml)
- 역할: `alruminum/dcNess/.github/actions/github-project-lifecycle@main` 을 호출해 issue drift 를 검출하고 merged PR 의 완료 후보 issue 를 Project Status `Done` 으로 보정한다.

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
- 선행 조건: GitHub remote 존재, 현재 branch `main`, `gh auth status` 통과. 조건이 안 맞으면 branch/commit/push 를 시작하지 않고 skip 안내만 출력한다.

seed 문서는 사용자 프로젝트 내용물이므로 사용자가 별도 작업 PR 에 포함할지 직접 판단한다.

## References

- [`hooks.md`](hooks.md) - CC hook / git hook / CI layer policy
- [`git-spec.md`](git-spec.md) - branch / commit / PR naming
- [`github-project.md`](github-project.md) - Project v2 fields and bootstrap
- [`issue-lifecycle.md`](issue-lifecycle.md) - issue hierarchy and Project lifecycle
- [`design.md`](design.md) - `docs/design.md` format
- [`hooks/hooks.json`](../../hooks/hooks.json) - CC hook registration
