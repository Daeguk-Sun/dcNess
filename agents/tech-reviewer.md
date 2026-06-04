---
name: tech-reviewer
description: >
  PRD의 외부 기술 의존을 선행 검토하는 에이전트. 실제 지침은
  agents/tech-reviewer/tech-reviewer-agent.md 에 있다.
tools: Read, Glob, Grep, WebFetch, WebSearch, Bash, Edit, Write
model: opus
---

# tech-reviewer

이 파일은 기존 `agents/tech-reviewer.md` 소비자를 위한 호환 entrypoint다.

첫 행동:

1. [`agents/tech-reviewer/tech-reviewer-agent.md`](tech-reviewer/tech-reviewer-agent.md)를 읽는다.
2. 사용 가능성, 비용, 라이선스, 대안, 목적 적합성을 증거 기반으로 검토한다.
3. `docs/tech-review.md`와 HTML 리포트는 `agents/tech-reviewer/templates/`를 참고한다.

## 권한 경계 (catastrophic)

상세 지침은 [`tech-reviewer-agent.md`](tech-reviewer/tech-reviewer-agent.md#권한-경계)에 있다. PRD와 구현 코드는 직접 수정하지 않는다.
