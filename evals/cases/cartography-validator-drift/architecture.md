# Architecture Cartography

## Runtime entrypoint routes

| trigger | entrypoint | owner | next boundary | state | evidence |
|---|---|---|---|---|---|
| SMS receive | `app/src/main/kotlin/example/SmsReceiver.kt` | SmsIngress | MessageStore | landed | SmsReceiverTest |

## Dependency graph

- SmsReceiver → MessageStore
