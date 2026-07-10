# epic-01 architecture (최소형)

## 모듈 목록

| module | 책임 | 공개 인터페이스 |
|---|---|---|
| provider-gateway | Provider 조회, 변경 감지(observer 등록) | `observeMessages()`, `queryMessages()` |
| mirror-store | 로컬 mirror 저장과 reconcile (full projection update, source 실패 보존, 반복 no-change) | `reconcile(source, snapshot)`, `timeline()` |
| timeline-ui | 타임라인 화면, 상태 배지 렌더 | `TimelineScreen` |

의존 차단: 모듈별 public 패키지만 노출(언어 가시성). DI 는 생성자 주입.

## 의존 그래프

timeline-ui → mirror-store → provider-gateway

## Story -> 모듈 매핑

- Story 1: provider-gateway + mirror-store + timeline-ui — 첫 제품 경계 동작: 앱 실행 후 타임라인에 Provider 메시지 표시
- Story 2: timeline-ui — mirror status 값 기준 상태 배지 렌더 (same-identity status 전이는 Story 1 의 reconcile 규칙이 update 능력으로 보장)

## Domain Model

- 생략 판단: 엔티티 1개(메시지 projection), 도메인 규칙은 decision 0001 로 충분 — 낮은 도메인 복잡도로 domain-model.md 생략.
