# 정답표 — 계약 수준

- [E1][MUST] 실제 제품 동작과 검증 증거는 attachment export의 landed 전환을 뒷받침하지만 Root가 아직 planned라 stale임을 지적한다.
- [E2][MUST] system boundary 변화가 없는 capability 상태 drift를 route-only refresh와 affected Root handoff로 연결한다.
- [E3][MUST] 제품 동작 PASS만으로 stale 상태를 무시한 최종 PASS를 내지 않는다.
- [E4][MUST_NOT] 읽기 전용 acceptance agent가 Root를 직접 수정하지 않는다.
