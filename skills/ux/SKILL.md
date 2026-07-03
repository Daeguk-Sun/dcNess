---
name: ux
description: 구현 없이 목업과 흐름을 먼저 탐색하는 선행 디자인 utility. UX_FLOW(신규 화면 흐름) / UX_REFINE(기존 디자인 개선) 뒤 내부 canvas-design 을 얇게 감싸 drafts 반복 → 사용자 PICK → 확정본 승격 + canvas 등록으로 끝낸다. 사용자가 "/ux", "ux", "화면 플로우 짜줘", "디자인 시안", "와이어프레임", "ux 다듬어", "디자인 개선", "레이아웃 개선" 등을 말할 때 사용한다. 코드 구현은 `/impl`.
---

# UX Skill — 선행 디자인 탐색 wrapper

> `/ux` 는 구현 없이 디자인만 먼저 굴리고 싶을 때 쓰는 선행 탐색 경로다. 목업 생성·수정·확정은 내부 [`canvas-design`](../canvas-design/SKILL.md) 을 감싸는 얇은 wrapper 한 경로로만 수행한다. 산출 계약은 `docs/design-variants/` 확정본 규약과 동일하다: drafts 반복 → 사용자 PICK → 확정본 승격 + canvas 등록. 후속 `/impl` 은 머지된 확정본만 `기준 있음` 으로 이어받는다.

> 🔴 **분기 규칙 SSOT** — ux-architect / designer 결론 → 다음 호출 / 모드 전환 / cycle 한도 / escalate / 후속은 [`ux-routing.md`](ux-routing.md) 가 본 skill 의 단일 진본. 본 파일은 *진행 절차(Step)* 만 담는다. 분기·재진입·escalate 판단이 필요하면 그 파일을 읽는다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../docs/plugin/terms.md) 를 확인한다.

## Loop

- **loop**: `ux-design-stage` (UX_FLOW) / `ux-refine-stage` (UX_REFINE)
- **entry_point**: `ux` (UX_REFINE 는 refine 발화 동반)
- **task_list** (Step 1): ux-architect:UX_FLOW 또는 :UX_REFINE → 내부 canvas-design checkpoint → designer(필요 시) → 사용자 PICK
- **advance**: `UX_FLOW_READY` 또는 `UX_REFINE_READY` → `PASS`(canvas-design) → 종료
- **expected_steps**: 2 + 조건부 designer step. `canvas-design` 은 main-owned checkpoint 이며 helper begin/end-step 비대상이다.
- **분기 규칙**: [`ux-routing.md`](ux-routing.md)

본 skill 은 공개 workflow 가 아니라 utility 다. `/design` 은 product/technical design 을 다루고, `/impl` 은 구현한다. `/ux` 는 구현 PR 전에 목업과 흐름만 선행 탐색한다.

## worktree + commit/PR 계약

`/ux` 는 git-tracked 디자인 확정본을 만드는 action loop 다. Step 0 에서 공통 [`loop-procedure`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정) 의 worktree 분기를 따른다. 사용자가 명시적으로 워크트리 제외를 요청하지 않는 한 worktree 에서 진행한다.

canvas-design `PASS` 뒤 clean 이면 Step 7a 가 `/ux` 산출물만 명시 pathspec 으로 stage 해서 docs-only branch + PR 을 만든다. 포함 대상은 `docs/epics/<epic>/ux-flow.md`, 변경된 `docs/design.md`, `docs/design-variants/<screen-id>.html`, `docs/design-variants/canvas.html`, 새로 seed 된 `docs/design-variants/_lib/**` 이다.

PR merge 와 main sync 를 확인한 뒤에만 완료를 보고한다. 후속 `/impl` 은 머지된 확정본만 `기준 있음` 으로 이어받는다. PR/CI/merge 실패 시 `/impl` 기준 있음으로 안내하지 않고 중지한다. 확정본을 uncommitted 상태로 남긴 채 종료하지 않는다.

## 모드 판정 (진입 시)

| 모드 | 조건 | 시작 agent |
|---|---|---|
| **UX_FLOW** (ux-design-stage) | 신규 화면 플로우 정의 — PRD/스토리 화면 인벤토리 기반 와이어프레임 | ux-architect:UX_FLOW |
| **UX_REFINE** (ux-refine-stage) | 기존 디자인의 레이아웃·비주얼 개선 (이미 화면 존재) | ux-architect:UX_REFINE |

사용자 발화로 판정한다. "새 화면 / 플로우 / 와이어프레임" 은 UX_FLOW, "다듬어 / 개선 / refine / 레이아웃" 은 UX_REFINE 이다. 모호하면 사용자에게 한 번만 물어본다.

## Inputs

