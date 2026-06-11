---
name: acceptance
description: story 또는 epic 구현 완료 후 제품 단위 검수를 수행하는 MVP skill. 사용자가 "/acceptance story", "/acceptance epic", "story 검수", "epic 검수", "AC 기준으로 완료됐는지 봐줘" 등을 말할 때 사용한다. full E2E 검증은 MVP 범위 밖이며, Lite `/impl` 단발 작업에 자동 강제하지 않는다.
---

# Acceptance Skill — story/epic 제품 검수 MVP

`/acceptance` 는 PR 하나의 코드 리뷰가 아니라 제품 단위 완료 여부를 확인하는 검수 skill 이다. MVP 에서는 story / epic 검수만 다룬다.

> 🔴 **라우팅 SSOT** — `product-acceptance` 결론(`PASS` / `FAIL` / `ESCALATE`) → 다음 행동은 [`acceptance-routing.md`](acceptance-routing.md) 가 본 skill 의 단일 진본이다. 본 파일은 입력 정형화와 진행 절차만 담는다.

> `/impl-loop` 는 story/epic 마감 task 의 머지 *전* 에 같은 `product-acceptance` agent 로 inline 검수를 돈다 — 그 경로의 라우팅(gap 수정 루프 포함)은 [`impl-loop-routing.md` 마감 acceptance 라우팅](../impl-loop/impl-loop-routing.md#마감-acceptance-라우팅) 이 소유하고, 본 skill 의 prompt 규약(아래 Story/Epic Acceptance 호출 형식)만 재사용한다.

## Inputs

메인이 사용자에게 받거나 직접 확인해야 할 입력:

- 검수 단위: `story` 또는 `epic`
- story issue 또는 epic issue
- PRD/stories path
- 구현 PR 목록
- 있으면 테스트 결과, smoke 결과, 화면/API/CLI 동작 증거
- 이전 acceptance gap 이 있으면 그 결과와 재검수 대상

입력이 부족하면 추측으로 검수하지 않고 사용자에게 어떤 경로/PR/issue 가 필요한지 묻는다.

## 비대상

- 새 spec 작성 또는 PRD 변경 → `/spec`
- 설계 산출물 작성/수정 → `/design`
- 구현 자체 → `/impl`
- GitHub issue 초안/등록 → `/to-issue`
- release readiness, 배포, migration, full E2E 검증 → MVP 범위 밖. 후속 release/product acceptance 고도화에서 다룬다.

Lite `/impl` 단발 작업은 불필요하게 `/acceptance` 로 강제하지 않는다. 파일/symbol이 명확한 작은 수정은 기존 test + pr-reviewer + CI gate 로 끝날 수 있다.

## Story Acceptance

story 단위는 가볍게 돈다. 핵심은 AC / PR / test evidence 연결이다.

호출:

```
Agent(subagent_type="product-acceptance", prompt="""
mode: STORY_ACCEPTANCE
검수 단위: <story issue 또는 stories.md story>
기준 문서:
- <PRD/stories path>
- <관련 impl/architecture 문서가 있으면>
구현 증거:
- <구현 PR 목록>
- <테스트/smoke/동작 증거>
""")
```

판단 기대:

- story 목적과 구현 PR 이 연결됐는가.
- story AC / REQ 가 구현 파일, 테스트, smoke 증거 중 하나 이상과 연결됐는가.
- 설명만 있고 검수 가능한 증거가 없는 항목이 gap 으로 드러나는가.

## Epic Acceptance

epic 단위는 story보다 깊게 본다. 핵심은 PRD Must, cross-story gap, security/ops risk 다.

호출:

```
Agent(subagent_type="product-acceptance", prompt="""
mode: EPIC_ACCEPTANCE
검수 단위: <epic issue 또는 epic stories.md>
기준 문서:
- <docs/prd.md>
- <epic stories.md>
- <관련 architecture/impl 문서>
구현 증거:
- <story별 구현 PR 목록>
- <테스트/smoke/동작 증거>
""")
```

판단 기대:

- PRD Must 가 story/PR/test evidence 로 닫혔는가.
- story 사이 상태, 권한, 데이터 흐름이 어긋나 cross-story gap 을 만들지 않는가.
- security/ops risk 가 새로 생겼는데 후속 없이 묻히지 않았는가.

## 절차

1. 입력 단위가 story 인지 epic 인지 확인한다.
2. story면 `product-acceptance:STORY_ACCEPTANCE`, epic이면 `product-acceptance:EPIC_ACCEPTANCE` 를 호출한다.
3. `PASS`면 완료 후보로 보고한다.
4. `FAIL`이면 자동 수정하지 않고 gap 목록과 후속 라우팅을 prose 로 보고한다.
5. `ESCALATE`면 어떤 기준 문서, 구현 증거, 사용자 결정이 부족한지 보고하고 대기한다.

## 워크트리

`/acceptance` 는 read-only 검수 skill 이므로 워크트리 자동 진입 없음. GitHub issue 생성, 코드 수정, PR 생성/머지는 수행하지 않는다.

## 참조

- 라우팅: [`acceptance-routing.md`](acceptance-routing.md)
- agent: [`agents/product-acceptance.md`](../../agents/product-acceptance.md)
- public surface: [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
