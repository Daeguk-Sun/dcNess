---
name: issue-report
description: 버그/이슈를 자연어로 받아 qa 에이전트로 분류하고 다음 액션을 추천하는 스킬. 사용자가 "버그 있다", "이슈", "이상해", "안 돼", "오류", "이슈 리포팅", "이슈있다", "이슈왔쪄염", "뿌우 이슈 하나줄게", "뻐그있다", "버그있다" 등의 표현을 쓸 때 반드시 이 스킬을 사용한다. 분류 결과 (FUNCTIONAL_BUG / CLEANUP / DESIGN_ISSUE / KNOWN_ISSUE / SCOPE_ESCALATE) 에 따라 후속 skill 추천.
---

# Issue Report Skill

## Loop
`qa-triage` (loop 인덱스 = [`loop-procedure.md`](../docs/plugin/loop-procedure.md) §7.0). 본 skill 본문 = qa-triage 풀스펙 (input 명세 + enum 별 라우팅 추천).

## Inputs (메인이 사용자에게 받아야 할 정보)
- 이슈 제목 / 발화
- 재현 조건 (있으면)
- 화면·기능 / 예상 vs 실제 / 에러 메시지

명확화 안 되면 분석 시작 X (대기). qa agent 호출 *전* 위 항목 확보.

## 후속 라우팅 추천 (qa enum 별)
- `FUNCTIONAL_BUG` → `impl-task-loop` (`/impl`) fallback path (impl 부재 시 module-architect 선두 추가)
- `CLEANUP` → `impl-task-loop` (`/impl`) fallback path
- `DESIGN_ISSUE` → `ux-design-stage` (`/ux` 또는 designer 직접)
- `KNOWN_ISSUE` → 종료
- `SCOPE_ESCALATE` → 사용자 위임 (큰 변경 / 다중 모듈)

후속 skill 자동 진입 X — 사용자 결정.

## 사전 read (lazy — 필요시만, #400)
정상 흐름은 본 skill 본문 + 인용된 docs §번호 만으로 진행. *룰 모호 / 분기 발생* 시에만 `docs/plugin/orchestration.md` §3.1 (routing 한눈표 — qa 행) 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

## 절차
[`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1~§6 (Step mechanics) 따름. qa-triage 풀스펙 = 본 파일 (input 명세 + enum 별 라우팅 추천).