- 대상 화면/플로우 (PRD 화면 인벤토리, epic `ux-flow.md`, 또는 사용자 지정)
- (UX_REFINE) 개선 대상 기존 화면이나 확정 목업 경로
- (선택) GitHub issue 번호 — 대상이 있으면 시작 전 [`../../docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#github-project-status-lifecycle)에 따라 Project `Status=In progress` 로 이동한다.

## 비대상

- 코드 구현 (UI 포함) → `/impl`
- 제품/기술 설계 전체 → `/design`
- GitHub issue 초안/등록 → `/to-issue`

## ux-flow 화면 인벤토리 계약

UX_FLOW 산출 `docs/epics/<epic>/ux-flow.md` 의 화면 인벤토리는 `hi-fi 목업 필요` 열을 반드시 둔다. 값은 `필요/불필요` 중 하나로 쓴다.

- `필요`: 제품 첫 인상, 핵심 변환, 복잡한 상태, 구현자가 레이아웃을 오해하기 쉬운 화면. `canvas-design` 이 designer draft 를 만들 수 있다.
- `불필요`: 부수 화면, 단순 목록/설정/확인, 기존 패턴 반복. text wireframe 과 상태 설명으로 충분하다.
- 전 화면 일괄 목업화 금지. designer 는 `hi-fi 목업 필요` 가 `필요로 표시된 화면` 만 목업화한다.

UX_REFINE 은 기존 화면 섹션을 갱신할 때도 같은 열을 유지하고, 실제 visual draft 가 필요한 화면만 `필요` 로 표시한다.

## designer 진입 공통 preflight

designer 를 호출하는 모든 경로(UX_FLOW, UX_REFINE 사용자 승인 후, 사용자 PICK NG 의 `designer-ROUND-<n>`, `/design` 의 `UX_REFINE_READY` 후속)는 designer 호출 직전에 메인이 `docs/design-variants/` seed 를 보장한다.

- `/init-dcness` 기본 경로는 UI seed 를 설치하지 않을 수 있으므로 `docs/design-variants/_lib/` 와 `docs/design-variants/drafts/` 디렉터리를 만든다.
- `templates/design-variants/.gitignore`, `templates/design-variants/canvas.html`, `templates/design-variants/_lib/show-ids.js`, `templates/design-variants/_lib/canvas.js`, `templates/design-variants/drafts/.gitkeep` 를 각각 대응 경로로 복사한다.
- 기존 파일은 덮어쓰지 않는다. 기존 확정본과 `canvas.html` frame 은 유지한다.

## 절차 — UX_FLOW

1. **Step 0** — `begin-run ux` (entry_point=ux).
2. **Step 2 — ux-architect:UX_FLOW** → `UX_FLOW_READY`. 산출 = `docs/epics/epic-NN-<slug>/ux-flow.md` (+ 조건부 `docs/design.md` 시스템 토큰). 화면 인벤토리에 `hi-fi 목업 필요` 값을 표시한다.
   - `UX_REFINE_READY` → UX_REFINE 모드로 전환
   - `UX_FLOW_ESCALATE` → 사용자 위임
3. **Step 3 — canvas-design wrapper** — `hi-fi 목업 필요` 가 `필요로 표시된 화면` 만 내부 `canvas-design` 에 넘긴다. canvas-design 은 seed 보장, 필요 시 `begin-step designer`, draft 생성, 사용자 PICK, `docs/design-variants/<screen-id>.html` 확정본 승격, `docs/design-variants/canvas.html` canvas 등록까지 수행한다.
   - draft 산출물은 `docs/design-variants/drafts/<screen-id>-draft<N>.html`, `data-node-id`, `:root` CSS custom property 토큰을 포함한다.
   - 사용자 PICK NG → 공통 preflight 를 다시 확인한 뒤 `designer-ROUND-<n>` 으로 재생성한다. round 한도는 없다.
   - `PASS` → 확정 목업 경로와 핵심 node-id 매핑을 기록하고 종료
   - `ESCALATE` → 사용자 위임
4. **Step 종료** — `end-run` 뒤 clean 이면 commit/PR → merge → main sync. 후속 구현은 `/impl`.

## 절차 — UX_REFINE

UX_FLOW 와 동일하되:

- **Step 2 = ux-architect:UX_REFINE** (allowed_enums = `UX_REFINE_READY,UX_FLOW_ESCALATE`). 기존 화면 분석 → 개선 와이어프레임 → 대상 epic `ux-flow.md` 해당 화면 섹션만 update. `hi-fi 목업 필요` 열을 유지한다.
- **Step 2.5 — 사용자 승인** (helper 비대상, 컨벤션 `user-approval-2.5`): ux-architect `UX_REFINE_READY` 후 canvas-design 진입 전 메인이 refine 결과 prose 발췌 + 진행 여부를 확인한다. 거절 시 ux-architect 재호출 (cycle ≤ 2).
- 이후 공통 preflight → canvas-design wrapper → 필요 시 designer → 사용자 PICK → 확정본 승격 + canvas 등록.

## 종료 산출

- 확정 목업 경로: `docs/design-variants/<screen-id>.html`
- canvas 경로: `docs/design-variants/canvas.html`
- 핵심 node-id 매핑: `<data-node-id> -> 구현 컴포넌트/상태`
- 부수 화면 text wireframe: `docs/epics/<epic>/ux-flow.md`

## 참조

- 분기 규칙 (결론→다음 / 모드 전환 / cycle / escalate / 후속): [`ux-routing.md`](ux-routing.md)
- 내부 목업 변경 경로: [`canvas-design`](../canvas-design/SKILL.md)
- 공통 절차 mechanics: [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#진입-모델)
- agent 정의: [`agents/ux-architect.md`](../../agents/ux-architect.md) / [`agents/designer.md`](../../agents/designer.md)
- design 가이드: [`docs/plugin/design.md`](../../docs/plugin/design.md)
