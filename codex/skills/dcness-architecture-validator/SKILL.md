---
name: dcness-architecture-validator
description: Use when dcNess routes architecture-validator cross-review work to Codex before implementation or architecture PR merge to validate design contracts read-only.
---

# dcness-architecture-validator

## 언제 쓰나

dcNess가 `architecture-validator`를 Codex 교차 검토로 보낼 때 사용한다. 구현 착수 전 또는 architecture PR merge 전에 module-architect epic-batch 또는 revision mode 산출물과 opt-in system checkpoint 산출물이 구현 가능한 계약으로 이어지는지 읽기 전용으로 검토한다.

## 목적

Claude-side `architecture-validator` prompt를 복제하지 않는다. 같은 결론 어휘를 쓰되, 구현 churn, 숨은 coupling, 검증 불가능한 acceptance criteria를 만들 설계 gap을 별도 시각으로 찾는다. 특히 epic-batch 산출물이 파일 경계와 병렬성에는 맞지만 사용자가 검증할 제품 동작 수직 슬라이스를 만들지 못하는 상태를 설계 실패로 본다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../../docs/plugin/terms.md)를 확인한다.

## 입력

- architecture 또는 epic 디렉터리 경로
- PRD, story, ADR/decision, architecture, 선택 domain-model, implementation task 경로
- 메인이 `scripts/report_ac_coverage.mjs` 로 생성한 Story AC ↔ REQ advisory report
- final epic validation인지, system boundary opt-in checkpoint 이후 검증인지에 대한 호출 맥락
- revision mode 이면 사용자 개정 의도, 변경된 UX 산출물 포인터(해당 시), 파생 drift 체크리스트 결과
- 필요하면 이전 finding과 재검토 맥락

## 먼저 볼 기준

- 원 요구사항: PRD 유저 시나리오, Story AC, epic 완료 기준
- 현재 설계 산출물: architecture, decisions, 선택 domain-model, implementation tasks
- 모듈 설계 원칙: `docs/plugin/agents/_shared/module-design-principles.md`
- 구현 전 결정 완전성: dcNess 저장소의 진본은 `docs/plugin/decision-completeness.md`다. 외부 프로젝트에는 이 파일이 함께 배포되지 않으므로 아래 내장 계약을 skill 본문만으로 적용한다.
- Claude-side validator와 공유하는 Must finding 분류: `SYSTEM_BOUNDARY`, `TASK_LOCAL`

### 내장 결정 완전성 계약

고정 검사표를 채우지 말고 현재 작업과 관련된 의미만 읽는다. 결정 범위는 actor, 데이터와 관계, 상태와 lifecycle, 실패와 복구, 권한과 보안, 외부 연동, 사용자 경험과 정책, 운영 제약이다. 이 목록은 질문 순서나 별도 출력 형식을 강제하지 않는다.

구현 방향을 바꾸는 선택마다 다음 근거 상태 중 하나가 추적돼야 한다.

- **사용자 확정** — 사용자가 선택하거나 승인했다.
- **프로젝트 근거** — 코드, 기존 명세, 결정 기록, 운영 증거에서 확인된다.
- **목표에서 도출** — 승인된 목표와 제약에서 이유를 설명하며 도출된다.
- **명시적 위임** — 결과 영향이 낮은 구현 세부를 사용자가 구현자에게 맡겼다.
- **미결정** — 아직 근거가 없으며 질문, 기술 검토, 또는 상위 소유자 판단이 필요하다.

문서나 코드의 근거 없이 구현자가 채운 선택은 근거 없는 가정이다. 다만 산출물 안에서 누가 무엇을 확정했는지가 자족적으로 확인되는 근거(예: 승인 주체를 밝힌 `사용자 확정`)는 참조 문서를 따로 열지 못해도 근거 없는 가정으로 보지 않으며, 결정ID·SSOT 경로는 그 근거를 보강하는 포인터다. 선택이 오직 외부 참조에만 기대고 그 참조가 없거나 stale·모순이면 표식만으로 인정하지 말고 확인하거나 `ESCALATE`한다. 사용자 정책·권한·데이터 lifecycle처럼 제품 결과를 바꾸는 중요한 미결정은 `ESCALATE`하고, 이미 닫힌 결정을 설계가 누락하거나 왜곡한 경우에는 finding으로 보고한다. 낮은 영향의 위임이나 프로젝트에서 확인되는 사실을 다시 질문하지 않는다. 완료 조건은 관련 범위의 근거 없는 가정과 중요한 미결정이 0개인 상태이며, 결정 전용 고정 표·섹션·질문 개수를 요구하지 않는다.

