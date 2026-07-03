# 산출물 지도 (Deliverables Map)

> dcNess 활성 프로젝트의 `docs/` 산출물 위치, 생성 주체, 양식, 입력 경계의 SSOT.
> 기준은 사람이 훑기 편한 목차가 아니라, **cold-start stateless agent 가 같은 문서를 읽고 같은 맥락으로 시작하는 것**이다.

## 북극성

- 전역 사실은 전역 anchor 한 곳에 둔다. 같은 결정이 여러 epic 문서에 복제되어 drift 되는 구조를 만들지 않는다.
- role 입력은 결정론적인 최소 세트다. 각 agent 는 자기 역할에 필요한 전역 최소 문서와 대상 epic 고정 문서만 읽는다.
- downstream agent 가 읽어야 하는 산출물은 git-tracked 문서다. 실측 evidence, HTML report, handoff scratch 처럼 재현 가능한 임시물은 `.dcness-work/` 에 둔다.
- 새 프로젝트 산출물은 `docs/epics/`, `docs/modules/`, `docs/decisions/`, `docs/compact-plans/`, `docs/metrics/` 아래로만 증식한다. `docs/modules/` 는 모노레포·모듈화 프로젝트에서만 쓰는 opt-in 축이며, milestone 은 경로가 아니라 epic frontmatter 의 `milestone: vNN` 값이다.

## 문서 총량 예산

목표는 모든 문서를 항상 prompt 에 넣는 것이 아니라, cold session 이 진입점부터 필요한 진본을 짧은 탐색으로 복구하고 필요 시 핵심 설계 pack 을 전문 주입할 수 있게 유지하는 것이다.

| 범위 | 예산 | 근거 | 초과 시 조치 |
|---|---|---|---|
| normal epic full design pack (`stories.md` + `architecture.md` + 선택 `domain-model.md` + 선택 `ux-flow.md` + `impl/NN-*.md`) | target 1,500 lines | finsight 경량 하네스 실측 759줄이 단일 컨텍스트 설계에 충분했고, dcNess impl task 평균 40-60줄 기준 15-20 task까지 전문 주입 가능 | 중복 계약/결정 사본 제거, impl task 병합/분리 재검토, detail 을 `.dcness-work/` 로 내림 |
| hard warning full design pack | 2,000 lines | 2,000줄을 넘으면 cold session 전문 흡수보다 포인터 탐색 비용이 커지기 시작한다 | module-architect 보고에 warning, PR body 에 초과 사유와 후속 축소 계획 기록 |
| single task implementation pack (`docs/index.md` + 전역 최소 입력 + epic 고정 입력 + 대상 impl 1개) | target 900 lines | `/impl-loop` task 단위 cold-start 가 읽는 실제 입력 세트 | 대상 task 에 필요 없는 전문 사본 제거 |
| module scoped pack (`docs/modules/<module-id>/architecture.md` + `conventions.md`) | target 300 lines per module | 모듈 작업 cold-start 가 무관한 스택·빌드·규약을 읽지 않게 하기 위한 상한 | 전역과 중복되는 규칙 제거, module-local delta 만 남김 |

예산은 신규 산출물의 작성 압력이다. 기존 활성 프로젝트의 구양식 산출물은 계속 유효하지만, 수정하는 순간 신규 규칙에 맞춰 전문 사본을 줄인다.

## 적용 범위

- 본 지도는 `/init-dcness` 로 활성화한 외부 프로젝트의 산출물 구조에 적용된다.
- dcNess 저장소 자기 자신은 `docs/plugin/**`, `docs/internal/**`, `docs/archive/**` 운영 문서 체계를 별도로 쓴다.

## 전체 구조

