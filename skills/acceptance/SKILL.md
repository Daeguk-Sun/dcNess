---
name: acceptance
description: story 또는 epic 구현 완료 후 제품 단위 검수를 수행하는 MVP skill. 사용자가 "/acceptance story", "/acceptance epic", "story 검수", "epic 검수", "AC 기준으로 완료됐는지 봐줘" 등을 말할 때 사용한다. full E2E 검증은 MVP 범위 밖이지만, 핵심 AC가 mock-only green이나 대상 사용자에게 부적합한 입력/진행 동선으로만 닫히는 것은 gap으로 분리한다. Lite `/impl` 단발 작업에 자동 강제하지 않는다.
---

# Acceptance Skill — story/epic 제품 검수 MVP

`/acceptance` 는 PR 하나의 코드 리뷰가 아니라 제품 단위 완료 여부를 확인하는 검수 skill 이다. MVP 에서는 story / epic 검수만 다룬다.

> 🔴 **분기 규칙 SSOT** — `product-acceptance` 결론(`PASS` / `FAIL` / `ESCALATE`) → 다음 행동은 [`acceptance-routing.md`](acceptance-routing.md) 가 본 skill 의 단일 진본이다. 본 파일은 입력 정형화와 진행 절차만 담는다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../docs/plugin/terms.md) 를 확인한다.

