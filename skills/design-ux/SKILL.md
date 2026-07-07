---
name: design-ux
description: /design 내부 stage 1 전용 스킬. 공개 진입점이 아니며 /design dispatcher 가 UI epic 에서 ux-flow.md 가 아직 durable 하게 머지되지 않았을 때만 호출한다. ux-architect 와 필요한 canvas-design 경로를 실행하고 `docs/epics/<epic>/ux-flow.md`, `docs/design.md`, `docs/design-variants/` 확정본을 자체 PR 로 머지해 "ux 완료 · system 미완" 상태를 main 에 남긴다.
---

# design-ux — /design 내부 UX stage

> 이 스킬은 **공개 진입점이 아니다**. 사용자가 외우는 설계 진입점은 계속 `/design` 하나다. `/design` dispatcher 가 durable 산출물 실존 판정으로 이 stage 를 선택한다.

## 목적

UI epic 의 UX 산출물을 system/module 설계와 같은 PR 에 묶지 않고 먼저 durable 하게 머지한다. stage 1 PR 이 main 에 들어가면 `docs/epics/<epic>/ux-flow.md` 존재만으로 다음 세션이 "`/design` (ux 완료 · system 미완)" 상태를 복구할 수 있다.

## 진입 조건

- epic `stories.md` 는 존재한다.
- UI epic 으로 판정됐다.
- epic `ux-flow.md` 가 아직 없다.
- full design pack 은 아직 완료되지 않았다.

UI-less epic 은 이 stage 를 호출하지 않고 `/design` dispatcher 가 곧장 `design-system` stage 로 보낸다. `ux-flow.md` 가 이미 있으면 stage 1 은 완료된 것으로 보고 재실행하지 않는다.

## Loop

- **loop**: `design`
- **entry_point**: `design`
- **stage marker**: `begin-run design --stage design-ux`
- **task_list**: ux-architect:UX_FLOW → 필요한 경우 내부 canvas-design → 사용자 PICK
- **advance**: `UX_FLOW_READY` 또는 canvas-design `PASS` → stage 1 PR
- **expected_steps**: 1 + 조건부 designer step. canvas-design 은 main-owned checkpoint 이며 helper begin/end-step 비대상이다.

## 산출 계약

stage 1 PR 에 포함되는 파일은 UX stage 가 실제로 생성/갱신한 파일로 제한한다.

- 필수: `docs/epics/<epic>/ux-flow.md`
- 조건부: `docs/design.md`
- 조건부: `docs/design-variants/<screen-id>.html`
- 조건부: `docs/design-variants/canvas.html`
- 조건부 seed: `docs/design-variants/_lib/**`, `docs/design-variants/.gitignore`, `docs/design-variants/drafts/.gitkeep`
- 조건부 metrics: `docs/metrics/design-runs.jsonl`

architecture, domain-model, impl task 는 이 stage 에서 만들지 않는다. 그 산출물은 `design-system` stage 의 책임이다.

## 절차

1. **Stage 선택 확인** — `/design` dispatcher 가 넘긴 epic dir 를 기준으로 `stories.md` 와 UI 판정을 확인한다. `ux-flow.md` 가 이미 있으면 이 stage 를 중단하고 `design-system` 으로 돌아간다.
2. **Run 시작** — worktree/base ref 는 `/design` 과 동일하게 적용하고 `begin-run design --stage design-ux` 로 시작한다. 통합 브랜치 모드면 stage 1 PR 도 같은 base ref 를 사용한다.
3. **ux-architect 호출** — `UX_FLOW` 모드로 epic `ux-flow.md` 를 작성한다. 화면 인벤토리는 `hi-fi 목업 필요` 열을 유지한다.
4. **목업 필요 화면 처리** — `hi-fi 목업 필요` 가 `필요` 인 화면만 내부 [`canvas-design`](../canvas-design/SKILL.md) 으로 넘긴다. seed 보장, designer draft, 사용자 PICK, 확정본 승격, canvas 등록은 canvas-design 계약을 따른다.
5. **end-run + metrics freeze** — PR 생성 전에 `dcness-helper end-run` 을 실행해 `docs/metrics/design-runs.jsonl` 에 stage run 을 기록한다.
6. **stage 1 PR** — stage 1 산출물만 stage/commit/push/PR 생성한다. PR body 의 배포 경로에는 `/design` 내부 stage 이고 공개 진입점 변화가 없음을 명시한다. main 머지 직전에는 UX 산출물 요약과 diff 규모를 제시하고 사용자 확인 checkpoint 를 둔다. yolo 모드에서는 기존 `/design` 계약대로 확인을 생략할 수 있다.
7. **머지 후 반환** — PR merge/main sync 가 끝나면 `/design` dispatcher 로 돌아간다. 다음 durable 판정은 `ux-flow.md` 존재 + 설계 pack 부재이므로 `design-system` stage 를 선택한다.

## 결론 enum

마지막 단락에는 아래 중 하나를 명시한다.

- `DESIGN_UX_PR_MERGED` — stage 1 산출물이 PR 로 머지됐고 다음 `/design` 진입은 system stage 로 이어질 수 있다.
- `ESCALATE` — UI 판정, 사용자 PICK, seed 복사, PR/merge 실패 등 메인이 임의로 진행하면 안 되는 조건이다.

## 참조

- 공개 dispatcher: [`../design/SKILL.md`](../design/SKILL.md)
- 분기 규칙: [`../design/design-routing.md`](../design/design-routing.md)
- 내부 목업 wrapper: [`../canvas-design/SKILL.md`](../canvas-design/SKILL.md)
- public surface 계약: [`../../docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
