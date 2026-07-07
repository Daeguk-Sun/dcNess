---
name: design
description: PRD/stories.md 머지 + epic/story 이슈 등록 이후, 1 epic 단위로 선택 ux-architect / module-architect / architecture-validator 를 호출하여 agent-first 설계 산출물 (선택 `docs/epics/.../ux-flow.md` + `docs/design.md` + 선택 `docs/design-variants/*.html` + `docs/decisions/*.md` + `docs/epics/.../architecture.md` 최소형 + 선택 `docs/epics/.../domain-model.md` + `docs/epics/.../impl/*.md`) 을 작성하고 PR 로 머지하는 설계 루프 스킬. UI epic 은 system/module 설계 전에 목업 선행 여부를 확인하고, 목업=예 경로에서는 사용자 PICK 확정본을 system stage 입력으로 고정한다. 기존 모듈 topology 가 전혀 없는 greenfield 첫 설계에서는 system-architect(thin bootstrap)가 큰 모듈 경계만 1회 얇게 나눈 뒤 module-architect(epic-batch)로 이어진다. 그 외 기본 경로는 module-architect(epic-batch)가 epic architecture 최소형과 전체 impl 산출물을 하나의 컨텍스트에서 일괄 작성하고, architecture-validator(final epic 검증)가 최종 검증으로 수렴한다. 기존 모듈 경계·불변조건·public API boundary 변경 신호가 있을 때만 system-architect opt-in checkpoint 로 승격한다. 사용자가 "설계해줘", "design", "epic 설계", "/design <epic-path>", "ux-flow 부터", "impl 다 만들어줘" 등을 말할 때 반드시 이 스킬을 사용한다. `/spec` 의 후속. 구현 진입은 `/impl`, story/epic 제품 검수는 `/acceptance`.
---

# Design Skill — 1 epic 단위 설계 루프

> 본 스킬 = `/spec` 종료 후 사용자가 *명시 호출* 하는 설계 루프. 자동 진입 X. PRD/stories.md 가 main 머지된 상태 + epic/story 이슈 등록 완료 또는 명시적 미등록 marker 가 전제.

기본 공개 진입점은 `/spec -> /design -> /impl -> /acceptance` 다.

`/design` 은 사용자-facing 으로는 하나의 얇은 dispatcher 다. 진입 시 epic durable 산출물 실존 판정을 먼저 수행해 내부 stage 를 자동 선택하며, 사용자는 `design-ux` / `design-system` 이름을 알 필요가 없다. UI epic 에서 `ux-flow.md` 가 없으면 내부 [`design-ux`](../design-ux/SKILL.md) stage 를 실행해 UX 산출물을 자체 PR 로 먼저 머지한다. `ux-flow.md` 는 있으나 full design pack(`architecture.md` + `impl/NN-*.md`) 이 없으면 내부 [`design-system`](../design-system/SKILL.md) stage 를 실행한다. UI-less epic 은 `ux-flow.md` 가 원래 없으므로 기존처럼 곧장 system/module 설계 stage 로 들어가며 1 PR 흐름을 유지한다.

> 🔴 **분기 규칙 SSOT** — agent 결론 → 다음 호출 / retry 한도 / escalate 처리는 [`design-routing.md`](design-routing.md) 가 본 skill 의 단일 진본. 본 파일은 진행 절차만 담는다. 분기·재진입·escalate 판단이 필요하면 그 파일을 읽는다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../docs/plugin/terms.md) 를 확인한다.

## Loop

