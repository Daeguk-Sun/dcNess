# 공개 Workflow 진입점

> dcNess 사용자가 기본으로 외울 진입점과, 내부 gate/agent 를 구분하는 공개 진입점 계약. 용어 기준은 [`terms.md`](terms.md) 다.

dcNess 의 기본 공개 workflow 는 제품 생명주기 기준으로 계획 / 설계 / 구현 / 검수 네 단계다. 사용자가 기본으로 기억할 흐름은 `/spec -> /design -> /impl -> /acceptance` 다.

운영 원칙: 공개 진입점은 작게 유지하고, 사용자가 명시한 구현 의도는 우선한다. high-risk 신호는 설계 선행 권고로 보여주되 자동 차단하지 않는다.

| 기본 진입점 | 언제 쓰나 | 내부 처리 |
|---|---|---|
| `/spec` | 새 제품 기능, 큰 기획, PRD 변경처럼 의도 합의가 먼저 필요할 때 | PRD 초안/최종화 / stories / 필요한 tech-review preflight + `SPEC_ACCEPTANCE` |
| `/design` | PRD 이후 구현 전 product/technical design, 즉 설계 전체가 필요할 때 | UX / 시스템 / 모듈 / 기술 선택 설계. 구현 없이 visual design 만 먼저 탐색하려면 `/ux` |
| `/impl` | 구현, 수정, 버그픽스, 작은 리팩터링을 실제 PR 로 끝낼 때 | direct/design-doc 경로 + 구현 소유자 + 반대 진영 review를 내부 판정 |
| `/acceptance` | PRD / Epic / Story 기준 제품 검수와 gap 후속 연결이 필요할 때 | story/epic acceptance. 핵심 AC별 동작 증거와 mock-only gap 을 구분한다. 사람 full E2E 는 MVP 범위 밖 |

