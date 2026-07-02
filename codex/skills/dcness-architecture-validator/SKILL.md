---
name: dcness-architecture-validator
description: Use when dcNess routes architecture-validator cross-review work to Codex before implementation or architecture PR merge to validate design contracts read-only.
---

# dcness-architecture-validator

## 언제 쓰나

dcNess가 `architecture-validator`를 Codex 교차 검토로 보낼 때 사용한다. 구현 착수 전 또는 architecture PR merge 전에 system/module 설계 산출물이 구현 가능한 계약으로 이어지는지 읽기 전용으로 검토한다.

## 목적

Claude-side `architecture-validator` prompt를 복제하지 않는다. 같은 결론 어휘를 쓰되, 구현 churn, 숨은 coupling, 검증 불가능한 acceptance criteria를 만들 설계 gap을 별도 시각으로 찾는다. 특히 epic-batch 산출물이 파일 경계와 병렬성에는 맞지만 사용자가 검증할 제품 동작 수직 슬라이스를 만들지 못하는 상태를 설계 실패로 본다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../../docs/plugin/terms.md)를 확인한다.

## 입력

- architecture 또는 epic 디렉터리 경로
- PRD, story, ADR, architecture, 선택 domain-model, implementation task 경로
- 첫 architecture validation인지, module 산출 이후 final validation인지에 대한 호출 맥락
- 필요하면 이전 finding과 재검토 맥락

## 먼저 볼 기준

- 원 요구사항: PRD, story, acceptance criteria
- 현재 설계 산출물: architecture, ADR, 선택 domain-model, implementation tasks
- 모듈 설계 원칙: `agents/_shared/module-design-principles.md`
- Claude-side validator와 공유하는 분기 분류: `SYSTEM_BOUNDARY`, `CONTRACT_PROPAGATION`, `TASK_LOCAL`

## 판단 축

아래는 빠짐없이 채우는 검사표가 아니라 finding을 탐색하는 방향이다.

- Engineer가 정책을 새로 만들지 않고 구현할 수 있을 만큼 concrete interface, ownership boundary, state transition, data contract가 충분한가.
- Acceptance criteria가 원 PRD/story intent에 붙어 있는가, 아니면 문서끼리만 self-consistent하고 원 요구와 어긋났는가.
- Cross-story 또는 cross-module producer/consumer contract가 서로 같은 의미를 가리키는가.
- Placeholder, TODO, "decide later", 미구현 branch가 Must behavior를 막지 않는가.
- Dependency direction, public API boundary, shared domain model 변경이 명시되어 있는가.
- 대표 implementation task를 cold-read했을 때 숨은 assumption 없이 구현 가능한가.
- Contract Ledger가 signature만이 아니라 invariant, ordering, error mode, config, forbidden alternative까지 담는가.
- 계약 표면 코드 SSOT 대조가 있는가: brownfield 에서 기존 포트, 도메인 타입, 공개 entrypoint 와 새 설계/implementation task 가 어긋나지 않는가.
- Implementation task doc이 contract/interface altitude를 지키고 pseudo-code, loop body, private helper name, forced test-function name 같은 private implementation을 과하게 선점하지 않는가.
- Story 완료 시 실제로 검증되는 동작, 각 task 또는 task 묶음이 연결하는 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring), 첫 동작 증거 지점이 impl 산출물에 남았는가.
- Agent Operability evidence가 남았는가: epic architecture 의 Flow Ownership Map 과 impl 문서의 Agent Workability 가 edit target, state owner, validation path 를 복구할 수 있게 연결되는가.
- 병렬 독립성이나 파일 경계를 맞추기 위해 Story 동작을 레이어별 부품 task로 찢어 실제 제품 경계 동작 책임이 비어 있지 않은가.
- 첫 제품 경계 동작이 Story 마지막 task까지 밀렸는데 이유와 후속 검증이 없지 않은가.
- epic architecture 의 Story/모듈 구현 순서가 의존만이 아니라 첫 제품 경계 동작 증거를 앞당기는가. 부품을 다 만든 뒤에야 처음 동작하는 순서가 사유·경고 없이 남아 있지 않은가.
- impl 문서의 `### 수정 허용` 이 wave-plan 파서가 읽을 수 있는 경로 목록인가. 호출자가 `dcness-helper normalize-scope <impl dir>` 후 `wave-plan` 결과의 `unresolved_slugs` 또는 `format_unnormalized_slugs` 를 전달했으면 그 slug 를 우선 확인한다. normalizer 가 고칠 수 있는 볼드/라벨/괄호 설명은 finding 이 아니라 기계 교정 영역이다. normalizer 이후에도 경로가 없거나 여러 경로/산문이 섞여 남은 task 만 `TASK_LOCAL` finding 으로 드러낸다.

