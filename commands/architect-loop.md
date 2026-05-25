---
name: architect-loop
description: PRD/stories.md 머지 + epic/story 이슈 등록 *이후*, 1 epic 단위로 ux-architect / system-architect / architecture-validator / module-architect × K 를 순차 호출하여 설계 산출물 (`docs/ux-flow.md` + `docs/architecture.md` + `docs/adr.md` + `docs/milestones/.../impl/*.md` × K) 을 작성하고 1 PR 로 머지하는 설계 루프 스킬. 사용자가 "설계해줘", "architect-loop", "epic 설계", "/architect-loop <epic-path>", "ux-flow 부터", "impl 다 만들어줘" 등을 말할 때 반드시 이 스킬을 사용한다. `/product-plan` 의 후속. 구현 진입은 별도 (`/impl` / `/impl-loop`).
---

# Architect Loop Skill — 1 epic 단위 설계 루프

> 본 스킬 = `/product-plan` 종료 후 사용자가 *명시 호출* 하는 설계 루프. 자동 진입 X. PRD/stories.md 가 main 머지된 상태 + epic/story 이슈 등록 완료가 전제.

## Loop

`architect-loop` ([`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §4.2 — architect-loop 풀스펙).

## Inputs (메인이 사용자에게 받아야 할 정보)

- epic 경로 (필수, 예: `docs/milestones/v01/epics/epic-01-<slug>/`)
- 또는 stories.md 경로 (메인이 epic dir 추출)
- (선택) 사용자가 명시한 design medium — 미지정 시 ux-architect 가 detect + 역질문

## 전제 조건 (진입 전 충족 의무)

- `docs/prd.md` + `docs/stories.md` 가 main 머지된 상태 (`/product-plan` Step 7)
- epic + story 이슈 등록 완료 (`scripts/create_epic_story_issues.sh` 산출, stories.md 상단 `**GitHub Epic Issue:** [#NNN]` 마커 존재)
- 미충족 시 → `/product-plan` 재진입 권고 (사용자에게 안내)

## 비대상 (다른 skill 추천)

- PRD 신규 / 변경 → `/product-plan`
- 구현 (task PR) → `/impl` / `/impl-loop`
- 버그픽스 / qa → `/issue-report`
- 이미 설계 완료된 epic 의 일부 impl 보강 → `/impl` fallback (module-architect 직접)

## 사전 read (lazy — 필요시만, #400)

정상 흐름은 본 skill 본문 + 인용된 docs §번호 만으로 진행. 본문에 있는 catastrophic / Pre-flight gate / agent boundary 룰이 1차. *룰 모호 / 분기 발생* 시에만 `docs/plugin/loop-procedure.md` / `orchestration.md §4.2` (architect-loop 풀스펙) / `handoff-matrix.md` / `issue-lifecycle.md` / `git-spec.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

## 워크트리 (기본 켜짐)

Step 0 진입 시 자동 `EnterWorktree(name="architect-{ts_short}")`. 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.

**Base ref 분기 (MUST, #424)**: `docs/stories.md` `**Base Branch:** feature/<slug>` 마커 매치 시 통합 브랜치 모드 — outer worktree base ref + `docs/<epic-slug>` branch 둘 다 integration branch 기반. 절차 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.

## Pre-flight gate (Step 0 직후)

[`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §6 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

## 절차 (요약)

상세 = [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §4.2.

1. **Step 0** — 워크트리 진입 + `EnterWorktree` + branch (`docs/<epic-slug>`) + `begin-run architect-loop`
2. **Step 1** — TaskCreate (ux-architect / system-architect / architecture-validator / module-architect × K 의 K = stories.md 의 Story task 총수 추정)
3. **Step 2 — ux-architect:UX_FLOW** (5 카테고리 self-check 의무) → `UX_FLOW_READY` → **commit 1** (`docs/ux-flow.md`)
4. **Step 3 — system-architect** (self-check + `## impl 목차` 표 + `task_index` 컬럼 의무) → `READY`
5. **Step 3.5 — architecture-validator** (Placeholder Leak + Spike Gate) → `PASS` → **commit 2** (`docs/architecture.md` + `docs/adr.md`)
6. **Step 4.1 ~ 4.K — module-architect × K** (system-architect impl 목차 행마다 1번 호출, prompt 에 `task_index: i/total` 씀)
   - 각 호출 `READY` 직후 → **commit 3..K+2** (`docs/milestones/.../impl/NN-<slug>.md` 1 파일씩)
   - **batch 모드 (선택)**: K 가 크면 (≥ 8 권장 기준) Story 단위 묶음으로 1 호출 = N task (N ≤ 5 권장) 허용. 호출 prompt 에 강제 문구 — `본 호출에서 N 개 impl 파일을 분리 작성. 1 파일에 multiple task 통합 금지` + 각 task 의 `task_index: i/total` 박는다. 산출은 그대로 N 개 impl 파일 (1 파일 1 task 책임 분리 유지). 본질 해결 (system-architect = 모듈 contract / module-architect = 모듈 내부 위임) 은 [issue #511](https://github.com/alruminum/dcNess/issues/511) 영역 — 본 batch 는 단기 회피.
7. **Step 5 — PR + 머지** — `git push -u origin docs/<epic-slug>` + `gh pr create --base <BASE>` (body = 설계 산출물 요약 + `Part of #<epic-issue>`) + `bash scripts/pr-finalize.sh`
   - **base 분기 (MUST)**: `gh pr create` 직전 `docs/stories.md` 상단 `**Base Branch:**` 줄 매치 → `--base <매치 값>` (통합 브랜치 케이스, base = `feature/<slug>`). 매치 없음 → `--base main` (default). Step 0 의 `EnterWorktree` branch (`docs/<epic-slug>`) 도 동일 base 기반 — 절차 [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.
8. **Step 6 — ExitWorktree** + `end-run`

## 분기 / cycle (요약)

- ux-architect self-check FAIL → ux-architect 재진입 (cycle ≤ 2, prose 내부)
- `UX_REFINE_READY` → designer 분기 (`/ux` 또는 `ux-refine-stage`)
- architecture-validator `FAIL` → system-architect 재진입 (cycle ≤ 2)
- module-architect `SPEC_GAP_FOUND` → module-architect (보강 케이스) cycle (≤ 2) → 신규 케이스 재진입
- `*_ESCALATE` → 사용자 위임
- cycle 발생 시 working tree only — commit X. PASS 후만 commit.

## 후속 라우팅

- 본 loop clean → 자동 commit/PR + 머지 → 사용자에게 "`/impl-loop <epic-path>` 로 구현 진입할까요?" 안내
- 주의사항 → 사용자 결정 (수동)
- spec gap 발견 + cycle 한도 초과 → 사용자 위임 (`/product-plan` 재진입 권고)

## 참조

- 시퀀스 / loop 풀스펙: [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §4.2 (architect-loop 풀스펙)
- 절차 mechanics: [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1~§6
- 핸드오프 / 권한: [`docs/plugin/handoff-matrix.md`](../docs/plugin/handoff-matrix.md)
- 이슈 lifecycle: [`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md)
- 브랜치·커밋·PR 네이밍: [`docs/plugin/git-spec.md`](../docs/plugin/git-spec.md)
- agent 정의: [`agents/ux-architect.md`](../agents/ux-architect.md) / [`agents/system-architect.md`](../agents/system-architect.md) / [`agents/architecture-validator.md`](../agents/architecture-validator.md) / [`agents/module-architect.md`](../agents/module-architect.md)
