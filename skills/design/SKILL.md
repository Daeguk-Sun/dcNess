---
name: design
description: PRD/stories.md 머지 + epic/story 이슈 등록 이후, 1 epic 단위로 ux-architect / system-architect / module-architect / architecture-validator 를 호출하여 설계 산출물 (`docs/epics/.../ux-flow.md` + `docs/architecture.md` + `docs/conventions.md` + `docs/decisions/*.md` + `docs/epics/.../architecture.md` + 선택 `docs/epics/.../domain-model.md` + `docs/epics/.../impl/*.md`) 을 작성하고 1 PR 로 머지하는 설계 루프 스킬. system freeze 뒤에는 module-architect(epic-batch)가 epic 전체 impl 산출물을 하나의 컨텍스트에서 일괄 작성하고, architecture-validator(final epic 검증)가 최종 검증으로 수렴한다. 사용자가 "설계해줘", "design", "epic 설계", "/design <epic-path>", "ux-flow 부터", "impl 다 만들어줘" 등을 말할 때 반드시 이 스킬을 사용한다. `/spec` 의 후속. 구현 진입은 `/impl`, story/epic 제품 검수는 `/acceptance`.
---

# Design Skill — 1 epic 단위 설계 루프

> 본 스킬 = `/spec` 종료 후 사용자가 *명시 호출* 하는 설계 루프. 자동 진입 X. PRD/stories.md 가 main 머지된 상태 + epic/story 이슈 등록 완료 또는 명시적 미등록 marker 가 전제.

기본 공개 진입점은 `/spec -> /design -> /impl -> /acceptance` 다.

> 🔴 **분기 규칙 SSOT** — agent 결론 → 다음 호출 / retry 한도 / escalate 처리는 [`design-routing.md`](design-routing.md) 가 본 skill 의 단일 진본. 본 파일은 진행 절차만 담는다. 분기·재진입·escalate 판단이 필요하면 그 파일을 읽는다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../docs/plugin/terms.md) 를 확인한다.

## Loop

- **loop**: `design`
- **entry_point**: `design` (begin-run 인자 — 사용자 명시 진입)
- **task_list** (Step 1): (UI epic) ux-architect:UX_FLOW → [기술 스택 그릴미 또는 기록된 스택 결정 확인-후-skip — 메인 직접, helper 비대상] → system-architect → architecture-validator(1차/system freeze) → module-architect(epic-batch) → architecture-validator(final epic 검증) · (UI-less epic) ux-architect 제외
- **advance**: `UX_FLOW_READY` → `PASS`(system) → `PASS`(1차 freeze) → `PASS`(epic-batch) → `PASS`(final epic 검증)
- **expected_steps**: 5 (UI epic) / 4 (UI-less epic). 기술 스택 그릴미 또는 확인-후-skip 은 begin-step 비대상이라 미포함
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

**프로젝트 SSOT 설계문서도 lazy-read 대상 — 메인은 전문 흡수 금지 (#768).** 위 플러그인 절차 문서뿐 아니라 프로젝트 SSOT 설계문서 — `docs/index.md`, 전역 `architecture.md` / `conventions.md` / `decisions/`, epic 단위 `architecture.md` / 선택 `domain-model.md` 와 `impl-*.md` — 도 동일하게 lazy 다. 전문(full) read 는 module-architect / architecture-validator 의 책임이며, 메인은 슬림 포인터 작성·산출 적용에 필요한 포인터 식별 수준(grep + 해당 섹션 offset/limit) 만 확보한다.

메인이 정당하게 read 하는 최소 범위 예시:

- `stories.md` 의 Story 목록과 각 Story 헤더/완료 동작 위치
- `architecture.md` 의 Contract Ledger / Flow Ownership Map / 구현 순서 위치
- 산출 대상 impl 번호 · write 경계
- sub-agent 산출물을 적용할 때도 사전 전문 read 대신 적용 지점 grep

## 워크트리 (기본 켜짐)

Step 0 진입 시 자동 `EnterWorktree(name="design-{ts_short}")`. 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정).

