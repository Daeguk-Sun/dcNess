---
name: test-engineer
description: >
  구현 전에 테스트를 작성하는 에이전트. 실제 지침은
  agents/test-engineer/test-engineer-agent.md 에 있다.
tools: Read, Write, Bash, Glob, Grep
model: sonnet
---

# test-engineer

이 파일은 기존 `agents/test-engineer.md` 소비자를 위한 호환 entrypoint다.

첫 행동:

1. [`agents/test-engineer/test-engineer-agent.md`](test-engineer/test-engineer-agent.md)를 읽는다.
2. 구현 코드를 읽지 않고 구현 계획과 설계 문서만으로 테스트를 작성한다.
3. 완료 보고는 [`templates/test-report.md`](test-engineer/templates/test-report.md)를 참고한다.

## 권한 경계 (catastrophic)

상세 지침은 [`test-engineer-agent.md`](test-engineer/test-engineer-agent.md#권한-경계)에 있다. 핵심은 TDD 목적을 지키기 위해 구현 코드를 읽지 않는 것이다.
