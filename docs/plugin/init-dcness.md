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
| generated TDD hook 제안/생성 | `.dcness/tdd-hooks.json`, `.claude/settings.json`, `.claude/hooks/dcness-tdd-guard.sh`, `.codex/hooks.json`, `.codex/hooks/dcness-tdd-guard.sh` | `scripts/dcness-tdd-hooks` | 사용자에게 확인한 플랫폼 또는 사람 승인된 project-local 계약 + 사용자 승인 시 | self-test 통과 후보만 등록. CC 검증 후 Codex 생성 | X |
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
| doc sync workflow | `.github/workflows/doc-sync.yml` | [`templates/github-workflows/doc-sync.yml`](../../templates/github-workflows/doc-sync.yml) | GitHub remote 감지 시 추천 ON (중립 명명 설치에서는 제외) | always-overwrite | O |
| lint-build-test workflow | `.github/workflows/lint-build-test.yml` | [`templates/github-workflows/lint-build-test/android.yml`](../../templates/github-workflows/lint-build-test/android.yml) (플랫폼별 template) | GitHub remote 감지 + 플랫폼 template 존재 시 추천 ON | always-overwrite | O |
| Project lifecycle workflow | `.github/workflows/github-project-lifecycle.yml` | [`templates/github-workflows/github-project-lifecycle.yml`](../../templates/github-workflows/github-project-lifecycle.yml) | custom 선택 (중립 명명 설치에서는 제외) | always-overwrite | O |
| CI 검사 스크립트 사본 | `.github/ci-checks/**` | 설치한 workflow 가 실행하는 plugin script (`scripts/**`, doc-sync 는 `harness/story_runner.py`·`harness/parallel_wave.py`·design 엔진 원본 `templates/design-variants/_lib/*.js` 포함) — [`harness/ci_workflows.py`](../../harness/ci_workflows.py) 가 목록 소유 | 해당 workflow 설치 시 | always-overwrite. 설치 시점 plugin 버전에 고정 | O |
| project docs seed | `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` | authoring 템플릿 (`skills/spec/templates/index.md`, `skills/spec/templates/prd.md`, `docs/plugin/agents/system-architect/templates/root-architecture.md`, `docs/plugin/agents/system-architect/templates/conventions.md`) + `scripts/ensure_docs_index_next_section.mjs` — 시드와 산출 양식 단일 원본. 위치 SSOT [`deliverables-map.md`](deliverables-map.md) | 추천 bundle 또는 custom | 부재 시 생성. 기존 `docs/index.md` 는 진행 상태 섹션만 없을 때 append | X |
| volatile workdir ignore | `.gitignore` 의 `.dcness-work/` + `.claude/harness-state/` 재확인 | `/init-dcness` append | 추천 bundle 또는 custom | 없을 때만 추가 | X |
| design seed | `docs/design.md` | `docs/plugin/design.md` minimal 예시 | custom 선택 | 부재 시만 생성 | X |
| design preview seed | `docs/design-variants/**` | `templates/design-variants/**` | custom 선택 | 부재 시만 생성 | X |
| Role-split provider routing preset | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing enable-role-split-routing` | 추천 bundle | `build-worker=headless-chain`, `impl-validator=codex`, `architecture-validator=codex` | X |
| Validation routing custom | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing enable-codex-validation` / `disable-codex-validation` | custom | all-codex validation 또는 Claude validation 복귀 | X |
| Implementation routing custom | `~/.claude/plugins/data/dcness-dcness/routing.json` | `dcness-helper routing enable-headless-implementation` / `enable-claude-headless-implementation` / `set-implementation build-worker claude` | custom | `headless-chain`, `claude-headless`, `claude` 가능 | X |
| Project coordinates | repo variables `DCNESS_PROJECT_NUMBER`, `DCNESS_PROJECT_OWNER` | `gh variable set` | Project bootstrap 선택 | 값 갱신 | X |

> 🔴 **진단 동기화 의무**: 위 inventory 에 새 복사/배포 대상(git hook · CI workflow · 권한 등)을 추가하면, `dcness-helper status` 진단표(`harness/session_state.py` 의 `collect_status_diagnostics`)에도 해당 검사 항목을 함께 추가한다. 그렇지 않으면 사용자가 설치 누락을 한눈에 확인할 수 없다.

