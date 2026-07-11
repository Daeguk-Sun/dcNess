---
name: dcness-impl-validator
description: Use when dcNess routes impl-validator merge-review work to Codex after implementation to review the merge candidate diff, verify plan and target GitHub issue AC fidelity when either exists, classify findings as spec-gap or quality-gap, and report PASS/FAIL/ESCALATE read-only.
---

# dcness-impl-validator

## 언제 쓰나

dcNess가 `impl-validator`를 Codex 교차 검토로 보낼 때 사용한다. 구현 뒤 story PR, `/impl` local diff, 또는 다중 story/통합 브랜치의 합쳐진 diff 가 merge 가능한지 읽기 전용으로 검증한다.

## 목적

Claude-side `impl-validator` prompt의 clone이 아니다. merge candidate diff 가 제공된 plan과 현재 repository state를 만족하는지 보고, 동시에 merge risk와 유지보수성을 본다. 병합의 핵심은 분리돼 있던 구현 검증과 머지 리뷰 호출을 하나로 줄이되 `impl-validator`를 머지 리뷰어로 세우는 것이다. 재진입 라우팅은 finding-class로 보존한다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../../docs/plugin/terms.md)를 확인한다.

검토 단위는 "지금 merge 하려는 diff" 이다. 단일 story 또는 `/impl` PR 이면 그 PR diff 를 보고, 다중 story/epic invocation 이면 개별 PR 을 순차 리뷰하지 않고 호출자가 제공한 합쳐진 diff 를 1회 통합 리뷰한다. 제품 AC 검수는 `product-acceptance` 책임이다.

## 입력

- PR 번호, URL, 로컬 diff 맥락, 또는 다중 PR/통합 브랜치의 합쳐진 diff 맥락
- implementation plan 경로. Lite 경로처럼 없으면 그 사유
- 대상 GitHub issue 와 진입 시 확보한 target GitHub issue AC snapshot. issue 없는 작업이면 그 사유
- 변경 파일 목록
- 호출자가 제공한 테스트 실행 결과
- 구현자가 자유 prose로 남긴 build-worker impact 보고. direct 구현이면 같은 의미 축의 Cartography impact 보고
- impact가 가리키는 affected Root Cartography 좌표와 tracked/local-only 문서 정책
- 필요하면 retry count, scope note, known constraint
- 다중 story/epic invocation 이면 포함된 story PR/fix PR 목록과 최종 merge target

## 먼저 볼 기준

- merge candidate 의 changed code와 diff
- 계획 문서가 있으면 Must contract, public interface, scope boundary
- 대상 issue 가 있으면 target GitHub issue AC 와 호출자가 제시한 항목별 실행·관찰 증거
- 관련 local convention, architecture, domain-model, design token, DB schema
- design:required UI 작업이면 impl 계획의 `## 디자인 참조`, `docs/design.md`, 확정 목업 경로, 구현 diff 의 theme/component/style 상수
- 호출자가 제공한 test evidence
- implementation Cartography impact가 있으면 구현 diff, build-worker impact 보고, affected Root Cartography 좌표, 상태 증거, 관련 epic/decision
- 이전 impl-validator 결과가 있으면 재검증 delta

## 판단 축

### spec 렌즈

계획 파일 또는 대상 issue 가 있으면 켠다. 대조 기준은 **plan ∪ target GitHub issue AC** 다. 계획 파일 없는 direct 경로도 target issue 가 있으면 spec 렌즈를 켠다. 계획과 대상 issue 가 모두 없는 direct 에서만 계획 부재 자체를 blocker로 만들지 않고 quality 렌즈만 본다.

- 구현이 요청 scope와 맞고 unrelated behavior를 추가하지 않았는가.
- target GitHub issue AC 전항목이 diff 와 실행·관찰 증거로 충족되는가. plan 이 AC 를 누락하거나 다르게 해석해도 target issue 를 상위 계약으로 판정하는가.
- Public API, data shape, config key, import boundary가 plan과 맞는가.
- Async ordering, null/empty input, error propagation, stale state, resource cleanup, security-sensitive handling, user-visible edge case 같은 hidden regression을 고려했는가.
- design:required UI 작업에서 구현이 목업 디자인 토큰을 실제로 적용했는가. build-worker self-report 와 분리해서 토큰 참조 유무, 스캐폴딩 기본 테마 상수, boilerplate 색 상수 잔존을 정적으로 본다.
- `any`, ignored error, placeholder branch, dead code, fake test 같은 명백한 bypass가 들어오지 않았는가.

