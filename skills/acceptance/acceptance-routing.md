# acceptance 분기 규칙 SSOT

> **Status**: ACTIVE
> **Scope**: `/acceptance` skill 단일 전용 분기 규칙 진본. MVP 범위는 story / epic 제품 검수다. 진행 절차는 [`SKILL.md`](SKILL.md).

## 분기 그래프

```mermaid
flowchart TB
  IN[/acceptance input/] --> UNIT{검수 단위?}
  UNIT -->|story| SA[product-acceptance:STORY_ACCEPTANCE]
  UNIT -->|epic| EA[product-acceptance:EPIC_ACCEPTANCE]
  UNIT -->|불명확| U((사용자에게 입력 요청))

  SA -->|PASS| SP[story 완료 후보 보고]
  SA -->|FAIL| SG[story gap 목록 + 후속 분기]
  SA -->|ESCALATE| U

  EA -->|PASS| EP[epic 완료 후보 보고]
  EA -->|FAIL| EG[epic gap 목록 + 후속 분기]
  EA -->|ESCALATE| U

  SG -.->|자동 수정 X| TAX[gap taxonomy]
  EG -.->|자동 issue 생성 X| TAX
  TAX --> NEXT1["/impl · /design · /spec · /ux · /to-issue 후보"]

  classDef verify fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef report fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class SA,EA verify
  class SP,SG,EP,EG report
  class U user
```

## 결론 → 다음 행동

| 입력 | 다음 |
|---|---|
| `product-acceptance:STORY_ACCEPTANCE` `PASS` | story 완료 후보로 보고. 자동 close 는 하지 않는다. |
| `product-acceptance:STORY_ACCEPTANCE` `FAIL` | AC / PR / test evidence gap, 동작 증거 부족, mock-only green, 화면 증거 부재, 목업 불일치, 사용자 동선 부적합을 보고하고 `/impl`, `/design`, `/ux` 회수 후보를 제안한다. |
| `product-acceptance:EPIC_ACCEPTANCE` `PASS` | epic 완료 후보로 보고. 자동 close 는 하지 않는다. |
| `product-acceptance:EPIC_ACCEPTANCE` `FAIL` | Epic 완료 기준·Story AC, cross-story 동작 gap, mock-only green, 화면 증거 부재, 목업 불일치, cross-story 사용자 동선 부적합, security/ops risk 를 보고하고 후속 분기를 제안한다. |
| `ESCALATE` | 기준 문서, 구현 PR 목록, 권한, 사용자 결정 부족을 보고하고 대기한다. |

Cartography freshness gap은 standalone `/acceptance`의 읽기 전용 경계를 유지하면서 다음 producer까지 비지 않게 한다.

| Cartography 결과 | 다음 producer |
|---|---|
| 영향 없음 또는 Root와 일치 | 기존 story/epic 완료 후보 보고 |
| system boundary 유지 + route/state/as-built edge 또는 capability 상태 drift | `module-architect:CARTOGRAPHY_REFRESH`가 affected Root Cartography만 bounded refresh. local-only/ignored이면 canonical local refresh 또는 durable impact handoff를 보존하고 private docs를 code PR에 강제 포함하지 않음. durable impact handoff만으로 freshness가 해소되지는 않으며 canonical local Root refresh 확인 전에는 PASS 금지 |
| system boundary·global decision 변경 | route-only patch 금지. `/design --revise` 또는 system checkpoint backpressure 보고 |

standalone `/acceptance`는 이 producer를 직접 호출하지 않고 gap과 근거를 보고한다. product-acceptance와 acceptance skill은 모두 읽기 전용이다.

## 깊이 차이

Story acceptance 는 가볍게 AC / PR / test evidence 중심으로 돈다. 단, 핵심 AC는 단순 파일/테스트 존재가 아니라 동작 증거와 연결돼야 하며, 대상 사용자의 입력/진행 동선으로도 닫혀야 한다. mock-only green 과 사용자 동선 부적합은 gap 으로 분리한다. story마다 full product/security/performance audit 을 강제하지 않는다.

