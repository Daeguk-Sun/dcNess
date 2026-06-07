---
name: design
description: product/technical design 을 `/architect-loop` 호환 흐름으로 시작하는 public alias. 사용자가 "/design", "설계해줘", "product design", "technical design", "기술 설계" 등을 말할 때 사용한다. visual design 단독 요청은 `/ux` 가 더 적합하며, 본 alias 는 설계 전체를 뜻한다.
---

# Design Skill — architect-loop 호환 alias

`/design` 은 `/architect-loop` 의 public alias 다. 여기서 design 은 visual design 만이 아니라 product/technical design, 즉 PRD 이후 구현 전 설계 전체를 뜻한다.

## 실행 규칙

1. [`../architect-loop/SKILL.md`](../architect-loop/SKILL.md)를 읽고 그 절차를 그대로 따른다.
2. [`../architect-loop/architect-loop-routing.md`](../architect-loop/architect-loop-routing.md)를 라우팅 SSOT로 사용한다.
3. loop contract 의 `begin-run` 인자는 `begin-run architect-loop` 로 유지한다.
4. entry_point = `architect-loop` 를 사용하고 `design` 으로 시작하지 않는다. `harness/hooks.py` 의 architect-loop gate 가 exact entry point 를 기준으로 동작하기 때문이다.
5. 기존 `/architect-loop` 사용자는 그대로 호환된다. `/design` 추가가 `/architect-loop` 제거를 뜻하지 않는다.

## 범위

- 본 alias 는 #645의 분해 PR 중 `/design` entrypoint 추가 단계다.
- 기본 workflow surface flip(`/spec -> /design -> /impl -> /acceptance`)은 후속 #645 PR에서 처리한다.
- visual design 단독 보강이나 화면 시안 핸드오프는 `/ux` 흐름이 담당한다.
