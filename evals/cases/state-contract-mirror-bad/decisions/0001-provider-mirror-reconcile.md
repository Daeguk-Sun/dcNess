# 0001 — Provider 진본 + 로컬 mirror reconcile

## 결정

- 외부 Provider 가 메시지 진본(SSOT)이고 로컬 DB 는 read mirror 다.
- identity 는 (source, sourceId) 로 유지한다.
- provider-gateway 의 observer 가 Provider 변경을 감지하면 mirror-store 의 `reconcile(snapshot)` 이 호출되어 mirror 가 진본에 수렴한다.

## reconcile 규칙

- Provider snapshot 과 mirror 의 identity 존재 여부를 비교해, 신규 identity 는 전체 필드(status/box/body/timestamp/threadId/read)로 insert 한다.
- 이미 존재하는 identity 에서는 read(읽음) 플래그 변경만 update 한다.
- status/box/body/timestamp/threadId 필드는 존재하는 identity 에서 비교하지 않는다.
- snapshot 에 없는 identity 는 delete 한다.

## 버린 대안

- 전체 재적재(full reload): 매 변경마다 전체 삭제 후 재삽입은 스크롤 위치 유실과 배지 깜빡임을 만들어 버림.
