# 산출물 지도 (Deliverables Map)

> dcNess 활성 프로젝트의 `docs/` 산출물 위치, 생성 주체, 양식, 입력 경계의 SSOT.
> 기준은 사람이 훑기 편한 목차가 아니라, **cold-start stateless agent 가 같은 문서를 읽고 같은 맥락으로 시작하는 것**이다.

## 북극성

- 전역 사실은 전역 anchor 한 곳에 둔다. 같은 결정이 여러 epic 문서에 복제되어 drift 되는 구조를 만들지 않는다.
- role 입력은 결정론적인 최소 세트다. 각 agent 는 자기 역할에 필요한 전역 최소 문서와 대상 epic 고정 문서만 읽는다.
- downstream agent 가 읽어야 하는 산출물은 git-tracked 문서다. 실측 evidence, HTML report, handoff scratch 처럼 재현 가능한 임시물은 `.dcness-work/` 에 둔다.
- 새 프로젝트 산출물은 `docs/epics/`, `docs/decisions/`, `docs/compact-plans/` 아래로만 증식한다. milestone 은 경로가 아니라 epic frontmatter 의 `milestone: vNN` 값이다.

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
├── decisions/
│   └── NNNN-slug.md                 # 전역 결정 기록
├── compact-plans/
│   └── <slug>.md                    # 경량 구현 설계
└── epics/
    └── epic-NN-<slug>/
        ├── stories.md               # epic/story 요구사항
        ├── ux-flow.md               # 선택: epic 화면 흐름
        ├── architecture.md          # epic 국소 architecture
        ├── domain-model.md          # epic 국소 domain model
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
| 문서 entrypoint | `docs/index.md` | `/init-dcness`, `/spec` | `skills/spec/templates/index.md` |
| PRD | `docs/prd.md` | `/spec` | `skills/spec/templates/prd.md` |
| 전역 architecture map | `docs/architecture.md` | system-architect | `agents/system-architect/templates/root-architecture.md` |
| convention map | `docs/conventions.md` | `/init-dcness`, system-architect | `agents/system-architect/templates/conventions.md` |
| 기술 검토 결론 | `docs/tech-review.md` | tech-reviewer | `agents/tech-reviewer/templates/tech-review.md` |
| 전역 design token | `docs/design.md` | ux-architect | `docs/plugin/design.md` |
| 결정 기록 | `docs/decisions/NNNN-slug.md` | system-architect / module-architect | `agents/system-architect/templates/decision.md` |

`docs/architecture.md` 는 epic 이 늘 때마다 append-growing map 으로 갱신한다. 상세 설계 본문을 전역에 복제하지 않고, 전역 모듈/의존/결정 anchor 와 epic 문서 링크를 추가한다.

기술 스택, naming, formatter, runtime, package manager, dependency policy 같은 반복 입력은 `docs/conventions.md` 에 둔다. 전역 architecture 는 시스템 topology 와 cross-epic map 에 집중한다.

기술 검토의 본문 결론만 `docs/tech-review.md` 에 남긴다. raw evidence, 통합 HTML report, screenshots, logs 는 `.dcness-work/reviews/` 에 저장하고 git-tracked 산출물로 취급하지 않는다.

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

ADR 파일도 만들지 않는다.

- `docs/adr.md`
- `docs/epics/epic-NN-<slug>/adr.md`

결정 기록은 모두 `docs/decisions/NNNN-slug.md` 로 간다. epic 문서는 필요한 결정 링크만 둔다.

## Agent 입력 세트

agent prompt 는 문서 전문 재기입 대신 아래 포인터 세트를 넘긴다.

| 역할 | 전역 최소 입력 | epic 고정 입력 | 상황별 입력 |
|---|---|---|---|
| ux-architect | `docs/index.md`, `docs/prd.md`, `docs/conventions.md` | `stories.md`, 대상 `ux-flow.md` | `docs/design.md`, 기존 화면 코드 |
| system-architect | `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` | `stories.md`, `architecture.md`, `domain-model.md` | `docs/tech-review.md`, epic `tech-review.md`, `ux-flow.md` |
| module-architect | `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` | `stories.md`, `architecture.md`, `domain-model.md`, `impl/` | `docs/design.md`, `docs/compact-plans/<slug>.md` |
| tech-reviewer | `docs/index.md`, `docs/prd.md`, `docs/conventions.md` | option 4 때 대상 epic `stories.md` | `.dcness-work/reviews/` |

impl task 와 compact plan 은 `## 사전 준비` 아래에 `읽을 문서`와 `읽을 코드`를 명시한다. 이 두 목록은 downstream 구현 agent 의 deterministic input 이며, 문서 탐험을 대신하지 않는다.

## 시드 양식 = 산출 양식

`/init-dcness` 는 `docs/index.md`, `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/` 를 만든다. 시드 파일은 실제 authoring 템플릿과 같은 원본을 사용한다. 빈 seed 전용 복제본을 따로 만들지 않는다.

## dcness-self 영역

dcNess 저장소 자기 자신의 `docs/` 는 활성 프로젝트 구조를 그대로 적용하지 않는다.

- `docs/plugin/**` — 외부 활성 프로젝트가 받는 plug-in SSOT 문서.
- `docs/internal/**` — self 운영 문서.
- `docs/archive/**` — 폐기/역사 자료.
- `docs/compact-plans/**` — self 작업 중 생기는 compact plan.
