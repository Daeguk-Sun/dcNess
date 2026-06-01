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

- `docs/prd.md` (root) + epic 단위 `docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` 가 main 머지된 상태 (`/product-plan` Step 7)
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

**Base ref 분기 (MUST, #424)**: epic 단위 `docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 통합 브랜치 모드 — outer worktree base ref + `docs/<epic-slug>` branch 둘 다 integration branch 기반. 절차 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.

## Pre-flight gate (Step 0 직후)

[`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §6 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

## 절차 (요약)

상세 = [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §4.2.

K 의 의미: **Story 수 + 공통 호출 1 회 (공통 task 있으면) 또는 0 회 (없으면)**. 옛 task 단위 K (~27) 와 다르게 새 K 는 Story 묶음 단위라 ~5+α 영역.

1. **Step 0** — 워크트리 진입 + `EnterWorktree` + branch (`docs/<epic-slug>`) + `begin-run architect-loop`
2. **Step 1** — TaskCreate (ux-architect / system-architect / architecture-validator × 2회 / module-architect × K 의 K = Story 수 + 공통 호출)
3. **Step 2 — ux-architect:UX_FLOW** (5 카테고리 self-check 의무) → `UX_FLOW_READY` → **commit 1** (epic 단위 `docs/milestones/vNN/epics/epic-NN-*/ux-flow.md`)
4. **Step 3 — system-architect** — root `docs/architecture.md` + root `docs/adr.md` + epic 단위 architecture.md (모듈 목록 + 의존 그래프 + 공통 task 목록 + Story → 모듈 매핑) + epic 단위 adr.md + epic 단위 domain-model.md 산출. `## impl 목차` 표 폐기 (task 단위 분할은 module-architect 영역).
5. **Step 3.5 — architecture-validator 1차** — Placeholder Leak + 공통 SSOT 룰 위반 자동 영역 검증. Cross-Story Interface 는 이 시점 N/A (impl 파일 미작성). → `PASS` → **commit 2** (system-architect 산출물 일괄)
6. **Step 4 — module-architect × K** — Story 단위 + 공통 task 단위 순차 호출
   - **Step 4.0 (공통 task 있으면)** — `mode=common` + 공통 task 목록 (system-architect 가 epic 단위 architecture.md 의 공통 task 섹션에 박은 영역) prompt 에 박고 호출. 산출 = 공통 task 의 impl 파일 N 개. → **commit 3**
   - **Step 4.1 ~ 4.N (Story 순차)** — Story 1 개씩 prompt 에 박고 호출. 산출 = Story 안 task 의 impl 파일 N 개. 각 호출 `READY` 직후 → **commit 4..N+3**
   - batch 모드 폐기 — Story 묶음 자체가 batch 의 본질 해결 (옛 batch 모드는 issue [#511](https://github.com/alruminum/dcNess/issues/511) 본질 해결로 자연 폐기)
7. **Step 5 — architecture-validator 2차** — Cross-Story Interface 정합성 검증 (모든 impl 완성 후 producer ↔ consumer 시그니처 grep 비교) + Implementation Simulation (대표 impl task 2~3 개 cold-seat 시뮬레이션 — 표시 없는 암묵 gap 조기 포착) + Placeholder Leak 재검증 (module 단계 새로 생긴 영역) → `PASS` → **commit N+4** (검증 결과 메타)
8. **Step 6 — PR + 머지** — `git push -u origin docs/<epic-slug>` + `gh pr create --base <BASE>` (body = 설계 산출물 요약 + `Part of #<epic-issue>`) + `bash scripts/pr-finalize.sh`
   - **base 분기 (MUST)**: `gh pr create` 직전 epic 단위 stories.md 상단 `**Base Branch:**` 줄 매치 → `--base <매치 값>` (통합 브랜치 케이스, base = `feature/<slug>`). 매치 없음 → `--base main` (default). Step 0 의 `EnterWorktree` branch (`docs/<epic-slug>`) 도 동일 base 기반 — 절차 [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.
9. **Step 7 — ExitWorktree** + `end-run`

## 분기 / cycle (요약)

- ux-architect self-check FAIL → ux-architect 재진입 (cycle ≤ 2, prose 내부)
- `UX_REFINE_READY` → designer 분기 (`/ux` 또는 `ux-refine-stage`)
- architecture-validator 1차 `FAIL` (Step 3.5) → system-architect 재진입 (cycle ≤ 2). 보통 Placeholder Leak 또는 공통 SSOT 룰 위반 영역.
- architecture-validator 2차 `FAIL` (Step 5) → 해당 module-architect 재진입 (Cross-Story Interface 영역 또는 Implementation Simulation gap 보강, cycle ≤ 2). 또는 system-architect 재진입 (모듈 의존 그래프 영역).
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