Epic acceptance 는 Epic 완료 기준과 Story AC 전항목, cross-story gap, security/ops risk 를 포함한다. 여러 story가 합쳐질 때 생기는 흐름, 권한, 데이터, 운영 위험을 보며, PR/story 경계를 넘는 통합 동작과 사용자 동선 검증의 책임은 이 epic acceptance 에 있다. impl-validator 가 merge candidate diff 를 보는 동안, product-acceptance 는 story/epic 마감 경계에서 사용자 약속이 실제 동작 증거와 대상 사용자에게 맞는 진행 흐름으로 닫혔는지 확인한다.

## 동작 증거 판정

동작 증거는 사람 E2E만 뜻하지 않는다. 핵심 AC 성격에 맞으면 정적 타입검사/compile, 실데이터(non-mock) 통합 테스트, UI 자동화, API/CLI smoke, 실제 앱 진입점 실행 기록을 인정한다.

mock/stub/fake 기반 unit test 는 보조 증거다. 핵심 AC가 mock-only green으로만 닫히고 실제 제품 경계(API/CLI/UI/통합 wiring/compile-time contract)가 확인되지 않았으면 `검수 증거 부족 / 스모크 실패` 계열 gap 으로 보고한다.

정적 타입검사나 compile gate 가 의미 있는 stack 인데 증거에 없으면 품질 게이트 warning 으로 보고한다. warning 자체는 자동 FAIL 이 아니지만, 그 부재 때문에 핵심 AC의 wiring/contract 동작을 증명할 수 없으면 FAIL gap 이다.

## UI 목업 정합 판정

UI story/epic 에서 호출자가 확정 목업 경로와 구현 화면 스크린샷 또는 동등한 화면 증거 경로를 제공하면, product-acceptance 는 양쪽을 Read 로 열어 레이아웃 계층, 상태(default/empty/error 등), 핵심 `data-node-id`, 토큰 대응의 구조적 일치를 본다. pixel-diff 자동화는 하드 게이트가 아니다.

UI story 인데 실제 실행 화면을 확인할 화면 증거가 없으면 `화면 증거 부재` gap 으로 보고한다. 확정 목업과 화면 증거가 구조적으로 어긋나면 `목업 불일치` gap 으로 보고한다.

## 사용자 동선 적합성 판정

핵심 AC가 실제로 실행되더라도, 성공 경로가 대상 사용자에게 맞는 입력/진행 동선인지 별도로 본다. non-developer user-facing flow 에서 사용자가 내부 schema, DB shape, API payload, prompt/config shape, 내부 ID 같은 구현 계약을 직접 조립해야 목표를 달성할 수 있으면 `사용자 동선 부적합 / 내부 계약 노출` gap 으로 보고한다.

이 판정은 raw JSON 같은 특정 표현을 찾는 체크리스트가 아니라, 대상 사용자가 제품 개념과 작업 언어로 판단할 수 있는 흐름인지 보는 의미축이다. 개발자용 CLI/API처럼 JSON/config 입력이 대상 사용자에게 자연스러운 경우에는 안정된 공개 계약, 예제, 필드 설명, 오류 메시지가 문서화돼 있는지 확인한다. 문서화된 계약이면 gap 이 아니며, 문서가 부족하면 warning 또는 핵심 AC gap 으로 분리한다.

## Gap taxonomy → 후속 분기

`FAIL` 이면 product-acceptance prose 에서 gap 을 아래 taxonomy 로 묶어 보고한다. 후속은 자동 진입이 아니라 사용자에게 제안하는 다음 작업 단위다.

| gap 종류 | 후속 |
|---|---|
| PRD 유저 시나리오 / Story AC 미충족 | `/to-issue` 후보 + `/impl` |
| 설계 결함 / 범위 재정의 필요 | `/design` 또는 `/spec` |
| 검수 증거 부족 / 스모크 실패 | gap 또는 bug `/to-issue` 후보 + `/impl` |
| mock-only green / 동작 증거 부족 | gap 또는 bug `/to-issue` 후보 + `/impl` |
| 화면 증거 부재 | gap 또는 bug `/to-issue` 후보 + `/impl` |
| 목업 불일치 | gap 또는 bug `/to-issue` 후보 + `/ux` 또는 `/impl` |
| 사용자 동선 부적합 / 내부 계약 노출 | gap 또는 bug `/to-issue` 후보 + `/ux` 또는 `/impl` 또는 `/design` |
| UX 미완성 | `/ux` |
| 성능 병목 / 리팩토링 필요 | `/to-issue` 후보 + `/impl` 또는 `/design` |
| 보안 / 권한 / 데이터 리스크 | `/to-issue` 후보 + `/design` 또는 사용자 위임 |
| Root route/state/as-built edge 또는 capability 상태 drift | `module-architect:CARTOGRAPHY_REFRESH` + affected Root Cartography + durable impact handoff |
| system boundary / global decision Cartography gap | `/design --revise` 또는 system checkpoint backpressure |

