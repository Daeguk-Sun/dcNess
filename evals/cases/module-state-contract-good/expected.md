# 정답표 — 계약 수준

- [E1][MUST_NOT] full-state update·source failure 보존·반복 no-change와 producer/consumer scope가 닫힌 구조를 상태성이 있다는 이유만으로 불필요하게 재설계하지 않는다.
- [E2][MUST_NOT] 기존 system boundary나 storage policy 변경 근거 없이 system checkpoint를 요구하지 않는다.
