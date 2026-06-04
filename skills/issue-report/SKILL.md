---
name: issue-report
description: 버그/이슈를 자연어로 받아 qa 에이전트로 분류하고 다음 액션을 추천하는 스킬. 사용자가 "버그 있다", "이슈", "이상해", "안 돼", "오류", "이슈 리포팅", "이슈있다", "이슈왔쪄염", "뿌우 이슈 하나줄게", "뻐그있다", "버그있다" 등의 표현을 쓸 때 반드시 이 스킬을 사용한다. 분류 결과 (FUNCTIONAL_BUG / CLEANUP / DESIGN_ISSUE / KNOWN_ISSUE / SCOPE_ESCALATE) 에 따라 `/impl` 등 후속 skill 추천.
---

# Issue Report Skill

> 🔴 **라우팅 SSOT** — qa 분류 5종 (FUNCTIONAL_BUG / CLEANUP / DESIGN_ISSUE / KNOWN_ISSUE / SCOPE_ESCALATE) → 다음 호출 추천 / escalate / 후속은 [`issue-report-routing.md`](issue-report-routing.md) 가 본 skill 의 단일 진본. 본 파일은 *진행 절차 + input 명세* 만 담는다. 분기 판단이 필요하면 그 파일을 읽는다.

## Loop
- **loop**: `qa-triage`
- **entry_point**: `issue-report`
- **task_list** (Step 1): qa (1 step)
- **advance**: 개념 X — qa 분류 5 enum (FUNCTIONAL_BUG / CLEANUP / DESIGN_ISSUE / KNOWN_ISSUE / SCOPE_ESCALATE) → 후속 skill 추천 (자동 진입 X)
- **expected_steps**: 1
- **routing**: [`issue-report-routing.md`](issue-report-routing.md)

본 skill 본문 = qa-triage 풀스펙 (input 명세 + 라우팅 SSOT). 절차 mechanics = [`loop-procedure.md`](../../docs/plugin/loop-procedure.md).

## Inputs (메인이 사용자에게 받아야 할 정보)
- 이슈 제목 / 발화
- 재현 조건 (있으면)
- 화면·기능 / 예상 vs 실제 / 에러 메시지

명확화 안 되면 분석 시작 X (대기). qa agent 호출 *전* 위 항목 확보.

## 사전 read (lazy — 필요시만, #400)
정상 흐름은 본 skill 본문 + 인용된 docs 섹션 링크 만으로 진행. *룰 모호 / 분기 발생* 시에만 [`issue-report-routing.md`](issue-report-routing.md) (qa enum 별 라우팅) 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

## 절차
[`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md) 의 Step mechanics 따름. qa agent 분류 후 결론 → 다음 호출 추천 = [`issue-report-routing.md`](issue-report-routing.md). 후속 skill 자동 진입 X — 사용자 결정.
