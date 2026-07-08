---
name: design-ux
description: /design 내부 stage 1 전용 스킬. 공개 진입점이 아니며 /design dispatcher 가 UI epic 에서 ux-flow.md 가 아직 durable 하게 머지되지 않았거나, 완료된 full design pack 에 UX 층 개정 신호가 있을 때 호출한다. 목업 선행 여부를 확인한 뒤 ux-architect 와 목업=예 한정 디자인 시스템 체크포인트/canvas-design 경로를 실행하고, 사용자 최종 설계 승인 뒤에만 `docs/epics/<epic>/ux-flow.md`, `docs/design.md`, `docs/design-variants/` 확정본을 자체 PR 로 머지해 "ux 완료 · system 미완" 또는 "UX revision 완료 · system revision 필요" 상태를 main 에 남긴다.
---

# design-ux — /design 내부 UX stage

> 이 스킬은 **공개 진입점이 아니다**. 사용자가 외우는 설계 진입점은 계속 `/design` 하나다. `/design` dispatcher 가 durable 산출물 실존 판정으로 이 stage 를 선택한다.

## 목적

UI epic 의 UX 산출물을 system/module 설계와 같은 PR 에 묶지 않고 먼저 durable 하게 머지한다. stage 1 PR 이 main 에 들어가면 `docs/epics/<epic>/ux-flow.md` 존재만으로 다음 세션이 "`/design` (ux 완료 · system 미완)" 상태를 복구할 수 있다.

완료된 full design pack 에서 화면 통합·분할·삭제, 플로우 변경, `ux-flow.md`, 확정 목업, `docs/design.md` 토큰처럼 UX 산출물 자체를 바꾸는 명시 개정 신호가 있으면 revision mode 로 들어간다. 이때 stage 1 은 UX 산출물만 수술적으로 개정하고, architecture/impl/decision 전파는 stage 1 revision PR 머지 뒤 `design-system` revision mode 가 맡는다.

## 진입 조건

- epic `stories.md` 는 존재한다.
- UI epic 으로 판정됐다.
- epic `ux-flow.md` 가 아직 없거나, full design pack 이 이미 완료됐지만 UX 층 revision mode 이다.
- 신규 UX stage 라면 full design pack 은 아직 완료되지 않았다.

UI-less epic 은 이 stage 를 호출하지 않고 `/design` dispatcher 가 곧장 `design-system` stage 로 보낸다. `ux-flow.md` 가 이미 있고 UX 층 revision mode 도 아니면 stage 1 은 완료된 것으로 보고 재실행하지 않는다.

## Loop

- **loop**: `design`
- **entry_point**: `design`
- **stage marker**: `begin-run design --stage design-ux`
- **task_list**: 목업 선행 여부 checkpoint 또는 UX revision 의도 확인 → ux-architect:UX_FLOW → 목업=예 한정 디자인 시스템 체크포인트 → 필요한 경우 내부 canvas-design → 사용자 PICK
- **advance**: `UX_FLOW_READY` 또는 canvas-design `PASS` → 사용자 최종 설계 승인 → stage 1 PR
- **expected_steps**: 1 + 조건부 designer step. canvas-design 은 main-owned checkpoint 이며 helper begin/end-step 비대상이다.

## 산출 계약

stage 1 PR 에 포함되는 파일은 UX stage 가 실제로 생성/갱신한 파일로 제한한다. revision mode 에서도 system/module 산출물은 직접 수정하지 않는다.

- 필수: `docs/epics/<epic>/ux-flow.md`
- 조건부: `docs/design.md`
- 조건부: `docs/design-variants/<screen-id>.html`
- 조건부: `docs/design-variants/canvas.html`
- 조건부 seed: `docs/design-variants/_lib/**`, `docs/design-variants/.gitignore`, `docs/design-variants/drafts/.gitkeep`
- 조건부 metrics: `docs/metrics/design-runs.jsonl`

architecture, domain-model, impl task 는 이 stage 에서 만들지 않는다. 그 산출물은 `design-system` stage 의 책임이다.

## 절차

