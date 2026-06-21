---
name: design
description: PRD/stories.md 머지 + epic/story 이슈 등록 *이후*, 1 epic 단위로 ux-architect / system-architect / architecture-validator / module-architect 를 호출하여 설계 산출물 (`docs/epics/.../ux-flow.md` + `docs/architecture.md` + `docs/conventions.md` + `docs/decisions/*.md` + `docs/epics/.../impl/*.md`) 을 작성하고 1 PR 로 머지하는 설계 루프 스킬. system freeze 이후에는 공통 task 와 Story 단위마다 module-architect → architecture-validator 를 interleave 하고, 마지막에 cross-story 통합 검증을 수행한다. 사용자가 "설계해줘", "design", "epic 설계", "/design <epic-path>", "ux-flow 부터", "impl 다 만들어줘" 등을 말할 때 반드시 이 스킬을 사용한다. `/spec` 의 후속. 구현 진입은 `/impl`, story/epic 제품 검수는 `/acceptance`.
---

# Design Skill — 1 epic 단위 설계 루프

> 본 스킬 = `/spec` 종료 후 사용자가 *명시 호출* 하는 설계 루프. 자동 진입 X. PRD/stories.md 가 main 머지된 상태 + epic/story 이슈 등록 완료 또는 명시적 미등록 marker 가 전제.

기본 공개 진입점은 `/spec -> /design -> /impl -> /acceptance` 다.

> 🔴 **분기 규칙 SSOT** — agent 결론 → 다음 호출 / retry 한도 / escalate 처리는 [`design-routing.md`](design-routing.md) 가 본 skill 의 단일 진본. 본 파일은 *진행 절차(Step)* 만 담는다. 분기·재진입·escalate 판단이 필요하면 그 파일을 읽는다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../docs/plugin/terms.md) 를 확인한다.

## Loop

- **loop**: `design`
- **entry_point**: `design` (begin-run 인자 — 사용자 명시 진입)
- **task_list** (Step 1): (UI epic) ux-architect:UX_FLOW → [기술 스택 그릴미 — 메인 직접, helper 비대상] → system-architect → architecture-validator(1차/system freeze) → [module-architect(common) → architecture-validator(공통 단위)]? → (module-architect(Story N) → architecture-validator(Story 단위)) × Story 수 → architecture-validator(cross-story 통합) · (UI-less epic) ux-architect 제외
- **advance**: `UX_FLOW_READY` → `PASS`(system) → `PASS`(1차 freeze) → [`PASS`(공통 MA) → `PASS`(공통 AV)]? → (`PASS`(Story MA) → `PASS`(Story AV)) × Story 수 → `PASS`(cross-story 통합)
- **expected_steps**: 4 + 2C + 2S (UI epic) / 3 + 2C + 2S (UI-less epic). S = Story 수, C = 공통 task 호출 있으면 1 없으면 0. 기술 스택 그릴미는 begin-step 비대상이라 미포함
- **분기 규칙**: [`design-routing.md`](design-routing.md)

본 skill 본문 = design 절차 풀스펙 진본. 절차 mechanics = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md).

## Inputs (메인이 사용자에게 받아야 할 정보)

- epic 경로 (필수, 예: `docs/epics/epic-01-<slug>/`)
- 또는 stories.md 경로 (메인이 epic dir 추출)
- (선택) 사용자가 명시한 design medium — 미지정 시 ux-architect 가 detect + 역질문

## 전제 조건 (진입 전 충족 의무)

- `docs/prd.md` (root) + epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 가 main 머지된 상태 (`/spec` Step 10 결과)
- epic + story 이슈 등록 완료 (`scripts/create_epic_story_issues.sh` 산출, stories.md 상단 `**GitHub Epic Issue:** [#NNN]` 마커 존재) 또는 명시적 미등록 marker (`**GitHub Epic Issue:** 미등록 (사유: …)`) 존재
- 미충족 시 → `/spec` 재진입 권고 (사용자에게 안내)