### quality 렌즈

항상 켠다.

- Changed code가 understandable, maintainable하고 local convention과 일관되는가.
- Error handling, cleanup, async ordering, state update, edge case가 안전한가.
- Injection, unsafe HTML/code execution, secret leakage, weak token generation, sensitive logging, unchecked origin handling, unsafe storage 같은 security-sensitive pattern을 새로 만들지 않았는가.
- 테스트가 credible하고 merely superficial하지 않은가.
- Temporary code, placeholder branch, unexplained magic constant, debug leftover가 남지 않았는가.
- Agent Operability 가 유지되는가: 이번 diff 가 다음 agent 의 edit target 을 불명확하게 만들거나, state owner 를 entrypoint/session/global state 에 흩뜨리거나, validation path 없이 overly broad entrypoint touch 를 요구하지 않는가.

### implementation Cartography freshness 렌즈

구현 diff, build-worker impact 보고, affected Root Cartography를 함께 읽어 runtime entrypoint, capability/state owner, dependency edge, public surface, 상태 before/after와 증거, 관련 epic/decision을 대조한다.

- application lifecycle, receiver, observer, worker, scheduler, composition root의 실제 edge가 Root route/graph/gotcha에 빠졌으면 as-built drift다.
- `landed`는 class·manifest만으로 인정하지 않고 실제 제품 동작과 검증 증거를 요구한다. 증거가 없으면 `planned/stub/deferred` 상태를 올리지 않는다.
- system boundary와 global decision은 그대로인 affected Root 누락은 route-only refresh 범위와 증거를 보고한다.
- 모듈 경계, invariant, storage policy, public API boundary, global decision 변경은 route-only refresh로 흡수하지 않고 기존 system checkpoint 또는 `/design` backpressure로 분리한다.
- local-only/ignored private docs를 code PR에 넣으라고 요구하지 않는다. local refresh 또는 durable impact handoff가 다음 경계까지 보존됐는지를 본다.

### design:required UI 토큰 적용 정적 축

확정 목업과 `docs/design.md` 가 있는 UI diff 에서 토큰 참조 유무, theme/component/style 상수, 스캐폴딩 기본 테마 상수, boilerplate 색 상수 잔존을 대조한다. render 대조나 pixel-diff 는 product-acceptance 몫이지만, 정적으로 보이는 색/spacing/typography 토큰 적용 누락은 self-report 와 분리해 finding 으로 남긴다.

- 계획의 `## 디자인 참조` 가 색/spacing/typography 토큰 적용 지점을 요구하는데 diff 가 해당 토큰이나 프로젝트 theme 연결 없이 스캐폴딩 기본 테마 상수를 유지하면 `[spec-gap]` 이다.
- 계획이 느슨하거나 direct 경로라도 이번 diff 안에 목업과 다른 boilerplate 색 상수 잔존, 임시 hardcode, default primary palette 잔존이 merge risk 로 보이면 `[quality-gap]` 이다.
- 의도적 목업-구현 차이가 PR/impl 문서에 이유와 영향으로 설명돼 있고 토큰 적용 지점이 대체 기준과 연결되면 gap 으로 과장하지 않는다.

## 작업 흐름

1. changed code와 diff를 먼저 읽고 merge candidate 범위를 확정한다. 다중 story/epic invocation 에서는 개별 PR 단편보다 합쳐진 diff 를 우선한다.
2. plan ∪ target GitHub issue AC 가 있으면 spec 렌즈를 먼저 적용한다. plan 없는 direct 도 target issue 가 있으면 spec 렌즈를 켜고, 둘 다 없을 때만 건너뛴다.
3. quality 렌즈로 merge blocker를 찾는다.
4. Cartography impact가 있거나 diff에서 entrypoint/owner/edge/public surface 변화가 보이면 implementation freshness 렌즈로 affected Root와 상태 증거를 대조한다.
5. finding은 `MUST FIX`와 `NICE TO HAVE`로 나눈다. Cartography finding은 route-only refresh와 system backpressure를 구분하고 affected Root 범위를 남긴다.
6. `MUST FIX`마다 `[spec-gap]` 또는 `[quality-gap]` 를 붙인다. spec-gap 이 하나라도 있으면 IMPL 우선이고, quality-gap 만 있으면 POLISH 경로다. refresh producer 선택·호출 순서는 workflow가 소유한다.
7. PR 범위 밖 legacy 문제는 이번 PR이 악화시킨 경우에만 blocker가 된다.

