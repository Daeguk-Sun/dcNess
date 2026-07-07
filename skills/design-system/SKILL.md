---
name: design-system
description: /design 내부 stage 2 전용 스킬. 공개 진입점이 아니며 /design dispatcher 가 UI-less epic 이거나 stage 1 UX 산출물이 이미 durable 하게 머지된 epic 에서 호출한다. 기술 스택 체크포인트, system-architect 조건부 checkpoint, module-architect(epic-batch), architecture-validator final epic 검증을 수행하고 기존 full design pack 을 자체 PR 로 머지한다.
---

# design-system — /design 내부 system/module stage

> 이 스킬은 **공개 진입점이 아니다**. 사용자는 계속 `/design` 만 호출한다. `/design` dispatcher 가 durable 산출물 실존 판정으로 이 stage 를 선택한다.

## 목적

기존 `/design` 의 system/module 설계 pack 계약을 stage 2 로 격리한다. UI epic 에서는 stage 1 PR 로 머지된 `ux-flow.md` 와 확정 목업을 입력으로 사용하고, UI-less epic 에서는 기존처럼 UX stage 없이 한 PR 로 full design pack 을 만든다. 확정 목업이 존재하는 epic 에서는 목업 미참조 설계 금지 원칙을 적용한다.

## 진입 조건

- epic `stories.md` 는 존재한다.
- 다음 중 하나가 참이다.
  - UI-less epic 이다.
  - UI epic 이고 epic `ux-flow.md` 가 이미 존재한다.
- full design pack 이 아직 완료되지 않았다. 완료 판정은 `architecture.md` 존재 AND `impl/NN-*.md` 1개 이상 존재다.

## Loop

- **loop**: `design`
- **entry_point**: `design`
- **stage marker**: `begin-run design --stage design-system`
- **task_list**: 기술 스택 그릴미 또는 기록된 결정 확인 → 조건부 system-architect(thin bootstrap/checkpoint) → module-architect(epic-batch) → architecture-validator(final epic 검증)
- **advance**: `PASS`(thin bootstrap/checkpoint, 조건부) → `PASS`(epic-batch) → `PASS`(final epic 검증) → stage 2 PR
- **expected_steps**: 2 (UI-less 또는 UX 완료) + 조건부 system-architect step

## 산출 계약

stage 2 PR 은 기존 full design pack 계약을 유지한다.

- `docs/architecture.md` 또는 `docs/decisions/**` 의 필요한 system-level 결정
- epic `architecture.md`
- 선택 epic `domain-model.md`
- 선택 epic `tech-review.md`
- epic `impl/NN-*.md`
- `docs/metrics/design-runs.jsonl`

UI epic 이면 stage 1 의 epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, 화면별 확정 목업 `docs/design-variants/<screen-id>.html` 또는 `확정본 없음`, `docs/design-variants/canvas.html` 포인터 또는 부재 신호를 입력으로 읽지만 stage 2 가 UX 산출물을 다시 만드는 것이 기본값은 아니다. 확정 목업이 존재하면 확정 목업 경로, node-id 매핑, docs/design.md 토큰을 system-architect(조건부), module-architect(epic-batch), architecture-validator(final epic 검증) prompt 에 필수 입력으로 넣는다. 목업 미참조 설계 금지: 확정 목업이 있는데 epic architecture, impl task, final 검증 근거가 그 경로와 매핑을 전혀 대조하지 않으면 clean PASS 로 보지 않는다. UX 산출물 결함이 final 검증에서 발견되면 finding 영향에 맞춰 사용자에게 되돌림을 보고한다.

## 절차

