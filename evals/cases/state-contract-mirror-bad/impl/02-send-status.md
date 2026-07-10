---
design: optional
story: 2
task_index: 2/2
depends_on: [01-mirror-sync]
---

# 02-send-status

## 사전 준비

- 읽을 문서: `stories.md` (Story 2), `architecture.md`, `decisions/0001-provider-mirror-reconcile.md`

## 무엇을 만드나

- 발신 메시지 버블에 상태 배지(Pending/Sent/Failed)를 렌더한다. Story 2 완료 시 같은 버블의 배지가 전송 결과에 따라 갱신된다.
- 제품 경계: 타임라인 화면의 상태 배지.
- 첫 동작 증거 지점: 발신 후 배지가 Pending → Sent 로 바뀜.

## 왜 만드나

- PRD M2. Provider 의 같은 row 의 status 필드가 Pending → Sent/Failed 로 바뀌면 observer 를 통해 mirror 에 수렴하므로, 화면은 mirror 의 `timeline()` 을 구독해 status 값 기준으로 배지를 그리면 된다.

## Scope

### 수정 허용

- `src/timeline-ui/`

### 수정 금지

- `src/mirror-store/`
- `src/provider-gateway/`

## 인터페이스

- 계약/결정 링크:
  - module: timeline-ui (`architecture.md` 모듈 목록)
  - decision: `decisions/0001-provider-mirror-reconcile.md`
- owner/entrypoint 요약:
  - owner flow/module: timeline-ui
  - entrypoint role: TimelineScreen 렌더
  - state owner: mirror-store (`timeline()` 구독)
  - validation path: `./gradlew :timeline-ui:test`

## 수용 기준

| REQ | 내용 | 검증 명령 | 통과 조건 |
|---|---|---|---|
| REQ-001 | mirror status 값 기준 배지 렌더 | `(TEST) ./gradlew :timeline-ui:test --tests StatusBadgeTest` | green |

## 주의사항

- 모듈 설계 주의: 배지 상태 판정은 timeline-ui 내부 mapper 로 숨긴다.
