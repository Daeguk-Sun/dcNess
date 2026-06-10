---
name: compact-design
description: impl 도중 "설계가 부족하다" 고 판단됐을 때 되돌아오는 내부 경량 모듈 설계 스킬. 새 agent 를 만들지 않고 기존 module-architect 서브에이전트를 COMPACT_PLAN 모드로 호출하는 wrapper 다. 산출물은 `docs/compact-plans/<slug>.md` 한 파일이며, 그 경로가 후속 impl run 의 engineer 게이트 prerequisite(설계 산출물 실존) 증거가 된다. 사용자-facing 진입점이 아니라 `/impl` 내부의 되돌림(backpressure) 목적지로 호출된다. 새 product feature/epic 같은 full 설계는 `/design` 이 담당한다.
---

# compact-design — 내부 경량 모듈 설계 스킬

> 🔴 **이 스킬은 public surface 가 아니다.** 사용자가 외우는 진입점은 `/spec -> /design -> /impl -> /acceptance` 네 개다([`positioning.md`](../../docs/plugin/positioning.md)). compact-design 은 `/impl` 이 "구현 전에 경량 설계가 필요하다" 고 판단했을 때 되돌아오는 **내부 목적지**이고, full 설계 public 진입점은 `/design` 으로 유지된다. 새 사용자-facing 표면을 늘리지 않는다.

## 존재 이유 — 되돌림(backpressure) 의 1차 적용물

dcNess 의 단계 간 되돌림 원리(downstream 이 upstream 산출물 부족을 발견하면 upstream 으로 되돌려 보강) SSOT 는 [`workflow-router.md` 되돌림 원리](../../docs/plugin/workflow-router.md#되돌림backpressure-원리)다. 그중 **impl → 설계** 되돌림의 목적지가 본 스킬이다.

예전에는 경량 설계(compact plan)를 `/impl` Standard lane 이 워크플로 *안에서* 직접 생성·소비했다. 그 결과 "구현 중 설계가 부족하면 설계로 되돌린다" 는 경로가 구조적으로 없었고 설계 책임이 impl 레이어로 샜다. 본 스킬은 그 경량 설계를 impl 레이어 밖 독립 스킬로 옮긴다 — **설계 산출 주체는 종전과 동일하게 `module-architect`** 이고, 바뀌는 것은 호출 위치(impl 내부 → 되돌림 가능한 독립 스킬)뿐이다.

## 비대상 (다른 스킬)

- 새 product feature / epic / 외부 의존 선택 등 high-risk → full 설계 `/design` (compact 로 닫으면 안 됨)
- PRD 신규 / 변경 → `/spec`
- 설계 문서가 이미 있는 구현 → 곧장 `/impl` (되돌림 불필요)
- 버그픽스 한 줄 / concrete signal 충분 → `/impl` Lite (설계 산출물 없이 직접 구현)

## 입력 (호출 측이 줘야 할 정보)

- 대상 작업 slug (compact plan 파일명) — 예: `issue702-backpressure`
- 무엇이 부족해서 되돌아왔는지(설계 gap) 한 줄
- (있으면) 관련 issue 번호 · 관련 코드 SSOT 포인터

## 절차

1. **설계 gap 확인** — 호출 측(`/impl`)이 "직접 고칠 만한가 / 설계가 필요한가" 를 이미 판단해 되돌아온 상태다. 여기서는 *왜 compact 로 닫히는지*(= high-risk trigger 0개)를 재확인한다. high-risk 가 보이면 compact 로 닫지 말고 `/design` 또는 사용자 escalate 로 승격 보고한다.

2. **`module-architect:COMPACT_PLAN` 호출** — 새 agent 를 만들지 않는다. 기존 [`module-architect`](../../agents/module-architect.md) 서브에이전트를 COMPACT_PLAN 모드로 호출한다.
   - 산출물: `docs/compact-plans/<slug>.md` 한 파일.
   - 형식: [`agents/module-architect/templates/compact-plan.md`](../../agents/module-architect/templates/compact-plan.md) — 수정 허용/금지, 변경 방향, 테스트 기준, 수용 기준, 승격 신호.
   - 호출 prompt 는 슬림 포인터 규약을 따른다 — 관련 코드 SSOT / issue 포인터 + 설계 gap 만 전달하고 결정 전문을 재기입하지 않는다.

3. **승격 신호 점검** — module-architect 가 compact plan 작성 중 새 외부 의존 / auth·security·PII / migration·destructive / cross-module contract 변화를 발견하면 `NEW_DEP_ESCALATE` 또는 `ESCALATE` 로 Deep 승격을 보고한다. 이 경우 compact plan 을 확정하지 말고 호출 측에 승격을 돌려준다.

4. **산출물 경로 반환** — `PASS` 시 작성된 `docs/compact-plans/<slug>.md` 경로를 호출 측(`/impl`)에 돌려준다. 이 경로가 후속 구현의 **engineer 게이트 prerequisite(설계 산출물 실존)** 증거다.

## 호출 측(`/impl`)으로의 복귀 — engineer 게이트 prerequisite

compact plan 이 머지된 뒤 별도 run 으로 구현에 진입하는 경우(impl-loop 풀 4-agent 형태), 같은 run 안에 module-architect PASS prose 가 없다. 이때 `begin-run impl --design-doc docs/compact-plans/<slug>.md` 로 산출물을 run 에 기록하면 engineer 게이트가 그 실존을 prerequisite 증거로 인정한다([`hooks.md` engineer gate](../../docs/plugin/hooks.md#catastrophic-gatesh)).

반면 `/impl` Standard lane 처럼 **같은 run 안에서** module-architect:COMPACT_PLAN 이 돌아 PASS prose 가 생기는 경우는 그 prose 자체가 prerequisite 증거이므로 `--design-doc` 기록이 불필요하다. 두 경로 모두 게이트가 보는 것은 "설계 산출물의 실존" 하나다 — 이것이 #702 가 게이트에 적용한 원리(impl 은 설계 문서 유무만 보면 된다)다.

## 산출 후

호출 측 `/impl` 은 반환된 compact plan 을 받아 구현(test-engineer → engineer:IMPL → code-validator → pr-reviewer)으로 진행한다. 구현 중 설계가 또 부족하면 다시 본 스킬로 되돌릴 수 있다 — 되돌림은 예외가 아니라 완성도를 만드는 정상 루프다.

## 참조

- 되돌림 원리 SSOT: [`workflow-router.md` 되돌림 원리](../../docs/plugin/workflow-router.md#되돌림backpressure-원리)
- public surface 계약: [`positioning.md`](../../docs/plugin/positioning.md)
- impl 진입 분기: [`impl-routing.md`](../impl/impl-routing.md) · [`impl/SKILL.md`](../impl/SKILL.md)
- 설계 산출 agent: [`module-architect`](../../agents/module-architect.md)
- compact plan 템플릿: [`agents/module-architect/templates/compact-plan.md`](../../agents/module-architect/templates/compact-plan.md)
- engineer 게이트 design_doc: [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh)