```text
docs/
├── index.md                         # 프로젝트 문서 entrypoint
├── prd.md                           # 제품 요구사항
├── architecture.md                  # append-growing 전역 architecture map
├── conventions.md                   # 기술 스택, naming, tooling, style 결정
├── tech-review.md                   # 전역 기술 검토 결론
├── design.md                        # 선택: 전역 design token / system-level UX 결정
├── metrics/
│   └── design-runs.jsonl            # design run durable record index
├── decisions/
│   └── NNNN-slug.md                 # 전역 결정 기록
├── modules/                         # 선택: 모듈 스코프 docs
│   └── <module-id>/
│       ├── architecture.md          # 모듈 국소 architecture / boundary
│       ├── conventions.md           # 모듈 특수 stack/tooling/style delta
│       └── tech-review.md           # 선택: 모듈 한정 기술 검토 결론
├── compact-plans/
│   └── <slug>.md                    # 경량 구현 설계
└── epics/
    └── epic-NN-<slug>/
        ├── stories.md               # epic/story 요구사항
        ├── ux-flow.md               # 선택: epic 화면 흐름
        ├── architecture.md          # epic 국소 architecture
        ├── domain-model.md          # 선택: epic 국소 domain model
        ├── tech-review.md           # 선택: design 중 새 의존 option 4 검토 결론
        └── impl/
            └── NN-*.md              # 구현 task

.dcness-work/
├── spikes/
├── research/
├── open-questions/
├── handoffs/
└── reviews/                         # HTML report, raw evidence, screenshots, logs
```

## 전역 산출물

| 산출물 | 경로 | 생성 주체 | 양식 |
|---|---|---|---|
| 문서 entrypoint | `docs/index.md` | `/init-dcness`, `/spec`, `scripts/aggregate_index_map.mjs` | `skills/spec/templates/index.md` |
| PRD | `docs/prd.md` | `/spec` | `skills/spec/templates/prd.md` |
| 전역 architecture map | `docs/architecture.md` | system-architect | `agents/system-architect/templates/root-architecture.md` |
| convention map | `docs/conventions.md` | `/init-dcness`, system-architect | `agents/system-architect/templates/conventions.md` |
| 기술 검토 결론 | `docs/tech-review.md` | tech-reviewer | `agents/tech-reviewer/templates/tech-review.md` |
| 전역 design token | `docs/design.md` | ux-architect | `docs/plugin/design.md` |
| design run 기록 | `docs/metrics/design-runs.jsonl` | `dcness-helper end-run` before design PR | JSONL schema v1 (`harness/design_run_records.py`) |
| 결정 기록 | `docs/decisions/NNNN-slug.md` | system-architect / module-architect | `agents/system-architect/templates/decision.md` |

`docs/architecture.md` 는 epic 이 늘 때마다 append-growing map 으로 갱신한다. 상세 설계 본문을 전역에 복제하지 않고, 전역 모듈/의존/결정 anchor 와 epic 문서 링크를 추가한다.

`docs/index.md` 는 cold-start agent 의 정적 entrypoint 다. `## 에픽` 표는 `docs/epics/epic-NN-*` 디렉토리와 `stories.md` frontmatter `milestone` 값에서 파생되는 생성 섹션이며 수동 편집하지 않는다. 모듈 축을 쓰는 프로젝트에서는 `## 모듈` 표도 `docs/modules/<module-id>/` 에서 파생된다. live 진행상태를 문서에 복제하지 않고, 수동 섹션 `## 진행 상태 · 다음 작업` 에서 GitHub issue/label 상태, epic/story issue, `/next-work` 를 가리킨다. `/init-dcness` 는 기존 `docs/index.md` 를 overwrite 하지 않지만, 이 섹션이 없으면 `$PLUGIN_ROOT/scripts/ensure_docs_index_next_section.mjs` 로 섹션만 append 한다.

`$PLUGIN_ROOT/scripts/aggregate_index_map.mjs` 는 각 epic 폴더와 opt-in module 폴더를 결정적으로 정렬하고 `docs/index.md` 의 `## 에픽` / `## 모듈` 표를 생성/갱신한다. 파일이 없는 선택 산출물 셀은 링크가 아닌 `—` 로 남긴다. `docs/modules/` 가 없으면 모듈 표는 생성하지 않아 단일 루트 프로젝트의 기존 index 동작을 바꾸지 않는다.

`$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs` 는 각 `docs/epics/epic-NN-<slug>/architecture.md` 의 `## 모듈 목록` 표와 `## Contract Ledger` 표를 수집해 전역 `docs/architecture.md` 의 `에픽 간 지도`, `전역 모듈 토폴로지`, `공유 계약 인덱스` 섹션을 생성/갱신한다. 이 세 섹션은 파생물이며 수동 편집하지 않는다. 모듈 스코프 문서가 있는 모듈은 epic architecture 의 `## 모듈 목록` 에 `docs/modules/<module-id>/architecture.md` 링크를 남기면 전역 topology 표에도 rebased 링크로 드러난다. epic architecture 템플릿의 표 헤더는 도구의 파싱 계약이므로 변경하려면 도구와 테스트를 함께 갱신한다.

