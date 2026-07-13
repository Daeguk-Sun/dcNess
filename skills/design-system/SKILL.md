---
name: design-system
description: /design 내부 stage 2 전용 스킬. 공개 진입점이 아니며 /design dispatcher 가 UI-less epic, stage 1 UX 산출물이 이미 durable 하게 머지된 epic, 완료된 pack 의 system/module 개정 의도가 있는 epic, 또는 design-ux revision mode 가 막 머지되어 system/module 전파가 필요한 epic 에서 호출한다. 기술 스택 체크포인트, system-architect 조건부 checkpoint, module-architect(epic-batch 또는 revision mode), architecture-validator final epic 검증을 수행하고 사용자 최종 설계 승인 뒤에만 full design pack 을 자체 PR 로 머지한다.
---

# design-system — /design 내부 system/module stage

> 이 스킬은 **공개 진입점이 아니다**. 사용자는 계속 `/design` 만 호출한다. `/design` dispatcher 가 durable 산출물 실존 판정으로 이 stage 를 선택한다.

## 목적

기존 `/design` 의 system/module 설계 pack 계약을 stage 2 로 격리한다. UI epic 에서는 stage 1 PR 로 머지된 `ux-flow.md` 와 확정 목업을 입력으로 사용하고, UI-less epic 에서는 기존처럼 UX stage 없이 한 PR 로 full design pack 을 만든다. full design pack 이 완료됐더라도 `/design <epic> --revise` 또는 대화 맥락의 명시 개정 신호가 있으면 revision mode 로 들어가 완료 pack 을 수술적 개정한다. UX 산출물 자체를 바꾸는 신호는 `design-ux` revision mode 가 먼저 처리하며, 이 stage 는 갱신된 UX 산출물을 읽어 system/module 산출물 영향분을 전파한다. 확정 목업이 존재하는 epic 에서는 목업 미참조 설계 금지 원칙을 적용한다.

## 진입 조건

- epic `stories.md` 는 존재한다.
- 다음 중 하나가 참이다.
  - UI-less epic 이다.
  - UI epic 이고 epic `ux-flow.md` 가 이미 존재한다.
- full design pack 이 아직 완료되지 않았거나, full design pack 이 완료됐더라도 명시 system/module revision mode 또는 직전 `design-ux` revision 전파 mode 이다. 완료 판정은 `architecture.md` 존재 AND `impl/NN-*.md` 1개 이상 존재다.

## Loop

- **loop**: `design`
- **entry_point**: `design`
- **stage marker**: `begin-run design --stage design-system`
- **task_list**: Codebase Sanity receipt freshness preflight → affected capability/entrypoint Cartography freshness preflight → 기술 스택 그릴미 또는 기록된 결정 확인 → 조건부 system-architect(thin bootstrap/checkpoint) → module-architect(epic-batch 또는 revision mode) → architecture-validator(final epic 검증)
- **advance**: `PASS`(thin bootstrap/checkpoint, 조건부) → `PASS`(epic-batch 또는 revision mode) → `PASS`(final epic 검증) → 사용자 최종 설계 승인 → stage 2 PR
- **expected_steps**: 2 (UI-less 또는 UX 완료) + stale/missing Codebase Sanity receipt일 때 조건부 `impl-validator:CODEBASE_SANITY` + 조건부 system-architect step

## 산출 계약

stage 2 PR 은 기존 full design pack 계약을 유지한다.

- `docs/architecture.md` 또는 `docs/decisions/**` 의 필요한 system-level 결정
- epic `architecture.md`
- 선택 epic `domain-model.md`
- 선택 epic `tech-review.md`
- epic `impl/NN-*.md`
- `docs/metrics/design-runs.jsonl`

UI epic 이면 stage 1 의 epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, 화면별 확정 목업 `docs/design-variants/<screen-id>.html` 또는 `확정본 없음`, `docs/design-variants/canvas.html` 포인터 또는 부재 신호를 입력으로 읽는다. UX 산출물 자체 개정은 `design-ux` revision mode 의 책임이고, stage 2 가 UX 산출물을 다시 만드는 것이 기본값은 아니다. 확정 목업이 존재하면 확정 목업 경로, node-id 매핑, docs/design.md 토큰을 system-architect(조건부), module-architect(epic-batch 또는 revision mode), architecture-validator(final epic 검증) prompt 에 필수 입력으로 넣는다. 목업 미참조 설계 금지: 확정 목업이 있는데 epic architecture, impl task, final 검증 근거가 그 경로와 매핑을 전혀 대조하지 않으면 clean PASS 로 보지 않는다. UX 산출물 결함이 final 검증에서 발견되면 finding 영향에 맞춰 사용자에게 되돌림을 보고하고, UX 산출물 자체 수정이 필요하면 `design-ux` revision mode 로 되돌린다.

