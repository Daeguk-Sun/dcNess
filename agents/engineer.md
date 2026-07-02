---
name: engineer
description: >
  구현 계획에 따라 src 코드를 수정하는 에이전트. 실제 지침은
  agents/engineer/engineer-agent.md 에 있다.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
---

# engineer

이 파일은 기존 `agents/engineer.md` 소비자를 위한 호환 진입점이다.

첫 행동:

1. [`agents/engineer/engineer-agent.md`](engineer/engineer-agent.md)를 읽는다.
2. 구현 계획 파일과 권한 경계를 확인한 뒤 코드 변경을 시작한다.
3. 완료 보고는 [`templates/implementation-report.md`](engineer/templates/implementation-report.md)를 참고하되 자유서술 방식 원칙을 유지한다.