1. **Stage 선택 확인** — `/design` dispatcher 가 넘긴 epic dir 를 기준으로 `stories.md` 와 UI 판정, UX 층 revision mode 여부를 확인한다. `ux-flow.md` 가 이미 있고 revision mode 가 아니면 이 stage 를 중단하고 `design-system` 으로 돌아간다.
2. **Run 시작** — worktree/base ref 는 `/design` 과 동일하게 적용하고 `begin-run design --stage design-ux` 로 시작한다. 통합 브랜치 모드면 stage 1 PR 도 같은 base ref 를 사용한다.
3. **목업 선행 여부 checkpoint** — UI epic 에서 목업 선행 여부를 1회 묻는다. 목업=예 가 아니면 목업 없음 으로 처리한다. 사용자 opt-out 발화나 yolo 모드는 yolo 기본값 = 목업 없음 이며, 기존 UX stage 흐름 그대로 ux-flow 와 text wireframe 만 durable 하게 남긴다. opt-out 정규식은 `/design` dispatcher 의 `(목업|mockup|시안|디자인)\s*(빼|없|말|나중|생략)` 를 따른다.
4. **디자인 시스템 체크포인트 (목업=예 한정)** — docs/design.md 실존+유효 이면 확인-후-skip 한다. 부재하면 사용자에게 참고 디자인 시스템을 요청한다. 이미 `docs/design-refs/` 같은 ad-hoc 베이스라인 문서가 있으면 외부 import 1회 변환으로 `docs/design.md` 에 흡수하고, 같은 내용을 반복 import 하지 않는다. 이 결과를 ux-architect prompt 의 참고 디자인 시스템 신호로 전달한다.
5. **ux-architect 호출** — `UX_FLOW` 모드로 epic `ux-flow.md` 를 작성한다. revision mode 에서는 기존 `ux-flow.md`, `docs/design.md`, 확정 목업/canvas 포인터와 "화면 통합/분할/삭제 등 UX 층 개정 의도"를 입력으로 넣고 영향 UX 산출물만 개정하게 한다. 화면 인벤토리는 `hi-fi 목업 필요` 열을 유지하고, 목업=예 경로에서는 `docs/design.md` 토큰을 참고 디자인 시스템 신호에 맞춰 정리한다.
6. **목업 필요 화면 처리** — 목업=예 경로에서만 `hi-fi 목업 필요` 가 `필요` 인 화면을 내부 [`canvas-design`](../canvas-design/SKILL.md) 으로 넘긴다. seed 보장, designer draft, 사용자 PICK, 확정본 승격, canvas 등록은 canvas-design 계약을 따른다. 확정본 승격 후 메인은 epic `ux-flow.md` 화면 인벤토리의 `확정 목업 경로` 를 `docs/design-variants/<screen-id>.html` 로 채우고, 화면별 `확정 목업` 항목에 canvas 경로와 핵심 node-id 매핑을 기록한다. system stage 는 사용자 PICK 확정 이후에만 진입한다.
   - 목업 없음 경로에서는 canvas-design 을 강제하지 않는다. `hi-fi 목업 필요` 는 후속 `/ux` 또는 `/impl` 기준 확보 판단의 신호로만 남긴다.
7. **end-run + metrics freeze** — PR 생성 전에 `dcness-helper end-run` 을 실행해 `docs/metrics/design-runs.jsonl` 에 stage run 을 기록한다.
8. **사용자 최종 설계 승인 + stage 1 PR** — UX 산출물 요약, 목업 선행 여부, 확정 목업 경로와 diff 규모를 제시해 사용자 최종 설계 승인을 받는다. revision mode 에서는 UX revision 산출물 요약, 변경 전후 화면/플로우 영향, 유지/폐기한 확정 목업 경로와 diff 규모를 함께 제시한다. 승인 응답 전에는 `git add`, `git commit`, `git push`, `gh pr create`, `$PLUGIN_ROOT/scripts/pr-finalize.sh` 를 호출하지 않는다. 승인 뒤에만 stage 1 산출물만 stage/commit/push/PR 생성한다. PR body 의 배포 경로에는 `/design` 내부 stage 이고 공개 진입점 변화가 없음을 명시한다.
9. **머지 후 반환** — PR merge/main sync 가 끝나면 `/design` dispatcher 로 돌아간다. 신규 UX stage 의 다음 durable 판정은 `ux-flow.md` 존재 + 설계 pack 부재이므로 `design-system` stage 를 선택한다. revision mode 였다면 직전 stage 1 revision PR 이 UX 산출물을 바꿨다는 신호를 유지해 `design-system` revision mode 로 이어지고, architecture/decision/impl task 의 영향분을 전파한다.

## 결론 enum

마지막 단락에는 아래 중 하나를 명시한다.

- `DESIGN_UX_PR_MERGED` — stage 1 산출물이 PR 로 머지됐고 다음 `/design` 진입은 system stage 로 이어질 수 있다.
- `ESCALATE` — UI 판정, 사용자 PICK, seed 복사, PR/merge 실패 등 메인이 임의로 진행하면 안 되는 조건이다.

## 참조

- 공개 dispatcher: [`../design/SKILL.md`](../design/SKILL.md)
- 분기 규칙: [`../design/design-routing.md`](../design/design-routing.md)
- 내부 목업 wrapper: [`../canvas-design/SKILL.md`](../canvas-design/SKILL.md)
- public surface 계약: [`../../docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