**Base ref 분기 (MUST, #424)**: epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 통합 브랜치 모드 — outer worktree base ref + `docs/<epic-slug>` branch 둘 다 integration branch 기반. 절차 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424).

## Pre-flight gate (Step 0 직후)

[`docs/plugin/issue-lifecycle.md` mid-flow 누락 차단](../../docs/plugin/issue-lifecycle.md#mid-flow-누락-차단-pre-flight-gate) 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

## Sub-agent prompt 작성 checkpoint (#780)

`ux-architect` / `system-architect` / `module-architect` / `architecture-validator` 호출 전, `begin-step` stdout 의 `[PROMPT_SLOT_CHECK]` 를 Agent prompt 작성 전에 읽는다. prompt 는 [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md) 3슬롯을 사용한다.

- **대상 + 읽을 진본**: `docs/index.md`, epic `stories.md`, 전역/epic `architecture.md`, `docs/conventions.md`, `docs/decisions/`, 선택 epic `domain-model.md`, 검토 대상 산출물, 기존 코드의 계약 표면 코드 SSOT(포트, 도메인 타입, 공개 entrypoint) 포인터만 둔다. 요구사항·계약·설계 결정을 prompt 에 전문 재기입하지 않는다.
- **worktree**: design worktree 활성 시 worktree 절대경로를 넣는다. main repo 절대경로를 worktree 경로처럼 넘기지 않는다.
- **이 호출 특유**: Step 2.9 그릴미 합의 또는 기록된 스택 결정 확인-후-skip 사실, artifact audit 결과, wave-plan 신호처럼 아직 진본에 없는 신호만 둔다. 모듈 분할 방식·알고리즘·검증 assert 방식 같은 방법 처방은 넣지 않는다.

## 기술 스택 그릴미 체크포인트 (Step 2.9 — system-architect 직전)

system-architect(Step 3) 호출 직전 메인 Claude 가 사용자와 직접 기술 스택을 합의하거나, 이미 기록된 스택 결정이 있으면 확인 안내 후 skip 하는 체크포인트다. system-architect 는 서브에이전트라 사용자와 직접 대화할 수 없으므로, 미기록 합의만 prompt 로 일회 전달하고 system-architect 가 그 결정을 `docs/conventions.md` 또는 `docs/decisions/NNNN-slug.md` 에 기록하도록 지시한다.

- **기록된 스택 결정 있으면 확인-후-skip**: `docs/conventions.md` 또는 `docs/decisions/**` 에 현재 epic 에 적용 가능한 언어/프레임워크/DB/외부 의존 결정이 실존하면, 메인은 사용자에게 "기록된 스택 결정이 있어 그릴미를 생략하고 이 결정을 사용한다" 고 한 줄 안내한 뒤 그릴미를 반복하지 않는다. 이 skip 사실은 system-architect prompt 의 미기록 신호로 한 번만 전달한다.
- **첫 epic 등 미기록 상태면 그릴미 유지**: 적용 가능한 결정이 없거나 tech-review 축 2 권고가 미해결이면 기존 그릴미 패턴을 진행한다. 한 번에 한 질문 / 가설+권장안 제시 / 코드·문서 탐색 우선 / 결정나무 가지치기 원칙을 따른다.
- **사용자 opt-out**: 사용자 발화에 정규식 `(그릴미|기술\s*스택|스택)\s*(빼|없|말|알아서|생략)` 매치 시 skip 한다.
- **UI 판정과 무관** — UI epic / UI-less epic 모두 system-architect 직전에 위치한다.
- **미합의** (사용자가 스택 결정 못 냄 / 보류) 시 처리 = [`design-routing.md` escalate 처리](design-routing.md#escalate-처리).

## UI-less epic 분기 (Step 1 전 판정)

TaskCreate 직전 메인이 `docs/prd.md` 의 "화면 인벤토리 + 대략적 플로우" 섹션을 read 하고 판정한다. ux-architect 산출물(ux-flow.md)은 system-architect 의 "(있으면)" 선택 입력일 뿐이므로, UI-less epic 에서 ux 단계 skip 은 후속 단계를 깨지 않는다.

| 판정 | 조건 | 행동 |
|---|---|---|
| **UI epic** | 유효 화면 (= `(UI 없음)` 아닌 항목) ≥ 1 개 | Step 2 ux-architect 진행 |
| **UI-less epic** | 화면 인벤토리 항목이 전부 `(UI 없음)` / 섹션 부재 / 유효 화면 0 개 | Step 1 TaskCreate 에서 ux-architect 제외 + Step 2 skip (commit 1 없음) → Step 2.9 |
| **모호** | 화면 인벤토리 일부만 UI / 판정 불확실 | 보수적으로 UI epic 진행 |

- 판정은 메인 prose 자율 영역 — hook 강제 아님 ([`CLAUDE.md`](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)).
- UI-less 판정 시 expected_steps = 4, UI epic 은 5.

## 절차 (요약)

상세 = 본 절차 + [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#진입-모델) Step mechanics.

1. **Step 0** — 워크트리 진입 + `EnterWorktree` + branch (`docs/<epic-slug>`) + `begin-run design`
2. **Step 1** — UI 판정 후 TaskCreate. UI epic → ux-architect / system-architect / architecture-validator 1차 / module-architect(epic-batch) / architecture-validator(final epic 검증). UI-less epic → ux-architect 제외.
3. **Step 2 — ux-architect:UX_FLOW** (UI epic 한정) → `UX_FLOW_READY` → commit 1 (epic 단위 `docs/epics/epic-NN-*/ux-flow.md`)
4. **Step 2.9 — 기술 스택 그릴미 또는 기록된 스택 결정 확인-후-skip** — 메인 직접, helper begin/end-step 비대상. 미기록 합의 또는 skip 사실만 Step 3 prompt 로 전달한다.
5. **Step 3 — system-architect** — 전역 append map, `docs/conventions.md`/`docs/decisions/**`, epic `architecture.md` 를 작성한다. domain 복잡도가 낮으면 `domain-model.md 생략 가능` 이며, 생략 판단 근거를 epic `architecture.md` 에 남긴다. 도메인 invariant / entity / value object / aggregate / domain service 가 구현 판단에 필요하면 `domain-model.md` 를 작성한다. system-architect 는 계약 표면 코드 SSOT 대조를 수행해 기존 포트, 도메인 타입, 공개 entrypoint 와 설계가 어긋나지 않는지 확인하고 그 증거를 산출물에 남긴다. → `PASS`
6. **Step 3.5 — architecture-validator 1차/system freeze** — system 산출물 기준으로 요구사항 출처, 설계 표준, Contract Ledger 충분성, 구현 순서(첫 제품 경계 동작 앞당김), Flow Ownership Map, domain-model 작성/생략 근거, 계약 표면 코드 SSOT 대조 증거를 검토한다. → `PASS` → commit 2. 이후 system 문서 freeze — final epic 검증 FAIL 이 와도 finding 분류가 `SYSTEM_BOUNDARY` 가 아니면 system-architect 재진입 X.
7. **Step 4 — module-architect(epic-batch)** — epic 전체 impl 산출물을 하나의 컨텍스트에서 일괄 작성한다. Story 단위 작성 주체로 쪼개지 않는다. 입력은 전체 `stories.md`, frozen epic `architecture.md`, 선택 `domain-model.md`, `ux-flow.md`, `docs/conventions.md`, `docs/decisions/**`, 계약 표면 코드 SSOT 포인터다. 산출물은 공통 task 와 모든 Story 의 `impl/NN-*.md` 전체이며, 각 impl task 는 `risk / engine / depends_on`, `수정 허용`, Contract Ledger row-key references, Story 동작 수직 슬라이스, 각 Story 완료 시 실제로 검증되는 동작, 첫 제품 경계 동작 증거 지점, Agent Workability 를 계속 충족해야 한다. 공통 task 가 있으면 같은 batch 안에서 먼저 필요한 기반 task 로 배치한다.
   - **규모 preflight**: Step 4 진입 전 메인이 Story 수와 예상 full design pack 규모를 [`deliverables-map.md`](../../docs/plugin/deliverables-map.md) 의 target 1,500줄 / hard warning 2,000줄 예산에 맞춰 빠르게 추정한다. 2,000줄 초과가 예상되거나 impl task 수가 한 sub-agent 출력 한계에 몰릴 정도로 크면 자동으로 얇은 batch 를 진행하지 말고 사용자에게 epic 분할 또는 예외적 batch 2분할을 위임한다. batch 2분할을 선택해도 Story 단위 작성/검증 기본값 복원이 아니며, 분할 경계·공유 계약을 epic architecture/Contract Ledger 에 먼저 남기고 final epic 검증은 전체 산출물 기준으로 한 번 더 수행한다.
   - **기본값 금지**: 모든 Story 에 단위 검증을 기본값으로 복원하지 않는다. 고위험 신호가 뒤늦게 드러나면 메인 판단으로 추가 검증 또는 사용자 위임을 선택할 수 있지만, 기본 루프는 epic-batch 생산 + final epic 검증이다.
   - **계약 변경**: public contract 를 만들거나 바꾸면 Contract Ledger 를 갱신하고 impl 문서는 row key 만 가리킨다.
8. **Step 5.0 — mechanical pre-final checks** — final validator 호출 직전 메인이 1회 실행한다: `bash "$PLUGIN_ROOT/scripts/dcness-helper" normalize-scope <epic impl 디렉토리>` → `bash "$PLUGIN_ROOT/scripts/dcness-helper" wave-plan <epic impl 디렉토리>` → `node "$PLUGIN_ROOT/scripts/check_design_artifact_structure.mjs" --root "$PROJECT_ROOT"`. artifact audit 가 `contract-ledger-missing-contract-column`, `contract-references-shape`, `contract-detail-copy`, `unknown-ledger-row-key` 를 보고하면 false-clean 방지를 위해 final validator 로 넘어가지 말고 해당 파일을 module-architect `mode=contract_sweep` 로 되돌린다. normalizer/wave-plan 에 `unresolved_slugs` 또는 `format_unnormalized_slugs` 가 남으면 해당 slug 만 final validator prompt 의 미기록 신호로 전달한다.
9. **Step 5 — architecture-validator final epic 검증** — epic 전체 산출물을 한 번에 검증한다. 요구사항 출처 충실도, 설계 표준, 계약과 인터페이스, 제품 동작 슬라이스, Story 간 compose/wiring, Contract Ledger sweep, cold-seat 구현 가능성, PRD origin 대조, impl 과상세화, domain-model 작성/생략 근거, 계약 표면 코드 SSOT 대조 증거를 본다. Must finding 마다 `SYSTEM_BOUNDARY` / `CONTRACT_PROPAGATION` / `TASK_LOCAL` 분류를 붙인다. → `PASS` → 최종 검증 결과 commit.
10. **Step 6 — end-run + design run 기록 freeze** — final epic architecture-validator `PASS` 직후, PR 생성 전에 `bash "$PLUGIN_ROOT/scripts/dcness-helper" end-run` 을 실행한다. end-run 안전망이 finalize-run/review 를 만들고, `/design` run 이면 현재 design worktree 의 `docs/metrics/design-runs.jsonl` 도 갱신한다. 이 파일은 design 산출물이므로 같은 PR 에 포함되어야 한다. PR/merge 뒤에 end-run 을 미루면 worktree 또는 main working tree 에 uncommitted metrics 가 고립되므로 금지한다.
11. **Step 7 — PR + 머지 + ExitWorktree** — `git push -u origin docs/<epic-slug>` + `gh pr create --base <BASE>` (body = 설계 산출물 요약 + `Part of #<epic-issue>`) + `bash scripts/pr-finalize.sh` → merge/main sync 완료 후 ExitWorktree.
   - **base 분기 (MUST)**: `gh pr create` 직전 epic 단위 stories.md 상단 `**Base Branch:**` 줄 매치 → `--base <매치 값>` (통합 브랜치 케이스, base = `feature/<slug>`). 매치 없음 → `--base main` (default). Step 0 의 `EnterWorktree` branch (`docs/<epic-slug>`) 도 동일 base 기반 — 절차 [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424).

> 각 Step 의 agent 결론에 따른 분기·재진입·cycle 한도·escalate = [`design-routing.md`](design-routing.md). loop 종료 후 후속(`/impl` 안내 등)도 그 파일.

## validation provider resolve (Codex opt-in)

architecture-validator 1차와 final epic 검증 모두 호출 직전 provider 를 resolve 한다.

```bash
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
