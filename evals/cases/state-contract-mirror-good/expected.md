# 정답표 — 계약 수준

검수 보고를 채점할 때 아래 기대만 본다. 어떤 검수자가 어떤 문구로 말했는지는 채점하지 않는다. 이 케이스는 same-identity 가변 전이·source 실패 보존·반복 no-change 가 이미 닫힌 reconcile 설계를 같은 축에서 과잉 지적하지 않는가만 본다.

- [E1][MUST_NOT] 보고가 "같은 identity 의 status 전이가 mirror 에 반영되지 않는다"는 취지의 결함을 지적하지 않는다.
- [E2][MUST_NOT] 보고가 full projection update, source 실패 보존, 반복 no-change 로 닫힌 reconcile 구조 자체를 결함으로 지적하거나 그 이유만으로 system 재설계/checkpoint 를 요구하지 않는다.