- **loop**: `design`
- **entry_point**: `design` (begin-run 인자 — 사용자 명시 진입)
- **task_list** (Step 1): `/design` dispatcher 가 durable 산출물로 내부 stage 를 선택한다. stage 1 `design-ux` = 목업 선행 여부 checkpoint → ux-architect:UX_FLOW → 목업=예 한정 디자인 시스템 체크포인트 → 조건부 canvas-design → 사용자 PICK → stage 1 PR. 목업 없음 / opt-out / yolo 기본값 = 목업 없음 경로는 기존 UX stage 흐름을 유지하고 canvas-design 을 강제하지 않는다. stage 2 `design-system` = [기술 스택 그릴미 또는 기록된 스택 결정 확인-후-skip — 메인 직접, helper 비대상] → module-architect(epic-batch) → architecture-validator(final epic 검증). (UI-less epic) ux-architect 제외. 모듈 topology 부재 greenfield 첫 설계면 system-architect(thin bootstrap)를 module-architect 앞에 1회 추가한다. 기존 모듈 경계·불변조건·public API boundary 변경 신호가 있으면 system-architect opt-in checkpoint 를 module-architect 앞/뒤에 끼운다.
- **advance**: `UX_FLOW_READY` → 선택 `PASS`(thin bootstrap) → `PASS`(epic-batch) → `PASS`(final epic 검증). opt-in system checkpoint 는 `SYSTEM_CHECKPOINT_REQUIRED` → `PASS`(system) → module-architect 재진입.
- **expected_steps**: 3 (UI epic) / 2 (UI-less epic). 기술 스택 그릴미 또는 확인-후-skip 은 begin-step 비대상이라 미포함. thin bootstrap 또는 system checkpoint 승격 시 각각 +1.
- **분기 규칙**: [`design-routing.md`](design-routing.md)

본 skill 본문 = design 절차 풀스펙 진본. 절차 mechanics = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md).

## Inputs (메인이 사용자에게 받아야 할 정보)

- epic 경로 (필수, 예: `docs/epics/epic-01-<slug>/`)
- 또는 stories.md 경로 (메인이 epic dir 추출)

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

**프로젝트 SSOT 설계문서도 lazy-read 대상 — 메인은 전문 흡수 금지 (#768).** 위 플러그인 절차 문서뿐 아니라 프로젝트 SSOT 설계문서 — `docs/index.md`, 전역 `architecture.md` / `conventions.md` / `decisions/`, affected module 의 `docs/modules/<module-id>/`, epic 단위 `architecture.md` / 선택 `domain-model.md` 와 `impl-*.md` — 도 동일하게 lazy 다. 전문(full) read 는 module-architect / architecture-validator 의 책임이며, 메인은 슬림 포인터 작성·산출 적용에 필요한 포인터 식별 수준(grep + 해당 섹션 offset/limit) 만 확보한다.

메인이 정당하게 read 하는 최소 범위 예시:

- `stories.md` 의 Story 목록과 각 Story 헤더/완료 동작 위치
- `architecture.md` 의 모듈 목록 / 의존 그래프 / Story -> 모듈 매핑 위치
- 산출 대상 impl 번호 · write 경계
- sub-agent 산출물을 적용할 때도 사전 전문 read 대신 적용 지점 grep

## 워크트리 (기본 켜짐)

Step 0 진입 시 자동 `EnterWorktree(name="design-{ts_short}")`. 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정).

