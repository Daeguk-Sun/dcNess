# Init dcNess Bootstrap Reference

> **Status**: ACTIVE
> **Scope**: `/init-dcness` 가 사용자 프로젝트에 무엇을 쓰는지, 어떤 항목이 자동 적용되는지, 재실행 시 어떤 기준으로 skip/overwrite 되는지 설명한다.
> **Public surface**: 새 command 나 skill 을 추가하지 않는다. 사용자-facing 진입점은 `/init-dcness` 하나다.

`/init-dcness` 본문은 실행 런북이고, 이 문서는 상세 reference 다. hook 정책 자체의 SSOT 는 [`hooks.md`](hooks.md) 이며, 본 문서는 hook skip 룰을 재정의하지 않는다.

## Completion Onboarding

Core activation 완료 출력은 한 화면 분량의 **5분 온보딩** 블록을 포함한다. 이 블록은 SSOT 본문을 복제하지 않고 다음 포인터만 제공한다.

- 강제/자율 경계: [`hooks.md#catastrophic-gatesh`](hooks.md#catastrophic-gatesh) 와 [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)
- 첫 작업 진입점: [`workflow-router.md#구현-경로-표`](workflow-router.md#구현-경로-표) 와 [`positioning.md`](positioning.md)
- hook-first recovery / 재실행 판단: hook 차단 메시지, `dcness-helper status`, 본 문서 [Re-run Matrix](#re-run-matrix)

## Bootstrap Inventory

### Core

core activation 완료 기준이다. 아래 항목이 끝나고 `dcness-helper status` 기준 FAIL 이 0 이면 `/init-dcness` 는 즉시 `활성화 완료`를 출력한다. Optional 항목의 INFO/WARN 은 core 성공 조건이 아니다.

| 대상 | 위치 | Source | 언제 | 멱등성 | 자동 PR 대상 |
|---|---|---|---|---|---|
| 활성 whitelist | `~/.claude/plugins/data/dcness-dcness/projects.json` | `harness/session_state.py` | 항상 | 중복 제거 | X |
| Read 권한 | `~/.claude/settings.json` | `/init-dcness` jq patch | 항상 | 없을 때만 추가 | X |
| local git hook | `.git/hooks/pre-commit` | `scripts/hooks/pre-commit` | 항상 | always-overwrite | X |
| local git hook | `.git/hooks/commit-msg` | `scripts/hooks/commit-msg` | 항상 | always-overwrite | X |
| local git hook | `.git/hooks/post-checkout` | `scripts/hooks/post-checkout` | 항상 | always-overwrite | X |
| local git hook | `.git/hooks/pre-push` | `scripts/hooks/pre-push` | 항상 | always-overwrite | X |
| runtime state ignore | `.gitignore` 의 `.claude/harness-state/` | `/init-dcness` append | 항상 | 없을 때만 추가 | X |
| project context seed/migration | `CLAUDE.md` | `scripts/dcness-context-docs` / `harness/context_docs.py` | 항상 | 부재 시 생성. 기존 파일은 cold-start 앵커만 없을 때 append | X |
| file boundary override suggestion | `.dcness/boundary.json` 후보만 | `dcness-helper boundary-suggestions` / `harness/boundary_suggestions.py` | 항상 | read-only. 사람 승인 전 작성 없음 | X |
| generated TDD hook 제안/생성 | `.dcness/tdd-hooks.json`, `.claude/settings.json`, `.claude/hooks/dcness-tdd-guard.sh`, `.codex/hooks.json`, `.codex/hooks/dcness-tdd-guard.sh` | `scripts/dcness-tdd-hooks` | 플랫폼 감지 또는 사람 승인된 project-local 계약 + 사용자 승인 시 | self-test 통과 후보만 등록. CC 검증 후 Codex 생성 | X |
| Codex validator skills | `$CODEX_HOME/skills/dcness-*` | `codex/skills/dcness-*` | 항상 | always-overwrite. Validator wrapper 는 활성 plugin 원본을 우선 주입하고 이 복사본은 native Codex skill 등록과 fallback 용도 | X |
| Codex provider routing 상태 확인 | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing status` | 항상 확인 | read-only | X |
| CC hooks | Claude Code plugin hook registry | `hooks/hooks.json` | 활성 프로젝트 새 세션 | 사용자 repo 쓰기 없음 | X |

### Optional

core activation 완료 뒤 추천 bundle 1질문(`Y/n/custom`, 엔터 = Y) 또는 custom 경로에서만 적용한다. 기본 `n` 또는 skip 은 core guard 를 끄지 않는다.

| 대상 | 위치 | Source | 언제 | 멱등성 | 자동 PR 대상 |
|---|---|---|---|---|---|
| git naming workflow | `.github/workflows/git-naming-validation.yml` | [`templates/github-workflows/git-naming-validation.yml`](../../templates/github-workflows/git-naming-validation.yml) | GitHub remote 감지 시 추천 ON | always-overwrite | O |
| PR body workflow | `.github/workflows/pr-body-validation.yml` | [`templates/github-workflows/pr-body-validation.yml`](../../templates/github-workflows/pr-body-validation.yml) | GitHub remote 감지 시 추천 ON | always-overwrite | O |
| doc path workflow | `.github/workflows/doc-path-integrity.yml` | [`templates/github-workflows/doc-path-integrity.yml`](../../templates/github-workflows/doc-path-integrity.yml) | GitHub remote 감지 시 추천 ON | always-overwrite | O |
| doc sync workflow | `.github/workflows/doc-sync.yml` | [`templates/github-workflows/doc-sync.yml`](../../templates/github-workflows/doc-sync.yml) | GitHub remote 감지 시 추천 ON | always-overwrite | O |
| Project lifecycle workflow | `.github/workflows/github-project-lifecycle.yml` | [`templates/github-workflows/github-project-lifecycle.yml`](../../templates/github-workflows/github-project-lifecycle.yml) | custom 선택 | always-overwrite | O |
| project docs seed | `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` | authoring 템플릿 (`skills/spec/templates/index.md`, `skills/spec/templates/prd.md`, `docs/plugin/agents/system-architect/templates/root-architecture.md`, `docs/plugin/agents/system-architect/templates/conventions.md`) + `scripts/ensure_docs_index_next_section.mjs` — 시드와 산출 양식 단일 원본. 위치 SSOT [`deliverables-map.md`](deliverables-map.md) | 추천 bundle 또는 custom | 부재 시 생성. 기존 `docs/index.md` 는 진행 상태 섹션만 없을 때 append | X |
| volatile workdir ignore | `.gitignore` 의 `.dcness-work/` + `.claude/harness-state/` 재확인 | `/init-dcness` append | 추천 bundle 또는 custom | 없을 때만 추가 | X |
| design seed | `docs/design.md` | `docs/plugin/design.md` minimal 예시 | custom 선택 | 부재 시만 생성 | X |
| design preview seed | `docs/design-variants/**` | `templates/design-variants/**` | custom 선택 | 부재 시만 생성 | X |
| Role-split provider routing preset | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing enable-role-split-routing` | 추천 bundle | `build-worker=headless-chain`, `impl-validator=codex`, `architecture-validator=codex` | X |
| Validation routing custom | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing enable-codex-validation` / `disable-codex-validation` | custom | all-codex validation 또는 Claude validation 복귀 | X |
| Implementation routing custom | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing enable-headless-implementation` / `enable-claude-headless-implementation` / `set-implementation build-worker claude` | custom | `headless-chain`, `claude-headless`, `claude` 가능 | X |
| Project coordinates | repo variables `DCNESS_PROJECT_NUMBER`, `DCNESS_PROJECT_OWNER` | `gh variable set` | Project bootstrap 선택 | 값 갱신 | X |

> 🔴 **진단 동기화 의무**: 위 inventory 에 새 복사/배포 대상(git hook · CI workflow · 권한 등)을 추가하면, `dcness-helper status` 진단표(`harness/session_state.py` 의 `collect_status_diagnostics`)에도 해당 검사 항목을 함께 추가한다. 그렇지 않으면 사용자가 설치 누락을 한눈에 확인할 수 없다.

`dcness-helper status` 는 설치 상태뿐 아니라 최근 hook fail-open 활동도 `hook fail-open 진단` 항목으로 보여준다. 정상 inactive no-op 은 기록하지 않고, 활성 프로젝트에서 enforcement hook 이 검사를 평가하지 못하고 allow 한 경우만 최근 reason category 를 WARN 으로 노출한다. 자세한 정책은 [`hooks.md`](hooks.md) 가 SSOT 다.

`CLAUDE.md` seed/migration 은 사용자 repo 에 복사하지 않는 plugin script (`$PLUGIN_ROOT/scripts/dcness-context-docs`) 로 처리한다. 부재 시 Anthropic 공식 구조 기반 템플릿을 만들고, 기존 파일은 cold-start 앵커만 additive append 한다. 6축 quality audit 결과는 출력하지만 구조 개선·삭제·재배치는 후보만 제안한다.

파일 경계 override 제안은 `dcness-helper boundary-suggestions` 로 처리한다. 코어 `ALLOW_MATRIX` 가 커버하지 않는 비표준 소스 디렉터리가 있을 때만 `.dcness/boundary.json` 의 implementation add 후보를 출력하며, 표준 레이아웃·빈 프로젝트·이미 override 로 커버된 프로젝트는 no-op 이다. 이 helper 는 read-only 이므로 실제 boundary 파일 작성은 사람 승인 뒤 메인이 수행한다.

Generated TDD hook 은 `scripts/dcness-tdd-hooks` 로 처리한다. dcNess 소유 영역은 **TDD 계약**과 **self-test** 이며, self-test fixture 는 `무-test 구현 파일 → deny`, `매칭 test 있음 → allow`, `test 파일 자체 → allow` 를 검증한다. helper 는 `python`, `web`, `go`, `android`, `ios` 프리셋으로 기본 project-local config 를 만들 수 있고, 프리셋 미지원 플랫폼은 사람 승인된 `.dcness/tdd-hooks.json` 계약을 우선 사용한다. 모든 계약은 `source_roots`, `impl_exts` 가 필요하고, custom 플랫폼은 `test_candidate_templates` 도 필요하다. 선택 `test_file_globs` 로 test 파일 자체 allow 규칙을 보강한다. `/init-dcness` 에서 생성할 때는 CC hook 후보를 먼저 self-test 하고 통과해야 `.claude/settings.json` 에 등록한다. 그 다음 Codex hook 후보를 같은 계약으로 self-test 하고 `.codex/hooks.json` 에 등록한다. 빈 프로젝트·project-local 계약 없는 미지원 플랫폼·생성 실패는 no-op 으로 안전 통과한다.

생성 파일(`.dcness/tdd-hooks.json`, `.claude/settings.json`, `.claude/hooks/dcness-tdd-guard.sh`, `.codex/hooks.json`, `.codex/hooks/dcness-tdd-guard.sh`)은 자동 workflow PR 에 섞지 않는다. in-place 실행은 현재 디스크의 hook 파일이 실존·등록돼 있으면 커밋 없이도 impl pre-flight 를 통과한다. 다만 linked worktree 나 headless worker 체크아웃에서 project-local hook 을 재사용하려면 이 파일들이 Git 에 커밋돼 있어야 하며, 없으면 중앙 fallback 으로 내려간다. `scripts/dcness-tdd-hooks status` 와 `ensure` 는 linked worktree 에서 커밋이 필요한 경우 `commit-required`, in-place 에서만 실존하는 경우 `commit-advisory` 를 출력한다.

`docs/index.md` 의 epic/module 표와 기존 `docs/index.md` 의 진행 상태 섹션 보강은 사용자 repo 에 복사하지 않는 plugin script (`$PLUGIN_ROOT/scripts/aggregate_index_map.mjs`, `$PLUGIN_ROOT/scripts/ensure_docs_index_next_section.mjs`) 로 처리한다. 전역 architecture 인간용 요약은 필요할 때 `$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs` 로 `.dcness-work/reports/architecture-map.md` 에 온디맨드 생성한다. `/design` 산출물 구조 감사도 사용자 repo 에 복사하지 않는 plugin script (`$PLUGIN_ROOT/scripts/check_design_artifact_structure.mjs`) 로 처리한다. 활성 프로젝트에서는 이 스크립트를 현재 프로젝트 루트에서 실행한다.

제품 journey runner도 사용자 repo에 복사하지 않는 plugin script (`$PLUGIN_ROOT/scripts/dcness-product-journey`)로 제공한다. project-local 계약은 owner module/소스 영역의 opt-in 매니페스트이며 `/init-dcness`가 자동 생성하거나 덮어쓰지 않는다. UI journey도 같은 계약과 helper를 재사용하고 project-owned command가 단계별 화면 증거를 생성한다. 실행 receipt와 log는 기존 ignored `.dcness-work/product-journey/`에 남고 [`outcome-scorecard.md`](outcome-scorecard.md)가 집계한다. 계약과 판정 경계는 [`product-journey.md`](product-journey.md)가 소유한다.

## Provider Routing

provider config는 프로젝트별 파일이 아니라 plugin 공용 `~/.claude/plugins/data/dcness-dcness/routing.json` 하나다. 지원 형식은 schema v3의 `routes`와 `implementation_routes`이며, validation agent는 `impl-validator`·`architecture-validator`, implementation agent는 `build-worker`만 지원한다.

- 추천 role split은 `routing enable-role-split-routing`으로 `build-worker=headless-chain`, `impl-validator=codex`, `architecture-validator=codex`를 함께 기록한다.
- validation custom은 `routing enable-codex-validation`, `routing disable-codex-validation` 또는 `routing set <agent> claude|codex`를 사용한다.
- implementation custom은 `routing enable-headless-implementation`, `routing enable-claude-headless-implementation` 또는 `routing set-implementation build-worker claude|claude-headless|headless-chain`을 사용한다. Claude-only는 `routing set-implementation build-worker claude`다.
- schema v3만 지원한다. `routing doctor`가 version 오류로 실패하는 config는 삭제하고 `routing enable-role-split-routing`으로 현행 파일을 새로 만든 뒤 필요한 custom override를 적용한다.

config 형식 검증과 runtime provider fallback은 다른 계약이다. `headless-chain`은 provider가 workspace를 바꾸기 전에 실패했을 때만 다음 provider로 진행하고, 변경 뒤 실패하면 중단한다.

## Provider Mirror Sync

`impl-validator`, `architecture-validator` 의 판단 축·결론 어휘·FAIL/ESCALATE 보고 가이드를 바꾸는 PR 은 Claude 경로와 Codex mirror 를 같은 PR 안에서 함께 갱신한다.

| validator | Claude path | Codex mirror path |
|---|---|---|
| architecture-validator | `docs/plugin/agents/architecture-validator/architecture-validator-agent.md` | `codex/skills/dcness-architecture-validator/SKILL.md` |
| impl-validator | `docs/plugin/agents/impl-validator/impl-validator-agent.md` | `codex/skills/dcness-impl-validator/SKILL.md` |

공유 guidance 는 `docs/plugin/agents/_shared/validation-reporting-guidance.md` 를 Claude agent 가 참조하고, Codex skill 은 같은 의미 문구를 내장한다. Codex skill 은 native Codex frontmatter(`--- name: ... description: ... ---`)를 유지해야 하며, `/init-dcness` Core Step 5 가 `$CODEX_HOME/skills/dcness-*` 로 always-overwrite 배포한다. 동기화 회귀는 `tests/test_validator_handoff_guidance.py` 가 막는다.

`scripts/dcness-codex-validator` 는 plugin update 직후 재-init 전에도 현행 지침을 쓰도록 활성 plugin 원본을 먼저 prompt 에 주입한다. `$CODEX_HOME` 배포본이 원본과 다르면 stale copy 로 경고한 뒤 원본을 사용한다.

## Recommended Bundle Defaults

`/init-dcness` 기본 경로는 core activation 완료 뒤 `Y/n/custom` 1질문만 사용한다. 엔터 = Y 다.

- GitHub remote 가 있고 `.github/workflows/` 설치가 가능하면 `git-naming-validation.yml`, `pr-body-validation.yml`, `doc-path-integrity.yml`, `doc-sync.yml` 추천 ON.
- 루트 `architecture.md` 가 있고 `docs/architecture.md` 가 없으면 `docs/architecture.md` 는 추천 OFF. 메시지에 `root architecture.md 감지로 docs/architecture.md skip` 을 남긴다.
- `docs/index.md`, `docs/prd.md`, `docs/conventions.md`, `docs/decisions/` 는 부재 시 추천 ON. 기존 `docs/index.md` 에 진행 상태 섹션이 없으면 보강 ON.
- 루트 `architecture.md` 가 없고 `docs/architecture.md` 도 없으면 `docs/architecture.md` 추천 ON.
- `.gitignore` 에 `.dcness-work/` 가 없으면 추천 ON. `.claude/harness-state/` 는 core activation 에서 항상 보장한다.
- `docs/design-variants/` 는 기본 skip. 단일 `app/page.tsx` 정도의 UI 흔적만으로 design kit 를 설치하지 않는다.
- GitHub Project lifecycle 은 기본 skip. `gh` 인증, Project number, PAT/secrets, field/label 복구가 얽히므로 custom 에서만 진행한다.
- Provider routing 추천 bundle 은 `enable-role-split-routing` 단일 entrypoint 로 역할 분리 preset 을 적용한다: `build-worker=headless-chain`, `impl-validator=codex`, `architecture-validator=codex`.
- 기존 활성 프로젝트가 추천 preset 만 소급 적용하려면 `dcness-helper routing enable-role-split-routing` 실행 뒤 `dcness-helper routing doctor` 로 PASS 를 확인한다.
- custom 지원 범위와 설정 순서는 [Provider Routing](#provider-routing)을 따른다.
- workflow 변경 PR 은 GitHub remote 가 있고, `gh auth status` 가 통과하고, 이번 `/init-dcness` run 이 쓴 `.github/workflows/*.yml` 변경이 있고, 현재 branch 가 `main` 이면 추천 ON. Y 선택 시 별도 질문 없이 해당 파일만 stage 해서 branch/commit/push/PR 을 진행한다. `gh` 미설치/미인증이면 자동 PR 은 skip 하고 custom/manual 안내만 남긴다. 기존 dirty workflow 파일은 자동 포함하지 않는다.

## Already Automatic

`/init-dcness` 가 whitelist 를 활성화하면 새 Claude Code 세션부터 [`hooks/hooks.json`](../../hooks/hooks.json) 의 CC hooks 가 자동 등록된다. 사용자가 따로 설치할 파일은 없다.

- `session-start.sh`: 세션 상태 초기화와 활성 안내.
- `catastrophic-gate.sh`: Agent 호출 전 작업 순서 보호.
- `file-guard.sh`: file/bash/MCP 경계와 외부 상태 변경 차단.
- `tdd-guard.sh`: generated project-local hook 이 있으면 그 hook 을 먼저 실행하고, 없으면 TS/JS 구현 파일 및 Bash write target 수정 직전 매칭 test 존재를 중앙 fallback 으로 확인한다. 상세 범위와 한계는 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 가 SSOT.
- `post-agent-clear.sh`, `post-file-op-trace.sh`, `subagent-stop-clear.sh`, `stop-end-run.sh`: run state 보존과 종료 처리.

과거 TDD 관련 CI/commit-msg 방식의 폐기 이력은 release note 기록이며, `/init-dcness` 실행 절차가 아니다. 현행 TDD Guard 계약은 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 와 `scripts/dcness-tdd-hooks` self-test 만 따른다.

## CI Workflow Snippets

이 섹션은 `/init-dcness` 가 사용자 repo 의 `.github/workflows/` 로 복사하는 workflow template inventory 를 제공한다. 검증 본체는 사용자 repo 에 복사하지 않고 dcNess composite action 을 호출한다.

### git-naming-validation.yml

- 대상 경로: `.github/workflows/git-naming-validation.yml`
- 템플릿: [`templates/github-workflows/git-naming-validation.yml`](../../templates/github-workflows/git-naming-validation.yml)
- 역할: `Daeguk-Sun/dcNess/.github/actions/git-naming@main` 을 호출해 `github.head_ref` 와 PR title 을 검증한다.

### pr-body-validation.yml

- 대상 경로: `.github/workflows/pr-body-validation.yml`
- 템플릿: [`templates/github-workflows/pr-body-validation.yml`](../../templates/github-workflows/pr-body-validation.yml)
- 역할: `Daeguk-Sun/dcNess/.github/actions/pr-body@main` 을 호출해 PR body 에 issue trailer 가 있는지 확인한다.

### doc-path-integrity.yml

- 대상 경로: `.github/workflows/doc-path-integrity.yml`
- 템플릿: [`templates/github-workflows/doc-path-integrity.yml`](../../templates/github-workflows/doc-path-integrity.yml)
- 역할: `Daeguk-Sun/dcNess/.github/actions/doc-path-integrity@main` 을 호출해 활성 프로젝트의 context/SSOT 문서(`CLAUDE.md`, `AGENTS.md`, root `architecture.md`, `docs/index.md`, `docs/project-context.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/modules/**`, `docs/decisions/**`) 안 repo-relative 경로 참조가 실제 파일 또는 디렉토리를 가리키는지 확인한다. 문서가 그대로여도 참조 대상 파일 삭제·이동으로 stale path 가 생길 수 있어 PR마다 실행한다.

### doc-sync.yml

- 대상 경로: `.github/workflows/doc-sync.yml`
- 템플릿: [`templates/github-workflows/doc-sync.yml`](../../templates/github-workflows/doc-sync.yml)
- 역할: `Daeguk-Sun/dcNess/.github/actions/doc-sync@main` 을 호출해 `docs/index.md` 의 epic/module 표가 파생 원본과 byte-level 로 일치하는지 확인하고, `/design` 산출물의 agent-first 핵심 섹션과 line budget 을 감사한다. `docs/index.md` 또는 유효 epic/module 이 없는 빈 환경은 no-op PASS 한다.

### github-project-lifecycle.yml

- 대상 경로: `.github/workflows/github-project-lifecycle.yml`
- 템플릿: [`templates/github-workflows/github-project-lifecycle.yml`](../../templates/github-workflows/github-project-lifecycle.yml)
- 역할: `Daeguk-Sun/dcNess/.github/actions/github-project-lifecycle@main` 을 호출해 issue/label drift 를 검출하고 merged PR 의 완료 후보 issue 에서 `in-progress` label 을 제거한다. Project 좌표가 설정된 repo 에서는 Project Status `Done` 미러를 best-effort 로 함께 시도한다.

`in-progress` label 제거에는 `issues: write` 권한이 필요하다. Project v2 미러에는 `secrets.DCNESS_PROJECT_TOKEN` 에 classic PAT `project` + `read:org` scope 가 필요하다. token 이 없거나 Project API 가 실패하면 Project 미러만 warning 으로 skip 되고 issue/label lifecycle 은 GitHub token 권한으로 계속 동작한다.

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

Project가 없거나 필드가 부족하면 생성 또는 복구 안내를 제공한다. lifecycle repo label 7종(`IssueType` 6종 + `in-progress`)이 부족하면 `--apply` 로 생성/갱신할 수 있다. 기존 Project field 의 option 이 부족한 경우는 GitHub CLI 제한 때문에 script 가 복구 안내를 내고 멈춘다. 다른 repo 에 적용할 때도 `--repo`, `--owner`, `--project` 값을 바꿔 같은 bootstrap 경로를 사용한다.

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
| 파일 경계 override 후보 재확인 | 아니오 | `/init-dcness` 와 `/impl` 시작 시 `dcness-helper boundary-suggestions` 가 read-only 로 다시 감지한다. |
| `.claude/harness-state/` gitignore 보강 | 예 | runtime state ignore 는 사용자 repo `.gitignore` append 라서 `/init-dcness` 재실행 때 적용된다. |
| `CLAUDE.md` seed/migration 로직 갱신 | 예 | 기존 활성 프로젝트의 root `CLAUDE.md` 생성·cold-start 앵커 append 는 `/init-dcness` 재실행 때 적용된다. |
| 선택형 `.github/workflows/*.yml` 갱신 | 예 | workflow 파일은 사용자 repo 에 배포된 사본이다. 기존 epic 또는 module docs 가 있는 프로젝트는 doc-sync 채택 직후 index 집계기를 1회 실행해야 한다. 전역 architecture 요약은 온디맨드다. |
| Provider routing preset/custom 변경 | 예 | 기존 활성 프로젝트도 plugin 공용 local data 를 갱신해야 한다. 추천 preset 은 `dcness-helper routing enable-role-split-routing` 뒤 `dcness-helper routing doctor` 로 적용·검증하고, custom은 [Provider Routing](#provider-routing)의 현행 값만 사용한다. Native Codex skill 등록/fallback 용 `$CODEX_HOME/skills` 도 최신화된다. |
| Project lifecycle 좌표 저장/변경 | 예 | repo variables 와 선택형 workflow 를 갱신해야 한다. |
| docs/design + docs/design-variants seed 추가 | 예 | 부재 파일 seed 는 사용자 repo 에 직접 생성된다. draft 는 `docs/design-variants/drafts/` 에 두고 `.gitignore` 로 무시하되 `drafts/.gitkeep` 으로 디렉터리를 보존한다. |
| TDD Guard 정책 갱신 | 아니오 | 중앙 fallback 과 self-test 본체는 plug-in update 로 갱신된다. project-local generated hook 이 없는 기존 프로젝트는 `/init-dcness` 또는 `/impl` 진입 시 생성 제안을 다시 받을 수 있다. |

## Auto PR Scope

`/init-dcness` 의 자동 commit + PR 단계는 `.github/workflows/*.yml` 만 대상으로 한다.

- 포함: `git-naming-validation.yml`, `pr-body-validation.yml`, `doc-path-integrity.yml`, `doc-sync.yml`, `github-project-lifecycle.yml`
- 제외: `.git/hooks/*` (git 내부 파일), generated TDD hook bootstrap(`.dcness/tdd-hooks.json`, `.claude/**`, `.codex/**` — 자동 workflow PR 제외. linked worktree/headless 재사용이 필요하면 별도 bootstrap commit 대상), `~/.claude/**`, `$CODEX_HOME/**`, `.gitignore` runtime/volatile ignore, `docs/*` seed, `docs/design-variants/*` seed, 자동 CC hook 설명
- 선행 조건: GitHub remote 존재, 현재 branch `main`, `gh auth status` 통과. 조건이 안 맞으면 branch/commit/push 를 시작하지 않고 skip 안내만 출력한다.

seed 문서는 사용자 프로젝트 내용물이므로 사용자가 별도 작업 PR 에 포함할지 직접 판단한다.

## Deactivation

비활성화는 별도 command 가 아니라 `/init-dcness` 스킬이 겸한다("dcness 꺼줘" 류 발화). 실행 절차와 잔존물 정리 목록은 [`commands/init-dcness.md`](../../commands/init-dcness.md#비활성화) 의 비활성화 섹션이 runbook 진본이다.

- `dcness-helper disable` 은 whitelist 에서 현재 main repo 항목만 제거한다. plug-in 중앙 hook 은 매 호출 `is-active` 판정이므로 즉시 pass-through 된다 (`DCNESS_FORCE_ENABLE=1` 프로세스 제외).
- project-local 설치물(CLAUDE.md 의 dcNess 안내, git hook shim 4종, generated TDD hook, CI workflow 템플릿)은 whitelist 와 무관하게 잔존한다. 완전 제거는 runbook 의 dcNess 소유물 한정 항목별 정리를 따른다.

## References

- [`hooks.md`](hooks.md) - CC hook / git hook / CI layer policy
- [`git-spec.md`](git-spec.md) - branch / commit / PR naming
- [`github-project.md`](github-project.md) - Project v2 fields and bootstrap
- [`issue-lifecycle.md`](issue-lifecycle.md) - issue hierarchy, label lifecycle, optional Project mirror
- [`design.md`](design.md) - `docs/design.md` format
- [`hooks/hooks.json`](../../hooks/hooks.json) - CC hook registration
