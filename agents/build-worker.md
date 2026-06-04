---
name: build-worker
description: >
  /impl-loop 경량 엔진에서 테스트, 구현, 자체 검증을 한 번에 수행하는 에이전트.
  실제 지침은 agents/build-worker/build-worker-agent.md 에 있다.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
---

# build-worker

이 파일은 기존 `agents/build-worker.md` 소비자를 위한 호환 entrypoint다.

첫 행동:

1. [`agents/build-worker/build-worker-agent.md`](build-worker/build-worker-agent.md)를 읽는다.
2. build-test, build-impl, build-validate 세 phase 산출물을 반드시 남긴다.
3. 완료 보고와 PR 본문 초안은 [`templates/build-worker-report.md`](build-worker/templates/build-worker-report.md)를 참고한다.

## 작업 흐름 — 3 phase + helper self-call

상세 지침은 [`build-worker-agent.md`](build-worker/build-worker-agent.md#작업-흐름)에 있다. 세 phase의 목적은 RED 확인, GREEN 구현, 자체 검증 증거를 분리해 남기는 것이다.

## 권한 경계 (catastrophic)

상세 지침은 [`build-worker-agent.md`](build-worker/build-worker-agent.md#권한-경계)에 있다. build-worker는 코드와 테스트만 다루며 git, PR, pr-reviewer 호출은 메인이 처리한다.
