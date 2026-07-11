# 익명 메시지 mirror 설계 초안

## Stories

- Story 1: 외부 Provider의 메시지를 Room mirror로 가져와 timeline에 표시한다.
- Story 2: Provider의 동일 row가 Pending에서 Sent/Failed로 바뀌면 같은 timeline bubble의 상태 배지가 바뀐다.
- Story 3: 두 source의 메시지를 합치며 한 source read가 실패해도 그 source의 마지막 성공 상태를 보존한다.

## architecture/decision

- `(source_id, provider_row_id)`가 mirror identity이고 status를 포함한 나머지는 mutable projection이다.
- source별 성공 snapshot은 transaction에서 insert/update/delete하며, 동일 identity의 projection 차이는 전체 update한다.
- 성공한 empty snapshot만 해당 source rows를 delete한다. read failure source는 기존 rows를 보존하고 다른 성공 source만 반영한다.
- duplicate observer event와 같은 snapshot 반복은 no-change다. source별 reconcile은 직렬화되어 concurrent run도 같은 결과로 수렴한다.
- observer/provider-gateway가 snapshot을 생산하고 mirror-store가 state/write owner이며 timeline-ui가 `timeline()` read model을 소비한다.

## impl task

1. `mirror-sync` (`src/mirror-store/`, `src/provider-gateway/`, `src/timeline-ui/`): source별 insert/full update/delete, failure preservation, duplicate/concurrent idempotence와 최초 import의 timeline 표시를 연결한다. owner/entrypoint 요약과 import→mirror→timeline integration acceptance가 위 decision을 가리킨다.
2. `status-badge` (`src/timeline-ui/`, `depends_on: [mirror-sync]`): mirror-store가 생산한 same-identity status transition을 소비한다. owner/entrypoint 요약과 actual observer→mirror→timeline integration test가 있다.
3. `multi-source` (`src/provider-gateway/`, `src/mirror-store/`, `depends_on: [mirror-sync]`): source partition, partial failure preservation, repeated no-change를 검증한다.

각 task scope는 필요한 producer/owner/consumer wiring을 허용하며 module/decision 링크와 실행 가능한 validation path가 있다.
