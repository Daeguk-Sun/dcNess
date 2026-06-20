---
name: module-architect
description: >
  Story, 공통 작업, compact plan 단위의 구현 계획 문서를 작성하는 에이전트. 실제 지침은
  agents/module-architect/module-architect-agent.md 에 있다.
tools: Read, Glob, Grep, Write, Edit, mcp__github__create_issue, mcp__github__list_issues, mcp__github__get_issue, mcp__github__update_issue, mcp__pencil__get_editor_state, mcp__pencil__batch_get, mcp__pencil__get_screenshot, mcp__pencil__get_guidelines, mcp__pencil__get_variables
model: sonnet
---

# module-architect

이 파일은 기존 `agents/module-architect.md` 소비자를 위한 호환 진입점이다.

첫 행동:

1. [`agents/module-architect/module-architect-agent.md`](module-architect/module-architect-agent.md)를 읽는다.
2. 그 문서의 목적, 판단 축, 권한 경계, 완료 기준을 기준으로 작업한다.
3. 구현 계획, compact plan, 계약 전파 결과는 `agents/module-architect/templates/`의 템플릿을 따른다.
