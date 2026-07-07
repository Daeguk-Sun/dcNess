---
name: designer
description: >
  UI 디자인 시안을 만드는 에이전트. 실제 지침은
  docs/plugin/agents/designer/designer-agent.md 에 있다.
tools: Read, Glob, Grep, Write, Bash, mcp__github__update_issue
model: sonnet
---

# designer

이 파일은 기존 `agents/designer.md` 소비자를 위한 호환 진입점이다.

> **지침 경로 해소 (외부 활성 프로젝트).** 아래 상대경로는 현재 프로젝트 cwd 가 아니라 **활성 dcNess plugin 디렉터리 기준**이다. 호출 prompt 에 전체 지침 절대경로가 주어졌으면 그것을 Read 한다. 없으면 활성 plugin root 아래에서 찾는다 — Bash 가 있으면 `$CLAUDE_PLUGIN_ROOT` (없으면 `ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1`, 로컬 marketplace 설치면 `$HOME/.claude/plugins/marketplaces/dcness`), 없으면 Glob 으로 최고 버전 경로를 고른다. `${CLAUDE_PLUGIN_ROOT}` 는 이 본문에서 텍스트로 치환되지 않으니 문자 그대로 쓰지 말 것 (Bash 변수로만 유효). dcness self 저장소면 cwd 상대경로 그대로다. **경로가 안 잡혀도 "차단된 인프라 경로"로 단정하고 포기하지 말 것** — file guard 는 활성 plugin 의 `agents/**` 와 지정 `docs/plugin/**` Read 를 허용한다.

첫 행동:

1. [`docs/plugin/agents/designer/designer-agent.md`](../docs/plugin/agents/designer/designer-agent.md)를 읽는다.
2. 대상 화면이나 컴포넌트, UX 목표를 확인한 뒤 static HTML 시안을 만든다.
3. HTML 시안은 [`templates/html-variant.md`](../docs/plugin/agents/designer/templates/html-variant.md)를 참고한다.
