---
design: optional
story: 1
task_index: 1/2
depends_on: []
---

# 01-mirror-sync

## 사전 준비

- 읽을 문서: `stories.md` (Story 1), `architecture.md`, `decisions/0001-provider-mirror-reconcile.md`

## 무엇을 만드나

- Provider 메시지를 mirror 로 import 하고 observer 변경 시 decision 0001 의 reconcile 규칙(full projection update, source 실패 보존, 반복 no-change)대로 수렴시킨다. Story 1 완료 시 타임라인에 Provider 메시지가 보인다.
- 제품 경계: 앱 실행 후 타임라인 화면 첫 표시.
- 첫 동작 증거 지점: 타임라인에 Provider 메시지 렌더.

## 왜 만드나

- PRD M1. 동작 슬라이스 우선 — import 와 화면 표시를 한 task 묶음으로 닫는다. Story 2 가 소비하는 same-identity status 전이 update 능력도 이 task 의 reconcile 이 생산한다.

## Scope

### 수정 허용

- `src/mirror-store/`
- `src/provider-gateway/`

### 수정 금지

- `src/timeline-ui/`

## 인터페이스

- 계약/결정 링크:
  - module: mirror-store, provider-gateway (`architecture.md` 모듈 목록)
  - decision: `decisions/0001-provider-mirror-reconcile.md`
- owner/entrypoint 요약:
  - owner flow/module: mirror-store
  - entrypoint role: observer 콜백 → reconcile dispatch
  - state owner: mirror-store (로컬 mirror rows)
  - validation path: `./gradlew :mirror-store:test`

## 수용 기준

| REQ | 내용 | 검증 명령 | 통과 조건 |
|---|---|---|---|
| REQ-001 | 신규 identity 전체 필드 insert | `(TEST) ./gradlew :mirror-store:test --tests ReconcileInsertTest` | green |
| REQ-002 | 같은 identity 의 status 변경(Pending→Sent) 이 full projection update 로 반영 | `(TEST) ./gradlew :mirror-store:test --tests ReconcileStatusUpdateTest` | green |
| REQ-003 | source read 실패 시 해당 source 기존 mirror 보존 | `(TEST) ./gradlew :mirror-store:test --tests ReconcileFailurePreserveTest` | green |
| REQ-004 | 같은 snapshot 반복 적용 시 no-change | `(TEST) ./gradlew :mirror-store:test --tests ReconcileIdempotenceTest` | green |

## 주의사항

- 모듈 설계 주의: reconcile 로직은 mirror-store 내부에 숨기고 공개 인터페이스는 `reconcile(source, snapshot)`/`timeline()` 만 유지.
