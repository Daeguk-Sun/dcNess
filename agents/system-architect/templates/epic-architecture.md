# Epic Architecture

## 사전 준비

- 읽을 문서:
  - `docs/index.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/conventions.md`
  - `docs/decisions/`
  - `docs/epics/<epic>/stories.md`
  - `docs/epics/<epic>/domain-model.md`
- 읽을 코드:
  -

## 전역 map 반영

- `docs/architecture.md` append 필요 여부:
- 추가/갱신할 전역 anchor:
- 연결할 `docs/decisions/NNNN-slug.md`:

## 모듈 목록

<!-- `$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs` 가 이 표를 파싱한다. 헤더명과 표 형태를 유지한다. -->

| 모듈 | 책임 | 의존 모듈 | 공개 API | 테스트 단위 |
|---|---|---|---|---|
|  |  |  |  |  |

## 의존 그래프

```mermaid
flowchart LR
```

## Contract Ledger

<!-- `$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs` 가 공유 계약 인덱스로 수집한다. 헤더명과 표 형태를 유지한다. -->

| contract | owner | producer | consumer | invariant | ordering | error mode | config | forbidden alternative | refs |
|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |

## Decisions

| Decision | Scope | Reason |
|---|---|---|
|  |  |  |

## 공통 task 후보

| task | 이유 | 선행 조건 |
|---|---|---|
|  |  |  |

## Story -> 모듈 매핑

| Story | 영향 모듈 | 이유 |
|---|---|---|
|  |  |  |

## 구현 순서

- 순서와 근거:
- 첫 제품 경계 동작 증거가 나오는 시점:
- 부품-먼저 순서면 경고와 사유:

## Module Design Check

- Deep module:
- 작은 공개 노출 범위:
- DI/의존 차단:
