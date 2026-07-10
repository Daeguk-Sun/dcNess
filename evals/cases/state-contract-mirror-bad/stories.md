# stories — epic-01 메시지 타임라인

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

## Story 1 — 타임라인 mirror import

- Provider 의 메시지를 로컬 mirror 로 가져와 타임라인에 표시한다.
- Provider 변경은 observer 가 감지해 mirror 가 진본에 수렴한다.
- 완료 동작: 타임라인 화면에서 Provider 메시지가 보인다.

## Story 2 — 발신 상태 표시

- 발신 메시지는 Provider 에 Pending 상태 row 로 기록되고, 전송 결과에 따라 같은 row 의 status 필드가 Sent 또는 Failed 로 바뀐다.
- 완료 동작: 같은 메시지 버블의 상태 배지가 Pending → Sent/Failed 로 갱신된다.