> **design → spec 되돌림(backpressure)**: 위 "미충족 시 `/spec` 재진입" 과, design 도중 architect 가 PRD/요구사항 부족(`ESCALATE`) · 미검증 새 외부 의존(`NEW_DEP_ESCALATE`)을 발견해 upstream 으로 되돌리는 것은 모두 같은 되돌림 원리다 — downstream 이 upstream 산출물 부족을 판단하면 upstream 으로 되돌려 보강한다. 예외가 아니라 정상 루프다. 원리 SSOT = [`workflow-router.md` 되돌림 원리](../../docs/plugin/workflow-router.md#되돌림backpressure-원리), 처리 진본 = [`design-routing.md` escalate 처리](design-routing.md#escalate-처리).

## 비대상 (다른 skill 추천)

- PRD 신규 / 변경 → `/spec`
- 구현 (task PR) → `/impl`
- 버그픽스 → `/impl`
- GitHub issue 초안/등록 → `/to-issue`
- 이미 설계 완료된 epic 의 일부 deep impl 보강 → `/impl` 또는 deep task 파일을 직접 지정하는 `/impl-loop`

## 사전 read (lazy — 필요시만, #400)

정상 흐름은 본 skill 본문 + 인용된 docs 섹션 링크 만으로 진행. 본문에 있는 순서 차단 훅 / Pre-flight gate / agent boundary 룰이 1차. *룰 모호 / 분기 발생* 시에만 [`design-routing.md`](design-routing.md) (분기 규칙) / `docs/plugin/loop-procedure.md` (절차 mechanics) / `issue-lifecycle.md` / `git-spec.md` 부분 read (grep + offset/limit). 용어·공개 진입점·분기 표현 수정/리뷰 시에만 `docs/plugin/terms.md` 를 확인한다. 통째 read 폐기 — 메인 cache_read 기준치 감축.

**프로젝트 SSOT 설계문서도 lazy-read 대상 — 메인은 전문 흡수 금지 (#768).** 위 플러그인 절차 문서뿐 아니라 **프로젝트 SSOT 설계문서** — `docs/index.md`, 전역 `architecture.md` / `conventions.md` / `decisions/`, epic 단위 `architecture.md` / `domain-model.md` 와 `impl-*.md` — 도 동일하게 lazy 다. 전문(full) read 는 **module-architect / architecture-validator 의 책임**이며, 메인은 슬림 포인터 작성·산출 적용에 필요한 **포인터 식별 수준**(grep + 해당 섹션 offset/limit) 만 확보한다. 메인이 "좋은 슬림 포인터를 쓰려면 SSOT 를 다 읽어야 한다"는 명분으로 설계문서·인접 impl 전문을 흡수하지 않는다 — 그렇게 하면 슬림 포인터([`loop-procedure.md`](../../docs/plugin/loop-procedure.md#호출-prompt-슬림-포인터-규약))가 줄이려던 메인 cache_read 가 오히려 팽창한다. 메인이 정당하게 read 하는 최소 범위 예시:

- `stories.md` 의 **해당 Story 섹션** (요구사항 진본 — module-architect 필수 read 목록에 빠져 있어 포인터에서 누락하면 안 됨, Step 4 참조)
- `architecture.md` 의 **`## Cross-Story Lessons` / 호출별 제약** (그 호출에 특유한 금지·불변)
- 산출 대상 **impl 번호 · write 경계**
- sub-agent 산출물을 *적용*할 때도 사전 전문 read 대신 **적용 지점 grep** (해당 심볼/섹션만)

## 워크트리 (기본 켜짐)

Step 0 진입 시 자동 `EnterWorktree(name="design-{ts_short}")`. 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정).

**Base ref 분기 (MUST, #424)**: epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 통합 브랜치 모드 — outer worktree base ref + `docs/<epic-slug>` branch 둘 다 integration branch 기반. 절차 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424).

## Pre-flight gate (Step 0 직후)

[`docs/plugin/issue-lifecycle.md` mid-flow 누락 차단](../../docs/plugin/issue-lifecycle.md#mid-flow-누락-차단-pre-flight-gate) 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

## Sub-agent prompt 작성 checkpoint (#780)

`ux-architect` / `system-architect` / `module-architect` / `architecture-validator` 호출 전, `begin-step` stdout 의 `[PROMPT_SLOT_CHECK]` 를 Agent prompt 작성 전에 읽는다. prompt 는 [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md) 3슬롯을 사용한다.

- **대상 + 읽을 진본**: `docs/index.md`, epic `stories.md`, 전역/epic `architecture.md`, `docs/conventions.md`, `docs/decisions/`, epic `domain-model.md`, 검토 대상 산출물 같은 SSOT 포인터만 둔다. 요구사항·계약·설계 결정을 prompt 에 전문 재기입하지 않는다.
- **worktree**: design worktree 활성 시 worktree 절대경로를 넣는다. main repo 절대경로를 worktree 경로처럼 넘기지 않는다.
- **이 호출 특유**: Step 2.9 그릴미 합의, Cross-Story Lessons, wave-plan 신호처럼 아직 진본에 없는 신호만 둔다. 모듈 분할 방식·알고리즘·검증 assert 방식 같은 방법 처방은 넣지 않는다.

## 기술 스택 그릴미 체크포인트 (Step 2.9 — system-architect 직전)

system-architect(Step 3) 호출 *직전*에 메인 Claude 가 사용자와 **직접** 기술 스택을 합의하는 체크포인트. system-architect 는 서브에이전트라 사용자와 직접 대화 불가 — 그릴미는 메인이 진행하고, **아직 어떤 SSOT 문서에도 없는 합의 결론**(미기록 결정)이므로 system-architect 호출 prompt 로 일회 전달하되, system-architect 가 그 결정을 `docs/conventions.md` 또는 `docs/decisions/NNNN-slug.md` 에 기록하도록 지시한다 (슬림 포인터 규약의 미기록 결정 예외 — [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#호출-prompt-슬림-포인터-규약)). 기존 `Step 2.5 사용자 PICK` (impl-ui-design-loop) 와 동형 — helper begin/end-step **비대상** (사용자 체크포인트). step 컨벤션 `tech-stack-grill-2.9`.

- **발동: 기본 ON.** 사용자 발화에 정규식 `(그릴미|기술\s*스택|스택)\s*(빼|없|말|알아서|생략)` 매치 시에만 skip (워크트리 빼 패턴 동형). skip 시 system-architect 가 기존대로 스택 자율 결정.
- **UI 판정과 무관** — UI epic (Step 2 ux-architect 후) / UI-less epic (Step 2 skip 후) 둘 다 항상 system-architect 직전에 위치.
- **진행**: 메인이 `docs/prd.md` + (있으면) `docs/tech-review.md` 를 read → 그릴미 패턴 (한 번에 한 질문 / 가설+권장안 제시 / 코드·문서 탐색 우선 / 결정나무 가지치기, [`spec-prd-reference.md`](../spec/spec-prd-reference.md) `## 그릴미 패턴` 차용) 으로 스택 합의. tech-review **축 2 권고** (스펙 강등 / 업그레이드 / 대안 기술) 를 사용자 눈앞에서 채택·미채택 결론까지 도출.
- **산출**: 별도 파일 X. 합의 결론 (채택 스택 + 축 2 권고 채택/미채택)은 **미기록 결정 예외**라 system-architect 호출 prompt 로 일회 전달하고, system-architect 가 `docs/conventions.md` 또는 `docs/decisions/NNNN-slug.md` 에 영구 기록한다. prompt 는 이 미기록 합의만 담고, root/epic 의 기존 설계 결정은 재기입하지 않는다 (슬림 포인터 규약 = [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#호출-prompt-슬림-포인터-규약)).
- **tech-review.md 미전달 케이스** (외부 의존 0 개 → `/tech-review` skip): 축 2 권고 영역만 N/A. 스택 합의 그릴미 자체는 그대로 진행 (외부 의존 없어도 언어·프레임워크·DB 등 핵심 스택 결정엔 사용자 참여).
- **미합의** (사용자가 스택 결정 못 냄 / 보류) 시 처리 = [`design-routing.md` escalate 처리](design-routing.md#escalate-처리).

## UI-less epic 분기 (Step 1 전 판정)

TaskCreate 직전 메인이 `docs/prd.md` 의 **"화면 인벤토리 + 대략적 플로우"** 섹션을 read 하고 판정한다. ux-architect 산출물(ux-flow.md)은 system-architect 의 "(있으면)" 선택 입력일 뿐이고 architecture-validator / module-architect 는 ux-flow 를 참조하지 않으므로, UI-less epic 에서 ux 단계 skip 은 후속 단계를 깨지 않는다.

| 판정 | 조건 | 행동 |
|---|---|---|
| **UI epic** | 유효 화면 (= `(UI 없음)` 아닌 항목) ≥ 1 개 | 평소대로 Step 2 ux-architect 진행 |
| **UI-less epic** | 화면 인벤토리 항목이 **전부 `(UI 없음)`** / 섹션 부재 / 유효 화면 0 개 | Step 1 TaskCreate 에서 **ux-architect 제외** + Step 2 skip (commit 1 없음) → Step 3 직행 |
| **모호** | 화면 인벤토리 일부만 UI / 판정 불확실 | **보수적으로 UI epic 진행** (skip 은 명백할 때만) |

- 판정은 메인 prose 자율 영역 — hook 강제 아님 ([`CLAUDE.md`](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)). PRD 화면 인벤토리는 자유 텍스트라 메인이 의미로 판정.
- UI-less 판정 시 expected_steps = `3 + 2C + 2S` (UI epic 은 `4 + 2C + 2S`). S = Story 수, C = 공통 task 호출 있으면 1 없으면 0.

## 절차 (요약)

상세 = 본 절차 + [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#진입-모델) Step mechanics.

단위 수의 의미: **S = Story 수, C = 공통 task 호출 있으면 1 없으면 0**. 옛 task 단위 K (~27) 처럼 task 파일 수만큼 architect 를 부르지 않는다. system freeze 이후에는 공통 task 묶음과 각 Story 묶음마다 생산과 검증을 붙여 진행한다.

1. **Step 0** — 워크트리 진입 + `EnterWorktree` + branch (`docs/<epic-slug>`) + `begin-run design`
2. **Step 1** — *UI 판정* (위 `## UI-less epic 분기`) 후 TaskCreate. UI epic → (ux-architect / system-architect / architecture-validator 1차 / 공통 task interleave 선택 / Story별 module-architect+architecture-validator / final cross-story architecture-validator). **UI-less epic → ux-architect 제외** 후 같은 interleave 흐름.
3. **Step 2 — ux-architect:UX_FLOW** (5 카테고리 self-check 의무) → `UX_FLOW_READY` → **commit 1** (epic 단위 `docs/epics/epic-NN-*/ux-flow.md`).
   - **UI-less epic 이면 본 Step 전체 skip** (commit 1 없음) → 바로 Step 2.9 (기술 스택 그릴미). ux-flow 경로는 system-architect 에 미전달 (원래 "(있으면)" 선택 입력이라 자연 처리)
4. **Step 2.9 — 기술 스택 그릴미** (메인 직접, 기본 ON + opt-out) — 위 `## 기술 스택 그릴미 체크포인트` 절차. helper begin/end-step 비대상 (commit 없음). 합의 결론은 미기록 결정 예외라 Step 3 system-architect prompt 로 일회 전달 + system-architect 가 SSOT 기록 (슬림 포인터 규약). opt-out 발화 매치 시 본 Step skip → Step 3 직행.
5. **Step 3 — system-architect** — `docs/architecture.md` append map + `docs/conventions.md`/`docs/decisions/NNNN-slug.md` 결정 + epic 단위 architecture.md (모듈 목록 + 의존 그래프 + **Contract Ledger** + 공통 task 목록 + Story → 모듈 매핑) + epic 단위 domain-model.md 산출. **Contract Ledger** = cross-task 계약(owner/producer/consumer/invariant/ordering/error mode/config/forbidden alternative)의 단일 원장, epic 단위 architecture.md `## Contract Ledger` 에 위치 (system-architect 작성, 이후 module-architect 가 CONTRACT_AMENDMENT 시 갱신). **호출 prompt = 슬림 포인터 규약** ([`loop-procedure.md`](../../docs/plugin/loop-procedure.md#호출-prompt-슬림-포인터-규약)): 기존 SSOT 문서(`docs/index.md`, PRD, 전역/epic architecture, conventions, decisions, stories)는 system-architect 가 자체 read 하므로 prompt 에 재기입하지 않고, **Step 2.9 합의 결론만 미기록 결정 예외로 전달**(그릴미 skip 케이스면 미전달 → 자율 결정) + system-architect 가 그 결정을 conventions/decisions 에 기록하도록 지시한다. `## impl 목차` 표 폐기 (task 단위 분할은 module-architect 영역).
6. **Step 3.5 — architecture-validator 1차** — system 산출물만 존재하는 시점에 적용 가능한 축을 검토한다. 핵심 축은 요구사항 출처 충실도, 설계 표준, Contract Ledger 충분성, 구현 순서(첫 제품 경계 동작 앞당김), system freeze 가능성이다. Cross-Story / impl 관련 검토는 impl 파일 작성 전이라 N/A. → `PASS` → **commit 2** (system-architect 산출물 일괄). **이후 system 문서 freeze** — Step 4 단위 검증 또는 Step 5 최종 검증 FAIL 이 와도 finding 분류가 `SYSTEM_BOUNDARY` 가 아니면 system-architect 재진입 X (stale 전파는 `CONTRACT_PROPAGATION` sweep).
7. **Step 4 — module-architect / architecture-validator 단위 interleave** — 공통 task 선행 검증 후 Story별 interleave 를 수행한다. 각 module-architect 호출 prompt = **슬림 포인터 규약** ([`loop-procedure.md`](../../docs/plugin/loop-procedure.md#호출-prompt-슬림-포인터-규약)): SSOT 포인터(`docs/index.md`, 전역 architecture/conventions/decisions, epic `architecture.md`/`domain-model.md`/`stories.md` + UI epic 이면 `ux-flow.md` + 코드 SSOT) + 대상 단위 + 호출별 핵심 제약 + 산출 경로·번호·write 경계. 결정·계약·요구사항 **전문을 prompt 에 재기입하지 않고** 포인터로 준다 — module-architect 와 architecture-validator 가 그 문서를 자체 read 한다. Story 요구사항 텍스트의 진본인 `stories.md` 해당 Story 섹션은 포인터에서 빠뜨리지 않는다 (빠지면 module 매핑만으로 Story impl 이 만들어져 요구사항 누락).
   - **Step 4.0 (공통 task 있으면)** — `mode=common` + **대상 = epic 단위 architecture.md 의 공통 task 섹션**(목록 전문 복사 X, 섹션 포인터로 지정) 으로 module-architect 호출. 산출 = 공통 task 의 impl 파일 N 개. 이어서 같은 공통 task 범위로 **module-architect(common) → architecture-validator(공통 단위)** 를 수행한다. `PASS` 전에는 Story 1 로 넘어가지 않는다. `PASS` 후 공통 산출물 freeze + commit.
   - **공통 task 없음 → 공통 단위 검증 없이 Story 1** 로 바로 진입한다. 공통-less epic 은 빈 공통 validation 을 만들지 않는다.
   - **Step 4.1 ~ 4.S (Story 순차)** — **대상 = Story N (`stories.md` 의 해당 Story 섹션 포인터)** 1 개씩 지정한다. 산출 = Story 안 task 의 impl 파일 N 개. module-architect 는 병렬 독립성보다 Story 동작 수직 슬라이스를 우선해 task를 자르고, 각 Story 완료 시 실제로 검증되는 동작과 첫 제품 경계 동작 증거 지점을 impl 산출물에 남긴다. 각 Story 마다 **module-architect(Story N) → architecture-validator(Story 단위)** 를 수행하고, `PASS` 전에는 다음 Story module-architect 를 호출하지 않는다. `PASS` 후 해당 Story 산출물 freeze + commit.
   - **Cross-Story Lessons** — 공통 단위/Story 단위 검증에서 확정된 횡단 규칙, validator finding 의 해결 내용, Contract Ledger 보강, "다음 Story 에 반드시 지켜야 할 금지/불변" 은 epic `architecture.md` 의 `## Cross-Story Lessons` 섹션(없으면 생성) 또는 Contract Ledger/common task 산출물 같은 SSOT 문서에 기록한다. 다음 module-architect prompt 에는 **SSOT 문서 기록 + 포인터 전달** 을 우선하고, prompt 직접 전달은 미기록 결정 예외일 때만 허용한다. 큰 본문을 매 Story prompt 에 반복 주입하지 않는다.
   - batch 모드 폐기 — Story 묶음 자체가 batch 의 본질 해결 (옛 batch 모드는 issue [#511](https://github.com/alruminum/dcNess/issues/511) 본질 해결로 자연 폐기)
8. **Step 5 — architecture-validator cross-story 통합** — 모든 공통/Story 단위가 architecture-validator `PASS` 로 freeze 된 뒤 수행하는 최종 안전망이다. 요구사항 출처 충실도, 설계 표준, 계약과 인터페이스, 제품 동작 슬라이스, 구현 가능성, drift와 scope, 표현 수준을 cross-story 관점으로 검토한다. 특히 Story 간 compose/wiring, forward-ref 회수, Contract Ledger sweep, Cross-Story Lessons 일관성, Story별 첫 제품 경계 동작 증거, cold-seat 구현 가능성, PRD origin 대조, impl 과상세화 검출을 확인한다. Must finding 마다 분류 동반 — `SYSTEM_BOUNDARY` → system-architect, `CONTRACT_PROPAGATION` → module-architect `mode=contract_sweep` (재설계 X), `TASK_LOCAL` → module-architect 보강 ([`design-routing.md`](design-routing.md#finding-분류-분기)). → `PASS` → **최종 검증 결과 commit** (검증 결과 메타)
   - **Step 5.0 — 병렬 wave 형식 사전 점검 (mechanical, #693)**: final validator 호출 *직전* 메인이 1회 실행 — `bash "$PLUGIN_ROOT/scripts/dcness-helper" wave-plan <epic impl 디렉토리>`. 출력 JSON 의 `format_unnormalized_slugs` 가 비어있지 않으면, 그 task 들의 `### 수정 허용` 형식이 wave-plan 파서 규격(bullet 당 순수 경로)과 어긋나 *조용히 직렬 강등*될 상태다. 해당 slug 를 validator 호출 prompt 에 신호로 전달(미기록 결정 예외, 슬림 포인터 규약)하고, validator 는 이를 `TASK_LOCAL` finding 으로 확정 → module-architect 보강(전용 헤더 + 순수 경로, 설명은 `# 주석`/blockquote)으로 교정한다. LLM 눈대중이 아닌 파서 실측이 진본이라 silent 강등을 막는다.
9. **Step 6 — PR + 머지** — `git push -u origin docs/<epic-slug>` + `gh pr create --base <BASE>` (body = 설계 산출물 요약 + `Part of #<epic-issue>`) + `bash scripts/pr-finalize.sh`
   - **base 분기 (MUST)**: `gh pr create` 직전 epic 단위 stories.md 상단 `**Base Branch:**` 줄 매치 → `--base <매치 값>` (통합 브랜치 케이스, base = `feature/<slug>`). 매치 없음 → `--base main` (default). Step 0 의 `EnterWorktree` branch (`docs/<epic-slug>`) 도 동일 base 기반 — 절차 [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424).
10. **Step 7 — ExitWorktree** + `end-run`

> 각 Step 의 agent 결론에 따른 분기·재진입·cycle 한도·escalate = [`design-routing.md`](design-routing.md). loop 종료 후 후속(`/impl` 안내 등)도 그 파일.

## validation provider resolve (Codex opt-in)

architecture-validator 1차와 단위/최종 검증 모두 호출 직전 provider 를 resolve 한다.

```bash
PROVIDER=$("$HELPER" routing resolve architecture-validator)
if [ "$PROVIDER" = "codex" ]; then
  # begin-step architecture-validator 는 기존 절차대로 먼저 호출.
  "$PLUGIN_ROOT/scripts/dcness-codex-validator" architecture-validator --prompt-file "$PROMPT_FILE"
else
  # 기존 Claude Agent(subagent_type="architecture-validator") 경로.
fi
```

Codex 분기는 read-only validation 전용이다. wrapper 가 Codex 마지막 응답을 저장하고 `end-step architecture-validator --prose-file ...` 까지 수행하므로 별도 end-step 중복 호출 금지.

## 참조

- 분기 규칙 (결론→다음 / retry / escalate): [`design-routing.md`](design-routing.md) — 본 skill 분기 규칙 SSOT
- 용어 사전: [`docs/plugin/terms.md`](../../docs/plugin/terms.md)
- loop spec: 본 skill `## Loop` + 본문 (design 절차 풀스펙). 공통 절차 mechanics = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#진입-모델)
- 절차 mechanics: [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md) 의 Step mechanics
- 권한 경계: [`harness/agent_boundary.py`](../../harness/agent_boundary.py)
- 이슈 lifecycle: [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md)
- 브랜치·커밋·PR 네이밍: [`docs/plugin/git-spec.md`](../../docs/plugin/git-spec.md)
- agent 정의: [`agents/ux-architect.md`](../../agents/ux-architect.md) / [`agents/system-architect.md`](../../agents/system-architect.md) / [`agents/architecture-validator.md`](../../agents/architecture-validator.md) / [`agents/module-architect.md`](../../agents/module-architect.md)
