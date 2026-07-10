# PRD — 메시지 타임라인 (발췌)

외부 Provider 저장소가 메시지의 진본(SSOT)이고, 앱 로컬 DB 는 화면 표시용 read mirror 다.

## Must

- M1. 사용자는 타임라인 화면에서 Provider 메시지 목록을 본다 (Provider → mirror import).
- M2. 사용자가 보낸 메시지는 전송 진행(Pending) → 전송 완료(Sent) 또는 실패(Failed) 상태가 같은 메시지 버블의 배지에 반영된다. 발신 상태는 Provider 의 같은 row 의 status 필드 변경으로 표현된다.

## 화면 인벤토리 + 대략적 플로우

- 타임라인 화면 1개. 메시지 버블에 상태 배지(Pending/Sent/Failed)가 붙는다.
