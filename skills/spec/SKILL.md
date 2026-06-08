---
name: spec
description: 새 기능 / PRD 변경 / 큰 기획을 시작하는 public entrypoint. 사용자가 "/spec", "스펙 작성", "PRD 작성", "기획해줘", "새 기능 스펙" 등을 말할 때 사용한다. 실제 절차는 내부 절차 파일 `skills/product-plan/SKILL.md` 를 그대로 따른다.
---

# Spec Skill — public entrypoint

`/spec` 는 기본 workflow surface 의 public entrypoint 다. 내부 절차는 `skills/product-plan/SKILL.md` 에 둔다.

## 실행 규칙

1. [`../product-plan/SKILL.md`](../product-plan/SKILL.md)를 읽고 그 절차를 그대로 따른다.
2. [`../product-plan/product-plan-routing.md`](../product-plan/product-plan-routing.md)를 라우팅 SSOT로 사용한다.
3. `/spec` 완료 전 `product-acceptance:SPEC_ACCEPTANCE` 체크포인트를 수행한다.
4. GitHub issue 번호가 대상이면 product-plan 진입 전 [`../../docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#github-project-status-lifecycle)에 따라 Project `Status=In progress` 로 이동한다.

## 범위

- 본 skill 은 현재 기본 workflow surface 의 `/spec` entrypoint 다.
- 기본 lifecycle surface 는 `/spec -> /design -> /impl -> /acceptance` 다. `/spec` 는 PRD / Epic / Story / AC 정의와 `SPEC_ACCEPTANCE` 까지를 담당하고, product/technical design 은 `/design` 으로 넘긴다.
- full E2E 검증은 `/spec` 이행 범위 밖이며 release/product acceptance 고도화 후속이다.
