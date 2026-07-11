# Architecture Cartography fixture

> 이 root는 capability와 runtime entrypoint만 라우팅한다. Story 상세, 구현 순서, 상세 topology는 각 epic architecture가 소유한다.

## Runtime entrypoint routes

| 변경 목적 / trigger | 시작 entrypoint (실제 repo-relative 경로) | flow owner | 다음 경계 | 상태 | 상태 증거 | 관련 상세 지도 | 전역 결정 |
|---|---|---|---|---|---|---|---|
| SMS 수신 | `app/src/main/kotlin/example/sms/SmsReceiver.kt` | SmsIngress | MessageStore | landed | `app/src/test/kotlin/example/sms/SmsReceiverTest.kt` dispatch contract | [epic-01 seam](docs/epics/epic-01-sms/architecture.md) | [ADR-0001](docs/decisions/0001-message-routing.md) |
| MMS WAP push 수신 | `app/src/main/kotlin/example/mms/MmsWapPushReceiver.kt` | MmsIngress | 기존 SmsIngress seam | stub | class seam only | [epic-01 seam](docs/epics/epic-01-sms/architecture.md), [epic-02 detail](docs/epics/epic-02-mms/architecture.md) | [ADR-0001](docs/decisions/0001-message-routing.md), [ADR-0002](docs/decisions/0002-mms-transport.md) |
| MMS 송신 | `app/src/main/kotlin/example/mms/MmsSender.kt` | MmsTransport | platform carrier API | stub | class seam only | [epic-02 detail](docs/epics/epic-02-mms/architecture.md) | [ADR-0002](docs/decisions/0002-mms-transport.md) |

## Capability routes

| capability | owner | code root | 상태 | 상세 지도 | 결정 |
|---|---|---|---|---|---|
| message ingress | SmsIngress | `app/src/main/kotlin/example/sms/` | landed | [epic-01](docs/epics/epic-01-sms/architecture.md) | [ADR-0001](docs/decisions/0001-message-routing.md) |
| MMS transport | MmsTransport | `app/src/main/kotlin/example/mms/` | stub | [epic-02](docs/epics/epic-02-mms/architecture.md) | [ADR-0002](docs/decisions/0002-mms-transport.md) |

## 의존 그래프

- `app-root --> data`: `app/src/main/kotlin/example/App.kt`가 시작 시 `app/src/main/kotlin/example/data/MessageObserver.kt`를 시작한다.
- ingress owner는 저장 경계만 호출하고 platform receiver에 제품 상태를 붙이지 않는다.

## 도메인 용어 포인터

- 메시지 envelope: [ADR-0001](docs/decisions/0001-message-routing.md)

## 전역 gotcha

- Application lifecycle이 data observer를 시작하는 as-built edge를 설계 graph에서 누락하지 않는다. 근거는 `app/src/main/kotlin/example/App.kt`다.
- Android receiver 자격과 class seam만 존재하면 `stub`이며 제품 동작이 아니다.

## Root 갱신 조건

- runtime entrypoint, capability owner, 전역 decision, 상태 또는 전역 금지 방향이 바뀔 때 갱신한다.
- Story 매핑, 구현 순서, epic-local topology만 바뀌면 해당 epic architecture만 갱신한다.