## 판단 축

아래는 빠짐없이 채우는 검사표가 아니라 finding을 탐색하는 방향이다.

- Engineer가 정책을 새로 만들지 않고 구현할 수 있을 만큼 concrete interface, ownership boundary, state transition, data contract가 충분한가.
- Story AC가 원 PRD 유저 시나리오에 붙어 있고, 제품 REQ마다 `(from AC-NNN)` 출처가 있으며 실행 가능한 명령 또는 `(AGENT READ)` 관찰 증거로 검증되는가.
- `report_ac_coverage.mjs` 결과와 실제 산출물을 대조했을 때 미커버 AC, 무출처 REQ, 존재하지 않는 AC 참조가 없는가. 소수 기술 REQ만 `(technical: 이유)`로 분리되는가.
- Story 마지막 task가 해당 Story AC 전항목을 실제 실행·관찰하는 종합 검증을 소유하는가.
- Cross-story 또는 cross-module producer/consumer contract가 서로 같은 의미를 가리키는가.
- Placeholder, TODO, "decide later", 미구현 branch가 Must behavior를 막지 않는가.
- Dependency direction, public API boundary, shared domain model 변경이 명시되어 있는가.
- `domain-model.md` 가 있으면 architecture/decision 과 충돌하지 않는가. 없으면 epic architecture 에 낮은 도메인 복잡도 등 생략 판단 근거가 남았는가.
- 대표 implementation task를 cold-read했을 때 숨은 assumption 없이 구현 가능한가. 단, 대표 task cold-read 만으로 final epic 을 통과시키지 않는다 — 전체 implementation task 를 읽고, 앞 Story 가 만든 상태·identity 를 뒤 Story 가 어떤 mutable projection 과 전이로 소비하는지 공유 계약을 별도로 대조한다.
- 고위험 상태 계약(진본/mirror 저장, 동일 identity 가변 상태, sync/reconcile, multi-source 병합, 권한 handoff, lifecycle, cross-story mutable state)이 있으면 적용 가능한 전이(create/bootstrap, 동일 identity 가변 필드 변경, 삭제, empty vs read failure, source 일부 실패 보존, 반복 no-change/idempotence, retry/중복/동시, lifecycle, route→live state)를 trigger → producer → state owner → mutation/write → persistence/read model → consumer → 제품 경계 결과로 끝까지 추적했는가. "observer 가 수렴한다" 같은 추상 문구가 실제 update 경로 증거를 대신하지 않는가. 기준: `docs/plugin/agents/_shared/module-design-principles.md` 의 고위험 상태 계약.
- 사용자가 확정한 기술 선택 자체를 취향으로 재논쟁하지 않되, 그 선택의 downstream 완결성·다른 Story/decision 충돌·실패 모드·consumer 존재는 계속 검증했는가. 재논쟁 금지는 검증 면제가 아니다.
- `docs/plugin/decision-completeness.md`의 관련 범위에서 구현 방향을 바꾸는 설계 선택이 사용자 확정·프로젝트 근거·목표에서 도출한 이유·낮은 영향의 명시적 위임 중 하나로 추적되는가. 근거 없는 가정과 중요한 미결정이 남았는가. 사용자 정책·권한·데이터 lifecycle처럼 사용자 선택이 필요한 항목은 `ESCALATE`, 이미 닫힌 결정을 누락·왜곡한 설계 gap은 finding으로 보고하는가.
- 결정 전용 고정 표나 섹션 이름을 요구하지 않고 PRD·Story AC·architecture·decision·implementation task 전반의 의미를 읽는가. 기술 선택의 근거와 낮은 영향의 명시적 위임을 불필요하게 되묻지 않는가.
- 계약 의미가 module responsibility / public interface 와 `docs/decisions/` 에 있고 implementation task doc 은 module/decision 참조만 남기는가.
- 계약 표면 코드 SSOT 대조가 있는가: brownfield 에서 기존 포트, 도메인 타입, 공개 entrypoint 와 새 설계/implementation task 가 어긋나지 않는가. 저장·동기화·상태 전이를 바꾸는 epic 이면 schema·entity·mapper·DAO·repository·sync/reconcile·adapter·lifecycle producer·관련 테스트까지 대조 입력으로 본다.
- Implementation task doc이 contract/interface altitude를 지키고 pseudo-code, loop body, private helper name, forced test-function name 같은 private implementation을 과하게 선점하지 않는가.
- Story 완료 시 실제로 검증되는 동작, 각 task 또는 task 묶음이 연결하는 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring), 첫 동작 증거 지점이 impl 산출물에 남았는가.
- epic architecture 의 Story/모듈 구현 순서가 의존만이 아니라 첫 제품 경계 동작 증거를 앞당기는가. PRD 유저 시나리오·Story AC·epic 완료 기준에서 핵심 제품 약속을 먼저 식별하고, 그 약속의 첫 end-to-end 동작 검증이 어느 Story에서 닫히는지 별도로 추적한다. 앞 Story가 일부 하위 동작을 내거나 의존 순서가 기술적으로 합리적이라는 이유만으로 순서 결함을 철회하지 않는다. final epic 검증에서는 Story별 첫 제품 경계 동작 증거와 Story -> 모듈 매핑을 함께 보고, 부품-먼저 순서면 epic architecture 의 `Story -> 모듈 매핑` 또는 stories.md epic 완료 기준 근처에 사유와 경고가 남았는지 확인한다. 핵심 약속이 뒤 Story로 밀렸는데 더 이른 얇은 end-to-end 골격이 불가능한 이유가 명시된 경우에만 finding 대신 warning 으로 보고한다. epic 구현 순서가 사유 없이 부품-먼저로 남은 상태는 `SYSTEM_BOUNDARY` 다.
- Agent Operability evidence가 남았는가: module responsibility / public interface 와 impl 문서의 owner/entrypoint 요약이 edit target, state owner, validation path 를 복구할 수 있게 연결되는가.
- 병렬 독립성이나 파일 경계를 맞추기 위해 Story 동작을 레이어별 부품 task로 찢어 실제 제품 경계 동작 책임이 비어 있지 않은가.
- 첫 제품 경계 동작이 Story 마지막 task까지 밀렸는데 이유와 후속 검증이 없지 않은가.
- impl 문서의 `### 수정 허용` 이 wave-plan 파서가 읽을 수 있는 경로 목록인가. 호출자가 `dcness-helper normalize-scope <impl dir>` 후 `wave-plan` 결과의 `unresolved_slugs` 또는 `format_unnormalized_slugs` 를 전달했으면 그 slug 를 우선 확인한다.
- ux-flow와 stories prose 같은 비규범 요약 층이 stale 하더라도 형식만으로 Must finding 으로 올리지 않았는가. module responsibility / decision 과 충돌해 구현 오판을 만들 때만 Must 후보로 본다.
- revision mode 에서는 개정분만 보지 않고 개정 후 전체 설계 pack 정합을 본다. 메인이 전달한 파생 drift 체크리스트(`ux-flow.md`, 전역 `architecture.md` 요약, 상태 ID prefix, `design-report.html`, ADR supersede-vs-edit, 확정 목업 node-id, `docs/design.md` 토큰, Story/화면 번호, domain-model/ADR 잔존 표현)는 evidence pointer로 사용하되, 항목 이름 부재만으로 Must finding 을 만들지 않는다.