사용자는 구현 경로나 엔진 이름을 외울 필요가 없다. `/impl` 은 설계를 하지 않고 파일·이슈·테스트 같은 concrete signal 이 있거나 자연어 구현 의도가 충분하면 바로 구현한다. 설계도 경로가 있으면 design-doc 으로 받은 설계도를 구현한다. 이미 명확한 복잡 신호가 있으면 첫 source edit 전에 headless owner를 선택하고, 단순하거나 애매하면 main-direct로 진행한다. 구현 도중 owner를 바꾸지 않으며 review는 실제 구현 성공 provider의 반대 진영이다. issue 등록은 사용자가 요청했을 때만 `/to-issue` 로 분기하고, 제품 의미가 실제로 둘 이상일 때만 짧게 묻는다. high-risk trigger 나 새 epic/product feature 는 설계 선행을 권장하는 신호지만, 사용자가 그대로 진행을 택하면 `/impl` 이 구현한다. 조건과 권고 기준은 [`workflow-router.md#구현-경로-표`](workflow-router.md#구현-경로-표) 가 소유한다. 본 문서는 공개 진입점과 사용자-facing 노출 범위만 소유한다.

## Support Entrypoints

아래 skill 은 기본 생명주기 밖의 issue 초안/등록 흐름이다. 수정 실행은 `/impl`, 제품 검수 후속은 `/acceptance`, GitHub issue 로 추적할 작업 후보는 `/to-issue` 로 구분한다.

| support 진입점 | 역할 |
|---|---|
| `/to-issue` | 문제/작업 후보를 메인이 맥락에서 추론해 dcNess 표준 Issue Brief 로 구성하고, 초안 승인 대기 없이 GitHub issue 와 Project item 으로 바로 등록 (사용자는 web 에서 확인·수정) |

## Advanced Entrypoints

아래 skill 은 기본 공개 진입점이 아니라 고급/전문 진입점이다. 사용자가 직접 호출할 수는 있지만 README 기본 흐름에서는 lifecycle 진입점 뒤의 내부 단계로 설명한다.

| 고급 진입점 | 위치 |
|---|---|
| `/tech-review` | high-risk 설계 선행을 선택했을 때 `/spec` 내부 preflight 로 쓰는 선행 기술 검증 |
| `/impl-loop` | story/epic 단위 headless 구현 runner |

## Utility 공개 노출 범위

운영 보조 command 와 구현 전 선행 탐색 utility 는 workflow 진입점과 분리한다.

| 유틸리티 | 역할 |
|---|---|
| `/ux` | 구현 없이 목업과 흐름을 먼저 탐색한다. 디자인 시스템 / 디자인 토큰 / 베이스라인 요청도 ad-hoc 문서가 아니라 `docs/design.md` 기준 신호로 정리한다. 내부 `canvas-design` wrapper 를 통해 drafts 반복 → 사용자 PICK → 확정본 승격 + 보드·진입점 재생성 규약을 따른다 |
| `/init-dcness` | 프로젝트 활성화. 비활성화(whitelist 제거) 요청도 같은 진입점이 처리한다 |
| `/migrate-dcness` | 기존 비-dcness 프로젝트를 코드 역설계로 전역 docs(`prd.md`/`architecture.md`/`conventions.md`/`decisions/`/`index.md`)를 채워 부트스트랩하는 일회성 유틸리티. `/init-dcness`(활성화)의 짝. epic/story 산출물은 만들지 않는다 |
| `/next-work` | GitHub issue open/closed 상태, `in-progress` label, Issue Brief Priority 로 다음 작업 후보를 read-only 조회 |
| `/run-review` | 끝난 run의 비용·낭비와 활성 프로젝트 전반의 반복 신호를 함께 검토하고, 가치 있는 하네스 경량화 후보가 있을 때만 실험 승인을 요청 |
| `/smart-compact` | resume prompt 포함 *같은 세션* context compact 보조 |
| `/handoff` | 세션을 넘기기 전 의도/결정/진행/다음 액션을 `.dcness-work/handoffs/next-session.md` 에 인계 문서로 기록한다. 다음 세션 SessionStart 훅이 최우선 주입 후 archive 로 clear 하는 결정적 cross-session warm 인계 (auto-memory 비의존) |
| `/efficiency` | 세션 토큰/비용 분석 |

## Internal Skills

아래 skill 은 공개 진입점이 아니라 **다른 workflow 내부에서만 호출**되는 내부 skill 이다. 일부는 되돌림(backpressure) 목적지이고, 일부는 공개 workflow 의 stage 분리용 목적지다. 사용자가 `/` 진입점으로 외우지 않으며 README 기본 흐름에도 노출하지 않는다.

| 내부 skill | 역할 |
|---|---|
| `canvas-design` | `/ux`, `/impl`, `/impl-loop` 이 UI 기준 확보나 선행 목업 탐색이 필요하다고 판정했을 때 호출하는 내부 wrapper. designer draft 생성, 사용자 PICK, 확정본 승격, 보드·진입점 재생성을 한 경로로 수행하며 공개 진입점으로 노출하지 않음 |
| `design-ux` | `/design` dispatcher 가 UI epic 의 UX 산출물이 아직 durable 하지 않다고 판정했을 때 호출하는 내부 stage 1. `ux-flow.md` / `docs/design.md` / `docs/design-variants/` 확정본을 자체 PR 로 머지하며 공개 진입점으로 노출하지 않음 |
| `design-system` | `/design` dispatcher 가 UI-less epic 이거나 UX stage 완료 epic 이라고 판정했을 때 호출하는 내부 stage 2. 기존 system/module 설계 pack 계약을 자체 PR 로 머지하며 공개 진입점으로 노출하지 않음 |

`canvas-design` 은 시각 기준 확보를 각 workflow 안에 중복 기술하지 않기 위한 내부 wrapper 다. 확정본 SSOT 는 `docs/design-variants/screens/` 이며, designer 는 `drafts/` 만 쓰고 메인이 PICK과 승격을 소유한다. 파생 보드와 진입점은 생성기가 갱신한다. `/ux` 는 이 경로를 얇게 감싸고, `/impl` 과 `/impl-loop` 은 확정 목업 경로와 node-id 매핑을 구현자에게 전달한다.

`design-ux` 와 `design-system` 은 `/design` 의 내부 stage 다. 사용자가 stage 이름을 호출하지 않고, `/design` 이 durable 산출물 실존 판정으로 자동 선택한다. `ux-flow.md` 존재 + 설계 pack 부재이면 `docs/index.md` 와 `/next-work` 가 "`/design` (ux 완료 · system 미완)" 을 표시해 다음 `/design` 진입이 system stage 로 이어진다.

## Internal Agents

agent 는 사용자가 외워야 하는 command 가 아니다. `architecture-validator`, `build-worker`, `impl-validator`, `designer`, `module-architect`, `product-acceptance`, `system-architect`, `tech-reviewer`, `ux-architect` 는 workflow 내부에서 호출되는 gate/worker/reviewer 로 분류한다.

특히 `impl-validator`, `architecture-validator` 는 read-only validation provider 분기 대상이다. `build-worker` 는 `/impl-loop`와 복잡 `/impl`의 내부 headless implementation provider이며 새 공개 구현 경로가 아니다. provider가 Claude든 Codex든 사용자-facing 단계 이름은 `impl-validator` / `build-worker` 같은 agent 이름으로 유지한다.

## Contract Gate

기본/support/고급/유틸리티/내부 agent 목록(과 내부 skill `internalSkills`)과 skill/command/agent 의 frontmatter name 대 path 정합은 [`scripts/check_public_surface.mjs`](https://github.com/Daeguk-Sun/dcNess/blob/main/scripts/check_public_surface.mjs) 가 검사한다. 새 기본 workflow 를 추가하려면 이 문서와 gate 기대값을 함께 수정해야 한다. `canvas-design`, `design-ux`, `design-system` 같은 내부 skill 은 `internalSkills` 카테고리로 분류돼 `/` 공개 진입점에 추가되지 않는다.

### 신규 공개 진입점 justification (왜 작게 유지하나)

운영 원칙상 사용자-facing 공개 노출 범위는 작게 유지가 기본이다 (내부 정책은 정교해도 외부 UX 는 단순하게). 따라서 새 skill/command/agent/gate 를 추가하려면 PR 에서 **왜 기존 공개 진입점으로 부족한지**를 먼저 설명한다 — 구체적으로:

- 기존 위험 분기([`workflow-router.md`](workflow-router.md))의 구현 경로로 흡수 안 되는가?
- 기존 validator(`impl-validator` / `architecture-validator`)로 검증이 안 되는가?
- 기존 utility/agent 의 내부 단계로 둘 수 없고 *새 public 발화*가 꼭 필요한가?

세 질문에 모두 "그렇다(기존으론 부족)"가 서지 않으면 새 공개 진입점 대신 기존 구현 경로/agent 내부 단계로 흡수한다. 이 justification 은 [`CLAUDE.md` 안티패턴 5](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) 의 self 가드레일이자 PR 템플릿 체크 항목이다.
