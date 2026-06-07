---
name: spec
description: 새 기능 / PRD 변경 / 큰 기획을 `/product-plan` 호환 흐름으로 시작하는 public alias. 사용자가 "/spec", "스펙 작성", "PRD 작성", "기획해줘", "새 기능 스펙" 등을 말할 때 사용한다. 실제 절차는 `skills/product-plan/SKILL.md` 를 그대로 따른다.
---

# Spec Skill — product-plan 호환 alias

`/spec` 는 `/product-plan` 의 public alias 다. 새 기능의 PRD, stories, tech-review 스켈레톤을 만드는 동일한 흐름을 더 짧은 이름으로 노출한다.

## 실행 규칙

1. [`../product-plan/SKILL.md`](../product-plan/SKILL.md)를 읽고 그 절차를 그대로 따른다.
2. [`../product-plan/product-plan-routing.md`](../product-plan/product-plan-routing.md)를 라우팅 SSOT로 사용한다.
3. `/spec` 완료 전 `product-acceptance:SPEC_ACCEPTANCE` 체크포인트를 수행한다.
4. 기존 `/product-plan` 사용자는 그대로 호환된다. `/spec` 추가가 `/product-plan` 제거를 뜻하지 않는다.

## 범위

- 본 alias 는 현재 기본 workflow surface 의 `/spec` entrypoint 다.
- 기본 lifecycle surface 는 `/spec -> /design -> /impl -> /acceptance` 다. `/spec` 는 PRD / Epic / Story / AC 정의와 `SPEC_ACCEPTANCE` 까지를 담당하고, product/technical design 은 `/design` 으로 넘긴다.
- full E2E 검증은 `/spec` 이행 범위 밖이며 release/product acceptance 고도화 후속이다.
