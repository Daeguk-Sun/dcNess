# 익명 메시지 mirror 설계 초안

## Stories

- Story 1: 외부 Provider의 메시지를 Room mirror로 가져와 timeline에 표시한다.
- Story 2: Provider의 동일 row가 Pending에서 Sent/Failed로 바뀌면 같은 timeline bubble의 상태 배지가 바뀐다.
- Story 3: 두 source의 메시지를 합치며 한 source read가 실패해도 timeline을 제공한다.

## 현재 architecture/decision 초안

- Provider row id가 mirror identity다.
- reconcile은 처음 보는 id를 insert하고, 기존 id는 read flag가 다를 때만 update하며 snapshot에서 사라진 id를 delete한다.
- observer가 Provider 변경을 감지하면 mirror가 수렴한다.
- 여러 source snapshot을 합쳐 한 번에 reconcile한다. empty 결과와 read failure의 구분, source별 실패 처리는 정하지 않았다.

## 현재 impl task 초안

1. `mirror-sync` (`src/mirror-store/`, `src/provider-gateway/`, `src/timeline-ui/`): insert/read-flag update/delete와 observer dispatch, 최초 import의 timeline 표시를 연결한다. 검증은 insert/read/delete unit test와 import→mirror→timeline integration test다.
2. `status-badge` (`src/timeline-ui/`, `depends_on: [mirror-sync]`): mirror status를 읽어 배지를 렌더한다. `src/mirror-store/`는 수정 금지다.
3. `multi-source` (`src/provider-gateway/`, `depends_on: [mirror-sync]`): 두 source snapshot을 합쳐 기존 reconcile을 호출한다. 실패와 반복 실행 acceptance는 없다.

각 task에는 module link와 validation command가 있으나 produced/consumed transition은 따로 적지 않았다.