design preview 후보는 `docs/design-variants/drafts/`, 확정본은 `screens/`, 파생 보드는
`boards/`에 둔다. 상세 계약은 [`design-variants.md`](design-variants.md)가 소유한다.

`dcness-helper status` 는 설치 상태뿐 아니라 최근 hook fail-open 활동도 `hook fail-open 진단` 항목으로 보여준다. 정상 inactive no-op 은 기록하지 않고, 활성 프로젝트에서 enforcement hook 이 검사를 평가하지 못하고 allow 한 경우만 최근 reason category 를 WARN 으로 노출한다. 자세한 정책은 [`hooks.md`](hooks.md) 가 SSOT 다.

`CLAUDE.md` seed/migration 은 사용자 repo 에 복사하지 않는 plugin script (`$PLUGIN_ROOT/scripts/dcness-context-docs`) 로 처리한다. 부재 시 Anthropic 공식 구조 기반 템플릿을 만들고, 기존 파일은 cold-start 앵커만 additive append 한다. 6축 quality audit 결과는 출력하지만 구조 개선·삭제·재배치는 후보만 제안한다.

파일 경계 override 제안은 `dcness-helper boundary-suggestions` 로 처리한다. 코어 `ALLOW_MATRIX` 가 커버하지 않는 비표준 소스 디렉터리가 있을 때만 `.dcness/boundary.json` 의 implementation add 후보를 출력하며, 표준 레이아웃·빈 프로젝트·이미 override 로 커버된 프로젝트는 no-op 이다. 이 helper 는 read-only 이므로 실제 boundary 파일 작성은 사람 승인 뒤 메인이 수행한다.

Generated TDD hook 은 `scripts/dcness-tdd-hooks` 로 처리한다. dcNess 소유 영역은 **TDD 계약**과 **self-test** 이며, self-test fixture 는 `무-test 구현 파일 → deny`, `매칭 test 있음 → allow`, `test 파일 자체 → allow` 를 검증한다. helper 는 `python`, `web`, `go`, `android`, `ios` 프리셋으로 기본 project-local config 를 만들 수 있고, 프리셋 미지원 플랫폼은 사람 승인된 `.dcness/tdd-hooks.json` 계약을 우선 사용한다. helper 는 파일 구성으로 플랫폼을 추측하지 않는다. 계약이 없으면 `/init-dcness` 가 사용자에게 플랫폼을 물어 확인한 프리셋 이름을 `ensure --platform <값>` 으로 넘긴다. 기존 계약의 `platform` 과 다른 값을 넘기면 계약을 덮어쓰지 않고 실패한다. 모든 계약은 `source_roots`, `impl_exts` 가 필요하고, custom 플랫폼은 `test_candidate_templates` 도 필요하다. 선택 `test_file_globs` 로 test 파일 자체 allow 규칙을 보강한다. `/init-dcness` 에서 생성할 때는 CC hook 후보를 먼저 self-test 하고 통과해야 `.claude/settings.json` 에 등록한다. 그 다음 Codex hook 후보를 같은 계약으로 self-test 하고 `.codex/hooks.json` 에 등록한다. 빈 프로젝트·계약과 `--platform` 이 모두 없는 호출·생성 실패는 no-op 으로 안전 통과한다.

생성 파일(`.dcness/tdd-hooks.json`, `.claude/settings.json`, `.claude/hooks/dcness-tdd-guard.sh`, `.codex/hooks.json`, `.codex/hooks/dcness-tdd-guard.sh`)은 자동 workflow PR 에 섞지 않는다. linked worktree 나 headless worker 체크아웃에서 project-local hook 을 재사용하려면 이 파일들이 Git 에 커밋돼 있어야 하며, 없으면 중앙 fallback 으로 내려간다. `scripts/dcness-tdd-hooks status` 와 `ensure` 는 linked worktree 에서 커밋이 필요한 경우 `commit-required`, in-place 에서만 실존하는 경우 `commit-advisory` 를 출력한다. 이 설치 health는 `/init-dcness`/`status`가 소유하며 일반 구현 착수 앞에서 반복하지 않는다.

