---
name: ux
description: 화면 UX 플로우 정의 + 디자인 시안 핸드오프를 ux-architect → designer → 사용자 PICK 순서로 진행하는 design-stage 스킬. 2 모드 — UX_FLOW (신규 화면 플로우, ux-design-stage) / UX_REFINE (기존 디자인 레이아웃·비주얼 개선, ux-refine-stage). 사용자가 "/ux", "ux", "화면 플로우 짜줘", "디자인 시안", "와이어프레임", "ux 다듬어", "디자인 개선", "레이아웃 개선" 등을 말할 때 반드시 이 스킬을 사용한다. `/issue-report` 의 DESIGN_ISSUE 후속 + `/architect-loop` 의 UX_REFINE_READY 후속. 코드 구현은 별도 (`/impl`).
---

# UX Stage Skill — 화면 플로우 + 디자인 핸드오프

> design handoff loop. **코드 변경 X (commit 없음)**. ux-architect 가 화면 플로우/와이어프레임 정의 → designer 가 시안 생성 → 사용자 PICK. 산출 = `docs/ux-flow.md` (+ 조건부 `docs/design.md`) + 시안 파일 + DESIGN_HANDOFF 패키지.

## Loop

`ux-design-stage` (UX_FLOW) / `ux-refine-stage` (UX_REFINE). loop 한눈 인덱스 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §7.0.

## 모드 판정 (진입 시)

| 모드 | 조건 | 시작 agent |
|---|---|---|
| **UX_FLOW** (ux-design-stage) | 신규 화면 플로우 정의 — PRD/스토리 화면 인벤토리 기반 와이어프레임 | ux-architect:UX_FLOW |
| **UX_REFINE** (ux-refine-stage) | 기존 디자인의 레이아웃·비주얼 개선 (이미 화면 존재) | ux-architect:UX_REFINE |

사용자 발화로 판정 — "새 화면 / 플로우 / 와이어프레임" = UX_FLOW, "다듬어 / 개선 / refine / 레이아웃" = UX_REFINE. 모호 시 사용자 역질문.

## Inputs (메인이 사용자에게 받아야 할 정보)

- 대상 화면/플로우 (PRD 화면 인벤토리 또는 사용자 지정)
- (UX_REFINE) 개선 대상 기존 화면 경로 (routes/screens 등)
- (선택) design medium — 미지정 시 designer 가 `docs/design.md` frontmatter `medium` detect + 역질문

## 비대상 (다른 skill 추천)

- 코드 구현 (UI 포함) → `/impl` (impl-ui-design-loop — designer step 자동 포함)
- 화면 없는 epic 설계 → `/architect-loop`
- 버그/이슈 분류 → `/issue-report`

## 절차 — UX_FLOW (ux-design-stage)

1. **Step 0** — `begin-run ux` (entry_point=ux). commit 없음 (design handoff).
2. **Step 2 — ux-architect:UX_FLOW** (5 카테고리 self-check 의무) → `UX_FLOW_READY`. 산출 = `docs/ux-flow.md` (+ 조건부 `docs/design.md` 시스템 토큰).
   - `UX_REFINE_READY` → UX_REFINE 모드로 전환 (아래 절차)
   - `UX_FLOW_ESCALATE` → 사용자 위임
3. **Step 3 — designer** → `PASS` (시안 생성). 환경 감지 = `docs/design.md` frontmatter `medium: pencil|html`. 부재 시 designer Step 0 에서 detect + 사용자 역질문.
   - `ESCALATE` → 사용자 위임
4. **Step 3.5 — 사용자 PICK** (helper begin/end-step 비대상, 컨벤션 `user-pick-3.5`): 메인이 시안 경로 (Pencil 캔버스 또는 `design-variants/<screen>-v<N>.html`) + node-id 안내 + OK/NG.
   - OK → **DESIGN_HANDOFF 패키지** (이슈 코멘트 + `docs/design.md` + 시안 파일) → 종료
   - NG → designer 재호출 (round 한도 X, sub_cycle `designer-ROUND-<n>`)
5. **Step 종료** — `end-run`.

## 절차 — UX_REFINE (ux-refine-stage)

위 UX_FLOW 와 동일하되:
- **Step 2 = ux-architect:UX_REFINE** (allowed_enums = `UX_REFINE_READY,UX_FLOW_ESCALATE`). 기존 화면 분석 → 개선 와이어프레임 (모든 기존 요소 보존, 재배치만) → `docs/ux-flow.md` 해당 화면 섹션만 update.
- **Step 2.5 — 사용자 승인** (helper 비대상, 컨벤션 `user-approval-2.5`): ux-architect `UX_REFINE_READY` 후 designer 진입 *전* 메인이 사용자에게 refine 결과 prose 발췌 + 진행 여부 확인. 거절 시 ux-architect 재호출 (cycle ≤ 2).
- 이후 Step 3 (designer) → Step 3.5 (사용자 PICK) = UX_FLOW 동일.

## 분기 / sub_cycles

- ux-architect self-check FAIL (UX_FLOW) / 사용자 거절 (UX_REFINE Step 2.5) → ux-architect 재진입 (cycle ≤ 2)
- designer `PASS` + 사용자 NG → `designer-ROUND-<n>` 재생성 (사용자 자유 결정, round 한도 X)
- designer `ESCALATE` / ux-architect `UX_FLOW_ESCALATE` → 사용자 위임
- cycle 발생 시 commit 없음 (design handoff loop 자체가 commit X)

## 후속 라우팅

- DESIGN_HANDOFF 완료 → 구현은 `/impl` (impl-ui-design-loop 자동 — designer step 포함)
- 결론 → 다음 호출 라우팅 진본 = [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §3.1

## 참조

- loop 인덱스: [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §7.0
- 절차 mechanics: [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1~§6
- 라우팅(핸드오프): [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §3.1
- agent 정의: [`agents/ux-architect.md`](../agents/ux-architect.md) / [`agents/designer.md`](../agents/designer.md)
- design 가이드: [`docs/plugin/design.md`](../docs/plugin/design.md)
