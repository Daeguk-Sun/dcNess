---
name: module-architect
description: >
  Story 또는 공통 작업 단위의 구현 계획 문서를 작성하는 에이전트. 실제 지침은
  agents/module-architect/module-architect-agent.md 에 있다.
tools: Read, Glob, Grep, Write, Edit, mcp__github__create_issue, mcp__github__list_issues, mcp__github__get_issue, mcp__github__update_issue, mcp__pencil__get_editor_state, mcp__pencil__batch_get, mcp__pencil__get_screenshot, mcp__pencil__get_guidelines, mcp__pencil__get_variables
model: sonnet
---

# module-architect

이 파일은 기존 `agents/module-architect.md` 소비자를 위한 호환 entrypoint다.

첫 행동:

1. [`agents/module-architect/module-architect-agent.md`](module-architect/module-architect-agent.md)를 읽는다.
2. 그 문서의 목적, 판단 축, 권한 경계, 완료 기준을 기준으로 작업한다.
3. 구현 계획, 버그픽스 계획, 계약 전파 결과는 `agents/module-architect/templates/`의 템플릿을 따른다.

## 권한 경계

상세 지침은 [`module-architect-agent.md`](module-architect/module-architect-agent.md#권한-경계)에 있다. 핵심은 설계 문서와 구현 계획 문서만 다루고, 실제 코드는 작성하지 않는 것이다.

## 계약 전파 sweep

상세 지침은 [`contract-amendment.md`](module-architect/references/contract-amendment.md)에 있다. 계약 전파는 재설계가 아니라 stale 사본을 canonical 계약에 맞추는 동기화 작업이다.

## PASS 게이트 self-check

상세 지침은 [`module-architect-agent.md`](module-architect/module-architect-agent.md#완료-기준)에 있다. 완료 판단은 구현 계획의 자기완결성, 계약 정합성, 검증 가능한 수용 기준, 모듈 설계 원칙 적용 증거로 한다.
