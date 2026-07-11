# 정답표 — 계약 수준

- [E1][MUST] design(planned/stub) 상태가 초기 설계 증거에 맞고 구현 뒤 실제 제품 증거로 landed가 됐음을 추적한다.
- [E2][MUST] stale Root가 발견된 최초 code validation은 merge 진행이 아니라 bounded refresh와 재검증으로 이어져야 한다고 판정한다.
- [E3][MUST] refresh가 affected route/state/as-built edge만 갱신하고 system boundary나 global decision을 바꾸지 않았음을 확인한다.
- [E4][MUST] refresh 뒤 같은 merge candidate diff와 갱신 Root를 code revalidation하여 freshness가 해소됐고, 제품 동작·검증 증거와 Root landed 상태가 일치하므로 acceptance를 통과할 수 있다고 판정한다.
- [E5][MUST] 다음 design이 이전 상태를 그대로 신뢰하지 않고 affected capability/entrypoint를 현재 코드와 Cartography에 재대조했음을 확인한다.
- [E6][MUST] 전체 trace가 `design → impl → code validation → bounded refresh → code revalidation → acceptance → 다음 design` 순서로 닫혔으면 최종 PASS로 판정한다.
- [E7][MUST_NOT] boundary 변화가 없는 trace를 system 재설계로 과장하지 않는다.