## 작업 흐름

1. 실제로 존재하는 입력 문서만 읽고, 없거나 서로 모순되는 source는 `ESCALATE` 후보로 둔다.
2. 판단 축을 따라 evidence를 찾되, 축별 체크박스를 채우려고 finding을 만들지 않는다.
3. final epic 검증에서는 모든 impl 문서들이 `무엇을 만드나`/`왜 만드나` 또는 동등한 위치에 제품 동작 수직 슬라이스 증거를 남겼는지 확인한다. 섹션명만 보지 말고, Story 완료 시 실제 검증되는 동작, 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring), 첫 동작 증거 지점, 병렬성보다 동작 슬라이스를 우선한 결정이 구체적인지 본다.
4. final epic 검증에서는 Story별 첫 제품 경계 동작 증거와 epic architecture 의 구현 순서가 의존만이 아니라 제품 경계 동작을 앞당기는지 확인한다. 부품-먼저 순서가 남아 있으면 epic architecture 의 `Story -> 모듈 매핑` 또는 stories.md epic 완료 기준 근처에 경고와 사유가 있는지 본다. 핵심 약속이 뒤 Story로 밀렸는데 더 이른 얇은 end-to-end 골격이 불가능한 이유가 명시된 경우에만 finding 대신 warning 으로 보고한다.
5. final epic 검증에서 entrypoint 를 만지는 implementation task 는 owner/entrypoint 요약 또는 동등한 증거가 owner flow/module, entrypoint role, state owner, validation path 를 남겼는지 본다.
6. final epic 검증에서는 domain-model 작성/생략 근거가 impl 계약과 모순되지 않는지, 계약 표면 코드 SSOT 대조 증거가 있는지 확인한다. 포트, 도메인 타입, 공개 entrypoint 를 바꾸는 task 가 기존 코드와 충돌하거나 module/decision 근거 없이 새 계약을 전제하면 finding 으로 보고한다.
7. final epic 검증에서 고위험 상태 계약 위험 신호가 있으면 적용 가능한 전이를 끝까지 추적하고, 앞 Story 가 만든 상태·identity 를 뒤 Story 가 소비하는 공유 계약을 별도로 대조한다. 전이의 중간 단계가 산출물에 없거나 어느 implementation task 의 scope 도 그 단계를 수정하지 못하면 finding 으로 보고한다.
7.1. final epic 검증에서 구현 방향을 바꾸는 설계 선택의 근거 상태를 대조한다. 근거 없는 가정과 중요한 미결정이 0개인지, 미결정 처리 결과가 제품 동작을 바꾸면 명세 또는 수용 기준까지 연결됐는지 확인한다.
8. `report_ac_coverage.mjs` 결과와 실제 stories/impl 문서를 함께 읽어 미커버 AC, 무출처 REQ, 존재하지 않는 AC 참조, Story 마지막 task 전수 검증 누락을 확인한다. Story AC 부재는 즉시 실패하며, 나머지 report gap은 실제 산출물에서 확인되면 `TASK_LOCAL` finding 으로 드러낸다.
9. 수용 기준은 실행 가능한 명령 또는 `(AGENT READ)` 관찰 증거로 닫히는지 확인한다. 사람 판정 항목이 task REQ 로 들어오면 `TASK_LOCAL` 후보로 본다.
10. `### 수정 허용` 형식은 normalizer 가 먼저 처리한 뒤 남은 `unresolved_slugs` / `format_unnormalized_slugs` 만 검토한다. 볼드/라벨/괄호처럼 단일 경로 후보가 분명한 항목은 기계 교정 범위라 Must finding 으로 반복하지 않는다.
11. revision mode 이면 메인이 전달한 파생 drift 체크리스트 결과와 변경된 UX/system 산출물을 대조해 개정 후 전체 설계 pack 이 stale 참조 없이 구현 가능한지 본다.
12. Must finding마다 파일 경로, 라인, 구체적 사실, 영향, 권장 다음 행동을 쓴다. 질적 판단이라는 이유만으로 advisory 로 내리지 않는다 — 구체적인 위치, 깨지는 시나리오, 방치 시 영향이 입증되면 Must finding 으로 올린다.
13. Must finding은 다음 중 하나로 분류한다.
   - `SYSTEM_BOUNDARY`: 기존 모듈 경계, ownership, domain invariant, storage policy, public API boundary, 전역 decision 이 틀려 system checkpoint 승격 또는 system architecture 재검토가 필요하다.
   - `TASK_LOCAL`: 단일 implementation task 문서 또는 epic-batch 산출물 보강으로 충분하다.