1. **Stage 선택 확인** — `/design` dispatcher 가 넘긴 epic dir 를 기준으로 full design pack 이 아직 미완인지 확인한다. 이미 완료됐으면 `/impl` 을 안내한다.
2. **Run 시작** — worktree/base ref 는 `/design` 과 동일하게 적용하고 `begin-run design --stage design-system` 로 시작한다. 통합 브랜치 모드면 stage 2 PR 도 같은 base ref 를 사용한다.
3. **stage 1 입력 수집** — UI epic 이면 epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, `ux-flow.md` 화면 인벤토리의 확정 목업 경로, 화면별 확정 목업 `docs/design-variants/<screen-id>.html` 또는 `확정본 없음`, `docs/design-variants/canvas.html` 포인터 또는 부재 신호를 먼저 확인한다. 확정본이 있으면 확정 목업 경로, node-id 매핑, docs/design.md 토큰을 이후 prompt 의 미기록 신호로 전달한다. 인벤토리가 `확정본 없음` 인 화면은 목업 부재로 전달하고 화면 ID 관례로 파일 경로를 추론하지 않는다.
4. **기술 스택 체크포인트** — 기록된 스택 결정이 있으면 확인 안내 후 skip 하고, 없으면 메인이 사용자와 직접 합의한다.
5. **조건부 system-architect** — greenfield topology 부재면 thin bootstrap 을 1회 호출한다. 기존 모듈 경계·도메인 invariant·storage policy·public API boundary·전역 decision 변경 신호가 있으면 opt-in checkpoint 를 호출한다. UI epic 은 조건부 system-architect prompt 에도 stage 1 UX 산출물 4종(epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, 화면별 확정 목업 또는 `확정본 없음`, canvas 포인터 또는 부재 신호)을 넣는다.
6. **module-architect(epic-batch)** — epic architecture 최소형과 epic 전체 impl 산출물을 하나의 컨텍스트에서 일괄 작성한다. Story 단위 작성 주체로 쪼개지 않는다. 확정 목업이 있는 UI epic 은 목업 대조 근거를 architecture 와 impl `## 디자인 참조` 에 남기고, impl task 의 `## 디자인 참조` 가 확정 목업 경로와 핵심 node-id 매핑으로 채워지게 한다.
7. **mechanical pre-final checks** — normalize-scope, wave-plan, design artifact audit 를 실행하고 unresolved 신호만 final validator prompt 에 전달한다.
8. **architecture-validator(final epic 검증)** — 기존 설계 pack 계약 그대로 final epic 검증을 수행한다. 확정 목업이 있는 UI epic 에서는 목업 미참조 설계 금지 원칙에 따라 디자인 대조 근거를 검토한다. FAIL 은 `design-routing.md` 의 finding 분류에 따라 system checkpoint 또는 module-architect 로 되돌린다.
9. **end-run + metrics freeze** — PR 생성 전에 `dcness-helper end-run` 을 실행해 `docs/metrics/design-runs.jsonl` 에 stage run 을 기록한다.
10. **stage 2 PR** — full design pack 산출물을 stage/commit/push/PR 생성한다. main 머지 직전에는 설계 pack 요약과 diff 규모를 제시하고 사용자 확인 checkpoint 를 둔다. yolo 모드에서는 기존 `/design` 계약대로 확인을 생략할 수 있다. PR merge/main sync 후 `/impl <epic-path>` 를 안내한다.

## 결론 enum

마지막 단락에는 아래 중 하나를 명시한다.

- `DESIGN_SYSTEM_PR_MERGED` — stage 2 full design pack 이 PR 로 머지됐고 다음 작업은 `/impl` 이다.
- `ESCALATE` — 스택 합의, system checkpoint, validator finding, PR/merge 실패 등 메인이 임의로 진행하면 안 되는 조건이다.

## 참조

- 공개 dispatcher: [`../design/SKILL.md`](../design/SKILL.md)
- 분기 규칙: [`../design/design-routing.md`](../design/design-routing.md)
- 산출물 지도: [`../../docs/plugin/deliverables-map.md`](../../docs/plugin/deliverables-map.md)
- public surface 계약: [`../../docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
