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

정상 흐름은 본 skill 본문 + 인용된 docs §번호 만으로 진행. 본문에 있는 catastrophic / Pre-flight gate / agent boundary 룰이 1차. *룰 모호 / 분기 발생* 시에만 `docs/plugin/loop-procedure.md` / `orchestration.md §4.2` (architect-loop 풀스펙) / `issue-lifecycle.md` / `git-spec.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

## 워크트리 (기본 켜짐)

Step 0 진입 시 자동 `EnterWorktree(name="architect-{ts_short}")`. 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.

**Base ref 분기 (MUST, #424)**: epic 단위 `docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 통합 브랜치 모드 — outer worktree base ref + `docs/<epic-slug>` branch 둘 다 integration branch 기반. 절차 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.

## Pre-flight gate (Step 0 직후)

[`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §6 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

## 기술 스택 그릴미 체크포인트 (Step 2.9 — system-architect 직전)

system-architect(Step 3) 호출 *직전*에 메인 Claude 가 사용자와 **직접** 기술 스택을 합의하는 체크포인트. system-architect 는 서브에이전트라 사용자와 직접 대화 불가 — 그릴미는 메인이 진행하고, 합의 결론을 system-architect 호출 prompt 에 박아 전달한다. 기존 `Step 2.5 사용자 PICK` (impl-ui-design-loop) 와 동형 — helper begin/end-step **비대상** (사용자 체크포인트). step 컨벤션 `tech-stack-grill-2.9`.

- **발동: 기본 ON.** 사용자 발화에 정규식 `(그릴미|기술\s*스택|스택)\s*(빼|없|말|알아서|생략)` 매치 시에만 skip (워크트리 빼 패턴 동형). skip 시 system-architect 가 기존대로 스택 자율 결정.
- **UI 판정과 무관** — UI epic (Step 2 ux-architect 후) / UI-less epic (Step 2 skip 후) 둘 다 항상 system-architect 직전에 위치.
- **진행**: 메인이 `docs/prd.md` + (있으면) `docs/tech-review.md` 를 read → 그릴미 패턴 (한 번에 한 질문 / 가설+권장안 제시 / 코드·문서 탐색 우선 / 결정나무 가지치기, [`product-plan.md`](product-plan.md) `## 그릴미 패턴` 차용) 으로 스택 합의. tech-review **축 2 권고** (스펙 강등 / 업그레이드 / 대안 기술) 를 사용자 눈앞에서 채택·미채택 결론까지 도출.
- **산출**: 별도 파일 X. 합의 결론 (채택 스택 + 축 2 권고 채택/미채택)을 system-architect 호출 prompt 에 박는다. system-architect 가 architecture.md / adr.md 에 영구 기록 (축 2 권고는 채택/미채택 + 이유를 adr.md 1줄, agent 자기 규율).
- **tech-review.md 미전달 케이스** (외부 의존 0 개 → `/tech-review` skip): 축 2 권고 영역만 N/A. 스택 합의 그릴미 자체는 그대로 진행 (외부 의존 없어도 언어·프레임워크·DB 등 핵심 스택 결정엔 사용자 참여).

## UI-less epic 분기 (Step 1 전 판정)

TaskCreate 직전 메인이 `docs/prd.md` 의 **"화면 인벤토리 + 대략적 플로우"** 섹션을 read 하고 판정한다. ux-architect 산출물(ux-flow.md)은 system-architect 의 "(있으면)" 선택 입력일 뿐이고 architecture-validator / module-architect 는 ux-flow 를 참조하지 않으므로, UI-less epic 에서 ux 단계 skip 은 후속 단계를 깨지 않는다.

| 판정 | 조건 | 행동 |
|---|---|---|
| **UI epic** | 유효 화면 (= `(UI 없음)` 아닌 항목) ≥ 1 개 | 평소대로 Step 2 ux-architect 진행 |
| **UI-less epic** | 화면 인벤토리 항목이 **전부 `(UI 없음)`** / 섹션 부재 / 유효 화면 0 개 | Step 1 TaskCreate 에서 **ux-architect 제외** + Step 2 skip (commit 1 없음) → Step 3 직행 |
| **모호** | 화면 인벤토리 일부만 UI / 판정 불확실 | **보수적으로 UI epic 진행** (skip 은 명백할 때만) |

- 판정은 메인 prose 자율 영역 — hook 강제 아님 ([`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §0). PRD 화면 인벤토리는 자유 텍스트라 메인이 의미로 판정.
- UI-less 판정 시 expected_steps = `3 + K` (UI epic 은 `4 + K`).

## 절차 (요약)

상세 = [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §4.2.

K 의 의미: **Story 수 + 공통 호출 1 회 (공통 task 있으면) 또는 0 회 (없으면)**. 옛 task 단위 K (~27) 와 다르게 새 K 는 Story 묶음 단위라 ~5+α 영역.

1. **Step 0** — 워크트리 진입 + `EnterWorktree` + branch (`docs/<epic-slug>`) + `begin-run architect-loop`
2. **Step 1** — *UI 판정* (아래 `## UI-less epic 분기`) 후 TaskCreate. UI epic → (ux-architect / system-architect / architecture-validator × 2회 / module-architect × K). **UI-less epic → ux-architect 제외** (system-architect / architecture-validator × 2회 / module-architect × K). K = Story 수 + 공통 호출
3. **Step 2 — ux-architect:UX_FLOW** (5 카테고리 self-check 의무) → `UX_FLOW_READY` → **commit 1** (epic 단위 `docs/milestones/vNN/epics/epic-NN-*/ux-flow.md`).
   - **UI-less epic 이면 본 Step 전체 skip** (commit 1 없음) → 바로 Step 2.9 (기술 스택 그릴미). ux-flow 경로는 system-architect 에 미전달 (원래 "(있으면)" 선택 입력이라 자연 처리)
4. **Step 2.9 — 기술 스택 그릴미** (메인 직접, 기본 ON + opt-out) — 위 `## 기술 스택 그릴미 체크포인트` 절차. helper begin/end-step 비대상 (commit 없음). 합의 결론을 Step 3 system-architect prompt 에 박아 전달. opt-out 발화 매치 시 본 Step skip → Step 3 직행.
5. **Step 3 — system-architect** — root `docs/architecture.md` + root `docs/adr.md` + epic 단위 architecture.md (모듈 목록 + 의존 그래프 + 공통 task 목록 + Story → 모듈 매핑) + epic 단위 adr.md + epic 단위 domain-model.md 산출. **Step 2.9 합의 결론 (채택 스택 + 축 2 권고 채택/미채택) 을 prompt 에 박아 전달** (그릴미 skip 케이스면 미전달 → 자율 결정). `## impl 목차` 표 폐기 (task 단위 분할은 module-architect 영역).
6. **Step 3.5 — architecture-validator 1차** — Placeholder Leak + 공통 SSOT 룰 위반 자동 영역 검증. Cross-Story Interface 는 이 시점 N/A (impl 파일 미작성). → `PASS` → **commit 2** (system-architect 산출물 일괄)
7. **Step 4 — module-architect × K** — Story 단위 + 공통 task 단위 순차 호출
   - **Step 4.0 (공통 task 있으면)** — `mode=common` + 공통 task 목록 (system-architect 가 epic 단위 architecture.md 의 공통 task 섹션에 박은 영역) prompt 에 박고 호출. 산출 = 공통 task 의 impl 파일 N 개. → **commit 3**
   - **Step 4.1 ~ 4.N (Story 순차)** — Story 1 개씩 prompt 에 박고 호출. 산출 = Story 안 task 의 impl 파일 N 개. 각 호출 `READY` 직후 → **commit 4..N+3**
   - batch 모드 폐기 — Story 묶음 자체가 batch 의 본질 해결 (옛 batch 모드는 issue [#511](https://github.com/alruminum/dcNess/issues/511) 본질 해결로 자연 폐기)
8. **Step 5 — architecture-validator 2차** — Cross-Story Interface 정합성 검증 (모든 impl 완성 후 producer ↔ consumer 시그니처 grep 비교) + Implementation Simulation (대표 impl task 2~3 개 cold-seat 시뮬레이션 — 표시 없는 암묵 gap 조기 포착) + Origin Anchor (PRD `## 수용 기준` AC-NNN ↔ impl REQ `(from AC-NNN)` 인용 커버리지 + 리터럴 self-consistently-wrong 검출 + 참조 실재 + present-vs-예정 + 절차 의미) + Placeholder Leak 재검증 (module 단계 새로 생긴 영역) → `PASS` → **commit N+4** (검증 결과 메타)
9. **Step 6 — PR + 머지** — `git push -u origin docs/<epic-slug>` + `gh pr create --base <BASE>` (body = 설계 산출물 요약 + `Part of #<epic-issue>`) + `bash scripts/pr-finalize.sh`
   - **base 분기 (MUST)**: `gh pr create` 직전 epic 단위 stories.md 상단 `**Base Branch:**` 줄 매치 → `--base <매치 값>` (통합 브랜치 케이스, base = `feature/<slug>`). 매치 없음 → `--base main` (default). Step 0 의 `EnterWorktree` branch (`docs/<epic-slug>`) 도 동일 base 기반 — 절차 [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.
10. **Step 7 — ExitWorktree** + `end-run`

## 분기 / cycle (요약)

- ux-architect self-check FAIL → ux-architect 재진입 (cycle ≤ 2, prose 내부)
- **기술 스택 그릴미 (Step 2.9)** 미합의 (사용자가 스택 결정 못 냄 / 보류) → loop 진행 보류 + 사용자 위임 (강제 자율 결정 X). system-architect PASS 후 사용자가 스택 번복 원하면 새 cycle 신설 X — 기존 system-architect 재진입 (또는 `ESCALATE` → `/product-plan` 재진입) 경로 재활용.
- `UX_REFINE_READY` → designer 분기 (`/ux` 또는 `ux-refine-stage`)
- architecture-validator 1차 `FAIL` (Step 3.5) → system-architect 재진입 (cycle ≤ 2). 보통 Placeholder Leak 또는 공통 SSOT 룰 위반 영역.
- architecture-validator 2차 `FAIL` (Step 5) → 해당 module-architect 재진입 (Cross-Story Interface 영역 / Implementation Simulation gap / Origin Anchor — PRD AC 미인용·리터럴 불일치·절차 미충족 보강, cycle ≤ 2). 또는 system-architect 재진입 (모듈 의존 그래프 영역).
- module-architect `SPEC_GAP_FOUND` → module-architect (보강 케이스) cycle (≤ 2) → 신규 케이스 재진입
- system-architect / module-architect `NEW_DEP_ESCALATE` (새 외부 의존 = tech-review 미검증) → loop 자동 중단 X. 메인이 사용자에게 3안 제시: (1) **채택 + 수동 검증** — 사용자 승인 → 해당 architect 재진입 (architecture.md/adr.md 에 "사용자 승인, tech-review 미경유" 흔적 명시) (2) **대안 기술 우회** — 이미 tech-review 검증된 대안 지정 → architect 재진입 (3) **전체 원점 회귀** — `/architect-loop` 중단 + `/product-plan` 재진입 + 새 tech-review (기존 단방향 경로). (1)/(2) 재진입 cycle ≤ 2. **어느 옵션이든 tech-reviewer 재호출 없음 (단방향 catastrophic 보존)**.
- `*_ESCALATE` → 사용자 위임
- cycle 발생 시 working tree only — commit X. PASS 후만 commit.

## 후속 라우팅

- 본 loop clean → 자동 commit/PR + 머지 → 사용자에게 "`/impl-loop <epic-path>` 로 구현 진입할까요?" 안내
- 주의사항 → 사용자 결정 (수동)
- spec gap 발견 + cycle 한도 초과 → 사용자 위임 (`/product-plan` 재진입 권고)

## 참조

- 시퀀스 / loop 풀스펙: [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §4.2 (architect-loop 풀스펙)
- 절차 mechanics: [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1~§6
- 핸드오프(라우팅): [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §3 / 권한: [`harness/agent_boundary.py`](../harness/agent_boundary.py)
- 이슈 lifecycle: [`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md)
- 브랜치·커밋·PR 네이밍: [`docs/plugin/git-spec.md`](../docs/plugin/git-spec.md)
- agent 정의: [`agents/ux-architect.md`](../agents/ux-architect.md) / [`agents/system-architect.md`](../agents/system-architect.md) / [`agents/architecture-validator.md`](../agents/architecture-validator.md) / [`agents/module-architect.md`](../agents/module-architect.md)
