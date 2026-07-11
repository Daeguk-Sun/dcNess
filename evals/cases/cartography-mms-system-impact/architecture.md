# Architecture Cartography

## Runtime entrypoint routes

| trigger | entrypoint | owner | state | evidence | epic/decision |
|---|---|---|---|---|---|
| SMS receive | `app/src/main/kotlin/example/sms/SmsReceiver.kt` | SmsIngress | landed | receiver integration test | epic-01 / ADR-0001 |

## Dependency graph

- SmsReceiver → MessageStore
