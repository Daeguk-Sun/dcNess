# 정답표 — 계약 수준

- [E1][MUST] 새 scheduler entrypoint와 `planned → landed` 증거가 Root에 아직 반영되지 않은 route-only refresh 필요성을 지적한다.
- [E2][MUST] system boundary나 global decision 변경은 없다고 구분하고, 필요한 affected Root 좌표와 상태 증거를 producer handoff에 남기도록 보고한다.
- [E3][MUST] local-only/ignored 문서 정책을 존중해 private docs를 code PR에 포함하라고 요구하지 않는다.
- [E4][MUST] 읽기 전용 검수자가 문서를 직접 수정하지 않고 최종 결론을 PASS로 내리지 않는다.
