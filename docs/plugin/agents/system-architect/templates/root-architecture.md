# 전역 아키텍처 지도 (Cartography)

> 이 문서는 후속 agent가 변경 목적이나 외부 trigger에서 실제 코드와 상세 지도까지 이동하는 작은 Cartography router다. epic별 상세 topology, Story→모듈 매핑, 구현 순서, 계약 전문, Contract Ledger, 기술 스택 표를 복제하지 않는다.
> 기술 스택과 운영 convention 은 `docs/conventions.md`, 모듈 특수 delta 는 `docs/modules/<module-id>/`, 결정 기록은 `docs/decisions/NNNN-slug.md` 를 가리킨다.
> 여러 epic의 capability/owner 보조 뷰가 필요할 때만 `node "$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs"` 로 `.dcness-work/reports/architecture-map.md` 를 그 시점에 생성한다. 이 임시 리포트는 필수 agent 입력, checked-in freshness 진본, as-built 코드 증거가 아니다.

상태는 timestamp가 아니라 이동 가능한 증거로 판정한다.

- `landed`: 실제 repo-relative 코드 entrypoint와 제품 동작·검증 증거가 모두 존재한다.
- `stub`: manifest/플랫폼 자격 또는 후속 seam은 존재하지만 제품 동작은 아직 없다.
- `planned`: accepted epic/decision에 설계됐지만 실행 코드 entrypoint는 아직 없다.
- `deferred`: 후속 spec/design에서 경계를 다시 확정해야 하며 그 문서 포인터만 존재한다.
- 모든 코드 좌표는 agent가 바로 열 수 있는 실제 repo-relative 경로다. 축약된 디렉터리 표기나 존재하지 않는 예상 경로를 쓰지 않는다.

## 시스템 개요

-

## Runtime entrypoint routes

| 변경 목적 / 외부 trigger | 시작 entrypoint (실제 repo-relative 경로) | flow/capability owner | 다음 경계 | 상태 | 관련 epic | global decision |
|---|---|---|---|---|---|---|
|  |  |  |  | planned |  |  |

## Capability routes

| capability | owner | 실제 code root | 상태 | 상세 지도 | global decision |
|---|---|---|---|---|---|
|  |  |  | planned |  |  |

## 큰 모듈 경계

| 모듈 | 책임 | 공개 인터페이스 | 결정 |
|---|---|---|---|
|  |  |  |  |

## 의존 그래프

- 허용 방향과 금지 방향을 적고, 설계 문서와 실제 코드 wiring을 함께 읽어 as-built edge를 누락하지 않는다.

## 외부 경계

| 경계 | 방향 | 프로토콜 | 소유자 | 결정 |
|---|---|---|---|---|
|  |  |  |  |  |

## 도메인 용어 포인터

| 용어 | canonical owner | 상세 문서 |
|---|---|---|
|  |  |  |

## 전역 gotcha

- 반복적으로 잘못 구현되는 전역 wiring, lifecycle, 금지 경로와 실제 코드 근거를 적는다.

## Root 갱신 조건

- runtime entrypoint, stable capability owner, global decision, `landed/stub/planned/deferred` 상태, 전역 허용·금지 의존 방향, 도메인 용어 owner, 전역 gotcha가 바뀌면 root를 갱신한다.
- Story→모듈 매핑, 구현 순서, epic-local topology/계약 상세만 바뀌면 root를 갱신하지 않고 해당 epic architecture가 소유한다.
- `landed` 전환 전에는 실제 entrypoint와 제품 동작·검증 증거를 대조한다. 생성된 온디맨드 리포트의 행만으로 상태를 올리지 않는다.

## 결정 링크

- `docs/decisions/`