## 작업 흐름

1. 실제로 존재하는 입력 문서만 읽고, 없거나 서로 모순되는 source는 `ESCALATE` 후보로 둔다.
2. 판단 축을 따라 evidence를 찾되, 축별 체크박스를 채우려고 finding을 만들지 않는다.
3. system 단위(1차) 검증에서는 epic architecture 의 구현 순서가 첫 제품 경계 동작 증거를 앞당기는지, 부품-먼저 순서면 epic architecture 의 `구현 순서` 섹션 또는 stories.md epic 완료 기준 근처에 사유와 경고가 남았는지 확인한다. 사유가 기록돼 있으면 finding 대신 warning 으로 보고한다.
4. system 단위(1차) 검증에서는 새 mode/screen/panel/API/CLI/pipeline flow 가 있으면 epic architecture 의 Flow Ownership Map 에 owner module, entrypoint touch, state owner, validation path 가 남았는지 본다.
5. final epic 검증에서는 모든 impl 문서들이 `Story 동작 슬라이스` 또는 동등한 증거를 남겼는지 확인한다. 섹션명만 보지 말고, Story 완료 시 실제로 검증되는 동작, 제품 경계, 첫 동작 증거 지점, 병렬성보다 동작 슬라이스를 우선한 결정이 구체적인지 본다.
6. final epic 검증에서 entrypoint 를 만지는 implementation task 는 `Agent Workability` 또는 동등한 증거가 owner flow/module, entrypoint role, state owner, allowed touch, forbidden touch, validation path, future change scenario 를 남겼는지 본다.
7. final epic 검증에서는 Story별 첫 제품 경계 동작 증거와 Flow Ownership Map 을 한 번 더 훑어, 여러 task/story가 합쳐질 때 사용자에게 약속한 흐름의 edit target 과 검증 책임이 비어 있지 않은지 확인한다.
8. final epic 검증에서는 계약 표면 코드 SSOT 대조 증거를 확인한다. 포트, 도메인 타입, 공개 entrypoint 를 바꾸는 task 가 기존 코드와 충돌하거나 Contract Ledger/decision 근거 없이 새 계약을 전제하면 finding 으로 보고한다.
9. `### 수정 허용` 형식은 normalizer 가 먼저 처리한 뒤 남은 `unresolved_slugs` / `format_unnormalized_slugs` 만 검토한다. 볼드/라벨/괄호처럼 단일 경로 후보가 분명한 항목은 기계 교정 범위라 Must finding 으로 반복하지 않는다.
10. Must finding마다 파일 경로, 라인, 구체적 사실, 영향, 권장 다음 행동을 쓴다.
11. Must finding은 다음 중 하나로 분류한다.
   - `SYSTEM_BOUNDARY`: 상위 boundary, ownership, domain invariant가 틀려 system architecture 재검토가 필요하다.
   - `CONTRACT_PROPAGATION`: 결정은 맞지만 architecture/domain/ADR/impl 문서 사본이 stale해 targeted sync가 필요하다.
   - `TASK_LOCAL`: 단일 implementation task 문서만 잘못되어 해당 task 수정으로 충분하다.
12. Story/task 산출물의 수직 슬라이스 증거 누락, Agent Workability 누락, 병렬성 때문에 동작이 레이어별 부품으로 찢긴 상태, 마지막 task까지 첫 제품 동작이 밀린 상태는 보통 `TASK_LOCAL` 이다. epic 구현 순서가 사유 없이 부품-먼저로 남은 상태는 `SYSTEM_BOUNDARY` 다. Flow Ownership Map 누락도 `SYSTEM_BOUNDARY` 다.
13. 예시에 없는 문제라도 설계 실패 가능성이 evidence로 보이면 finding으로 남긴다.

## FAIL / ESCALATE 판단 노트와 재검증 delta-first 보고

이 가이드는 출력 schema 가 아니라 메인이 다음 행동을 판단할 수 있게 실패 사실, 판단 근거, 재검증 변화량을 드러내는 의미 요구다. heading 은 권장 카테고리일 뿐 필수 schema 가 아니다.

첫 `FAIL` 또는 `ESCALATE` 판단에서는 판정, 깨진 기대, 근거, 확인 위치, 영향 표면, 오케스트레이터 판단점, 판단 한계를 짧게 남긴다. 수정 설계, 담당자 지정, 최소 수정 범위 요구는 넣지 않는다.

같은 agent/mode 의 retry 또는 재검증이면 전체 배경을 반복하지 않고 직전 결과 대비 변화부터 쓴다. 재검증 결과는 changed / resolved / still failing / new 를 먼저 드러내고, 권장 카테고리는 해소됨, 유지됨, 신규, 판단 불가다. 남은 차단 finding 에는 파일/라인/명령 같은 재현 가능한 근거를 유지한다.

별도 영구 산출물 작성 금지, read-only agent 가 직접 파일 쓰기 금지, JSON, marker, 고정 schema, 필수 heading 강제는 도입하지 않는다. `PASS` 단발에는 적용하지 않는다.

## 완료 기준

- PASS이면 system-architect 또는 module-architect 재진입이 필요 없는 이유가 설명된다.
- system 단위(1차) 검증이면 epic architecture 의 구현 순서가 첫 제품 경계 동작 증거를 앞당기는지 검토했다.
- system 단위(1차) 검증이면 Flow Ownership Map 이 필요한 flow owner, state owner, validation path 를 담는지 검토했다.
- final epic 검증이면 대상 impl 문서의 제품 동작 수직 슬라이스 증거를 검토했다.
- final epic 검증이면 entrypoint touch 가 있는 implementation task 의 Agent Workability 증거를 검토했다.
- final epic 검증이면 Story별 첫 제품 경계 동작 증거와 compose/wiring 책임, edit target 책임을 검토했다.
- 적용 가능한 경우 계약 표면 코드 SSOT 대조 증거를 검토했다.
- `### 수정 허용` 형식 신호가 주어졌다면 normalizer 이후에도 남은 미해결 slug 인지 구분했다.
- FAIL이면 모든 Must finding에 path:line evidence, 분류 token, 다음 행동이 있다.
- ESCALATE이면 어떤 source 문서나 호출 맥락이 없어 검증이 불가능한지 명확하다.

## 권한 경계

- 읽기 전용이다.
- 파일 생성, 수정, 삭제, commit, push, PR 생성, 외부 상태 변경 명령을 실행하지 않는다.
- repo evidence 없이 이름만 보고 함수, field, contract 존재를 추측하지 않는다.
- taste나 문체 선호를 architecture blocker로 올리지 않는다.

## 결론과 보고

간결한 prose로 verdict summary, severity순 finding, 검토한 evidence, 권장 다음 행동을 쓴다. 마지막 단락에는 `PASS`, `FAIL`, `ESCALATE` 중 결론 단어 하나만 명시한다.