Contract Ledger 는 cross-task 계약 전문의 단일 진본이다. `contract` 열은 stable row key 이며 발급 후 재사용하거나 의미를 바꾸지 않는다. impl/compact 산출물은 `contract.produces` / `contract.consumes` 와 `## Contract References` 에 row-key references 만 남긴다. invariant, ordering, error mode, config, forbidden alternative 전문은 `impl/NN-*.md` 나 compact plan 에 복제하지 않는다. task 내부 한정 private interface 는 cross-task 사본 문제가 없으므로 impl 문서 `## 인터페이스` 에 둘 수 있다.

기술 스택, naming, formatter, runtime, package manager, dependency policy 같은 반복 입력은 `docs/conventions.md` 에 둔다. 전역 architecture 는 시스템 topology 와 cross-epic map 에 집중한다.

기술 검토의 본문 결론만 `docs/tech-review.md` 에 남긴다. raw evidence, 통합 HTML report, screenshots, logs 는 `.dcness-work/reviews/` 에 저장하고 git-tracked 산출물로 취급하지 않는다.

`docs/metrics/design-runs.jsonl` 은 `/design` final validator `PASS` 직후 PR 생성 전에 helper 가 쓰는 영속 측정 인덱스다. worktree 진입 상태에서는 현재 design worktree 의 `docs/metrics/` 에 기록되고, design 산출물 PR 에 함께 커밋된다. PR/merge 뒤 `end-run` 을 미루면 기록이 worktree 또는 main working tree 에 uncommitted 상태로 고립되므로 `/design` 은 `end-run` 후 PR 을 만든다. run-local `ledger.jsonl` 이 TTL 정리되어도 후속 검증 세션은 이 파일만으로 run 단위 판정, finding 분류 분포(FAIL/ESCALATE prose token 언급 수), 재검증 cycle, 시간, 가능한 토큰량을 조회한다. 조회 계약은 `dcness-helper design-records [--json] [--limit N]` 이다. 사람이 산출물 본문을 손으로 편집하지 않는다.

## 모듈 산출물

`docs/modules/<module-id>/` 는 모노레포 또는 모듈화 프로젝트에서 특정 모듈만 다른 스택·빌드 명령·규약·runtime boundary 를 가질 때 만든다. 단순 디렉토리, 작은 library, 또는 전역 규약으로 충분한 내부 package 는 모듈 산출물을 만들지 않는다. 모듈 축은 문서 총량을 줄이기 위한 입력 경계이지, 코드 의존 그래프 관리 도구가 아니다.

`module-id` 는 문서 스코프 ID 다. repo-relative 코드 경로와 같을 필요는 없지만, 한 번 정하면 변경하지 않고 `docs/index.md` 의 `## 모듈` 표와 결정 기록 `scope` 값에 같은 ID 를 쓴다. 허용 형식은 `docs/modules/<module-id>/` 디렉토리명 기준으로 소문자 시작 + `[a-z0-9_-]` 다.

| 산출물 | module 폴더 기준 경로 | 생성 주체 | 양식 |
|---|---|---|---|
| module architecture | `architecture.md` | system-architect | 전역 architecture 와 같은 표 원칙을 쓰되 module-local boundary, owned code roots, local adapters, validation command 만 기록 |
| module conventions | `conventions.md` | system-architect | 전역 `docs/conventions.md` 의 delta 만 기록. 공통 formatter, branch rule, issue rule 복제 금지 |
| module tech-review | `tech-review.md` | tech-reviewer | 해당 모듈 한정 새 runtime/tool/dependency 검토가 있을 때만 작성 |

전역에 남기는 것:

- 제품 요구사항과 사용자-facing 범위: `docs/prd.md`
- epic/story 요구사항과 구현 순서: `docs/epics/epic-NN-<slug>/`
- 여러 모듈이 공유하는 시스템 topology, public contract, cross-epic map: `docs/architecture.md`
- 공통 스택·공통 도구·repo 전역 style: `docs/conventions.md`
- 결정 기록 파일 위치: `docs/decisions/NNNN-slug.md`

모듈로 내리는 것:

- 특정 모듈만 다른 runtime, package manager, build/test command, formatter/linter rule
- 특정 모듈 내부의 entrypoint, adapter, local port, owned code root, validation path
- 특정 모듈에만 적용되는 dependency policy 또는 기술 검토 결론
- 전역 문서에 두면 다른 모듈 작업자가 매번 무관한 세부사항을 읽게 되는 반복 입력

결정 기록은 위치를 분산하지 않고 계속 `docs/decisions/NNNN-slug.md` 에 둔다. frontmatter `scope` 값만 확장한다.

```yaml
scope: global
scope: epic-NN
scope: module:<module-id>
scope: module:<module-id>/epic-NN
```

기존 `global` 과 `epic-NN` 값은 그대로 유효하다. 결정이 여러 모듈을 동시에 바꾸면 module scope 를 여러 개 나열하지 말고 `epic-NN` 또는 `global` 로 올린 뒤 본문 링크에서 영향 모듈을 적는다. `module:<module-id>/epic-NN` 은 특정 epic 안에서 특정 모듈에만 닫히는 결정에 사용한다.

## 교차 모듈 epic

epic 은 제품 단위라 여러 모듈을 가로지를 수 있다. 교차 모듈 epic 도 `docs/epics/epic-NN-<slug>/` 하나만 가진다. backend 와 mobile app 을 동시에 바꾸는 기능이라도 모듈별 `stories.md` 사본을 만들지 않는다.

교차 모듈 epic 의 기준:

- `stories.md` 는 사용자-facing Story 와 완료 동작만 소유한다.
- epic `architecture.md` 는 `Story -> 모듈 매핑`, `Flow Ownership Map`, `Contract Ledger` 로 affected module 과 cross-module contract 를 드러낸다.
- 모듈별 `architecture.md` / `conventions.md` 는 해당 모듈의 local boundary 와 validation path 만 제공한다. epic 요구사항이나 Contract Ledger 전문을 복제하지 않는다.
- cross-module contract 전문은 epic `architecture.md` 의 `## Contract Ledger` 와 전역 `docs/architecture.md` generated `공유 계약 인덱스` 로 올라간다. 모듈 문서는 필요한 Ledger row key 링크만 둔다.
- module-architect 는 affected module 의 docs 만 읽는다. 같은 repo 의 다른 모듈 docs 는 code search 로 필요성이 확인되기 전까지 입력 세트에 넣지 않는다.

## epic 산출물

각 epic 은 `docs/epics/epic-NN-<slug>/` 폴더 하나를 가진다. `NN` 은 프로젝트 전역에서 증가하는 epic 번호다. milestone 은 폴더에 넣지 않고 `stories.md` frontmatter 의 `milestone: vNN` 로 표현한다.

| 산출물 | epic 폴더 기준 경로 | 생성 주체 | 양식 |
|---|---|---|---|
| Story 정의 | `stories.md` | `/spec` | `skills/spec/spec-stories-reference.md` |
| UX flow | `ux-flow.md` | ux-architect | `agents/ux-architect/templates/ux-flow.md` |
| epic architecture | `architecture.md` | system-architect / module-architect | `agents/system-architect/templates/epic-architecture.md` |
| domain model | `domain-model.md` | system-architect / module-architect | `agents/system-architect/templates/domain-model.md` |
| epic tech-review | `tech-review.md` | tech-reviewer | `agents/tech-reviewer/templates/tech-review.md` |
| impl task | `impl/NN-*.md` | module-architect | `agents/module-architect/templates/impl-task.md` |

epic `domain-model.md` 는 조건부 산출물이다. entity, value object, aggregate, domain service, invariant 같은 도메인 모델이 구현 판단에 필요할 때 작성한다. 낮은 도메인 복잡도에서는 생략 가능하며, 생략 판단 근거는 epic `architecture.md` 에 남긴다.

epic `tech-review.md` 는 `/design` 중 `NEW_DEP_ESCALATE` option 4 로 새 외부 의존을 해당 epic 범위에서 검토할 때만 만든다. 전역 PRD preflight 결과와 섞지 않는다.

## 작업용 산출물

| 산출물 | 경로 | 생성 주체 | 양식 |
|---|---|---|---|
| compact plan | `docs/compact-plans/<slug>.md` | module-architect | `agents/module-architect/templates/compact-plan.md` |

compact plan 은 `/impl` Standard 진입 전 경량 설계 산출물이다. 구현자가 읽어야 하므로 git-tracked 문서로 남긴다.

## Volatile 작업 영역