`docs/index.md` 의 epic/module 표와 기존 `docs/index.md` 의 진행 상태 섹션 보강은 사용자 repo 에 복사하지 않는 plugin script (`$PLUGIN_ROOT/scripts/aggregate_index_map.mjs`, `$PLUGIN_ROOT/scripts/ensure_docs_index_next_section.mjs`) 로 처리한다. 전역 architecture 인간용 요약은 필요할 때 `$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs` 로 `.dcness-work/reports/architecture-map.md` 에 온디맨드 생성한다. `/design` 산출물 구조 감사와 design-variants 생성기 3종도 plugin script (`$PLUGIN_ROOT/scripts/check_design_artifact_structure.mjs`, `$PLUGIN_ROOT/scripts/design/`) 로 처리한다. 활성 프로젝트 작업 중에는 이 스크립트를 현재 프로젝트 루트에서 실행한다. 단 `doc-sync.yml` 을 설치하면 PR CI 가 쓸 사본이 `.github/ci-checks/` 로 함께 복사된다 ([CI Workflow Snippets](#ci-workflow-snippets)).

제품 journey runner도 사용자 repo에 복사하지 않는 plugin script (`$PLUGIN_ROOT/scripts/dcness-product-journey`)로 제공한다. project-local 계약은 owner module/소스 영역의 opt-in 매니페스트이며 `/init-dcness`가 자동 생성하거나 덮어쓰지 않는다. UI journey도 같은 계약과 helper를 재사용하고 project-owned command가 단계별 화면 증거를 생성한다. 실행 receipt와 log는 기존 ignored `.dcness-work/product-journey/`에 남고 [`outcome-scorecard.md`](outcome-scorecard.md)가 집계한다. 계약과 판정 경계는 [`product-journey.md`](product-journey.md)가 소유한다.

## Provider Routing

provider config는 프로젝트별 파일이 아니라 plugin 공용 `~/.claude/plugins/data/dcness-dcness/routing.json` 하나다. 지원 형식은 schema v3의 `routes`와 `implementation_routes`이며, validation agent는 `impl-validator`·`architecture-validator`, implementation agent는 `build-worker`만 지원한다.

- 추천 role split은 `routing enable-role-split-routing`으로 `build-worker=headless-chain`, `impl-validator=codex`, `architecture-validator=codex`를 함께 기록한다.
- validation custom은 `routing enable-codex-validation`, `routing disable-codex-validation` 또는 `routing set <agent> claude|codex`를 사용한다.
- implementation custom은 `routing enable-headless-implementation`, `routing enable-claude-headless-implementation` 또는 `routing set-implementation build-worker claude|claude-headless|headless-chain`을 사용한다. Claude-only는 `routing set-implementation build-worker claude`다.
- schema v3만 지원한다. `routing doctor`가 version 오류로 실패하는 config는 삭제하고 `routing enable-role-split-routing`으로 현행 파일을 새로 만든 뒤 필요한 custom override를 적용한다.

config 형식 검증과 runtime provider fallback은 다른 계약이다. `headless-chain`은 provider가 workspace를 바꾸기 전에 실패했을 때만 다음 provider로 진행한다. 변경 뒤 recoverable timeout/empty output/guard failure는 같은 provider·같은 workspace에서 bounded continuation하고, 복구 불가 또는 한도 소진이면 diff를 보존해 중단한다.

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
- 같은 조건에서 프로젝트 플랫폼에 lint-build-test template 이 있으면 `lint-build-test.yml` 추천 ON. 결정 규칙은 [lint-build-test.yml](#lint-build-testyml) 을 따른다.
- 중립 명명 설치는 기본 OFF 다. custom 에서 켠다.
- 루트 `architecture.md` 가 있고 `docs/architecture.md` 가 없으면 `docs/architecture.md` 는 추천 OFF. 메시지에 `root architecture.md 감지로 docs/architecture.md skip` 을 남긴다.
- `docs/index.md`, `docs/prd.md`, `docs/conventions.md`, `docs/decisions/` 는 부재 시 추천 ON. 기존 `docs/index.md` 에 진행 상태 섹션이 없으면 보강 ON.
- 루트 `architecture.md` 가 없고 `docs/architecture.md` 도 없으면 `docs/architecture.md` 추천 ON.
- `.gitignore` 에 `.dcness-work/` 가 없으면 추천 ON. `.claude/harness-state/` 는 core activation 에서 항상 보장한다.
- `docs/design-variants/` 는 기본 skip. 단일 `app/page.tsx` 정도의 UI 흔적만으로 design kit 를 설치하지 않는다.
- GitHub Project lifecycle 은 기본 skip. `gh` 인증, Project number, PAT/secrets, field/label 복구가 얽히므로 custom 에서만 진행한다.
- Provider routing 추천 bundle 은 `enable-role-split-routing` 단일 entrypoint 로 역할 분리 preset 을 적용한다: `build-worker=headless-chain`, `impl-validator=codex`, `architecture-validator=codex`.
- 기존 활성 프로젝트가 추천 preset 만 소급 적용하려면 `dcness-helper routing enable-role-split-routing` 실행 뒤 `dcness-helper routing doctor` 로 PASS 를 확인한다.
- custom 지원 범위와 설정 순서는 [Provider Routing](#provider-routing)을 따른다.
- workflow 변경 PR 은 GitHub remote 가 있고, `gh auth status` 가 통과하고, 이번 `/init-dcness` run 이 쓴 `.github/workflows/*.yml` 또는 `.github/ci-checks/**` 변경이 있고, 현재 branch 가 `main` 이면 추천 ON. Y 선택 시 별도 질문 없이 해당 파일만 stage 해서 branch/commit/push/PR 을 진행한다. `gh` 미설치/미인증이면 자동 PR 은 skip 하고 custom/manual 안내만 남긴다. 기존 dirty workflow 파일은 자동 포함하지 않는다.

## Already Automatic

`/init-dcness` 가 whitelist 를 활성화하면 새 Claude Code 세션부터 [`hooks/hooks.json`](../../hooks/hooks.json) 의 CC hooks 가 자동 등록된다. 사용자가 따로 설치할 파일은 없다.

- `session-start.sh`: 세션 상태 초기화와 활성 안내.
- `catastrophic-gate.sh`: Agent 호출 전 작업 순서 보호.
- `file-guard.sh`: file/bash/MCP 경계와 외부 상태 변경 차단.
- `tdd-guard.sh`: generated project-local hook 이 있으면 그 hook 을 먼저 실행하고, 없으면 TS/JS 구현 파일 및 Bash write target 수정 직전 매칭 test 존재를 중앙 fallback 으로 확인한다. 상세 범위와 한계는 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 가 SSOT.
- `post-agent-clear.sh`, `subagent-stop-clear.sh`, `stop-end-run.sh`: run state 보존과 종료 처리.

과거 TDD 관련 CI/commit-msg 방식의 폐기 이력은 release note 기록이며, `/init-dcness` 실행 절차가 아니다. 현행 TDD Guard 계약은 [`hooks.md#tdd-guardsh`](hooks.md#tdd-guardsh) 와 `scripts/dcness-tdd-hooks` self-test 만 따른다.

## CI Workflow Snippets

이 섹션은 `/init-dcness` 가 사용자 repo 에 설치하는 workflow template inventory 를 제공한다. 설치는 `scripts/dcness-ci-workflows install` 이 담당하며, workflow 를 `.github/workflows/` 로 복사하면서 그 workflow 가 실행하는 검사 스크립트도 plugin 안의 상대 경로 그대로 `.github/ci-checks/` 아래에 복사한다.

- **자기 저장소만으로 실행**: 설치된 workflow 는 외부 저장소 action 이나 스크립트를 참조하지 않는다. `uses:` 는 GitHub 공식 `actions/*`(checkout, setup-node, setup-python, setup-java)만 쓰고, 검사는 체크아웃한 `.github/ci-checks/` 사본을 실행한다. 따라서 plugin 저장소의 변경이 사용자 PR 검사 결과를 사용자 모르게 바꾸지 않는다.
- **버전 고정과 갱신 경로**: 사본은 설치 시점의 plugin 버전에 고정된다. 규칙 갱신은 plugin 업데이트 뒤 `/init-dcness` 를 재실행해 사용자가 선택해 반영하며, 재실행은 workflow 와 사본을 always-overwrite 한다. 설치기가 쓴 파일만 workflow PR 에 stage 된다.
- **구버전 이전**: 이전 버전은 workflow 가 `Daeguk-Sun/dcNess/.github/actions/<name>@main` 을 원격 호출했다. 이런 workflow 가 남아 있으면 `dcness-helper status` 의 `선택형 CI workflow` 행이 WARN 으로 알려 주고, `/init-dcness` 재실행이 복사 방식으로 덮어쓴다.
- **중립 명명 설치**: `--neutral-naming` 을 켜면 설치 산출물의 경로·파일명·workflow 이름·job 이름·본문에 하네스 이름이 나오지 않는다. 하네스를 비공개로 두고 공개 저장소에 산출물만 올리는 프로젝트용이다. `doc-sync.yml` 과 `github-project-lifecycle.yml` 은 하네스 산출물 형식(생성 구역 표식, 설정 변수 이름)을 직접 검사하므로 이 설치에서 제외되고 건너뛴 이유가 출력된다.

### git-naming-validation.yml

- 대상 경로: `.github/workflows/git-naming-validation.yml`
- 템플릿: [`templates/github-workflows/git-naming-validation.yml`](../../templates/github-workflows/git-naming-validation.yml)
- 복사 스크립트: `scripts/check_git_naming.mjs`
- 역할: 복사된 `check_git_naming.mjs` 로 `github.head_ref` 와 PR title 을 검증한다.

### pr-body-validation.yml

- 대상 경로: `.github/workflows/pr-body-validation.yml`
- 템플릿: [`templates/github-workflows/pr-body-validation.yml`](../../templates/github-workflows/pr-body-validation.yml)
- 복사 스크립트: `scripts/check_pr_body.mjs`
- 역할: 복사된 `check_pr_body.mjs` 로 PR body 에 issue trailer 가 있는지 확인한다.

### doc-path-integrity.yml

- 대상 경로: `.github/workflows/doc-path-integrity.yml`
- 템플릿: [`templates/github-workflows/doc-path-integrity.yml`](../../templates/github-workflows/doc-path-integrity.yml)
- 복사 스크립트: `scripts/check_doc_path_integrity.mjs`
- 역할: 복사된 `check_doc_path_integrity.mjs` 로 활성 프로젝트의 context/SSOT 문서(`CLAUDE.md`, `AGENTS.md`, root `architecture.md`, `docs/index.md`, `docs/project-context.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/modules/**`, `docs/decisions/**`) 안 repo-relative 경로 참조가 실제 파일 또는 디렉토리를 가리키는지 확인한다. 문서가 그대로여도 참조 대상 파일 삭제·이동으로 stale path 가 생길 수 있어 PR마다 실행한다.

### doc-sync.yml

- 대상 경로: `.github/workflows/doc-sync.yml`
- 템플릿: [`templates/github-workflows/doc-sync.yml`](../../templates/github-workflows/doc-sync.yml)
- 복사 스크립트: `scripts/aggregate_index_map.mjs`, `scripts/lib/epic_phase.mjs`, `scripts/check_design_artifact_structure.mjs`, `scripts/dcness-story-runner`, `harness/story_runner.py`, `harness/parallel_wave.py`, `scripts/design/*.mjs`, 그리고 design 생성기가 프로젝트 엔진 사본과 비교하려고 읽는 원본 `templates/design-variants/_lib/*.js`. 복사본이 plugin 원본 경로를 런타임에 읽지 않도록 의존 파일 전체를 함께 복사하며, `tests/test_ci_workflows_install.py` 가 이 의존 닫힘을 검사한다.
- 역할: 복사된 사본으로 `docs/index.md` 의 epic/module 표가 파생 원본과 byte-level 로 일치하는지 확인하고, `/design` 산출물의 agent-first 핵심 섹션·line budget·impl story/의존 순서를 감사한다. story/의존 순서 판정은 복사된 story runner 를 Python 3.11 로 실행한다. `docs/index.md` 또는 유효 epic/module 이 없는 빈 환경은 no-op PASS 한다. 중립 명명 설치에서는 제외된다.

### lint-build-test.yml

- 대상 경로: `.github/workflows/lint-build-test.yml`
- 템플릿: 프로젝트 플랫폼의 `templates/github-workflows/lint-build-test/<platform>.yml`. 현재 [`android.yml`](../../templates/github-workflows/lint-build-test/android.yml) 만 있다.
- 복사 스크립트: 없음. 사용자 repo 의 빌드 도구만 실행하며 하네스 이름이 들어가지 않아 중립 명명 설치에도 그대로 포함된다.
- 역할: `main` 대상 `pull_request` 에서 lint → 빌드 → 단위 테스트를 순서대로 실행하고, 하나라도 실패하면 PR 검사가 실패한다. Android 기본 명령은 `./gradlew :app:lintDebug`, `./gradlew :app:assembleDebug`, `./gradlew :app:testDebugUnitTest` 이며 `actions/setup-java`(temurin 17, Gradle cache)로 JDK 와 Gradle 캐시를 준비한다.
- 플랫폼 결정 규칙: `--platform` 명시값 → TDD 계약(`.dcness/tdd-hooks.json`)의 `platform` 순서로 정한다. 파일 구성으로 추측하지 않는다. 계약이 없으면 `/init-dcness` 가 사용자에게 확인한 값을 `--platform` 으로 넘긴다.
- skip 동작: 플랫폼이 지정되지 않았거나, 그 플랫폼 template 이 없거나, Android 인데 `gradlew` 또는 `app/build.gradle(.kts)` 가 없으면 파일을 쓰지 않고 `skip lint-build-test: <이유>` 를 출력한다.
- 수정: 명령은 설치 후 프로젝트 모듈 구성에 맞게 고쳐도 된다. 재실행은 template 으로 덮어쓰므로 명령을 고친 프로젝트는 재실행 때 이 workflow 를 선택에서 뺀다.

### github-project-lifecycle.yml

- 대상 경로: `.github/workflows/github-project-lifecycle.yml`
- 템플릿: [`templates/github-workflows/github-project-lifecycle.yml`](../../templates/github-workflows/github-project-lifecycle.yml)
- 복사 스크립트: `scripts/github_project_lifecycle.mjs`, `scripts/check_issue_body.mjs`, `scripts/lib/epic_phase.mjs`
- 역할: 복사된 `github_project_lifecycle.mjs` 로 issue/label drift 를 검출하고 merged PR 의 완료 후보 issue 에서 `in-progress` label 을 제거한다. Project 좌표가 설정된 repo 에서는 Project Status `Done` 미러를 best-effort 로 함께 시도한다.

`in-progress` label 제거에는 `issues: write` 권한이 필요하다. Project v2 미러에는 `secrets.DCNESS_PROJECT_TOKEN` 에 classic PAT `project` + `read:org` scope 가 필요하다. token 이 없거나 Project API 가 실패하면 Project 미러만 warning 으로 skip 되고 issue/label lifecycle 은 GitHub token 권한으로 계속 동작한다. token 이 전달됐지만 GitHub 이 거부하면(만료·폐기 → HTTP 401) issue/label lifecycle 정리까지 건너뛰지만, workflow 는 건너뛴 대상과 이유를 warning 으로 남기고 성공으로 끝난다.

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
| 파일 경계 override 후보 재확인 | 아니오 | `/init-dcness` 설정/진단 시 `dcness-helper boundary-suggestions` 로 read-only 재감지한다. 일반 구현 착수에는 선행하지 않는다. |
| `.claude/harness-state/` gitignore 보강 | 예 | runtime state ignore 는 사용자 repo `.gitignore` append 라서 `/init-dcness` 재실행 때 적용된다. |
| `CLAUDE.md` seed/migration 로직 갱신 | 예 | 기존 활성 프로젝트의 root `CLAUDE.md` 생성·cold-start 앵커 append 는 `/init-dcness` 재실행 때 적용된다. |
| 선택형 `.github/workflows/*.yml` 또는 검사 스크립트 갱신 | 예 | workflow 와 `.github/ci-checks/` 검사 스크립트는 사용자 repo 에 배포된 사본이라 plugin update 만으로 바뀌지 않는다. 원격 호출 구버전 workflow 도 재실행으로 복사 방식에 옮겨 간다. 기존 epic 또는 module docs 가 있는 프로젝트는 doc-sync 채택 직후 index 집계기를 1회 실행해야 한다. 전역 architecture 요약은 온디맨드다. |
| Provider routing preset/custom 변경 | 예 | 기존 활성 프로젝트도 plugin 공용 local data 를 갱신해야 한다. 추천 preset 은 `dcness-helper routing enable-role-split-routing` 뒤 `dcness-helper routing doctor` 로 적용·검증하고, custom은 [Provider Routing](#provider-routing)의 현행 값만 사용한다. Native Codex skill 등록/fallback 용 `$CODEX_HOME/skills` 도 최신화된다. |
| Project lifecycle 좌표 저장/변경 | 예 | repo variables 와 선택형 workflow 를 갱신해야 한다. |
| docs/design + docs/design-variants seed 추가 | 예 | 부재한 엔진 4파일·빈 변형 전수 보드·ignore만 사용자 repo에 생성된다. 저니 보드와 두 진입점은 프로젝트 진본에서 생성한다. |
| TDD Guard 정책 갱신 | 아니오 | 중앙 fallback 과 self-test 본체는 plug-in update 로 갱신된다. project-local generated hook 설치 제안은 `/init-dcness`/`status`가 소유한다. |

## Auto PR Scope

`/init-dcness` 의 자동 commit + PR 단계는 이번 run 이 쓴 `.github/workflows/*.yml` 과 `.github/ci-checks/**` 검사 스크립트만 대상으로 한다.

- 포함: `git-naming-validation.yml`, `pr-body-validation.yml`, `doc-path-integrity.yml`, `doc-sync.yml`, `lint-build-test.yml`, `github-project-lifecycle.yml`, 그리고 이 workflow 들이 실행하는 `.github/ci-checks/**` 사본
- 제외: `.git/hooks/*` (git 내부 파일), generated TDD hook bootstrap(`.dcness/tdd-hooks.json`, `.claude/**`, `.codex/**` — 자동 workflow PR 제외. linked worktree/headless 재사용이 필요하면 별도 bootstrap commit 대상), `~/.claude/**`, `$CODEX_HOME/**`, `.gitignore` runtime/volatile ignore, `docs/*` seed, `docs/design-variants/*` seed, 자동 CC hook 설명
- 선행 조건: GitHub remote 존재, 현재 branch `main`, `gh auth status` 통과. 조건이 안 맞으면 branch/commit/push 를 시작하지 않고 skip 안내만 출력한다.

seed 문서는 사용자 프로젝트 내용물이므로 사용자가 별도 작업 PR 에 포함할지 직접 판단한다.

## Deactivation

비활성화는 별도 command 가 아니라 `/init-dcness` 스킬이 겸한다("dcness 꺼줘" 류 발화). 실행 절차와 잔존물 정리 목록은 [`commands/init-dcness.md`](../../commands/init-dcness.md#비활성화) 의 비활성화 섹션이 runbook 진본이다.

- `dcness-helper disable` 은 whitelist 에서 현재 main repo 항목만 제거한다. plug-in 중앙 hook 은 매 호출 `is-active` 판정이므로 즉시 pass-through 된다 (`DCNESS_FORCE_ENABLE=1` 프로세스 제외).
- project-local 설치물(CLAUDE.md 의 dcNess 안내, git hook shim 4종, generated TDD hook, CI workflow 템플릿과 `.github/ci-checks/` 검사 스크립트 사본)은 whitelist 와 무관하게 잔존한다. 완전 제거는 runbook 의 dcNess 소유물 한정 항목별 정리를 따른다.

## References

- [`hooks.md`](hooks.md) - CC hook / git hook / CI layer policy
- [`git-spec.md`](git-spec.md) - branch / commit / PR naming
- [`github-project.md`](github-project.md) - Project v2 fields and bootstrap
- [`issue-lifecycle.md`](issue-lifecycle.md) - issue hierarchy, label lifecycle, optional Project mirror
- [`design.md`](design.md) - `docs/design.md` format
- [`hooks/hooks.json`](../../hooks/hooks.json) - CC hook registration