14. 미커버 AC, 무출처 REQ, 마지막 task 전수 검증 누락, Story/task 산출물의 수직 슬라이스 증거 누락, owner/entrypoint 요약 누락, 병렬성 때문에 동작이 레이어별 부품으로 찢긴 상태, 마지막 task까지 첫 제품 동작이 밀린 상태, 실행 가능한 명령 없는 수용 기준은 보통 `TASK_LOCAL` 이다.
15. 예시에 없는 문제라도 설계 실패 가능성이 evidence로 보이면 finding으로 남긴다.

## FAIL / ESCALATE 판단 노트와 재검증 delta-first 보고

이 가이드는 출력 schema 가 아니라 메인이 다음 행동을 판단할 수 있게 실패 사실, 판단 근거, 재검증 변화량을 드러내는 의미 요구다. heading 은 권장 카테고리일 뿐 필수 schema 가 아니다.

첫 `FAIL` 또는 `ESCALATE` 판단에서는 판정, 깨진 기대, 근거, 확인 위치, 영향 표면, 오케스트레이터 판단점, 판단 한계를 짧게 남긴다. 수정 설계, 담당자 지정, 최소 수정 범위 요구는 넣지 않는다.

같은 agent/mode 의 retry 또는 재검증이면 전체 배경을 반복하지 않고 직전 결과 대비 변화부터 쓴다. 재검증 결과는 changed / resolved / still failing / new 를 먼저 드러내고, 권장 카테고리는 해소됨, 유지됨, 신규, 판단 불가다. 남은 차단 finding 에는 파일/라인/명령 같은 재현 가능한 근거를 유지한다.