`.dcness-work/` 는 agent 가 참고할 수 있지만 장기 진본이 아닌 작업 흔적을 둔다.

| 영역 | 용도 |
|---|---|
| `.dcness-work/spikes/` | 짧은 탐색 결과, 버릴 수 있는 실험 |
| `.dcness-work/research/` | 외부 문서 조사 raw note |
| `.dcness-work/open-questions/` | 아직 산출물로 확정되지 않은 질문 |
| `.dcness-work/handoffs/` | run 간 임시 handoff |
| `.dcness-work/reviews/` | tech-review evidence, HTML report, logs |

`/init-dcness` 는 사용자 프로젝트 `.gitignore` 에 `.dcness-work/` 를 추가한다.

## 금지된 신규 산출물 위치

다음 root-flat 경로는 신규 산출물 위치가 아니다. 단일 epic 프로젝트도 같은 epic 폴더 구조를 쓴다.

- `docs/stories.md`
- `docs/ux-flow.md`
- `docs/domain-model.md`
- `docs/impl/`
- `docs/<module-id>-architecture.md`
- `docs/<module-id>-conventions.md`

ADR 파일도 만들지 않는다.

- `docs/adr.md`
- `docs/epics/epic-NN-<slug>/adr.md`

결정 기록 파일은 모두 `docs/decisions/NNNN-slug.md` 로 간다. epic 문서와 module 문서는 필요한 결정 링크만 둔다.

## Agent 입력 세트

agent prompt 는 문서 전문 재기입 대신 아래 포인터 세트를 넘긴다.

| 역할 | 전역 최소 입력 | module 스코프 입력 | epic 고정 입력 | 상황별 입력 |
|---|---|---|---|---|
| ux-architect | `docs/index.md`, `docs/prd.md`, `docs/conventions.md` | 해당 화면이 특정 모듈에 닫히면 `docs/modules/<module-id>/conventions.md` | `stories.md`, 대상 `ux-flow.md` | `docs/design.md`, 기존 화면 코드 |
| system-architect | `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` | affected module 의 `architecture.md`, `conventions.md`, 선택 `tech-review.md` | `stories.md`, `architecture.md`, 선택 `domain-model.md` | `docs/tech-review.md`, epic `tech-review.md`, `ux-flow.md`, 코드 계약 표면 |
| module-architect | `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` | affected module 의 `architecture.md`, `conventions.md`, validation path | `stories.md`, `architecture.md`, 선택 `domain-model.md`, `impl/` | `docs/design.md`, `docs/compact-plans/<slug>.md`, 코드 계약 표면 |
| tech-reviewer | `docs/index.md`, `docs/prd.md`, `docs/conventions.md` | 새 의존·runtime 이 특정 모듈에 닫히면 해당 module docs | option 4 때 대상 epic `stories.md` | `.dcness-work/reviews/` |

impl task 와 compact plan 은 `## 사전 준비` 아래에 `읽을 문서`와 `읽을 코드`를 명시한다. 이 두 목록은 downstream 구현 agent 의 deterministic input 이며, 문서 탐험을 대신하지 않는다. 모듈 작업이면 affected module 문서만 이 목록에 넣는다.

## 시드 양식 = 산출 양식

`/init-dcness` 는 `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` 를 만든다. 시드 파일은 실제 authoring 템플릿과 같은 원본을 사용한다. 빈 seed 전용 복제본을 따로 만들지 않는다. `docs/modules/` 는 모노레포·모듈화가 확인된 뒤 만드는 opt-in 산출물이므로 `/init-dcness` 기본 seed 로 만들지 않는다.

index epic/module 표와 전역 architecture map 이 stale 인지 확인하려면 활성 프로젝트 루트에서 plugin script 를 실행한다.

```sh
node "$PLUGIN_ROOT/scripts/aggregate_index_map.mjs" --check
node "$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs" --check
node "$PLUGIN_ROOT/scripts/check_design_artifact_structure.mjs"
```

## dcness-self 영역

dcNess 저장소 자기 자신의 `docs/` 는 활성 프로젝트 구조를 그대로 적용하지 않는다.

- `docs/plugin/**` — 외부 활성 프로젝트가 받는 plug-in SSOT 문서.
- `docs/internal/**` — self 운영 문서.
- `docs/archive/**` — 폐기/역사 자료.
- `docs/compact-plans/**` — self 작업 중 생기는 compact plan.
