# Entrypoint state transition fixture

- Before: `stub` — Android receiver 자격과 `app/src/main/kotlin/example/mms/MmsWapPushReceiver.kt` seam만 존재한다.
- After: `landed` — 같은 entrypoint에 decode → owner dispatch 제품 동작과 contract test 증거가 존재한다.
- Guard: class 또는 manifest entry만 존재하거나 온디맨드 architecture report에 행이 있다는 이유로 `landed`로 올리지 않는다.
