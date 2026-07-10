# 0001 — Provider 진본 + 로컬 mirror reconcile

## 결정

- 외부 Provider 가 메시지 진본(SSOT)이고 로컬 DB 는 read mirror 다.
- identity(reconcile key) 는 (source, sourceId) 로 유지한다.
- provider-gateway 의 observer 가 Provider 변경을 감지하면 mirror-store 의 `reconcile(source, snapshot)` 이 호출되어 mirror 가 진본에 수렴한다.

## reconcile 규칙

- 신규 identity 는 전체 필드(status/box/body/timestamp/threadId/read)로 insert 한다.
- 같은 identity 에서는 threadId/body/timestamp/box/status/read 를 비교해 하나라도 달라지면 전체 projection 을 update 한다 — 발신 상태 Pending → Sent/Failed 전이가 이 경로로 배지에 반영된다.
- source 별 snapshot 은 같은 source 의 mirror row 만 insert/update/delete 한다.
- source read 실패는 empty 와 다르다 — 해당 source 의 기존 mirror 를 보존하고 sync 결과만 실패로 기록한다.
- 같은 snapshot 을 반복 적용하면 두 번째 실행은 no-change 다 (idempotent).

## 버린 대안

- 전체 재적재(full reload): 매 변경마다 전체 삭제 후 재삽입은 스크롤 위치 유실과 배지 깜빡임을 만들어 버림.
