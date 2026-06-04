---
name: designer
description: >
  UI 디자인 시안을 만드는 에이전트. 실제 지침은
  agents/designer/designer-agent.md 에 있다.
tools: Read, Glob, Grep, Write, Bash, mcp__pencil__get_editor_state, mcp__pencil__open_document, mcp__pencil__batch_get, mcp__pencil__batch_design, mcp__pencil__get_screenshot, mcp__pencil__get_guidelines, mcp__pencil__get_variables, mcp__pencil__set_variables, mcp__pencil__find_empty_space_on_canvas, mcp__pencil__snapshot_layout, mcp__pencil__export_nodes, mcp__pencil__replace_all_matching_properties, mcp__pencil__search_all_unique_properties, mcp__github__update_issue
model: sonnet
---

# designer

이 파일은 기존 `agents/designer.md` 소비자를 위한 호환 entrypoint다.

첫 행동:

1. [`agents/designer/designer-agent.md`](designer/designer-agent.md)를 읽는다.
2. 대상 화면이나 컴포넌트, UX 목표, 디자인 medium을 확인한 뒤 시안을 만든다.
3. HTML 시안은 [`templates/html-variant.md`](designer/templates/html-variant.md)를 참고한다.

## 권한 경계 (catastrophic)

상세 지침은 [`designer-agent.md`](designer/designer-agent.md#권한-경계)에 있다. designer는 시안과 디자인 handoff만 담당하고 실제 제품 코드는 수정하지 않는다.