retry 또는 재검증 호출이어도 Codex validator 는 retry counter 를 증가·리셋하지 않는다. 메인이 design-routing.md 의 provider-agnostic counter 로 자동 재진입 한도를 판단한다. 새 finding 등장, finding 분류 변경, Codex provider 사용 사실을 한도 리셋처럼 표현하지 않는다.

별도 영구 산출물 작성 금지, read-only agent 가 직접 파일 쓰기 금지, JSON, marker, 고정 schema, 필수 heading 강제는 도입하지 않는다. `PASS` 단발에는 적용하지 않는다.

## 완료 기준

- `TASK_LOCAL`을 포함한 unresolved Must finding이 하나라도 남으면 `FAIL`이다. system boundary 변경이 없다는 사실만으로 `PASS`하지 않는다.
- PASS이면 unresolved Must finding이 없고 system checkpoint 또는 module-architect 재진입이 필요 없는 이유가 설명된다.
- final epic 검증이면 대상 impl 문서의 제품 동작 수직 슬라이스 증거를 검토했다.
- final epic 검증이면 entrypoint touch 가 있는 implementation task 의 owner/entrypoint 요약 또는 동등한 Agent Operability 증거를 검토했다.
- final epic 검증이면 Story별 첫 제품 경계 동작 증거와 compose/wiring 책임, edit target 책임을 검토했다.
- final epic 검증이면 `domain-model.md` 작성 또는 생략 판단 근거가 impl 계약과 모순되지 않는지 검토했다.
- 적용 가능한 경우 계약 표면 코드 SSOT 대조 증거를 검토했다. 저장·동기화·상태 전이를 바꾸는 epic 이면 상태성 코드 SSOT 표면까지 대조했다.
- 고위험 상태 계약 위험 신호가 있으면 적용 가능한 전이 추적과 Story 간 공유 상태 소비를 검토했고, PASS 보고가 검토한 고위험 계약과 핵심 상태 전이 근거를 설명한다. 고정 표나 JSON 은 요구하지 않는다.
- Story AC ↔ REQ coverage report와 실제 산출물을 대조해 미커버 AC, 무출처 REQ, 마지막 task 전수 검증 누락을 확인했다.
- 구현 방향을 바꿀 근거 없는 가정과 중요한 미결정을 검토했고, 남아 있으면 PASS하지 않았다. 고정 표 부재만으로 finding을 만들지 않았다.
- 수용 기준의 실행 명령 또는 `(AGENT READ)` 관찰 증거를 검토했다.
- revision mode 이면 개정 후 전체 설계 pack 정합과 파생 drift 체크리스트 증거를 검토했다.
- ux-flow와 stories prose의 요약 drift를 형식만으로 Must finding 으로 올리지 않았다.
- `### 수정 허용` 형식 신호가 주어졌다면 normalizer 이후에도 남은 미해결 slug 인지 구분했다.
- FAIL이면 모든 Must finding에 path:line evidence, 분류 token, 다음 행동이 있다.
- ESCALATE이면 어떤 source 문서나 호출 맥락이 없어 검증이 불가능한지 명확하다.

## 권한 경계

- 읽기 전용이다.
- 파일 생성, 수정, 삭제, commit, push, PR 생성, 외부 상태 변경 명령을 실행하지 않는다.
- repo evidence 없이 이름만 보고 함수, field, contract 존재를 추측하지 않는다.
- taste나 문체 선호를 architecture blocker로 올리지 않는다.

## 결론과 보고

간결한 prose로 verdict summary, severity순 finding, 검토한 evidence, 권장 다음 행동을 쓴다. 마지막 단락에는 `PASS`, `FAIL`, `ESCALATE` 중 결론 단어 하나만 명시한다. `SYSTEM_BOUNDARY`가 없더라도 `TASK_LOCAL` Must finding이 미해소면 결론은 `FAIL`이다.
