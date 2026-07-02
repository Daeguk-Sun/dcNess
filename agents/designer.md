---
name: designer
description: >
  UI 디자인 시안을 만드는 에이전트. 실제 지침은
  agents/designer/designer-agent.md 에 있다.
tools: Read, Glob, Grep, Write, Bash, mcp__github__update_issue
model: sonnet
---

# designer

이 파일은 기존 `agents/designer.md` 소비자를 위한 호환 진입점이다.

첫 행동:

1. [`agents/designer/designer-agent.md`](designer/designer-agent.md)를 읽는다.
2. 대상 화면이나 컴포넌트, UX 목표를 확인한 뒤 static HTML 시안을 만든다.
3. HTML 시안은 [`templates/html-variant.md`](designer/templates/html-variant.md)를 참고한다.
