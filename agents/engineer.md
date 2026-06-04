---
name: engineer
description: >
  구현 계획에 따라 src 코드를 수정하는 에이전트. 실제 지침은
  agents/engineer/engineer-agent.md 에 있다.
tools: Read, Write, Edit, Bash, Glob, Grep, mcp__pencil__get_editor_state, mcp__pencil__batch_get, mcp__pencil__get_screenshot, mcp__pencil__get_guidelines, mcp__pencil__get_variables
model: sonnet
---

# engineer

이 파일은 기존 `agents/engineer.md` 소비자를 위한 호환 entrypoint다.

첫 행동:

1. [`agents/engineer/engineer-agent.md`](engineer/engineer-agent.md)를 읽는다.
2. 구현 계획 파일과 권한 경계를 확인한 뒤 코드 변경을 시작한다.
3. 완료 보고는 [`templates/implementation-report.md`](engineer/templates/implementation-report.md)를 참고하되 prose-only 원칙을 유지한다.

## 권한 경계 (catastrophic)

상세 지침은 [`engineer-agent.md`](engineer/engineer-agent.md#권한-경계)에 있다. 핵심은 `src/**` 구현만 담당하고, `docs/**`, git, PR, 이슈 상태 변경을 메인에게 남기는 것이다.

## 1 task = 1 PR (engineer 는 src 만)

상세 지침은 [`engineer-agent.md`](engineer/engineer-agent.md#권한-경계)에 있다. engineer는 working tree 변경물만 남기고, 커밋과 PR은 메인이 처리한다.