revision mode 에서는 full design pack 이 완료됐더라도 전체 재생성을 기본값으로 두지 않는다. 사용자 개정 의도와 영향 그래프에 걸린 산출물만 수술적 개정하고, 미변경 impl task 를 재생성하지 않는다. 직전 `design-ux` revision 이 있으면 변경된 `ux-flow.md` 화면 인벤토리, 확정 목업 경로, node-id 보존/폐기 결정을 입력으로 받아 architecture/decision/impl task 영향분만 전파한다. 파생 drift 체크리스트(전역 `architecture.md` 요약, 상태 ID prefix, `design-report.html`, ADR supersede-vs-edit, `ux-flow.md`, 확정 목업 node-id, `docs/design.md` 토큰, Story/화면 번호 참조, 도메인 모델 잔존 표현)를 module-architect 입력과 final epic 검증 입력에 함께 넣는다.

## 절차

1. **Stage 선택 확인** — `/design` dispatcher 가 넘긴 epic dir 를 기준으로 full design pack 이 아직 미완인지, 명시 system/module revision mode 인지, 또는 직전 `design-ux` revision 전파 mode 인지 확인한다. 이미 완료됐고 revision mode 가 아니면 `/impl` 을 안내한다.
2. **Run 시작** — worktree와 stage 2 PR은 `/design`과 동일한 `main` base를 적용하고 `begin-run design --stage design-system`로 시작한다.
3. **stage 1 입력 수집** — UI epic 이면 epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, `ux-flow.md` 화면 인벤토리의 확정 목업 경로, 화면별 확정 목업 `docs/design-variants/<screen-id>.html` 또는 `확정본 없음`, `docs/design-variants/canvas.html` 포인터 또는 부재 신호를 먼저 확인한다. 확정본이 있으면 확정 목업 경로, node-id 매핑, docs/design.md 토큰을 이후 prompt 의 미기록 신호로 전달한다. 인벤토리가 `확정본 없음` 인 화면은 목업 부재로 전달하고 화면 ID 관례로 파일 경로를 추론하지 않는다. 직전 `design-ux` revision 이 있으면 변경 전후 화면 ID, 통합/분할/삭제된 화면, 유지/폐기된 확정 목업과 node-id 결정을 함께 전달한다.
4. **Codebase Sanity receipt freshness preflight** — `SANITY_RECEIPT_DIR="$("$HELPER" sanity-receipt-dir --project-root "$PROJECT_ROOT")"`로 persistent primary-worktree의 `.dcness-work/codebase-sanity/`를 찾고 직전 Codebase Sanity receipt가 기록한 code revision/tree identity를 현재 code tree와 대조한다. 같으면 증거를 재사용한다. receipt 부재 또는 구현·hotfix로 stale이면 메인이 test/lint/build/typecheck/coverage 명령·exit/warning을 현재 revision에서 수집하고 `impl-validator:CODEBASE_SANITY`를 이번 epic의 affected scope로 재감사한다. PASS이면 메인이 현재 tree identity의 receipt를 같은 persistent local 경로에 보존한다. `ExitWorktree`가 stage worktree를 제거해도 receipt는 남고 local-only/ignored receipt는 code PR에 노출하지 않는다. 이 receipt는 canonical Root refresh 완료 증거나 다음 단계의 affected capability/entrypoint 현재 코드 대조를 대신하지 않는다.
5. **Cartography freshness preflight** — stories, Root, 관련 global decision에서 affected capability/entrypoint를 식별하고 `landed/stub/planned/deferred` 상태를 현재 코드의 runtime entrypoint와 wiring 증거에 대조한다. 기존 topology가 없으면 thin bootstrap을 유지한다. system boundary·domain invariant·storage policy·shared public boundary·global decision 변경이 명백하면 상세 작성 전에 system checkpoint로 선승격한다. boundary 없는 route/state 갱신은 별도 heavyweight stage로 보내지 않고 module-architect가 bounded하게 처리하며, 놓친 영향은 기존 `SYSTEM_CHECKPOINT_REQUIRED`와 final validator의 `SYSTEM_BOUNDARY` finding으로 회수한다. affected Root 좌표와 관련 epic/decision은 이후 architect/validator prompt에 넣는다.
6. **기술 스택 체크포인트** — 기록된 스택 결정이 있으면 확인 안내 후 skip 하고, 없으면 메인이 사용자와 직접 합의한다.
7. **조건부 system-architect** — greenfield topology 부재면 thin bootstrap 을 1회 호출한다. 기존 모듈 경계·도메인 invariant·storage policy·public API boundary·전역 decision 변경 신호가 있으면 opt-in checkpoint 를 호출한다. UI epic 은 조건부 system-architect prompt 에도 stage 1 UX 산출물 4종(epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, 화면별 확정 목업 또는 `확정본 없음`, canvas 포인터 또는 부재 신호)을 넣는다.
8. **module-architect(epic-batch / revision mode)** — 신규 pack 에서는 epic architecture 최소형과 epic 전체 impl 산출물을 하나의 컨텍스트에서 일괄 작성한다. Story 단위 작성 주체로 쪼개지 않는다. revision mode 에서는 영향 산출물만 수술적 개정하고, 미변경 impl task 를 재생성하지 않는다. 직전 `design-ux` revision 전파 mode 라면 변경된 화면/플로우가 architecture, Story -> 모듈 매핑, impl `## 디자인 참조`, task 수/순서에 미치는 영향만 반영한다. 확정 목업이 있는 UI epic 은 목업 대조 근거를 architecture 와 impl `## 디자인 참조` 에 남기고, impl task 의 `## 디자인 참조` 가 확정 목업 경로와 핵심 node-id 매핑으로 채워지게 한다.
9. **mechanical pre-final checks** — normalize-scope, wave-plan, 확정 목업 UI epic 한정 mockup-node-check, design artifact audit 를 실행하고 unresolved 신호만 final validator prompt 에 전달한다.
10. **architecture-validator(final epic 검증)** — 기존 설계 pack 계약 그대로 final epic 검증을 수행한다. revision mode 에서도 개정분만 보지 않고 개정 후 전체 pack 정합과 파생 drift 체크리스트 결과를 검토한다. 확정 목업이 있는 UI epic 에서는 목업 미참조 설계 금지 원칙에 따라 디자인 대조 근거를 검토한다. FAIL 은 `design-routing.md` 의 finding 분류에 따라 system checkpoint 또는 module-architect 로 되돌린다.
11. **end-run + metrics freeze** — PR 생성 전에 `dcness-helper end-run` 을 실행해 `docs/metrics/design-runs.jsonl` 에 stage run 을 기록한다.
12. **사용자 최종 설계 승인 + stage 2 PR** — final epic 검증 PASS 뒤 설계 pack 요약, revision mode 여부와 drift audit 결과, diff 규모를 제시해 사용자 최종 설계 승인을 받는다. 승인 응답 전에는 `git add`, `git commit`, `git push`, `gh pr create`, `$PLUGIN_ROOT/scripts/pr-finalize.sh` 를 호출하지 않는다. 승인 뒤에만 full design pack 산출물을 stage/commit/push/PR 생성하고 merge/main sync 후 `/impl <epic-path>` 를 안내한다.

## 결론 enum

마지막 단락에는 아래 중 하나를 명시한다.

- `DESIGN_SYSTEM_PR_MERGED` — stage 2 full design pack 이 PR 로 머지됐고 다음 작업은 `/impl` 이다.
- `ESCALATE` — 스택 합의, system checkpoint, validator finding, PR/merge 실패 등 메인이 임의로 진행하면 안 되는 조건이다.

## 참조

- 공개 dispatcher: [`../design/SKILL.md`](../design/SKILL.md)
- 분기 규칙: [`../design/design-routing.md`](../design/design-routing.md)
- 산출물 지도: [`../../docs/plugin/deliverables-map.md`](../../docs/plugin/deliverables-map.md)
- public surface 계약: [`../../docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