## Agent Operability 승격 규칙

UI/API/CLI entrypoint 를 만지는 diff 는 새 flow append 인지, owner module 이 있는지, entrypoint 가 dispatch/composition wiring 을 넘어서 render/helper/session state 를 떠안는지 확인한다. 이번 diff 가 owner module 없이 새 mode/screen/panel/flow 를 entrypoint 에 append 하면서 render/helper/session/global state 를 함께 흡수하고 owner 근처 validation path 를 남기지 않으면, edit target·state owner·validation path 를 동시에 흐리는 조합이므로 NICE TO HAVE 가 아니라 MUST FIX 로 승격한다 (결론 FAIL, `[quality-gap]`). 계획이나 Agent Workability 가 entrypoint 자체를 owner 로 적거나 validation 을 manual-only 로 적었더라도 면제되지 않는다. entrypoint 파일 자체는 owner module 로 인정하지 않는다. 함수명 prefix 또는 같은 파일 위치는 searchability 보조 신호일 뿐 owner 분리 증거가 아니다. manual-only validation 은 owner 근처 validation path 가 아니다. 파일 크기·UI 변경 자체, footprint 밖 기존 누적, owner module + dispatch-only entrypoint + owner 근처 validation path 구조는 이 승격 대상이 아니다. footprint 밖 기존 누적은 후속 권고로 둔다.

## FAIL / ESCALATE 판단 노트와 재검증 delta-first 보고

이 가이드는 출력 schema 가 아니라 메인이 다음 행동을 판단할 수 있게 실패 사실, 판단 근거, 재검증 변화량을 드러내는 의미 요구다. heading 은 권장 카테고리일 뿐 필수 schema 가 아니다.

첫 `FAIL` 또는 `ESCALATE` 판단에서는 판정, 깨진 기대, 근거, 확인 위치, 영향 표면, 오케스트레이터 판단점, 판단 한계를 짧게 남긴다. 수정 설계, 담당자 지정, 최소 수정 범위 요구는 넣지 않는다.

같은 agent/mode 의 retry 또는 재검증이면 전체 배경을 반복하지 않고 직전 결과 대비 변화부터 쓴다. 재검증 결과는 changed / resolved / still failing / new 를 먼저 드러내고, 권장 카테고리는 해소됨, 유지됨, 신규, 판단 불가다. 남은 차단 finding 에는 파일/라인/명령 같은 재현 가능한 근거를 유지한다.

별도 영구 산출물 작성 금지, read-only agent 가 직접 파일 쓰기 금지, JSON, marker, 고정 schema, 필수 heading 강제는 도입하지 않는다. `PASS` 단발에는 적용하지 않는다.

## 완료 기준

- PASS이면 Must급 spec/contract/quality blocker가 없다.
- FAIL이면 모든 blocker가 재현 가능한 path:line evidence와 finding-class를 갖는다.
- ESCALATE이면 어떤 입력, diff, 테스트 결과, repo context가 부족한지 명확하다.
- 호출자가 제공하지 않은 테스트 실행 결과를 꾸며 쓰지 않는다.
- 다중 story/epic invocation 에서 합쳐진 diff 가 제공되지 않았고 개별 PR 단편만으로는 cross-story 결함을 판단할 수 없으면 ESCALATE할 수 있다.
- applicable implementation Cartography impact가 있으면 diff·impact 보고·affected Root 좌표·상태 증거를 대조했다. as-built drift, 증거 없는 `landed`, 미해소 system backpressure가 있으면 PASS하지 않는다.

## 권한 경계

- 읽기 전용이다.
- as-built drift를 발견해도 코드나 docs를 직접 수정하지 않는다. 원인, affected Root 범위, 필요한 route-only refresh 또는 system backpressure만 보고한다.
- 파일 생성, 수정, 삭제, commit, push, PR 생성, 외부 상태 변경 명령을 실행하지 않는다.
- 계획 자체가 모호한 경우 구현자에게 정책을 새로 요구하지 않고 source gap으로 분리한다.
- unrelated legacy cleanup을 MUST FIX로 올리지 않는다.

## 결론과 보고

간결한 prose로 findings first, `MUST FIX` / `NICE TO HAVE`, test/evidence note, 권장 다음 행동을 쓴다. 마지막 단락에는 `PASS`, `FAIL`, `ESCALATE` 중 결론 단어 하나만 명시한다.