> `/impl-loop` 는 story/epic 마감 task 의 머지 *전* 에 같은 `product-acceptance` agent 로 inline 검수를 돈다 — 그 경로의 결론→다음(gap 수정 루프 포함)은 [`impl-loop-routing.md` 마감 acceptance 분기](../impl-loop/impl-loop-routing.md#마감-acceptance-분기) 가 소유하고, 본 skill 의 prompt 규약(아래 Story/Epic Acceptance 호출 형식)만 재사용한다.

## Inputs

메인이 사용자에게 받거나 직접 확인해야 할 입력:

- 검수 단위: `story` 또는 `epic`
- story issue 또는 epic issue
- `docs/index.md`, `docs/prd.md`, `docs/epics/<epic>/stories.md`
- 필요한 `docs/decisions/` decision, 전역/epic architecture, impl 문서 경로
- 구현 PR 목록
- 핵심 AC별 동작 증거: 정적 타입검사/compile, 실데이터(non-mock) 통합 테스트, UI 자동화, API/CLI smoke, 화면/API/CLI 동작 기록 중 해당하는 것
- 대상 사용자와 핵심 입력/진행 동선
- mock/stub/fake 를 쓴 증거라면 mock 경계와 실제로 실행된 제품 경계
- 이전 acceptance gap 이 있으면 그 결과와 재검수 대상

입력이 부족하면 추측으로 검수하지 않고 사용자에게 어떤 경로/PR/issue 가 필요한지 묻는다.

## 비대상

- 새 spec 작성 또는 PRD 변경 → `/spec`
- 설계 산출물 작성/수정 → `/design`
- 구현 자체 → `/impl`
- GitHub issue 초안/등록 → `/to-issue`
- release readiness, 배포, migration, 사람 full E2E 검증 → MVP 범위 밖. 후속 release/product acceptance 고도화에서 다룬다. 단, 자동 동작 증거 판정은 story/epic acceptance 범위다.

Lite `/impl` 단발 작업은 불필요하게 `/acceptance` 로 강제하지 않는다. 파일/symbol이 명확한 작은 수정은 기존 test + pr-reviewer + CI gate 로 끝날 수 있다.

## 동작 증거 원칙

`/acceptance` 의 기준은 "구현 파일 또는 테스트가 존재한다"가 아니라, 사용자에게 약속한 핵심 AC가 실제 제품 경계에서 확인됐는가다.

- 동작 증거는 사람 E2E만 뜻하지 않는다. AC 성격에 맞으면 정적 타입검사/compile, 실데이터(non-mock) 통합 테스트, UI 자동화, API/CLI smoke, 실제 앱 진입점 실행 기록도 동작 증거로 인정한다.
- mock/stub/fake 기반 unit test 는 보조 증거가 될 수 있다. 그러나 핵심 AC가 mock-only green으로만 뒷받침되고 실제 제품 경계(API/CLI/UI/통합 wiring/compile-time contract)가 한 번도 확인되지 않았으면 gap이다.
- 정적 타입검사나 compile gate 가 의미 있는 stack(TypeScript, typed Python, Rust, Go 등)인데 증거에 없으면 품질 게이트 warning 으로 보고한다. 이 warning 자체만으로 FAIL 로 만들지는 않지만, 그 부재 때문에 핵심 AC의 wiring/contract 동작을 증명할 수 없으면 검수 증거 gap 이다.

## 사용자 동선 적합성 원칙

`/acceptance` 는 동작 증거와 별개로, 핵심 AC의 입력과 진행 동선이 대상 사용자에게 맞는지도 본다. 성공 경로가 내부 구현 형태를 사용자가 직접 이해하고 조립해야만 열리는 경우에는 제품 완료로 보지 않는다.

- non-developer user-facing flow 는 제품 개념과 사용자의 작업 언어로 진행돼야 한다. 내부 schema, DB shape, API payload, prompt/config shape, 내부 ID 같은 구현 계약을 사용자가 직접 만들어 넣어야 핵심 AC가 수행되면 gap 이다.
- 이 기준은 특정 문자열을 금지하는 체크리스트가 아니라, 대상 사용자가 자연스럽게 판단하고 수행할 수 있는 입력/진행 동선인지 보는 의미축이다.
- 개발자용 CLI/API는 JSON/config 입력이 정당할 수 있다. 다만 공개 계약으로 문서화된 예제, 필드 의미, 오류 메시지가 있어야 하며, 문서화되지 않은 내부 shape 노출은 warning 또는 gap 으로 남긴다.

## Story Acceptance

story 단위는 가볍게 돈다. 핵심은 AC / PR / test evidence 연결을 넘어서, 핵심 AC별 동작 증거와 mock-only gap 을 구분하는 것이다.

호출:

```
Agent(subagent_type="product-acceptance", prompt="""
mode: STORY_ACCEPTANCE
검수 단위: <story issue 또는 stories.md story>
기준 문서:
- <docs/index.md>
- <docs/prd.md>
- <docs/epics/<epic>/stories.md>
- <관련 docs/decisions/ decision, impl/architecture 문서가 있으면>
구현 증거:
- <구현 PR 목록>
- <테스트/smoke/동작 증거: 타입검사/compile, 실데이터 통합 테스트, UI 자동화, API/CLI smoke 등>
- <mock/stub/fake 사용 범위와 실제 제품 경계 실행 여부>
- <대상 사용자와 핵심 입력/진행 동선: 제품 언어인지, 내부 계약 조립을 요구하는지>
""")
```

판단 기대:

- story 목적과 구현 PR 이 연결됐는가.
- story AC / REQ 가 구현 파일, 테스트, smoke 증거 중 하나 이상과 연결됐는가.
- 핵심 AC 가 동작 증거와 연결됐는가, 아니면 mock-only green 인가.
- 핵심 AC 가 대상 사용자에게 적합한 입력/진행 동선으로 닫혔는가, 아니면 내부 계약 조립을 요구하는가.
- 설명만 있고 검수 가능한 증거가 없는 항목과 mock-only 증거만 있는 항목이 gap 으로 드러나는가.
- 정적 타입검사/compile gate 부재가 무음 통과하지 않고 warning 또는 gap 으로 보고되는가.

## Epic Acceptance

epic 단위는 story보다 깊게 본다. 핵심은 PRD Must, cross-story gap, cross-PR/story 통합 동작 증거, security/ops risk 다.

호출:

```
Agent(subagent_type="product-acceptance", prompt="""
mode: EPIC_ACCEPTANCE
검수 단위: <epic issue 또는 epic stories.md>
기준 문서:
- <docs/prd.md>
- <docs/epics/<epic>/stories.md>
- <관련 docs/decisions/ decision, architecture/impl 문서>
구현 증거:
- <story별 구현 PR 목록>
- <story별 테스트/smoke/동작 증거>
- <cross-story 통합 동작 증거: 타입검사/compile, 실데이터 통합 테스트, UI 자동화, API/CLI smoke 등>
- <cross-story 사용자 입력/진행 동선: 대상 사용자에게 자연스러운 흐름인지>
""")
```

판단 기대:

- PRD Must 가 story/PR/test evidence 로 닫혔는가.
- story 사이 상태, 권한, 데이터 흐름이 어긋나 cross-story gap 을 만들지 않는가.
- 여러 PR/story 를 합쳤을 때 핵심 사용자 흐름이 동작 증거로 닫혔는가, 아니면 각 PR의 mock-only green만 남았는가.
- 여러 PR/story 를 합친 핵심 사용자 흐름이 내부 schema/payload 조립이 아니라 대상 사용자의 작업 언어로 진행되는가.
- security/ops risk 가 새로 생겼는데 후속 없이 묻히지 않았는가.

## 절차

1. 입력 단위가 story 인지 epic 인지 확인한다.
2. story면 `product-acceptance:STORY_ACCEPTANCE`, epic이면 `product-acceptance:EPIC_ACCEPTANCE` 를 호출한다.
3. `PASS`면 완료 후보로 보고한다.
4. `FAIL`이면 자동 수정하지 않고 gap 목록과 후속 분기를 prose 로 보고한다.
5. `ESCALATE`면 어떤 기준 문서, 구현 증거, 사용자 결정이 부족한지 보고하고 대기한다.

## 워크트리

`/acceptance` 는 read-only 검수 skill 이므로 워크트리 자동 진입 없음. GitHub issue 생성, 코드 수정, PR 생성/머지는 수행하지 않는다.

## 참조

- 분기 규칙: [`acceptance-routing.md`](acceptance-routing.md)
- agent: [`agents/product-acceptance.md`](../../agents/product-acceptance.md)
- 공개 진입점: [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
- 용어 사전: [`docs/plugin/terms.md`](../../docs/plugin/terms.md)
