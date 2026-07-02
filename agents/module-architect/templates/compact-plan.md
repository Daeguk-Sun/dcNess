---
depth: standard
design: optional|required
story: compact
issue: <optional>
contract:
  produces:             # Ledger row keys only when this plan changes a cross-task/public contract
  consumes:             # Ledger row keys only
---

# Compact Implementation Plan

## 사전 준비

- 읽을 문서:
  - `docs/index.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/conventions.md`
  - `docs/decisions/`
- 읽을 코드:
  -

## 배경 / 문제

-

## 수정 범위

### 수정 허용

-

### 수정 금지

-

## 변경 방향

-

## 디자인 참조

> `design: required` 이거나 UI 기준 확보 분기가 `기준 있음` / `신규 시각 구조 + 기준 없음` 으로 판정된 compact plan 은 확정 목업 경로와 핵심 node-id 매핑을 적는다. `design: optional` 이고 시각 구조 불변이면 `해당 없음` 으로 명시한다.

- 확정 목업 경로: `docs/design-variants/<screen-id>.html` 또는 해당 없음
- canvas 경로: `docs/design-variants/canvas.html` 또는 해당 없음
- 핵심 `data-node-id` → 구현 컴포넌트/상태:
  - `<screen-id>.<node>` → `<component or state>`
- 목업 대비 의도적 차이:
  -

## Contract References

> Cross-task/public contract details live only in the relevant epic `architecture.md` `## Contract Ledger` or root architecture decision link.
> Use Ledger row keys only here; do not copy invariant, ordering, error mode, config, or forbidden alternative.

| kind | Ledger row key | action | note |
|---|---|---|---|
| produces |  | new/update/existing | Ledger updated or not applicable |
| consumes |  | existing |  |

## 테스트 기준

-

## 수용 기준

| REQ | 내용 | 검증 | 통과 조건 |
|---|---|---|---|
| REQ-001 |  |  |  |

## 승격 신호

- 새 외부 dependency/API/SDK/model 필요:
- auth/security/PII/compliance 영향:
- migration/destructive/public API breakage:
- cross-module/cross-story contract 변화:

위 항목 중 하나라도 실제로 필요하면 compact plan 을 확정하지 말고 경량 범위 초과 → full 설계(`/design`) escalate 를 보고한다.
