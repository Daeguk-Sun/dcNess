---
epic: epic-01-read-receipt-toggle
milestone: v01
---

# Story Backlog

## Epic — 읽음 표시 끄기

**목표**: 사용자가 읽음 표시를 켜거나 끄고, 그 선택대로 대화 화면이 동작한다.
**완료 기준**:
1. [command] 선택을 꺼짐으로 바꾼 뒤 메시지를 읽고 상대 화면을 확인하는 journey smoke 가 종료코드 0으로 끝난다.
2. [command] 선택 값 저장 실패와 불러오기 실패 contract test 가 종료코드 0으로 끝난다.

선택 1개와 그 동작을 한 번에 검증해야 하므로 이 eval fixture 는 의도적으로 단일 Story 를 유지한다.

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

### Story 1 — 읽음 표시 선택과 대화 화면 동작

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 대화를 쓰는 사용자,
**I want** 읽음 표시를 켜거나 끄길,
**So that** 메시지를 읽었다는 사실을 상대에게 알릴지 내가 정할 수 있다.

**Acceptance criteria:**
- AC-001 [command]: Given 선택을 바꾼 적 없는 사용자, When 설정 화면을 열면, Then 읽음 표시 선택이 켜짐으로 보이고 안내 문구 한 줄이 함께 보인다.
- AC-002 [command]: Given 선택이 켜짐인 두 사용자, When 한 사용자가 메시지를 읽으면, Then 보낸 사용자의 대화 화면에 읽음 표시가 나타난다.
- AC-003 [command]: Given 선택이 꺼짐인 사용자, When 그 사용자가 1:1 대화 또는 그룹 대화의 메시지를 읽으면, Then 상대의 대화 화면에 읽음 표시가 나타나지 않는다.
- AC-004 [command]: Given 선택이 꺼짐인 사용자와 선택이 켜짐인 상대, When 상대가 그 사용자의 메시지를 읽으면, Then 그 사용자의 대화 화면에 읽음 표시가 나타나지 않는다.
- AC-005 [command]: Given 읽음 표시가 이미 나타난 메시지, When 읽은 사용자가 선택을 꺼짐으로 바꾸면, Then 이미 나타난 읽음 표시는 그대로 남는다.
- AC-006 [command]: Given 한 기기에서 선택을 바꾼 사용자, When 같은 계정의 다른 기기에서 설정 화면을 열면, Then 바뀐 값이 보인다.
- AC-007 [command]: Given 선택 값 저장이 실패하는 상태, When 사용자가 선택을 바꾸면, Then 선택이 이전 값으로 돌아가고 오류 문구와 다시 시도 동선이 보인다.
- AC-008 [command]: Given 선택 값을 불러오지 못하는 상태, When 사용자가 대화 화면을 열면, Then 마지막으로 확인한 값으로 동작한다.
