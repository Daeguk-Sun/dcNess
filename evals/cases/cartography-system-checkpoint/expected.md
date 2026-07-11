# 정답표 — 계약 수준

- [E1][MUST] landed public REST boundary를 제거하고 capability owner를 바꾸는 diff는 route-only refresh가 아니라 system boundary와 global decision 변경이라고 지적한다.
- [E2][MUST] affected Root 좌표만 고쳐 통과시키지 않고 기존 system checkpoint 또는 `/design` backpressure가 필요하다고 보고한다.
- [E3][MUST] 읽기 전용 검수자가 코드나 문서를 직접 수정하지 않고 최종 결론을 PASS로 내리지 않는다.