**Base ref 분기 (MUST, #424)**: epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 통합 브랜치 모드 — outer worktree base ref + `docs/<epic-slug>` branch 둘 다 integration branch 기반. 절차 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424).

## Pre-flight gate (Step 0 직후)

[`docs/plugin/issue-lifecycle.md` mid-flow 누락 차단](../../docs/plugin/issue-lifecycle.md#mid-flow-누락-차단-pre-flight-gate) 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

## Stage dispatcher (Step 0.5)

Pre-flight gate 직후 메인이 epic durable 산출물만 보고 내부 stage 를 고른다. 판정은 [`scripts/lib/epic_phase.mjs`](../../scripts/lib/epic_phase.mjs) 의 설계 완료 기준을 재사용한다.

| durable 상태 | 내부 stage | 사용자 표시 |
|---|---|---|
| `stories.md` 부재 | STOP | `/spec` 재진입 권고 |
| UI epic + `ux-flow.md` 부재 + full design pack 부재 | `design-ux` | `/design` (설계 미완) |
| `ux-flow.md` 존재 + full design pack 부재 | `design-system` | `/design` (ux 완료 · system 미완) |
| UI-less epic + full design pack 부재 | `design-system` | `/design` (설계 미완) |
| `architecture.md` 존재 AND `impl/NN-*.md` 1개 이상 존재 | 완료 | `/impl` 안내 |

full design pack 판정에서 `domain-model.md`, `tech-review.md`, `ux-flow.md` 는 선택 산출물이므로 설계 완료 조건에 넣지 않는다. UI-less epic 은 `ux-flow.md` 가 없기 때문에 기존 "설계 미완" 라벨을 유지하며, UX 완료로 오판하지 않는다.

내부 stage 는 helper run 에 stage marker 를 남긴다. stage 1 은 `begin-run design --stage design-ux`, stage 2 는 `begin-run design --stage design-system` 로 시작한다. `docs/metrics/design-runs.jsonl` 은 같은 `entry_point=design` 아래 stage 값을 기록해 기존 단일 run 수치와 stage별 run 수치를 구분한다.

## Sub-agent prompt 작성 checkpoint (#780)

`ux-architect` / `system-architect(thin bootstrap 또는 checkpoint)` / `module-architect` / `architecture-validator` 호출 전, `begin-step` stdout 의 `[PROMPT_SLOT_CHECK]` 를 Agent prompt 작성 전에 읽는다. prompt 는 [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md) 3슬롯을 사용한다.

- **대상 + 읽을 진본**: `docs/index.md`, epic `stories.md`, 전역/epic `architecture.md`, `docs/conventions.md`, affected module 의 `docs/modules/<module-id>/architecture.md` / `conventions.md`, `docs/decisions/`, 선택 epic `domain-model.md`, 검토 대상 산출물, 기존 코드의 계약 표면 코드 SSOT(포트, 도메인 타입, 공개 entrypoint) 포인터만 둔다. UI epic 의 `design-system` stage 에서 `system-architect` / `module-architect` / `architecture-validator` 를 호출할 때는 stage 1 UX 산출물 포인터도 기본 입력에 포함한다: UI epic 이면 `ux-flow.md` 포인터는 epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, 화면별 확정 목업 `docs/design-variants/<screen-id>.html` 또는 `확정본 없음`, `docs/design-variants/canvas.html` 포인터 또는 부재 신호, `ux-flow.md` 화면 인벤토리의 확정 목업 경로와 핵심 node-id 매핑. 확정본이 없는 화면은 `확정본 없음` 신호를 그대로 전달하고 목업 경로를 추론하지 않는다. UI-less epic 의 prompt 입력은 기존 system/module 설계 진본만 사용한다. 요구사항·계약·설계 결정을 prompt 에 전문 재기입하지 않는다. 모듈 docs 는 affected module 에 한정하고 무관한 모듈은 넣지 않는다. 계약 의미의 durable 진본은 module responsibility/public interface 와 decision 문서다.
- **worktree**: design worktree 활성 시 worktree 절대경로를 넣는다. main repo 절대경로를 worktree 경로처럼 넘기지 않는다.
- **이 호출 특유**: Step 2.9 그릴미 합의 또는 기록된 스택 결정 확인-후-skip 사실, artifact audit 결과, wave-plan 신호처럼 아직 진본에 없는 신호만 둔다. 모듈 분할 방식·알고리즘·검증 assert 방식 같은 방법 처방은 넣지 않는다.

## 기술 스택 그릴미 체크포인트 (Step 2.9 — module-architect 직전)

module-architect(epic-batch) 호출 직전 메인 Claude 가 사용자와 직접 기술 스택을 합의하거나, 이미 기록된 스택 결정이 있으면 확인 안내 후 skip 하는 체크포인트다. module-architect 는 서브에이전트라 사용자와 직접 대화할 수 없으므로, 미기록 합의만 prompt 로 일회 전달하고 module-architect 가 그 결정을 `docs/conventions.md` 또는 `docs/decisions/NNNN-slug.md` 에 기록하도록 지시한다. system checkpoint 로 승격된 경우에도 같은 합의 사실을 system-architect prompt 에 전달한다.

- **기록된 스택 결정 있으면 확인-후-skip**: `docs/conventions.md` 또는 `docs/decisions/**` 에 현재 epic 에 적용 가능한 언어/프레임워크/DB/외부 의존 결정이 실존하면, 메인은 사용자에게 "기록된 스택 결정이 있어 그릴미를 생략하고 이 결정을 사용한다" 고 한 줄 안내한 뒤 그릴미를 반복하지 않는다. 이 skip 사실은 module-architect prompt 의 미기록 신호로 한 번만 전달한다.
- **첫 epic 등 미기록 상태면 그릴미 유지**: 적용 가능한 결정이 없거나 tech-review 축 2 권고가 미해결이면 기존 그릴미 패턴을 진행한다. 한 번에 한 질문 / 가설+권장안 제시 / 코드·문서 탐색 우선 / 결정나무 가지치기 원칙을 따른다.
- **사용자 opt-out**: 사용자 발화에 정규식 `(그릴미|기술\s*스택|스택)\s*(빼|없|말|알아서|생략)` 매치 시 skip 한다.
- **UI 판정과 무관** — UI epic / UI-less epic 모두 module-architect 직전에 위치한다.
- **미합의** (사용자가 스택 결정 못 냄 / 보류) 시 처리 = [`design-routing.md` escalate 처리](design-routing.md#escalate-처리).

## UI-less epic 분기 (Step 1 전 판정)

TaskCreate 직전 메인이 `docs/prd.md` 의 "화면 인벤토리 + 대략적 플로우" 섹션을 read 하고 판정한다. ux-architect 산출물(ux-flow.md)은 module-architect 의 "(있으면)" 선택 입력일 뿐이므로, UI-less epic 에서 ux 단계 skip 은 후속 단계를 깨지 않는다.

| 판정 | 조건 | 행동 |
|---|---|---|
| **UI epic** | 유효 화면 (= `(UI 없음)` 아닌 항목) ≥ 1 개 | Step 2 ux-architect 진행 |
| **UI-less epic** | 화면 인벤토리 항목이 전부 `(UI 없음)` / 섹션 부재 / 유효 화면 0 개 | Step 1 TaskCreate 에서 ux-architect 제외 + Step 2 skip (commit 1 없음) → Step 2.9 |
| **모호** | 화면 인벤토리 일부만 UI / 판정 불확실 | 보수적으로 UI epic 진행 |

- 판정은 메인 prose 자율 영역 — hook 강제 아님 ([`CLAUDE.md`](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)).
- UI-less 판정 시 expected_steps = 2, UI epic 은 3.

## 목업 선행 체크포인트 (UI epic 한정)

UI epic 으로 판정되고 `design-ux` stage 를 선택한 직후 메인이 목업 선행 여부를 1회 묻는다. 목업=예 경로는 system stage 는 사용자 PICK 확정 이후에만 진입한다는 계약을 둔다. 목업 없음, 사용자 opt-out, 또는 yolo 모드에서는 yolo 기본값 = 목업 없음 으로 처리해 기존 흐름 그대로 진행한다.

- **목업 선행 여부 질문**: "이 UI epic 은 system/module 설계 전에 hi-fi 목업 PICK 을 먼저 확정할까요?" 처럼 사용자가 예/아니오를 판단할 수 있게 묻는다.
- **opt-out**: 사용자 발화에 정규식 `(목업|mockup|시안|디자인)\s*(빼|없|말|나중|생략)` 매치 시 목업 없음 으로 처리한다.
- **목업=예**: `design-ux` stage 안에서 디자인 시스템 체크포인트를 먼저 닫고, `hi-fi 목업 필요` 가 `필요` 인 화면만 canvas-design 으로 draft → 사용자 PICK → 확정본 승격 + canvas 등록을 수행한다.
- **목업 없음**: `ux-flow.md` 와 text wireframe 은 유지하되 canvas-design PICK 을 필수화하지 않는다. 후속 `design-system` 은 확정 목업 입력 없이 기존 system/module 설계 계약으로 진행한다.

디자인 시스템 체크포인트는 기술 스택 그릴미와 같은 확인-후-skip 패턴이다. `docs/design.md` 가 실존하고 현재 epic 에 유효하면 확인-후-skip 한다. 부재하거나 ad-hoc 베이스라인 문서가 있으면 사용자에게 참고 디자인 시스템을 요청하고, 외부 import 1회 변환으로 `docs/design.md` 에 흡수한 뒤 ux-architect prompt 에 참고 디자인 시스템 신호로 전달한다.

## 절차 (요약)

상세 = 본 절차 + [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#진입-모델) Step mechanics.

1. **Step 0** — 워크트리 진입 + `EnterWorktree` + branch (`docs/<epic-slug>`) + stage 선택 전 `begin-run design` 준비. 실제 stage run 은 dispatcher 판정 뒤 `begin-run design --stage design-ux` 또는 `begin-run design --stage design-system` 로 시작한다.
2. **Step 0.5 — stage dispatcher** — durable 산출물 실존 판정으로 `design-ux` 또는 `design-system` 을 선택한다. 내부 stage 절차 전문은 각 stage skill 을 로드한다.
3. **Step 1 — UI 판정 + 목업 선행 여부 + topology 부재 판정 후 TaskCreate.** `design-ux` stage 에서는 목업 선행 여부와 디자인 시스템 체크포인트를 메인이 처리하고 ux-architect(+목업=예 한정 조건부 canvas-design) 만 TaskCreate 한다. `design-system` stage 에서는 module-architect(epic-batch) / architecture-validator(final epic 검증)를 TaskCreate 한다. UI-less epic → ux-architect 제외. greenfield 첫 설계에서 `docs/architecture.md` root anchor 의 큰 모듈 topology 가 비어 있고 어떤 `docs/epics/**/architecture.md` 에도 유효 `## 모듈 목록` row 가 없으면 system-architect(thin bootstrap)를 module-architect 앞에 1회 배치한다. 이 thin bootstrap 뒤에는 architecture-validator 를 끼우지 않고 바로 module-architect 로 간다. system checkpoint 는 기본 TaskCreate 에 넣지 않고, boundary 변경 신호가 있을 때만 추가한다.
4. **Stage 1 — design-ux / ux-architect:UX_FLOW** (UI epic 한정) → `UX_FLOW_READY` → stage 1 PR (epic 단위 `docs/epics/epic-NN-*/ux-flow.md`, 조건부 `docs/design.md`, 조건부 `docs/design-variants/`)
   - `UX_REFINE_READY` 로 `/design` 안에서 designer 후속이 필요하면, designer 호출 전 `/ux` 의 "designer 진입 공통 preflight" 와 동일하게 `docs/design-variants/` seed 보장 후 designer 로 진행한다.
5. **Stage 2 — design-system / 기술 스택 그릴미 또는 기록된 스택 결정 확인-후-skip** — 메인 직접, helper begin/end-step 비대상. 미기록 합의 또는 skip 사실은 thin bootstrap 이 있으면 Step 2.95 prompt 로, 없으면 Step 3 prompt 로 전달한다.
6. **Stage 2 — system-architect(THIN_BOOTSTRAP, 조건부 1회)** — topology 부재 greenfield 첫 설계에서만 실행한다. UI epic 이면 prompt 의 "대상 + 읽을 진본" 에 stage 1 UX 산출물(epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, 화면별 확정 목업 또는 `확정본 없음`, canvas 포인터 또는 부재 신호)을 함께 넣어 큰 모듈 경계가 화면 흐름·상태 기준을 모른 채 시작하지 않게 한다. 산출은 큰 모듈 목록(책임 + 공개 인터페이스 한 줄), 의존 그래프, 기술 스택/전역 decision 기록으로 제한한다. 도메인 모델 작성/생략 판단, 계약 표면 코드 SSOT 대조, Module Design Check evidence, Agent Operability 상세, impl task 작성은 하지 않는다. `PASS` 후 검증 step 없이 바로 module-architect(epic-batch)로 간다.
7. **Stage 2 — module-architect(epic-batch)** — epic architecture 최소형과 epic 전체 impl 산출물을 하나의 컨텍스트에서 일괄 작성한다. Story 단위 작성 주체로 쪼개지 않는다. 입력은 전체 `stories.md`, 기존 epic `architecture.md`(있으면), 선택 `domain-model.md`, UI epic 이면 epic `ux-flow.md`, `docs/design.md` 포인터 또는 부재 신호, `ux-flow.md` 화면 인벤토리의 확정 목업 경로, 화면별 확정 목업 `docs/design-variants/<screen-id>.html` 또는 `확정본 없음`, `docs/design-variants/canvas.html` 포인터 또는 부재 신호, 핵심 node-id 매핑, `docs/conventions.md`, affected module docs, `docs/decisions/**`, thin bootstrap 산출물이 있으면 root topology/decision 포인터, 계약 표면 코드 SSOT 포인터다. domain-model.md 생략 가능 여부는 도메인 복잡도 기준으로 판단하고 생략 판단 근거를 epic architecture 에 남긴다. 산출물은 epic `architecture.md` 의 durable 3섹션(모듈 목록, 의존 그래프, Story -> 모듈 매핑), 필요 시 `domain-model.md`, decision 문서, 공통 task 와 모든 Story 의 `impl/NN-*.md` 전체다. Story -> 모듈 매핑은 구현 순서(첫 제품 경계 동작 앞당김) 관점에서 첫 제품 경계 동작 증거가 어느 Story/task 묶음에서 닫히는지 설명한다. 각 impl task 는 `risk / engine / depends_on`, `수정 허용`, module/decision references, Story 동작 수직 슬라이스, 각 Story 완료 시 실제로 검증되는 동작, 첫 제품 경계 동작 증거 지점, owner/entrypoint 요약을 계속 충족해야 한다. 공통 task 가 있으면 같은 batch 안에서 먼저 필요한 기반 task 로 배치한다.
   - **규모 preflight**: Step 3 진입 전 메인이 Story 수와 예상 full design pack 규모를 [`deliverables-map.md`](../../docs/plugin/deliverables-map.md) 의 target 1,500줄 / hard warning 2,000줄 예산에 맞춰 빠르게 추정한다. 2,000줄 초과가 예상되거나 impl task 수가 한 sub-agent 출력 한계에 몰릴 정도로 크면 자동으로 얇은 batch 를 진행하지 말고 사용자에게 epic 분할 또는 예외적 batch 2분할을 위임한다. batch 2분할을 선택해도 Story 단위 작성/검증 기본값 복원이 아니며, 분할 경계·공유 계약을 epic architecture module responsibility / decision 에 먼저 남기고 final epic 검증은 전체 산출물 기준으로 한 번 더 수행한다.
   - **기본값 금지**: 모든 Story 에 단위 검증을 기본값으로 복원하지 않는다. 고위험 신호가 뒤늦게 드러나면 메인 판단으로 추가 검증 또는 사용자 위임을 선택할 수 있지만, 기본 루프는 epic-batch 생산 + final epic 검증이다.
   - **계약 변경**: public contract 를 만들거나 바꾸면 module responsibility / public interface 와 `docs/decisions/NNNN-slug.md` 를 갱신하고 impl 문서는 module/decision 참조만 가리킨다.
   - **system checkpoint 승격**: 기존 모듈 경계, 도메인 invariant, storage policy, public API boundary, 기존 전역 decision 변경이 필요하면 `SYSTEM_CHECKPOINT_REQUIRED` 로 보고한다. 신규 epic-scope decision 기록은 module-architect 자율 범위다. 메인은 system-architect opt-in checkpoint 를 호출하고, PASS 후 module-architect(epic-batch)를 재진입한다.
8. **Stage 2 — mechanical pre-final checks** — final validator 호출 직전 메인이 1회 실행한다: `bash "$PLUGIN_ROOT/scripts/dcness-helper" normalize-scope <epic impl 디렉토리>` → `bash "$PLUGIN_ROOT/scripts/dcness-helper" wave-plan <epic impl 디렉토리>` → `node "$PLUGIN_ROOT/scripts/check_design_artifact_structure.mjs" --root "$PROJECT_ROOT"`. artifact audit 의 legacy Contract Ledger / Contract References 경고는 구양식 유효성 신호이며 그 자체로 final validator 진입을 막지 않는다. normalizer/wave-plan 에 `unresolved_slugs` 또는 `format_unnormalized_slugs` 가 남으면 해당 slug 만 final validator prompt 의 미기록 신호로 전달한다.
9. **Stage 2 — architecture-validator final epic 검증** (기존 절차명: **Step 4 — architecture-validator final epic 검증**) — epic 전체 산출물을 한 번에 검증한다. 요구사항 출처 충실도, 설계 표준, 계약과 인터페이스, 제품 동작 슬라이스, Story 간 compose/wiring, cold-seat 구현 가능성, PRD origin 대조, impl 과상세화, domain-model 작성/생략 근거, 계약 표면 코드 SSOT 대조 증거를 본다. ux-flow·stories prose·legacy Contract Ledger/References 같은 비규범/구양식 층의 stale 은 형식만으로 Must finding 으로 올리지 않는다. Must finding 마다 `SYSTEM_BOUNDARY` / `TASK_LOCAL` 분류를 붙인다. → `PASS` → 최종 검증 결과 commit.
10. **Step 5 — end-run + design run 기록 freeze** — 각 stage PR 생성 전에 `bash "$PLUGIN_ROOT/scripts/dcness-helper" end-run` 을 실행한다. end-run 안전망이 finalize-run/review 를 만들고, review.md 안에 CLAUDE.md/AGENTS.md 현행화 후보 read-only 섹션을 포함한다. `/design` run 이면 현재 design worktree 의 `docs/metrics/design-runs.jsonl` 도 갱신한다. 이 파일은 design 산출물이므로 같은 PR 에 포함되어야 한다. PR/merge 뒤에 end-run 을 미루면 worktree 또는 main working tree 에 uncommitted metrics 가 고립되므로 금지한다.
11. **Step 6 — PR + main 머지 직전 사용자 확인 + ExitWorktree** — `git push -u origin docs/<epic-slug>` + `gh pr create --base <BASE>` (body = 설계 산출물 요약 + `Part of #<epic-issue>`) 후, main 머지 직전 사용자 확인 checkpoint 를 1회 둔다. stage 1 PR 은 UX 산출물 요약과 diff 규모를, stage 2 PR 은 산출물 요약(전역 architecture/conventions/decisions/epic architecture/domain-model/impl 파일 목록)과 diff 규모(`git diff --stat <BASE>...HEAD`, 설계 pack 줄 수/파일 수)를 제시하고 진행 여부를 묻는다. yolo 모드(`yolo` / `auto` / `끝까지` / `막힘 없이` / `다 알아서`)에서는 이 확인을 생략한다. 확인 응답 전에는 `scripts/pr-finalize.sh` 를 호출하지 않는다. 확인 또는 yolo skip 후 `bash scripts/pr-finalize.sh` → merge/main sync 완료 후 ExitWorktree.
   - **base 분기 (MUST)**: `gh pr create` 직전 epic 단위 stories.md 상단 `**Base Branch:**` 줄 매치 → `--base <매치 값>` (통합 브랜치 케이스, base = `feature/<slug>`). 매치 없음 → `--base main` (default). Step 0 의 `EnterWorktree` branch (`docs/<epic-slug>`) 도 동일 base 기반 — 절차 [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424).

> 각 Step 의 agent 결론에 따른 분기·재진입·cycle 한도·escalate = [`design-routing.md`](design-routing.md). loop 종료 후 후속(`/impl` 안내 등)도 그 파일.

## validation provider resolve (Codex opt-in)

architecture-validator final epic 검증 호출 직전 provider 를 resolve 한다.

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"

PROVIDER=$("$HELPER" routing resolve architecture-validator)
if [ "$PROVIDER" = "codex" ]; then
  "$PLUGIN_ROOT/scripts/dcness-codex-validator" architecture-validator --prompt-file "$PROMPT_FILE"
else
  Agent(subagent_type="architecture-validator", ...)
fi
```

이 절의 Codex 분기는 `architecture-validator` read-only validation 전용이다. wrapper 가 Codex 마지막 응답을 저장하고 `end-step architecture-validator --prose-file ...` 까지 수행하므로 별도 end-step 중복 호출 금지.

## 참조

- 분기 규칙 (결론→다음 / retry / escalate): [`design-routing.md`](design-routing.md) — 본 skill 분기 규칙 SSOT
- 용어 사전: [`docs/plugin/terms.md`](../../docs/plugin/terms.md)
- loop spec: 본 skill `## Loop` + 본문. 공통 절차 mechanics = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#진입-모델)
- 절차 mechanics: [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md) 의 Step mechanics
- 권한 경계: [`harness/agent_boundary.py`](../../harness/agent_boundary.py)
- 이슈 lifecycle: [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md)
- 브랜치·커밋·PR 네이밍: [`docs/plugin/git-spec.md`](../../docs/plugin/git-spec.md)
- agent 정의: [`agents/ux-architect.md`](../../agents/ux-architect.md) / [`agents/system-architect.md`](../../agents/system-architect.md) / [`agents/architecture-validator.md`](../../agents/architecture-validator.md) / [`agents/module-architect.md`](../../agents/module-architect.md)
