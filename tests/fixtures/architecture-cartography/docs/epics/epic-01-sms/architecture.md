# SMS architecture

## 모듈 목록

| 모듈 | 책임 | 의존 모듈 | 공개 인터페이스 | 검증 경로 | 결정 |
|---|---|---|---|---|---|
| SmsIngress | SMS receive owner | MessageStore | `receiveSms(intent)` | receiver contract test | [ADR-0001](../../decisions/0001-message-routing.md) |

## 의존 그래프

- SmsReceiver -> SmsIngress -> MessageStore

## Story -> 모듈 매핑

| Story | 모듈 | 이유 |
|---|---|---|
| 1 | SmsIngress | SMS 수신 구현 순서와 상세 seam은 이 epic이 소유한다. |
