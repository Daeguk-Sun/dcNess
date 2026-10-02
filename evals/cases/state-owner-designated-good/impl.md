# 05-leave-room

## 무엇을 만드나

대화방 화면 상단 막대에 "대화방 나가기" 메뉴를 추가한다. 메뉴를 누르면 확인 dialog 를 띄우고, 확인하면 서버에 나가기를 요청한 뒤 대화 목록으로 돌아간다.

나가기 흐름의 상태(dialog 표시 여부, 요청 중 여부, 실패 메시지)는 상단 막대의 다른 메뉴 상태와 마찬가지로 상단 막대 ViewModel(`RoomTopBarViewModel`)이 관리한다.

## Agent Workability

- owner flow/module: `feature/room/topbar`
- allowed touch: `feature/room/topbar/**`, `data/room/RoomRepository.kt`
- validation path: `feature/room/topbar` 단위 테스트

## Scope

### 수정 허용

- `feature/room/topbar/**`
- `data/room/RoomRepository.kt`

### 수정 금지

- 대화 목록 화면

## 수용 기준

| REQ | 내용 | 검증 | 통과 조건 |
|---|---|---|---|
| REQ-001 | 나가기 메뉴를 누르면 확인 dialog 가 열린다 | unit test | dialog 표시 상태가 참 |
| REQ-002 | 확인하면 서버 요청 후 대화 목록으로 이동한다 | unit test | 나가기 요청 후 대화 목록 이동 이벤트 |
| REQ-003 | 서버 요청이 실패하면 오류를 표시하고 화면에 머문다 | unit test | 오류 메시지 존재, 이동 이벤트 없음 |
