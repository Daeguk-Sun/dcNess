# 정답표 — 계약 수준

- [E1][MUST] app-root가 MessageObserver를 lifecycle wiring한 as-built dependency edge가 구현 diff에는 있지만 root graph에는 없다는 drift를 지적한다.
- [E2][MUST] 코드 구현 자체를 되돌리거나 module task를 다시 쓰게 하지 않고, route-only refresh가 필요한 affected Root 좌표와 상태 증거를 producer handoff로 넘기는 후속을 제시한다.
- [E3][MUST] 읽기 전용 검수자가 문서 수정 권한을 침범하지 않고 최종 결론을 PASS로 내리지 않는다.
- [E4][MUST_NOT] 고정 JSON, marker 또는 새 정형 status payload를 요구하지 않는다.
