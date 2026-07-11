# MMS architecture

## 모듈 목록

| 모듈 | 책임 | 의존 모듈 | 공개 인터페이스 | 검증 경로 | 결정 |
|---|---|---|---|---|---|
| MmsIngress | WAP push owner; SmsIngress seam 재사용 | SmsIngress | `receiveMms(wapPush)` | WAP push contract test | [ADR-0001](../../decisions/0001-message-routing.md), [ADR-0002](../../decisions/0002-mms-transport.md) |
| MmsTransport | carrier API owner | platform API | `sendMms(envelope)` | carrier adapter test | [ADR-0002](../../decisions/0002-mms-transport.md) |

## 의존 그래프

- MmsWapPushReceiver -> MmsIngress -> SmsIngress seam
- MmsSender -> MmsTransport -> platform carrier API

## Story -> 모듈 매핑

| Story | 모듈 | 이유 |
|---|---|---|
| 1 | MmsIngress | WAP push 상세 구현 순서 |
| 2 | MmsTransport | MMS 송신 상세 구현 순서 |
