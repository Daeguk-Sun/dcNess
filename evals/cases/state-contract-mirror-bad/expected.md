# 정답표 — 계약 수준

검수 보고를 채점할 때 아래 기대만 본다. 어떤 검수자가 어떤 문구로 말했는지, finding 이 몇 개인지는 채점하지 않는다.

- [E1][MUST] 보고가 "이미 존재하는 identity 의 가변 상태(status) 변경을 reconcile 이 비교/update 하지 않아 Pending → Sent/Failed 전이가 mirror(와 배지)에 반영되지 않는다"는 취지의 결함을 지적한다.
- [E2][MUST] 보고가 "observer 로 수렴한다는 서술만으로 실제 status update 경로를 대신할 수 없다" 또는 "그 update 를 구현할 task 가 없고 Story 2 task 의 scope(수정 금지: mirror-store)로는 gap 을 고칠 수 없다"는 취지의 결함을 지적한다.
- [E3][MUST] 최종 결론이 통과(PASS)가 아니다.