story acceptance 는 주로 PRD 유저 시나리오 / Story AC 미충족, 검수 증거 부족 / 스모크 실패, mock-only green / 동작 증거 부족, 화면 증거 부재, 목업 불일치, 사용자 동선 부적합 / 내부 계약 노출을 만든다. epic acceptance 는 cross-story gap, 화면 증거 부재, cross-story 목업 불일치, cross-story 사용자 동선 부적합, 성능 병목 / 리팩토링 필요, 보안 / 권한 / 데이터 리스크까지 같이 본다.

품질 게이트 warning 은 gap 과 별개로 남길 수 있다. 예를 들어 TypeScript 프로젝트에 `tsc --noEmit` 또는 그에 준하는 compile/typecheck 증거가 전혀 없으면 warning 으로 보고하고, 핵심 AC 검증에도 영향을 주는 경우에만 위 gap taxonomy 로 승격한다.

사용자 동선 warning 도 gap 과 별개로 남길 수 있다. 예를 들어 개발자용 CLI/API가 JSON 입력을 받는 것은 정당하지만 계약 예제가 부족하면 warning 으로 보고하고, 그 부족 때문에 대상 사용자가 핵심 AC를 수행할 수 없으면 gap 으로 승격한다.

`/design` 은 `/design` 호환 alias 이므로 acceptance gap 의 설계 회수 후보는 사용자-facing 공개 진입점인 `/design` 으로 제안한다.

acceptance gap issue 는 제품 검수 후속이다. 이미 기준 문서와 구현 증거에서 나온 gap 이므로, 별도 분류 흐름으로 되돌리지 않는다.

## Gap 처리

`FAIL` 은 끝이 아니라 다음 작업 단위로 돌아가기 위한 보고다.

- 자동 수정하지 않는다. (standalone `/acceptance` 한정 — `/impl-loop` 의 story/epic 마감 inline 검수는 마감 PR 이 아직 열려 있어 auto-fixable gap 의 수정 루프를 돌며, 그 결론→다음은 [`impl-loop-routing.md` 마감 acceptance 분기](../impl-loop/impl-loop-routing.md#마감-acceptance-분기) 가 소유한다.)
- 자동 issue 생성하지 않는다.
- 사용자 승인 없이 GitHub issue 를 만들지 않는다.
- gap 은 기준 문서, 구현 증거, 누락 사실, 후속 분기를 포함한다.
- gap 을 GitHub issue 로 만들 때는 `/to-issue` 로 Issue Brief 초안과 사용자 승인을 먼저 거친다.

## Issue 생성 단계 전략

- 1차: 자동 issue 생성 없이 gap 목록 + 후속 분기 prose 만 안정화한다.
- 2차: 사용자 승인 또는 명시 옵션이 있을 때만 `/to-issue` 흐름으로 GitHub issue 를 만든다.
- 3차: story/epic sub-issue 연결과 close 정책 정합을 다룬다.
- 후속: release/product acceptance 에서 사람 full E2E gap loop 를 별도로 설계한다. 사람 full E2E gap loop 는 MVP 범위 밖이지만, 자동 동작 증거 판정은 story/epic acceptance 의 현재 범위다.

후속 분기는 MVP 에서 prose 보고만 한다. acceptance gap issue 생성과 자동 연결은 후속 단계에서 다룬다.

## Non-goals

- 사람 full E2E 검증은 MVP 범위 밖이다.
- direct `/impl` 단발 작업을 `/acceptance` 로 강제하지 않는다.
- 기존 `impl-validator`, `architecture-validator` 를 대체하지 않는다.
