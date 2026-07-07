# Epic Architecture

## 사전 준비

- 읽을 문서:
  - `docs/index.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/conventions.md`
  - `docs/decisions/`
  - `docs/modules/<module-id>/architecture.md` (affected module 이 있으면)
  - `docs/modules/<module-id>/conventions.md` (affected module 이 있으면)
  - `docs/epics/<epic>/stories.md`
  - `docs/epics/<epic>/domain-model.md` (있으면)
- 읽을 코드:
  -

## Domain Model

- `domain-model.md` 작성 여부:
- 생략 판단 근거 (생략 시 필수):
- 작성 필요 신호 (invariant / entity / value object / aggregate / domain service):

## 모듈 목록

> durable 설계 진본이다. cross-task 불변조건, forbidden append, flow/state owner, 공개 entrypoint 책임은 해당 모듈의 `책임` 또는 `공개 인터페이스` 칸에 한 줄로 둔다. 긴 사유와 대안 폐기는 `docs/decisions/NNNN-slug.md` 로 분리하고 이 표에는 decision id/link 만 남긴다.

| 모듈 | 책임 | 의존 모듈 | 공개 인터페이스 | 검증 경로 | 결정 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 의존 그래프

```mermaid
flowchart LR
```

## Story -> 모듈 매핑

| Story | 영향 모듈 | 첫 제품 경계 동작 증거 | 이유 |
|---|---|---|---|
|  |  |  |  |
